#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup.py -- 交互式配置引导：问清你要哪些可选功能，只收集那些功能需要的东西。

    python scripts/setup.py

**主线功能（选题 / 大纲 / 正文 / 改稿 / 标题 / 排版）不需要跑这个。**
装完 `pip install pyyaml` 就能用，本脚本只管可选模块。

设计约束（见发布规约 optional-features.md）：
  · 可选模块默认关闭，未启用时在别处完全静默
  · 只问已选模块所需的配置，不问用不到的
  · 已经配好的不重复问，第二次跑是「改配置」不是「从头来」
  · 密钥只写 .env，其余写 profile —— 沿用三层分离，不因为是引导就混着写
  · 非交互环境（CI / 管道）打印待办清单后退出，不阻塞

永远不打印任何密钥的值。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import profile_config as pc  # noqa: E402

OK, DOT = "✅", "·"


# ===== 模块目录 =====
# 每个条目就是 README「可选功能」章要写的四件事，此处是单一真源。

MODULES = [
    {
        "key": "xhs",
        "name": "小红书图文",
        "what": "把定稿围绕一个传播命题重编成 6-10 张 3:4 轮播图文，开浏览器填好，你点「发布」",
        "need": "小红书账号 + 一个能驱动创作服务平台网页端的发布脚本（自备）",
        "without": "完全不影响写作与公众号发布",
        "fields": [
            ("post_script", "发布脚本的绝对路径（.ts）", True),
        ],
    },
    {
        "key": "weibo",
        "name": "微博",
        "what": "生成完整微博正文与 4-9 张 1:1 专属图，开浏览器填好，你点「发送」",
        "need": "微博账号；发布脚本可自动发现（baoyu-post-to-weibo）",
        "without": "完全不影响写作与公众号发布",
        "fields": [
            ("post_script", "发布脚本路径（留空=自动查找）", False),
        ],
    },
    {
        "key": "podcast",
        "name": "播客（RSS）",
        "what": "把定稿做成双主持音频，复用到公众号、官网与自己的 RSS",
        "need": "NotebookLM 登录态、ffmpeg、一台放 mp3 与 feed.xml 的主机（可 SSH）",
        "without": "完全不影响写作与公众号发布",
        "fields": [
            ("focus_prompt", "主持风格提示词文件路径", True),
            ("remote_host", "feed 主机（如 user@host）", True),
            ("remote_episodes_dir", "主机上放 mp3 的目录", True),
            ("feed_rebuild_command", "主机上重建 feed.xml 的命令", True),
        ],
        "switches": [
            ("auto_after_finalize", "取得正式链接后自动推送 RSS？", False),
            ("wechat_embed", "公众号导读后也放同级播客音频卡？", False),
        ],
    },
]


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask_yes_no(prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {prompt} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)
    if not raw:
        return default
    return raw in ("y", "yes", "是")


