#!/usr/bin/env python3
"""
🗜️ 图片压缩工具（PIL 实现，中文路径友好）
========================================================
替代 baoyu-compress-image 在 Windows + 中文路径下的 ImageMagick `convert` 崩溃问题
。

策略：
  1. ≤ target_max_mb 的文件 → 仅 optimize=True 重写（轻量瘦身，体积通常省 15-30%）
  2. > target_max_mb 的文件 → 等比缩长边到 1024px（1K 横切规范）+ optimize=True
  3. 内置跳过清单：hero.png / bgm_cover.png / music_cover.png（组件小图，无需压缩）

用法：
  python compress_images.py 素材/             # 压缩目录下所有 PNG
  python compress_images.py 素材/cover.png    # 压缩单个文件
  python compress_images.py 素材/ --max-mb 2  # 自定义阈值

集成位置：autopilot.md 第八步 b。
"""

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

# Windows GBK 控制台/管道下 print 中文会 UnicodeEncodeError，强制 UTF-8
# （与 prep_writing.py / learn_edits.py / regression_baseline.py 同源防护）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow 未安装。请：pip install Pillow", file=sys.stderr)
    sys.exit(1)


# 跟 add_logo.js 内置跳过清单保持一致（layout.md "Logo 水印例外" 同源）
SKIP_NAMES = {"hero.png", "bgm_cover.png", "music_cover.png"}

# 1K 横切规范长边（image-routing.md "1K 分辨率横切规范"）
TARGET_LONG_EDGE = 1024

# 后处理台账：add_logo.js 打完水印记一笔 sha，本脚本压缩完更新同一笔。
# 处理前先比「当前 sha == 台账 sha」——命中即跳过。这不只是省重编码时间：
# add_logo.js 是**就地覆写且无已处理检测**的，整目录重跑后处理会在已打过
# 水印的图上再叠一层 35% logo（2026-08-16 审计确认的真缺陷），台账是唯一护栏。
LEDGER_NAME = ".postprocess-ledger.json"


def _ledger_path(directory: Path) -> Path:
    return directory / LEDGER_NAME


