# -*- coding: utf-8 -*-
"""x_article.py 离线测试：Markdown → X 块翻译、说明文字预检、块序列校验。不碰浏览器。"""
from pathlib import Path

import pytest

from scripts import x_article as xa


FIXTURE_MD = """---
title: "教程 | 测试标题：两条路"
description: "摘要"
---

> **导读：** 这是导读。

# 教程 | 测试标题：两条路

开头段落，带**加粗**和 <mark>高亮</mark>，还有[链接](https://example.com/a)。

## 第一节

| 字段 | 填 |
|---|---|
| 用户名 | `abc@qq.com` |
| 端口 | 443 |

![一张截图](素材/shot.png)

*这是正文自带的图注*

---

### 小标题

```text
第一行
第二行
```

- 项一
- 项二

1. 甲
2. 乙

<!-- SANSHENG-VISUAL-START:01 -->
![信息图标题](素材/infographic-01.png)
<!-- SANSHENG-VISUAL-END:01 -->

<!-- SANSHENG-SOURCES -->
<section style="margin:22px 8px;">
  <section style="padding:16px 16px 12px;border-bottom:1px solid #eef0f2;">
    <section style="font-size:11px;">SOURCES</section>
  </section>
  <section style="padding:14px 16px 16px;"><section style="font-size:15px;">来源甲</section><section style="font-size:12px;">说明甲</section><section style="font-size:13px;">https://example.com/src</section></section>
</section>
<!-- /SANSHENG-SOURCES -->

<!-- AUDIO-CARD-START -->
<section>音频卡</section>
<!-- AUDIO-CARD-END -->
"""


@pytest.fixture
def parsed(tmp_path: Path):
    return xa.parse_markdown(FIXTURE_MD, tmp_path)


def test_title_strips_category_prefix(parsed):
    assert parsed["title"] == "测试标题：两条路"
    assert parsed["raw_title"].startswith("教程 | ")


def test_headings_bold_mark_links(parsed):
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "<h1>第一节</h1>" in html and "<h2>小标题</h2>" in html
    assert "<strong>加粗</strong>" in html and "<strong>高亮</strong>" in html
    assert '<a href="https://example.com/a">链接</a>' in html
    assert "`" not in html  # 行内代码去反引号


def test_table_becomes_key_value_list(parsed):
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "<table" not in html
    assert "<li><strong>用户名</strong>：abc@qq.com</li>" in html
    assert "<li><strong>端口</strong>：443</li>" in html


def test_image_divider_and_own_caption(parsed):
    kinds = [k for k, _ in parsed["blocks"]]
    assert kinds.count("image") == 2
    assert "divider" in kinds
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    # 正文自带图注（以 * 开头）时不重复贴 alt；信息图 alt 永不贴
    assert "<p><em>一张截图</em></p>" not in html
    assert "信息图标题" not in html
    assert "<em>这是正文自带的图注</em>" in html


def test_code_block_to_blockquotes_keeps_lang_tag(parsed):
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "<blockquote>[text]</blockquote><blockquote>第一行</blockquote><blockquote>第二行</blockquote>" in html


def test_lists_ordered_and_unordered(parsed):
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "<ul><li>项一</li><li>项二</li></ul>" in html
    assert "<ol><li>甲</li><li>乙</li></ol>" in html


def test_sources_parsed_and_machine_blocks_dropped(parsed):
    assert parsed["sources"] == ["来源甲：说明甲 https://example.com/src"]
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "音频卡" not in html and "SOURCES" not in html


def test_lead_quote_kept_as_blockquote(parsed):
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert html.startswith("<blockquote><strong>导读：</strong> 这是导读。</blockquote>")


# ---------------------------------------------------------------- 说明文字预检
def test_caption_weight_cjk_counts_double():
    assert xa.caption_weight("ab") == 2
    assert xa.caption_weight("中文") == 4
    assert xa.caption_weight("🏗") == 2


def test_caption_rejects_over_limit_url_hashtags_bait():
    too_long = "字" * 129  # 258 权重
    assert any("超过上限" in p for p in xa.check_caption(too_long))
    assert any("URL" in p for p in xa.check_caption("看这里 https://x.com/a"))
    assert any("裸域名" in p for p in xa.check_caption("去 sanshengai.top 看看"))  # X 会把裸域名自动转成 t.co 链接
    assert xa.check_caption("更新到 V1.77 了，共 3.5 万字") == []  # 小数点不是域名
    assert any("hashtag" in p for p in xa.check_caption("#AI 与 #Mac 的事"))
    assert any("诱饵" in p for p in xa.check_caption("觉得有用请点赞转发"))
    assert xa.check_caption("Mac 和安卓自带日历能双向同步，中间只有两个免费选择。") == []


# ---------------------------------------------------------------- 块序列校验
PLAN = [
    ("html", "<h1>标题</h1><p>段一</p>"),
    ("image", "/tmp/a.png"),
    ("html", "<p>段二</p><blockquote>引</blockquote><ul><li>项</li></ul>"),
    ("divider", ""),
    ("html", "<p>段三</p>"),
]
GOOD = [
    "longform-header-one|标题", "longform-unstyled|段一", "media|编辑",
    "longform-unstyled|段二", "longform-blockquote|引", "longform-unordered-list-item|项",
    "divider|", "longform-unstyled|段三", "longform-unstyled|",
]


def test_diff_blocks_passes_on_exact_match():
    assert xa.diff_blocks(PLAN, GOOD) == []


def test_diff_blocks_catches_paragraph_rendered_as_heading():
    bad = list(GOOD)
    bad[1] = "longform-header-one|段一"  # 文本一样、块类型错——09-19 发坏三篇的形态
    diffs = xa.diff_blocks(PLAN, bad)
    assert any("块类型 h1" in d for d in diffs)


def test_diff_blocks_catches_missing_text_and_extra_empty_blocks():
    missing = [b for b in GOOD if not b.endswith("|段二")]
    assert any(d.startswith("-段二") for d in xa.diff_blocks(PLAN, missing))
    extra_empty = GOOD[:2] + ["longform-unstyled|"] + GOOD[2:]
    assert any("多余空块" in d for d in xa.diff_blocks(PLAN, extra_empty))


def test_diff_blocks_tolerates_empty_between_media_and_placeholder_residue():
    plan = [("image", "/a"), ("image", "/b"), ("html", "<p>尾</p>")]
    ok = ["media|", "longform-unstyled|", "media|", "longform-unstyled|尾"]
    assert xa.diff_blocks(plan, ok) == []
    residue = ["media|", "longform-unstyled|XIMGPH_2", "media|", "longform-unstyled|尾"]
    assert any("占位符残留" in d for d in xa.diff_blocks(plan, residue))


def test_maturity_buckets():
    assert xa.maturity(1) == "early"
    assert xa.maturity(30) == "day3"
    assert xa.maturity(9999) == "plateau"
