# -*- coding: utf-8 -*-
"""微信 HTML 必须先修复非法内联字体属性，再允许发布。"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from format_layout import _BROKEN_INLINE_FONT_RE, repair_inline_font_family_quotes  # noqa: E402


def test_repair_baoyu_cjk_font_stack_keeps_card_styles_valid():
    broken = (
        '<section style="font-family: "Source Han Serif SC", '
        '"Noto Serif CJK SC", "Source Han Serif CN", STSong, serif; '
        'border: 1px solid #0E926F;">主题曲</section>'
    )
    fixed = repair_inline_font_family_quotes(broken)

    assert not _BROKEN_INLINE_FONT_RE.search(fixed)
    assert "font-family: Source Han Serif SC, Noto Serif CJK SC" in fixed
    assert "border: 1px solid #0E926F" in fixed