def load_ledger(directory: Path) -> dict:
    try:
        data = json.loads(_ledger_path(directory).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def record_ledger(path: Path, stage: str) -> None:
    """把 path 的当前字节 sha 记进其所在目录的台账。失败只警告，不拦流程。"""
    try:
        directory = path.resolve().parent
        ledger = load_ledger(directory)
        ledger[path.name] = {
            "sha256": _sha256(path),
            "stage": stage,
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        _ledger_path(directory).write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"WARN: 后处理台账写入失败（不拦流程）：{exc}", file=sys.stderr)


def ledger_says_unchanged(path: Path) -> bool:
    """只认 stage == "compressed" 的记录。

    add_logo.js 打完章会先记一笔 stage="logo"——那说明水印在了、但**还没压缩**，
    此时跳过等于让 >max-mb 的图永远得不到缩尺寸（首版实现踩过这个坑，
    活体链路验证当场抓到）。压缩是链路末步，只有自己盖过的章才作数。
    """
    entry = load_ledger(path.resolve().parent).get(path.name)
    return (
        bool(entry)
        and entry.get("stage") == "compressed"
        and entry.get("sha256") == _sha256(path)
    )


def compress_one(path: Path, target_max_mb: float, verbose: bool = True) -> tuple[float, float, str]:
    """压缩单个 PNG，返回 (原大小 MB, 压缩后 MB, 状态)"""
    if path.suffix.lower() != ".png":
        return (0, 0, "SKIP_NOT_PNG")
    if path.name in SKIP_NAMES:
        size_mb = path.stat().st_size / 1024 / 1024
        if verbose:
            print(f"SKIP  {path.name:30s} ({size_mb:.2f}MB) -- 组件小图跳过清单")
        return (size_mb, size_mb, "SKIP_COMPONENT")
    if ledger_says_unchanged(path):
        size_mb = path.stat().st_size / 1024 / 1024
        if verbose:
            print(f"SKIP  {path.name:30s} ({size_mb:.2f}MB) -- 台账命中，字节未变")
        return (size_mb, size_mb, "SKIP_UNCHANGED")

    orig_mb = path.stat().st_size / 1024 / 1024
    try:
        img = Image.open(path)
    except Exception as e:
        if verbose:
            print(f"FAIL  {path.name:30s} 无法读取：{e}")
        return (orig_mb, orig_mb, f"FAIL_READ:{e}")

    w, h = img.size
    long_side = max(w, h)
    resized = False

    if orig_mb > target_max_mb and long_side > TARGET_LONG_EDGE:
        scale = TARGET_LONG_EDGE / long_side
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        resized = True

    try:
        img.save(path, "PNG", optimize=True)
    except Exception as e:
        if verbose:
            print(f"FAIL  {path.name:30s} 写入失败：{e}")
        return (orig_mb, orig_mb, f"FAIL_WRITE:{e}")

    new_mb = path.stat().st_size / 1024 / 1024
    tag = "RESIZE" if resized else "OPT   "
    record_ledger(path, "compressed")
    if verbose:
        action = f"{tag} {path.name:30s} {orig_mb:.2f}MB -> {new_mb:.2f}MB ({(1-new_mb/orig_mb)*100:.0f}% saved)"
        print(action)
    return (orig_mb, new_mb, tag.strip())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 微信 media/uploadimg 只收 jpg / png。其余格式一律 40005 invalid file type，
# 而 baoyu-post-to-wechat 把上传异常 catch 掉只打一行 stderr、img 保留本地 src
# —— 于是草稿里是坏图，所有校验却显示通过（2026-07-28 六张 .webp 连推三版才发现）。
# 所以在**发布前的最后一道机械步骤**就地转掉，不依赖任何人记得这条规则。
WECHAT_UNSUPPORTED = {".webp", ".avif", ".heic", ".heif", ".bmp", ".tiff", ".tif"}


def convert_unsupported(directory: Path, *, verbose: bool = True) -> list[tuple[Path, Path]]:
    """把微信不收的图片格式就地转成 PNG，并改写 定稿.md / 定稿.html 里的引用。

    转完删除原文件：留着只会让下次有人又引用回去。
    """
    if not directory.is_dir():
        return []
    targets = sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in WECHAT_UNSUPPORTED
    )
    if not targets:
        return []

    from PIL import Image

    converted: list[tuple[Path, Path]] = []
    for src in targets:
        dst = src.with_suffix(".png")
        try:
            with Image.open(src) as im:
                im.convert("RGB").save(dst, "PNG", optimize=True)
        except Exception as exc:  # noqa: BLE001 - 转换失败要说清是哪张，不能静默
            print(f"WARN: {src.name} 转 PNG 失败：{exc}", file=sys.stderr)
            continue
        converted.append((src, dst))

    if not converted:
        return []

    # 改引用。文章目录是 素材/ 的上一级。
    article_dir = directory.parent
    for doc in ("定稿.md", "定稿.html"):
        path = article_dir / doc
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        for src, dst in converted:
            text = text.replace(src.name, dst.name)
        if text != original:
            path.write_text(text, encoding="utf-8")
            if verbose:
                print(f"  ↻ {doc} 中的引用已改为 .png")

    for src, _ in converted:
        src.unlink(missing_ok=True)

    if verbose:
        names = "、".join(s.name for s, _ in converted)
        print(f"⚠️  微信不收这些格式，已转为 PNG（{len(converted)} 张）：{names}")
    return converted


