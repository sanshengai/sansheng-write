"""Source changes can reuse exact raw calls, with truthful historical evidence."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.assemble_release import author_content_sha256
from scripts.stylebook_workflow import collect_host_result, digest, sha, produce_candidate
from scripts.stylebook_workflow import generation_requests
from scripts.visual_workflow import compile_visual_plan
from scripts.stylebook_reuse import reuse_raw, validate_raw
from scripts.stylebook_review import production_inputs, review_candidate, verify_candidate_review
from test_stylebook_workflow import host_result_fixture
from test_stylebook_review import mocked_reviewer


def recompile_source(tmp_path):
    plan_path = tmp_path / "visual-plan.json"
    plan = json.loads(plan_path.read_text())
    article = tmp_path / "定稿.md"
    article.write_text(article.read_text() + "\n")
    plan["source"] = {"sha256": sha(article), "author_content_sha256": author_content_sha256(article.read_text())}
    plan["article_plan"]["source"]["sha256"] = sha(article)
    plan["cover"]["source"]["sha256"] = sha(article)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False))
    current, errors = compile_visual_plan(tmp_path)
    assert not errors, errors
    return current


def changed_source(tmp_path, monkeypatch):
    invocation, _, _ = host_result_fixture(tmp_path, monkeypatch)
    old, errors = collect_host_result(tmp_path, invocation)
    assert not errors
    current = recompile_source(tmp_path)
    assert current["request_id"] != old["request_id"]
    return old


def test_reference_bytes_changed_at_same_path_are_rejected(tmp_path, monkeypatch):
    from PIL import Image
    invocation, submitted, _ = host_result_fixture(tmp_path, monkeypatch)
    reference = tmp_path / "style-reference.png"
    Image.new("RGB", (128, 128), "ivory").save(reference)
    plan_path = tmp_path / "visual-plan.json"
    plan = json.loads(plan_path.read_text())
    plan["cover"]["references"] = [{"role": "style", "path": str(reference)}]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False))
    _, errors = compile_visual_plan(tmp_path)
    assert not errors
    pending, errors = generation_requests(tmp_path, only={"cover"})
    assert not errors
    host = {k:v for k,v in pending.items() if k != "path"}
    submitted.update(host_request_path=pending["path"], host_request_digest=digest(host),
                     request_id=host["request_id"], call=host["requests"][0]["call"])
    invocation.write_text(json.dumps(submitted))
    old, errors = collect_host_result(tmp_path, invocation)
    assert not errors
    recompile_source(tmp_path)
    reused, errors = reuse_raw(tmp_path, Path(old["receipt_path"]), "cover")
    assert not errors, errors
    made, errors = produce_candidate(tmp_path, Path(reused["receipt_path"]))
    assert not errors
    Image.new("RGB", (128, 128), "navy").save(reference)
    refused, errors = reuse_raw(tmp_path, Path(old["receipt_path"]), "cover")
    assert refused is None and errors
    with pytest.raises(ValueError, match="参考图字节已改变"):
        production_inputs(tmp_path, Path(made["receipt_path"]))


def test_reuse_actual_production_review_and_historical_mutation(tmp_path, monkeypatch):
    old = changed_source(tmp_path, monkeypatch)
    old_path = Path(old["receipt_path"])
    before = old_path.read_bytes()
    reused, errors = reuse_raw(tmp_path, old_path, "cover")
    assert not errors, errors
    assert reused["source_strength"] == "host_attested_reused"
    assert reused["reuse"]["new_invocation"] is False
    assert reused["submitted_result"] == old["submitted_result"]
    assert old_path.read_bytes() == before
    made, errors = produce_candidate(tmp_path, Path(reused["receipt_path"]))
    assert not errors, errors
    mocked_reviewer(monkeypatch)
    review, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
    assert not errors and review["passed"], errors
    verify_candidate_review(tmp_path, Path(review["report_path"]))
    old_path.write_bytes(before + b" ")
    with pytest.raises(ValueError, match="来源凭证已改变"):
        verify_candidate_review(tmp_path, Path(review["report_path"]))


@pytest.mark.parametrize("mutation", ["prompt", "raw", "host", "snapshot", "empty"])
def test_reuse_rejects_changed_inputs_and_empty_origin(tmp_path, monkeypatch, mutation):
    old = changed_source(tmp_path, monkeypatch)
    path = Path(old["receipt_path"])
    if mutation == "prompt":
        plan_path = tmp_path / "visual-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["cover"]["content"]["subject"] += " changed"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False))
        _, errors = compile_visual_plan(tmp_path)
        assert not errors
    elif mutation == "raw": (tmp_path / old["raw_path"]).write_bytes(b"damaged")
    elif mutation == "host": (tmp_path / old["host_request_path"]).write_text("{}")
    elif mutation == "snapshot":
        compiled = json.loads((tmp_path / "素材/stylebook-requests" / f"{old['request_id']}.json").read_text())
        (tmp_path / compiled["source_snapshot"]).write_text("changed historical author")
    else: path.write_bytes(b"")
    reused, errors = reuse_raw(tmp_path, path, "cover")
    assert reused is None and errors


def test_rehashed_reuse_cannot_hide_old_invocation_or_claim_new_invocation(tmp_path, monkeypatch):
    old = changed_source(tmp_path, monkeypatch)
    reused, errors = reuse_raw(tmp_path, Path(old["receipt_path"]), "cover")
    assert not errors
    saved = json.loads(Path(reused["receipt_path"]).read_text())
    for change in ("strip_origin", "new_invocation", "different_output"):
        value = json.loads(json.dumps(saved))
        if change == "strip_origin":
            value.pop("reuse")
            value["source_strength"] = "host_attested"
        elif change == "new_invocation": value["reuse"]["new_invocation"] = True
        else: value["submitted_result"]["output"]["sha256"] = "0" * 64
        path = Path(reused["receipt_path"]).parent / f"{digest(value)}.json"
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            validate_raw(tmp_path, path)
        made, errors = produce_candidate(tmp_path, path)
        assert not errors
        with pytest.raises(ValueError):
            production_inputs(tmp_path, Path(made["receipt_path"]))


def test_reuse_cli_reports_no_new_generation(tmp_path, monkeypatch):
    old = changed_source(tmp_path, monkeypatch)
    entry = Path(__file__).resolve().parents[1] / "scripts/pipeline.py"
    run = subprocess.run([sys.executable, str(entry), "--dir", str(tmp_path), "reuse-stylebook-raw",
                          "--raw-receipt", old["receipt_path"], "--id", "cover"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "没有新生图调用" in run.stdout and "QA 尚未完成" in run.stdout
