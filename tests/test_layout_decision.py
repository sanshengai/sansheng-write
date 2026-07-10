# -*- coding: utf-8 -*-
"""P1-5 交付附件 _layout-decision.md：机械事实自动扫 + AUTO 标记幂等保留语义段。"""
import os
import importlib.util

SW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "format_layout", os.path.join(SW, "scripts", "format_layout.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

_MD = """---
title: t
---
## 第一章
### A
> **划重点**
> - x

| 列A | 列B |
|-----|-----|
| 1 | 2 |

<!-- stat: 300|美元|额度 -->
<!-- steps: a || b -->
<!-- compare: 旧|x || 新|y -->
![图](素材/a.png)
## 第二章
### B
"""


def _mk(tmp_path):
    (tmp_path / "定稿.md").write_text(_MD, encoding="utf-8")
    return str(tmp_path)


def test_first_run_writes_scaffold_with_facts(tmp_path):
    cwd = _mk(tmp_path)
    F.write_layout_decision(cwd, {"genre": "教程文", "title_final": "标题X"})
    out = (tmp_path / "_layout-decision.md").read_text(encoding="utf-8")
    assert "## 一、机械事实（自动）" in out and "## 二、语义决策" in out
    assert "H2 大编号 ×2" in out and "H3 子标题 ×2" in out
    assert "数字卡 ×1 / 步骤条 ×1 / 对比块 ×1" in out
    assert "教程文" in out and "标题X" in out
    assert out.count("AUTO-FACTS-START") == 1 and out.count("AUTO-FACTS-END") == 1


def test_second_run_refreshes_facts_preserves_semantics(tmp_path):
    cwd = _mk(tmp_path)
    F.write_layout_decision(cwd, {"genre": "教程文", "title_final": "旧标题"})
    p = tmp_path / "_layout-decision.md"
    # 模拟 LLM 填一条语义
    p.write_text(p.read_text(encoding="utf-8").replace("_TODO_", "编排器已填的理由。", 1),
                 encoding="utf-8")
    # 二次跑：机械段刷新、语义段保留
    F.write_layout_decision(cwd, {"genre": "教程文", "title_final": "新标题"})
    out = p.read_text(encoding="utf-8")
    assert "编排器已填的理由。" in out, "已填语义段必须保留"
    assert "新标题" in out and "旧标题" not in out, "机械段须刷新"
    assert out.count("AUTO-FACTS-START") == 1


def test_no_md_is_safe(tmp_path):
    """无 定稿.md 时不抛（facts 段空信号），交付附件非关键路径。"""
    F.write_layout_decision(str(tmp_path), {})
    # 无 定稿.md 也应能生成骨架（信号全 0），且不崩
    out = (tmp_path / "_layout-decision.md").read_text(encoding="utf-8")
    assert "机械事实" in out
