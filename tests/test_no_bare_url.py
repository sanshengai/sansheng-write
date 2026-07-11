# -*- coding: utf-8 -*-
"""verify_no_bare_url 裸 URL 门测试：模板内 URL 放行 + 裸放正文/划重点/文末手敲必抓。

夹具 URL 全用中性占位（example.com 等），不含任何真实品牌域名。
"""
import os
import tempfile
from scripts.contracts import verify_no_bare_url

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# link-card / deep-read 模板里 URL 框的真实标记（带 word-break:break-all）
SAFE_BOX = (
    '<section style="font-size:13px;color:#4a6b7a;font-weight:600;line-height:1.6;'
    'text-align:left;word-break:break-all;background:#eaf1f5;border-radius:6px;'
    'padding:8px 10px;">{url}</section>'
)


def _run(html):
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html)
        path = f.name
    try:
        return verify_no_bare_url(path)
    finally:
        os.unlink(path)


def test_bare_url_in_paragraph_fails():
    """文末手敲的裸 URL 段落（分散对齐 + 难复制的翻车形态）→ fail。"""
    r = _run('<section style="font-size:15px;color:#333;">'
             '国内直达：example.com/tools/treasure（官网资源页）</section>')
    assert r['verdict'] == 'fail', r
    assert r['hits'] >= 1


def test_bare_https_url_fails():
    """https:// 全写裸放正文 → fail。"""
    r = _run('<p>项目地址 https://github.com/acme/widget-cli 欢迎 star</p>')
    assert r['verdict'] == 'fail', r


def test_bare_url_in_takeaway_like_block_fails():
    """划重点式区块里内嵌裸 URL（分散对齐来源）→ fail。"""
    r = _run('<section style="display:table-cell;vertical-align:top;">'
             'GitHub 打不开就走 example.com/tools/mirror-download，国内加速直下</section>')
    assert r['verdict'] == 'fail', r


def test_url_in_link_card_box_ok():
    """URL 装进 link-card 的 word-break 浅框 → ok（正确用法不误杀）。"""
    r = _run(SAFE_BOX.format(url='https://example.com/tools/treasure'))
    assert r['verdict'] == 'ok', r['errors']


def test_url_in_takeaway_with_wordbreak_ok():
    """修好后的划重点内容单元格带 word-break → 即便混进 URL 也不判裸（防分散已达成）。"""
    r = _run('<span style="display:table-cell; vertical-align:top; text-align:left; '
             'word-break:break-all;">见 example.com/tools/treasure</span>')
    assert r['verdict'] == 'ok', r['errors']


def test_url_in_img_src_ok():
    """图片 src / data-local-path 属性里的 URL 不是正文可见文本 → ok。"""
    r = _run('<img src="https://img.example.com/cover/aBcDeF123/640.png" '
             'data-local-path="素材/cover.png" style="width:100%;">')
    assert r['verdict'] == 'ok', r['errors']


def test_plain_domain_no_path_ok():
    """纯域名提及（无 /路径，短、不分散）→ 不匹配、ok。"""
    r = _run('<section style="font-size:14px;">官网 example.com，欢迎来玩</section>')
    assert r['verdict'] == 'ok', r['errors']


def test_filename_and_version_not_flagged():
    """文件名（cover.png）/ 版本号（v0.1.0）不是 URL → ok。"""
    r = _run('<p>产物 cover.png，当前 v0.1.0，模型 gpt-image-2</p>')
    assert r['verdict'] == 'ok', r['errors']


def test_short_inline_citation_ok():
    """短行内引用（<18 字符，如 claude.com/blog）风险低 → 放行，不误伤正文引用。"""
    r = _run('<p>官方说明见 claude.com/blog，2026-06-30 更新。</p>')
    assert r['verdict'] == 'ok', r['errors']


def test_long_bare_url_still_fails_with_paren_note():
    """长引流 URL 带中文括注 → 仍 fail，且不把括注吞进 URL。"""
    r = _run('<p>国内直达：example.com/tools/treasure（本站直供加速下载）</p>')
    assert r['verdict'] == 'fail', r
    # URL 片段不应把中文括注内容吞进来（消息样板自带全角括号，故查括注文字「本站」）
    assert '本站' not in r['errors'][0]


def test_comment_mention_ok():
    """注释里提到 URL 不算正文。"""
    r = _run('<!-- 旧引流 example.com/tools/treasure 已迁模板 --><p>正文</p>')
    assert r['verdict'] == 'ok', r['errors']


def test_missing_file():
    r = verify_no_bare_url(os.path.join(SKILL_ROOT, "no_such_定稿.html"))
    assert r['verdict'] == 'no_article'
