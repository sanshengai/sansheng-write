import json
from pathlib import Path

from PIL import Image
import pytest

from scripts import pipeline
from scripts.evidence import (
    seal_visual_receipt,
    sha256_file,
    verify_publish_receipt,
    verify_publish_ready,
    verify_visual_receipt,
    write_publish_receipt,
    write_publish_ready,
)


def _png(path: Path, size=(1200, 675), color=(220, 210, 190)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _visual_bundle(root: Path) -> Path:
    (root / "素材/prompts/final").mkdir(parents=True)
    (root / "article-meta.yaml").write_text(
        "cover_style: montage-evidence\n"
        "infographic_subject: ai-product\ninfographic_style: claymation\n",
        encoding="utf-8",
    )
    specs = [("cover", "cover.png", (1200, 510))]
    specs += [
        ("infographic", "infographic-01.png", (576, 1024)),
        ("infographic", "infographic-02.png", (1024, 576)),
        ("infographic", "infographic-03.png", (1024, 576)),
        ("infographic", "infographic-04.png", (576, 1024)),
    ]
    logs = []
    for i, (stage, name, size) in enumerate(specs):
        output = root / "素材" / name
        prompt = root / "素材/prompts/final" / f"{stage}-{i}.md"
        _png(output, size=size)
        prompt.write_text(
            "---\nstyle: claymation\n---\n精致、克制、清晰。\n", encoding="utf-8"
        )
        producer = "baoyu-cover-image" if stage == "cover" else "baoyu-infographic"
        logs.append({
            "schema_version": 2,
            "record_id": f"rec-{i}",
            "stage": stage,
            "producer": producer,
            "tool": producer,
            "renderer": "imagegen",
            "model": "test-model",
            "output": f"素材/{name}",
            "output_sha256": sha256_file(output),
            "prompt": f"素材/prompts/final/{stage}-{i}.md",
            "prompt_sha256": sha256_file(prompt),
            "cmd": f"{producer} --style claymation 素材/prompts/final/{stage}-{i}.md",
        })
    (root / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in logs) + "\n",
        encoding="utf-8",
    )
    (root / "_visual-qa.md").write_text(
        "# 视觉验收\n"
        "- [x] 封面主标题精致\n- [x] 封面无杂字\n- [x] 封面裁切安全\n"
        "- [x] 图 1 信息图逐字核对\n- [x] 图 2 信息图逐字核对\n"
        "- [x] 图 3 信息图逐字核对\n- [x] 图 4 信息图逐字核对\n"
        "- [x] 四张信息图风格一致\n\n结论：通过\n",
        encoding="utf-8",
    )
    return root


def test_visual_receipt_binds_final_bytes(tmp_path):
    article = _visual_bundle(tmp_path)
    receipt, errors = seal_visual_receipt(article)
    assert receipt and errors == []
    _png(article / "素材/cover.png", size=(1200, 510), color=(10, 20, 30))
    _, errors = verify_visual_receipt(article)
    assert any("旧 visual receipt 失效" in e for e in errors), errors


