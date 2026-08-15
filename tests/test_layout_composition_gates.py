"""版式三闸（2026-08-16 第 90 篇实跑固化）。

背景：前三类闸门管「文字会不会被渲坏」，但第 90 篇 infographic-03 仍连废 6 版，
根因全在**版式**——竖排三栏诱导中文竖排、三栏只给两标签导致模型自补、
主体横贯到边被 crop_safe 打回。这三条各自独立可测，只在宽图/多分区时触发。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from visual_workflow import _layout_composition_errors as check  # noqa: E402


# ── ① 横图竖排结构 ─────────────────────────────────────────────────────────

def test_wide_image_with_vertical_bands_is_rejected():
    errs = check("infographics[0]",
                 "The frame is divided into three vertical bands by two thin clay grooves.",
                 "16:9", ["甲", "乙", "丙"])
    assert any("竖向结构" in e for e in errs)


def test_wide_image_top_to_bottom_is_rejected():
    errs = check("x", "A tall clay column runs from top to bottom of the frame.",
                 "2.35:1", ["甲"])
    assert any("竖向结构" in e for e in errs)


def test_portrait_image_may_be_vertical():
    """9:16 竖图本来就该竖着排，不能误伤。"""
    errs = check("x", "A tall clay conveyor belt runs from top to bottom of the frame.",
                 "9:16", ["甲", "乙"])
    assert errs == []


def test_wide_image_horizontal_layout_passes():
    errs = check("x", "A wide clay river runs horizontally, read as three equal parts left to right. "
                      "In the left part one stone, in the middle part three stones, in the right part a bridge.",
                 "16:9", ["只做一步", "各管一段", "整条焊死"])
    assert errs == []


# ── ② 分区数 vs 标签数 ─────────────────────────────────────────────────────

def test_three_parts_two_labels_is_rejected():
    """第 90 篇实测：三栏两标签 → 模型自补一个，「各管一段」渲两遍。"""
    errs = check("x", "In the left part one stone. In the middle part three stones. "
                      "In the right part one bridge.",
                 "16:9", ["各管一段", "整条焊死"])
    assert any("自己补一个" in e for e in errs)


def test_three_parts_three_labels_passes():
    errs = check("x", "In the left part one stone. In the middle part three stones. "
                      "In the right part one bridge.",
                 "16:9", ["只做一步", "各管一段", "整条焊死"])
    assert not any("自己补一个" in e for e in errs)


def test_centre_and_center_spellings_count_once():
    """centre / center 是同一个分区，不能算成两个。"""
    errs = check("x", "In the left part a stone, in the centre part a jar, in the center part a lamp.",
                 "16:9", ["甲", "乙"])
    # 分区应判定为 left+middle=2，标签 2 条 → 不报
    assert not any("自己补一个" in e for e in errs)


def test_single_subject_image_not_affected():
    errs = check("x", "One clay booklet lies flat at the centre of the frame with three arms.",
                 "9:16", ["读文章"])
    assert errs == []


# ── ③ 主体贴边 ─────────────────────────────────────────────────────────────

def test_edge_to_edge_subject_is_rejected():
    errs = check("x", "A wide clay river runs from the left edge to the right edge.",
                 "16:9", ["甲", "乙"])
    assert any("crop_safe" in e for e in errs)


def test_fills_the_frame_is_rejected():
    errs = check("x", "One giant clay gear fills the frame.", "16:9", ["甲"])
    assert any("crop_safe" in e for e in errs)


def test_margin_first_phrasing_passes():
    errs = check("x", "A generous band of empty ivory clay frames all four edges. Inside it sits one diorama.",
                 "16:9", ["甲"])
    assert errs == []


# ── 集成：真实任务单必须仍然通过 ───────────────────────────────────────────

def test_shipped_template_still_passes_composition_gate():
    import json
    from visual_workflow import validate_visual_plan
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "templates" / "visual-plan.template.json").read_text(encoding="utf-8"))
    assert validate_visual_plan(plan) == []
