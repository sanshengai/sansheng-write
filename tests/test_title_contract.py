"""标题公式门（contracts.audit_title_contract）。

真实翻车样本：内部结构编号 +「你转发过的那些…多半不是他说的」揭穿式反差同时命中，
散文规则拦不住，故下沉为机器门。「那句话兑现在正文哪一节」是语义判断，
不在本门范围，故不为它写用例。

两档语义：`fail` = 硬禁（阻断）；`warn` = 配额或有条件可用（只提示），
对应 title.md 里「自夸词是配额，不是禁令」。
"""

from scripts.contracts import audit_title_contract, verify_title_contract


def test_quote_style_title_passes():
    # 作者选定的原话型标题
    r = audit_title_contract("分享 | 爱因斯坦传：我没有特别的天赋，只有强烈的好奇")
    assert r["verdict"] == "ok", r["notes"]


def test_short_quote_title_passes():
    r = audit_title_contract("分享 | 曾国藩传：结硬寨，打呆仗")
    assert r["verdict"] == "ok", r["notes"]


def test_scene_style_title_passes():
    r = audit_title_contract("分享 | 爱因斯坦传：广义相对论那八年，他怎么走过来的")
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


def test_self_praise_is_quota_not_ban():
    r = audit_title_contract("分享 | 曾国藩传：目前全网最全")
    assert r["verdict"] == "warn", r["notes"]
    assert any("配额" in w for w in r["warnings"])


def test_not_a_but_b_only_warns():
    r = audit_title_contract("洞察 | Claude Code：不是编辑器，而是命令行 agent")
    assert r["verdict"] == "warn", r["notes"]
    assert r["violations"] == []


def test_rejects_over_length():
    long_tail = "四本传记连同语录与百科逐章蒸馏成一页可查证的网页每句都能点回原书出处"
    r = audit_title_contract(f"洞察 | 爱因斯坦：{long_tail}")
    assert r["verdict"] == "fail"
    assert any("字位" in v for v in r["violations"])


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
