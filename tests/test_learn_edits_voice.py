# -*- coding: utf-8 -*-
"""learn_edits 自动灌库（声纹）纯函数回归 — 不碰真实 voice-samples.md 文件。"""
from scripts import learn_edits as L


def test_split_paragraphs_basic():
    txt = "段一。\n\n段二有内容。\n\n\n段三。"
    assert L._split_paragraphs(txt) == ["段一。", "段二有内容。", "段三。"]


def test_is_voice_sample_excludes_non_prose():
    assert L._is_voice_sample("# 这是一级标题") is False
    assert L._is_voice_sample("> 引用块这种也不当声纹样本，哪怕够长也排除掉它免得污染") is False
    assert L._is_voice_sample("- 列表项一二三\n- 列表项四五六\n- 列表项七八九十") is False
    assert L._is_voice_sample("太短") is False
    # 够长的散文段通过（>50 字）
    prose = ("技术这东西，不落到你具体某天省下的那两小时上，吹得再高也是别人的故事，跟你没关系；"
             "我宁可写一句你今晚就能用上的话，也不写十句听着热血的空话。")
    assert L._is_voice_sample(prose) is True


def test_select_voice_candidates_picks_edited_and_new_excludes_unchanged():
    draft = (
        "AI 写的开头，众所周知人工智能正在改变世界，方方面面都有影响，这是机器写的套话段落充数。\n\n"
        "这是一段会被 作者 大改的话，原本写得很书面很套路，充满了潜移默化和从根本上这类副词补丁，读起来像机器。"
    )
    final = (
        # 第一段与 draft 几乎一致 → 不收（作者 没改 = AI 原段）
        "AI 写的开头，众所周知人工智能正在改变世界，方方面面都有影响，这是机器写的套话段落充数。\n\n"
        # 第二段被实质重写 → 收
        "这段我重写了：别整那些虚的，就是机器现在能干活了，你昨天还在手搓的事今天它十分钟给你交差，差距就这么实在。\n\n"
        # 第三段全新（draft 无近似）→ 收
        "我后来又补了一整段全新的话，纯粹是我自己想说的——技术这东西，不落到你具体某天省下的两小时上，吹得再高也是别人的故事。"
    )
    cands = L._select_voice_candidates(draft, final)
    assert len(cands) == 2
    assert not any(c.startswith("AI 写的开头") for c in cands)   # 未改 AI 段被排除
    assert any("我重写了" in c for c in cands)                   # 重写段被收
    assert any("全新的话" in c for c in cands)                   # 新写段被收


def test_select_voice_candidates_unchanged_doc_yields_nothing():
    same = "这是一整段没有任何改动的散文，从草稿到定稿一字未改，不该被当成 作者 的新声音灌进库里去。"
    assert L._select_voice_candidates(same, same) == []


# ── B2（2026-09-22）：HTML 模板块不得进声纹库 ─────────────────────────────────
AUDIO_CARD = (
    "<!-- AUDIO-CARD-START -->\n"
    '<section data-audio-role="theme" style="margin: 20px 0; padding: 16px; border: 1px solid #d7e3ea;">\n'
    '  <section style="display: table; width: 100%; margin-bottom: 12px;">\n'
    '    <section style="display: table-cell; font-size: 14px; color: #2F6F8F; font-weight: bold;">'
    "<span>🎵</span>阅读配乐｜本文主题曲</section>\n"
    "  </section>\n"
    '  <p style="text-align: center; color: #b0b6bb;">（👉 删除本段文字，并插入主题曲音频）</p>\n'
    "</section>\n"
    "<!-- AUDIO-CARD-END -->"
)
PROSE = ("技术这东西，不落到你具体某天省下的那两小时上，吹得再高也是别人的故事，跟你没关系；"
         "我宁可写一句你今晚就能用上的话，也不写十句听着热血的空话。")


def test_is_voice_sample_rejects_html_template_blocks():
    """🔴 反例：一段 AUDIO-CARD HTML 必须 False（原来它够长、不以 #/-/> 开头，会被当散文收进去）。"""
    assert L._is_voice_sample(AUDIO_CARD) is False
    assert L._is_voice_sample('<section style="margin:22px 8px;border:1px solid #d7e3ea;">'
                              "<section>DEEP READ</section><section>继续往下读，模型每周都在变。</section></section>") is False
    assert L._is_voice_sample("<!-- SANSHENG-SOURCES -->\n这里本来是信源卡片，前面有一整行 HTML 注释标记，够长也不能收。") is False
    assert L._is_voice_sample(PROSE) is True   # 散文段仍 True


def test_strip_template_zones_removes_paired_blocks_and_endmatter_tail():
    tail_prose = "这一段在 DEEP-READ 标记之后，是尾注区里机器填的说明文字，够长、不带任何 HTML，光靠段首判断拦不住它。"
    inner_prose = "这一段夹在 AUDIO-CARD 成对标记中间但自己不带标签，是模板里的说明文案，同样不是作者写的声音样本。"
    final = (
        PROSE + "\n\n"
        + "<!-- AUDIO-CARD-START -->\n<section>x</section>\n\n" + inner_prose + "\n\n<!-- AUDIO-CARD-END -->\n\n"
        + "<!-- SANSHENG-VISUAL-START:01 -->\n![图](a.png)\n<!-- SANSHENG-VISUAL-END:01 -->\n\n"
        + "第二段正文，也是作者自己写的，讲的是别的事情，但同样够长够实在，应该被当成候选段留下来参与比对。\n\n"
        + "<!-- SANSHENG-DEEP-READ -->\n<section>deep</section>\n\n" + tail_prose + "\n\n"
        + "<!-- SANSHENG-SOURCES -->\n<section>src</section>"
    )
    paras = L._split_paragraphs(L._strip_template_zones(final))
    assert paras[0] == PROSE and any(p.startswith("第二段正文") for p in paras)
    assert not any("<!--" in p or "<section" in p for p in paras)
    assert inner_prose not in paras and tail_prose not in paras
    # 没有标记的旧稿原样返回
    assert L._strip_template_zones(PROSE + "\n\n第二段。") == PROSE + "\n\n第二段。"


def test_select_voice_candidates_never_picks_template_blocks(monkeypatch):
    """端到端：draft 无模板块、final 带模板块 → 模板块与 draft 相似度极低，原逻辑会当「作者新写」收进去。"""
    monkeypatch.setattr(L, "_jev_voice_client", lambda: None)   # 纯 difflib 路径，不碰真台账
    draft = PROSE
    tail_prose = "这一段在 DEEP-READ 标记之后，是尾注区里机器填的说明文字，够长、不带任何 HTML，光靠段首判断拦不住它。"
    final = (PROSE + "\n\n" + AUDIO_CARD + "\n\n"
             + "我后来又补了一整段全新的话，纯粹是我自己想说的——技术这东西，不落到你具体某天省下的两小时上，吹得再高也是别人的故事。\n\n"
             + "<!-- SANSHENG-DEEP-READ -->\n\n" + tail_prose)
    cands = L._select_voice_candidates(draft, final)
    assert len(cands) == 1 and "全新的话" in cands[0]
    assert not any("AUDIO-CARD" in c or "<section" in c or c == tail_prose for c in cands)
