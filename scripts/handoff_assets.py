#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expose receipt-bound upload assets at the article folder's top level.

The export is a deterministic, immutable snapshot.  It never searches for
plausible files: cover comes from the sealed visual receipt, theme playback
comes from ``_music-manifest.json``, and an optional podcast comes from its
audio manifest.
"""

from __future__ import annotations

import argparse
import hashlib
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
    from .music_manifest import (
        MUSIC_MANIFEST_FILE,
        ThemeAsset,
        duration_matches,
        probe_audio_duration,
        validate_music_manifest,
    )
except ImportError:  # pragma: no cover - direct script execution
    from evidence import sha256_file, stable_digest, verify_visual_receipt
    from music_manifest import (
        MUSIC_MANIFEST_FILE,
        ThemeAsset,
        duration_matches,
        probe_audio_duration,
        validate_music_manifest,
    )


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


THEME_COVER = Path("素材/bgm_cover.png")
PODCAST_COVER = Path("素材/podcast_cover.png")


def _audio_covers(
    article_dir: Path,
    *,
    podcast_present: bool,
) -> tuple[list[dict[str, Any]], list[CopySpec], list[str]]:
    """主题曲封面必交付；播客封面在本篇有播客时必交付。

    两张图由 ``audio_covers.ensure_audio_covers`` 在 handoff 前生成（pipeline
    ``handoff-assets`` 已串好）；这里只认已存在的文件，缺了就报错而不是静默少给——
    作者是在微信编辑器里逐条插音频时才发现少封面的，事后补比事前拦贵得多。
    """
    wanted: list[tuple[str, str, Path, str]] = [
        ("theme_cover", "主题曲封面", THEME_COVER, "theme-cover.png"),
    ]
    if podcast_present:
        wanted.append(("podcast_cover", "播客封面", PODCAST_COVER, "podcast-cover.png"))
    entries: list[dict[str, Any]] = []
    specs: list[CopySpec] = []
    errors: list[str] = []
    for role, label, relative, destination in wanted:
        source = article_dir / relative
        if not source.is_file() or source.stat().st_size == 0:
            errors.append(
                f"缺{label}：{relative.as_posix()}；先运行 audio_covers.py 生成"
            )
            continue
        digest = sha256_file(source)
        size = source.stat().st_size
        specs.append(CopySpec(role, source, destination, digest, size))
        entries.append({
            "role": role,
            "label": label,
            "source": {"path": relative.as_posix(), "sha256": digest, "bytes": size},
            "handoff": {"path": destination, "sha256": digest, "bytes": size},
        })
    return entries, specs, errors


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
    cover_entries, cover_specs, cover_errors = _audio_covers(
        article_dir,
        podcast_present=(article_dir / PODCAST_MANIFEST).is_file(),
    )
    errors.extend(cover_errors)
    entries.extend(cover_entries)
    specs.extend(cover_specs)
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
    """Default to the article itself; a separate export requires target_root."""
    article_dir = Path(article_dir).resolve()
    revision_value = str(revision or "").strip()
    if revision_value and target_root is None:
        return None, "", ["--revision 仅用于显式 --target-root 的独立导出"]
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
    if target_root is None:
        return _export_in_article(article_dir, receipt, specs)
    root = Path(target_root).expanduser().resolve()
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


def _export_in_article(
    article_dir: Path, receipt: dict[str, Any], specs: list[CopySpec]
) -> tuple[Path | None, str, list[str]]:
    """Preserve all article files; never overwrite a conflicting upload asset."""
    flat_specs = []
    for entry, spec in zip(receipt["assets"], specs):
        # An existing root-level song already has a useful name; do not make a
        # second theme-prefixed copy beside it. Nested songs keep their basename.
        name = spec.source.name if spec.role == "theme" else spec.destination
        entry["handoff"]["path"] = name
        flat_specs.append(CopySpec(spec.role, spec.source, name, spec.sha256, spec.bytes))
    names = [spec.destination for spec in flat_specs]
    if len({name.casefold() for name in names}) != len(names) or HANDOFF_RECEIPT_FILE in names:
        return None, "", ["上传资产同名，无法放在文章第一层；请先区分源文件名称"]
    payloads = {spec.destination: (spec.bytes, spec.sha256) for spec in flat_specs}
    receipt_bytes = _canonical_json(receipt)
    payloads[HANDOFF_RECEIPT_FILE] = (len(receipt_bytes), hashlib.sha256(receipt_bytes).hexdigest())
    # Check the complete set before creating anything, including the receipt.
    missing = []
    for name, (size, digest) in payloads.items():
        destination = article_dir / name
        if destination.is_symlink():
            return None, "", [f"文章第一层目标是符号链接，拒绝写入：{name}"]
        if not destination.exists():
            missing.append(name)
        elif not destination.is_file() or destination.stat().st_size != size or sha256_file(destination) != digest:
            return None, "", [f"文章第一层已有不同内容，未覆盖：{name}；请核实旧文件后再处理"]
    if not missing:
        return article_dir, "unchanged", []
    temp = Path(tempfile.mkdtemp(prefix=".handoff-tmp-", dir=article_dir))
    created: list[tuple[Path, int]] = []
    try:
        for spec in flat_specs:
            if spec.destination not in missing:
                continue
            staged = temp / spec.destination
            shutil.copyfile(spec.source, staged)
            if staged.stat().st_size != spec.bytes or sha256_file(staged) != spec.sha256:
                raise HandoffError(f"复制后校验失败：{spec.destination}")
        if HANDOFF_RECEIPT_FILE in missing:
            (temp / HANDOFF_RECEIPT_FILE).write_bytes(receipt_bytes)
        # link() atomically installs a new file without replacing concurrent
        # writes; assets come first, the receipt is installed last.
        for name in missing:
            destination = article_dir / name
            os.link(temp / name, destination)
            created.append((destination, destination.stat().st_ino))
        return article_dir, "created", []
    except (OSError, HandoffError) as exc:
        for destination, inode in reversed(created):
            size, digest = payloads[destination.name]
            if (not destination.is_symlink() and destination.is_file()
                    and destination.stat().st_ino == inode
                    and destination.stat().st_size == size
                    and sha256_file(destination) == digest):
                destination.unlink()
        return None, "", [str(exc)]
    finally:
        shutil.rmtree(temp)


def _main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="将封面、主题曲及可选播客交付到文章目录第一层"
    )
    parser.add_argument("article_dir")
    parser.add_argument(
        "--target-root",
        default="",
        help="仅在明确需要独立副本时指定导出根目录；默认直接放在文章目录",
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


# ---------------------------------------------------------------------------
# 主仓镜像：作者只在 SANSHENG_WRITE_ARCHIVE_DIR（主仓 文稿成品/）找成品。
# 文章在 git worktree 里生产时，tracked 文件靠合回主线快进到主仓，但 mp3 / mp4
# 这类被 .gitignore 的交付物永远到不了主仓——2026-09-15、09-17 连续两篇作者在
# worktree 里找不到音频视频。镜像只复制、不删除、不覆盖不同内容。
# ---------------------------------------------------------------------------
MIRROR_EXTRA_DIRS = ("素材/视频", "素材/作者素材")
MIRROR_EXTRA_FILES = ("dist/podcast/audio.mp3", "dist/podcast/audio.json",
                      "dist/podcast/audio.manifest.json", "dist/podcast/shownotes.md")
MIRROR_TOP_SUFFIXES = (".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".mp4", ".mov")


def mirror_deliverables_to_archive_root(
    article_dir: Path, archive_root: Path | None
) -> tuple[Path | None, list[str], list[str]]:
    """把文章第一层的上传文件、作者供图、视频与播客产物镜像到主仓同名目录。

    返回 (镜像目录 | None, 已复制的相对路径, 错误)。文章目录本身已在归档根下、
    或未配置归档根时返回 (None, [], [])，不算错误。目标同路径内容不同 → 记错误、
    不覆盖；内容相同 → 跳过。
    """
    article_dir = Path(article_dir).resolve()
    if archive_root is None:
        return None, [], []
    root = Path(archive_root).expanduser().resolve()
    try:
        article_dir.relative_to(root)
        return None, [], []  # 已经在主仓成品目录里生产，无需镜像
    except ValueError:
        pass
    target = root / article_dir.name
    sources: list[Path] = []
    for child in sorted(article_dir.iterdir()):
        if child.is_file() and child.suffix.lower() in MIRROR_TOP_SUFFIXES:
            sources.append(child)
    for rel in MIRROR_EXTRA_DIRS:
        folder = article_dir / rel
        if folder.is_dir():
            sources.extend(p for p in sorted(folder.rglob("*")) if p.is_file())
    for rel in MIRROR_EXTRA_FILES:
        f = article_dir / rel
        if f.is_file():
            sources.append(f)
    copied: list[str] = []
    errors: list[str] = []
    for src in sources:
        rel = src.relative_to(article_dir)
        dst = target / rel
        if dst.is_symlink():
            errors.append(f"镜像目标是符号链接，拒绝写入：{rel}")
            continue
        if dst.exists():
            if dst.stat().st_size == src.stat().st_size and sha256_file(dst) == sha256_file(src):
                continue
            errors.append(f"主仓已有不同内容，未覆盖：{rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.tmp")
        shutil.copyfile(src, tmp)
        if sha256_file(tmp) != sha256_file(src):
            tmp.unlink(missing_ok=True)
            errors.append(f"镜像复制后哈希不一致：{rel}")
            continue
        os.replace(tmp, dst)
        copied.append(str(rel))
    return target, copied, errors
