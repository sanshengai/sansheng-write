# -*- coding: utf-8 -*-
"""process_table 路由 + 列宽测试。

2026-07-07 拍板的版式路由：
  - ≥3 列 → 缩 11px；一屏放得下 width:100% 不滚，放不下（≥4 列）overflow-x 横滑
  - 2 列「术语|释义」型 → 术语卡（左竖条，绕开表格）
  - 2 列对称数据 → 保留 12px 改良表

2026-09-15 改为 section 版 CSS 表（每行 display:table、每格 display:table-cell 带 width）：
  微信编辑器保存/发布会清掉 <td>/<th> 上的 width（3 篇线上文章核对 0 存活），
  而 section 上的 display:table-cell;width 原样存活。列宽按内容像素需求分配：
  短列只拿自己需要的宽，长列均摊折行。
"""
import os
import re
import importlib.util

SW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "format_layout", os.path.join(SW, "scripts", "format_layout.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)


def _table(rows_html, header):
    return (f'<div id="output"><table><thead>{header}</thead>'
            f'<tbody>{rows_html}</tbody></table></div>')


def _row_widths(out):
    """每个 sw-tr 行里各格的 width 序列（只看格子，不看行自身的 width）。"""
    result = []
    for chunk in out.split('<section class="sw-tr"')[1:]:
        cells = re.findall(r'<section class="sw-t[hd]"[^>]*>', chunk)
        result.append([re.search(r'width: ([0-9.]+(?:%|px))', c).group(1) for c in cells])
    return result


def _pct(w):
    return float(w.rstrip("%"))


def test_three_cols_shrink_to_11px_and_fit_100pct():
    """3 列（短内容）→ 11px + width:100% + overflow:hidden（放得下不横滑）。"""
    html = _table(
        "<tr><td>2025</td><td>Claude Code</td><td>终端 Agent</td></tr>"
        "<tr><td>2026</td><td>协作平台</td><td>团队协作</td></tr>",
        "<th>时间</th><th>产品</th><th>形态</th>")
    out = F.process_table(html)
    assert "font-size: 11px" in out
    assert "width: 100%" in out and "overflow: hidden" in out
    assert "overflow-x: auto" not in out


def test_four_cols_horizontal_scroll_only_when_it_does_not_fit():
    """4 列长内容 → 11px + overflow-x:auto + 每行固定 px 宽（放不下横滑）；
    4 列短内容 → 放得下就 100% 不横滑。"""
    html = _table(
        "<tr><td>Opus 4.8 Thinking</td><td>1M tokens</td><td>输入 15 美元/百万</td><td>最强推理，长上下文最稳</td></tr>"
        "<tr><td>Sonnet 5</td><td>200K tokens</td><td>输入 3 美元/百万</td><td>均衡快，日常首选</td></tr>",
        "<th>模型</th><th>上下文</th><th>价格</th><th>特点</th>")
    out = F.process_table(html)
    assert "overflow-x: auto" in out
    assert re.search(r'class="sw-tr" style="display: table; width: \d{3,}px', out), "每行应有固定 px 宽以触发横滑"
    assert "font-size: 11px" in out

    short = _table(
        "<tr><td>Opus</td><td>1M</td><td>较高</td><td>最强</td></tr>",
        "<th>模型</th><th>上下文</th><th>价格</th><th>特点</th>")
    out2 = F.process_table(short)
    assert "overflow-x: auto" not in out2 and "overflow: hidden" in out2


def test_two_col_term_table_becomes_cards():
    """2 列「术语|长释义」→ 术语卡（左竖条），不是表。"""
    html = _table(
        "<tr><td><strong>Agent</strong></td>"
        "<td>能自主规划并调用工具完成多步任务的 AI 系统，区别于一问一答的对话模型。</td></tr>"
        "<tr><td><strong>MCP</strong></td>"
        "<td>模型上下文协议，让模型以统一方式接入外部工具与数据源，是当下事实标准。</td></tr>",
        "<th>术语</th><th>说明</th>")
    out = F.process_table(html)
    assert "<table" not in out and 'class="sw-table"' not in out, "术语表应转卡片"
    assert "border-left: 3px solid #2F6F8F" in out
    # 术语标题剥掉冗余 <strong>（<p> 已加粗）
    assert "<strong>Agent</strong>" not in out
    assert ">Agent<" in out


def test_two_col_symmetric_data_keeps_table():
    """2 列对称数据（右列短）→ 保留 12px 改良表，不转卡。"""
    html = _table(
        "<tr><td>Q1</td><td>1.2 亿</td></tr>"
        "<tr><td>Q2</td><td>1.8 亿</td></tr>",
        "<th>季度</th><th>营收</th>")
    out = F.process_table(html)
    assert 'class="sw-table"' in out and "border-left: 3px solid" not in out
    assert "font-size: 12px" in out


def test_no_table_tags_survive_and_widths_live_on_section_cells():
    """🔴 微信会清掉 td/th 的 width：输出里不得再有 <table>/<td>/<th>，
    列宽必须写在 display:table-cell 的 section 上，且每一行都写（各行各自成表才对齐）。"""
    html = _table(
        "<tr><td>停</td><td>把开机广告和常驻推送的服务停掉，重启后不再自启</td><td>437 MB</td></tr>"
        "<tr><td>留</td><td>系统输入法、遥控器服务</td><td>0</td></tr>",
        "<th>动作</th><th>说明</th><th>结果</th>")
    out = F.process_table(html)
    assert not re.search(r"<(table|thead|tbody|tr|td|th)[\s>]", out)
    rows = _row_widths(out)
    assert len(rows) == 3, rows
    assert rows[0] == rows[1] == rows[2], "各行列宽必须一致"
    assert all(re.search(r'display: table-cell; [^"]*width: ', c) for c in re.findall(r'<section class="sw-t[hd]"[^>]*>', out))
    assert "display: table-cell; width:" not in out, "不得撞上导读栏检测签名"


def test_widths_follow_content_short_column_stays_narrow():
    """列宽跟内容走：一字列（停/留）只拿自己需要的宽，长文列拿走大头；
    放得下的表按需求比例分。"""
    html = _table(
        "<tr><td>停</td><td>把开机广告和常驻推送的服务停掉，重启后不再自启，内存立刻多出来</td><td>437 MB</td></tr>"
        "<tr><td>留</td><td>系统输入法、遥控器服务</td><td>0</td></tr>",
        "<th>动作</th><th>说明</th><th>结果</th>")
    w = [_pct(x) for x in _row_widths(F.process_table(html))[0]]
    assert w[0] < 16 and w[2] < 22 and w[1] > 60, w
    assert abs(sum(w) - 100) < 0.2

    fits = _table("<tr><td>Q1</td><td>1.2 亿</td></tr>", "<th>季度</th><th>营收</th>")
    w2 = [_pct(x) for x in _row_widths(F.process_table(fits))[0]]
    assert 35 < w2[0] < 65, w2  # 两列都很短：按需求比例分，不会被压成极端


def test_table_widths_override_wins():
    """article-meta 的 table_widths 覆盖优先于脚本估算，并按文中顺序消费。"""
    html = _table("<tr><td>Q1</td><td>1.2 亿</td></tr>", "<th>季度</th><th>营收</th>")
    out = F.process_table(html, table_widths=[[30, 70]])
    assert _row_widths(out)[0] == ["30%", "70%"]


def test_baoyu_wrapped_scroll_table_single_wrapper():
    """🔴 回归(55号真机)：baoyu 用 <section ...overflow:auto> 包住表 → 只能有 1 层
    border-radius 容器，不得二次包裹成双边框。"""
    baoyu = ('<div id="output"><section style="font-family: PingFang SC, Microsoft YaHei; '
             'font-size: 16px; line-height: 1.75; text-align: left; max-width: 100%; overflow: auto;">'
             '<table class="preview-table"><thead>'
             '<th>模型</th><th>上下文</th><th>价格</th><th>特点</th></thead><tbody>'
             '<tr><td>Opus 4.8 Thinking</td><td>1M tokens</td><td>输入 15 美元/百万</td><td>最强推理，长上下文最稳</td></tr>'
             '<tr><td>Sonnet 5</td><td>200K tokens</td><td>输入 3 美元/百万</td><td>均衡快，日常首选</td></tr>'
             '</tbody></table></section></div>')
    out = F.process_table(baoyu)
    assert out.count("border-radius: 10px") == 1, "横滑表被双层包裹（双边框）"
    assert out.count("overflow-x: auto") == 1
    assert 'margin: 0 8px 0.8em;"><section style="border-radius: 10px' not in out


def test_baoyu_wrapped_fit_table_single_wrapper():
    """放得下的 2 列/短 3 列表(overflow:hidden 分支)经 baoyu wrapper 也只 1 层容器。"""
    baoyu = ('<div id="output"><section style="font-family: X; font-size: 16px; '
             'line-height: 1.75; max-width: 100%; overflow: auto;">'
             '<table class="preview-table"><thead><th>季度</th><th>营收</th></thead>'
             '<tbody><tr><td>Q1</td><td>1.2 亿</td></tr>'
             '<tr><td>Q2</td><td>1.8 亿</td></tr></tbody></table></section></div>')
    out = F.process_table(baoyu)
    assert out.count("border-radius: 10px") == 1


def test_process_table_is_idempotent():
    html = _table("<tr><td>Q1</td><td>1.2 亿</td></tr>", "<th>季度</th><th>营收</th>")
    once = F.process_table(html)
    assert F.process_table(once) == once


def test_pure_fixtures_match_frozen_baseline():
    """两个 process_table _pure fixture（3列 + 术语卡）须与冻结 expected 逐行一致。"""
    pure = os.path.join(SW, "tests", "golden", "_pure")
    for stem in ("process_table", "process_table_term"):
        src = open(os.path.join(pure, f"{stem}.in.html"), encoding="utf-8").read()
        exp = open(os.path.join(pure, f"{stem}.expected.html"), encoding="utf-8").read()
        assert F.process_table(src).splitlines() == exp.splitlines(), \
            f"{stem} 输出偏离冻结基线"
