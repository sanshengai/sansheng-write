"""Known candidate objections survive a model's passing QA report."""
from __future__ import annotations

import json
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, _immutable, digest, sha
    from .stylebook_review import production_inputs, verify_candidate_review
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, _immutable, digest, sha
    from stylebook_review import production_inputs, verify_candidate_review


def reject_candidate(cwd: Path, production_path: Path, reason: str) -> dict:
    """Record an observed problem; it is host-attested, not an independent review."""
    cwd = Path(cwd).resolve()
    reason = reason.strip()
    if not reason:
        raise ValueError("候选异议必须说明实际观察到的问题")
    record, _, _ = production_inputs(cwd, production_path)
    objection = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                 "status": "rejected_candidate", "production_id": record["production_id"], "id": record["id"],
                 "production_path": str(Path(production_path).resolve().relative_to(cwd)),
                 "production_sha256": sha(Path(production_path)), "final_sha256": record["outputs"]["main"]["sha256"],
                 "source_strength": "host_attested_observation", "reason": reason}
    path = cwd / "素材/stylebook-objections" / record["production_id"] / f"{digest(objection)}.json"
    _immutable(path, objection)
    return {**objection, "path": str(path)}


def verify_acceptable_candidate(cwd: Path, report_path: Path) -> dict:
    """Candidate-only prerequisite; does not certify a group, plan or release."""
    cwd = Path(cwd).resolve()
    report = verify_candidate_review(cwd, report_path)
    objections = cwd / "素材/stylebook-objections" / report["production_id"]
    for path in sorted(objections.glob("*.json")):
        objection = json.loads(path.read_text())
        if path.stem != digest(objection) or objection.get("production_id") != report["production_id"]:
            raise ValueError("已记录的候选异议损坏，不能忽略后继续交付")
        raise ValueError("该最终候选有未解决的实际异议，模型绿灯不能覆盖：" + objection["reason"])
    return report
