"""金句必须出自定稿原句（G3）；标题必须有「锚点：一句话」结构（G5）。2026-09-23 审计。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import contracts  # noqa: E402
import pipeline  # noqa: E402


def _article(tmp_path: Path, body: str) -> Path:
    art = tmp_path / "108-测试"
    art.mkdir()
    (art / "定稿.md").write_text(body, encoding="utf-8")
    return art


def test_golden_line_invented_for_the_gate_is_rejected(tmp_path):
    art = _article(tmp_path, "读得懂，要点却不在前面。\n")
    golden = tmp_path / "golden.md"
    golden.write_text("- 一个把上限往上推，一个把价格往下砍。 *(108-测试)*\n", encoding="utf-8")
    errors = pipeline._golden_line_errors(art, golden)
    assert errors and "不在定稿正文里" in errors[0]


def test_golden_line_with_only_quote_and_period_differences_passes(tmp_path):
    art = _article(tmp_path, "他说**读得懂**，要点却不在前面\n")
    golden = tmp_path / "golden.md"
    golden.write_text("- 「读得懂，要点却不在前面。」 *(108-测试)*\n", encoding="utf-8")
    assert pipeline._golden_line_errors(art, golden) == []


def test_missing_marker_is_rejected(tmp_path):
    art = _article(tmp_path, "正文\n")
    golden = tmp_path / "golden.md"
    golden.write_text("- 别篇的句子 *(107-别篇)*\n", encoding="utf-8")
    errors = pipeline._golden_line_errors(art, golden)
    assert errors and "缺本篇来源标记" in errors[0]


def test_title_without_two_parts_only_warns():
    # 2026-10-21 起「锚点：一句话」不再是硬结构；整句一段只提示补可得物
    result = contracts.audit_title_contract("分享 | 全网最好的初中英语学习网站（限时免费）")
    assert result["violations"] == []
    assert any("可得物" in w for w in result["warnings"])


def test_title_without_colon_but_with_takeaway_passes():
    result = contracts.audit_title_contract("分享 | 德鲁克 5 本书，整理成 3 条今天能用的管理规则")
    assert result["verdict"] == "ok", result["notes"]


def test_author_exemption_is_recorded_on_structure_hint(tmp_path):
    art = tmp_path / "103-推广"
    art.mkdir()
    (art / "article-meta.yaml").write_text('title: "分享 | 全网最好的初中英语学习网站（限时免费）"\n', encoding="utf-8")
    (art / "_blueprint-approval.md").write_text(
        "作者指定标题：分享 | 全网最好的初中英语学习网站（限时免费）\n标题公式豁免：推广篇沿用网站口号\n审批结论：通过\n",
        encoding="utf-8")
    result = contracts.verify_title_contract(str(art))
    assert result["violations"] == []
    assert any("已按审批记录豁免" in w for w in result["warnings"])


# ---------- 结尾落点（Q3）----------

def _closing_article(tmp_path, ending: str, closing_type: str = "硬切") -> Path:
    art = tmp_path / "105-测试"
    art.mkdir()
    (art / "定稿.md").write_text(f"# 标题\n\n## 一节\n\n正文。\n\n{ending}\n\n<!-- SANSHENG-DEEP-READ -->\n<section>卡片</section>\n", encoding="utf-8")
    (art / "article-meta.yaml").write_text(f'closing_type: "{closing_type}"\n', encoding="utf-8")
    return art


def _brand_with_rules(monkeypatch):
    monkeypatch.setattr(pipeline, "brand", lambda: {"writing": {
        "closing_types_allowed": ["自然断流", "硬切"], "closing_no_question_ending": True}})


def test_question_ending_is_rejected(tmp_path, monkeypatch):
    _brand_with_rules(monkeypatch)
    art = _closing_article(tmp_path, "判断的价格接近于零之后，人留下的是哪一种判断？")
    problems = pipeline._closing_rule_problems(art, (art / "定稿.md").read_text(encoding="utf-8"))
    assert problems and "问句收尾" in problems[0]


def test_action_ending_passes(tmp_path, monkeypatch):
    _brand_with_rules(monkeypatch)
    art = _closing_article(tmp_path, "我会先按这个分工派活，用做完率和账单决定默认。")
    assert pipeline._closing_rule_problems(art, (art / "定稿.md").read_text(encoding="utf-8")) == []


def test_disallowed_closing_type_is_rejected(tmp_path, monkeypatch):
    _brand_with_rules(monkeypatch)
    art = _closing_article(tmp_path, "先按分工派活。", closing_type="未答之问")
    problems = pipeline._closing_rule_problems(art, (art / "定稿.md").read_text(encoding="utf-8"))
    assert problems and "未答之问" in problems[0]


def test_no_profile_rule_means_no_check(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "brand", lambda: {})
    art = _closing_article(tmp_path, "还剩什么？")
    assert pipeline._closing_rule_problems(art, (art / "定稿.md").read_text(encoding="utf-8")) is None
