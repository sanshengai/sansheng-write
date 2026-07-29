#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""distribute.py -- 一稿多投的分发层引擎（渠道注册 / 计划 / 校验 / 派发）。

定位：微信草稿箱之后的**第二段链路**。公众号定稿是唯一上游真源，各渠道从它派生，
而不是各写各的——那样会出现「同一篇文章在三个平台说法不一致」。

与 release-runtime 的分工：
  release-runtime  定稿 → 排版 → 视觉 → 微信草稿箱 → finalize（永久链接 + 归档 + 官网）
  distribute       finalize 之后 → 小红书 / 微博 / 播客

三段式（与 skill 既有哲学一致：**脚本做闸门，agent 做内容**）：
  plan      读定稿 + meta + 素材，产出各渠道的「约束 + 待填槽」到 _distribute-plan.json
  verify    校验 agent 填好的文案是否满足该渠道硬约束（字数 / 标签格式 / 必填），失败 exit 2
  dispatch  真正派发；不可自动化的渠道产出「手动发布包」并明确说明人工边界

设计铁律：
  1. 私有值（账号名 / 主机 / 节目 ID / 目录）**只从 profile 读**，公开仓不留真值。
  2. 失败明确阻断，不 skip、不伪造状态——与 publish.md 同一条底线。
  3. 每个渠道派发后落 receipt；没有 receipt 就不算发过。
  4. 派发是**外向且不可撤回**的动作：`dispatch` 默认只做 dry-run，真发必须显式 --confirm。

用法：
    python distribute.py status   [--dir .]
    python distribute.py plan     [--dir .] [--only xhs,weibo]
    python distribute.py verify   <channel> [--dir .]
    python distribute.py dispatch <channel> [--dir .] [--confirm]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from profile_config import (  # noqa: E402
    distribute_channel,
    distribute_config,
    using_example_profile,
)

# ===== 【第 1 节】渠道注册表 =====
#
# 增渠道只改这里 + profile 的 distribute.channels + references/distribute.md 的口径表。
# `dispatch_mode` 是**能力事实**不是偏好：
#   auto   -- 有可编程发布路径（微博走 baoyu-post-to-weibo 的 Chrome CDP）
#   rss    -- 自建 RSS，平台侧自动抓取（播客）
#   manual -- 平台无开放发布接口，只能人工（小红书；这条改不了，别假装能自动）

CHANNELS: dict[str, dict] = {
    "xhs": {
        "label": "小红书图文",
        "dispatch_mode": "manual",
        "artifacts": ["文案.txt", "images/"],
        "upstream": "xhs-outline.md",
        "note": "小红书无开放发布接口，dispatch 只产手动发布包",
    },
    "weibo": {
        "label": "微博",
        "dispatch_mode": "auto",
        "artifacts": ["文案.txt"],
        "upstream": "定稿.md",
        "note": "复用小红书图；正文超 140 字会被折叠",
    },
    "podcast": {
        "label": "播客（小宇宙）",
        "dispatch_mode": "rss",
        "artifacts": ["audio.mp3", "shownotes.md"],
        "upstream": "定稿.md",
        "note": "NotebookLM 生成音频 → 自建 feed.xml → 平台侧抓取",
    },
}

STATE_FILE = "_distribute-state.json"
PLAN_FILE = "_distribute-plan.json"
RECEIPT_FILE = "_receipt.json"
DIST_DIRNAME = "dist"

# 状态机：一条单向链，任何一环缺证据都不允许跳到下一环
STATUSES = ("pending", "planned", "drafted", "verified", "dispatched")


# ===== 【第 2 节】配置解析（私有值的唯一入口） =====

def channel_config(channel: str) -> dict:
    """单渠道配置。解析真源在 profile_config，本文件不自己碰 profile。"""
    return distribute_channel(channel)


def channel_enabled(channel: str) -> bool:
    return bool(channel_config(channel).get("enabled"))


def enabled_channels() -> list[str]:
    return [c for c in CHANNELS if channel_enabled(c)]


