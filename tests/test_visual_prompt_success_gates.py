"""把 2026-08-15 生图对照实验的结论钉成闸门。

实验：同一份内容、同一个模型（Banana 2）、逐张人工判定文字合同，
共 60 张。三个因子分别单独变动：

  变体              prompt   allowlist 重叠   SCENE        首过率（01+04）
  A（改造前现状）    5000 字符  4 / 2          抽象几何      1/6 =  17%
  E                 930 字符  1 / 1          抽象几何      6/12 =  50%
  F                1112 字符  1 / 1          具体物象     11/12 =  92%

结论：
  · 光精简 prompt 几乎没用（D 组单独精简到 940 字符，最难那张仍是 1/3）
  · 修 allowlist 重叠：+33 个百分点
  · SCENE 给具体物象：+42 个百分点 ← 最大的一块
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import visual_workflow as vw  # noqa: E402


# ── allowlist 重叠 ────────────────────────────────────────────────────────
def test_full_containment_still_blocked():
    """重叠 4（完整包含）实测 0/6，必须拦。"""
    errs = vw._text_overlap_errors(
        "infographic-01", "一个月，八次更新",
        ["八次更新", "中国五个", "美国三个"])
    assert errs
    assert any("八次更新" in e for e in errs)


def test_partial_overlap_two_chars_now_blocked():
    """重叠 2 实测首过率只有 50% —— 旧实现放行了它，全库 36 张里漏掉 19 张。"""
    errs = vw._text_overlap_errors(
        "infographic-04", "换底座的只有三个",
        ["新底座三个", "旧底座五个"])
    assert errs, "重叠 2 必须拦下"
    assert any("底座" in e for e in errs)


def test_overlap_of_one_char_passes():
    """重叠 1 实测 6/6 全过，不能误伤。"""
    assert vw._text_overlap_errors(
        "infographic-01", "一个月，八次更新", ["中国五个", "美国三个"]) == []


def test_zero_overlap_passes():
    assert vw._text_overlap_errors(
        "infographic-02", "两种分工", ["走量", "攻坚"]) == []


def test_experiment_verified_rewrites_pass():
    """实验里实测 5/6 和 6/6 的那两份改写，闸门必须放行。"""
    assert vw._text_overlap_errors(
        "infographic-01", "一个月，八次更新", ["中国五个", "美国三个"]) == []
    assert vw._text_overlap_errors(
        "infographic-04", "底座之变", ["换了三个", "没换五个"]) == []


def test_longest_common_substring_is_contiguous():
    """必须是连续子串，不是子序列 —— 否则「中国五个」和「美国三个」会被
    误判成重叠 3（共有 国/个 等不连续字符），把一份实测 100% 的任务单拦掉。"""
    assert vw._longest_common_substring("中国五个", "美国三个") == "国"
    assert vw._longest_common_substring("换底座的只有三个", "新底座三个") == "底座"
    assert vw._longest_common_substring("走量", "攻坚") == ""


# ── SCENE 具体物象 ────────────────────────────────────────────────────────
ABSTRACT_01 = ("One vertical spine, largest block at top shrinking downward. "
               "Text appears in exactly three places: a title band at the very "
               "top, one group label beside the left column, one group label "
               "beside the right column. Individual blocks carry no text at all.")

# 🔴 原本这里写的是 "…like a calendar strip"，实测 6 次翻 3 次且每次都翻在
#    那个日历上（见下方 CALENDAR_01 与 test_textual_prop_is_blocked）。
CONCRETE_01 = ("A tall smooth clay column stands down the centre of the frame. "
               "Standing in a column to its left are five small rounded clay "
               "robots, each holding up a tiny pennant. Standing to its right "
               "are three more of the same robots.")

ABSTRACT_04 = ("A central hub with spokes radiating to two clusters. Text "
               "appears in exactly three places.")

CONCRETE_04 = ("In the upper left, three small clay houses sit on a fresh "
               "pale-jade foundation slab, and a tiny clay worker is sliding the "
               "third one into place. In the lower right, five identical houses "
               "sit on an older cracked beige slab.")


def test_abstract_only_layout_is_blocked():
    """实测 50%：模型没东西可画就拿文字填空白。"""
    for label, layout in (("infographic-01", ABSTRACT_01),
                          ("infographic-04", ABSTRACT_04)):
        errs = vw._layout_concrete_subject_errors(label, layout)
        assert errs, f"{label} 的抽象 layout 必须拦下"
        assert "抽象几何" in errs[0]


def test_concrete_layout_passes():
    """实测 83% 与 100% 的那两份，必须放行。"""
    assert vw._layout_concrete_subject_errors("infographic-01", CONCRETE_01) == []
    assert vw._layout_concrete_subject_errors("infographic-04", CONCRETE_04) == []


def test_layout_with_no_geometry_words_is_not_flagged():
    """既没抽象几何也没具体物象时不报错 —— 这条闸门只治「光有几何」。"""
    assert vw._layout_concrete_subject_errors(
        "infographic-02", "Two evidence zones separated by a controlled gap") != []
    assert vw._layout_concrete_subject_errors("infographic-03", "") == []


def test_concrete_word_beats_abstract_word_in_same_layout():
    """同时出现几何词和实体词时放行 —— 实体词说明模型有活干。"""
    mixed = ("Two columns of clay carts on the left and one big machine on the "
             "right, each sitting on its own low platform.")
    assert vw._layout_concrete_subject_errors("infographic-02", mixed) == []


# ── 与既有闸门的联动 ──────────────────────────────────────────────────────
def test_ninth_ninth_article_plan_would_be_caught_on_both_counts():
    """第 89 篇那份任务单，两条新闸门都该抓到。"""
    overlap = vw._text_overlap_errors(
        "infographic-01", "一个月，八次更新",
        ["八次更新", "中国五个", "美国三个"])
    scene = vw._layout_concrete_subject_errors("infographic-01", ABSTRACT_01)
    assert overlap and scene, "89 篇的 01 应当被两条闸门同时拦下"


def _plan(layout, title, expected):
    """一份除被测字段外全合规的 plan。"""
    def sheet(i, pos, aspect, t, lt, lay, exp):
        return {"id": i, "position": pos, "aspect_ratio": aspect, "title": t,
                "layout_type": lt, "layout": lay, "anchor": f"锚句{i}",
                "expected_text": exp, "facts": ["已核实事实"]}
    return {
        "schema_version": 1,
        "cover": {"title": "封面", "subtitle": "副标",
                  "visual_facts": ["事实一", "事实二"]},
        "hero": {"title": "Hero", "visual_facts": ["核心"]},
        "infographics": [
            sheet("01", "opening", "9:16", title, "linear-progression",
                  layout, expected),
            sheet("02", "middle", "16:9", "两种分工", "binary-comparison",
                  CONCRETE_04, ["走量", "攻坚"]),
            sheet("03", "middle", "16:9", "两条线，只动了一条", "hub-spoke",
                  CONCRETE_01, ["快线更新了", "主力线未动"]),
            sheet("04", "closing", "9:16", "底座之变", "winding-roadmap",
                  CONCRETE_04, ["换了三个", "没换五个"]),
        ],
    }


def test_validate_plan_actually_calls_the_concrete_subject_gate():
    """钉住调用点，不只钉函数。

    只测 _layout_concrete_subject_errors 本身是不够的：把 validate_visual_plan
    里那行调用删掉，单元测试照样全绿（实测过）。这条走真实校验入口。
    """
    bad = vw.validate_visual_plan(
        _plan(ABSTRACT_01, "一个月，八次更新", ["中国五个", "美国三个"]))
    assert any("抽象几何" in e for e in bad), f"抽象 layout 必须在校验入口被拦：{bad}"

    good = vw.validate_visual_plan(
        _plan(CONCRETE_01, "一个月，八次更新", ["中国五个", "美国三个"]))
    assert good == [], f"实测 83% 的那份不该被拦：{good}"


def test_validate_plan_actually_calls_the_overlap_gate():
    bad = vw.validate_visual_plan(
        _plan(CONCRETE_01, "换底座的只有三个", ["新底座三个", "旧底座五个"]))
    assert any("共享" in e for e in bad), f"重叠 2 必须在校验入口被拦：{bad}"


@pytest.mark.parametrize("title,labels,expect_blocked", [
    ("两种分工", ["走量", "攻坚"], False),                      # 实测 6/6
    ("两条线，只动了一条", ["快线更新了", "主力线未动"], False),   # 实测 6/6
    ("换底座的只有三个", ["新底座三个", "旧底座五个"], True),      # 实测 3/6
    ("一个月，八次更新", ["八次更新", "中国五个"], True),          # 实测 0/6
])
def test_gate_matches_measured_pass_rates(title, labels, expect_blocked):
    """闸门的判定必须和实测首过率对得上：实测 100% 的放行，≤50% 的拦下。"""
    blocked = bool(vw._text_overlap_errors("x", title, labels))
    assert blocked is expect_blocked


# ── 自带文字的物件（2026-08-16 实证）────────────────────────────────────
CALENDAR_01 = ("A tall clay ribbon runs down the centre of the frame like a "
               "calendar strip. Five small clay robots stand to its left, three "
               "to its right, each holding a tiny pennant.")

PLAIN_01 = ("A tall smooth clay column stands down the centre of the frame. "
            "Five small clay robots stand to its left, three to its right, "
            "each holding a tiny pennant.")


def test_textual_prop_is_blocked():
    """实测：留着 calendar strip，6 次里翻车 3 次且每次都翻在那个日历上。"""
    errs = vw._layout_textual_prop_errors("infographic-01", CALENDAR_01)
    assert errs
    assert "calendar" in errs[0]


def test_plain_prop_passes():
    """唯一变量换掉之后必须放行。"""
    assert vw._layout_textual_prop_errors("infographic-01", PLAIN_01) == []


@pytest.mark.parametrize("word", [
    "newspaper", "signboard", "billboard", "poster", "screen", "dashboard",
    "whiteboard", "menu", "ticket", "receipt", "chart", "notebook",
])
def test_common_textual_props_are_all_covered(word):
    """这些词在信息图 layout 里都很自然会被想到 —— 正因为自然才要拦。"""
    layout = f"Three small clay houses next to a {word} on a low platform."
    assert vw._layout_textual_prop_errors("x", layout), f"漏拦：{word}"


def test_textual_prop_gate_is_wired_into_validate():
    """钉调用点，不只钉函数。"""
    bad = vw.validate_visual_plan(
        _plan(CALENDAR_01, "一个月，八次更新", ["中国五个", "美国三个"]))
    assert any("自带文字" in e for e in bad), f"校验入口必须拦下：{bad}"

    good = vw.validate_visual_plan(
        _plan(PLAIN_01, "一个月，八次更新", ["中国五个", "美国三个"]))
    assert good == [], f"换掉之后不该被拦：{good}"


def test_concrete_and_textual_gates_are_independent():
    """两条闸门管的是不同的事，别互相顶替。"""
    # 有具体物象、但那物象自带文字 → 只该被 textual 那条拦
    assert vw._layout_concrete_subject_errors("x", CALENDAR_01) == []
    assert vw._layout_textual_prop_errors("x", CALENDAR_01)
    # 抽象几何、不含文字物件 → 只该被 concrete 那条拦
    assert vw._layout_concrete_subject_errors("x", ABSTRACT_01)
    assert vw._layout_textual_prop_errors("x", ABSTRACT_01) == []