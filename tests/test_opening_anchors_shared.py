"""开篇重点标识：预检与排版门共用一个判据（2026-09-23 审计 G2）。

第 108 篇首段中英数字混排，汉字不足 40 个：旧预检只数汉字所以跳过，排版门按总字符
算才拦下。反例就用那一段原文。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import contracts  # noqa: E402

MIXED = ("北京时间 9 月 23 日 0 点 31 分，Anthropic 发布 Claude Opus 5.5。1 小时 41 分钟后，"
         "2 点 12 分，OpenAI 发布 GPT-6 Sol，同时发了小一号的 GPT-6 Luna。")


def _doc(opening: str) -> str:
    return f"---\ntitle: t\n---\n\n{opening}\n\n## 第一节\n\n正文。\n"


def test_mixed_script_paragraph_without_anchor_is_flagged():
    result = contracts.audit_opening_anchors(_doc(MIXED))
    assert result["naked"], "中英数字混排的实质段必须计入"
    assert any("开篇重点标识硬门" in e for e in result["errors"])


def test_anchored_paragraph_passes_presence_gate():
    anchored = MIXED.replace("Claude Opus 5.5", "**Claude Opus 5.5**").replace("GPT-6 Sol，", "**GPT-6 Sol**，")
    result = contracts.audit_opening_anchors(_doc(anchored))
    assert result["naked"] == []


def test_density_gate_needs_one_anchor_per_120_chars():
    long_para = "**开头**" + "这是一段足够长的开篇说明文字，用来测试比例密度门是否生效。" * 12
    result = contracts.audit_opening_anchors(_doc(long_para))
    assert any("密度门" in e for e in result["errors"])


def test_captions_tables_and_images_are_not_paragraphs():
    opening = "![图](a.png)\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<p>图注：来源某某官方发布页，这一行不是正文段落也不该被算进去</p>"
    assert contracts.audit_opening_anchors(_doc(opening))["errors"] == []


def test_preflight_and_format_layout_call_the_shared_function():
    root = Path(__file__).resolve().parents[1] / "scripts"
    for name in ("pipeline.py", "format_layout.py"):
        assert "audit_opening_anchors(" in (root / name).read_text(encoding="utf-8"), name
