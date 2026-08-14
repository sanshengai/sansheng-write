"""视觉任务单的三条「编译期预防」检查。

2026-08-14 第 89 篇实跑：机械链共发起 45 次生图，其中 39 次是重渲（必要量的
7.5 倍），同时是撞 429 的主因。逐次复盘发现约 30 次可由纯字符串检查在编译期
拦掉。本文件用**当时真实失败的那些任务单**做用例 —— 每条都必须能拦住当初那版。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from visual_workflow import (  # noqa: E402
    _layout_negative_phrasing_errors,
    _layout_node_label_errors,
    _text_overlap_errors,
)


# --- ① expected_text 互不包含（实测白渲约 8 次）---

def test_label_inside_title_is_rejected():
    """真实case：标题「走量的和攻坚的」含标签「走量」「攻坚」→ 各渲两遍。"""
    errs = _text_overlap_errors("infographics[1]", "走量的和攻坚的", ["走量", "攻坚"])
    assert len(errs) == 2
    assert "恰好一次" in errs[0]


def test_rewritten_title_passes():
    """改成「两种分工」后不含任何标签词 —— 当轮即过。"""
    assert _text_overlap_errors("x", "两种分工", ["走量", "攻坚"]) == []


def test_labels_containing_each_other_rejected():
    errs = _text_overlap_errors("x", "标题", ["快线", "快线更新了"])
    assert len(errs) == 1
    assert "互相包含" in errs[0]


def test_title_equal_to_label_not_double_counted():
    """title 与某条 expected_text 完全相同是允许的（同一处文字）。"""
    assert _text_overlap_errors("x", "换底座的只有三个", ["换底座的只有三个"]) == []


def test_disjoint_labels_pass():
    assert _text_overlap_errors("x", "两条线，只动了一条",
                                ["快线更新了", "主力线未动"]) == []


# --- ② layout 否定式措辞（实测白渲约 12 次）---

def test_negative_phrasing_rejected():
    """真实case：连写三轮 no sign board / no rounded plate，模型照样加底板。"""
    layout = ("Labels sit directly on the surface as raised clay letters, "
              "with no sign board, no rounded plate and no punctuation around them.")
    errs = _layout_negative_phrasing_errors("x", layout)
    assert len(errs) == 1
    assert "正面描述" in errs[0]


def test_chinese_negative_phrasing_rejected():
    assert _layout_negative_phrasing_errors("x", "标签周围不要任何装饰符号") != []


def test_positive_phrasing_passes():
    """改成正面描述后过 —— 这正是当轮渲对的那一版。"""
    layout = ("Render all three the same way -- freestanding sculpted clay letters "
              "resting straight on the background surface, identical treatment to "
              "the title, only smaller.")
    assert _layout_negative_phrasing_errors("x", layout) == []


def test_empty_layout_passes():
    assert _layout_negative_phrasing_errors("x", "") == []


# --- ③ 节点数量未声明无文字（实测白渲约 10 次）---

def test_node_count_without_textfree_declaration_rejected():
    """真实case：eight ordered stops → 同一个词被渲了 8 遍。"""
    layout = ("Single vertical timeline, newest node at top, eight ordered stops, "
              "exactly one short label per stop")
    errs = _layout_node_label_errors("x", layout)
    assert len(errs) == 1
    assert "各贴一遍标签" in errs[0]


def test_three_milestones_also_rejected():
    """同一根因的另一例：three passed milestones → 标签渲了 3 遍。"""
    layout = "One continuous route with three passed milestones and one unbuilt at the end"
    assert _layout_node_label_errors("x", layout) != []


def test_node_count_with_textfree_declaration_passes():
    """补上「节点不带文字」的正面声明后过 —— 修好的那一版。"""
    layout = ("One vertical spine, largest block at top shrinking downward. "
              "Text appears in exactly three places: a title band at the very top, "
              "one group label beside the left column, one group label beside the "
              "right column. Individual blocks carry no text at all.")
    assert _layout_node_label_errors("x", layout) == []


def test_layout_without_node_count_passes():
    layout = "Two separated zones of unequal mass, many small units on one side"
    assert _layout_node_label_errors("x", layout) == []


# --- 回归保护：三条检查不得被悄悄摘掉 ---

def test_all_three_checks_catch_the_original_failing_plans():
    """把第 89 篇最初那版任务单喂进来，三条必须全部报错。"""
    bad_title, bad_labels = "走量的和攻坚的", ["走量", "攻坚"]
    bad_layout = ("Single vertical timeline, eight ordered stops, exactly one short "
                  "label per stop, with no plate and no punctuation")
    assert _text_overlap_errors("x", bad_title, bad_labels), "① 未拦住"
    assert _layout_negative_phrasing_errors("x", bad_layout), "② 未拦住"
    assert _layout_node_label_errors("x", bad_layout), "③ 未拦住"
