"""Consumer-path mutations; synthetic model answers are not acceptance evidence."""
import importlib
import hashlib
import json
from pathlib import Path

import pytest

from scripts.visual_workflow import compile_visual_plan
from scripts.stylebook_workflow import digest
from scripts.stylebook_plan_review import review_article_plan, verify_plan_review
from scripts.stylebook_group import select_group, verify_group
from test_stylebook_workflow import setup_plan


BODY_CHECKS = ("reasonable", "position_ok", "shape_ok", "form_ok", "basis_ok",
               "no_literal_metaphor_or_real_face", "fidelity_ok", "reader_value_ok")


def plan_report(tmp_path, monkeypatch, *, body=True, fail=None, change=None, backend="ark_agent_plan",
                actual=None, existing_media=False):
    source_plan = setup_plan(tmp_path, monkeypatch, body=body)
    if existing_media:
        from scripts.assemble_release import author_content_sha256
        (tmp_path / "素材").mkdir(exist_ok=True)
        (tmp_path / "素材/shot.png").write_bytes(b"source media bytes; no pixel review")
        source = tmp_path / "定稿.md"
        source.write_text(source.read_text() + "\n![原图说明](素材/shot.png)\n![待补截图](素材/missing.png)\n")
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        source_plan["source"] = {"sha256": sha, "author_content_sha256": author_content_sha256(source.read_text())}
        source_plan["article_plan"]["source"]["sha256"] = sha
        source_plan["cover"]["source"]["sha256"] = sha
        source_plan["article_plan"]["editorial_constraints"] = {"author_words": "保留真实截图，不用生成图替代。"}
        (tmp_path / "visual-plan.json").write_text(json.dumps(source_plan, ensure_ascii=False))
    result, errors = compile_visual_plan(tmp_path)
    assert not errors
    monkeypatch.delenv("SANSHENG_IMAGE_QA_BACKEND", raising=False)
    if backend:
        monkeypatch.setenv("SANSHENG_IMAGE_PLAN_REVIEW_BACKEND", backend)
    else:
        monkeypatch.delenv("SANSHENG_IMAGE_PLAN_REVIEW_BACKEND", raising=False)
    peer = importlib.import_module("stylebook.qa.plan_review")

    def review(plan, article, backend=None, **kw):
        assert article.read_text() and "cover_brief" in plan
        value = {"items": [{"id": item["id"], **dict.fromkeys(BODY_CHECKS, True),
                            "why": "synthetic test answer"} for item in plan["items"]],
                 "missed_positions": [], "cover_review": {"fidelity_ok": True, "theme_ok": True,
                 "no_unrequested_claims": True, "why": "synthetic cover answer"}, "_reviewer": "test-only"}
        if fail == "body":
            value["items"][0]["fidelity_ok"] = False
        elif fail == "cover":
            value["cover_review"]["no_unrequested_claims"] = False
        elif fail == "missed":
            value["missed_positions"] = ["synthetic omitted context"]
        elif fail == "reviewer":
            value.pop("_reviewer")
        if change:
            change(article)
        if actual != "":
            value["_backend"] = actual or backend
        return value

    monkeypatch.setattr(peer, "review", review)
    return review_article_plan(tmp_path)


@pytest.mark.parametrize("body", [False, True])
def test_full_plan_accepts_zero_or_one_body_image_only_with_cover_review(tmp_path, monkeypatch, body):
    report, errors = plan_report(tmp_path, monkeypatch, body=body)
    assert not errors and report["passed"]
    verified = verify_plan_review(tmp_path, Path(report["report_path"]))
    assert verified["existing_visual_assessment"] == "editorial_text_context_only"
    (tmp_path / "定稿.md").write_text("changed source")
    with pytest.raises(ValueError):
        verify_plan_review(tmp_path, Path(report["report_path"]))


@pytest.mark.parametrize("fail", ["body", "cover", "missed"])
def test_any_plan_failure_is_kept_and_blocks_selection(tmp_path, monkeypatch, fail):
    report, errors = plan_report(tmp_path, monkeypatch, fail=fail)
    assert not errors and report["passed"] is False
    verify_plan_review(tmp_path, Path(report["report_path"]), require_passed=False)
    selected, errors = select_group(tmp_path, Path(report["report_path"]), {})
    assert selected is None and errors
    assert not (tmp_path / "素材/stylebook-selection.json").exists()


@pytest.mark.parametrize("kind", ["during", "reviewer"])
def test_incomplete_or_changed_review_cannot_save_report(tmp_path, monkeypatch, kind):
    report, errors = plan_report(tmp_path, monkeypatch, fail="reviewer" if kind == "reviewer" else None,
                                 change=(lambda path: path.write_text("changed during review")) if kind == "during" else None)
    assert report is None and errors
    assert not (tmp_path / "素材/stylebook-plan-reviews").exists()


