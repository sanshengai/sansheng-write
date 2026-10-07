"""Select a complete, current article group; no release or style admission claim."""
from __future__ import annotations

import json
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, _immutable, digest, generation_requests, sha
    from .stylebook_plan_review import verify_plan_review
    from .stylebook_acceptance import verify_acceptable_candidate
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, _immutable, digest, generation_requests, sha
    from stylebook_plan_review import verify_plan_review
    from stylebook_acceptance import verify_acceptable_candidate


def selection_inputs(cwd: Path, plan_report: Path, reports: dict[str, Path]) -> dict:
    cwd = Path(cwd).resolve()
    reviewed = verify_plan_review(cwd, plan_report)
    pending, errors = generation_requests(cwd)
    if errors:
        raise ValueError("；".join(errors))
    expected_ids = {task["id"] for task in pending["requests"]}
    if not isinstance(reports, dict) or set(reports) != expected_ids:
        raise ValueError("整组选图必须恰好包含封面及本篇全部正文图片 ID，不得缺项或混入其他图")
    plan = json.loads((cwd / "visual-plan.json").read_text())
    assets = {}
    for image_id, report_path in reports.items():
        report_path = Path(report_path).resolve()
        report = verify_acceptable_candidate(cwd, report_path)
        if report["id"] != image_id:
            raise ValueError("图片 ID 与所选验收报告不一致")
        production = cwd / report["production_path"]
        made = json.loads(production.read_text())
        if made["request_id"] != pending["request_id"]:
            raise ValueError("整组不能混用不同编译请求的成品")
        main = cwd / made["files"]["main"]
        assets[image_id] = {"qa_report": str(report_path.relative_to(cwd)), "qa_report_sha256": sha(report_path),
                            "production": report["production_path"], "production_sha256": sha(production),
                            "production_id": made["production_id"], "image": str(main.relative_to(cwd)),
                            "image_sha256": sha(main), "style": made["manifest"]["style"],
                            "palette": made["manifest"].get("palette")}
    return {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
            "status": "group_selected_pending_assembly", "request_id": pending["request_id"],
            "group": plan["group"], "plan_review": str(Path(plan_report).resolve().relative_to(cwd)),
            "plan_review_sha256": sha(Path(plan_report)), "actual_plan_reviewer": reviewed["actual_reviewer"],
            "assets": assets, "selection_adapter_sha256": sha(Path(__file__))}


def select_group(cwd: Path, plan_report: Path, reports: dict[str, Path]) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        identity = selection_inputs(cwd, plan_report, reports)
        selection_id = digest(identity)
        snapshot = cwd / "素材/stylebook-selections" / f"{selection_id}.json"
        _immutable(snapshot, identity)
        record = {**identity, "selection_id": selection_id, "selection_path": str(snapshot.relative_to(cwd))}
        (cwd / "素材/stylebook-selection.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        return record, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f"画风库整组选图失败：{exc}"]


def verify_group(cwd: Path) -> dict:
    cwd = Path(cwd).resolve()
    record = json.loads((cwd / "素材/stylebook-selection.json").read_text())
    identity = {key: value for key, value in record.items() if key not in ("selection_id", "selection_path")}
    expected_path = cwd / "素材/stylebook-selections" / f"{digest(identity)}.json"
    if record.get("selection_id") != digest(identity) or cwd / record["selection_path"] != expected_path:
        raise ValueError("当前整组选图凭证改变或不属于不可变快照")
    if json.loads(expected_path.read_text()) != identity:
        raise ValueError("整组选图快照已改变")
    current = selection_inputs(cwd, cwd / identity["plan_review"],
                               {key: cwd / asset["qa_report"] for key, asset in identity["assets"].items()})
    if current != identity:
        raise ValueError("整组原文、计划、成品、验收或实际问题状态已改变")
    return record
