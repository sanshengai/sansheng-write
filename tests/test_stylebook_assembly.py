"""Exact-source assembly consumer tests, using clearly synthetic model/tool outputs."""
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.stylebook_workflow import generation_requests, collect_host_result, produce_candidate, digest, sha
from scripts.stylebook_review import review_candidate, verify_candidate_review
from scripts.stylebook_plan_review import verify_plan_review
from scripts.stylebook_group import select_group, verify_group
from scripts.stylebook_source import assembled_text
from scripts.stylebook_assembly import verify_assembly
from scripts.assemble_release import assemble_release_markdown, author_content_sha256
from test_stylebook_plan_group import plan_report
from test_stylebook_review import mocked_reviewer


def accepted_group(tmp_path, monkeypatch, *, body):
    full, errors = plan_report(tmp_path, monkeypatch, body=body)
    assert not errors
    pending, errors = generation_requests(tmp_path)
    assert not errors
    host = {key: value for key, value in pending.items() if key != "path"}
    image = tmp_path / "synthetic-output.png"
    Image.new("RGB", (128, 128), "ivory").save(image)
    reports = {}
    mocked_reviewer(monkeypatch)
    for task in host["requests"]:
        result = tmp_path / f"synthetic-{task['id']}.json"
        result.write_text(json.dumps({"schema_version": 1, "backend": "image_gen.imagegen",
            "invocation_status": "succeeded", "host_request_path": pending["path"],
            "host_request_digest": digest(host), "request_id": host["request_id"], "id": task["id"],
            "call": task["call"], "tool_output": "Synthetic test response",
            "output": {"path": str(image), "sha256": sha(image)}}))
        raw, errors = collect_host_result(tmp_path, result)
        assert not errors
        made, errors = produce_candidate(tmp_path, Path(raw["receipt_path"]))
        assert not errors
        qa, errors = review_candidate(tmp_path, Path(made["receipt_path"]))
        assert not errors
        reports[task["id"]] = Path(qa["report_path"])
    selected, errors = select_group(tmp_path, Path(full["report_path"]), reports)
    assert not errors
    return full, reports, selected


@pytest.mark.parametrize("body", [False, True])
def test_consumer_assembly_preserves_source_and_all_bound_reviews(tmp_path, monkeypatch, body):
    full, reports, selected = accepted_group(tmp_path, monkeypatch, body=body)
    original = (tmp_path / "定稿.md").read_bytes()
    batch = json.loads((tmp_path / "素材/render-batch.json").read_text())
    source = tmp_path / batch["source_snapshot"]
    assert source.read_bytes() == original
    result, errors = assemble_release_markdown(tmp_path)
    assert not errors, errors
    assert result["image_count"] == int(body)
    assert verify_assembly(tmp_path)["assembly_id"] == result["assembly_id"]
    assert source.read_bytes() == original
    assert author_content_sha256((tmp_path / "定稿.md").read_text()) == author_content_sha256(original.decode())
    verify_plan_review(tmp_path, Path(full["report_path"]))
    for report in reports.values():
        verify_candidate_review(tmp_path, report)
    assert verify_group(tmp_path)["selection_id"] == selected["selection_id"]
    repeated, errors = assemble_release_markdown(tmp_path)
    assert not errors and not repeated["changed"]
    assert repeated["assembly_id"] == result["assembly_id"]


@pytest.mark.parametrize("mutation", ["author", "image_reference", "extra_block", "source", "active_image", "receipt", "method"])
def test_assembled_consumer_rejects_changed_inputs(tmp_path, monkeypatch, mutation):
    _, _, _ = accepted_group(tmp_path, monkeypatch, body=True)
    result, errors = assemble_release_markdown(tmp_path)
    assert not errors
    draft = tmp_path / "定稿.md"
    batch = json.loads((tmp_path / "素材/render-batch.json").read_text())
    if mutation == "author":
        draft.write_text(draft.read_text().replace("验证来源", "不用验证"))
    elif mutation == "image_reference":
        draft.write_text(draft.read_text().replace("素材/infographic-01.png", "素材/unreviewed.png"))
    elif mutation == "extra_block":
        draft.write_text(draft.read_text() + "\n<!-- SANSHENG-VISUAL-START:extra -->\n![](evil.png)\n<!-- SANSHENG-VISUAL-END:extra -->\n")
    elif mutation == "source":
        (tmp_path / batch["source_snapshot"]).write_text("replacement source")
    elif mutation == "active_image":
        (tmp_path / "素材/cover.png").write_bytes(b"replacement image")
    elif mutation == "method":
        import scripts.stylebook_source as source
        monkeypatch.setattr(source, "methods", lambda: {"source": "changed", "assembly_helpers": "changed"})
    else:
        receipt = tmp_path / "素材/stylebook-assembly.json"
        record = json.loads(receipt.read_text())
        record["source_sha256"] = "0" * 64
        receipt.write_text(json.dumps(record))
    with pytest.raises((ValueError, OSError)):
        verify_assembly(tmp_path)


def test_canonical_blocks_preserve_inline_markup_and_preceding_position():
    original = '<mark>唯一的一句话。</mark>\n\n后面的正文。\n'
    plan = {"article_plan": {"items": [{"id": "01", "position": "「唯一的一句话。」之后"},
                                         {"id": "02", "position": "「后面的正文。」之前"}]}}
    output = assembled_text(original, plan)
    assert '<mark>唯一的一句话。</mark>' in output
    assert output.index("START:01") > output.index("</mark>")
    assert output.index("START:02") < output.index("后面的正文。")
    assert author_content_sha256(original) == author_content_sha256(output)
    with pytest.raises(ValueError, match="唯一命中"):
        assembled_text("重复一句话。\n\n重复一句话。", {"article_plan": {"items": [{"id":"01","position":"「重复一句话。」之后"}]}})


def test_no_group_or_blank_source_cannot_assemble(tmp_path, monkeypatch):
    plan_report(tmp_path, monkeypatch)
    before = (tmp_path / "定稿.md").read_bytes()
    result, errors = assemble_release_markdown(tmp_path)
    assert result is None and errors
    assert (tmp_path / "定稿.md").read_bytes() == before
    (tmp_path / "定稿.md").write_bytes(b"")
    pending, errors = generation_requests(tmp_path)
    assert pending is None and errors