# ===== 【第 3 节】文章目录读取 =====

def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_article_meta(article_dir: Path) -> dict:
    """读 article-meta.yaml。缺 PyYAML 时明确报错而不是静默降级。"""
    meta_path = article_dir / "article-meta.yaml"
    if not meta_path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        sys.exit("[distribute] 需要 PyYAML：pip install pyyaml")
    with meta_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_final_title(article_dir: Path) -> str:
    """标题真源 = .state.json 的 writing.title_final。

    🔴 不读 article-meta.yaml 的 title：改标题时 retitle 会同步 title_final，
    而 meta 可能滞后。这与 archive 的取值口径保持一致（见 release-runtime.md）。
    """
    state = _read_json(article_dir / ".state.json")
    stages = state.get("stages") or {}
    title = ((stages.get("writing") or {}).get("title_final") or "").strip()
    if title:
        return title
    return str(read_article_meta(article_dir).get("title") or "").strip()


def read_final_text(article_dir: Path) -> str:
    p = article_dir / "定稿.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def read_wechat_url(article_dir: Path) -> str:
    """公众号永久链接。分发文案里的原文入口指向它，也是 finalize 已跑过的证据。

    🔴 真源是 `.state.json` 的 `stages.publish.wechat_url`（finalize 写入）。
    不要去读 `_publish-receipt.json`——那是**草稿箱**凭证，只有 draft_media_id，
    正式发布前 `formal_publish` 一直是 false，拿它判断会永远得到「未发布」。
    """
    state = _read_json(article_dir / ".state.json")
    pub = (state.get("stages") or {}).get("publish") or {}
    url = str(pub.get("wechat_url") or "").strip()
    return url if url.startswith("http") else ""


def list_source_images(article_dir: Path) -> list[str]:
    """素材/ 下的图，供微博与小红书复用（封面优先排前）。"""
    assets = article_dir / "素材"
    if not assets.is_dir():
        return []
    imgs = sorted(
        p.name for p in assets.iterdir()
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )
    return sorted(imgs, key=lambda n: (0 if "cover" in n or "封面" in n else 1, n))


# ===== 【第 4 节】状态机 =====

def dist_dir(article_dir: Path) -> Path:
    return article_dir / DIST_DIRNAME


def channel_dir(article_dir: Path, channel: str) -> Path:
    return dist_dir(article_dir) / channel


def read_state(article_dir: Path) -> dict:
    st = _read_json(dist_dir(article_dir) / STATE_FILE)
    if not st:
        st = {"schema_version": 1, "channels": {}}
    st.setdefault("channels", {})
    return st


def set_status(article_dir: Path, channel: str, status: str, **extra) -> None:
    if status not in STATUSES:
        sys.exit(f"[distribute] 非法状态 {status!r}，合法值：{', '.join(STATUSES)}")
    st = read_state(article_dir)
    entry = st["channels"].setdefault(channel, {})
    entry["status"] = status
    entry["updated_at"] = _now()
    entry.update(extra)
    st["updated_at"] = _now()
    _write_json(dist_dir(article_dir) / STATE_FILE, st)


def get_status(article_dir: Path, channel: str) -> str:
    return (read_state(article_dir)["channels"].get(channel) or {}).get("status", "pending")


def _is_drifted(article_dir: Path, channel: str) -> bool:
    """静默版漂移判断（status 用，不打印）。"""
    entry = read_state(article_dir)["channels"].get(channel) or {}
    recorded = entry.get("source_digest")
    if not recorded:
        return False
    return recorded != _digest(read_final_text(article_dir))


def _source_drifted(article_dir: Path, channel: str) -> bool:
    """定稿是否已变更、而该渠道的文案还停在旧版本上。

    🔴 verify 和 dispatch **都要**查这一条。只在 verify 查是不够的：
    `plan --only weibo` 之后，小红书仍停在 verified，可它的文案对应的是旧定稿——
    光看状态就会把一份过期文案发出去，造成各平台说法不一致。
    每个渠道记自己的 source_digest，而不是共用计划里的那一个。
    """
    if not _is_drifted(article_dir, channel):
        return False
    print(f"[distribute] ✗ 定稿.md 已变更，{CHANNELS[channel]['label']} 的文案已过期。", file=sys.stderr)
    print(f"             重跑 `distribute plan --only {channel}` 并复核该渠道文案。", file=sys.stderr)
    return True


