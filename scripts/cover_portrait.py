"""封面真实肖像合成（确定性，不经生图模型）。

为什么必须确定性：真人肖像禁止由生图模型生成（iron-rules §视觉 4 / image-routing.md
「优先使用可授权的真实新闻照，禁止生成相似人物肖像」）。让模型照着照片重画，出来的是
「像又不像」的假脸 —— 对活人是失真，对历史人物是伪造史料。所以 renderer 只出底板、
右区留空场，真实肖像由本脚本贴上去。这一层与 `add_logo.js` 打水印、`compress_images.py`
压缩同属封面既有的确定性后处理，凭证按 `stage` 记账。

版式由 2026-08-28 的实拍对照定案（作者选定 E3）：

- **满幅出血**：肖像顶右、顶上、顶下三边，不加描边、不留边框。
- **宽度按肖像自身比例反推**，而不是写死百分比：`宽 = 画布高 × 肖像宽高比`。
  这条是几何必然推出来的 —— 铺满整高时，若照片区比原图更宽，就必须裁掉上下，
  实测直接把发顶和下巴切掉（作者判为不可接受）。反推之后铺满整高也无需垂直裁切。
- **暖调映射**：纯黑白肖像压在深炭底上偏冷、偏肃穆（作者原话：像墓碑）。映射到
  「暖炭 → 暖象牙」的灰阶后年代感还在、肃穆感消失。**不做 AI 上色** —— 给历史人物
  上色等于编造肤色眼色。
- **左缘渐隐**：60px 线性渐隐，让照片融进底纹而不是硬切一条竖线。
- **右区清场**：贴图前先把右区抹回环境渐变。prompt 已明写「右区留空、不要画板」，
  模型照旧会画一块圆角面板；照片起点比它靠右时，板的左边缘会露出来像叠了两层。
  抹的时候取样列必须落在纯背景上（取最右侧 40 列的逐行中位数）—— 早先版本取画面
  中部一列，撞进标题笔画，从字里拖出一条横线穿到右边。

用法：

    python cover_portrait.py <文章目录>            # 就地合成 素材/cover.png
    python cover_portrait.py <文章目录> --check     # 只校验声明与素材，不写盘
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

# 版式常量（改这里等于改版式，别在调用处各写一份）
WARM_DARK = (34, 27, 23)
WARM_LIGHT = (252, 246, 234)
WARM_GAMMA = 0.92
CONTRAST = 1.16
FADE_PX = 60
CLEAN_FROM = 0.55          # 从画布这个比例往右先抹干净
WIDTH_MIN, WIDTH_MAX = 0.26, 0.40   # 照片区宽度占画布宽的合理带宽
TOP_GIVE = 0.06            # 必须垂直裁切时，最多从顶部让出这么多（保发顶）


def _require_pillow():
    try:
        from PIL import Image, ImageEnhance  # noqa: F401
    except Exception as exc:  # pragma: no cover - 环境问题
        raise SystemExit(f"需要 Pillow：{exc}")


def portrait_spec(meta: dict) -> dict:
    spec = (meta or {}).get("cover_portrait") or {}
    if not isinstance(spec, dict):
        raise SystemExit("cover_portrait 必须是映射")
    return spec


def validate(spec: dict, article_dir: pathlib.Path) -> list[str]:
    """声明完整性：肖像是真实人物照片，来源与许可必须落盘可查。"""
    errors: list[str] = []
    file = str(spec.get("file") or "").strip()
    if not file:
        errors.append("cover_portrait.file 为空")
    else:
        p = pathlib.Path(file)
        if not p.is_absolute():
            p = article_dir / file
        if not p.is_file():
            errors.append(f"肖像文件不存在：{p}")
    for key, why in (
        ("source", "取自哪里（页面 / 馆藏 / 档案编号）"),
        ("license", "许可（公有领域 / 已授权，写明依据）"),
    ):
        if not str(spec.get(key) or "").strip():
            errors.append(f"cover_portrait.{key} 必填 —— {why}")
    anchor = spec.get("anchor")
    if anchor is not None:
        ok = (
            isinstance(anchor, (list, tuple))
            and len(anchor) == 2
            and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in anchor)
        )
        if not ok:
            errors.append("cover_portrait.anchor 应是 [x, y]，取值 0--1（脸部中心占原图比例）")
    return errors


def photo_region(canvas: tuple[int, int], portrait: tuple[int, int]) -> tuple[int, int, int]:
    """按肖像自身比例反推照片区，返回 (x起点, 宽, 高)。

    宽 = 画布高 × 肖像宽高比 —— 这样铺满整高时不需要垂直裁切，发顶保得住。
    过宽会吃掉文字区、过窄压不住画面，所以夹在 WIDTH_MIN--WIDTH_MAX 之间。
    """
    import math

    cw, ch = canvas
    pw, ph = portrait
    want = ch * (pw / ph)
    # 夹紧要先取整再比较，否则 int() 截断会让结果掉到下界之下
    lo, hi = math.ceil(cw * WIDTH_MIN), int(cw * WIDTH_MAX)
    width = max(lo, min(int(round(want)), hi))
    return cw - width, width, ch


def warm_tone(im, dark=WARM_DARK, light=WARM_LIGHT, gamma=WARM_GAMMA):
    from PIL import ImageEnhance

    g = ImageEnhance.Contrast(im.convert("L")).enhance(CONTRAST)
    # 🔴 Image.point 对 RGB 要三段连续 256 长的通道 LUT；交错成 [r,g,b,…] 会把通道
    #    错位，灰阶直接变蓝调（2026-08-28 实测踩过）。
    lut: list[int] = []
    for ch in range(3):
        for c in range(256):
            t = (c / 255) ** gamma
            lut.append(int(dark[ch] + (light[ch] - dark[ch]) * t))
    return g.convert("RGB").point(lut)


def clean_right(base, from_ratio: float = CLEAN_FROM):
    """把右区抹回环境渐变，取最右侧 40 列的逐行中位数作填充。"""
    import numpy as np
    from PIL import Image

    a = np.asarray(base.convert("RGB")).astype(np.uint8)
    h, w, _ = a.shape
    strip = np.median(a[:, w - 40 :, :], axis=1).astype(np.uint8)
    x0 = int(w * from_ratio)
    out = a.copy()
    out[:, x0:, :] = np.repeat(strip[:, None, :], w - x0, axis=1)
    return Image.fromarray(out)


def crop_for_region(src, region: tuple[int, int], anchor: tuple[float, float]):
    """裁到照片区比例，垂直方向优先保住发顶。"""
    rw, rh = region
    w, h = src.size
    cw, ch = w, int(w * rh / rw)
    if ch > h:
        ch, cw = h, int(h * rw / rh)
    left = max(0, min(int(w * anchor[0] - cw / 2), w - cw))
    top = 0 if ch >= h * (1 - TOP_GIVE) else max(0, min(int(h * TOP_GIVE), h - ch))
    return src.crop((left, top, left + cw, top + ch))


def compose(cover_path: pathlib.Path, portrait_path: pathlib.Path,
            anchor: tuple[float, float] = (0.45, 0.34)) -> dict:
    from PIL import Image

    base = clean_right(Image.open(cover_path).convert("RGB"))
    cw, ch = base.size
    src = Image.open(portrait_path).convert("RGB")
    x0, rw, rh = photo_region((cw, ch), src.size)
    photo = warm_tone(crop_for_region(src, (rw, rh), anchor)).resize((rw, rh), Image.LANCZOS)

    mask = Image.new("L", (rw, rh), 255)
    if FADE_PX:
        px = mask.load()
        for x in range(min(FADE_PX, rw)):
            v = int(255 * (x / FADE_PX) ** 1.35)
            for y in range(rh):
                px[x, y] = v

    base.paste(photo, (x0, 0), mask)
    base.save(cover_path)
    return {
        "canvas": [cw, ch],
        "portrait_source_size": list(src.size),
        "photo_region": {"x": x0, "width": rw, "height": rh,
                         "width_ratio": round(rw / cw, 4),
                         "region_ratio": round(rw / rh, 4)},
        "treatment": {"warm_dark": list(WARM_DARK), "warm_light": list(WARM_LIGHT),
                      "gamma": WARM_GAMMA, "contrast": CONTRAST, "fade_px": FADE_PX},
        "vertical_crop_free": bool(abs(rw / rh - src.size[0] / src.size[1]) < 0.06),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="封面真实肖像确定性合成")
    ap.add_argument("article_dir")
    ap.add_argument("--check", action="store_true", help="只校验声明与素材，不写盘")
    args = ap.parse_args(argv)

    _require_pillow()
    article = pathlib.Path(args.article_dir)
    meta_path = article / "article-meta.yaml"
    if not meta_path.is_file():
        print(f"❌ 找不到 {meta_path}")
        return 2
    import yaml

    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    spec = portrait_spec(meta)
    if not str(spec.get("file") or "").strip():
        print("ℹ️ 本篇未声明 cover_portrait，跳过肖像合成（走标志物路线）")
        return 0

    errors = validate(spec, article)
    if errors:
        print("❌ cover_portrait 声明不完整：")
        for e in errors:
            print(f"   • {e}")
        return 2
    if args.check:
        print("✅ cover_portrait 声明与素材齐备（未写盘）")
        return 0

    cover = article / "素材" / "cover.png"
    if not cover.is_file():
        print(f"❌ 底板不存在：{cover}（先 render-visuals 出底板）")
        return 2
    portrait = pathlib.Path(str(spec["file"]))
    if not portrait.is_absolute():
        portrait = article / str(spec["file"])
    anchor = tuple(spec.get("anchor") or (0.45, 0.34))  # type: ignore[assignment]

    info = compose(cover, portrait, anchor)  # type: ignore[arg-type]
    receipt = {
        "stage": "portrait",
        "producer": "sansheng-write.cover-portrait",
        "portrait": {k: spec.get(k) for k in ("file", "source", "license", "credit")},
        **info,
    }
    log = article / ".gen-log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    print(f"✅ 已合成真实肖像：{cover}")
    print(f"   照片区 {info['photo_region']['width']}x{info['photo_region']['height']}"
          f" · 占宽 {info['photo_region']['width_ratio']:.1%}"
          f" · 免垂直裁切 {'是' if info['vertical_crop_free'] else '否（已优先保发顶）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
