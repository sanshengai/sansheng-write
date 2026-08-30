import json
import subprocess
import sys
from pathlib import Path

from scripts import pipeline
from scripts.evidence import sha256_file


PIPELINE = Path(pipeline.__file__).resolve()


def _article(tmp_path: Path) -> Path:
    article = tmp_path / "88-release-fixture"
    article.mkdir()
    (article / "定稿.md").write_text(
        "---\n"
        'title: "教程 | 一篇已经确认的文章"\n'
        'description: "这是给发布链使用的摘要。"\n'
        "---\n\n"
        "# 教程 | 一篇已经确认的文章\n\n"
        + "这是作者已经审定的正文内容。它只需要进入发布后端，不应重新经历大纲和写作流程。\n" * 80,
        encoding="utf-8",
    )
    (article / "article-meta.yaml").write_text(
        'title: "教程 | 一篇已经确认的文章"\n'
        'category: "TUT"\n'
        'outward_category: "tutorial"\n'
        'tags: ["AI工具"]\n'
        'digest: "这是给发布链使用的摘要。"\n'
        'lead:\n'
        '  line1: "规则不能丢"\n'
        '  line2: "发布链也要稳"\n'
        '  accent: "也要稳"\n'
        '  subtitle: "文章导读"\n'
        '  tag1: "硬门"\n'
        '  tag2: "证据"\n'
        'cover_style: "montage-evidence"\n'
        'infographic_subject: "ai-product"\n'
        'infographic_style: "claymation"\n'
        'visual_profile: "warm-light-clay"\n',
        encoding="utf-8",
    )
    (article / "_draft-approval.md").write_text(
        "# 定稿闸 · 作者拍板\n\n审批结论：通过\n作者意见：按这版进入发布链。\n",
        encoding="utf-8",
    )
    return article


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIPELINE), *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_adopt_final_creates_bound_release_job_and_state(tmp_path):
    article = _article(tmp_path)

    result = _run(article, "adopt-final")

    assert result.returncode == 0, result.stdout + result.stderr
    job = json.loads((article / "_release-job.json").read_text(encoding="utf-8"))
    state = pipeline.load_state(article)
    assert job["scope"] == "wechat-draft"
    assert job["final_path"] == "定稿.md"
    assert job["final_sha256"] == sha256_file(article / "定稿.md")
    assert job["meta_sha256"] == sha256_file(article / "article-meta.yaml")
    assert job["schema_version"] == 3
    assert job["approval_evidence"]["sha256"] == sha256_file(
        article / "_draft-approval.md"
    )
    assert job["approval_evidence"]["subject"]["title"] == (
        "教程 | 一篇已经确认的文章"
    )
    assert state["mode"] == "release-from-final"
    assert state["stages"]["outline"]["status"] == "adopted"
    assert state["stages"]["writing"]["status"] == "done"
    assert state["stages"]["writing"]["source_mode"] == "author-provided-final"
    checkpoint = json.loads(
        (article / "_checkpoint-receipts.json").read_text(encoding="utf-8")
    )
    assert checkpoint["checkpoints"]["draft"]["source_mode"] == "author-provided-final"
    assert checkpoint["checkpoints"]["draft"]["approval_evidence"] == job["approval_evidence"]


def test_adopt_final_requires_real_approval_and_invalid_cases_write_nothing(tmp_path):
    """缺失/拒绝/待确认都不能让 adopt-final 制造任何运行凭证。"""
    for suffix, approval_text in (
        ("missing", None),
        ("rejected", "审批结论：拒绝\n"),
        ("pending", "审批结论：尚未确认\n"),
    ):
        case_root = tmp_path / suffix
        case_root.mkdir()
        article = _article(case_root)
        approval = article / "_draft-approval.md"
        if approval_text is None:
            approval.unlink()
        else:
            approval.write_text(approval_text, encoding="utf-8")

        result = _run(article, "adopt-final")

        assert result.returncode == 2, result.stdout + result.stderr
        assert "不得" in result.stdout or "有效通过" in result.stdout
        assert not (article / ".state.json").exists()
        assert not (article / "_release-job.json").exists()
        assert not (article / "_checkpoint-receipts.json").exists()


def test_invalid_approval_preserves_existing_runtime_bytes(tmp_path):
    article = _article(tmp_path)
    (article / "_draft-approval.md").write_text("审批结论：拒绝\n", encoding="utf-8")
    sentinels = {
        article / ".state.json": b'{"sentinel":"state"}',
        article / "_release-job.json": b'{"sentinel":"job"}',
        article / "_checkpoint-receipts.json": b'{"sentinel":"receipt"}',
    }
    for path, payload in sentinels.items():
        path.write_bytes(payload)

    result = _run(article, "adopt-final")

    assert result.returncode == 2
    for path, payload in sentinels.items():
        assert path.read_bytes() == payload