# ===== 【第 5 节】plan —— 产出各渠道的约束与待填槽 =====

def _slots_for(channel: str, ctx: dict, cfg: dict) -> dict:
    """该渠道要 agent 填的槽 + 必须遵守的硬约束。

    槽留空是**故意的**：脚本不编内容。规则性的东西（字数上限、标签格式）
    在这里说死，agent 照着填，verify 再机器复核一遍。
    """
    common = {
        "source_title": ctx["title"],
        "source_url": ctx["wechat_url"],
        "digest": ctx["digest"],
    }

    if channel == "xhs":
        return {
            **common,
            "constraints": {
                "title_max": int(cfg.get("title_max", 20)),
                "body_max": int(cfg.get("body_max", 1000)),
                "tag_prefix": "#",
                "tag_min": int(cfg.get("tag_min", 4)),
                "image_min": int(cfg.get("image_min", 6)),
                "image_max": int(cfg.get("image_max", 16)),
            },
            "fill": {"title": "", "body": "", "tags": []},
            "upstream_required": "xhs-outline.md（按 xhs-storyboard.md 提炼，禁按段落切）",
        }

    if channel == "weibo":
        return {
            **common,
            "constraints": {
                # 微博超 140 字折叠成「展开全文」，直接压阅读率。这是软上限不是硬上限，
                # 但骨架把它当硬门——想突破得显式改 profile，而不是随手写长。
                "body_max": int(cfg.get("body_soft_max", 140)),
                "tag_format": "#话题#（前后都要井号，与小红书不同）",
                "tag_min": int(cfg.get("tag_min", 2)),
                "image_max": int(cfg.get("image_max", 4)),
            },
            "fill": {"body": "", "tags": [], "images": []},
            "note": "URL 会被自动转 t.cn 短链，约占 25 字符，计入 140 字",
        }

    if channel == "podcast":
        return {
            **common,
            "constraints": {
                "shownotes_max": int(cfg.get("shownotes_max", 800)),
                "episode_title_max": int(cfg.get("episode_title_max", 60)),
            },
            "fill": {"episode_title": "", "shownotes": ""},
            "note": (
                "音频由 NotebookLM 生成，喂**裸定稿 markdown**、不做二次提炼；"
                "主持风格由 profile 的 podcast.focus_prompt 指向的提示词文件控制"
            ),
        }

    return dict(common)


