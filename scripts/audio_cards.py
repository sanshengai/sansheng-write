#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信文章双音频卡的单一模板与机器块操作。

主题曲与播客在信息层级上同级、在移动端保持上下流式排列。两张卡共用同一
骨架，只用标题、用途标签和占位提示区分，避免两个脚本各自复制 HTML 后漂移。
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROLE_ORDER = ("theme", "podcast")
MARKERS = {
    "theme": ("<!-- AUDIO-CARD-START -->", "<!-- AUDIO-CARD-END -->"),
    "podcast": ("<!-- PODCAST-CARD-START -->", "<!-- PODCAST-CARD-END -->"),
}
CARD_COPY = {
    "theme": {
        "icon": "🎵",
        "title": "阅读配乐｜本文主题曲",
        "placeholder": "（👉 删除本段文字，并插入主题曲音频）",
    },
    "podcast": {
        "icon": "🎧",
        "title": "音频版本｜本期播客",
        "placeholder": "（👉 删除本段文字，并插入播客音频）",
    },
}


def block_pattern(role: str) -> re.Pattern[str]:
    start, end = MARKERS[role]
    return re.compile(
        rf"(?ms)(?:\r?\n)?{re.escape(start)}.*?{re.escape(end)}(?:\r?\n)?"
    )


def render_card(role: str, meta: str) -> str:
    """渲染一张块级音频卡；不得在这里放假播放按钮或 flex 容器。"""
    if role not in CARD_COPY:
        raise ValueError(f"未知音频卡角色：{role}")
    start, end = MARKERS[role]
    copy = CARD_COPY[role]
    safe_meta = html.escape(meta.strip(), quote=True)
    return f"""{start}
<section data-audio-role="{role}" style="margin: 20px 0; padding: 16px; border: 1px solid #d7e3ea; border-radius: 10px; background: #f2f7f9;">
  <section style="display: table; width: 100%; margin-bottom: 12px; border-bottom: 1px dashed #d7e3ea; padding-bottom: 8px;">
    <section style="display: table-cell; text-align: left; vertical-align: middle; font-size: 14px; color: #2F6F8F; font-weight: bold;"><span style="font-size: 16px; margin-right: 4px;">{copy['icon']}</span>{copy['title']}</section>
    <section style="display: table-cell; text-align: right; vertical-align: middle; font-size: 12px; color: #8a929a; font-weight: normal;">{safe_meta}</section>
  </section>
  <p style="text-align: center; margin: 10px 0; color: #b0b6bb; font-size: 13px;">{copy['placeholder']}</p>
</section>
{end}"""


def extract_cards(text: str) -> dict[str, str]:
    cards: dict[str, str] = {}
    for role in ROLE_ORDER:
        match = block_pattern(role).search(text)
        if match:
            cards[role] = match.group(0).strip()
    return cards


def strip_audio_cards(text: str) -> str:
    clean = text.replace("\r\n", "\n")
    for role in ROLE_ORDER:
        clean = block_pattern(role).sub("", clean)
    return re.sub(r"\n{3,}", "\n\n", clean).rstrip() + "\n"


def upsert_card(article_path: Path, role: str, meta: str) -> bool:
    """幂等写入指定卡片，并把已有双卡统一收口到文末的固定顺序。"""
    original = article_path.read_text(encoding="utf-8")
    cards = extract_cards(original)
    cards[role] = render_card(role, meta)
    body = strip_audio_cards(original).rstrip()
    tail = "\n\n".join(cards[key] for key in ROLE_ORDER if key in cards)
    updated = f"{body}\n\n{tail}\n"
    if updated == original.replace("\r\n", "\n"):
        return False
    article_path.write_text(updated, encoding="utf-8")
    return True


def marker_count(text: str, role: str) -> int:
    return text.count(MARKERS[role][0])


def locate_theme_audio(article_dir: Path) -> Path | None:
    """定位本轮主题曲；优先生成 sidecar，旧文章仅在候选唯一时退回。"""
    candidates = sorted(
        [
            *article_dir.glob("*.mp3"),
            *((article_dir / "素材").glob("*.mp3") if (article_dir / "素材").is_dir() else []),
        ]
    )
    matches: list[tuple[str, Path]] = []
    for mp3 in candidates:
        sidecar = mp3.with_suffix(".json")
        if not sidecar.is_file():
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("prompt_version") and data.get("song_name"):
            matches.append((str(data.get("generated_at") or ""), mp3))
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    return candidates[0] if len(candidates) == 1 else None
