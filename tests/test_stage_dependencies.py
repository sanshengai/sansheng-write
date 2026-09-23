"""状态机按依赖标脏 + 任务单只绑定影响成稿的 meta（2026-09-23 审计 F2）。

一次实跑中：正文加一处粗体、meta 里填主题曲生成单要的 music 字段，逼着重新 adopt-final，
随后封面、配图、主题曲、排版、水印全部变脏；交接复制的「播客 | 标题.mp3」又把主题曲
阶段标脏，连带下游再来一轮。手动重验 9 次。
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts import pipeline
from scripts.evidence import stable_digest

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
        '  ghost: "RULE × GATE × PROOF"\n'
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
        cwd=cwd, text=True, encoding="utf-8", capture_output=True, check=False,
    )


# ---------- 依赖表 ----------

def test_writing_change_spares_cover_and_bgm():
    dependents = pipeline._dependent_stages("writing")
    assert "cover" not in dependents and "bgm" not in dependents
    assert {"layout", "publish", "archive"} <= set(dependents)


def test_invalidate_downstream_only_marks_real_dependents():
    state = {"stages": {name: {"status": "done"} for name in pipeline.STAGE_ORDER}}
    pipeline._invalidate_downstream(state, "writing", "正文改了")
    assert state["stages"]["cover"]["status"] == "done"
    assert state["stages"]["bgm"]["status"] == "done"
    assert state["stages"]["layout"]["status"] == "dirty"
    assert state["stages"]["publish"]["status"] == "dirty"


def test_outline_change_still_invalidates_everything():
    state = {"stages": {name: {"status": "done"} for name in pipeline.STAGE_ORDER}}
    pipeline._invalidate_downstream(state, "outline", "标题变了")
    assert all(state["stages"][name]["status"] == "dirty" for name in pipeline.STAGE_ORDER[1:])


# ---------- 主题曲阶段摘要只认音乐清单 ----------

def test_bgm_digest_ignores_handoff_copies(tmp_path):
    (tmp_path / "主题曲.mp3").write_bytes(b"theme-bytes")
    (tmp_path / "_music-manifest.json").write_text(json.dumps(
        {"schema_version": 1, "theme": {"playback": {"path": "主题曲.mp3"}}}), encoding="utf-8")
    before = pipeline._stage_artifact_digest(tmp_path, "bgm")
    (tmp_path / "播客 | 一篇文章.mp3").write_bytes(b"podcast-copy")
    (tmp_path / "音乐封面.png").write_bytes(b"cover")
    assert pipeline._stage_artifact_digest(tmp_path, "bgm") == before
    (tmp_path / "主题曲.mp3").write_bytes(b"new-theme-bytes")
    assert pipeline._stage_artifact_digest(tmp_path, "bgm") != before


# ---------- 封面阶段摘要：不认后处理补记，认封面文字 ----------

def _gen_log(article: Path, rows: list[dict]) -> None:
    (article / ".gen-log.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_cover_digest_ignores_postprocess_records(tmp_path):
    article = _article(tmp_path)
    render = {"stage": "cover", "output": "素材/cover.png", "record_id": "render-1",
              "output_sha256": "aaa", "producer": "sansheng-write.visual-planner"}
    _gen_log(article, [render])
    before = pipeline._stage_artifact_digest(article, "cover")
    post = dict(render, record_id="postprocess-1", output_sha256="bbb",
                post_process={"tool": "compress_images.py", "source_sha256": "aaa"})
    _gen_log(article, [render, post])
    assert pipeline._stage_artifact_digest(article, "cover") == before


def test_cover_digest_changes_when_cover_text_changes(tmp_path):
    article = _article(tmp_path)
    _gen_log(article, [{"stage": "cover", "output": "素材/cover.png", "record_id": "render-1",
                        "output_sha256": "aaa"}])
    before = pipeline._stage_artifact_digest(article, "cover")
    meta = article / "article-meta.yaml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("规则不能丢", "规则换了"), encoding="utf-8")
    assert pipeline._stage_artifact_digest(article, "cover") != before


# ---------- 任务单只绑定影响成稿的 meta ----------

def _append_music(article: Path) -> None:
    meta = article / "article-meta.yaml"
    meta.write_text(meta.read_text(encoding="utf-8")
                    + 'music:\n  style: "ethereal_folk"\n  gender: "male"\n  song_name: "测试歌"\n',
                    encoding="utf-8")


def test_music_fields_do_not_invalidate_release_job(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    _append_music(article)
    result = _run(article, "verify-release-job")
    assert result.returncode == 0, result.stdout + result.stderr


def test_title_change_still_invalidates_release_job(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    meta = article / "article-meta.yaml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("一篇已经确认的文章", "换了标题"), encoding="utf-8")
    result = _run(article, "verify-release-job")
    assert result.returncode != 0
    assert "article-meta已变化" in (result.stdout + result.stderr)


def test_legacy_job_without_meta_digest_keeps_whole_file_check(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "adopt-final").returncode == 0
    job_path = article / "_release-job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job.pop("meta_digest")
    subject = job["approval_evidence"]["subject"]
    subject.pop("meta_digest")
    job["approval_evidence"]["subject_digest"] = stable_digest(subject)
    job["job_digest"] = stable_digest({k: v for k, v in job.items() if k != "job_digest"})
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _run(article, "verify-release-job").returncode == 0
    _append_music(article)
    assert _run(article, "verify-release-job").returncode != 0
