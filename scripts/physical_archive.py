#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safely move one finished article from a worktree into a permanent archive.

The registry command ``pipeline.py archive`` intentionally remains metadata-only.
This module handles the separate filesystem handoff after every article writer has
stopped: snapshot, stage, SHA-256 verify, place, and optionally remove the source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECEIPT_FILE = "_physical-archive-receipt.json"
_ARTICLE_NAME_RE = re.compile(r"^[0-9]+-.+")


class PhysicalArchiveError(RuntimeError):
    """The archive operation cannot continue without risking data loss."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(root: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Return deterministic file hashes and directory names; refuse link traversal."""
    files: dict[str, dict[str, Any]] = {}
    directories: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if _is_link_or_junction(path):
            raise PhysicalArchiveError(f"拒绝归档符号链接或 Junction：{path}")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            stat = path.stat()
            files[relative] = {"bytes": stat.st_size, "sha256": _sha256(path)}
        else:
            raise PhysicalArchiveError(f"拒绝归档未知文件类型：{path}")
    return files, directories


def _manifest_digest(files: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _same_snapshot(
    left_files: dict[str, dict[str, Any]],
    left_dirs: set[str],
    right_files: dict[str, dict[str, Any]],
    right_dirs: set[str],
) -> bool:
    return left_files == right_files and left_dirs == right_dirs


def _validate_source(source: Path) -> Path:
    raw = source.expanduser()
    if not raw.is_absolute():
        raise PhysicalArchiveError(f"文章源目录必须是绝对路径：{source}")
    source = raw.resolve()
    if not source.is_dir():
        raise PhysicalArchiveError(f"文章源目录不存在：{source}")
    if source == Path(source.anchor):
        raise PhysicalArchiveError(f"拒绝把磁盘根目录当文章目录：{source}")
    if not _ARTICLE_NAME_RE.fullmatch(source.name):
        raise PhysicalArchiveError(
            f"文章目录名必须是“编号-选题”：{source.name!r}"
        )
    missing = [name for name in (".state.json", "article-meta.yaml") if not (source / name).is_file()]
    if missing:
        raise PhysicalArchiveError(
            "文章目录缺少身份文件，拒绝删除或搬运：" + "、".join(missing)
        )
    if _is_link_or_junction(source):
        raise PhysicalArchiveError(f"文章源目录不能是符号链接或 Junction：{source}")
    return source


def _validate_archive_root(source: Path, archive_root: Path) -> tuple[Path, Path]:
    raw = archive_root.expanduser()
    if not raw.is_absolute():
        raise PhysicalArchiveError(f"永久归档根目录必须是绝对路径：{archive_root}")
    root = raw.resolve()
    if not root.is_dir():
        raise PhysicalArchiveError(f"永久归档根目录不存在：{root}")
    if _is_link_or_junction(root):
        raise PhysicalArchiveError(f"永久归档根目录不能是符号链接或 Junction：{root}")
    target = root / source.name
    if source == target or _is_within(source, root) or _is_within(root, source):
        raise PhysicalArchiveError(
            f"源目录与永久归档根目录不能互相包含：source={source} archive_root={root}"
        )
    return root, target


def _acquire_lock(archive_root: Path, article_name: str) -> Path:
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", article_name)
    lock = archive_root / f".{safe_name}.physical-archive.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PhysicalArchiveError(
            f"同一篇文章已有实体归档任务或遗留锁：{lock}"
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"pid": os.getpid(), "article": article_name}, ensure_ascii=False))
    return lock


def _remove_owned_stage(stage: Path, archive_root: Path) -> None:
    if not stage.exists():
        return
    if stage.parent != archive_root or not stage.name.startswith(".physical-archive-staging-"):
        raise PhysicalArchiveError(f"拒绝清理不受本次任务所有的临时目录：{stage}")
    shutil.rmtree(stage)


def _write_receipt(target: Path, receipt: dict[str, Any]) -> None:
    final = target / RECEIPT_FILE
    temp = target / f".{RECEIPT_FILE}.{uuid.uuid4().hex}.tmp"
    temp.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(final)


def _verify_target_contains(
    target: Path, source_files: dict[str, dict[str, Any]], source_dirs: set[str]
) -> None:
    target_files, target_dirs = _snapshot(target)
    missing_dirs = sorted(source_dirs - target_dirs)
    missing_files = sorted(set(source_files) - set(target_files))
    changed_files = sorted(
        rel for rel in set(source_files) & set(target_files)
        if source_files[rel] != target_files[rel]
    )
    if missing_dirs or missing_files or changed_files:
        details = []
        if missing_dirs:
            details.append(f"缺目录 {missing_dirs[:5]}")
        if missing_files:
            details.append(f"缺文件 {missing_files[:5]}")
        if changed_files:
            details.append(f"哈希不一致 {changed_files[:5]}")
        raise PhysicalArchiveError("永久归档复验失败：" + "；".join(details))


