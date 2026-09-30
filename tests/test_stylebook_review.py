"""QA lifecycle checks with a fake independent call; no fake user/admission evidence."""
import importlib
import json
from pathlib import Path

import pytest

from scripts.stylebook_workflow import collect_host_result, produce_candidate, digest
from scripts.stylebook_review import review_candidate, verify_candidate_review
from test_stylebook_workflow import host_result_fixture


def candidate(tmp_path, monkeypatch):
    path, _, _ = host_result_fixture(tmp_path, monkeypatch)
    collected, errors = collect_host_result(tmp_path, path)
    assert not errors
    made, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert not errors
    return made


def mocked_reviewer(monkeypatch, *, failing=False, change=None):
    reviewer = importlib.import_module("stylebook.qa.reviewer")
    monkeypatch.setattr(reviewer, "source", lambda: "ark_agent_plan")

    def review(image, contract, expected, mode):
        qa = importlib.import_module("stylebook.qa")
        must, bans = qa.active_items(contract, mode)
        result = {"must_see": [{"item": item, "ok": True, "why": "synthetic test answer"} for item in must],
                  "must_not_see": [{"item": item, "present": False, "why": "synthetic test answer"} for item in bans],
                  "transcribed_text": expected, "content_match": {"ok": True, "why": "synthetic test answer"},
                  "_reviewer": "test-only-doubao"}
        if contract.get("_content_point_expectations"):
            result["point_match"] = [{"index": index, "ok": True, "why": "synthetic point answer"}
                                     for index in range(1, len(contract["_content_point_expectations"]) + 1)]
        if contract.get("_square_crop_expectation"):
            result["square_crop"] = {"ok": True, "why": "synthetic square answer"}
        if contract.get("_thumbnail_expectation"):
            result["thumbnail_readable"] = {"ok": True, "why": "synthetic thumbnail answer"}
        if failing:
            result["must_see"][-1]["ok"] = False
        if change:
            change(image)
        return result

    monkeypatch.setattr(reviewer, "review", review)


@pytest.mark.parametrize("failed", [False, True])
def test_reports_keep_failure_and_validate_exact_production(tmp_path, monkeypatch, failed):
    made = candidate(tmp_path, monkeypatch)
    mocked_reviewer(monkeypatch, failing=failed)
    report, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors, errors
    assert report["passed"] is (not failed)
    assert Path(report["report_path"]).exists()
    verified = verify_candidate_review(tmp_path, Path(report["report_path"]), require_passed=False)
    assert verified["production_id"] == made["production_id"]
    if failed:
        with pytest.raises(ValueError, match="未通过"):
            verify_candidate_review(tmp_path, Path(report["report_path"]))


@pytest.mark.parametrize("target", ["image", "article", "report", "preview"])
def test_old_report_rejects_mutated_actual_input(tmp_path, monkeypatch, target):
    made = candidate(tmp_path, monkeypatch)
    mocked_reviewer(monkeypatch)
    report, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors
    if target == "image":
        (tmp_path / made["files"]["main"]).write_bytes(b"replacement")
    elif target == "article":
        (tmp_path / "定稿.md").write_text("changed")
    elif target == "preview":
        Path(report["binding_paths"]["square"]).write_bytes(b"replacement")
    else:
        path = Path(report["report_path"])
        value = json.loads(path.read_text())
        value["actual_reviewer"] = "replacement"
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        verify_candidate_review(tmp_path, Path(report["report_path"]))


def test_change_during_independent_review_prevents_report(tmp_path, monkeypatch):
    made = candidate(tmp_path, monkeypatch)
    mocked_reviewer(monkeypatch, change=lambda image: image.write_bytes(b"changed while reviewing"))
    report, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert report is None and errors
    assert not (Path(made["receipt_path"]).parent / "qa-reports").exists()


@pytest.mark.parametrize("mutation", ["conclusion", "dependencies", "reviewer", "id"])
def test_rehashed_report_still_cannot_change_consumer_meaning(tmp_path, monkeypatch, mutation):
    made = candidate(tmp_path, monkeypatch)
    mocked_reviewer(monkeypatch, failing=True)
    report, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors
    value = json.loads(Path(report["report_path"]).read_text())
    if mutation == "conclusion":
        value["passed"] = True
        value["status"] = "qa_passed"
        value["verdict"]["passed"] = True
    elif mutation == "dependencies":
        value["binding_paths"].pop("production")
    elif mutation == "id":
        value["id"] = "wrong"
    else:
        value["actual_reviewer"] = "different"
    altered = Path(report["report_path"]).parent / f"{digest(value)}.json"
    altered.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        verify_candidate_review(tmp_path, altered, require_passed=False)


def test_actual_objection_blocks_green_report_without_rewriting_it(tmp_path, monkeypatch):
    from scripts.stylebook_acceptance import reject_candidate, verify_acceptable_candidate
    made = candidate(tmp_path, monkeypatch)
    mocked_reviewer(monkeypatch)
    report, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors
    report_path = Path(report["report_path"])
    before = report_path.read_bytes()
    verify_acceptable_candidate(tmp_path, report_path)
    with pytest.raises(ValueError, match="说明"):
        reject_candidate(tmp_path, Path(made["receipt_path"]), "  ")
    objection = reject_candidate(tmp_path, Path(made["receipt_path"]), "Test-only observed text collision")
    with pytest.raises(ValueError, match="模型绿灯不能覆盖"):
        verify_acceptable_candidate(tmp_path, report_path)
    assert report_path.read_bytes() == before
    Path(objection["path"]).write_text("{}")
    with pytest.raises(ValueError, match="损坏"):
        verify_acceptable_candidate(tmp_path, report_path)
