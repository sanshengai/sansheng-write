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
    capture(art)
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
    capture(art)
    FW.queue_learning(art)
    assert not FW.stalled()


def test_unchanged_final_teaches_nothing(art):
    FW.snapshot_ai_draft(art)
    capture(art)
    assert FW.queue_learning(art)["status"] == "unchanged"


def capture(art, text=None, kind="author-edited"):
    source = art / "author-original.md"
    source.write_text(text if text is not None else (art / "定稿.md").read_text())
    evidence = art / "author-request.md"
    evidence.write_text("作者明确说明：这是我的手改原件，请学习修改。")
    return FW.capture_author_revision(art, source, evidence=evidence, source_kind=kind)


def queue_revision(art, text=FINAL):
    capture(art, text)
    return FW.queue_learning(art)


def test_unproven_final_is_not_author_evidence(art):
    FW.snapshot_ai_draft(art)
    (art / "定稿.md").write_text(FINAL)
    (art / "_draft-approval.md").write_text("作者同意发布")
    item = FW.queue_learning(art)
    assert item["status"] == "needs_author_evidence"
    assert FW.pending_items() == []
    assert not list(art.rglob("diff-*.txt"))


def test_same_revision_is_queued_once_and_done_is_revision_scoped(art):
    FW.snapshot_ai_draft(art)
    first = queue_revision(art)
    assert FW.queue_learning(art)["status"] == "already_queued"
    assert len(FW.pending_items()) == 1
    FW.mark(first["learning_id"], "done")
    assert FW.queue_learning(art)["status"] == "already_learned"
    second = queue_revision(art, FINAL + "作者的新判断。")
    assert second["learning_id"] != first["learning_id"]
    assert [r["learning_id"] for r in FW.pending_items()] == [second["learning_id"]]


def test_machine_assembly_never_changes_registered_learning(art):
    FW.snapshot_ai_draft(art)
    first = queue_revision(art)
    original_diff = Path(first["diff"]).read_bytes()
    (art / "定稿.md").write_text(FINAL + "\n![截图](new.png)\n<!-- audio-card -->")
    (art / "author-original.md").write_text("源文件后来也被改了")
    item = FW.queue_learning(art, art / "定稿.md")
    assert item["status"] == "already_queued"
    assert item["learning_id"] == first["learning_id"]
    assert Path(first["diff"]).read_bytes() == original_diff
    assert len(FW.pending_items()) == 1


def test_author_directed_content_cannot_be_promoted_as_voice(art):
    FW.snapshot_ai_draft(art)
    capture(art, FINAL, kind="author-directed")
    item = FW.queue_learning(art)
    assert item["status"] == "pending"
    assert item["voice_eligible"] is False


@pytest.mark.parametrize("target", ["source_file", "evidence_file"])
def test_tampered_snapshot_or_evidence_refuses_new_queue(art, target):
    FW.snapshot_ai_draft(art)
    receipt = capture(art, FINAL)
    (art / receipt[target]).write_text("被改写")
    assert FW.queue_learning(art)["status"] == "needs_author_evidence"
    assert FW.pending_items() == []


@pytest.mark.parametrize("target", ["source_file", "evidence_file"])
def test_escaped_receipt_path_is_rejected(art, tmp_path, target):
    FW.snapshot_ai_draft(art)
    capture(art, FINAL)
    outside = tmp_path / "outside.md"
    outside.write_text("external")
    path = FW._learning_dir(art) / "current.json"
    receipt = json.loads(path.read_text())
    receipt[target] = str(outside)
    path.write_text(json.dumps(receipt))
    assert FW.queue_learning(art)["status"] == "needs_author_evidence"
    assert FW.pending_items() == []


def test_empty_author_source_or_evidence_is_rejected(art):
    source = art / "source.md"
    source.write_text(" ")
    evidence = art / "evidence.md"
    evidence.write_text("确认为手改")
    with pytest.raises(ValueError):
        FW.capture_author_revision(art, source, evidence=evidence, source_kind="author-edited")
    source.write_text(FINAL)
    evidence.write_text("")
    with pytest.raises(ValueError):
        FW.capture_author_revision(art, source, evidence=evidence, source_kind="author-edited")