def archive_article(
    source: Path | str,
    archive_root: Path | str,
    *,
    delete_source: bool = False,
) -> dict[str, Any]:
    """Archive one article and return a machine-readable receipt.

    Existing target files are never overwritten. Identical files are idempotent,
    target-only files are preserved, and any same-path hash/type conflict aborts
    before source deletion.
    """
    source = _validate_source(Path(source))
    archive_root, target = _validate_archive_root(source, Path(archive_root))
    lock = _acquire_lock(archive_root, source.name)
    stage = archive_root / f".physical-archive-staging-{source.name}-{uuid.uuid4().hex}"
    placed = "created"
    try:
        source_files, source_dirs = _snapshot(source)
        source_bytes = sum(record["bytes"] for record in source_files.values())

        target_files: dict[str, dict[str, Any]] = {}
        target_dirs: set[str] = set()
        if target.exists():
            if not target.is_dir() or _is_link_or_junction(target):
                raise PhysicalArchiveError(f"永久归档目标不是普通目录：{target}")
            target_files, target_dirs = _snapshot(target)
            type_conflicts = sorted(
                (set(source_files) & target_dirs) | (source_dirs & set(target_files))
            )
            hash_conflicts = sorted(
                rel for rel in set(source_files) & set(target_files)
                if source_files[rel] != target_files[rel]
            )
            if type_conflicts or hash_conflicts:
                parts = []
                if type_conflicts:
                    parts.append(f"文件/目录类型冲突 {type_conflicts[:8]}")
                if hash_conflicts:
                    parts.append(f"同路径哈希冲突 {hash_conflicts[:8]}")
                raise PhysicalArchiveError(
                    "目标已有不同内容，未覆盖、未删除源目录：" + "；".join(parts)
                )
            placed = "merged"

        shutil.copytree(source, stage, copy_function=shutil.copy2)
        staged_files, staged_dirs = _snapshot(stage)
        if not _same_snapshot(source_files, source_dirs, staged_files, staged_dirs):
            raise PhysicalArchiveError("临时副本与源目录的 SHA-256 快照不一致")
        current_files, current_dirs = _snapshot(source)
        if not _same_snapshot(source_files, source_dirs, current_files, current_dirs):
            raise PhysicalArchiveError("复制期间源目录发生变化；未放置归档、未删除源目录")

        if not target.exists():
            stage.replace(target)
        else:
            for relative in sorted(source_dirs, key=lambda value: (value.count("/"), value)):
                (target / relative).mkdir(exist_ok=True)
            for relative in sorted(set(source_files) - set(target_files)):
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                staged = stage / relative
                if destination.exists():
                    if not destination.is_file() or _sha256(destination) != source_files[relative]["sha256"]:
                        raise PhysicalArchiveError(f"放置期间目标发生冲突：{destination}")
                    continue
                staged.replace(destination)
            _remove_owned_stage(stage, archive_root)

        _verify_target_contains(target, source_files, source_dirs)
        receipt = {
            "schema_version": 1,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_from": str(source),
            "archive_root": str(archive_root),
            "target": str(target),
            "placement": placed,
            "source_file_count": len(source_files),
            "source_bytes": source_bytes,
            "source_manifest_sha256": _manifest_digest(source_files),
            "source_deleted": False,
        }
        _write_receipt(target, receipt)

        if delete_source:
            current_files, current_dirs = _snapshot(source)
            if not _same_snapshot(source_files, source_dirs, current_files, current_dirs):
                raise PhysicalArchiveError(
                    "删除前源目录发生变化；永久归档已保留，但源目录未删除"
                )
            _verify_target_contains(target, source_files, source_dirs)
            current_cwd = Path.cwd().resolve()
            if _is_within(current_cwd, source):
                os.chdir(archive_root)
            shutil.rmtree(source)
            if source.exists():
                raise PhysicalArchiveError(f"源目录删除后仍然存在：{source}")
            receipt["source_deleted"] = True
            _write_receipt(target, receipt)

        return receipt
    except OSError as exc:
        raise PhysicalArchiveError(f"实体归档文件系统错误：{exc}") from exc
    finally:
        try:
            if stage.exists():
                _remove_owned_stage(stage, archive_root)
        finally:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文章实体归档：复制、哈希复验、可选删除源目录")
    parser.add_argument("--dir", required=True, dest="source", help="文章源目录（绝对路径）")
    parser.add_argument("--archive-root", required=True, help="永久归档根目录（绝对路径）")
    parser.add_argument("--delete-source", action="store_true", help="复验通过后删除源目录")
    args = parser.parse_args(argv)
    try:
        receipt = archive_article(
            args.source,
            args.archive_root,
            delete_source=args.delete_source,
        )
    except PhysicalArchiveError as exc:
        print(f"❌ 实体归档失败：{exc}")
        return 2
    print(f"✅ 实体归档完成：{receipt['target']}")
    print(f"   文件：{receipt['source_file_count']}；字节：{receipt['source_bytes']}")
    print(f"   源目录：{'已删除' if receipt['source_deleted'] else '保留'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
