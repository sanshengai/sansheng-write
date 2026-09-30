"""Converter-loss repair uses source context, never guesses missing prose."""
from scripts.format_layout import repair_missing_nested_emphasis


def test_exact_unique_source_restores_nested_emphasis_idempotently():
    source='这件事的意义——***第三方买不到的视角***。'
    damaged='<p class="p">这件事的意义——<em style="font-style:italic;"></em>。</p>'
    fixed=repair_missing_nested_emphasis(damaged,source)
    assert fixed=='<p class="p">这件事的意义——<em style="font-style:italic;"><strong>第三方买不到的视角</strong></em>。</p>'
    assert repair_missing_nested_emphasis(fixed,source)==fixed


def test_wrong_or_ambiguous_context_and_empty_source_are_not_rewritten():
    damaged='<p>甲<em></em>乙</p>'
    for source in ['', '丙***缺失词***丁', '甲***[链接](https://example.com)***乙']:
        assert repair_missing_nested_emphasis(damaged,source)==damaged
    assert repair_missing_nested_emphasis(damaged+damaged,'甲***缺失词***乙')==damaged+damaged


def test_nonempty_emphasis_and_literal_html_are_preserved():
    html='<p>甲<em>真实作者文字</em>乙</p>'
    assert repair_missing_nested_emphasis(html,'甲***不同文字***乙')==html
    empty='<p>甲<em></em>乙</p>'
    assert repair_missing_nested_emphasis(empty,'甲***<script>bad</script>***乙')==empty
