from pathlib import Path
from types import SimpleNamespace

from scripts.assemble_release import strip_machine_assembly
from scripts.audio_cards import marker_count, render_card, upsert_card
from scripts.format_layout import LEAD_END_MARKER, process_lead


def test_dual_cards_are_same_level_ordered_and_idempotent(tmp_path: Path):
    final = tmp_path / "定稿.md"
    final.write_text("# 标题\n\n导读。\n\n正文。\n", encoding="utf-8")

    assert upsert_card(final, "podcast", "AI 生成 · 双主持") is True
    assert upsert_card(final, "theme", "原创 · 3 分 20 秒") is True
    first = final.read_text(encoding="utf-8")

    assert marker_count(first, "theme") == 1
    assert marker_count(first, "podcast") == 1
    assert first.index("<!-- AUDIO-CARD-START -->") < first.index(
        "<!-- PODCAST-CARD-START -->"
    )
    assert 'data-audio-role="theme"' in first
    assert 'data-audio-role="podcast"' in first
    assert "🎵" in first and "阅读配乐｜本文主题曲" in first
    assert "🎧" in first and "音频版本｜本期播客" in first

    assert upsert_card(final, "theme", "原创 · 3 分 20 秒") is False
    assert upsert_card(final, "podcast", "AI 生成 · 双主持") is False
    assert final.read_text(encoding="utf-8") == first


def test_machine_audio_cards_do_not_change_author_source_digest(tmp_path: Path):
    final = tmp_path / "定稿.md"
    author_text = "# 标题\n\n导读。\n\n正文。\n"
    final.write_text(author_text, encoding="utf-8")
    upsert_card(final, "theme", "原创")
    upsert_card(final, "podcast", "AI 生成")

    assert strip_machine_assembly(final.read_text(encoding="utf-8")) == author_text


def test_layout_places_both_cards_after_lead_before_body(tmp_path: Path):
    (tmp_path / "素材").mkdir()
    (tmp_path / "素材/hero.png").write_bytes(b"hero")
    html = (
        '<html><body><div id="output"><p>正文第一段</p>'
        + render_card("podcast", "AI 生成")
        + render_card("theme", "原创")
        + "</div></body></html>"
    )

    result = process_lead(html, tmp_path, SimpleNamespace())

    lead_end = result.index(LEAD_END_MARKER)
    theme = result.index("<!-- AUDIO-CARD-START -->")
    podcast = result.index("<!-- PODCAST-CARD-START -->")
    body = result.index("正文第一段")
    assert lead_end < theme < podcast < body
