import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from contracts import verify_no_bare_url
from format_layout import process_endmatter_url_cards


def test_source_link_becomes_wrapping_card_without_changing_link(tmp_path):
    url = "https://example.com/" + "long-path-" * 30
    raw = f'<!-- SANSHENG-SOURCES --><section><section><a href="{url}">{url}</a></section></section>'
    path = tmp_path / "article.html"
    path.write_text(raw)
    assert verify_no_bare_url(str(path))["verdict"] == "fail"
    rendered = process_endmatter_url_cards(raw)
    path.write_text(rendered)
    assert verify_no_bare_url(str(path))["verdict"] == "ok"
    assert rendered.count(url) == 2
    assert 'text-align:left' in rendered
    assert 'word-break:break-all' in rendered
    assert process_endmatter_url_cards(rendered) == rendered


def test_plain_body_urls_are_still_rejected(tmp_path):
    raw = '<section>https://example.com/path</section><!-- SANSHENG-SOURCES --><section>来源</section>'
    assert process_endmatter_url_cards(raw) == raw
    path = tmp_path / "article.html"
    path.write_text(process_endmatter_url_cards(raw))
    assert verify_no_bare_url(str(path))["verdict"] == "fail"


def test_empty_and_unmarked_or_mismatched_links_are_unchanged():
    for raw in ['', '<section><a href="https://example.com/a">https://example.com/a</a></section>',
                '<!-- SANSHENG-SOURCES --><section><a href="https://example.com/a">https://example.com/b</a></section>']:
        assert process_endmatter_url_cards(raw) == raw
