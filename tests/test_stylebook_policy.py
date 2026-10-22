import copy
import json
import hashlib

import pytest

from scripts import stylebook_policy
from scripts.visual_workflow import compile_visual_plan
from scripts.stylebook_workflow import generation_requests
from test_stylebook_workflow import setup_plan


def test_actual_compile_rejects_declared_signature_style_mismatch(tmp_path, monkeypatch):
    setup_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(stylebook_policy, "brand", lambda: {})
    (tmp_path / "article-meta.yaml").write_text("cover_style: montage-evidence\nvisual_profile: warm-light-clay\n")
    result, errors = compile_visual_plan(tmp_path)
    assert result is None and any("声明 montage-evidence" in x for x in errors)
    assert not (tmp_path / "素材/render-batch.json").exists()


def test_actual_compile_and_render_reject_mutated_author_defaults(tmp_path, monkeypatch):
    plan = setup_plan(tmp_path, monkeypatch)
    policy = {"cover": plan["cover"]["style"], "body": plan["group"]["style"]}
    monkeypatch.setattr(stylebook_policy, "brand", lambda: {"visual": {"stylebook": policy}})
    result, errors = compile_visual_plan(tmp_path)
    assert result and not errors
    ready, errors = generation_requests(tmp_path)
    assert ready and not errors
    policy["cover"] = "C76@r3"
    ready, errors = generation_requests(tmp_path)
    assert ready is None and any("作者默认" in x for x in errors)


def test_empty_configured_default_is_rejected_not_treated_as_absent(tmp_path, monkeypatch):
    setup_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(stylebook_policy, "brand", lambda: {"visual": {"stylebook": {"body": ""}}})
    result, errors = compile_visual_plan(tmp_path)
    assert result is None and any("不能留空" in x for x in errors)


def test_signature_identity_accepts_real_origin_not_unrelated_style(tmp_path, monkeypatch):
    plan = setup_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(stylebook_policy, "brand", lambda: {})
    (tmp_path / "article-meta.yaml").write_text("cover_style: montage-evidence\nvisual_profile: warm-light-clay\n")
    result = stylebook_policy.check(tmp_path, plan, lambda code: {"aliases": ["montage-evidence", "warm-light-clay"]})
    assert result["declarations"]["body"] == "warm-light-clay"


def square_chain(tmp_path):
    first, last = tmp_path / "first.png", tmp_path / "last.png"
    first.write_bytes(b"original generated image")
    last.write_bytes(b"refined generated image")
    def step(path, call):
        return {"backend": "image_gen.imagegen", "invocation_status": "succeeded",
                "tool_output": "actual host output", "call": call,
                "output": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    data = {"steps": [step(first, {"prompt": "canonical square"}),
                       step(last, {"prompt": "keep artwork; add margins", "referenced_image_paths": [str(first)]})]}
    receipt = tmp_path / "chain.json"
    receipt.write_text(json.dumps(data))
    return receipt, first, last, data


def test_square_chain_accepts_linked_original_and_refinement(tmp_path):
    receipt, _, last, _ = square_chain(tmp_path)
    stylebook_policy.verify_square_source(receipt, last, "canonical square")


@pytest.mark.parametrize("mutation", ["empty", "wrong_prompt", "unlinked_refinement", "changed_original", "wrong_master"])
def test_square_chain_rejects_mutated_provenance(tmp_path, mutation):
    receipt, first, last, data = square_chain(tmp_path)
    master = last
    if mutation == "empty":
        data["steps"] = []
    elif mutation == "wrong_prompt":
        data["steps"][0]["call"]["prompt"] = "unrelated"
    elif mutation == "unlinked_refinement":
        data["steps"][1]["call"]["referenced_image_paths"] = [str(last)]
    elif mutation == "changed_original":
        first.write_bytes(b"silently replaced")
    else:
        master = first
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        stylebook_policy.verify_square_source(receipt, master, "canonical square")


def test_actual_compile_rejects_empty_square_master_provenance(tmp_path, monkeypatch):
    plan = setup_plan(tmp_path, monkeypatch)
    plan["cover"]["square_master"] = {}
    (tmp_path / "visual-plan.json").write_text(json.dumps(plan))
    result, errors = compile_visual_plan(tmp_path)
    assert result is None and any("真实生成 receipt" in e for e in errors)


def test_actual_compile_blocks_s02_cover_without_square_first_stage(tmp_path, monkeypatch):
    plan = setup_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(stylebook_policy, "brand", lambda: {})
    plan["cover"].update(style="S02@r3", own_style=True)
    (tmp_path / "visual-plan.json").write_text(json.dumps(plan))
    result, errors = compile_visual_plan(tmp_path)
    assert result is None and any("不能跳过方形预览" in e for e in errors)
