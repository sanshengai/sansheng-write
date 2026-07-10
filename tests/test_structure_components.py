# -*- coding: utf-8 -*-
"""P1-4B 结构组件测试：数字卡 / 步骤条 / 对比块（自包含注释指令 → 品牌组件）。
含幂等、无指令安全、以及与 verify_final_html 产物关不冲突（flex/solid border 不误杀）。
"""
import os
import tempfile
import importlib.util

SW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "format_layout", os.path.join(SW, "scripts", "format_layout.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)
from scripts.contracts import verify_final_html


def _verify_ok(html):
    """把片段包成最小 <div id=output> 文档，过 verify_final_html，应 verdict ok。"""
    doc = f'<div id="output">{html}</div>'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(doc)
        p = f.name
    try:
        return verify_final_html(p)
    finally:
        os.unlink(p)


def test_stat_three_cards():
    src = '<!-- stat: 300|美元|白嫖额度 ; 90|天|有效期 ; 1M|tokens|上下文 -->'
    out = F.process_stat(src)
    assert out.count("font-size: 26px") == 3
    assert "<!-- stat:" not in out
    assert "display: flex" in out
    assert _verify_ok(out)["verdict"] == "ok"


def test_stat_idempotent_and_noop():
    src = '<!-- stat: 5|个|工具 -->'
    once = F.process_stat(src)
    assert F.process_stat(once) == once, "已渲染的数字卡二次跑不应再变"
    assert F.process_stat("<p>无指令</p>") == "<p>无指令</p>"


def test_steps_numbered_badges():
    src = '<!-- steps: 注册 || 建 key || 复制 || 调用 -->'
    out = F.process_steps(src)
    assert all(f">{i}<" in out for i in (1, 2, 3, 4))
    assert "border-radius: 999px" in out  # 圆号徽章
    assert "<!-- steps:" not in out
    assert _verify_ok(out)["verdict"] == "ok"


def test_compare_two_columns():
    src = '<!-- compare: 旧做法|手动复制，10 分钟 || 新做法|一键批量，10 秒 -->'
    out = F.process_compare(src)
    assert out.count("flex: 1") == 2
    assert "color: #2F6F8F" in out  # 新侧品牌绿标题
    assert "color: #8a929a" in out  # 旧侧中性灰标题
    assert "<!-- compare:" not in out
    assert _verify_ok(out)["verdict"] == "ok"


def test_compare_malformed_single_side_untouched():
    """只有一侧（无 || 分隔）→ 保留原指令不误渲。"""
    src = '<!-- compare: 只有一侧 -->'
    assert F.process_compare(src) == src


def test_all_components_use_only_tokens():
    """三组件输出不得含令牌外硬编码色（除品牌绿/灰阶/白）。抽查无红/蓝杂色。"""
    out = (F.process_stat('<!-- stat: 1|个|x -->')
           + F.process_steps('<!-- steps: a || b -->')
           + F.process_compare('<!-- compare: t|c || t2|c2 -->'))
    for bad in ("#0F4C81", "#d14", "red", "blue"):
        assert bad not in out