def cmd_plan(article_dir: Path, only: str = "") -> int:
    title = read_final_title(article_dir)
    if not title:
        print("[distribute] ✗ 读不到定稿标题（.state.json 的 writing.title_final）", file=sys.stderr)
        print("             分发的上游是已定稿的文章，请先跑完写作阶段。", file=sys.stderr)
        return 2

    final_text = read_final_text(article_dir)
    if not final_text:
        print(f"[distribute] ✗ 找不到 {article_dir / '定稿.md'}", file=sys.stderr)
        return 2

    meta = read_article_meta(article_dir)
    wechat_url = read_wechat_url(article_dir)

    targets = [c.strip() for c in only.split(",") if c.strip()] if only else enabled_channels()
    unknown = [c for c in targets if c not in CHANNELS]
    if unknown:
        print(f"[distribute] ✗ 未知渠道：{', '.join(unknown)}", file=sys.stderr)
        print(f"             已注册：{', '.join(CHANNELS)}", file=sys.stderr)
        return 2

    if not targets:
        print("[distribute] 没有已启用的渠道。")
        print("             在 profile 的 brand.yaml 里配置 distribute.channels.<渠道>.enabled: true")
        return 1

    ctx = {
        "title": title,
        "digest": str(meta.get("digest") or "").strip(),
        "tags": meta.get("tags") or [],
        "series": str(meta.get("series") or "").strip(),
        "wechat_url": wechat_url,
        "images": list_source_images(article_dir),
        "final_chars": len(re.sub(r"\s", "", final_text)),
    }

    plan = {
        "schema_version": 1,
        "generated_at": _now(),
        "article_dir": str(article_dir),
        "source_digest": _digest(final_text),
        "context": ctx,
        "channels": {},
    }

    for ch in targets:
        cfg = channel_config(ch)
        plan["channels"][ch] = {
            "label": CHANNELS[ch]["label"],
            "dispatch_mode": CHANNELS[ch]["dispatch_mode"],
            "enabled": channel_enabled(ch),
            **_slots_for(ch, ctx, cfg),
        }
        channel_dir(article_dir, ch).mkdir(parents=True, exist_ok=True)
        set_status(article_dir, ch, "planned", source_digest=plan["source_digest"])

    plan_path = dist_dir(article_dir) / PLAN_FILE
    _write_json(plan_path, plan)

    print(f"[distribute] ✓ 分发计划已生成：{plan_path}")
    print(f"             正文 {ctx['final_chars']} 字 ｜ 可复用图 {len(ctx['images'])} 张")
    if not wechat_url:
        print("             ⚠ 尚无公众号永久链接（finalize 未跑）——各渠道文案里的原文链接会留空")
    for ch in targets:
        print(f"             · {CHANNELS[ch]['label']}（{CHANNELS[ch]['dispatch_mode']}）→ {channel_dir(article_dir, ch)}")
    print()
    print("             下一步：按 references/distribute.md 各渠道口径填写文案，")
    print("             写入 dist/<渠道>/文案.txt，再跑 `distribute verify <渠道>`。")
    if using_example_profile():
        print("             ⚠ 当前跑在示例 profile 上，账号与节目信息均为占位值。")
    return 0


# ===== 【第 6 节】verify —— 硬门 =====

def _parse_copy_file(path: Path) -> dict:
    """文案文件格式：首个空行前是标题段，其后是正文，`#` 开头的行汇总为标签。

    刻意选了「人能直接复制粘贴」的纯文本而不是 YAML——这些文件的最终用途
    就是被人整段选中贴进平台输入框，多一层语法就多一次贴错的机会。
    """
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    if not raw.strip():
        return {}
    blocks = re.split(r"\n\s*\n", raw, maxsplit=1)
    head = blocks[0].strip()
    body = blocks[1].strip() if len(blocks) > 1 else ""
    tags = re.findall(r"#[^#\s]+#?", raw)
    return {"head": head, "body": body, "tags": tags, "raw": raw}


def _display_width(text: str) -> int:
    """终端显示宽度：CJK 全角字符占 2 列。

    对齐用 len() 会让中文列参差不齐——`小红书图文` 是 5 个字符但占 10 列。
    """
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _visible_len(text: str) -> int:
    """平台计数口径：按字符数，不排除标点，但排除首尾空白与换行。"""
    return len(text.replace("\n", "").strip())