def test_adopt_final_preserves_approval_bytes_and_rejects_later_drift(tmp_path):
    article = _article(tmp_path)
    approval = article / "_draft-approval.md"
    before = approval.read_bytes()

    assert _run(article, "adopt-final").returncode == 0
    assert approval.read_bytes() == before

    approval.write_text("审批结论：通过\n但这不是原来的拍板记录。\n", encoding="utf-8")
    result = _run(article, "verify-release-job")
    assert result.returncode == 2
    assert "审批证据已变化" in result.stdout


def test_adopt_final_rejects_title_drift_without_writing_state(tmp_path):
    article = _article(tmp_path)
    meta = article / "article-meta.yaml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            "教程 | 一篇已经确认的文章", "教程 | 另一标题", 1
        ),
        encoding="utf-8",
    )

    result = _run(article, "adopt-final")

    assert result.returncode == 2
    assert "标题" in result.stdout
    assert not (article / ".state.json").exists()
    assert not (article / "_release-job.json").exists()


def test_release_job_invalidates_when_final_changes(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    (article / "定稿.md").write_text(
        (article / "定稿.md").read_text(encoding="utf-8") + "\n发布后又改了。\n",
        encoding="utf-8",
    )

    result = _run(article, "verify-release-job")

    assert result.returncode == 2
    assert "定稿" in result.stdout and "变化" in result.stdout


def test_release_job_allows_only_registered_machine_assembly_blocks(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    draft = article / "定稿.md"
    original = draft.read_text(encoding="utf-8")
    draft.write_text(
        original
        + "\n<!-- SANSHENG-VISUAL-START:01 -->\n"
        + "![先锁定输入](素材/infographic-01.png)\n"
        + "<!-- SANSHENG-VISUAL-END:01 -->\n"
        + "\n<!-- AUDIO-CARD-START -->\n"
        + "<section>🎵 本文主题曲</section>\n"
        + "<!-- AUDIO-CARD-END -->\n",
        encoding="utf-8",
    )

    result = _run(article, "verify-release-job")

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_check_rebinds_machine_assembly_without_resetting_stages(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    draft = article / "定稿.md"
    draft.write_text(
        draft.read_text(encoding="utf-8")
        + "\n<!-- SANSHENG-VISUAL-START:01 -->\n"
        + "![先锁定输入](素材/infographic-01.png)\n"
        + "<!-- SANSHENG-VISUAL-END:01 -->\n",
        encoding="utf-8",
    )
    # release-check 还会跑完整发布硬门；这里仅测底层重绑定不会重置作者接管状态。
    from scripts.release_job import rebind_release_job

    job, changed, errors = rebind_release_job(article)

    assert errors == []
    assert changed is True
    assert job["final_sha256"] == sha256_file(draft)
    assert job.get("rebound_at")
    state = pipeline.load_state(article)
    assert state["stages"]["writing"]["status"] == "done"


def test_release_rebind_refuses_author_body_drift(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    draft = article / "定稿.md"
    draft.write_text(
        draft.read_text(encoding="utf-8").replace("作者已经审定", "作者又改写", 1),
        encoding="utf-8",
    )
    from scripts.release_job import rebind_release_job

    job, changed, errors = rebind_release_job(article)

    assert job is None
    assert changed is False
    assert any("作者正文" in error for error in errors)


def test_release_job_rejects_body_drift_even_when_machine_blocks_exist(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    draft = article / "定稿.md"
    original = draft.read_text(encoding="utf-8")
    draft.write_text(
        original.replace("这是作者已经审定的正文内容", "这是被偷偷改写的正文内容", 1)
        + "\n<!-- SANSHENG-VISUAL-START:01 -->\n"
        + "![先锁定输入](素材/infographic-01.png)\n"
        + "<!-- SANSHENG-VISUAL-END:01 -->\n",
        encoding="utf-8",
    )

    result = _run(article, "verify-release-job")

    assert result.returncode == 2
    assert "作者正文" in result.stdout or "变化" in result.stdout


def test_author_provided_final_checkpoint_does_not_forge_writing_review_files(tmp_path):
    article = _article(tmp_path)

    assert _run(article, "adopt-final").returncode == 0

    assert not (article / "_fact-check.md").exists()
    assert not (article / "_stutter-list.md").exists()
    assert not (article / "_draft-qc.md").exists()
    assert pipeline._checkpoint_errors("writing", article) == []
