#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_check.py -- 体检：你当前的环境能走到第几档？

    python scripts/setup_check.py

三条使用路径（详见 README）：
    ① 纯方法论      选题 → 大纲 → 正文 → 改稿 → 标题        零外部依赖
    ② + 排版        再加：一键排版 / 契约门 / 组件模板        + bun / md 转换器 / Node
    ③ 全自动发布    再加：配图 / 封面 / 推草稿箱              + 生图 key / 平台凭证

退出码：0 = 至少第 ① 档可用；1 = 连第 ① 档都不行（缺 Python 依赖）。
永远不打印任何密钥的值。
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

# Windows GBK 控制台默认无法编码本文用到的 ✅/⚠️/❌ 等符号，强制 UTF-8 避免体检自身崩溃
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, WARN, BAD = "✅", "⚠️ ", "❌"


def _py_mod(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _bin(name: str) -> bool:
    return shutil.which(name) is not None


def _env_present(name: str) -> bool:
    """只判断有没有，绝不读值、绝不打印值。"""
    if os.environ.get(name, "").strip():
        return True
    try:
        import profile_config as pc
        return bool(pc.load_secret(name, required=False))
    except Exception:
        return False


def main() -> int:
    print("=" * 62)
    print("  sansheng-write 环境体检")
    print("=" * 62)

    # ---------- 第 ① 档 ----------
    print("\n【① 纯方法论】选题 / 大纲 / 正文 / 改稿 / 标题")
    tier1 = []
    py_ok = sys.version_info >= (3, 10)
    print(f"  {OK if py_ok else BAD} Python {sys.version_info.major}.{sys.version_info.minor}"
          f"{'' if py_ok else '  (需要 3.10+)'}")
    tier1.append(py_ok)

    yaml_ok = _py_mod("yaml")
    print(f"  {OK if yaml_ok else BAD} PyYAML" + ("" if yaml_ok else "        pip install pyyaml"))
    tier1.append(yaml_ok)

    # profile
    try:
        import profile_config as pc
        pd = pc.profile_dir()
        if pc.using_example_profile():
            print(f"  {WARN}profile   使用仓内示例（中性配色 + 占位署名）")
            print(f"       想用你自己的：cp -r profile.example ~/my-profile && "
                  f"export SANSHENG_WRITE_PROFILE_DIR=~/my-profile")
        else:
            print(f"  {OK} profile   {pd}")
        b = pc.brand()
        print(f"  {OK} 主题      {b.get('theme') or 'default'}  primary={pc.colors().get('primary')}")
        authors = list(pc.authors_dir().glob("*.compact.md")) if pc.authors_dir().is_dir() else []
        # 注意 stem 只剥一层后缀：'x.compact.md' -> 'x.compact'，所以按文件名判断
        real = [a for a in authors if a.name != "example-author.compact.md"]
        if real:
            names = [a.name[: -len(".compact.md")] for a in real[:3]]
            print(f"  {OK} 风格手册  {len(real)} 套（{', '.join(names)}{'…' if len(real) > 3 else ''}）")
        else:
            print(f"  {WARN}风格手册  只有示例。产出会接近通用 AI 写作 -- 这是设计，不是缺陷。")
            print(f"       自建方法见 profile.example/corpus/authors/README.md")
    except Exception as e:  # pragma: no cover
        print(f"  {BAD} profile 解析失败：{e}")
        tier1.append(False)

    if not all(tier1):
        print(f"\n{BAD} 第 ① 档不可用。先装齐上面标 {BAD} 的东西。")
        return 1

    # ---------- 第 ② 档 ----------
    print("\n【② + 排版】一键排版 / 契约门 / 组件模板 / 微信 HTML")
    tier2 = []
    for label, ok, how in [
        ("bun",            _bin("bun"),   "https://bun.sh  （跑 markdown→HTML 转换器）"),
        ("Node.js 18+",    _bin("node"),  "https://nodejs.org  （配图加 logo 水印）"),
        ("jimp (npm)",     (Path(__file__).parent / "node_modules" / "jimp").is_dir(),
                           "cd scripts && npm install"),
    ]:
        print(f"  {OK if ok else WARN}{label:<14}" + ("" if ok else f"缺 -- {how}"))
        tier2.append(ok)
    print(f"  {WARN}markdown→HTML 转换器：本 skill 不捆绑，需自装（见 README 依赖矩阵）")

    # ---------- 第 ③ 档 ----------
    print("\n【③ 全自动】配图 / 封面 / 推送草稿箱")
    g_key = _env_present("GOOGLE_API_KEY")
    o_key = _env_present("OPENAI_API_KEY")
    print(f"  {OK if g_key else WARN}GOOGLE_API_KEY   " + ("已配置" if g_key else "未配置 -- 生图不可用（可用 OPENAI 兼容端点兜底）"))
    if g_key:
        try:
            import profile_config as pc
            k = pc.load_secret("GOOGLE_API_KEY", required=False)
            if k.startswith("AQ."):
                proj = _env_present("GOOGLE_VERTEX_PROJECT")
                print(f"  {OK if proj else BAD} 端点：Vertex Express（AQ. 前缀）"
                      + ("" if proj else " -- 还缺 GOOGLE_VERTEX_PROJECT"))
            else:
                print(f"  {OK} 端点：AI Studio（AIza 前缀）")
        except Exception:
            pass
    # openai 兜底不能只看 key 是否存在：曾出现「文档承诺、代码零实现」的假绿灯（key 配了
    # 也没用）。这里探测 gen_img.gen_openai 真实可调才发 ✅，否则如实降级为 ⚠️。
    openai_impl = False
    openai_probe_err = ""
    try:
        import gen_img
        openai_impl = callable(getattr(gen_img, "gen_openai", None))
    except Exception as e:
        openai_probe_err = str(e)[:80]
    if o_key and openai_impl:
        print(f"  {OK}OPENAI_API_KEY   已配置（生图兜底可用：gen_img.py --provider openai -m <模型名>）")
        if not _env_present("OPENAI_BASE_URL"):
            print(f"       OPENAI_BASE_URL 未配置 -- 默认打 {gen_img.DEFAULT_OPENAI_BASE_URL}；"
                  f"用第三方兼容端点需在 .env 显式配置")
    elif o_key:
        print(f"  {WARN}OPENAI_API_KEY   已配置，但 gen_img.py 的 openai 兜底不可用"
              + (f"（gen_img 导入失败：{openai_probe_err}）" if openai_probe_err
                 else "（未找到 gen_openai 实现）"))
    else:
        print(f"  {WARN}OPENAI_API_KEY   未配置（可选兜底）")

    mm = _env_present("MINIMAX_API_KEY")
    print(f"  {OK if mm else WARN}MINIMAX_API_KEY  " + ("已配置" if mm else "未配置 -- 文章主题曲 BGM 会自动跳过（可选彩蛋）"))

    # 微信凭证配在 baoyu 侧 ~/.baoyu-skills/.env（键名 WECHAT_APP_ID/WECHAT_APP_SECRET），
    # 不在本仓 .env——此前查错键名+错位置，永远发不了 ✅（复核 D5-1）
    wx = False
    _baoyu_env = Path.home() / ".baoyu-skills" / ".env"
    if _baoyu_env.is_file():
        try:
            _keys = {ln.split("=", 1)[0].strip() for ln in _baoyu_env.read_text(encoding="utf-8").splitlines()
                     if "=" in ln and not ln.strip().startswith("#")}
            wx = {"WECHAT_APP_ID", "WECHAT_APP_SECRET"} <= _keys
        except Exception:
            pass
    print(f"  {OK if wx else WARN}微信公众号凭证    "
          + ("已配置（~/.baoyu-skills/.env）" if wx
             else "未配置 -- 排版产物落盘为 HTML，你手动粘贴（配置位置：baoyu 侧 ~/.baoyu-skills/.env 的 WECHAT_APP_ID/WECHAT_APP_SECRET，非本仓 .env）"))

    pil = _py_mod("PIL")
    print(f"  {OK if pil else WARN}Pillow           " + ("" if pil else "缺 -- pip install pillow（生图缩放 / 配图压缩）"))

    # ---------- 结论 ----------
    print("\n" + "=" * 62)
    img_ready = g_key or (o_key and openai_impl)  # 生图可用 = Google 主路，或 openai 兜底真实可调
    if all(tier2) and img_ready:
        print("  结论：③ 全自动路径就绪 🎉")
    elif all(tier2):
        print("  结论：② 排版路径就绪。配一个生图 key 就能解锁 ③。")
    else:
        print("  结论：① 纯方法论就绪。写作全流程可用；排版/配图按上面提示补齐。")
    print("  任何一档缺东西都不影响更低档使用 -- 组件缺失只降级该环节，不断整链。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
