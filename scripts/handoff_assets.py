#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export only receipt-bound assets for manual upload.

The export is a deterministic, immutable snapshot.  It never searches for
plausible files: cover comes from the sealed visual receipt, theme playback
comes from ``_music-manifest.json``, and an optional podcast comes from its
audio manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from .evidence import sha256_file, stable_digest, verify_visual_receipt
    from .profile_config import load_secret
    from .music_manifest import (
        MUSIC_MANIFEST_FILE,
        ThemeAsset,
        duration_matches,
        probe_audio_duration,
        validate_music_manifest,
    )
except ImportError:  # pragma: no cover - direct script execution
    from evidence import sha256_file, stable_digest, verify_visual_receipt
    from profile_config import load_secret
    from music_manifest import (
        MUSIC_MANIFEST_FILE,
        ThemeAsset,
        duration_matches,
        probe_audio_duration,
        validate_music_manifest,
    )


HANDOFF_DIR_ENV = "SANSHENG_WRITE_HANDOFF_DIR"
HANDOFF_RECEIPT_FILE = "_handoff-receipt.json"
HANDOFF_SCHEMA = 1
PODCAST_AUDIO = Path("dist/podcast/audio.mp3")
PODCAST_MANIFEST = Path("dist/podcast/audio.manifest.json")
DurationProbe = Callable[[Path], tuple[float | None, str]]
VisualVerifier = Callable[[Path], tuple[dict | None, list[str]]]


class HandoffError(RuntimeError):
    pass