def test_publish_receipt_binds_html_hero_and_visuals(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>v1</html>", encoding="utf-8")
    assert write_publish_ready(article)[1] == []
    assert write_publish_receipt(article, "draft-1")[1] == []
    (article / "定稿.html").write_text("<html>v2</html>", encoding="utf-8")
    _, errors = verify_publish_receipt(article, "draft-1")
    assert any("必须重推" in e for e in errors), errors


def test_publish_ready_is_preflight_and_invalidates_on_local_change(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>v1</html>", encoding="utf-8")
    assert write_publish_ready(article)[1] == []
    (article / "定稿.html").write_text("<html>changed</html>", encoding="utf-8")
    _, errors = verify_publish_ready(article)
    assert any("publish-ready 后" in e for e in errors), errors


def test_publish_done_force_cannot_bypass_inline_gate(tmp_path):
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    pipeline.save_state(tmp_path, state)
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_done(
            "publish", tmp_path, ["draft_media_id=draft-unsafe"], force=True
        )
    assert exc.value.code == 2
    saved = pipeline.load_state(tmp_path)
    assert saved["stages"]["publish"]["status"] == "failed"
    assert "draft_media_id" not in saved["stages"]["publish"]
    assert not (tmp_path / "_publish-receipt.json").exists()


def test_failed_publish_restores_existing_receipt_and_state(tmp_path, monkeypatch):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>ready</html>", encoding="utf-8")
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "run_id": "run-fixture",
        "stages": {stage: {"status": "done"} for stage in pipeline.STAGE_ORDER},
    }
    state["stages"]["publish"]["draft_media_id"] = "trusted-id"
    pipeline.save_state(article, state)
    assert write_publish_ready(article)[1] == []
    receipt_path = article / pipeline.PUBLISH_RECEIPT_FILE
    receipt_path.write_text('{"draft_media_id":"trusted-id"}\n', encoding="utf-8")
    before_receipt = receipt_path.read_bytes()
    before_state = (article / pipeline.STATE_FILE).read_bytes()
    monkeypatch.setattr(
        pipeline, "verify_stage", lambda *args, **kwargs: (False, ["forced failure"])
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_done("publish", article, ["draft_media_id=new-id"], force=True)
    assert exc.value.code == 2
    assert receipt_path.read_bytes() == before_receipt
    assert (article / pipeline.STATE_FILE).read_bytes() != before_state
    saved = pipeline.load_state(article)
    assert saved["stages"]["publish"]["draft_media_id"] == "trusted-id"


def test_status_detects_prompt_and_qa_drift(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "run_id": "run-fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    for stage in ("cover", "infographic", "logo", "publish"):
        state["stages"][stage] = {
            "status": "done",
            "artifact_digest": pipeline._stage_artifact_digest(article, stage),
        }
    pipeline.save_state(article, state)
    prompt = article / "素材/prompts/final/cover-0.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    pipeline.cmd_status(article)
    saved = pipeline.load_state(article)
    assert saved["stages"]["cover"]["status"] == "dirty"
    assert saved["stages"]["logo"]["status"] == "dirty"
    assert saved["stages"]["publish"]["status"] == "dirty"

    # 重建干净摘要后只改 QA，logo 与 publish 也必须自动失效。
    for stage in ("cover", "infographic", "logo", "publish"):
        state["stages"][stage] = {
            "status": "done",
            "artifact_digest": pipeline._stage_artifact_digest(article, stage),
        }
    pipeline.save_state(article, state)
    qa = article / "_visual-qa.md"
    qa.write_text(qa.read_text(encoding="utf-8") + "复验变化\n", encoding="utf-8")
    pipeline.cmd_status(article)
    saved = pipeline.load_state(article)
    assert saved["stages"]["logo"]["status"] == "dirty"
    assert saved["stages"]["publish"]["status"] == "dirty"


def test_stage_timestamps_preserved_and_downstream_invalidated(tmp_path, monkeypatch):
    times = iter(["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"])
    monkeypatch.setattr(pipeline, "_now_iso", lambda: next(times))
    (tmp_path / "定稿.html").write_text("v1", encoding="utf-8")
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    state["stages"]["logo"]["status"] = "done"
    state["stages"]["publish"]["status"] = "done"
    pipeline._record_stage_success(tmp_path, state, "layout")
    first = state["stages"]["layout"]["first_completed_at"]
    (tmp_path / "定稿.html").write_text("v2", encoding="utf-8")
    pipeline._record_stage_success(tmp_path, state, "layout")
    assert state["stages"]["layout"]["first_completed_at"] == first
    assert state["stages"]["layout"]["last_verified_at"] != first
    assert state["stages"]["logo"]["status"] == "dirty"
    assert state["stages"]["publish"]["status"] == "dirty"