def stamp_gen_log(targets: list[Path], *, verbose: bool = True) -> int:
    """把后处理造成的字节变化补记进 .gen-log.jsonl。

    为什么必须记：`render-visuals --only` 沿用未重渲的图时，会拿磁盘字节和生图日志里
    最新一条的 output_sha256 对账，对不上就拒绝沿用（"证据链不接受来历不明的图"）。
    而 add_logo.js 打水印、本脚本压缩，都会正当地改变字节 —— 不补记的话，任何做过
    后处理的文章都再也补渲不了单张，只能整批重出，等于把 --only 废掉，还平白多烧几次生图配额。

    补记不是给证据链开口子，而是把「谁在什么时候改了这些字节」明确写下来：
    记录里保留原生成条目的 renderer/model/prompt 等出身信息，另加 post_process 字段
    说明这次变化的来源。找不到原始生成记录的图**不补记** —— 那种图本来就来历不明，
    正是校验该拦下的。
    """
    if not targets:
        return 0
    article_dir = targets[0].resolve().parent
    # 素材/ 在文章目录下，日志在文章目录根。逐级上找，最多两层。
    for candidate in (article_dir, article_dir.parent):
        log_path = candidate / ".gen-log.jsonl"
        if log_path.is_file():
            break
    else:
        return 0
    cwd = log_path.parent

    by_output: dict[str, dict] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("output"):
            by_output[str(entry["output"])] = entry  # 后写覆盖先写 = 取最新

    appended = []

    def sync_template_manifest(path: Path, image_sha256: str) -> None:
        """让确定性模板的设计清单绑定水印/压缩后的最终字节。

        模板清单约束的是文字框、safe bounds 与视觉结构；add_logo / 压缩不改变这些
        结构，却会改变 PNG 字节。若只补 .gen-log 而不同步这里，视觉 QA 会把自身
        已记录的合法后处理误判为来源不明。
        """
        manifest_path = path.with_suffix(".design.json")
        if not manifest_path.is_file():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if manifest.get("renderer") != "deterministic-template-compositor":
            return
        if manifest.get("image_sha256") == image_sha256:
            return
        manifest["image_sha256"] = image_sha256
        manifest["post_process"] = {
            "tool": "compress_images.py",
            "reason": "发布前水印与压缩改变 PNG 字节；设计结构未变",
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for path in targets:
        path = path.resolve()
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(cwd).as_posix()
        except ValueError:
            continue
        prior = by_output.get(rel)
        if not prior:
            continue
        actual = _sha256(path)
        sync_template_manifest(path, actual)
        if prior.get("output_sha256") == actual:
            continue  # 字节没变，不必留痕
        record = dict(prior)
        record["record_id"] = f"postprocess-{rel.rsplit('/', 1)[-1]}-{actual[:12]}"
        record["timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        record["output_sha256"] = actual
        record["bytes"] = path.stat().st_size
        record["post_process"] = {
            "tool": "compress_images.py",
            "reason": "发布前后处理（水印 + 压缩）改变了字节",
            "source_sha256": prior.get("output_sha256"),
        }
        appended.append(record)

    if appended:
        with log_path.open("a", encoding="utf-8") as fh:
            for record in appended:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        if verbose:
            print(f"gen-log: 补记 {len(appended)} 条后处理记录 -> {log_path}")
    return len(appended)


def main():
    parser = argparse.ArgumentParser(
        description="图片压缩（PIL 实现，中文路径友好）"
    )
    parser.add_argument("input", help="文件或目录路径")
    parser.add_argument(
        "--max-mb",
        type=float,
        default=2.0,
        help="目标最大体积（MB），超过则缩长边到 1K（默认 2.0）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，仅输出总结",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: 路径不存在 {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.is_file():
        targets = [input_path]
    else:
        # 先转掉微信不收的格式，再收集 PNG —— 顺序反了新转出来的图就漏压了
        convert_unsupported(input_path, verbose=not args.quiet)
        targets = sorted(input_path.glob("*.png"))

    if not targets:
        print(f"WARN: {input_path} 下无 PNG 文件")
        sys.exit(0)

    verbose = not args.quiet
    total_orig = 0.0
    total_new = 0.0
    skipped = 0
    processed = 0

    for p in targets:
        orig, new, status = compress_one(p, args.max_mb, verbose=verbose)
        total_orig += orig
        total_new += new
        if status.startswith("SKIP"):
            skipped += 1
        elif status in ("OPT", "RESIZE"):
            processed += 1

    # 无论本次是否真的压缩了，都按当前磁盘字节对账补记 ——
    # 水印是上一步 add_logo.js 打的，它同样会让字节漂移。
    stamp_gen_log(targets, verbose=verbose)

    print()
    print(
        f"Done: {processed} 张压缩 / {skipped} 张跳过，"
        f"总大小 {total_orig:.2f}MB -> {total_new:.2f}MB "
        f"({(1 - total_new/total_orig)*100 if total_orig > 0 else 0:.0f}% saved)"
    )


if __name__ == "__main__":
    main()
