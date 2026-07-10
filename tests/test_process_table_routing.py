# -*- coding: utf-8 -*-
"""process_table 2026-07-07 路由测试：多列→11px横滑 / 2列术语→术语卡 / 2列数据→改良表。

拍板锁定的版式规格（草稿箱实测确认）：
  - ≥3 列 → 缩 11px；一屏放得下 width:100% 不滚，放不下 overflow-x 横滑
  - 2 列「术语|释义」型 → 术语卡（左竖条，绕开表格）
  - 2 列对称数据 → 保留 12px 改良表
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


def test_three_cols_shrink_to_11px_and_fit_100pct():
    """3 列（短内容）→ 11px + width:100% + overflow:hidden（放得下不横滑）。"""
    html = _table(
        "<tr><td>2025</td><td>Claude Code</td><td>终端 Agent</td></tr>"
        "<tr><td>2026</td><td>Cowork</td><td>团队协作</td></tr>",
        "<th>时间</th><th>产品</th><th>形态</th>")
    out = F.process_table(html)
    assert "font-size: 11px" in out
    assert "width: 100%" in out and "overflow: hidden" in out
    assert "overflow-x: auto" not in out


def test_four_cols_horizontal_scroll():
    """4 列 → 11px + overflow-x:auto + table 固定 px 宽（放不下横滑）。"""
    html = _table(
        "<tr><td>Opus 4.8</td><td>1M</td><td>较高</td><td>最强推理</td></tr>"
        "<tr><td>Sonnet 5</td><td>200K</td><td>中</td><td>均衡快</td></tr>",
        "<th>模型</th><th>上下文</th><th>价格</th><th>特点</th>")
    out = F.process_table(html)
    assert "overflow-x: auto" in out
    assert re.search(r"width:\s*\d{3,}px", out), "table 应有固定 px 宽以触发横滑"
    assert "font-size: 11px" in out


def test_two_col_term_table_becomes_cards():
    """2 列「术语|长释义」→ 术语卡（左竖条），不再是 <table>。"""
    html = _table(
        "<tr><td><strong>Agent</strong></td>"
        "<td>能自主规划并调用工具完成多步任务的 AI 系统，区别于一问一答的对话模型。</td></tr>"
        "<tr><td><strong>MCP</strong></td>"
        "<td>模型上下文协议，让模型以统一方式接入外部工具与数据源，是当下事实标准。</td></tr>",
        "<th>术语</th><th>说明</th>")
    out = F.process_table(html)
    assert "<table" not in out, "术语表应转卡片、不保留 table"
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
    assert "<table" in out and "border-left: 3px solid" not in out
    assert "font-size: 12px" in out


def test_baoyu_wrapped_scroll_table_single_wrapper():
    """🔴 回归(55号真机)：baoyu 用 <section ...overflow:auto> 包住表 → 经 replace_wrapped_table
    包成横滑 section 后，fallback 兜底不得因只认 overflow:hidden 而二次包裹 → 双边框。
    横滑表(≥3列放不下)必须只有 1 层 border-radius:10px 容器。"""
    baoyu = ('<div id="output"><section style="font-family: PingFang SC, Microsoft YaHei; '
             'font-size: 16px; line-height: 1.75; text-align: left; max-width: 100%; overflow: auto;">'
             '<table class="preview-table"><thead>'
             '<th>模型</th><th>上下文</th><th>价格</th><th>特点</th></thead><tbody>'
             '<tr><td>Opus</td><td>1M</td><td>较高</td><td>最强推理</td></tr>'
             '<tr><td>Sonnet</td><td>200K</td><td>中</td><td>均衡快</td></tr>'
             '</tbody></table></section></div>')
    out = F.process_table(baoyu)
    assert out.count("border-radius: 10px") == 1, "横滑表被双层包裹（双边框）"
    assert out.count("overflow-x: auto") == 1
    # 不得出现 section 紧套 section 的横滑双壳
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


def test_pure_fixtures_match_frozen_baseline():
    """两个 process_table _pure fixture（3列横滑 + 术语卡）须与冻结 expected 逐行一致。"""
    pure = os.path.join(SW, "tests", "golden", "_pure")
    for stem in ("process_table", "process_table_term"):
        src = open(os.path.join(pure, f"{stem}.in.html"), encoding="utf-8").read()
        exp = open(os.path.join(pure, f"{stem}.expected.html"), encoding="utf-8").read()
        assert F.process_table(src).splitlines() == exp.splitlines(), \
            f"{stem} 输出偏离冻结基线"