def _configure_stdio() -> None:
    """Keep Chinese diagnostics readable under Windows legacy code pages."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class CopySpec:
    role: str
    source: Path
    destination: str
    sha256: str
    bytes: int


def _safe_name(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:80].rstrip(" .")


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _measure_duration(
    path: Path,
    declared: float,
    *,
    duration_probe: DurationProbe,
    label: str,
) -> tuple[float | None, list[str]]:
    measured, error = duration_probe(path)
    if error or measured is None:
        return None, [f"{label} 时长复验失败：{error or '未返回时长'}"]
    if not duration_matches(declared, measured):
        return None, [
            f"{label} manifest 时长 {declared:g}s 与 ffprobe {measured:g}s 不一致"
        ]
    return measured, []


def _cover_from_visual_receipt(
    article_dir: Path,
    *,
    visual_verifier: VisualVerifier,
) -> tuple[dict[str, Any] | None, CopySpec | None, list[str]]:
    receipt, errors = visual_verifier(article_dir)
    if errors or receipt is None:
        return None, None, list(errors or ["视觉 receipt 不可用"])
    manifest = receipt.get("manifest") or {}
    assets = manifest.get("assets") or []
    covers = [
        item
        for item in assets
        if isinstance(item, dict)
        and (item.get("stage") == "cover" or item.get("path") == "素材/cover.png")
    ]
    if len(covers) != 1:
        return receipt, None, [f"视觉 receipt 中封面应恰好 1 项，当前 {len(covers)} 项"]
    item = covers[0]
    relative = str(item.get("path") or "").replace("\\", "/")
    source = (article_dir / Path(relative)).resolve()
    try:
        source.relative_to(article_dir.resolve())
    except (ValueError, OSError):
        return receipt, None, ["视觉 receipt 的封面路径越出文章目录"]
    if not source.is_file():
        return receipt, None, [f"视觉 receipt 封面不存在：{relative}"]
    digest = sha256_file(source)
    if digest != str(item.get("sha256") or ""):
        return receipt, None, ["视觉 receipt 封面 SHA-256 与当前文件不一致"]
    try:
        expected_bytes = int(item.get("bytes"))
    except (TypeError, ValueError):
        return receipt, None, ["视觉 receipt 封面缺合法 bytes"]
    if expected_bytes <= 0:
        return receipt, None, ["视觉 receipt 封面 bytes 必须大于 0"]
    if expected_bytes != source.stat().st_size:
        return receipt, None, ["视觉 receipt 封面 bytes 与当前文件不一致"]
    suffix = source.suffix.lower() or ".png"
    spec = CopySpec("cover", source, f"cover{suffix}", digest, source.stat().st_size)
    entry = {
        "role": "cover",
        "label": "封面",
        "source": {
            "path": relative,
            "sha256": digest,
            "bytes": source.stat().st_size,
            "receipt": "_visual-receipt.json",
            # Bind the deterministic visual manifest, not the seal timestamp.
            "receipt_digest": str(receipt.get("manifest_digest") or stable_digest(manifest)),
        },
        "handoff": {
            "path": spec.destination,
            "sha256": digest,
            "bytes": source.stat().st_size,
        },
    }
    return entry, spec, []


def _theme_from_manifest(
    article_dir: Path,
    *,
    duration_probe: DurationProbe,
) -> tuple[dict[str, Any] | None, CopySpec | None, list[str]]:
    theme, errors = validate_music_manifest(article_dir)
    if errors or theme is None:
        return None, None, list(errors or ["主题曲 manifest 不可用"])
    measured, measure_errors = _measure_duration(
        theme.path,
        theme.duration_seconds,
        duration_probe=duration_probe,
        label="主题曲",
    )
    if measure_errors or measured is None:
        return None, None, measure_errors
    suffix = theme.path.suffix.lower() or ".mp3"
    destination = f"theme-{_safe_name(theme.title, fallback='audio')}{suffix}"
    spec = CopySpec("theme", theme.path, destination, theme.sha256, theme.bytes)
    entry = {
        "role": "theme",
        "label": "主题曲",
        "title": theme.title,
        "duration_seconds": theme.duration_seconds,
        "measured_duration_seconds": round(measured, 6),
        "origin": theme.origin,
        "registry": theme.registry,
        "source": {
            "path": theme.relative_path,
            "sha256": theme.sha256,
            "bytes": theme.bytes,
            "receipt": MUSIC_MANIFEST_FILE,
            "receipt_digest": theme.manifest_digest,
        },
        "handoff": {
            "path": destination,
            "sha256": theme.sha256,
            "bytes": theme.bytes,
        },
    }
    return entry, spec, []


def _podcast_from_manifest(
    article_dir: Path,
    *,
    duration_probe: DurationProbe,
) -> tuple[dict[str, Any] | None, CopySpec | None, list[str]]:
    audio = article_dir / PODCAST_AUDIO
    manifest_path = article_dir / PODCAST_MANIFEST
    if not audio.exists() and not manifest_path.exists():
        return None, None, []
    if not audio.is_file() or not manifest_path.is_file():
        return None, None, [
            "播客资产不完整：audio.mp3 与 audio.manifest.json 必须同时存在"
        ]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, [f"播客 manifest 解析失败：{exc}"]
    if not isinstance(manifest, dict):
        return None, None, ["播客 manifest 顶层必须是 JSON object"]
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("播客 manifest schema_version 应为 1")
    digest = sha256_file(audio)
    if str(manifest.get("audio_sha256") or "") != digest:
        errors.append("播客 manifest audio_sha256 与当前文件不一致")
    try:
        expected_bytes = int(manifest.get("bytes"))
    except (TypeError, ValueError):
        expected_bytes = 0
    if expected_bytes != audio.stat().st_size:
        errors.append("播客 manifest bytes 与当前文件不一致")
    try:
        declared = float(manifest.get("duration_seconds"))
    except (TypeError, ValueError):
        declared = 0.0
    if declared <= 0:
        errors.append("播客 manifest duration_seconds 必须大于 0")
    measured: float | None = None
    if not errors:
        measured, measure_errors = _measure_duration(
            audio,
            declared,
            duration_probe=duration_probe,
            label="播客",
        )
        errors.extend(measure_errors)
    if errors or measured is None:
        return None, None, errors
    spec = CopySpec("podcast", audio, "podcast.mp3", digest, audio.stat().st_size)
    entry = {
        "role": "podcast",
        "label": "播客",
        "duration_seconds": declared,
        "measured_duration_seconds": round(measured, 6),
        "source": {
            "path": PODCAST_AUDIO.as_posix(),
            "sha256": digest,
            "bytes": audio.stat().st_size,
            "receipt": PODCAST_MANIFEST.as_posix(),
            "receipt_digest": stable_digest(manifest),
        },
        "handoff": {
            "path": spec.destination,
            "sha256": digest,
            "bytes": audio.stat().st_size,
        },
    }
    return entry, spec, []


def build_handoff_snapshot(
    article_dir: Path,
    *,
    revision: str = "",
    duration_probe: DurationProbe = probe_audio_duration,
    visual_verifier: VisualVerifier = verify_visual_receipt,
) -> tuple[dict[str, Any] | None, list[CopySpec], list[str]]:
    """Resolve and verify the exact upload set without writing anything."""
    article_dir = Path(article_dir).resolve()
    if not article_dir.is_dir():
        return None, [], [f"文章目录不存在：{article_dir}"]
    entries: list[dict[str, Any]] = []
    specs: list[CopySpec] = []
    errors: list[str] = []
    for loader in (_cover_from_visual_receipt, _theme_from_manifest):
        kwargs: dict[str, Any] = (
            {"visual_verifier": visual_verifier}
            if loader is _cover_from_visual_receipt
            else {"duration_probe": duration_probe}
        )
        entry, spec, item_errors = loader(article_dir, **kwargs)
        errors.extend(item_errors)
        if entry is not None and spec is not None:
            entries.append(entry)
            specs.append(spec)
    podcast_entry, podcast_spec, podcast_errors = _podcast_from_manifest(
        article_dir,
        duration_probe=duration_probe,
    )
    errors.extend(podcast_errors)
    if podcast_entry is not None and podcast_spec is not None:
        entries.append(podcast_entry)
        specs.append(podcast_spec)
    if errors:
        return None, [], errors
    payload = {
        "schema_version": HANDOFF_SCHEMA,
        "article": {"directory": article_dir.name},
        "revision": str(revision or ""),
        "assets": entries,
    }
    return payload, specs, []


def _verify_existing(target: Path, expected: dict[str, Any]) -> tuple[bool, list[str]]:
    receipt_path = target / HANDOFF_RECEIPT_FILE
    if not receipt_path.is_file():
        return False, [f"目标已存在但缺 {HANDOFF_RECEIPT_FILE}"]
    try:
        actual = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"目标 receipt 无法读取：{exc}"]
    if actual != expected:
        return False, ["目标已有不同来源快照；请显式使用 --revision"]
    errors: list[str] = []
    for asset in expected.get("assets") or []:
        handoff = asset.get("handoff") or {}
        relative = str(handoff.get("path") or "")
        path = target / relative
        if not path.is_file():
            errors.append(f"幂等目标缺文件：{relative}")
            continue
        if path.stat().st_size != int(handoff.get("bytes") or 0):
            errors.append(f"幂等目标 bytes 不一致：{relative}")
        if sha256_file(path) != str(handoff.get("sha256") or ""):
            errors.append(f"幂等目标 SHA-256 不一致：{relative}")
    return not errors, errors


def export_handoff_assets(
    article_dir: Path,
    *,
    target_root: Path | None = None,
    revision: str = "",
    duration_probe: DurationProbe = probe_audio_duration,
    visual_verifier: VisualVerifier = verify_visual_receipt,
) -> tuple[Path | None, str, list[str]]:
    """Copy a verified snapshot through a sibling temp dir and atomic rename."""
    article_dir = Path(article_dir).resolve()
    raw_root = str(
        target_root
        or os.environ.get(HANDOFF_DIR_ENV, "").strip()
        or load_secret(HANDOFF_DIR_ENV, required=False)
    ).strip()
    if not raw_root:
        return None, "", [f"未配置 {HANDOFF_DIR_ENV}"]
    root = Path(raw_root).expanduser().resolve()
    revision_value = str(revision or "").strip()
    if revision_value and not re.fullmatch(r"[A-Za-z0-9._-]+", revision_value):
        return None, "", ["--revision 只允许字母、数字、点、下划线与连字符"]
    receipt, specs, errors = build_handoff_snapshot(
        article_dir,
        revision=revision_value,
        duration_probe=duration_probe,
        visual_verifier=visual_verifier,
    )
    if errors or receipt is None:
        return None, "", errors
    folder = _safe_name(article_dir.name, fallback="article")
    if revision_value:
        folder += f"--{revision_value}"
    target = root / folder
    root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        same, existing_errors = _verify_existing(target, receipt)
        return (target, "unchanged", []) if same else (None, "", existing_errors)

    temp = Path(tempfile.mkdtemp(prefix=f".{folder}.tmp-", dir=root))
    try:
        for spec in specs:
            destination = temp / spec.destination
            shutil.copyfile(spec.source, destination)
            if destination.stat().st_size != spec.bytes:
                raise HandoffError(f"复制后 bytes 不一致：{spec.destination}")
            if sha256_file(destination) != spec.sha256:
                raise HandoffError(f"复制后 SHA-256 不一致：{spec.destination}")
        (temp / HANDOFF_RECEIPT_FILE).write_bytes(_canonical_json(receipt))
        try:
            temp.rename(target)
        except FileExistsError:
            same, existing_errors = _verify_existing(target, receipt)
            if same:
                return target, "unchanged", []
            raise HandoffError("目标在原子落盘前被另一进程占用：" + "；".join(existing_errors))
        return target, "created", []
    except (OSError, HandoffError) as exc:
        return None, "", [str(exc)]
    finally:
        if temp.exists():
            resolved = temp.resolve()
            if resolved.parent == root and resolved.name.startswith(f".{folder}.tmp-"):
                shutil.rmtree(resolved)


def _main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="导出封面、主题曲及可选播客的可验证手工上传包"
    )
    parser.add_argument("article_dir")
    parser.add_argument(
        "--target-root",
        default="",
        help=f"覆盖 {HANDOFF_DIR_ENV} / .env 中的交接根目录",
    )
    parser.add_argument(
        "--revision",
        default="",
        help="目标已有不同快照时使用新的 revision 标识，如 r2",
    )
    args = parser.parse_args()
    target, status, errors = export_handoff_assets(
        Path(args.article_dir),
        target_root=Path(args.target_root) if args.target_root else None,
        revision=args.revision,
    )
    if errors or target is None:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print(f"{status}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
