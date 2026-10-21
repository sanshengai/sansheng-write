"""标题门（contracts.audit_title_contract）。

真实翻车样本：内部结构编号 +「你转发过的那些…多半不是他说的」揭穿式反差同时命中，
散文规则拦不住，故下沉为机器门。「有没有可得物、兑现在正文哪一节」是语义判断，
不在本门范围，故不为它写用例。

两档语义：`fail` = 硬禁（阻断）；`warn` = 噪头词、问句、翻转句、自夸词、接口长度（只提示）。
2026-10-21 起不再有字数上限，也不再硬要求「锚点：一句话」冒号结构。
"""

from scripts.contracts import (
    audit_cover_title_pair,
    audit_title_contract,
    verify_title_contract,
)


def test_liked_object_plus_takeaway_titles_pass():
    # 作者明确喜欢的两条改写（title.md §核心写法）；第一条没有冒号也要过
    for good in (
        "分享 | 德鲁克 5 本书，整理成 3 条今天能用的管理规则",
        "分享 | Claude 被封后，我的替补方案：Claude Code + Kimi Code + Antigravity",
        "分享 | Claude Code 清理家里的电视：开机广告没了，内存多出 437 MB",
    ):
        r = audit_title_contract(good)
        assert r["violations"] == [], (good, r["notes"])
        assert not any("可得物" in w for w in r["warnings"]), good


def test_quote_style_title_still_passes_gate():
    # 原话型不再是默认写法，但作者要求时仍可用，机器门不拦
    r = audit_title_contract("分享 | 曾国藩传：结硬寨，打呆仗")
    assert r["verdict"] == "ok", r["notes"]


def test_rejects_chapter_count():
    r = audit_title_contract("洞察 | 「爱因斯坦」16 章：四本传记蒸馏成一页")
    assert r["verdict"] == "fail"
    assert any("内部结构编号" in v for v in r["violations"])


def test_rejects_reader_accusing_reversal():
    r = audit_title_contract("洞察 | 曾国藩：你买过的《冰鉴》，不是他写的")
    assert r["verdict"] == "fail"
    assert any("揭穿式反差" in v for v in r["violations"])


def test_rejects_negation_reveal():
    r = audit_title_contract("洞察 | 爱因斯坦名言：多半不是他说的")
    assert r["verdict"] == "fail"
    assert any("揭穿式否定" in v for v in r["violations"])


def test_rejects_suspense_words():
    r = audit_title_contract("洞察 | Claude Code 涨价：这背后的真相")
    assert r["verdict"] == "fail"
    assert any("悬念" in v for v in r["violations"])


def test_requires_category_tag_prefix():
    r = audit_title_contract("爱因斯坦：四本传记蒸馏成一页，每句都能点回原书")
    assert r["verdict"] == "fail"
    assert any("分类标签前缀" in v for v in r["violations"])


def test_rejects_reveal_sentence_family():
    for bad in (
        "洞察 | 某模型：表面是降价，背后是抢开发者",
        "洞察 | 某模型：看起来像升级，其实是砍功能",
        "洞察 | 某模型：看似便宜，其实更贵",
        "洞察 | 某模型：原来真正的瓶颈是显存",
        "洞察 | 某模型：这不算升级，实际是换壳",
    ):
        r = audit_title_contract(bad)
        assert r["verdict"] == "fail", bad
        assert any("揭穿式句式" in v for v in r["violations"]), bad


def test_self_praise_warns_not_ban():
    r = audit_title_contract("分享 | 曾国藩传：目前全网最全")
    assert r["verdict"] == "warn", r["notes"]
    assert any("配额" in w for w in r["warnings"])


def test_not_a_but_b_only_warns():
    r = audit_title_contract("洞察 | Claude Code：不是编辑器，而是命令行 agent")
    assert r["verdict"] == "warn", r["notes"]
    assert r["violations"] == []
    assert any("翻转句" in w for w in r["warnings"])


def test_long_title_is_not_a_violation():
    # 不设字数上限；只有超过公众号接口文档的 32 字位时提示一句
    long_tail = "四本传记连同语录与百科逐章蒸馏成一页可查证的网页每句都能点回原书出处"
    r = audit_title_contract(f"分享 | 爱因斯坦传：{long_tail}")
    assert r["violations"] == []
    assert r["verdict"] == "warn"
    assert any("draft/add" in w for w in r["warnings"])


def test_title_under_api_width_has_no_length_note():
    r = audit_title_contract("分享 | 德鲁克 5 本书，整理成 3 条今天能用的管理规则")
    assert not any("字位" in w for w in r["warnings"])


