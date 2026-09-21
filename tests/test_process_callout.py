"""process_callout：普通 `>` 引用块 → 重点段强调卡 / 带出处行 → 金句卡（2026-09-22）。"""
import re

from scripts.format_layout import process_callout

BQ = ('<blockquote class="blockquote" style="padding: 1em; border-left: 4px solid #2F6F8F; '
      'background: #f7f7f7;"><p class="p" style="letter-spacing: 0.1em;">{}</p></blockquote>')


def test_plain_paragraph_becomes_callout():
    html = BQ.format("这一整段是作者结论，需要读者停下来看。")
    out = process_callout(html)
    assert "<blockquote" not in out
    assert out.count("<!-- CALLOUT -->") == 1
    assert "border-left:4px solid" in out and "border-radius:0 10px 10px 0" in out
    assert "font-weight:700" not in out            # 重点段不加粗
    assert "这一整段是作者结论" in out


def test_attribution_line_becomes_quote_card():
    html = BQ.format("教育的目的是培养独立思考的人。<br>-- 爱因斯坦")
    out = process_callout(html)
    assert out.count("<!-- QUOTE_CARD -->") == 1 and "<!-- CALLOUT -->" not in out
    assert "font-weight:700" in out                 # 引文加粗
    assert re.search(r'text-align:right[^>]*>-- 爱因斯坦</section>', out)


def test_lead_and_list_blocks_untouched():
    lead = BQ.format("<strong>导读：</strong> 这篇讲什么。")
    lst = '<blockquote><p><strong>核心结论</strong></p><ul><li>a</li></ul></blockquote>'
    out = process_callout(lead + lst)
    assert out.count("<blockquote") == 2
    assert "<!-- CALLOUT -->" not in out


def test_idempotent():
    html = BQ.format("重点段。") + BQ.format("金句。<br>-- 出处")
    once = process_callout(html)
    assert process_callout(once) == once
