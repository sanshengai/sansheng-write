"""Assemble only a complete accepted group, preserving exact editorial source."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable
    from .stylebook_group import verify_group
    from .stylebook_source import current_source, assembled_text
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable
    from stylebook_group import verify_group
    from stylebook_source import current_source, assembled_text


def inputs(cwd: Path) -> tuple[dict, str, dict]:
    cwd = Path(cwd).resolve()
    group = verify_group(cwd)
    plan = json.loads((cwd / "visual-plan.json").read_text())
    batch = json.loads((cwd / "素材/render-batch.json").read_text())
    source = current_source(cwd, batch, plan)
    text = assembled_text(source.read_bytes().decode("utf-8"), plan)
    assets = {image_id: {"source": item["image"], "sha256": item["image_sha256"],
                        "output": "素材/cover.png" if image_id == "cover" else f"素材/infographic-{image_id}.png"}
              for image_id, item in group["assets"].items()}
    identity = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                "status": "assembled_pending_release_review", "selection_id": group["selection_id"],
                "selection_sha256": sha(cwd / "素材/stylebook-selection.json"),
                "source": str(source.relative_to(cwd)), "source_sha256": sha(source),
                "author_content_sha256": batch["source"]["author_content_sha256"],
                "assembled_sha256": digest_bytes(text.encode("utf-8")), "assets": assets,
                "assembly_adapter_sha256": sha(Path(__file__).resolve())}
    return identity, text, group


def digest_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def assemble(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        identity, text, _ = inputs(cwd)
        before = (cwd / "定稿.md").read_bytes()
        with tempfile.TemporaryDirectory(prefix="stylebook-assembly-", dir=cwd / "素材") as scratch:
            scratch = Path(scratch)
            staged = []
            for image_id, asset in identity["assets"].items():
                data = (cwd / asset["source"]).read_bytes()
                if digest_bytes(data) != asset["sha256"]:
                    raise ValueError("装配期间最终图片已改变")
                stage = scratch / f"{image_id}.png"
                stage.write_bytes(data)
                staged.append((stage, cwd / asset["output"]))
            draft = scratch / "article.md"
            draft.write_bytes(text.encode("utf-8"))
            current, _, _ = inputs(cwd)
            if current != identity or (cwd / "定稿.md").read_bytes() != before:
                raise ValueError("装配期间原文、选图或验收已改变")
            for stage, target in staged:
                os.replace(stage, target)
            os.replace(draft, cwd / "定稿.md")
        assembly_id = digest(identity)
        snapshot = cwd / "素材/stylebook-assemblies" / f"{assembly_id}.json"
        _immutable(snapshot, identity)
        record = {**identity, "assembly_id": assembly_id, "assembly_path": str(snapshot.relative_to(cwd))}
        (cwd / "素材/stylebook-assembly.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        verify_assembly(cwd)
        return {**record, "changed": before != text.encode("utf-8"),
                "image_count": len(identity["assets"]) - 1}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f"画风库文章装配失败：{exc}"]


def verify_assembly(cwd: Path) -> dict:
    cwd = Path(cwd).resolve()
    record = json.loads((cwd / "素材/stylebook-assembly.json").read_text())
    identity = {key: value for key, value in record.items() if key not in ("assembly_id", "assembly_path")}
    assembly_id = digest(identity)
    snapshot = cwd / "素材/stylebook-assemblies" / f"{assembly_id}.json"
    if record.get("assembly_id") != assembly_id or (cwd / record["assembly_path"]).resolve() != snapshot:
        raise ValueError("文章装配凭证不属于本篇不可变快照")
    if json.loads(snapshot.read_text()) != identity:
        raise ValueError("文章装配快照已改变")
    current, text, _ = inputs(cwd)
    if current != identity:
        raise ValueError("装配依据、方法或完整验收已改变")
    if (cwd / "定稿.md").read_bytes() != text.encode("utf-8"):
        raise ValueError("当前文章不等于本次完整选图的确切装配结果")
    for item in identity["assets"].values():
        if sha(cwd / item["output"]) != item["sha256"]:
            raise ValueError("正文或封面正式图片已改变，装配凭证失效")
    return record
