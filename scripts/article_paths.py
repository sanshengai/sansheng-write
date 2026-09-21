#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者要亲手上传的文件名。

音乐、音乐封面、播客、播客封面都放在文章编号文件夹第一层，不放进 ``素材/``。
``素材/`` 只放正文插图。``dist/podcast/audio.mp3`` 仍是给官网和 RSS 取字节的
机器副本，不是作者上传时看到的那个文件名。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

THEME_COVER = Path("音乐封面.png")
PODCAST_COVER = Path("播客封面.png")
LEGACY_THEME_COVER = Path("素材/bgm_cover.png")
LEGACY_PODCAST_COVER = Path("素材/podcast_cover.png")
PODCAST_PREFIX = "播客 | "

# ASCII ``:`` 在 macOS 文件名里非法；``|`` 是作者指定的分隔符，必须留下。
_ILLEGAL = re.compile(r'[<>:"/\\?*\x00-\x1f]')


def podcast_filename(title: str) -> str:
    """``播客 | {文章标题}.mp3``。标题里的竖线保留，路径分隔符去掉。"""
    cleaned = _ILLEGAL.sub("", str(title or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = "未命名"
    name = f"{PODCAST_PREFIX}{cleaned}.mp3"
    while len(name.encode("utf-8")) > 240 and cleaned != "未命名":
        cleaned = cleaned[:-1].rstrip(" .") or "未命名"
        name = f"{PODCAST_PREFIX}{cleaned}.mp3"
    return name


def is_podcast_audio_name(name: str) -> bool:
    return name == "podcast.mp3" or (
        name.startswith(PODCAST_PREFIX) and name.endswith(".mp3")
    )


def article_title(article_dir: Path) -> str:
    """与分发侧一致：先 ``.state.json`` 的 title_final，再 article-meta，再定稿标题。"""
    state_path = article_dir / ".state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
        title = (
            ((state.get("stages") or {}).get("writing") or {}).get("title_final") or ""
        ).strip()
        if title:
            return title
    meta_path = article_dir / "article-meta.yaml"
    if meta_path.is_file():
        try:
            import yaml

            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            meta = {}
        except Exception:
            meta = {}
        if isinstance(meta, dict):
            title = str(meta.get("title") or "").strip()
            if title:
                return title
    draft = article_dir / "定稿.md"
    if draft.is_file():
        text = draft.read_text(encoding="utf-8", errors="replace")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
        if match:
            try:
                import yaml

                front = yaml.safe_load(match.group(1)) or {}
            except (OSError, ValueError):
                front = {}
            except Exception:
                front = {}
            if isinstance(front, dict):
                title = str(front.get("title") or "").strip()
                if title:
                    return title
    return ""


def podcast_upload_name(article_dir: Path) -> str:
    return podcast_filename(article_title(article_dir))


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_cover(article_dir: Path, *, kind: str) -> Path | None:
    """第一层的中文文件名优先。

    新旧两份字节相同时，继续认 ``素材/`` 里的旧文件作出处。这样第一次从旧路径
    复制到第一层之后，交付回执不会因为出处路径变了而判成另一份快照。
    """
    root_rel, legacy_rel = {
        "theme": (THEME_COVER, LEGACY_THEME_COVER),
        "podcast": (PODCAST_COVER, LEGACY_PODCAST_COVER),
    }[kind]
    root = article_dir / root_rel
    legacy = article_dir / legacy_rel
    root_ok = root.is_file() and root.stat().st_size > 0
    legacy_ok = legacy.is_file() and legacy.stat().st_size > 0
    if root_ok and legacy_ok and _sha256(root) == _sha256(legacy):
        return legacy
    if root_ok:
        return root
    if legacy_ok:
        return legacy
    return None


def cover_output(article_dir: Path, *, kind: str, force: bool = False) -> Path:
    """新封面写到文章编号文件夹第一层。已有旧文件时沿用它，除非强制重生成。"""
    root = article_dir / (THEME_COVER if kind == "theme" else PODCAST_COVER)
    if force:
        return root
    found = resolve_cover(article_dir, kind=kind)
    return found if found is not None else root
