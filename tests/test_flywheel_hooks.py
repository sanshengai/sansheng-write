"""写作飞轮钩子：存初稿基线、定稿自动比对、缺基线要明说、断流要看得见。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import flywheel_hooks as FW  # noqa: E402

DRAFT = "这是 AI 写的第一版。" * 80
FINAL = DRAFT.replace("第一版", "终稿", 1) + "\n作者补了一句大白话。\n"


@pytest.fixture
def art(tmp_path, monkeypatch):
    d = tmp_path / "108-测试"
    d.mkdir()
    (d / "定稿.md").write_text(DRAFT, encoding="utf-8")
    fly = tmp_path / "flywheel"
    monkeypatch.setattr(FW, "_flywheel_dir", lambda: fly)
    return d


def test_snapshot_once_and_never_overwritten_by_later_edits(art):
    meta = FW.snapshot_ai_draft(art)
    assert meta and meta["basis"] == "first_pipeline_call"
    (art / "定稿.md").write_text(FINAL, encoding="utf-8")  # 作者改稿之后再碰流水线
    assert FW.snapshot_ai_draft(art) is None
    snap = next(art.rglob("_ai-draft.md"))
    assert snap.read_text(encoding="utf-8") == DRAFT  # 基线仍是初稿


def test_no_snapshot_after_author_approval_or_for_stub_drafts(art):
    (art / "定稿.md").write_text("太短", encoding="utf-8")
    assert FW.snapshot_ai_draft(art) is None
    (art / "定稿.md").write_text(DRAFT, encoding="utf-8")
    (art / "_draft-approval.md").write_text("作者原话", encoding="utf-8")
    assert FW.snapshot_ai_draft(art) is None  # 已批准的稿多半是终稿
    assert FW.snapshot_ai_draft(art, force=True, basis="deliver_draft")["basis"] == "deliver_draft"


def test_final_edit_is_diffed_and_queued(art):
    FW.snapshot_ai_draft(art)
    (art / "定稿.md").write_text(FINAL, encoding="utf-8")
    item = FW.queue_learning(art)
    assert item["status"] == "pending" and item["diff_chars"] > 0 and Path(item["diff"]).is_file()
    assert [p["article"] for p in FW.pending_items()] == ["108-测试"]
    FW.mark("108-测试", "done")
    assert FW.pending_items() == []


def test_missing_baseline_is_reported_and_five_in_a_row_stall(art, tmp_path):
    item = FW.queue_learning(art)  # 没有快照
    assert item["status"] == "no_baseline" and "无法比对" in item["note"]
    for i in range(4):
        d = tmp_path / f"a{i}"
        d.mkdir()
        (d / "定稿.md").write_text(DRAFT)
        FW.queue_learning(d)
    assert FW.stalled()
    FW.snapshot_ai_draft(art)
    (art / "定稿.md").write_text(FINAL, encoding="utf-8")
    FW.queue_learning(art)
    assert not FW.stalled()


def test_unchanged_final_teaches_nothing(art):
    FW.snapshot_ai_draft(art)
    assert FW.queue_learning(art)["status"] == "unchanged"