def cmd_verify(article_dir: Path, channel: str) -> int:
    if channel not in CHANNELS:
        print(f"[distribute] ✗ 未知渠道 {channel!r}", file=sys.stderr)
        return 2

    plan = _read_json(dist_dir(article_dir) / PLAN_FILE)
    if not plan:
        print("[distribute] ✗ 还没有分发计划，先跑 `distribute plan`", file=sys.stderr)
        return 2

    spec = (plan.get("channels") or {}).get(channel)
    if not spec:
        print(f"[distribute] ✗ 计划里没有 {channel}，重跑 `distribute plan --only {channel}`", file=sys.stderr)
        return 2

    if _source_drifted(article_dir, channel):
        return 2

    cdir = channel_dir(article_dir, channel)
    problems: list[str] = []

    if channel in ("xhs", "weibo"):
        copy_path = cdir / "文案.txt"
        parsed = _parse_copy_file(copy_path)
        if not parsed:
            print(f"[distribute] ✗ 缺文案：{copy_path}", file=sys.stderr)
            return 2

        cons = spec.get("constraints") or {}
        if channel == "xhs":
            tmax = cons.get("title_max", 20)
            if _visible_len(parsed["head"]) > tmax:
                problems.append(f"标题 {_visible_len(parsed['head'])} 字，超过 {tmax} 字上限")
            bmax = cons.get("body_max", 1000)
            if _visible_len(parsed["body"]) > bmax:
                problems.append(f"正文 {_visible_len(parsed['body'])} 字，超过 {bmax} 字上限")
            bad = [t for t in parsed["tags"] if t.endswith("#") and len(t) > 1]
            if bad:
                problems.append(f"标签用了微博的 #话题# 格式：{' '.join(bad[:3])}（小红书是 #标签）")
        else:
            bmax = cons.get("body_max", 140)
            total = _visible_len(parsed["raw"])
            if total > bmax:
                problems.append(f"全文 {total} 字，超过 {bmax} 字（微博会折叠成「展开全文」）")
            bad = [t for t in parsed["tags"] if not t.endswith("#")]
            if bad:
                problems.append(f"标签缺尾部井号：{' '.join(bad[:3])}（微博是 #话题#）")

        if len(parsed["tags"]) < cons.get("tag_min", 2):
            problems.append(f"标签只有 {len(parsed['tags'])} 个，少于 {cons.get('tag_min', 2)} 个")

    elif channel == "podcast":
        shownotes = cdir / "shownotes.md"
        if not shownotes.is_file():
            print(f"[distribute] ✗ 缺 shownotes：{shownotes}", file=sys.stderr)
            return 2
        audio = cdir / "audio.mp3"
        if not audio.is_file():
            problems.append("缺 audio.mp3（先跑 dispatch 生成，或手动放入）")
        elif audio.stat().st_size < 100_000:
            problems.append(f"audio.mp3 只有 {audio.stat().st_size} 字节，疑似生成失败")

    if problems:
        print(f"[distribute] ✗ {CHANNELS[channel]['label']} 未通过校验：", file=sys.stderr)
        for p in problems:
            print(f"             · {p}", file=sys.stderr)
        return 2

    set_status(article_dir, channel, "verified", verified_at=_now())
    print(f"[distribute] ✓ {CHANNELS[channel]['label']} 文案校验通过")
    return 0


# ===== 【第 7 节】dispatch —— 派发（默认 dry-run） =====

def cmd_dispatch(article_dir: Path, channel: str, confirm: bool = False) -> int:
    if channel not in CHANNELS:
        print(f"[distribute] ✗ 未知渠道 {channel!r}", file=sys.stderr)
        return 2
    if not channel_enabled(channel):
        print(f"[distribute] ✗ {channel} 未在 profile 中启用", file=sys.stderr)
        return 2

    status = get_status(article_dir, channel)
    if status != "verified":
        print(f"[distribute] ✗ 当前状态 {status}，必须先通过 `distribute verify {channel}`", file=sys.stderr)
        return 2

    if _source_drifted(article_dir, channel):
        return 2

    mode = CHANNELS[channel]["dispatch_mode"]
    cdir = channel_dir(article_dir, channel)

    if mode == "manual":
        # 小红书：平台没有开放发布接口，这里**只产手动发布包**。
        # 不去驱动 UI 自动化冒充「自动发布」——那既不稳定，也会拿账号安全冒险。
        print(f"[distribute] {CHANNELS[channel]['label']}：手动发布包已就绪")
        print(f"             目录：{cdir}")
        print(f"             文案：{cdir / '文案.txt'}（首段=标题，其余=正文）")
        imgs = cdir / "images"
        if imgs.is_dir():
            print(f"             图片：{imgs}（{len(list(imgs.glob('*')))} 张，按文件名顺序上传）")
        print("             小红书无开放发布接口，这一步只能人工完成。")
        if confirm:
            _write_json(cdir / RECEIPT_FILE, {
                "channel": channel, "mode": "manual",
                "dispatched_at": _now(),
                "note": "作者确认已手动发布",
            })
            set_status(article_dir, channel, "dispatched")
            print("             ✓ 已登记为「作者确认发布」")
        else:
            print("             确认发布后跑 `--confirm` 登记凭证。")
        return 0

    if not confirm:
        print(f"[distribute] dry-run：{CHANNELS[channel]['label']}（{mode}）")
        print(f"             产物目录：{cdir}")
        print("             这是**对外发布**动作，确认无误后加 --confirm 真正执行。")
        return 0

    # ---- 真派发：骨架阶段各 adapter 尚未接线 ----
    # 这里刻意不写「假装成功」的桩：宁可明确未实现，也不能让状态机记下一次没发生过的发布。
    print(f"[distribute] ✗ {CHANNELS[channel]['label']} 的自动派发尚未接线。", file=sys.stderr)
    print(f"             mode={mode}；接线步骤见 references/distribute.md §渠道适配器", file=sys.stderr)
    return 3


