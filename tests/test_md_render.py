"""内置 Markdown 渲染器：与 baoyu-md 的真实输出逐节点对照（金标准夹具），外加中文加粗、手写 HTML、首个子元素等回归。"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import md_render as M  # noqa: E402
import md_render_compare as C  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "md_render"
PRIMARY = "#2F6F8F"


def render(tmp_path, name="features.md", **kw):
    out = tmp_path / (name + ".html")
    M.render_file(FIX / name, out, primary=PRIMARY, keep_title=True, **kw)
    return out


def test_features_match_baoyu_golden(tmp_path):
    """夹具 features.baoyu.html 是 baoyu-md 对同一份 markdown 的真实输出（代码块除外，那是有意不同）。"""
    C.SKIP_TAGS.clear(); C.SKIP_TAGS.add("pre")
    diffs = C.compare(FIX / "features.baoyu.html", render(tmp_path), ignore=("data-local-path", "style-html"), limit=10)
    assert [d for d in diffs if "'html'" not in d] == [], "\n".join(diffs)


def test_hand_written_html_gets_theme_type_styles_like_baoyu(tmp_path):
    C.SKIP_TAGS.clear()
    diffs = C.compare(FIX / "raw.baoyu.html", render(tmp_path, "raw.md"), ignore=("data-local-path",), limit=10)
    assert [d for d in diffs if "'html'" not in d] == [], "\n".join(diffs)


def test_cjk_bold_next_to_quotes_and_punctuation_is_still_bold():
    """CommonMark 对 **“词”**中文 会失效；预处理改成 HTML 标签后必须仍是加粗。"""
    html = M.convert("**“带引号的加粗”**紧跟中文，以及 *斜体*中文。", primary=PRIMARY)["html"]
    assert re.search(r"<strong[^>]*>“带引号的加粗”</strong>紧跟中文", html)
    assert re.search(r"<em[^>]*>斜体</em>中文", html)
    assert "**" not in html


def test_bold_inside_code_is_left_alone():
    html = M.convert("说明 `**不是加粗**` 与 **真加粗**", primary=PRIMARY)["html"]
    assert "<code" in html and ">**不是加粗**</code>" in html and html.count("<strong") == 1


def test_first_child_of_container_gets_margin_top_important():
    html = M.convert("首段\n\n次段", primary=PRIMARY)["html"]
    first, second = re.findall(r'<p class="p" style="([^"]*)"', html)
    assert "margin-top: 0 !important" in first and "margin-top: 0 !important" not in second


def test_keep_title_flag_controls_first_heading():
    md = "# 标题\n\n## 小节\n\n正文"
    assert "<h1" in M.convert(md, primary=PRIMARY, keep_title=True)["html"]
    dropped = M.convert(md, primary=PRIMARY, keep_title=False)["html"]
    assert "<h1" not in dropped and "<h2" in dropped  # 只去掉第一个 H1/H2


def test_images_become_local_path_img_and_survive_spaces(tmp_path):
    (tmp_path / "素材").mkdir()
    (tmp_path / "素材" / "a b.png").write_bytes(b"x")
    r = M.convert("![说明](<素材/a b.png>)", primary=PRIMARY, base_dir=tmp_path)
    assert f'src="素材/a b.png"' in r["html"] and f'data-local-path="{(tmp_path / "素材/a b.png").resolve()}"' in r["html"]
    assert 'alt="说明"' in r["html"] and r["images"] == [{"alt": "说明", "src": "素材/a b.png"}]


def test_meta_comes_from_frontmatter_then_body():
    r = M.convert("---\ntitle: 「标题」\ndescription: 描述\n---\n\n正文 " + "字" * 30, primary=PRIMARY)
    assert "<title>「标题」</title>" in r["html"] and 'name="description" content="描述"' in r["html"]
    r2 = M.convert("## 二级也算标题\n\n" + "这是一句足够长的正文用来生成摘要，超过二十个字。", primary=PRIMARY)
    assert r2["title"] == "二级也算标题" and r2["summary"].startswith("这是一句足够长")


def test_nested_lists_are_hoisted_like_baoyu_and_ordered_numbers_restart():
    html = M.convert("1. 一\n2. 二\n   - 内\n3. 三", primary=PRIMARY)["html"]
    assert html.index("1. 一") < html.index("2. 二") < html.index("• 内") < html.index("3. 三")
    assert re.search(r"</li><ul", html)  # 嵌套列表提到 li 之后


def test_regression_guard_a_wrong_style_is_detected(tmp_path):
    """反例：把主题色改错，金标准对照必须失败。"""
    out = tmp_path / "wrong.html"
    M.render_file(FIX / "features.md", out, primary="#123456", keep_title=True)
    C.SKIP_TAGS.clear(); C.SKIP_TAGS.add("pre")
    diffs = C.compare(FIX / "features.baoyu.html", out, ignore=("data-local-path",), limit=3)
    assert any("2f6f8f" in d for d in diffs)


def test_inline_hand_written_html_also_gets_theme_styles():
    html = M.convert('正文 <a href="https://x.com">链</a> 和 <b>粗</b> 与 <code>c</code>', primary=PRIMARY)["html"]
    assert re.search(r'<a href="https://x.com" style="color: #576b95; text-decoration: none;">链</a>', html)
    assert re.search(r'<code style="font-size: 90%; color: #d14;', html) and "<b>粗</b>" in html
