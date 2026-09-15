"""作者截图模式（infographic_mode: author-shots）。

守的东西：信息图 ≥4 的硬门可以由作者供图 ≥4 张兑现，但不能变成静默 skip——
供图不够、文件不存在、任务单里还列着信息图、素材里混进 infographic*.png，都要拦。
默认 generated 行为一个字不变。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import author_shots
from scripts.visual_workflow import validate_visual_plan

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _plan(with_items: bool) -> dict:
    plan = {
        "schema_version": 1,
        "cover": {"aspect_ratio": "2.35:1", "title": "T", "visual_facts": ["a"]},
        "hero": {"aspect_ratio": "1:1", "title": "H", "visual_facts": ["b"]},
        "infographics": [],
    }
    if with_items:
        plan["infographics"] = [
            {
                "id": "01", "position": "opening", "aspect_ratio": "9:16", "title": "x",
                "layout_type": "hub-spoke", "layout": "a clay scene", "anchor": "锚句。",
                "expected_text": ["甲"], "facts": ["f"],
            }
        ]
    return plan


def _article(tmp_path: Path, *, shots: int, mode: str = "author-shots") -> Path:
    article = tmp_path / "101-测试"
    (article / "素材" / "作者素材").mkdir(parents=True)
    (article / "article-meta.yaml").write_text(
        f"title: 测试\ninfographic_mode: {mode}\n", encoding="utf-8"
    )
    lines = ["# 测试", "", "正文第一段。", ""]
    for i in range(shots):
        (article / "素材" / "作者素材" / f"shot{i}.png").write_bytes(_PNG)
        lines += [f"![图{i}](素材/作者素材/shot{i}.png)", ""]
    (article / "定稿.md").write_text("\n".join(lines), encoding="utf-8")
    (article / "visual-plan.json").write_text(
        json.dumps(_plan(False), ensure_ascii=False), encoding="utf-8"
    )
    return article


def test_default_mode_still_requires_four_infographics():
    assert any("至少 4 张" in e for e in validate_visual_plan(_plan(False)))
    assert author_shots.infographic_mode({}) == "generated"


def test_author_shots_plan_must_have_empty_infographics():
    assert validate_visual_plan(_plan(False), infographic_mode="author-shots") == []
    errors = validate_visual_plan(_plan(True), infographic_mode="author-shots")
    assert any("必须为空" in e for e in errors)


def test_mode_value_is_validated():
    assert author_shots.mode_errors({"infographic_mode": "author-shots"}) == []
    assert author_shots.mode_errors({}) == []
    assert author_shots.mode_errors({"infographic_mode": "screenshots"})


def test_author_shot_refs_only_count_author_material_or_shot_prefix():
    md = (
        "![a](素材/作者素材/a.png)\n"
        "![b](素材/shot-b.png)\n"
        "![c](素材/infographic-01.png)\n"
        "![d](素材/hero.png)\n"
        '<img src="素材/作者素材/e.jpg">\n'
        "![a again](素材/作者素材/a.png)\n"
    )
    assert author_shots.author_shot_refs(md) == [
        "素材/作者素材/a.png", "素材/shot-b.png", "素材/作者素材/e.jpg"
    ]


def test_verify_author_shots_requires_four_existing_files(tmp_path):
    article = _article(tmp_path, shots=4)
    assert author_shots.verify_author_shots(article, (article / "定稿.md").read_text(encoding="utf-8")) == []

    three = _article(tmp_path / "three", shots=3)
    errors = author_shots.verify_author_shots(three, (three / "定稿.md").read_text(encoding="utf-8"))
    assert any("≥4 张作者供图" in e for e in errors)

    (article / "素材" / "作者素材" / "shot2.png").unlink()
    errors = author_shots.verify_author_shots(article, (article / "定稿.md").read_text(encoding="utf-8"))
    assert any("磁盘上不存在" in e for e in errors)


def test_pipeline_author_shots_gate_rejects_stray_infographics_and_listed_items(tmp_path):
    from scripts import pipeline

    article = _article(tmp_path, shots=5)
    assert pipeline._infographic_mode(article) == "author-shots"
    assert pipeline._author_shots_errors(article) == []

    (article / "素材" / "infographic-01.png").write_bytes(_PNG)
    assert any("infographic*.png" in e for e in pipeline._author_shots_errors(article))
    (article / "素材" / "infographic-01.png").unlink()

    (article / "visual-plan.json").write_text(
        json.dumps(_plan(True), ensure_ascii=False), encoding="utf-8"
    )
    assert any("仍列有 infographics" in e for e in pipeline._author_shots_errors(article))


def test_generated_mode_ignores_author_shots_gate(tmp_path):
    from scripts import pipeline

    article = _article(tmp_path, shots=0, mode="generated")
    assert pipeline._infographic_mode(article) == "generated"


def test_assemble_release_with_empty_plan_keeps_author_prose(tmp_path):
    from scripts.assemble_release import assemble_release_markdown, author_content_sha256

    article = _article(tmp_path, shots=4)
    before = (article / "定稿.md").read_text(encoding="utf-8")
    result, errors = assemble_release_markdown(article)
    assert errors == []
    assert result is not None
    after = (article / "定稿.md").read_text(encoding="utf-8")
    assert "SANSHENG-VISUAL-START" not in after
    assert author_content_sha256(after) == author_content_sha256(before)