def test_legacy_done_does_not_hide_later_pending(art):
    folder = FW._flywheel_dir()
    folder.mkdir()
    rows = [{"article": art.name, "status": "pending", "final_sha256": "old"},
            {"article": art.name, "status": "done"},
            {"article": art.name, "status": "pending", "final_sha256": "new"}]
    (folder / "pending_learn.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert [r["final_sha256"] for r in FW.pending_items()] == ["new"]
    FW.mark(art.name, "done")
    assert FW.pending_items() == []


def test_same_named_articles_do_not_settle_each_other(art, tmp_path):
    other = tmp_path / "another-root" / art.name
    other.mkdir(parents=True)
    (other / "定稿.md").write_text(DRAFT)
    for root in (art, other):
        FW.snapshot_ai_draft(root)
        queue_revision(root)
    pending = FW.pending_items()
    assert len(pending) == 2
    assert len({r["article_uid"] for r in pending}) == 2
    with pytest.raises(ValueError):
        FW.mark(art.name, "done")
    FW.mark(pending[0]["article_uid"], "done")
    assert [r["article_uid"] for r in FW.pending_items()] == [pending[1]["article_uid"]]


def test_queue_does_not_write_voice_corpus(art, monkeypatch):
    import profile_config
    voice = art / "private-profile" / "corpus" / "voice-samples.md"
    monkeypatch.setenv("SANSHENG_WRITE_PROFILE_DIR", str(voice.parent.parent))
    FW.snapshot_ai_draft(art)
    queue_revision(art)
    assert not voice.exists()


def test_capture_cli_uses_real_source_and_queue(tmp_path):
    import os
    import subprocess
    article = tmp_path / "article"
    article.mkdir()
    (article / "定稿.md").write_text(DRAFT)
    FW.snapshot_ai_draft(article)
    source = article / "author.md"
    source.write_text(FINAL)
    evidence = article / "request.md"
    evidence.write_text("作者明确交付手改原件并要求学习")
    env = {**os.environ, "SANSHENG_WRITE_PROFILE_DIR": str(tmp_path / "profile"),
           "SANSHENG_WRITE_WORKSPACE_DIR": str(tmp_path)}
    command = [sys.executable, str(ROOT / "scripts/flywheel_hooks.py"), "--dir", str(article),
               "capture-author", "--source", str(source), "--evidence", str(evidence),
               "--source-kind", "author-edited"]
    first = subprocess.run(command, capture_output=True, text=True, env=env)
    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    assert result["status"] == "pending"
    second = subprocess.run(command, capture_output=True, text=True, env=env)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "already_queued"
    assert Path(result["diff"]).is_file()


def test_capture_refuses_learning_directory_symlink_escape(art, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (art / "过程记录").mkdir()
    (art / "过程记录/learning").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        capture(art, FINAL)
    assert list(outside.iterdir()) == []


def test_mutation_of_digest_guard_breaks_consumer_rejection(art):
    """删除摘要校验后真实排队路径会接纳被篡改的样本，证明反例触达该门。"""
    import types
    FW.snapshot_ai_draft(art)
    receipt = capture(art, FINAL)
    (art / receipt["source_file"]).write_text("不是作者原件")
    assert FW.queue_learning(art)["status"] == "needs_author_evidence"
    code = Path(FW.__file__).read_text()
    guard = 'if _sha(path.read_bytes()) != receipt[key + "_sha256"]:'
    assert code.count(guard) == 1
    mutant = types.ModuleType("mutated_flywheel")
    mutant.__file__ = FW.__file__
    exec(compile(code.replace(guard, "if False:"), FW.__file__, "exec"), mutant.__dict__)
    mutant._flywheel_dir = FW._flywheel_dir
    assert mutant.queue_learning(art)["status"] == "pending"
