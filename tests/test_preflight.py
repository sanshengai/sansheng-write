"""`pipeline.py preflight`：把静态检查前移。

2026-08-14 第 89 篇实跑账本：verify_publish 反复 8 轮、verify_layout 6 轮、
format_layout 4 轮。逐条复盘发现，卡住的东西全是**纯静态检查**，却被放在链条
末端 —— 金句库缺来源标记要等到 finalize 才报，迟了整整五个阶段。

每迟报一个阶段 = 一次「回头改 → 重跑中间所有步骤」。本命令把它们集中到一个
不花任何配额的检查里。

本文件用**那一篇真实缺过的东西**做用例。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest  # noqa: E402

from pipeline import _preflight_checks  # noqa: E402


@pytest.fixture(autouse=True)
def _both_checkpoints_on(monkeypatch):
    """闸门锚点检查依赖 profile 配置；测试里固定成双闸开，与 sandy profile 一致。"""
    import profile_config

    monkeypatch.setattr(
        profile_config, "workflow_checkpoints", lambda: ["blueprint", "draft"]
    )


@pytest.fixture(autouse=True)
def _isolated_golden_lines(tmp_path_factory, monkeypatch):
    """金句库指向临时文件，避免测试文章被真实库判缺来源标记。"""
    import profile_config

    gl = tmp_path_factory.mktemp("gl") / "金句库.md"
    gl.write_text("# 金句库\n\n- 一句话 *(90-t)*\n", encoding="utf-8")
    monkeypatch.setattr(profile_config, "golden_lines_file", lambda: str(gl))


def _article(tmp_path: Path, **kw) -> Path:
    """造一篇「除指定缺陷外都合规」的文章目录。"""
    art = tmp_path / "90-t"
    art.mkdir()

    body = kw.get("body")
    if body is None:
        body = (
            "# 精选 | 标题\n\n"
            "**8 月这三天**，连着出了四个大模型，这一段要够四十个中文字才会被"
            "当成实质段落来检查重点标识。\n\n"
            "## 第一节\n\n" + "正文内容" * 300 + "\n"
        )
    (art / "定稿.md").write_text(body, encoding="utf-8")

    (art / "article-meta.yaml").write_text(
        'title: "精选 | 标题"\npart_subtitles:\n  - "副标"\n'
        "endmatter:\n  deep_read: false\n  sources: false\n",
        encoding="utf-8",
    )
    for name in kw.get("files", ["_blueprint-approval.md", "_draft-approval.md",
                                 "_draft-qc.md", "_opening-choice.md"]):
        (art / name).write_text("通过\n", encoding="utf-8")
    return art


def _levels(results, name_part):
    return [lv for lv, name, _ in results if name_part in name]


def test_missing_draft_qc_is_caught_early(tmp_path):
    """真实case：这个文件此前要等 approve draft 才报。"""
    art = _article(tmp_path, files=["_blueprint-approval.md", "_draft-approval.md",
                                    "_opening-choice.md"])
    assert "fail" in _levels(_preflight_checks(art), "_draft-qc.md")


def test_missing_opening_choice_is_caught_early(tmp_path):
    """真实case：此前要等 done writing 才警告。"""
    art = _article(tmp_path, files=["_blueprint-approval.md", "_draft-approval.md",
                                    "_draft-qc.md"])
    assert "fail" in _levels(_preflight_checks(art), "_opening-choice.md")


def test_naked_opening_paragraph_is_caught_early(tmp_path):
    """真实case：开篇标识不足此前要等**排版阶段**才报，迟三个阶段。"""
    body = (
        "# 精选 | 标题\n\n"
        "这一段有四十个以上的中文字符但是完全没有任何重点标识存在于其中，"
        "所以它应该被预检当场抓出来而不是等到排版阶段。\n\n"
        "## 第一节\n\n" + "正文内容" * 300 + "\n"
    )
    art = _article(tmp_path, body=body)
    assert "fail" in _levels(_preflight_checks(art), "开篇重点标识")


def test_marked_opening_passes(tmp_path):
    assert "fail" not in _levels(_preflight_checks(_article(tmp_path)), "开篇重点标识")


def test_deep_read_required_when_enabled(tmp_path):
    """真实case：文末模块此前也要等排版才报。"""
    art = _article(tmp_path)
    (art / "article-meta.yaml").write_text(
        'title: "精选 | 标题"\npart_subtitles:\n  - "副标"\n'
        "endmatter:\n  deep_read: true\n  sources: false\n",
        encoding="utf-8",
    )
    assert "fail" in _levels(_preflight_checks(art), "DEEP READ")


def test_sources_required_when_factcheck_exists(tmp_path):
    """sources: auto + 有事实复核 → 必须有 SOURCES 模块。"""
    art = _article(tmp_path)
    (art / "_fact-check.md").write_text("核了 58 条\n", encoding="utf-8")
    (art / "article-meta.yaml").write_text(
        'title: "精选 | 标题"\npart_subtitles:\n  - "副标"\n'
        "endmatter:\n  deep_read: false\n  sources: auto\n",
        encoding="utf-8",
    )
    assert "fail" in _levels(_preflight_checks(art), "SOURCES")


def test_visual_plan_problems_surface_here(tmp_path):
    """任务单问题应在预检暴露，而不是渲完 45 张图之后。"""
    import json

    art = _article(tmp_path)
    plan = {
        "schema_version": 1,
        "cover": {"aspect_ratio": "2.35:1", "title": "封面", "visual_facts": ["一件物证"]},
        "hero": {"aspect_ratio": "1:1", "title": "主视觉", "visual_facts": ["一个主体"]},
        "infographics": [{
            "id": "01", "position": "opening", "aspect_ratio": "9:16",
            "title": "走量的和攻坚的",          # 含下面两个标签 → 必被抓
            "layout_type": "binary-comparison",
            "layout": "Two zones with no plate and no punctuation",  # 否定式 → 必被抓
            "anchor": "锚句",
            "expected_text": ["走量", "攻坚"],
            "facts": ["一条事实"],
        }],
    }
    (art / "visual-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )
    assert "fail" in _levels(_preflight_checks(art), "visual-plan.json")


def test_clean_article_passes(tmp_path):
    """全合规时不该有 fail —— 否则预检会变成狼来了。"""
    results = _preflight_checks(_article(tmp_path))
    fails = [(n, d) for lv, n, d in results if lv == "fail"]
    assert fails == [], f"干净文章不应有 fail：{fails}"


def test_missing_draft_short_circuits(tmp_path):
    art = tmp_path / "91-t"
    art.mkdir()
    results = _preflight_checks(art)
    assert "fail" in _levels(results, "定稿.md")
