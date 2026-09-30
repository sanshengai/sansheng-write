"""Typography variants retain raw provenance and cannot silently change the brief."""
import copy
import json
from pathlib import Path

import pytest

from scripts.stylebook_layout import apply_layout, refit_candidate
from scripts.stylebook_review import review_candidate, verify_candidate_review
from scripts.stylebook_workflow import collect_host_result, digest, sha
from test_stylebook_workflow import host_result_fixture
from test_stylebook_review import mocked_reviewer


def prepared(tmp_path, monkeypatch):
    text = {"mode": "overlay", "items": [{"role": "title", "text": "来源可核对", "box": [.1, .2, .8, .2],
        "font_px": 60, "min_px": 40, "font_family": "hand", "weight": "bold", "require_blank": True}]}
    invocation, _, _ = host_result_fixture(tmp_path, monkeypatch, text=text)
    raw, errors = collect_host_result(tmp_path, invocation)
    assert not errors
    layout = tmp_path / "layout.json"
    layout.write_text(json.dumps({"version": 1, "items": [{"box": [.1, .4, .8, .2], "font_px": 66, "min_px": 40}]}))
    return raw, layout


def test_actual_refit_consumer_binds_new_geometry_and_original_invocation(tmp_path, monkeypatch):
    raw, layout = prepared(tmp_path, monkeypatch)
    host = tmp_path / raw["host_request_path"]
    original_host = host.read_bytes()
    result, errors = refit_candidate(tmp_path, Path(raw["receipt_path"]), layout)
    assert not errors, errors
    assert result["production_method"] == "refit_generated_raw_lettering"
    assert result["manifest"]["text"]["items"][0]["text"] == "来源可核对"
    assert result["manifest"]["text"]["items"][0]["box"] == [.1, .4, .8, .2]
    assert host.read_bytes() == original_host
    assert result["raw_receipt_sha256"] == sha(Path(raw["receipt_path"]))
    mocked_reviewer(monkeypatch)
    report, errors = review_candidate(tmp_path, Path(result["receipt_path"]))
    assert not errors and report["passed"]
    verify_candidate_review(tmp_path, Path(report["report_path"]))
    layout.write_text('{"version":1,"items":[{"box":[0.1,0.5,0.8,0.2]}]}')
    with pytest.raises(ValueError, match="已改变"):
        verify_candidate_review(tmp_path, Path(report["report_path"]))


@pytest.mark.parametrize("mutation", ["text", "count", "minimum", "zero_box", "outside", "nan", "empty"])
def test_refit_rejects_content_and_unreadable_layout_mutants(tmp_path, monkeypatch, mutation):
    raw, layout = prepared(tmp_path, monkeypatch)
    value = json.loads(layout.read_text())
    if mutation == "text": value["items"][0]["text"] = "invented claim"
    elif mutation == "count": value["items"].append({"font_px":60})
    elif mutation == "minimum": value["items"][0]["min_px"] = 20
    elif mutation == "zero_box": value["items"][0]["box"] = [.1,.1,0,.2]
    elif mutation == "outside": value["items"][0]["box"] = [.9,.9,.5,.5]
    elif mutation == "nan": value["items"][0]["box"][0] = float("nan")
    elif mutation == "empty": value["items"] = []
    layout.write_text(json.dumps(value))
    result, errors = refit_candidate(tmp_path, Path(raw["receipt_path"]), layout)
    assert result is None and errors
    assert not (tmp_path / "素材/stylebook-final").exists()


def test_rehashed_production_cannot_claim_changed_text(tmp_path, monkeypatch):
    from scripts.stylebook_review import production_inputs
    raw, layout = prepared(tmp_path, monkeypatch)
    result, errors = refit_candidate(tmp_path, Path(raw["receipt_path"]), layout)
    assert not errors
    value = json.loads(Path(result["receipt_path"]).read_text())
    value["manifest"]["text"]["items"][0]["text"] = "invented output"
    identity = {k:v for k,v in value.items() if k not in ("production_id", "files")}
    new_id = digest(identity)
    directory = Path(result["receipt_path"]).parent.parent / new_id
    directory.mkdir()
    for key, path in list(value["files"].items()):
        image = directory / Path(path).name
        image.write_bytes((tmp_path / path).read_bytes())
        value["files"][key] = str(image.relative_to(tmp_path))
    value["production_id"] = new_id
    receipt = directory / "production.json"
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="不一致"):
        production_inputs(tmp_path, receipt)