# ===== 【第 8 节】status =====

def cmd_status(article_dir: Path) -> int:
    title = read_final_title(article_dir) or "(未定稿)"
    st = read_state(article_dir)
    print(f"[distribute] {title}")
    print(f"             {article_dir}")
    print()

    cfg_ok = bool(distribute_config())
    if not cfg_ok:
        print("             ⚠ profile 里还没有 distribute 段，所有渠道均未启用。")
        print("               参考 profile.example/brand.yaml 的 `distribute:` 配置。")
        print()

    rows = []
    for ch, spec in CHANNELS.items():
        enabled = channel_enabled(ch)
        status = (st["channels"].get(ch) or {}).get("status", "pending")
        mark = {"pending": "·", "planned": "○", "drafted": "◐",
                "verified": "◑", "dispatched": "●"}.get(status, "?")
        if _is_drifted(article_dir, ch):
            mark, status = "⚠", f"{status}（定稿已变更，需重做）"
        rows.append((mark, spec["label"], spec["dispatch_mode"],
                     "启用" if enabled else "未启用", status))

    w = max(_display_width(r[1]) for r in rows)
    for mark, label, mode, en, status in rows:
        pad = " " * (w - _display_width(label))
        print(f"             {mark} {label}{pad}  {mode:<6}  {en}{'  ' if en == '启用' else ''}  {status}")

    print()
    wechat_url = read_wechat_url(article_dir)
    print(f"             公众号永久链接：{wechat_url or '（未 finalize）'}")
    return 0


# ===== 【第 9 节】CLI =====

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="distribute.py",
        description="一稿多投分发层：小红书 / 微博 / 播客",
    )
    parser.add_argument("--dir", default=".", help="文章目录（默认当前目录）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="各渠道状态一览")

    p_plan = sub.add_parser("plan", help="生成分发计划（约束 + 待填槽）")
    p_plan.add_argument("--only", default="", help="只规划指定渠道，逗号分隔")

    p_ver = sub.add_parser("verify", help="校验渠道文案（不通过 exit 2）")
    p_ver.add_argument("channel")

    p_dis = sub.add_parser("dispatch", help="派发到渠道（默认 dry-run）")
    p_dis.add_argument("channel")
    p_dis.add_argument("--confirm", action="store_true",
                       help="真正执行对外发布 / 登记手动发布凭证")

    args = parser.parse_args(argv)
    article_dir = Path(args.dir).resolve()
    if not article_dir.is_dir():
        print(f"[distribute] ✗ 目录不存在：{article_dir}", file=sys.stderr)
        return 2

    if args.cmd == "status":
        return cmd_status(article_dir)
    if args.cmd == "plan":
        return cmd_plan(article_dir, args.only)
    if args.cmd == "verify":
        return cmd_verify(article_dir, args.channel)
    if args.cmd == "dispatch":
        return cmd_dispatch(article_dir, args.channel, args.confirm)
    return 2


if __name__ == "__main__":
    sys.exit(main())
