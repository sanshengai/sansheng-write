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