def _ask_text(prompt: str, current: str = "") -> str:
    shown = f"  {prompt}"
    if current:
        shown += f"\n    当前：{current}\n    直接回车保留，输入新值覆盖"
    try:
        raw = input(f"{shown}\n  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)
    return raw or current


def _profile_writable() -> Path | None:
    """只允许写自己的 profile，绝不改仓内 profile.example。

    example 是给所有人看的中性默认，往里写个人配置既污染仓库，
    也会在下次 git pull 时冲突。
    """
    if pc.using_example_profile():
        return None
    return pc.profile_dir() / "brand.yaml"


def _print_module(m: dict, enabled: bool) -> None:
    mark = OK if enabled else DOT
    print(f"\n{mark} {m['name']}" + ("（已启用）" if enabled else ""))
    print(f"    能做什么：{m['what']}")
    print(f"    需要你提供：{m['need']}")
    print(f"    不启用会怎样：{m['without']}")


def main() -> int:
    try:
        pc.bind_workspace(Path.cwd())
    except pc.WorkspaceBindingError as exc:
        print(f"  ❌ 工作区绑定失败：{exc}")
        return 2
    print("=" * 64)
    print("  sansheng-write 配置引导")
    print("=" * 64)
    print()
    print("  主线功能（选题 / 大纲 / 正文 / 改稿 / 标题 / 排版）**不需要任何配置**，")
    print("  装完依赖就能用。下面问的全是可选模块，不要就一路回车跳过。")

    target = _profile_writable()
    if target is None:
        print()
        print("  ⚠ 当前跑在仓内 profile.example 上，不能往里写个人配置。")
        print("    先复制一份属于你自己的 profile：")
        print()
        print("      cp -r profile.example ~/my-write-profile")
        print("      export SANSHENG_WRITE_PROFILE_DIR=~/my-write-profile")
        print()
        print("    然后重新运行本脚本。")
        return 2

    current = {m["key"]: pc.distribute_channel(m["key"]) for m in MODULES}

    if not _interactive():
        # 非交互环境不阻塞，打印清单让人知道该配什么
        print()
        print("  检测到非交互环境，改为打印待办清单：")
        for m in MODULES:
            on = bool(current[m["key"]].get("enabled"))
            print(f"    [{'x' if on else ' '}] {m['name']}：{m['what']}")
            if not on:
                for f, desc, req in m["fields"]:
                    if req:
                        print(f"          需要 {f} -- {desc}")
        print()
        print(f"  在交互式终端里跑 `python {Path(__file__).name}` 完成配置。")
        return 0

    chosen: dict[str, dict] = {}
    for m in MODULES:
        was_on = bool(current[m["key"]].get("enabled"))
        _print_module(m, was_on)
        if not _ask_yes_no("启用？", default=was_on):
            chosen[m["key"]] = {"enabled": False}
            continue

        vals: dict = {"enabled": True}
        for field, desc, required in m["fields"]:
            got = _ask_text(desc, str(current[m["key"]].get(field) or ""))
            if required and not got:
                print(f"    ⚠ {field} 是必填，缺了这个模块跑不起来——本次先记为未启用。")
                vals = {"enabled": False}
                break
            if got:
                vals[field] = got
        if vals.get("enabled"):
            for field, prompt, default in m.get("switches", []):
                current_value = current[m["key"]].get(field)
                vals[field] = _ask_yes_no(
                    prompt,
                    default=bool(current_value) if current_value is not None else default,
                )
        chosen[m["key"]] = vals

    # ---- 写盘 ----
    print()
    print("-" * 64)
    turned_on = [m["name"] for m in MODULES if chosen[m["key"]].get("enabled")]
    if not turned_on:
        print("  没有启用任何可选模块——主线功能照常可用，这是完全正常的选择。")
    else:
        print("  将启用：" + " / ".join(turned_on))
    print(f"  写入：{target}")
    if not _ask_yes_no("确认写入？", default=True):
        print("  已取消，未改动任何文件。")
        return 0

    _write_profile(target, chosen)
    print()
    print(f"  {OK} 已写入。用 `python scripts/setup_check.py` 复查。")
    if turned_on:
        print("  提示：需要账号登录态的模块，首次使用会弹出浏览器让你登录一次。")
    return 0


def _write_profile(target: Path, chosen: dict) -> None:
    """把选择合并进 profile 的 distribute 段。

    🔴 只在能保留注释时才就地改写。PyYAML 的 safe_dump 会把整个文件重排并
    **抹掉所有注释**——profile 里的注释往往是决策记录和踩坑说明，丢了比没写入更糟。
    所以没有 ruamel.yaml 时不写盘，改为打印片段让用户自己粘贴。
    """
    try:
        from ruamel.yaml import YAML                      # noqa: PLC0415
    except ImportError:
        _print_snippet(target, chosen)
        return

    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    data = {}
    if target.is_file():
        with target.open(encoding="utf-8") as f:
            data = yaml_rt.load(f) or {}

    dist = data.setdefault("distribute", {}).setdefault("channels", {})
    for key, vals in chosen.items():
        ch = dist.setdefault(key, {})
        ch.update(vals)

    backup = target.with_suffix(target.suffix + ".bak")
    if target.is_file():
        backup.write_bytes(target.read_bytes())

    import io
    buf = io.StringIO()
    yaml_rt.dump(data, buf)
    # write_bytes 而非 write_text：Windows 下 write_text 会把 \n 转成 \r\n，
    # 让本来 LF 的 profile 变成混合换行。
    target.write_bytes(buf.getvalue().encode("utf-8"))
    if backup.exists():
        print(f"  （原文件已备份到 {backup.name}）")


def _print_snippet(target: Path, chosen: dict) -> None:
    """没有 ruamel 时的安全出口：打印片段，由用户自己贴进 profile。"""
    import yaml

    print()
    print("  ⚠ 没装 ruamel.yaml，自动写入会抹掉 profile 里的全部注释，因此**不写盘**。")
    print(f"    要么 `pip install ruamel.yaml` 后重跑本脚本（会保留注释就地改），")
    print(f"    要么把下面这段粘进 {target}：")
    print()
    snippet = yaml.safe_dump({"distribute": {"channels": chosen}},
                             allow_unicode=True, sort_keys=False, width=100)
    for line in snippet.splitlines():
        print("      " + line)
    print()


if __name__ == "__main__":
    sys.exit(main())