def test_rehashed_false_plan_conclusion_still_rejected(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch, fail="cover")
    assert not errors
    value = json.loads(Path(report["report_path"]).read_text())
    value["passed"] = True
    value["status"] = "plan_review_passed"
    changed = Path(report["report_path"]).parent / f"{digest(value)}.json"
    changed.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="结论"):
        verify_plan_review(tmp_path, changed)


def test_group_requires_exact_complete_set(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch)
    assert not errors
    for reports in ({}, {"cover": Path("missing")}, {"cover": Path("missing"), "01": Path("missing"), "extra": Path("missing")}):
        group, errors = select_group(tmp_path, Path(report["report_path"]), reports)
        assert group is None and any("恰好" in e for e in errors)
    assert not (tmp_path / "素材/stylebook-selection.json").exists()


def test_actual_cover_selection_rechecks_known_objection(tmp_path, monkeypatch):
    from scripts.stylebook_workflow import collect_host_result, produce_candidate
    from scripts.stylebook_review import review_candidate
    from scripts.stylebook_acceptance import reject_candidate
    from PIL import Image
    from scripts.stylebook_workflow import generation_requests, sha
    from test_stylebook_review import mocked_reviewer

    report, errors = plan_report(tmp_path, monkeypatch, body=False)
    assert not errors
    pending, errors = generation_requests(tmp_path)
    assert not errors
    image = tmp_path / "synthetic-tool-output.png"
    Image.new("RGB", (128, 128), "ivory").save(image)
    host = {key: value for key, value in pending.items() if key != "path"}
    task = host["requests"][0]
    result = tmp_path / "synthetic-host-result.json"
    result.write_text(json.dumps({"schema_version": 1, "backend": "image_gen.imagegen",
        "invocation_status": "succeeded", "host_request_path": pending["path"],
        "host_request_digest": digest(host), "request_id": host["request_id"], "id": task["id"],
        "call": task["call"], "tool_output": "Synthetic test response",
        "output": {"path": str(image), "sha256": sha(image)}}))
    collected, errors = collect_host_result(tmp_path, result)
    assert not errors
    made, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert not errors
    mocked_reviewer(monkeypatch)
    qa, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors
    group, errors = select_group(tmp_path, Path(report["report_path"]), {"cover": Path(qa["report_path"])})
    assert not errors, errors
    assert verify_group(tmp_path)["selection_id"] == group["selection_id"]
    reject_candidate(tmp_path, Path(made["receipt_path"]), "Synthetic test observed collision")
    with pytest.raises(ValueError, match="模型绿灯不能覆盖"):
        verify_group(tmp_path)


def test_recorded_backend_is_the_image_skill_resolution(tmp_path, monkeypatch):
    peer = importlib.import_module("stylebook.qa.plan_review")
    report, errors = plan_report(tmp_path, monkeypatch, backend=None)
    assert not errors and report["backend"] == peer.resolve_backend() == "ark_coding_plan"
    verify_plan_review(tmp_path, Path(report["report_path"]))


def test_review_on_a_different_backend_cannot_save_report(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch, actual="claude_cli")
    assert report is None and any("后端" in error for error in errors)
    assert not list((tmp_path / "素材/stylebook-plan-reviews").glob("*.json"))


def test_review_without_backend_field_cannot_save_report(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch, actual="")
    assert report is None and any("后端" in error for error in errors)


def test_existing_media_context_resolves_from_article_and_binds_bytes(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch, body=False, existing_media=True)
    assert not errors
    context = report["binding_values"]["existing_visuals"]
    assert context["reference_count"] == 2
    assert context["references"][0]["status"] == "local_bytes_verified"
    assert context["references"][1]["status"] == "missing_or_unreadable"
    assert report["binding_paths"]["existing-media:existing-01"] == str(tmp_path / "素材/shot.png")
    peer = importlib.import_module("stylebook.qa.plan_review")
    prompt = peer.prompt(report["binding_values"]["review_plan"], Path(report["binding_paths"]["article"]), "inline")
    assert "保留真实截图，不用生成图替代。" in prompt
    assert "原图说明" in prompt and "local_bytes_verified" in prompt
    verify_plan_review(tmp_path, Path(report["report_path"]))
    (tmp_path / "素材/shot.png").write_bytes(b"changed after review")
    with pytest.raises(ValueError):
        verify_plan_review(tmp_path, Path(report["report_path"]))


def test_missing_media_becoming_available_requires_current_evidence(tmp_path, monkeypatch):
    report, errors = plan_report(tmp_path, monkeypatch, body=False, existing_media=True)
    assert not errors
    (tmp_path / "素材/missing.png").write_bytes(b"now available")
    with pytest.raises(ValueError):
        verify_plan_review(tmp_path, Path(report["report_path"]))
