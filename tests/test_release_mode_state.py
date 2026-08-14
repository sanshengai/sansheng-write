"""release-from-final 模式下的状态处理（第 89 篇实跑修的两处）。

1. adopt-final 原本把**所有**阶段无差别重置成 pending。走完整流程的文章在
   adopt-final 之前，cover/infographic/bgm/layout/logo 往往已经 verify 通过、
   视觉字节也已 seal，一律清空等于逼人把五个阶段重验一遍 —— 实测白跑一轮。

2. 该模式下 outline 被标 adopted（不是 done），于是它后面每个 done 阶段都会刷
   一条「顺序异常，可能是手动 skip 残留」—— 实测一次刷 8 行，全是误报。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _article(tmp_path: Path) -> Path:
    art = tmp_path / "90-r"
    art.mkdir()
    (art / "定稿.md").write_text(
        "# 精选 | 标题\n\n" + "正文内容" * 500, encoding="utf-8"
    )
    (art / "article-meta.yaml").write_text(
        'title: "精选 | 标题"\ncategory: "OBS"\noutward_category: "picks"\n'
        'digest: "摘要"\ncover_style: montage-evidence\n'
        "infographic_style: claymation\nvisual_profile: warm-light-clay\n"
        'lead:\n  line1: "四个字"\n  line2: "副标题在这"\n  accent: "在这"\n'
        '  tag1: "标签"\n  tag2: "分类"\n',
        encoding="utf-8",
    )
    return art


def test_verified_downstream_stages_survive_adopt_final(tmp_path):
    """已 done 的视觉/排版阶段不该被 adopt-final 清空。"""
    import pipeline
    from release_job import adopt_final

    art = _article(tmp_path)
    pipeline.cmd_init(art)
    state = pipeline.load_state(art)
    for stage in ("cover", "infographic", "bgm", "layout", "logo"):
        state["stages"][stage] = {"status": "done"}
    pipeline.save_state(art, state)

    job, errors = adopt_final(art, art / "定稿.md", art / "article-meta.yaml")
    assert not errors, errors

    after = pipeline.load_state(art)["stages"]
    for stage in ("cover", "infographic", "bgm", "layout", "logo"):
        assert after[stage]["status"] == "done", f"{stage} 被无谓清空了"
        assert after[stage].get("carried_over_by") == "adopt-final"


def test_unverified_stages_stay_pending(tmp_path):
    """没验过的阶段不能被顺手标成 done。"""
    import pipeline
    from release_job import adopt_final

    art = _article(tmp_path)
    pipeline.cmd_init(art)

    adopt_final(art, art / "定稿.md", art / "article-meta.yaml")

    after = pipeline.load_state(art)["stages"]
    for stage in ("cover", "infographic", "bgm", "layout", "logo"):
        assert after[stage]["status"] == "pending"


def test_outline_and_writing_are_still_taken_over(tmp_path):
    """adopt-final 该接管的仍要接管。"""
    import pipeline
    from release_job import adopt_final

    art = _article(tmp_path)
    pipeline.cmd_init(art)
    adopt_final(art, art / "定稿.md", art / "article-meta.yaml")

    after = pipeline.load_state(art)["stages"]
    assert after["outline"]["status"] == "adopted"
    assert after["writing"]["status"] == "done"
    assert after["writing"]["source_mode"] == "author-provided-final"


def test_adopted_counts_as_completed_upstream(tmp_path):
    """adopted 是合法的「已了结」状态，不能让后面每个 done 都报顺序异常。

    这是第 89 篇刷出 8 行误报的直接原因：outline=adopted 不被认作已完成，
    于是它后面 8 个阶段挨个报一遍「可能是手动 skip 残留」。
    这里刻意**不设** mode，好让断言直接压在状态元组上（否则会被
    release-from-final 分支遮掉，单点变异打不红）。
    """
    import pipeline

    art = _article(tmp_path)
    pipeline.cmd_init(art)
    state = pipeline.load_state(art)
    state["stages"]["outline"] = {"status": "adopted"}
    for stage in ("writing", "cover", "infographic", "bgm", "layout", "logo"):
        state["stages"][stage] = {"status": "done"}
    pipeline.save_state(art, state)

    warnings = pipeline._cross_check(art, pipeline.load_state(art))
    bogus = [w for w in warnings if "顺序异常" in w]
    assert bogus == [], f"adopted 上游不该触发顺序异常：{bogus}"


def test_release_mode_names_the_actual_skipped_stage(tmp_path):
    """release-from-final 下真有 skip 时，要点名是哪个阶段，而不是甩一句通用猜测。"""
    import pipeline

    art = _article(tmp_path)
    pipeline.cmd_init(art)
    state = pipeline.load_state(art)
    state["mode"] = "release-from-final"
    state["stages"]["outline"] = {"status": "adopted"}
    state["stages"]["writing"] = {"status": "skip"}
    state["stages"]["bgm"] = {"status": "pending"}
    state["stages"]["layout"] = {"status": "done"}
    pipeline.save_state(art, state)

    warnings = pipeline._cross_check(art, pipeline.load_state(art))
    hits = [w for w in warnings if "layout=done" in w]
    assert hits, f"真 skip 仍要提醒：{warnings}"
    assert "release-from-final" in hits[0]
    assert "writing" in hits[0], f"要点名具体阶段：{hits[0]}"
    assert "手动 skip 残留" not in hits[0], "该模式不该用通用猜测文案"


def test_normal_mode_still_warns_on_real_gap(tmp_path):
    """常规模式下真的跳阶段仍要提醒。"""
    import pipeline

    art = _article(tmp_path)
    pipeline.cmd_init(art)
    state = pipeline.load_state(art)
    state["stages"]["outline"] = {"status": "pending"}
    state["stages"]["layout"] = {"status": "done"}
    pipeline.save_state(art, state)

    warnings = pipeline._cross_check(art, pipeline.load_state(art))
    assert any("前序阶段未完成" in w for w in warnings)
