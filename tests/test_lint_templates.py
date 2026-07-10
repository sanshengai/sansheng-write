# -*- coding: utf-8 -*-
"""lint_templates.py 测试：现状模板 0 ERROR + lint 真能抓违规/豁免生效。"""
import os
from scripts.lint_templates import lint_all, lint_text

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_current_templates_zero_error():
    """现有 templates/*.html + bgm 脚本必须 0 ERROR（回归门）。"""
    errors, _warns = lint_all(SKILL_ROOT)
    assert errors == [], "模板出现平台硬违规:\n" + "\n".join(errors)


def test_current_templates_zero_warn():
    """现状 baseline 应无色值/圆角漂移 WARN（新增漂移即暴露）。"""
    _errors, warns = lint_all(SKILL_ROOT)
    assert warns == [], "模板出现令牌漂移 WARN:\n" + "\n".join(warns)


def test_lint_catches_forbidden_css():
    """position:absolute / display:grid / class= 应报 ERROR。"""
    bad = '<section style="position:absolute; display:grid;"><span>x</span></section>'
    errors, _ = lint_text("bad.html", bad)
    assert any("position" in e for e in errors)
    assert any("grid" in e for e in errors)


def test_lint_flags_off_palette_color():
    """令牌外色值（如随手一个灰）应 WARN。"""
    bad = '<section style="color:#ababab;">x</section>'
    _errors, warns = lint_text("bad.html", bad)
    assert any("#ababab" in w for w in warns)


def test_brand_green_alpha_not_flagged():
    """品牌绿任意 alpha 的 rgba 不算漂移。"""
    ok = '<section style="background:rgba(47, 111, 143,0.42);">x</section>'
    _errors, warns = lint_text("ok.html", ok)
    assert warns == []


def test_profile_card_class_exempt():
    """mp-common-profile 关注卡合法带 class → 不报 class ERROR。"""
    card = ('<section class="mp_profile_iframe_wrp custom_select_card_wrp">'
            '<mp-common-profile class="mpprofile js_uneditable" data-id="x">'
            '</mp-common-profile></section>')
    errors, _ = lint_text("footer.html", card)
    assert not any("class" in e for e in errors), errors


def test_html_comment_mentions_not_flagged():
    """注释里提及 position:absolute / <div id=output> 不算真实违规。"""
    commented = '<!-- 旧版 position:absolute 不支持；须在 <div id="output"> 内 -->\n<section>x</section>'
    errors, _ = lint_text("c.html", commented)
    assert errors == [], errors


def test_off_scale_radius_warns():
    """脱 4 档圆角（如 14px）应 WARN，档内（10px）不 WARN。"""
    _e1, w1 = lint_text("a.html", '<section style="border-radius:14px;">x</section>')
    assert any("14px" in w for w in w1)
    _e2, w2 = lint_text("b.html", '<section style="border-radius:10px;">x</section>')
    assert w2 == []
