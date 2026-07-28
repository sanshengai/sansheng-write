#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adopt an author-approved final draft into the deterministic release runtime."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from assemble_release import author_content_sha256
from evidence import sha256_file, stable_digest, write_checkpoint_receipt
from works_registry import CATEGORY_CODES, OUTWARD_CATEGORIES, TAG_VOCAB


RELEASE_JOB_FILE = "_release-job.json"
RELEASE_SCOPE = "wechat-draft"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _relative_file(cwd: Path, value: Path, label: str) -> tuple[Path | None, list[str]]:
    path = value if value.is_absolute() else cwd / value
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None, [f"{label}不存在：{path}"]
    if not resolved.is_file():
        return None, [f"{label}不是文件：{resolved}"]
    try:
        resolved.relative_to(cwd.resolve())
    except ValueError:
        return None, [f"{label}必须位于文章目录内：{resolved}"]
    return resolved, []


def _frontmatter(text: str) -> dict:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|$)", text, re.S)
    if not match:
        return {}
    try:
        value = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _validate_final_and_meta(final_path: Path, meta_path: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    draft_text = final_path.read_text(encoding="utf-8")
    if len(draft_text) < 1500:
        errors.append("定稿.md 内容过短（< 1500 字）")
    try:
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {}, [f"article-meta.yaml 解析失败：{exc}"]
    if not isinstance(meta, dict):
        return {}, ["article-meta.yaml 顶层必须是对象"]

    draft_meta = _frontmatter(draft_text)
    h1_match = re.search(r"(?m)^#\s+(.+?)\s*$", draft_text)
    draft_title = str(draft_meta.get("title") or (h1_match.group(1) if h1_match else "")).strip()
    title = str(meta.get("title") or "").strip()
    if not title:
        errors.append("article-meta.yaml 缺 title")
    elif draft_title and draft_title != title:
        errors.append(
            f"定稿标题与 article-meta.yaml 标题不一致：{draft_title!r} != {title!r}"
        )

    category = str(meta.get("category") or "")
    if category not in CATEGORY_CODES:
        errors.append(f"category 缺失或非法（需 {sorted(CATEGORY_CODES)}）")
    outward = str(meta.get("outward_category") or "")
    if outward not in OUTWARD_CATEGORIES:
        errors.append(
            f"outward_category 缺失或非法（需 {sorted(OUTWARD_CATEGORIES)}）"
        )
    elif title and not title.startswith(f"{OUTWARD_CATEGORIES[outward]} | "):
        errors.append(
            f"标题必须带对外分类前缀 {OUTWARD_CATEGORIES[outward]} | "
        )
    tags = meta.get("tags") or []
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        errors.append("tags 必须是字符串列表")
    else:
        bad = [tag for tag in tags if tag not in TAG_VOCAB]
        if bad:
            errors.append(f"tags 含受控词表外标签：{bad}")
    if not str(meta.get("digest") or "").strip():
        errors.append("article-meta.yaml 缺 digest")

    expected_style = {
        "ai-product": "claymation",
        "phenomenon": "morandi-journal",
    }
    subject = str(meta.get("infographic_subject") or "")
    style = str(meta.get("infographic_style") or "")
    if subject not in expected_style:
        errors.append("infographic_subject 必须为 ai-product 或 phenomenon")
    elif style != expected_style[subject]:
        errors.append(
            f"infographic_subject={subject} 必须使用 {expected_style[subject]}"
        )
    if style == "claymation" and meta.get("visual_profile") != "warm-light-clay":
        errors.append("claymation 必须显式 visual_profile: warm-light-clay")
    if style == "morandi-journal" and meta.get("visual_profile"):
        errors.append("morandi-journal 不得绑定 claymation visual_profile")
    cover_style = str(meta.get("cover_style") or "montage-evidence")
    if cover_style != "montage-evidence":
        errors.append("release-from-final 当前只接受 cover_style: montage-evidence")
    return meta, errors


def _new_state(cwd: Path, stages: list[str]) -> dict:
    now = _now_iso()
    return {
        "schema_version": 2,
        "topic_id": cwd.name,
        "topic_dir": str(cwd),
        "run_id": str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        "stages": {stage: {"status": "pending"} for stage in stages},
        "notes": [],
        "orchestrator": "on",
        "state_writer": "orchestrator",
    }


def adopt_final(
    cwd: Path,
    final_path: Path = Path("定稿.md"),
    meta_path: Path = Path("article-meta.yaml"),
) -> tuple[dict | None, list[str]]:
    """Create a release-only state and bind it to the exact approved bytes."""

    cwd = Path(cwd).resolve()
    final, errors = _relative_file(cwd, Path(final_path), "定稿")
    meta_file, meta_errors = _relative_file(cwd, Path(meta_path), "article-meta")
    errors.extend(meta_errors)
    if errors or final is None or meta_file is None:
        return None, errors
    meta, validate_errors = _validate_final_and_meta(final, meta_file)
    if validate_errors:
        return None, validate_errors

    # Imported lazily to avoid a module import cycle: pipeline imports this module
    # only from its command handlers.
    import pipeline

    state_path = cwd / pipeline.STATE_FILE
    state = (
        pipeline.load_state(cwd)
        if state_path.exists()
        else _new_state(cwd, pipeline.STAGE_ORDER)
    )
    state["mode"] = "release-from-final"
    state["stages"] = {
        stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER
    }
    state["stages"]["outline"] = {
        "status": "adopted",
        "source_mode": "author-provided-final",
    }
    state["stages"]["writing"] = {
        "status": "done",
        "source_mode": "author-provided-final",
        "title_final": str(meta.get("title") or ""),
    }

    approval = cwd / "_draft-approval.md"
    approval.write_text(
        "# 作者定稿接管\n\n"
        "审批结论：通过\n"
        "来源：作者提供定稿\n"
        f"定稿 SHA-256：{sha256_file(final)}\n"
        f"接管时间：{_now_iso()}\n",
        encoding="utf-8",
    )
    checkpoint, checkpoint_errors = write_checkpoint_receipt(
        cwd,
        "draft",
        "author-provided-final",
        "作者确认的定稿直接接入发布后端；不伪造写作期审查产物。",
    )
    if checkpoint_errors:
        approval.unlink(missing_ok=True)
        return None, checkpoint_errors

    pipeline.save_state(cwd, state)
    final_rel = final.relative_to(cwd).as_posix()
    meta_rel = meta_file.relative_to(cwd).as_posix()
    job = {
        "schema_version": 2,
        "job_id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "scope": RELEASE_SCOPE,
        "article_dir": str(cwd),
        "final_path": final_rel,
        "final_sha256": sha256_file(final),
        "author_content_sha256": author_content_sha256(
            final.read_text(encoding="utf-8")
        ),
        "meta_path": meta_rel,
        "meta_sha256": sha256_file(meta_file),
        "checkpoint_digest": checkpoint["artifact_digest"],
        "state_run_id": state["run_id"],
        "required_terminal_state": "wechat-draft-verified",
        "formal_publish": False,
    }
    job["job_digest"] = stable_digest(
        {key: value for key, value in job.items() if key != "job_digest"}
    )
    (cwd / RELEASE_JOB_FILE).write_text(
        json.dumps(job, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return job, []


def validate_release_job(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    path = cwd / RELEASE_JOB_FILE
    if not path.exists():
        return None, [
            f"缺 {RELEASE_JOB_FILE}；作者确认定稿后先执行 pipeline.py adopt-final"
        ]
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"{RELEASE_JOB_FILE} 解析失败：{exc}"]
    errors: list[str] = []
    if job.get("scope") != RELEASE_SCOPE or job.get("formal_publish") is not False:
        errors.append("release job 范围不是安全的 wechat-draft")
    expected_digest = stable_digest(
        {key: value for key, value in job.items() if key != "job_digest"}
    )
    if job.get("job_digest") != expected_digest:
        errors.append("release job 自身摘要不一致")
    if Path(str(job.get("article_dir") or "")).resolve() != cwd:
        errors.append("release job 的 article_dir 与当前目录不一致")
    for label, path_key, hash_key in (
        ("定稿", "final_path", "final_sha256"),
        ("article-meta", "meta_path", "meta_sha256"),
    ):
        rel = str(job.get(path_key) or "")
        target = cwd / Path(rel)
        if not rel or not target.exists():
            errors.append(f"{label}文件缺失：{rel or '(空)'}")
        elif sha256_file(target) != job.get(hash_key):
            if label != "定稿":
                errors.append(
                    f"{label}已变化，旧 release job 失效；需重新 adopt-final"
                )
                continue
            expected_author_hash = str(job.get("author_content_sha256") or "")
            actual_author_hash = author_content_sha256(
                target.read_text(encoding="utf-8")
            )
            if not expected_author_hash or actual_author_hash != expected_author_hash:
                errors.append(
                    "定稿作者正文已变化，旧 release job 失效；需重新 adopt-final"
                )
    try:
        import pipeline

        state = pipeline.load_state(cwd)
        if state.get("run_id") != job.get("state_run_id"):
            errors.append("release job 与当前 state.run_id 不一致")
    except SystemExit:
        errors.append("缺 .state.json，release job 无对应状态机")
    return job, errors


def rebind_release_job(cwd: Path) -> tuple[dict | None, bool, list[str]]:
    """Refresh byte hashes after registered machine assembly only.

    `author_content_sha256` is the authority boundary.  A visual/audio assembly can
    change file bytes while leaving author prose intact; rebind records that honestly
    without resetting release stages or manufacturing a new author approval.
    """
    cwd = Path(cwd).resolve()
    job, errors = validate_release_job(cwd)
    if errors or job is None:
        return None, False, errors
    final = cwd / Path(str(job["final_path"]))
    meta = cwd / Path(str(job["meta_path"]))
    author_hash = author_content_sha256(final.read_text(encoding="utf-8"))
    if author_hash != str(job.get("author_content_sha256") or ""):
        return None, False, ["定稿作者正文已变化，拒绝用机器重绑定掩盖；请重新 adopt-final"]
    next_final_sha = sha256_file(final)
    next_meta_sha = sha256_file(meta)
    if next_meta_sha != str(job.get("meta_sha256") or ""):
        return None, False, ["article-meta.yaml 已变化，机器重绑定不接受内容配置漂移；请重新 adopt-final"]
    if next_final_sha == str(job.get("final_sha256") or ""):
        return job, False, []
    rebound = dict(job)
    rebound["final_sha256"] = next_final_sha
    rebound["rebound_at"] = _now_iso()
    rebound["job_digest"] = stable_digest(
        {key: value for key, value in rebound.items() if key != "job_digest"}
    )
    (cwd / RELEASE_JOB_FILE).write_text(
        json.dumps(rebound, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return rebound, True, []
