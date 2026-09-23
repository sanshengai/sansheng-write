"""执行卡与源文档同步守护（2026-09-23 审计 E1）。

执行卡是从大文档提炼的：源章节一改、卡片还停在旧说法上，就会把 Agent 带偏。
这里既跑真实仓库的检查，也用临时目录构造反例，证明每一类漂移都会被拒绝。
"""
import json
from pathlib import Path

import pytest

from scripts import exec_cards

SOURCE = """# 写作

## 三条直球守则

结论先行。

## 句间引力

上句尾接下句头。

### 句间引力细则

顶真。
"""

CARD = "# 执行卡：示例\n\n- 结论先行（出处：writing.md §三条直球守则；writing.md §句间引力细则）。\n"


@pytest.fixture
def refs(tmp_path: Path) -> Path:
    (tmp_path / "writing.md").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "执行卡-示例.md").write_text(CARD, encoding="utf-8")
    assert exec_cards.refresh(tmp_path) == []
    assert exec_cards.check(tmp_path) == []
    return tmp_path


def test_real_cards_are_in_sync():
    """源章节改了就要回头复核卡片，复核完 `exec_cards.py refresh`。"""
    problems = exec_cards.check()
    assert problems == [], "\n".join(problems)


def test_parse_citations_splits_and_dedupes():
    text = "a（出处：a.md §甲；b.md §乙）b（出处：a.md §甲）"
    assert exec_cards.parse_citations(text) == [("a.md", "甲"), ("b.md", "乙")]


def test_section_stops_at_same_or_higher_heading(refs):
    text, problem = exec_cards.section_text(refs / "writing.md", "句间引力细则")
    assert not problem and text.startswith("### 句间引力细则") and "顶真" in text
    text, _ = exec_cards.section_text(refs / "writing.md", "三条直球守则")
    assert "句间引力" not in text


def test_changed_source_section_is_reported(refs):
    path = refs / "writing.md"
    path.write_text(SOURCE.replace("结论先行。", "结论先行，第一屏下判。"), encoding="utf-8")
    problems = exec_cards.check(refs)
    assert any("§三条直球守则 已改动" in p for p in problems)
    assert exec_cards.refresh(refs) == [] and exec_cards.check(refs) == []


def test_ambiguous_heading_is_rejected(refs):
    card = refs / "执行卡-示例.md"
    card.write_text(CARD.replace("§句间引力细则", "§句间引力"), encoding="utf-8")
    assert any("2 个标题含「句间引力」" in p for p in exec_cards.check(refs, digests=False))


def test_missing_heading_and_file_are_rejected(refs):
    card = refs / "执行卡-示例.md"
    card.write_text(CARD + "（出处：writing.md §不存在的节；nope.md §甲）\n", encoding="utf-8")
    problems = exec_cards.check(refs, digests=False)
    assert any("找不到标题含「不存在的节」" in p for p in problems)
    assert any("源文件不存在：nope.md" in p for p in problems)


def test_heading_inside_code_fence_does_not_count(refs):
    (refs / "writing.md").write_text(SOURCE + "\n```\n## 三条直球守则\n```\n", encoding="utf-8")
    assert exec_cards.check(refs, digests=False) == []


def test_word_cap_and_size_are_rejected(refs):
    card = refs / "执行卡-示例.md"
    card.write_text(CARD + "- 全文控制在 1500 字以内。\n", encoding="utf-8")
    assert any("全文字数限定" in p for p in exec_cards.check(refs, digests=False))
    card.write_text(CARD + "字" * 4000, encoding="utf-8")
    assert any("超过 10240" in p for p in exec_cards.check(refs, digests=False))


def test_stale_manifest_entry_is_reported(refs):
    manifest = json.loads((refs / exec_cards.MANIFEST.name).read_text(encoding="utf-8"))
    manifest["执行卡-示例.md"]["writing.md §已删除的节"] = "0" * 16
    (refs / exec_cards.MANIFEST.name).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    assert any("已不再引用" in p for p in exec_cards.check(refs))
