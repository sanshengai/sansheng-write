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
    assert any("裸域名" in p for p in xa.check_caption("去 example.com 看看"))  # X 会把裸域名自动转成 t.co 链接
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


# ---------------------------------------------------------------- X 版适配文件
def test_x_variant_preferred_over_wechat_final(tmp_path: Path):
    (tmp_path / "定稿.md").write_text("---\ntitle: 公众号版\n---\n\n正文 A\n", encoding="utf-8")
    assert xa.parse_article(tmp_path)["source"] == "定稿.md"
    (tmp_path / "定稿.x.md").write_text("---\ntitle: X 版\n---\n\n正文 B\n", encoding="utf-8")
    parsed = xa.parse_article(tmp_path)
    assert parsed["source"] == "定稿.x.md" and parsed["title"] == "X 版"
    assert "正文 A" not in "".join(v for k, v in parsed["blocks"] if k == "html")


def test_sources_without_closing_marker_stop_at_next_comment(tmp_path: Path):
    src = lambda name, url: (f'<section style="padding:14px 16px 16px;"><section style="font-size:15px;">{name}</section>'
                             f'<section style="font-size:13px;">{url}</section></section>')
    md = ("---\ntitle: t\n---\n\n正文\n\n<!-- SANSHENG-SOURCES -->\n<section>" + src("来源甲", "https://a.example/1") +
          "</section>\n<!-- 推荐阅读 -->\n<section>" + src("推荐乙", "https://example.com/x") +
          "</section>\n<!-- AUDIO-CARD-START -->\n<section>音频</section>\n<!-- AUDIO-CARD-END -->\n")
    parsed = xa.parse_markdown(md, tmp_path)
    assert parsed["sources"] == ["来源甲 https://a.example/1"]  # 推荐阅读那条不能混进信息来源


def test_post_matches_rejects_someone_elses_post():
    cap = "同样 10 万元本金、年化 8% 投 30 年：年费 0.15% 的宽基指数滚到约 96.6 万"
    title = "我用 AI 蒸馏了 15 本投资大师经典"
    assert xa.post_matches("示例账号 @example_handle · 1分钟 同样 10 万元本金、年化 8% 投 30 年：年费 0.15%…", cap, title)
    assert xa.post_matches("文章 我用 AI 蒸馏了 15 本投资大师经典，普通人该懂的理念全在这", "", title)
    # 09-19 实证：Premium+ 失效后发布静默失败，主页首条是上一篇（封号文），不能当成本篇
    assert not xa.post_matches("示例账号 · 3分钟 Anthropic 的透明度报告：2025 下半年封禁 145 万个账号", cap, title)
    assert not xa.post_matches("", cap, title)


def test_audio_card_at_top_does_not_truncate_body(tmp_path: Path):
    md = ("---\ntitle: t\n---\n\n> 导读\n\n<!-- AUDIO-CARD-START -->\n<section>音频卡</section>\n<!-- AUDIO-CARD-END -->\n\n"
          "# 标题\n\n正文第一段\n\n## 一节\n\n正文第二段\n")
    parsed = xa.parse_markdown(md, tmp_path)
    html = "".join(v for k, v in parsed["blocks"] if k == "html")
    assert "正文第一段" in html and "<h1>一节</h1>" in html and "音频卡" not in html


def test_code_block_blank_lines_dropped(tmp_path: Path):
    md = "---\ntitle: t\n---\n\n```bash\nuv tool install x\n\n# 或者 pip\npip install x\n```\n"
    html = "".join(v for k, v in xa.parse_markdown(md, tmp_path)["blocks"] if k == "html")
    assert "<blockquote></blockquote>" not in html and "<blockquote> </blockquote>" not in html
    assert html.count("<blockquote>") == 4  # [bash] + 3 行非空


# ---------------------------------------------------------------- X 版内容体检
def test_lint_blocks_declaration_first_line():
    md = "---\ntitle: t\n---\n\n# 标题\n\n本文 2026 年 4 月首发；9 月核过命令。\n\n正文。\n"
    errors, _ = xa.lint_x_source(md)
    assert any("首屏是声明" in e for e in errors)
    md2 = "# 标题\n\n> 截至 2026-09，以下价格已更新。\n\n正文。\n"
    assert any("首屏是声明" in e for e in xa.lint_x_source(md2)[0])


def test_lint_passes_conclusion_first_and_tail_provenance():
    md = ("# 标题\n\n先说结论：开机广告没了，空闲内存从 551 MB 涨到 988 MB。\n\n"
          "## 第一步：连上 ADB\n\n命令很短。\n\n---\n\n版本说明：本文 2026 年 4 月首发。\n")
    errors, warnings = xa.lint_x_source(md)
    assert errors == [] and warnings == []


def test_lint_blocks_placeholder_residue():
    md = "# 标题\n\n结论在前。\n\nXIMGPH_3\n\n正文。\n"
    assert any("占位符" in e for e in xa.lint_x_source(md)[0])


