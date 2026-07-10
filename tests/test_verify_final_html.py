# -*- coding: utf-8 -*-
"""verify_final_html 产物关测试：合成 golden 通过 + 硬违规必抓 + 校准守卫(flex/class/div 不误杀)。"""
import os
from scripts.contracts import verify_final_html

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 合成夹具（不含任何真实文章内容）；重新生成：
#   python tests/golden/_synthetic_final/make_fixture.py
GOLDEN = os.path.join(SKILL_ROOT, "tests", "golden", "_synthetic_final", "定稿.html")


def test_golden_final_html_passes():
    """合成 定稿.html（含 class=/<div id=output>/flex/居中 dashed 占位）应 ok、零 error、零 warn。"""
    r = verify_final_html(GOLDEN)
    assert r['verdict'] == 'ok', r['errors']
    assert r['errors'] == []
    assert r['warnings'] == [], r['warnings']


def test_calibration_flex_class_div_not_flagged():
    """校准守卫：baoyu 合法产出的 flex/class/<div> 不能被误判为违规。"""
    html = ('<div id="output"><section class="p" style="display:flex;">'
            '<span>正文</span></section></div>')
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    try:
        r = verify_final_html(path)
        assert r['verdict'] == 'ok', r['errors']
    finally:
        os.unlink(path)


def _run(html):
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    try:
        return verify_final_html(path)
    finally:
        os.unlink(path)


def test_hard_violations_fail():
    """style/script/position:absolute/grid/var/@media 命中即 fail。"""
    for bad in [
        '<style>.x{}</style><section>x</section>',
        '<section style="position:absolute;">x</section>',
        '<section style="display:grid;">x</section>',
        '<section style="color:var(--c);">x</section>',
        '<section>@media(max-width:1px){}</section>',
    ]:
        r = _run(bad)
        assert r['verdict'] == 'fail', f"应 fail: {bad}"
        assert r['hits'] >= 1


def test_comment_mention_not_flagged():
    """注释里提到 position:absolute 不算真实违规。"""
    r = _run('<!-- 旧版 position:absolute 已弃 --><section>x</section>')
    assert r['verdict'] == 'ok', r['errors']


def test_four_side_dashed_non_centered_warns():
    """四周虚线框（非居中）→ WARN，不 fail。"""
    r = _run('<section style="border:1px dashed #ccc;padding:10px;">强调</section>')
    assert r['verdict'] == 'ok'
    assert r['warnings']


def test_directional_dashed_ok():
    """方向性 border-bottom dashed（如深读栏下划线）不 WARN。"""
    r = _run('<section style="border-bottom:1px dashed rgba(47, 111, 143,0.15);">x</section>')
    assert r['warnings'] == []


def test_centered_dashed_placeholder_ok():
    """居中素材占位块的四周虚线是唯一例外，不 WARN。"""
    r = _run('<section style="border:1.5px dashed #ddd;text-align:center;padding:30px;">🎬 待补素材</section>')
    assert r['warnings'] == []


def test_missing_file():
    r = verify_final_html(os.path.join(SKILL_ROOT, "no_such_定稿.html"))
    assert r['verdict'] == 'no_article'
