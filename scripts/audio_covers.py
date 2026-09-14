#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题曲封面与播客封面：缺哪张生成哪张，产物固定落 ``素材/``。

背景（2026-09-14 第 99 篇）：主题曲封面原来由 Lyria 自动链顺手生成；主题曲改走
MiniMax 网页手工生成后这一步就断了，播客封面流水线里从来没有。作者要在微信
编辑器里给两条音频各配一张封面，结果连着两篇都得事后补。现在把两张封面收进
``handoff-assets`` 的前置步骤：交付上传文件前先保证它们存在。

- 主题曲封面：``素材/bgm_cover.png``，歌名来自 ``_music-manifest.json``。
- 播客封面：``素材/podcast_cover.png``，仅当 ``dist/podcast/audio.manifest.json``
  存在（即本篇真的有播客）时生成。
- 渲染器只走 ``baoyu-image-gen``，provider/model 按文章目录的 ``renderer-policy.json``
  逐项降级，与信息图同一条链；封面图不加品牌水印（与 music.md 既有约定一致）。
- 已存在且非空的封面不重生成；``--force`` 才覆盖。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .music_manifest import MUSIC_MANIFEST_FILE
    from .render_visuals import _load_policy, resolve_renderer_command
except ImportError:  # pragma: no cover - direct script execution
    from music_manifest import MUSIC_MANIFEST_FILE
    from render_visuals import _load_policy, resolve_renderer_command

THEME_COVER = Path("素材/bgm_cover.png")
PODCAST_COVER = Path("素材/podcast_cover.png")
PODCAST_MANIFEST = Path("dist/podcast/audio.manifest.json")
PROMPT_DIR = Path("素材/prompts")
GEN_LOG = ".gen-log.jsonl"
# codex-cli 出图机器级串行锁；另一篇文章在渲时等它放锁，别当失败。
LOCK_BUSY_MARK = "lock_busy"
LOCK_RETRY_LIMIT = 12
LOCK_RETRY_SECONDS = 60


def _primary_color() -> str:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from profile_config import colors as _colors

        return str(_colors().get("primary") or "#2F6F8F")
    except Exception:
        return "#2F6F8F"


def _frontmatter_field(article_dir: Path, key: str) -> str:
    """从 定稿.md frontmatter 取 title / description，取不到返回空串。"""
    draft = article_dir / "定稿.md"
    if not draft.is_file():
        return ""
    text = draft.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return ""
    head = text.split("---", 2)
    if len(head) < 3:
        return ""
    for line in head[1].splitlines():
        if line.strip().startswith(f"{key}:"):
            value = line.split(":", 1)[1].strip()
            return value.strip('"').strip("'")
    return ""


def _theme_title(article_dir: Path) -> str:
    manifest = article_dir / MUSIC_MANIFEST_FILE
    if not manifest.is_file():
        return ""
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    theme = payload.get("theme") if isinstance(payload, dict) else None
    return str((theme or {}).get("title") or "").strip()


def _shared_style(primary: str) -> str:
    return (
        f"Mood: contemplative, intimate, unrushed, ambient lighting with deep warm horizon glow. "
        f"Color palette: deep cinematic dark background with a muted accent of {primary}, "
        f"warm cream highlights, a single warm ember spark. "
        f"Style: hand-painted digital, soft edges, subtle gradients, one central focal element, "
        f"ample negative space. "
        f"NO realistic people, NO text, NO watermark, NO logos, NO UI elements. 1:1 square aspect ratio."
    )


def build_theme_cover_prompt(song_title: str, digest: str, primary: str) -> str:
    theme = digest.strip() or "a quiet desk at dawn"
    return (
        f'A cinematic, painterly album cover for a Mandarin vocal song titled "{song_title}". '
        f"The song accompanies an article about: {theme} "
        f"Translate that subject into one calm, symbolic still-life scene; the objects may hint at the "
        f"subject but stay abstract and logo-free. Must look like a legitimate album cover, not an "
        f"infographic. " + _shared_style(primary)
    )


def build_podcast_cover_prompt(article_title: str, digest: str, primary: str) -> str:
    subject = digest.strip() or article_title.strip() or "a late-evening conversation"
    return (
        f"A cinematic, painterly podcast episode cover for a Mandarin talk episode. The episode "
        f"discusses: {subject} Render it as one quiet, symbolic evening scene, like two people talking "
        f"it through over a desk lamp; objects stay abstract and logo-free. Must look like a legitimate "
        f"podcast cover, not an infographic. " + _shared_style(primary)
    )


