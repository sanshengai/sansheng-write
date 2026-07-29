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


def _check_optional_distribute() -> None:
    """一稿多投是可选模块：**没启用就一个字都不打印**。

    见发布规约 optional-features.md：可选模块默认关闭、未启用即静默。
    一个只想写文章的用户跑完体检，不该知道这些渠道存在。
    """
    try:
        import distribute
    except Exception:
        return

    enabled = [c for c in distribute.CHANNELS if distribute.channel_enabled(c)]
    if not enabled:
        return

    print("\n【可选 · 一稿多投】" + " / ".join(distribute.CHANNELS[c]["label"] for c in enabled))
    for ch in enabled:
        cfg = distribute.channel_config(ch)
        label = distribute.CHANNELS[ch]["label"]
        if distribute.CHANNELS[ch]["dispatch_mode"] == "assisted":
            script = distribute.resolve_post_script(ch, cfg)
            bun_ok = bool(distribute._find_bun())
            ok = bool(script) and bun_ok
            detail = ("已就绪" if ok else
                      ("缺发布脚本 -- 配 profile 的 "
                       f"distribute.channels.{ch}.post_script" if not script
                       else "缺 bun -- https://bun.sh"))
        else:
            need = ("focus_prompt", "remote_host", "remote_episodes_dir", "feed_rebuild_command")
            missing = [k for k in need if not str(cfg.get(k) or "").strip()]
            ok = not missing
            detail = "已就绪" if ok else f"缺 {', '.join(missing)}"
        # 中文占 2 列，用字符数对齐会参差；复用 distribute 的显示宽度
        pad = " " * max(0, 14 - distribute._display_width(label))
        print(f"  {OK if ok else WARN}{label}{pad}{detail}")


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
    print("\n【③ 全自动】配图 / BGM / 官方读回草稿")
    renderer_ready = False
    try:
        from render_visuals import probe_renderer, resolve_renderer_command

        renderer_command, revision, renderer_errors = resolve_renderer_command()
        renderer_probe = (
            probe_renderer(renderer_command)
            if renderer_command and not renderer_errors
            else {"ok": False, "error": "; ".join(renderer_errors)}
        )
        renderer_ready = bool(renderer_probe.get("ok"))
        print(
            f"  {OK if renderer_ready else BAD}baoyu-image-gen renderer  "
            + (
                f"能力探测通过（{revision[:12]}）"
                if renderer_ready
                else f"不可用 -- {renderer_probe.get('error')}"
            )
        )
    except Exception as exc:
        print(f"  {BAD}baoyu-image-gen renderer  探测失败 -- {exc}")

    mm = _env_present("MINIMAX_API_KEY")
    print(f"  {OK if mm else BAD}MINIMAX_API_KEY  " + ("已配置" if mm else "未配置 -- BGM 是发布硬门"))

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

    # ---------- 可选模块：一稿多投 ----------
    # 🔴 只体检**已启用**的渠道。未启用 = 完全静默：不检查、不提示、不计入结论。
    # 只想写文章的人不该在体检报告里看见小红书/微博/播客——他想了解时会去读 README。
    _check_optional_distribute()

    # ---------- 结论 ----------
    print("\n" + "=" * 62)
    if all(tier2) and renderer_ready and mm and wx:
        print("  结论：③ 全自动路径就绪 🎉")
    elif all(tier2):
        print("  结论：② 排版路径就绪。补齐上方③的硬门后才能自动推草稿。")
    else:
        print("  结论：① 纯方法论就绪。写作全流程可用；排版/配图按上面提示补齐。")
    print("  低档能力可独立使用；进入发布机械链后，任何硬门缺失都会明确非零退出。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
