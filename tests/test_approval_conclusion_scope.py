"""审批结论只看结论行，不扫全文。

2026-08-14 第 89 篇实跑：否决词此前扫全文，把「记录里提到拒绝」和「审批结论
是拒绝」混为一谈。我在 `_draft-approval.md` 里如实写了「未采纳冷读的某条建议
（会违反品牌铁律）」，其中「拒绝」二字命中，整份审批被判 rejected，闸门当场
拦死。

**审读记录写得越认真越容易被罚** —— 一份负责的记录必然要写清哪条意见没采纳、
为什么没采纳。这是反向激励，必须修。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evidence import _approval_anchor  # noqa: E402


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "_draft-approval.md").write_text(text, encoding="utf-8")
    return tmp_path


# --- 该放行的：正文提到否决词，但结论是通过 ---

def test_body_mentioning_rejection_still_approved(tmp_path):
    """本次真实卡死的那一份记录。"""
    _write(tmp_path, (
        "# 定稿闸门 · 作者审读记录\n\n"
        "冷读挑出 21 条，修 20 条（拒绝「全篇 -- 改全角」一条，违反品牌铁律）。\n"
        "事实复核抓出一处硬伤，已删除。\n\n"
        "审批结论：通过\n"
    ))
    anchor, errors = _approval_anchor(tmp_path, "draft")
    assert errors == []
    assert anchor["decision"] == "approved", "正文提到拒绝不该翻转审批结论"


def test_multiple_rejection_words_in_body_still_approved(tmp_path):
    _write(tmp_path, (
        "作者不同意原方案，要求改倒叙。\n"
        "「三个坑」整节被驳回，已删。\n"
        "某条建议未通过复核，也已剔除。\n\n"
        "审批结论：通过\n"
    ))
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "approved"


# --- 该拦的：结论行本身是否决 ---

def test_conclusion_line_rejected(tmp_path):
    _write(tmp_path, "# 审读\n\n内容都挺好。\n\n审批结论：不通过\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "rejected"


def test_conclusion_line_pending(tmp_path):
    _write(tmp_path, "审批结论：尚未确认\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "rejected"


def test_conclusion_line_refused(tmp_path):
    _write(tmp_path, "正文写得不错。\n\n审批结论：拒绝\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "rejected"


# --- 兜底：没写结论行时不得被正文的否决词蒙混过关 ---

def test_no_conclusion_line_but_body_rejects(tmp_path):
    """忘写结论行 + 正文写着不通过 → 仍判 rejected，不放行。"""
    _write(tmp_path, "# 审读\n\n这一版不通过，请重写开头。\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "rejected"


def test_no_conclusion_line_and_clean_body_is_unknown(tmp_path):
    _write(tmp_path, "# 审读\n\n看完了，挺好。\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "unknown"


# --- 其余既有语义不得回归 ---

def test_waived_still_works(tmp_path):
    _write(tmp_path, "作者免检授权：免检\n")
    assert _approval_anchor(tmp_path, "draft")[0]["decision"] == "waived"


def test_blueprint_gate_uses_outline_conclusion(tmp_path):
    (tmp_path / "_blueprint-approval.md").write_text(
        "方案 1 ~ 方案 5 已列。开头选 A 版。封面风格 montage-evidence。\n"
        "作者未采纳方案 3，理由是标题太绕。\n\n"
        "大纲：通过\n",
        encoding="utf-8",
    )
    assert _approval_anchor(tmp_path, "blueprint")[0]["decision"] == "approved"


def test_missing_file_reports_error(tmp_path):
    anchor, errors = _approval_anchor(tmp_path, "draft")
    assert anchor == {}
    assert errors and "_draft-approval.md" in errors[0]