def test_lint_warns_wechat_tone_tables_and_daodu():
    md = ("# 标题\n\n> **导读：** 这是导读。\n\n你猜是谁？真的吗？为什么？\n\n"
          "不是因为视频短，是因为外包了。不是多一把刀，是多一个员工。\n\n**划重点**\n\n"
          "| 场景 | A | B |\n|---|---|---|\n| 长视频 | 慢 | 快 |\n")
    errors, warnings = xa.lint_x_source(md)
    assert errors == []
    joined = "\n".join(warnings)
    for key in ("导读", "问句", "不是…是…", "划重点", "表格"):
        assert key in joined, key


def test_lint_ignores_code_blocks_and_machine_tail():
    md = ("# 标题\n\n结论：能用。\n\n```text\n是不是？不是 a，是 b？\n```\n\n"
          "<!-- SANSHENG-SOURCES -->\n本文首发于？？？\n")
    assert xa.lint_x_source(md) == ([], [])


# ---------------------------------------------------------------- X 标题提示（title.md §禁用清单）
def test_lint_x_title_warns_prefix_and_noise_only():
    md = "---\ntitle: x\n---\n\n# 洞察 | Claude Code 和 Codex 怎么选？\n\n结论：按本地和云端分。\n"
    errors, warnings = xa.lint_x_source(md)
    assert errors == []
    joined = "\n".join(warnings)
    assert "分类前缀" in joined and "问句" in joined


def test_lint_x_title_reads_frontmatter_when_no_h1():
    md = "---\ntitle: 别再只会问 AI 了！\n---\n\n结论：能用。\n"
    joined = "\n".join(xa.lint_x_source(md)[1])
    assert "催促" in joined and "感叹号" in joined


def test_lint_x_title_passes_liked_titles():
    for t in ("德鲁克 5 本书，整理成 3 条今天能用的管理规则",
              "Claude 被封后，我的替补方案：Claude Code + Kimi Code + Antigravity"):
        assert xa.lint_x_title(t) == [], t


def fake_wechat(slug):
    # Synthetic IDs only; build the service URL without embedding a real article link.
    from urllib.parse import urlunsplit
    return urlunsplit(("https", "mp.weixin.qq.com", "/s/" + slug, "", ""))


@pytest.mark.parametrize("location,content", [
    (".state.json", {"stages": {"publish": {"wechat_url": fake_wechat("valid_article")}}}),
    ("过程记录/_website-sync-receipt.json", {"latest": {"wechat_url": fake_wechat("valid_article")}}),
    ("_website-sync-receipt.json", {"wechat_url": fake_wechat("valid_article")}),
    ("过程记录/_wechat-published-audio-receipt.json", {"proof_kind": "wechat_published_article_audio", "remote_verified": True, "wechat_url": fake_wechat("valid_article")}),
])
def test_formal_wechat_sources_are_read(tmp_path, location, content):
    import json
    path = tmp_path / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content))
    assert xa.wechat_url(tmp_path) == fake_wechat("valid_article")
    assert "公众号原文" in xa.tail_links(tmp_path, "Example", "", {})


@pytest.mark.parametrize("location,content", [
    ("过程记录/_publish-receipt.json", {"scope": "wechat-draft", "wechat_url": fake_wechat("valid_article")}),
    ("过程记录/_wechat-published-audio-receipt.json", {"proof_kind": "wechat_published_article_audio", "remote_verified": False, "wechat_url": fake_wechat("valid_article")}),
    ("过程记录/_wechat-published-audio-receipt.json", {"proof_kind": "wechat_draft_audio", "remote_verified": True, "wechat_url": fake_wechat("valid_article")}),
    ("过程记录/_website-sync-receipt.json", {"wechat_url": "https://mp.weixin.qq.com.attacker.test/s/fake"}),
    ("过程记录/_website-sync-receipt.json", {"attempts": [{"wechat_url": fake_wechat("old_attempt")}]}),
])
def test_draft_unverified_and_unrelated_sources_cannot_supply_wechat(tmp_path, location, content):
    import json
    path = tmp_path / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content))
    assert xa.wechat_url(tmp_path) == ""


def test_state_formal_link_takes_priority_over_old_receipt(tmp_path):
    import json
    (tmp_path / ".state.json").write_text(json.dumps({"stages": {"publish": {"wechat_url": fake_wechat("current")}}}))
    (tmp_path / "_website-sync-receipt.json").write_text(json.dumps({"wechat_url": fake_wechat("old")}))
    assert xa.wechat_url(tmp_path).endswith("/current")


def test_malformed_publication_containers_do_not_crash_or_leak_links(tmp_path):
    import json
    (tmp_path / ".state.json").write_text('{"stages":[]}')
    (tmp_path / "_website-sync-receipt.json").write_text(json.dumps({"latest": [{"wechat_url": fake_wechat("untrusted")}]}))
    assert xa.wechat_url(tmp_path) == ""