def test_noise_words_warn_not_fail():
    for bad, key in (
        ("分享 | 别再给 API 多花钱：8 个开源路由", "催促"),
        ("分享 | Cloudflare 域名邮箱：保姆级配置教程", "营销"),
        ("洞察 | Claude Code 和 Codex 怎么选？", "问句"),
        ("分享 | TRAE 全面升级，太像 Codex 了！", "感叹号"),
        ("洞察 | 几十块钱的 AI 课，卖的其实是「目标」", "揭穿"),
        ("洞察 | 德鲁克五本书，反复讲的不是怎么管人，是怎么负责", "翻转"),
        ("资讯 | 深度解读：某模型发布", "空修饰"),
    ):
        r = audit_title_contract(bad)
        assert r["violations"] == [], (bad, r["notes"])
        assert r["verdict"] == "warn", bad
        assert any(key in w for w in r["warnings"]), (bad, r["warnings"])


def test_single_clause_title_warns_missing_takeaway():
    r = audit_title_contract("洞察 | 从抢年轻人到抢老人中国的生意变了")
    assert r["verdict"] == "warn"
    assert any("可得物" in w for w in r["warnings"])


def test_normal_version_number_in_product_name_survives():
    # 产品名里的数字不是内部编号：Claude 4.5 / GPT-5 这类不能误杀
    r = audit_title_contract("资讯 | Gemini 3 发布：多模态实测能替掉哪几步")
    assert r["verdict"] == "ok", r["notes"]


def test_empty_title_skips():
    assert audit_title_contract("")["verdict"] == "skip"


def test_verify_reads_meta(tmp_path):
    (tmp_path / "article-meta.yaml").write_text(
        'title: "洞察 | 「曾国藩」15 章：你买过的《冰鉴》，不是他写的"\n',
        encoding="utf-8",
    )
    r = verify_title_contract(str(tmp_path))
    assert r["verdict"] == "fail"
    assert len(r["violations"]) >= 2  # 编号 + 反差


def test_verify_skips_without_meta(tmp_path):
    assert verify_title_contract(str(tmp_path))["verdict"] == "skip"


# --- 封面 L1/L2 与外标题分工（锚点有意重复，那一句不许重复）---

def test_cover_pair_passes_for_liked_examples():
    # title.md §两个配套范例
    assert audit_cover_title_pair(
        "分享 | 德鲁克 5 本书，整理成 3 条今天能用的管理规则",
        "德鲁克 5 本书", "1946 到 1999 一张地图",
    )["verdict"] == "ok"
    assert audit_cover_title_pair(
        "分享 | Claude 被封后，我的替补方案：Claude Code + Kimi Code + Antigravity",
        "Claude 被封", "ORCA 编成一支队",
    )["verdict"] == "ok"


def test_cover_pair_passes_when_l2_uses_another_fill():
    r = audit_cover_title_pair(
        "分享 | 爱因斯坦传：我没有特别的天赋，只有强烈的好奇",
        "爱因斯坦传", "每句都能点回原信",
    )
    assert r["verdict"] == "ok", r["notes"]


def test_cover_pair_passes_for_zeng():
    r = audit_cover_title_pair(
        "分享 | 曾国藩传：结硬寨，打呆仗", "曾国藩传", "785 封家书原文",
    )
    assert r["verdict"] == "ok", r["notes"]


def test_cover_pair_rejects_shortened_copy_of_title():
    r = audit_cover_title_pair(
        "分享 | 爱因斯坦传：我没有特别的天赋，只有强烈的好奇",
        "爱因斯坦传", "只有强烈的好奇",
    )
    assert r["verdict"] == "fail"
    assert any("砍短" in v for v in r["violations"])


def test_cover_pair_warns_on_shared_words():
    r = audit_cover_title_pair(
        "分享 | 曾国藩传：家书奏稿日记，一页读完", "曾国藩传", "家书奏稿摊在一页",
    )
    assert r["verdict"] == "warn"
    assert any("共用" in w for w in r["warnings"])


def test_cover_pair_warns_when_anchor_drifts():
    r = audit_cover_title_pair(
        "分享 | 爱因斯坦传：我没有特别的天赋，只有强烈的好奇",
        "相对论八年", "每句都能点回原信",
    )
    assert r["verdict"] == "warn"
    assert any("锚点可能漂" in w for w in r["warnings"])


def test_cover_pair_skips_without_line2():
    assert audit_cover_title_pair("分享 | 爱因斯坦传：随便", "爱因斯坦传", "")["verdict"] == "skip"
