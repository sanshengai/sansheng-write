import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.stylebook_workflow import collect_host_result, produce_candidate, sha
from test_stylebook_workflow import host_result_fixture


def fixture(tmp_path, monkeypatch):
    record, submitted, original = host_result_fixture(tmp_path, monkeypatch)
    edited = tmp_path / "actual-edited.png"
    Image.new("RGB", (128, 128), "lightgreen").save(edited)
    submitted["base_output"] = copy.deepcopy(submitted["output"])
    submitted["base_tool_output"] = submitted["tool_output"]
    submitted["output"] = {"path": str(edited), "sha256": sha(edited)}
    submitted["refinements"] = [{"backend": "image_gen.imagegen", "invocation_status": "succeeded",
                                 "tool_output": "Synthetic edit response; test fixture",
                                 "call": {"prompt": "Correct margins; preserve composition",
                                          "referenced_image_paths": [str(original)]},
                                 "output": copy.deepcopy(submitted["output"])}]
    record.write_text(json.dumps(submitted))
    return record, submitted, original


def test_actual_collect_and_production_bind_original_plus_edited_bytes(tmp_path, monkeypatch):
    record, submitted, original = fixture(tmp_path, monkeypatch)
    raw, errors = collect_host_result(tmp_path, record)
    assert not errors, errors
    assert raw["submitted_result"]["refinements"] == submitted["refinements"]
    assert not raw["independent_invocation_verified"]
    receipt = Path(raw["receipt_path"])
    produced, errors = produce_candidate(tmp_path, receipt)
    assert not errors, errors
    assert str(original) in produced["dependencies_sha256"]


@pytest.mark.parametrize("mutation", ["empty", "unlinked", "changed_original", "wrong_final"])
def test_actual_collector_rejects_invalid_edit_chain(tmp_path, monkeypatch, mutation):
    record, submitted, original = fixture(tmp_path, monkeypatch)
    if mutation == "empty":
        submitted["refinements"] = []
    elif mutation == "unlinked":
        submitted["refinements"][0]["call"]["referenced_image_paths"] = []
    elif mutation == "changed_original":
        original.write_bytes(b"changed")
    else:
        submitted["output"] = submitted["base_output"]
    record.write_text(json.dumps(submitted))
    result, errors = collect_host_result(tmp_path, record)
    assert result is None and errors


def test_three_real_edits_keep_full_chain_and_reject_broken_middle(tmp_path, monkeypatch):
    record, submitted, original = fixture(tmp_path, monkeypatch)
    for i in (2, 3):
        previous = submitted['output']['path']
        edited = tmp_path / f'edit-{i}.png'
        Image.new('RGB', (128, 128), (20 * i, 140, 100)).save(edited)
        output = {'path': str(edited), 'sha256': sha(edited)}
        submitted['refinements'].append({'backend': 'image_gen.imagegen', 'invocation_status': 'succeeded',
            'tool_output': 'Synthetic test edit', 'call': {'prompt': f'Fix separate issue {i}',
            'referenced_image_paths': [previous]}, 'output': output})
        submitted['output'] = output
    record.write_text(json.dumps(submitted))
    raw, errors = collect_host_result(tmp_path, record)
    assert raw and not errors
    assert len(raw['submitted_result']['refinements']) == 3
    submitted['refinements'][1]['call']['referenced_image_paths'] = [str(original)]
    record.write_text(json.dumps(submitted))
    raw, errors = collect_host_result(tmp_path, record)
    assert raw is None and errors
