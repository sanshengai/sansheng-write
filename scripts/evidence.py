#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Artifact evidence helpers for the sansheng-write pipeline.

The pipeline records decisions in Markdown for humans and seals the exact bytes in
JSON for machines.  Human-readable notes remain useful, but they are never accepted
as proof that the currently published files are the files that were reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


VISUAL_RECEIPT_FILE = "_visual-receipt.json"
PUBLISH_RECEIPT_FILE = "_publish-receipt.json"
PUBLISH_READY_FILE = "_publish-ready.json"
CHECKPOINT_RECEIPT_FILE = "_checkpoint-receipts.json"
FINAL_PROMPT_PREFIX = "素材/prompts/final/"
VISUAL_PRODUCER = "sansheng-write.visual-planner"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm_relpath(value: str) -> str:
    return str(value or "").replace("\\", "/").removeprefix("./")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_digest(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _latest_by_output(cwd: Path, stage: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for rec in _read_jsonl(cwd / ".gen-log.jsonl"):
        if rec.get("stage") != stage:
            continue
        output = norm_relpath(rec.get("output", ""))
        if output:
            latest[output] = rec
    return latest


def _prompt_from_record(rec: dict) -> str:
    prompt = norm_relpath(rec.get("prompt", ""))
    if prompt:
        return prompt
    cmd = str(rec.get("cmd") or "")
    match = re.search(r"(?:素材[/\\]prompts[/\\][^\s\"']+\.md)", cmd)
    return norm_relpath(match.group(0)) if match else ""


def _producer(rec: dict) -> str:
    return str(rec.get("producer") or rec.get("tool") or "").strip()


def _renderer(rec: dict) -> str:
    value = str(rec.get("renderer") or "").strip()
    if value:
        return value
    cmd = str(rec.get("cmd") or "")
    if "gen_img" in cmd:
        return "gen_img"
    if "imagegen" in cmd:
        return "imagegen"
    return ""


def build_visual_manifest(
    cwd: Path, *, strict: bool = True, allow_postprocessed: bool = False
) -> tuple[dict, list[str]]:
    """Build a manifest for the final cover, infographic, and optional Hero bytes.

    `strict=True` is the v0.6 contract: the final exact-output log must use a
    canonical prompt under 素材/prompts/final and carry prompt/output hashes,
    producer, renderer, and model.
    """

    cwd = Path(cwd)
    errors: list[str] = []
    assets: list[dict] = []
    specs: list[tuple[str, str, set[str]]] = []
    cover = cwd / "素材" / "cover.png"
    if cover.exists():
        specs.append(("cover", "素材/cover.png", {VISUAL_PRODUCER}))
    else:
        errors.append("缺 素材/cover.png")

    infos = sorted((cwd / "素材").glob("infographic*.png"))
    if len(infos) < 4:
        errors.append(f"最终信息图仅 {len(infos)} 张（需 ≥4）")
    for path in infos:
        specs.append(
            ("infographic", norm_relpath(str(path.relative_to(cwd))),
             {VISUAL_PRODUCER, "baoyu-diagram"})
        )

    hero = cwd / "素材" / "hero.png"
    if hero.exists():
        specs.append((
            "hero",
            "素材/hero.png",
            {VISUAL_PRODUCER},
        ))

    logs = {
        "cover": _latest_by_output(cwd, "cover"),
        "infographic": _latest_by_output(cwd, "infographic"),
        "hero": _latest_by_output(cwd, "hero"),
    }
    banned_cover = re.compile(r"\b(?:largest|extra-black|ultra-black)\b", re.I)

    for stage, rel, allowed_producers in specs:
        output_path = cwd / Path(rel)
        rec = logs[stage].get(rel)
        if not rec:
            errors.append(f"{rel} 缺精确 output 的最终 gen-log 记录")
            continue

        producer = _producer(rec)
        renderer = _renderer(rec)
        model = str(rec.get("model") or "").strip()
        provenance_mode = str(rec.get("provenance_mode") or "rendered").strip()
        prompt_rel = _prompt_from_record(rec)
        prompt_path = cwd / Path(prompt_rel) if prompt_rel else None
        if producer not in allowed_producers:
            errors.append(
                f"{rel} producer={producer or '(空)'}；应为 {sorted(allowed_producers)}"
            )
        if not renderer:
            errors.append(f"{rel} 缺 renderer，无法区分 baoyu 语义生产者与像素后端")
        if strict and not model:
            errors.append(f"{rel} 缺 model")
        if provenance_mode not in {"rendered", "adopted-postprocessed"}:
            errors.append(f"{rel} provenance_mode 非法：{provenance_mode or '(空)'}")
        if not prompt_rel:
            errors.append(f"{rel} 最终日志缺 prompt 路径")
            continue
        if strict and not prompt_rel.startswith(FINAL_PROMPT_PREFIX):
            errors.append(
                f"{rel} 最终 prompt 必须位于 {FINAL_PROMPT_PREFIX}，当前为 {prompt_rel}"
            )
        if not prompt_path or not prompt_path.exists():
            errors.append(f"{rel} prompt 不存在：{prompt_rel}")
            continue

        prompt_sha = sha256_file(prompt_path)
        output_sha = sha256_file(output_path)
        logged_prompt_sha = str(rec.get("prompt_sha256") or "")
        logged_output_sha = str(rec.get("output_sha256") or "")
        if strict and logged_prompt_sha != prompt_sha:
            errors.append(f"{rel} prompt_sha256 与当前 prompt 字节不一致")
        if (strict and logged_output_sha and logged_output_sha != output_sha
                and not allow_postprocessed):
            errors.append(f"{rel} output_sha256 与渲染后字节不一致（是否未登记后处理）")
        if strict and not logged_output_sha:
            errors.append(f"{rel} 最终日志缺 output_sha256")

        prompt_text = prompt_path.read_text(encoding="utf-8")
        if stage == "cover":
            hits = sorted({m.group(0).lower() for m in banned_cover.finditer(prompt_text)})
            if hits:
                errors.append(f"封面 canonical prompt 含禁词：{hits}")

        assets.append({
            "stage": stage,
            "path": rel,
            "sha256": output_sha,
            "bytes": output_path.stat().st_size,
            "prompt": prompt_rel,
            "prompt_sha256": prompt_sha,
            "producer": producer,
            "renderer": renderer,
            "renderer_revision": str(rec.get("renderer_revision") or ""),
            "provider": str(rec.get("provider") or ""),
            "model": model,
            "provenance_mode": provenance_mode,
            "generation_record_id": str(rec.get("record_id") or ""),
            "visual_profile": str(rec.get("visual_profile") or ""),
            "visual_profile_sha256": str(rec.get("visual_profile_sha256") or ""),
            "host_agent": str(rec.get("host_agent") or ""),
            "orchestrator_skill": str(rec.get("orchestrator_skill") or ""),
            "extend_sha256": str(rec.get("extend_sha256") or ""),
        })

    meta_subset: dict = {}
    meta_path = cwd / "article-meta.yaml"
    if meta_path.exists():
        try:
            import yaml
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            meta_subset = {
                "cover_style": meta.get("cover_style") or "montage-evidence",
                "infographic_subject": meta.get("infographic_subject") or "",
                "infographic_style": meta.get("infographic_style") or "",
                "visual_profile": meta.get("visual_profile") or "",
            }
        except Exception as exc:  # pragma: no cover - pipeline reports parse detail
            errors.append(f"article-meta.yaml 解析失败：{exc}")

    manifest = {"schema_version": 1, "meta": meta_subset, "assets": assets}
    return manifest, errors


def seal_visual_receipt(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    qa = cwd / "_visual-qa.json"
    if not qa.exists():
        return None, ["缺 _visual-qa.json，先运行独立结构化视觉 QA"]
    try:
        qa_payload = json.loads(qa.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"_visual-qa.json 解析失败：{exc}"]
    try:
        from .visual_qa import validate_qa_result
    except ImportError:  # pragma: no cover - direct script execution
        from visual_qa import validate_qa_result
    qa_errors = validate_qa_result(cwd, qa_payload)
    if qa_errors:
        return None, qa_errors
    # add_logo/compression 会合法改变渲染器输出；从 seal 开始由 receipt 接管最终字节。
    manifest, errors = build_visual_manifest(
        cwd, strict=True, allow_postprocessed=True
    )
    if errors:
        return None, errors
    receipt = {
        "schema_version": 1,
        "sealed_at": now_iso(),
        "manifest": manifest,
        "manifest_digest": stable_digest(manifest),
        "qa_path": "_visual-qa.json",
        "qa_sha256": sha256_file(qa),
    }
    (cwd / VISUAL_RECEIPT_FILE).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt, []


def verify_visual_receipt(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    path = cwd / VISUAL_RECEIPT_FILE
    if not path.exists():
        return None, [f"缺 {VISUAL_RECEIPT_FILE}：logo/压缩后必须执行 pipeline.py seal visual"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"{VISUAL_RECEIPT_FILE} 解析失败：{exc}"]
    manifest, errors = build_visual_manifest(
        cwd, strict=True, allow_postprocessed=True
    )
    current_digest = stable_digest(manifest)
    if receipt.get("manifest_digest") != current_digest:
        errors.append("视觉资产字节/prompt/生成记录已变化，旧 visual receipt 失效")
    qa = cwd / str(receipt.get("qa_path") or "_visual-qa.json")
    if not qa.exists() or receipt.get("qa_sha256") != sha256_file(qa):
        errors.append("_visual-qa.json 已变化或缺失，需重新运行视觉 QA 并 seal visual")
    elif qa.exists():
        try:
            qa_payload = json.loads(qa.read_text(encoding="utf-8"))
            try:
                from .visual_qa import validate_qa_result
            except ImportError:  # pragma: no cover - direct script execution
                from visual_qa import validate_qa_result
            errors.extend(validate_qa_result(cwd, qa_payload))
        except Exception as exc:
            errors.append(f"_visual-qa.json 解析失败：{exc}")
    return receipt, errors


def build_publish_manifest(cwd: Path) -> tuple[dict, list[str]]:
    cwd = Path(cwd)
    receipt, errors = verify_visual_receipt(cwd)
    files: list[dict] = []
    for rel in ("定稿.html", "素材/hero.png"):
        path = cwd / Path(rel)
        if not path.exists():
            errors.append(f"缺 {rel}")
            continue
        files.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    payload = {
        "schema_version": 1,
        "visual_manifest_digest": (receipt or {}).get("manifest_digest", ""),
        "files": files,
    }
    return payload, errors


def write_publish_ready(cwd: Path) -> tuple[dict | None, list[str]]:
    """Seal the exact local package *before* calling the external publisher."""
    cwd = Path(cwd)
    manifest, errors = build_publish_manifest(cwd)
    if errors:
        return None, errors
    receipt = {
        "schema_version": 1,
        "sealed_at": now_iso(),
        "manifest": manifest,
        "manifest_digest": stable_digest(manifest),
    }
    (cwd / PUBLISH_READY_FILE).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt, []


def verify_publish_ready(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    path = cwd / PUBLISH_READY_FILE
    if not path.exists():
        return None, [
            f"缺 {PUBLISH_READY_FILE}；调用微信前必须先执行 pipeline.py verify publish --pre"
        ]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"{PUBLISH_READY_FILE} 解析失败：{exc}"]
    manifest, errors = build_publish_manifest(cwd)
    if receipt.get("manifest_digest") != stable_digest(manifest):
        errors.append("publish-ready 后本地产物已变化；必须重新跑 verify publish --pre")
    return receipt, errors


def write_publish_receipt(cwd: Path, draft_media_id: str) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    ready, ready_errors = verify_publish_ready(cwd)
    if ready_errors:
        return None, ready_errors
    manifest, errors = build_publish_manifest(cwd)
    if errors:
        return None, errors
    receipt = {
        "schema_version": 1,
        "sealed_at": now_iso(),
        "draft_media_id": draft_media_id,
        "publish_ready_digest": (ready or {}).get("manifest_digest", ""),
        "manifest": manifest,
        "manifest_digest": stable_digest(manifest),
    }
    (cwd / PUBLISH_RECEIPT_FILE).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt, []


def verify_publish_receipt(cwd: Path, draft_media_id: str) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    path = cwd / PUBLISH_RECEIPT_FILE
    if not path.exists():
        return None, [f"缺 {PUBLISH_RECEIPT_FILE}，draft_media_id 未绑定本地发布产物"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"{PUBLISH_RECEIPT_FILE} 解析失败：{exc}"]
    manifest, errors = build_publish_manifest(cwd)
    if receipt.get("draft_media_id") != draft_media_id:
        errors.append("publish receipt 的 draft_media_id 与 state 不一致")
    if receipt.get("manifest_digest") != stable_digest(manifest):
        errors.append("HTML/hero/视觉资产已在推草稿后变化，publish receipt 失效，必须重推")
    if int(receipt.get("schema_version") or 1) >= 2:
        if receipt.get("scope") != "wechat-draft" or receipt.get("formal_publish") is not False:
            errors.append("publish receipt 越权：只允许 wechat-draft / formal_publish=false")
        if receipt.get("remote_verified") is not True:
            errors.append("publish receipt 缺官方 draft/get 读回确认")
        checks = (receipt.get("remote_readback") or {}).get("checks") or {}
        if not checks or not all(value is True for value in checks.values()):
            errors.append("publish receipt 的远端字段检查未全部通过")
    return receipt, errors


def _semantic_draft_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"(?ms)^<!-- AUDIO-CARD-START -->.*?^<!-- AUDIO-CARD-END -->\s*",
        "",
        text,
    )
    text = re.sub(r"(?m)^!\[[^\]]*\]\(素材/[^)]+\)\s*$", "", text)
    text = re.sub(r"(?m)^coverImage:\s*.*$", "coverImage: <generated>", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _approval_anchor(cwd: Path, gate: str) -> tuple[dict, list[str]]:
    names = {
        "blueprint": "_blueprint-approval.md",
        "draft": "_draft-approval.md",
    }
    name = names.get(gate, "")
    path = Path(cwd) / name if name else None
    if not path or not path.exists():
        return {}, [f"缺 {name or gate + ' approval anchor'}"]
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?:不通过|未通过|拒绝|驳回|不同意|尚未确认|待确认)", text):
        decision = "rejected"
    elif re.search(r"(?m)^(?:[-*]\s*)?(?:审批结论|作者免检授权)\s*[：:]\s*(?:免检|跳过)", text):
        decision = "waived"
    elif re.search(r"(?m)^(?:[-*]\s*)?(?:审批结论|大纲)\s*[：:]\s*通过(?:[，,。；;\s]|$)", text):
        decision = "approved"
    else:
        decision = "unknown"
    return {
        "path": name,
        "sha256": sha256_file(path),
        "decision": decision,
    }, []


def checkpoint_artifact(
    cwd: Path, gate: str, source_mode: str = ""
) -> tuple[dict, list[str]]:
    cwd = Path(cwd)
    errors: list[str] = []
    if gate == "draft":
        draft = cwd / "定稿.md"
        if not draft.exists():
            return {}, ["缺 定稿.md"]
        semantic = _semantic_draft_text(draft)
        supporting = []
        for rel in ("_fact-check.md", "_stutter-list.md", "_draft-qc.md"):
            path = cwd / rel
            if not path.exists() and source_mode != "author-provided-final":
                errors.append(f"draft 审批前缺 {rel}")
            elif path.exists():
                supporting.append({"path": rel, "sha256": sha256_file(path)})
        anchor, anchor_errors = _approval_anchor(cwd, gate)
        errors.extend(anchor_errors)
        return {
            "gate": gate,
            "semantic_sha256": hashlib.sha256(semantic.encode("utf-8")).hexdigest(),
            "supporting_files": supporting,
            "approval_anchor": anchor,
        }, errors
    if gate == "blueprint":
        outline = cwd / "大纲.md"
        meta_path = cwd / "article-meta.yaml"
        if not outline.exists():
            errors.append("缺 大纲.md")
        if not meta_path.exists():
            errors.append("缺 article-meta.yaml")
        meta_subset = {}
        if meta_path.exists():
            try:
                import yaml
                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
                meta_subset = {
                    "title": meta.get("title") or "",
                    "cover_style": meta.get("cover_style") or "montage-evidence",
                    "infographic_subject": meta.get("infographic_subject") or "",
                    "infographic_style": meta.get("infographic_style") or "",
                    "visual_profile": meta.get("visual_profile") or "",
                }
            except Exception as exc:
                errors.append(f"article-meta.yaml 解析失败：{exc}")
        anchor, anchor_errors = _approval_anchor(cwd, gate)
        errors.extend(anchor_errors)
        return {
            "gate": gate,
            "outline_sha256": sha256_file(outline) if outline.exists() else "",
            "meta": meta_subset,
            "approval_anchor": anchor,
        }, errors
    return {}, [f"未知 checkpoint gate：{gate}"]


def write_checkpoint_receipt(cwd: Path, gate: str, source_mode: str,
                             note: str = "") -> tuple[dict | None, list[str]]:
    cwd = Path(cwd)
    artifact, errors = checkpoint_artifact(cwd, gate, source_mode=source_mode)
    if errors:
        return None, errors
    decision = artifact.get("approval_anchor", {}).get("decision")
    expected = "waived" if source_mode == "checkpoint-waived" else "approved"
    if decision != expected:
        return None, [
            f"{gate} 审批结论={decision or '(空)'}；source_mode={source_mode} 要求 {expected}"
        ]
    path = cwd / CHECKPOINT_RECEIPT_FILE
    payload = {"schema_version": 1, "checkpoints": {}}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                payload.update(old)
                payload.setdefault("checkpoints", {})
        except Exception:
            pass
    rec = {
        "approved_at": now_iso(),
        "source_mode": source_mode,
        "decision": decision,
        "note": note,
        "artifact": artifact,
        "artifact_digest": stable_digest(artifact),
    }
    payload["checkpoints"][gate] = rec
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec, []


def verify_checkpoint_receipt(cwd: Path, gate: str) -> list[str]:
    cwd = Path(cwd)
    path = cwd / CHECKPOINT_RECEIPT_FILE
    if not path.exists():
        return [f"缺 {CHECKPOINT_RECEIPT_FILE}；作者确认后执行 pipeline.py approve {gate}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rec = payload.get("checkpoints", {}).get(gate)
    except Exception as exc:
        return [f"{CHECKPOINT_RECEIPT_FILE} 解析失败：{exc}"]
    if not isinstance(rec, dict):
        return [f"{CHECKPOINT_RECEIPT_FILE} 缺 {gate} 记录"]
    artifact, errors = checkpoint_artifact(
        cwd, gate, source_mode=str(rec.get("source_mode") or "")
    )
    if rec.get("artifact_digest") != stable_digest(artifact):
        errors.append(f"{gate} 审批对象已变化，旧审批失效，需重新 approve")
    if rec.get("source_mode") not in {
        "new-draft", "author-provided-final", "checkpoint-waived"
    }:
        errors.append(f"{gate} receipt 缺合法 source_mode")
    expected = "waived" if rec.get("source_mode") == "checkpoint-waived" else "approved"
    current_decision = artifact.get("approval_anchor", {}).get("decision")
    if rec.get("decision") != expected or current_decision != expected:
        errors.append(
            f"{gate} 当前/封存审批结论不是 {expected}（当前={current_decision}，封存={rec.get('decision')}）"
        )
    return errors


def files_digest(cwd: Path, relpaths: Iterable[str]) -> str:
    rows = []
    for rel in sorted(set(norm_relpath(p) for p in relpaths)):
        path = Path(cwd) / Path(rel)
        if path.exists() and path.is_file():
            rows.append({"path": rel, "sha256": sha256_file(path)})
    return stable_digest(rows)