def _log(article_dir: Path, record: dict[str, Any]) -> None:
    record = {"at": datetime.now(timezone.utc).isoformat(), **record}
    with (article_dir / GEN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _render_one(
    article_dir: Path,
    *,
    stage: str,
    prompt_file: Path,
    output: Path,
    command: list[str],
    renderers: list[dict[str, Any]],
) -> list[str]:
    """按策略顺序尝试；每个 renderer 内部只对 lock_busy 重试。"""
    errors: list[str] = []
    for renderer in renderers:
        args = list(command) + [
            "--promptfiles", str(prompt_file),
            "--image", str(output),
            "--quality", str(renderer.get("quality") or "2k"),
            "--imageSize", str(renderer.get("imageSize") or "1K"),
        ]
        if renderer.get("provider"):
            args += ["--provider", str(renderer["provider"])]
        if renderer.get("model"):
            args += ["--model", str(renderer["model"])]
        for attempt in range(1, LOCK_RETRY_LIMIT + 1):
            completed = subprocess.run(
                args, cwd=str(article_dir), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=900, check=False,
            )
            combined = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
                _log(article_dir, {
                    "stage": stage, "renderer": "baoyu-image-gen",
                    "provider": renderer.get("provider"), "model": renderer.get("model"),
                    "attempt": attempt, "output": str(output.relative_to(article_dir)),
                    "prompt": str(prompt_file.relative_to(article_dir)),
                })
                return []
            if LOCK_BUSY_MARK in combined and attempt < LOCK_RETRY_LIMIT:
                time.sleep(LOCK_RETRY_SECONDS)
                continue
            errors.append(
                f"{stage} renderer {renderer.get('id')} 失败（exit={completed.returncode}）："
                f"{combined.strip()[-300:]}"
            )
            break
    return errors


def ensure_audio_covers(
    article_dir: Path, *, force: bool = False
) -> tuple[list[Path], list[str]]:
    """保证主题曲封面（必需）与播客封面（有播客才需要）存在；返回 (就位文件, 错误)。"""
    article_dir = Path(article_dir).resolve()
    if not article_dir.is_dir():
        return [], [f"文章目录不存在：{article_dir}"]
    primary = _primary_color()
    digest = _frontmatter_field(article_dir, "description")
    title = _frontmatter_field(article_dir, "title")
    song = _theme_title(article_dir)

    jobs: list[tuple[str, Path, str]] = []
    if not song:
        return [], [f"缺 {MUSIC_MANIFEST_FILE} 或其中无歌名，无法生成主题曲封面"]
    jobs.append(("theme_cover", THEME_COVER, build_theme_cover_prompt(song, digest, primary)))
    if (article_dir / PODCAST_MANIFEST).is_file():
        jobs.append(("podcast_cover", PODCAST_COVER, build_podcast_cover_prompt(title, digest, primary)))

    ready: list[Path] = []
    pending: list[tuple[str, Path, str]] = []
    for stage, rel, prompt in jobs:
        target = article_dir / rel
        if target.is_file() and target.stat().st_size > 0 and not force:
            ready.append(target)
        else:
            pending.append((stage, rel, prompt))
    if not pending:
        return ready, []

    command, _revision, errors = resolve_renderer_command()
    if errors or command is None:
        return ready, errors
    renderers, policy_errors = _load_policy(article_dir)
    if policy_errors:
        return ready, policy_errors
    (article_dir / PROMPT_DIR).mkdir(parents=True, exist_ok=True)
    (article_dir / THEME_COVER).parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for stage, rel, prompt in pending:
        prompt_file = article_dir / PROMPT_DIR / f"{rel.stem}.md"
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
        item_errors = _render_one(
            article_dir, stage=stage, prompt_file=prompt_file,
            output=article_dir / rel, command=command, renderers=renderers,
        )
        if item_errors:
            failures.extend(item_errors)
        else:
            ready.append(article_dir / rel)
    return ready, failures


def _main() -> int:
    parser = argparse.ArgumentParser(description="生成缺失的主题曲封面 / 播客封面（素材/）")
    parser.add_argument("article_dir", nargs="?", default=".")
    parser.add_argument("--force", action="store_true", help="已存在也重新生成")
    args = parser.parse_args()
    ready, errors = ensure_audio_covers(Path(args.article_dir), force=args.force)
    for path in ready:
        print(f"✅ {path}")
    if errors:
        print("❌ 封面生成失败：")
        for error in errors:
            print(f"   • {error}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
