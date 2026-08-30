#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Article-local theme-music provenance contract.

``_music-manifest.json`` is the only authority for selecting a theme playback
file.  File names, directory scans, mtimes, and generator sidecars are never
used to infer which MP3 is current or where it came from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MUSIC_MANIFEST_FILE = "_music-manifest.json"
MUSIC_MANIFEST_SCHEMA = 1
THEME_LABEL = "主题曲"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _configure_stdio() -> None:
    """Keep Chinese diagnostics readable under Windows legacy code pages."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ThemeAsset:
    path: Path
    relative_path: str
    sha256: str
    bytes: int
    duration_seconds: float
    title: str
    origin: dict[str, str]
    registry: dict[str, str]
    manifest: dict[str, Any]
    manifest_digest: str


def _inside_article(article_dir: Path, value: str | Path) -> tuple[Path | None, str]:
    root = article_dir.resolve()
    raw = Path(value)
    candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        relative = candidate.relative_to(root)
    except (ValueError, OSError):
        return None, "playback.path 越出文章目录"
    if not relative.parts or ".." in relative.parts:
        return None, "playback.path 非法"
    return candidate, relative.as_posix()


def build_music_manifest(
    article_dir: Path,
    audio_path: Path,
    *,
    title: str,
    duration_seconds: float,
    provider: str,
    model: str,
    mode: str,
    registry_reference: str,
    registry_entry: str,
) -> dict[str, Any]:
    """Build a manifest from explicit provenance; never infer origin metadata."""
    article_dir = Path(article_dir)
    audio, relative = _inside_article(article_dir, Path(audio_path))
    if audio is None or not audio.is_file():
        raise ValueError(f"主题曲 playback 文件不存在或越出文章目录：{audio_path}")
    fields = {
        "title": title,
        "origin.provider": provider,
        "origin.model": model,
        "origin.mode": mode,
        "registry.reference": registry_reference,
        "registry.entry": registry_entry,
    }
    missing = [name for name, value in fields.items() if not str(value or "").strip()]
    if missing:
        raise ValueError("音乐 manifest 缺显式字段：" + ", ".join(missing))
    duration = float(duration_seconds or 0)
    if duration <= 0:
        raise ValueError("duration_seconds 必须大于 0")
    return {
        "schema_version": MUSIC_MANIFEST_SCHEMA,
        "theme": {
            "role": "theme",
            "label": THEME_LABEL,
            "title": str(title).strip(),
            "playback": {
                "path": relative,
                "sha256": sha256_file(audio),
                "bytes": audio.stat().st_size,
                "duration_seconds": duration,
            },
            "origin": {
                "provider": str(provider).strip(),
                "model": str(model).strip(),
                "mode": str(mode).strip(),
            },
            "registry": {
                "reference": str(registry_reference).strip(),
                "entry": str(registry_entry).strip(),
            },
        },
    }


def write_music_manifest(
    article_dir: Path,
    audio_path: Path,
    **kwargs: Any,
) -> Path:
    """Atomically replace the article-local manifest after full validation."""
    article_dir = Path(article_dir).resolve()
    payload = build_music_manifest(article_dir, Path(audio_path), **kwargs)
    path = article_dir / MUSIC_MANIFEST_FILE
    candidate = path.with_name(path.name + ".next")
    candidate.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        parsed, errors = validate_music_manifest(article_dir, manifest_path=candidate)
        if errors or parsed is None:
            raise ValueError("；".join(errors) or "音乐 manifest 校验失败")
        candidate.replace(path)
    finally:
        if candidate.exists():
            candidate.unlink()
    return path


def validate_music_manifest(
    article_dir: Path,
    *,
    manifest_path: Path | None = None,
) -> tuple[ThemeAsset | None, list[str]]:
    """Validate schema, provenance fields, containment, bytes and SHA-256."""
    article_dir = Path(article_dir).resolve()
    path = Path(manifest_path) if manifest_path else article_dir / MUSIC_MANIFEST_FILE
    if not path.is_file():
        return None, [
            f"缺 {MUSIC_MANIFEST_FILE}；主题曲不得从任意 MP3 或最新 sidecar 猜测"
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{path.name} 解析失败：{exc}"]
    if not isinstance(payload, dict):
        return None, [f"{path.name} 顶层必须是 JSON object"]

    errors: list[str] = []
    if payload.get("schema_version") != MUSIC_MANIFEST_SCHEMA:
        errors.append(
            f"{path.name} schema_version 应为 {MUSIC_MANIFEST_SCHEMA}"
        )
    theme = payload.get("theme")
    if not isinstance(theme, dict):
        return None, errors + [f"{path.name} 缺 theme object"]
    if theme.get("role") != "theme":
        errors.append("theme.role 必须为 theme")
    if theme.get("label") != THEME_LABEL:
        errors.append(f"theme.label 必须使用通道中性标签「{THEME_LABEL}」")
    title = str(theme.get("title") or "").strip()
    if not title:
        errors.append("theme.title 不能为空")

    playback = theme.get("playback")
    if not isinstance(playback, dict):
        return None, errors + ["theme.playback 必须是 object"]
    relative_value = str(playback.get("path") or "").strip()
    audio, normalized = _inside_article(article_dir, relative_value)
    if audio is None:
        errors.append(normalized)
    elif relative_value.replace("\\", "/") != normalized:
        errors.append("playback.path 必须是规范化的文章内相对路径")
    elif not audio.is_file():
        errors.append(f"playback 文件不存在：{normalized}")

    expected_sha = str(playback.get("sha256") or "").strip().lower()
    if not _SHA256_RE.fullmatch(expected_sha):
        errors.append("playback.sha256 必须是 64 位小写 SHA-256")
    try:
        expected_bytes = int(playback.get("bytes"))
    except (TypeError, ValueError):
        expected_bytes = 0
    if expected_bytes <= 0:
        errors.append("playback.bytes 必须大于 0")
    try:
        duration = float(playback.get("duration_seconds"))
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        errors.append("playback.duration_seconds 必须大于 0")
    if audio is not None and audio.is_file():
        if expected_bytes != audio.stat().st_size:
            errors.append("playback.bytes 与当前文件不一致")
        if _SHA256_RE.fullmatch(expected_sha) and expected_sha != sha256_file(audio):
            errors.append("playback.sha256 与当前文件不一致")

    origin = theme.get("origin")
    if not isinstance(origin, dict):
        origin = {}
        errors.append("theme.origin 必须是 object")
    registry = theme.get("registry")
    if not isinstance(registry, dict):
        registry = {}
        errors.append("theme.registry 必须是 object")
    for prefix, values, keys in (
        ("origin", origin, ("provider", "model", "mode")),
        ("registry", registry, ("reference", "entry")),
    ):
        for key in keys:
            if not str(values.get(key) or "").strip():
                errors.append(f"theme.{prefix}.{key} 不能为空")
    if errors or audio is None:
        return None, errors
    clean_origin = {key: str(origin[key]).strip() for key in ("provider", "model", "mode")}
    clean_registry = {key: str(registry[key]).strip() for key in ("reference", "entry")}
    return ThemeAsset(
        path=audio,
        relative_path=normalized,
        sha256=expected_sha,
        bytes=expected_bytes,
        duration_seconds=duration,
        title=title,
        origin=clean_origin,
        registry=clean_registry,
        manifest=payload,
        manifest_digest=stable_digest(payload),
    ), []


def probe_audio_duration(path: Path) -> tuple[float | None, str]:
    """Measure duration with ffprobe; callers may not substitute a declaration."""
    executable = shutil.which("ffprobe")
    if not executable:
        return None, "找不到 ffprobe，无法复验音频时长"
    try:
        result = subprocess.run(
            [
                executable,
                "-v", "error",
                "-show_entries", "format=duration:stream=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"ffprobe 执行失败：{exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知错误").strip()[:300]
        return None, f"ffprobe 无法读取音频：{detail}"
    try:
        data = json.loads(result.stdout or "{}")
        values = [
            (data.get("format") or {}).get("duration"),
            *[item.get("duration") for item in data.get("streams") or []],
        ]
        durations = [float(value) for value in values if value not in (None, "N/A", "")]
        duration = max(durations) if durations else 0.0
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, f"ffprobe 时长解析失败：{exc}"
    return (duration, "") if duration > 0 else (None, "ffprobe 未返回正时长")


def duration_matches(declared: float, measured: float) -> bool:
    tolerance = max(1.0, float(declared) * 0.005)
    return abs(float(declared) - float(measured)) <= tolerance


def _main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="创建或验证文章本地 _music-manifest.json"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="为已明确来源的主题曲创建 manifest")
    create.add_argument("article_dir")
    create.add_argument("--audio", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--duration-seconds", required=True, type=float)
    create.add_argument("--provider", required=True)
    create.add_argument("--model", required=True)
    create.add_argument("--mode", required=True)
    create.add_argument("--registry-ref", required=True)
    create.add_argument("--registry-entry", default="")
    verify = sub.add_parser("verify", help="校验 manifest 与当前播放文件")
    verify.add_argument("article_dir")
    verify.add_argument("--probe-duration", action="store_true")
    args = parser.parse_args()

    article_dir = Path(args.article_dir).resolve()
    if args.command == "create":
        audio = Path(args.audio)
        if not audio.is_absolute():
            audio = article_dir / audio
        try:
            path = write_music_manifest(
                article_dir,
                audio,
                title=args.title,
                duration_seconds=args.duration_seconds,
                provider=args.provider,
                model=args.model,
                mode=args.mode,
                registry_reference=args.registry_ref,
                registry_entry=args.registry_entry or args.title,
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    asset, errors = validate_music_manifest(article_dir)
    if not errors and asset is not None and args.probe_duration:
        measured, probe_error = probe_audio_duration(asset.path)
        if probe_error:
            errors.append(probe_error)
        elif measured is not None and not duration_matches(asset.duration_seconds, measured):
            errors.append(
                f"playback.duration_seconds={asset.duration_seconds:g} 与 ffprobe={measured:g} 不一致"
            )
    if errors or asset is None:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        f"OK: {asset.relative_path} sha256={asset.sha256} "
        f"bytes={asset.bytes} duration={asset.duration_seconds:g}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
