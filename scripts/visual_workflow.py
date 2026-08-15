#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile a restricted article visual plan into canonical renderer prompts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

try:
    from . import baoyu_contract
except ImportError:  # pragma: no cover - direct script execution
    import baoyu_contract

try:
    from .evidence import stable_digest
    from .profile_config import visual_profile
    from .visual_contracts import cover_text_contract
except ImportError:  # pragma: no cover - direct script execution
    from evidence import stable_digest
    from profile_config import visual_profile
    from visual_contracts import cover_text_contract


VISUAL_PLAN_FILE = "visual-plan.json"
VISUAL_PRODUCER = "sansheng-write.visual-planner"
BAOYU_ARTICLE_METHOD = "baoyu-article-illustrator"
BAOYU_INFOGRAPHIC_METHOD = "baoyu-infographic"
# 🔴 全站信息图统一粘土风，不再按题材做风格路由（2026-07-29 作者拍板）。
# 旧机制让 infographic_subject 这个主观判断去决定视觉：填 ai-product 走 claymation、
# 填 phenomenon 走 morandi-journal，而三处校验只查「subject 与 style 是否配套」，
# 从不查 subject 本身填得对不对——填错之后整条链自洽，六层门全绿、QA 全绿、封存通过，
# 作者来回退了四五轮都没有任何闸门报警。风险源就是这条路由本身，直接砍掉。
# morandi-journal 配方仍留在 profile 的 visual.profiles 里封存，只是不再被路由到。
INFOGRAPHIC_STYLE = "claymation"
SUPPORTED_STYLES = {INFOGRAPHIC_STYLE}
PROFILE_BY_STYLE = {
    "claymation": "warm-light-clay",
    "morandi-journal": "morandi-journal",
}
_SUSPICIOUS_DOUBLE_CHARACTER_CLUSTER = re.compile(
    r"([\u4e00-\u9fff])\1([\u4e00-\u9fff])\2"
)
_CJK = re.compile(r"[\u4e00-\u9fff]")
# \ud83d\udd34 layout \u4f1a\u539f\u6837\u8fdb prompt \u7684 COMPOSITION GUIDANCE \u6bb5\u3002\u90a3\u6bb5\u5e26\u7740\u300c\u7edd\u4e0d\u53ef\u6e32\u67d3\u4e3a
# \u53ef\u89c1\u6587\u5b57\u300d\u7684\u7981\u4ee4\uff0c\u4f46\u7981\u4ee4\u538b\u5f97\u4f4f\u77ed\u6807\u7b7e\uff0c\u538b\u4e0d\u4f4f\u6574\u6bb5\u4e2d\u6587\u6563\u6587\u2014\u2014\u6a21\u578b\u770b\u89c1\u4e2d\u6587\u5c31\u60f3\u753b\u3002
# \u5b9e\u6d4b\uff0882-\u683c\u62c9\u5fb7\u5a01\u5c14\u4e94\u672c\u4e66\uff0c\u540c\u4e00\u6761\u6d41\u6c34\u7ebf\u3001\u540c\u4e00\u4efd\u914d\u65b9\u3001\u540c\u4e00\u4e2a\u6a21\u578b\uff09\uff1a
#   layout \u4e2d\u6587 0 \u5b57   \u2192 hero / infographic-04 \u4e00\u6b21\u6210\u529f
#   layout \u4e2d\u6587 108 \u5b57 \u2192 infographic-01 \u8fde\u5e9f 4 \u7248\uff08\u6807\u7b7e\u9519\u4f4d\u3001\u591a\u753b\u300c\u8bad\u7ec3\u4e0e\u6bd4\u8d5b\u300d\u3001
#                        \u6807\u9898\u91cd\u590d\u4e24\u6b21\u3001\u4e71\u7801\u300c50\u5bf9\u9009\u4e2d\uff0c\u7275\u300d\uff09
#   layout \u4e2d\u6587 158 \u5b57 \u2192 infographic-02 \u4e71\u7801\u300c\u5b9e\u8fd1\u4ec6\u79bd\u4eba\u7c92\u300d
#   layout \u4e2d\u6587 181 \u5b57 \u2192 infographic-03 \u591a\u753b\u300c\u6c61\u67d3\u300d
# \u300c\u8bad\u7ec3\u4e0e\u6bd4\u8d5b\u300d\u6b63\u662f layout \u91cc\u300c\u7ecf\u7531\u5c11\u5e74\u9009\u62d4\u3001\u8bad\u7ec3\u548c\u6bd4\u8d5b\u65f6\u95f4\u300d\u88ab\u7167\u7740\u753b\u4e86\u51fa\u6765\u3002
# \u7a33\u5b9a\u8dd1\u5b8c 100+ \u7bc7\u7684\u5386\u53f2\u6587\u7ae0\uff0clayout \u4e2d\u6587\u90fd\u5728 11-20 \u5b57\uff08"\u4e09\u6bb5\u5bf9\u6bd4"\u8fd9\u7c7b\u77ed\u6807\u7b7e\uff09\u3002
# \u9608\u503c\u53d6 24\uff1a\u5bb9\u5f97\u4e0b\u5386\u53f2\u5199\u6cd5\uff0c\u62e6\u5f97\u4f4f\u6563\u6587\u3002\u6784\u56fe\u7ec6\u8282\u8bf7\u5199\u82f1\u6587\uff0c\u82f1\u6587\u957f\u63cf\u8ff0\u5b9e\u6d4b\u65e0\u5bb3
# \uff08infographic-04 \u7528\u4e86 538 \u5b57\u82f1\u6587\uff0c\u4e00\u6b21\u6210\u529f\uff09\u3002
LAYOUT_CJK_MAX = 24
INFOGRAPHIC_LAYOUTS = {
    "linear-progression": "one directional sequence with clearly ordered causal stages",
    "hub-spoke": "one central subject connected to distinct contributing conditions and one outcome",
    "binary-comparison": "two separated evidence zones with a controlled transition between them",
    "winding-roadmap": "one continuous route with ordered milestones and a decisive final action",
}


# ============================================================================
# 视觉任务单的三条「编译期预防」检查（2026-08-14 第 89 篇实跑后新增）
#
# 背景：那一篇机械链共发起 45 次生图，其中 39 次是重渲 —— 必要量的 7.5 倍，
# 同时也是撞 429 限流的主因。逐次复盘后，其中约 30 次可由下面三条纯字符串
# 检查在**编译期**拦掉，根本不必等图渲出来再由 visual-qa 发现。
# 生图一次几十秒且吃配额，把可机器判的错留到渲染后，是最贵的一种晚发现。
# ============================================================================

# 否定式措辞：生图模型对 "no X" 基本不敏感（实测连写三轮 no sign board /
# no rounded plate / no punctuation，模型照样加底板；改成正面描述当轮就对）。
_LAYOUT_NEGATIVE_PATTERNS = re.compile(
    r"\b(no|not|without|avoid|never|don't|do not|free of)\b|不要|禁止|不得|不能|没有",
    re.IGNORECASE,
)

# 「N 个节点/里程碑」这类表述会诱导模型给每个节点各贴一遍标签
# （实测：eight ordered stops → 同一个词渲了 8 遍；three milestones → 3 遍）。
# 数量词与名词之间允许夹 0-2 个修饰词（ordered / passed / equal / small …），
# 否则 "three passed milestones" 这类会漏网（本文件配套测试当场抓到过）。
_LAYOUT_NODE_COUNT = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:[a-z-]+\s+){0,2}"
    r"(stops?|steps?|milestones?|nodes?|points?|stages?|segments?)\b",
    re.IGNORECASE,
)
# 声明「节点不带文字」的正面表述，命中任一即认为已规避
_LAYOUT_NODE_TEXTFREE = re.compile(
    r"carry no text|no text on|without any lettering|free of any lettering|"
    r"no lettering|carries no label|no label on|text appears in exactly",
    re.IGNORECASE,
)


def _longest_common_substring(a: str, b: str) -> str:
    """最长公共**子串**（连续），不是子序列。"""
    if not a or not b:
        return ""
    prev = [0] * (len(b) + 1)
    best_len, best_end = 0, 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], i
        prev = cur
    return a[best_end - best_len:best_end]


# 一张图内多条中文短句之间允许的最长公共子串。2 起就显著掉首过率。
_TEXT_OVERLAP_MAX = 1


def _text_overlap_errors(label: str, title: str, expected: list[str]) -> list[str]:
    """同一张图里的中文短句之间，共享的连续字符不得超过 1 个。

    2026-08-15 实测（Banana 2，第 89 篇四张信息图，每张 3-6 次）：

        条目间最长公共子串   首过率
              0             6/6  = 100%
              1             6/6  = 100%
              2             3/6  =  50%
              4（完整包含）  0/6  =   0%

    机理：模型在同一张画布上摆多条短句时，共享字越多越容易「串台」——
    把某条渲两遍、把 A 的字渲到 B 的位置、或干脆把短句拆成单字铺满节点。
    实测全库 36 张信息图里有 21 张（58%）重叠 ≥2，这是重渲量的主要来源之一。

    原实现只拦「完整包含」（全库 36 张里仅命中 2 张），漏掉了重叠 2-3 的
    19 张 —— 而那一档的首过率只有 50%。
    """
    errors: list[str] = []
    values = [str(v).strip() for v in expected if str(v).strip()]
    title = (title or "").strip()

    for value in values:
        if title and value != title and value in title:
            errors.append(
                f"{label}.expected_text「{value}」是 title「{title}」的子串 —— "
                f"渲出来会出现两次，必然违反 visual-qa 的 required_text"
                f"「整图恰好一次」硬门。请改写 title 使其不含任何标签词"
            )

    lines = ([title] if title else []) + values
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if a == b or (a, b) in seen:
                continue
            seen.add((a, b))
            if a in b or b in a:
                if a in values and b in values:
                    errors.append(
                        f"{label}.expected_text 存在互相包含的两条：「{a}」与「{b}」—— "
                        f"短的那条会被判出现两次。请改写成互不包含的措辞"
                    )
                continue
            shared = _longest_common_substring(a, b)
            if len(shared) > _TEXT_OVERLAP_MAX:
                errors.append(
                    f"{label} 的「{a}」与「{b}」共享了 {len(shared)} 个连续字"
                    f"「{shared}」—— 实测重叠 ≥2 时首过率掉到 50%（重叠 ≤1 时是 100%）。"
                    f"模型会把两条串在一起：渲重复、错位、或拆成单字铺满节点。"
                    f"请改写其中一条，把重复的字挪开"
                )
    return errors


def _layout_negative_phrasing_errors(label: str, layout: str) -> list[str]:
    """layout 用否定式描述构图 → 生图模型基本无视，白渲一轮。"""
    if not layout:
        return []
    hit = _LAYOUT_NEGATIVE_PATTERNS.search(layout)
    if not hit:
        return []
    return [
        f"{label}.layout 含否定式措辞「{hit.group(0)}」—— 生图模型对 no/不要 这类"
        f"指令基本不敏感（实测连写三轮 no sign board / no rounded plate，模型照样加底板；"
        f"改成正面描述「像标题那样的独立立体黏土字」当轮即对）。"
        f"请改写成**正面描述你要什么**，而不是列举不要什么"
    ]


# 抽象几何词：只写这些等于没告诉模型画什么。
_LAYOUT_ABSTRACT_ONLY = re.compile(
    r"\b(block|blocks|node|nodes|cluster|clusters|hub|spine|column|columns|"
    r"panel|panels|box|boxes|shape|shapes|band|bands|segment|segments|"
    r"zone|zones|area|areas|section|sections|group|groups|row|rows|"
    r"circle|circles|square|squares|rectangle|rectangles|bar|bars|"
    r"spoke|spokes|arrow|arrows|line|lines|layer|layers|tier|tiers)\b",
    re.IGNORECASE,
)
# 具体物象：能让模型"有活干"的实体名词。命中任一即认为 layout 给了可画的东西。
_LAYOUT_CONCRETE_SUBJECT = re.compile(
    r"\b(robot|robots|house|houses|building|buildings|cart|carts|truck|trucks|"
    r"car|cars|train|trains|bridge|bridges|road|roads|machine|machines|"
    r"worker|workers|figure|figures|person|people|hand|hands|tree|trees|"
    r"plant|plants|seed|seeds|book|books|desk|desks|chair|chairs|door|doors|"
    r"window|windows|ladder|ladders|stair|stairs|boat|boats|bag|bags|"
    r"box of|jar|jars|bottle|bottles|cup|cups|bowl|bowls|coin|coins|"
    r"key|keys|lock|locks|clock|clocks|lamp|lamps|flag|flags|tent|tents|"
    r"brick|bricks|stone|stones|rock|rocks|slab|slabs|crate|crates|"
    r"shelf|shelves|basket|baskets|bucket|buckets|scale|balance|"
    r"factory|shop|store|tower|wall|fence|gate|path|river|mountain|"
    r"conveyor|gear|gears|pipe|pipes|valve|switch|button|lever)\b",
    re.IGNORECASE,
)


# 自带文字属性的物件：现实里它们表面就写着字，模型照着画就会渲出计划外的文字。
_LAYOUT_TEXTUAL_PROP = re.compile(
    r"\b(calendar|newspaper|magazine|book|books|page|pages|document|documents|"
    r"sign|signs|signboard|signpost|billboard|poster|posters|banner|banners|"
    r"screen|screens|monitor|display|dashboard|scoreboard|whiteboard|blackboard|"
    r"chalkboard|noticeboard|menu|menus|ticket|tickets|receipt|receipts|"
    r"invoice|certificate|diploma|notebook|ledger|chart|charts|graph|graphs|"
    r"spreadsheet|scroll|manuscript|nameplate|plaque|passport|invitation)\b",
    # 🔴 刻意**不收** label / tag / note / letter / form / map / badge：
    #    在 layout 里 "one group label beside the left column" 说的是**我们自己的
    #    标签文字**（计划内、白名单里的那几条），不是「一件写着字的道具」。
    #    第一版把 label 收进来，当场误伤了两份合规 fixture —— 词表宁可窄一点，
    #    真漏了还有 visual-qa 兜底；误伤会逼作者改掉本来正确的写法。
    re.IGNORECASE,
)


def _layout_textual_prop_errors(label: str, layout: str) -> list[str]:
    """layout 提到自带文字的物件 → 模型往那件东西上写计划外的字。

    🔴 2026-08-16 实证。同一条生产管线、同一份 allowlist、同样的具体物象要求，
    layout 里只要留着 "like a calendar strip"，条幅上就反复渲出「月三月月日」
    「1月 2月 3月 23 24 25 26」这类日期字 —— 6 次里翻车 3 次，且每次都翻在
    那个日历上。把这一个词换成 "a tall smooth clay column"，其余一字不改。

    机理和抽象几何那条相反但同源：抽象几何是「没东西可画所以拿文字填」，
    自带文字的物件是「这东西现实里本来就写着字，所以照着写」。两条都指向
    同一件事 —— 画面里每一块地方都得有明确的、非文字的内容。

    日历、报纸、招牌、屏幕、书页、图表这类物件在信息图里很自然会被想到，
    正因为自然才更要拦：它是最容易不知不觉写进 layout 的一类词。
    """
    if not layout:
        return []
    hit = _LAYOUT_TEXTUAL_PROP.search(layout)
    if not hit:
        return []
    return [
        f"{label}.layout 出现自带文字的物件「{hit.group(0)}」—— 这类东西现实里表面就写着字，"
        f"模型会照着往上写，渲出计划外的文字（实测 like a calendar strip 让条幅上反复"
        f"出现「月三月月日」这类日期字，6 次翻 3 次且每次都翻在日历上）。"
        f"换成不带文字的实体：条幅→光面黏土立柱、报纸→卷起的纸卷、招牌→空白木牌、"
        f"屏幕→纯色方块。要的是形状和位置，不是那件东西的文字属性"
    ]


def _layout_concrete_subject_errors(label: str, layout: str) -> list[str]:
    """layout 只写抽象几何、没给可画的实体 → 模型拿文字填满画面。

    🔴 2026-08-15 实测，这是三个因子里贡献最大的一条（+42 个百分点）。

    同一张图、同一个模型（Banana 2）、同样修好的 allowlist，只改 SCENE：

        SCENE 写法                                          首过率
        "One vertical spine, largest block at top…"          3/6 = 50%
        "五个小机器人各举一面旗站成一列，右边三个"            5/6 = 83%

        "A central hub with spokes radiating to two clusters" 3/6 = 50%
        "三座小房子刚被搬上新地基，五座还在裂开的旧地基上"    6/6 = 100%

    机理：扩散模型必须把画布填满。SCENE 只给 block / node / cluster 这类
    抽象几何时，模型没有可画的实体，就把**标签文字**当成填充物 —— 拆成单字
    铺到每个方块上、把标签渲两遍、或在空白处补乱码汉字。给它具体东西画，
    它就不折腾文字了。

    附带收益：出图的视觉质量和语义准确度都明显更高（房子/机器人/裂开的地基
    比抽象方块好看，也更贴题）。
    """
    if not layout:
        return []
    if _LAYOUT_CONCRETE_SUBJECT.search(layout):
        return []
    abstract = _LAYOUT_ABSTRACT_ONLY.findall(layout)
    if not abstract:
        return []
    uniq = sorted({a.lower() for a in abstract})
    return [
        f"{label}.layout 只有抽象几何（{'、'.join(uniq[:5])}），没给模型任何可画的实体 —— "
        f"实测这一条最伤：首过率 50% vs 具体物象的 83-100%。"
        f"扩散模型必须把画布填满，没东西画就拿**标签文字**当填充物"
        f"（拆成单字铺到方块上、把标签渲两遍、空白处补乱码汉字）。"
        f"请把几何换成能画的东西 —— 不是「五个方块」而是"
        f"「五个小机器人各举一面旗」，不是「中心枢纽连着两簇节点」而是"
        f"「三座小房子刚被搬上新地基，五座还留在裂开的旧地基上」"
    ]


def _layout_node_label_errors(label: str, layout: str) -> list[str]:
    """layout 提到节点数量却没声明节点无文字 → 模型给每个节点复制一遍标签。"""
    if not layout:
        return []
    hit = _LAYOUT_NODE_COUNT.search(layout)
    if not hit or _LAYOUT_NODE_TEXTFREE.search(layout):
        return []
    return [
        f"{label}.layout 描述了节点数量「{hit.group(0)}」，但未声明节点本身不带文字 —— "
        f"模型会给每个节点各贴一遍标签（实测 eight ordered stops 把同一个词渲了 8 遍）。"
        f"请补一句正面声明，如「Individual blocks carry no text at all」或"
        f"「Text appears in exactly N places: ...」"
    ]


def _nonempty_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_visual_plan(plan: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["visual-plan.json 顶层必须是对象"]
    if plan.get("schema_version") != 1:
        errors.append("visual plan schema_version 必须为 1")

    cover = plan.get("cover")
    if not isinstance(cover, dict):
        errors.append("缺 cover 对象")
    else:
        aspect = str(cover.get("aspect_ratio") or "2.35:1")
        if aspect != "2.35:1":
            errors.append("cover aspect_ratio=2.35:1 是固定合同")
        if not str(cover.get("title") or "").strip():
            errors.append("cover.title 不能为空")
        if not _nonempty_list(cover.get("visual_facts")):
            errors.append("cover.visual_facts 必须是非空字符串列表")

    hero = plan.get("hero")
    if not isinstance(hero, dict):
        errors.append("缺 hero 对象")
    else:
        aspect = str(hero.get("aspect_ratio") or "1:1")
        if aspect != "1:1":
            errors.append("hero aspect_ratio=1:1 是固定合同")
        if not str(hero.get("title") or "").strip():
            errors.append("hero.title 不能为空")
        if not _nonempty_list(hero.get("visual_facts")):
            errors.append("hero.visual_facts 必须是非空字符串列表")

    images = plan.get("infographics")
    if not isinstance(images, list):
        return errors + ["infographics 必须是列表"]
    if len(images) < 4:
        errors.append("infographics 至少 4 张")
    ids = [str(item.get("id") or "") for item in images if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("infographic id 必须唯一")
    for index, item in enumerate(images):
        label = f"infographics[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} 必须是对象")
            continue
        for field in (
            "id",
            "position",
            "aspect_ratio",
            "title",
            "layout_type",
            "layout",
            "anchor",
        ):
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}.{field} 不能为空")
        layout_type = str(item.get("layout_type") or "")
        if layout_type and layout_type not in INFOGRAPHIC_LAYOUTS:
            errors.append(
                f"{label}.layout_type 必须是已登记 Baoyu 布局："
                f"{sorted(INFOGRAPHIC_LAYOUTS)}"
            )
        layout_cjk = len(_CJK.findall(str(item.get("layout") or "")))
        if layout_cjk > LAYOUT_CJK_MAX:
            errors.append(
                f"{label}.layout 含 {layout_cjk} 个中文字，超过上限 {LAYOUT_CJK_MAX}。"
                "layout 会原样进 prompt，模型会把这段中文当成要画的文字"
                "（实测：108 字 → 连废 4 版，181 字 → 多画「污染」；"
                "0 字 → 一次成功）。请改用英文描述构图，或压到短标签"
            )
        if not _nonempty_list(item.get("expected_text")):
            errors.append(f"{label}.expected_text 必须是非空字符串列表")
        else:
            for text_index, value in enumerate(item["expected_text"]):
                if _SUSPICIOUS_DOUBLE_CHARACTER_CLUSTER.search(value):
                    errors.append(
                        f"{label}.expected_text[{text_index}] 疑似重复字：{value}"
                    )
            # 🔴 2026-08-14 第 89 篇实跑新增：expected_text 之间、以及与 title 之间
            #    不得互相包含。否则渲出来该词会出现两次，直接违反 visual-qa 的
            #    required_text「整图恰好出现一次」硬门 —— 而这一刀要等图渲完才砍下来。
            #    实测代价：标题「走量的和攻坚的」含标签「走量」「攻坚」，白渲 8 次。
            #    纯字符串检查，没有任何理由留到渲染后才发现。
            errors.extend(_text_overlap_errors(
                label, str(item.get("title") or ""), item["expected_text"]
            ))
        # 🔴 layout 是原样进 prompt 的构图指令，下面三条来自实跑的教训：
        _layout_raw = str(item.get("layout") or "")
        errors.extend(_layout_negative_phrasing_errors(label, _layout_raw))
        errors.extend(_layout_node_label_errors(label, _layout_raw))
        # 三个因子里贡献最大的一条（2026-08-15 对照实验：+42 个百分点）
        errors.extend(_layout_concrete_subject_errors(label, _layout_raw))
        # 与上一条同源：物象要具体，但不能是自带文字的物件（2026-08-16 实证）
        errors.extend(_layout_textual_prop_errors(label, _layout_raw))
        if not _nonempty_list(item.get("facts")):
            errors.append(f"{label}.facts 必须是非空字符串列表")
        position = str(item.get("position") or "")
        aspect = str(item.get("aspect_ratio") or "")
        if index == 0 and (position != "opening" or aspect != "9:16"):
            errors.append("首张信息图必须 position=opening 且 aspect_ratio=9:16")
        elif index == len(images) - 1 and (
            position != "closing" or aspect != "9:16"
        ):
            errors.append("末张信息图必须 position=closing 且 aspect_ratio=9:16")
        elif 0 < index < len(images) - 1 and (
            position != "middle" or aspect != "16:9"
        ):
            errors.append(f"中间信息图 {item.get('id') or index} 必须为 16:9")
    return errors


def _load_json(path: Path, label: str) -> tuple[dict, list[str]]:
    if not path.exists():
        return {}, [f"缺 {label}：{path.name}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"{label} 解析失败：{exc}"]
    return (value, []) if isinstance(value, dict) else ({}, [f"{label} 顶层必须是对象"])


def _load_meta(cwd: Path) -> tuple[dict, list[str]]:
    path = cwd / "article-meta.yaml"
    if not path.exists():
        return {}, ["缺 article-meta.yaml"]
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {}, [f"article-meta.yaml 解析失败：{exc}"]
    return (value, []) if isinstance(value, dict) else ({}, ["article-meta.yaml 顶层必须是对象"])


def _quoted(value: object) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            # JSON flow sequences are valid YAML.  Keep provenance chains as
            # arrays instead of stringifying the Python repr; otherwise the
            # logger iterates the string one character at a time.
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {_quoted(value)}")
    lines.append("---")
    return "\n".join(lines)


def _expected_text_digest(values: list[str]) -> str:
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _recipe(meta: dict) -> tuple[dict, list[str]]:
    style = str(meta.get("infographic_style") or "")
    errors: list[str] = []
    if style != INFOGRAPHIC_STYLE:
        errors.append(
            f"infographic_style 必须是 {INFOGRAPHIC_STYLE}（全站统一粘土风）；"
            f"当前为 {style or '(空)'}"
        )
    expected_name = PROFILE_BY_STYLE.get(INFOGRAPHIC_STYLE, "")
    declared_name = str(meta.get("visual_profile") or "").strip()
    if declared_name != expected_name:
        errors.append(f"visual_profile 必须是 {expected_name}")
        return {}, errors
    if declared_name and declared_name != expected_name:
        errors.append(
            f"{style} 的 visual_profile 必须为 {expected_name} 或留空由编译器锁定"
        )
        return {}, errors
    name = expected_name
    recipe = visual_profile(name) or {}
    if not recipe:
        errors.append(f"profile 中缺 {name} 视觉配方")
        return {}, errors
    recipe = dict(recipe)
    recipe["sha256"] = stable_digest(recipe)
    return recipe, errors


def _cover_text(meta: dict, item: dict) -> dict:
    text, _ = cover_text_contract(meta)
    return text


def _cover_prompt(item: dict, meta: dict, recipe: dict) -> str:
    text = _cover_text(meta, item)
    title = text["line1"]
    subtitle = text["line2"]
    expected = [
        value
        for value in (title, subtitle, *text["tags"])
        if value
    ]
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        # 🔴 封面不接 baoyu-cover-image（2026-08-02 复核定案）：
        # montage-evidence 是自建签名视觉（英文 ghost 叠加），只反哺方法论、不走外部配方。
        # 声明一个明确不使用的依赖只会让 producer_chain 再次退化成空标签。
        "producer_chain": [VISUAL_PRODUCER],
        "cover_text_contract": text["contract_revision"],
        "stage": "cover",
        "style": "montage-evidence",
        "visual_profile": recipe["name"],
        "visual_profile_sha256": recipe["sha256"],
        "aspect_ratio": "2.35:1",
        "expected_text_sha256": _expected_text_digest(expected),
    }
    tags = " / ".join(text["tags"])
    background = recipe["background"]
    accent = recipe["accent"]
    accent_hint = (
        f"the exact characters 「{text['accent_phrase']}」"
        if text.get("accent_phrase")
        else "its final 2-5 characters (the semantic landing phrase of the line)"
    )
    pictorial_facts = "\n".join(
        f"- {str(fact).strip()}"
        for fact in item.get("visual_facts") or []
        if str(fact).strip()
    )
    # 🔴 2026-08-16 精简：4954 → ~2660 字符（模型可见正文 ~2220），对齐信息图
    #    prompt 的同一套实证规则（frontmatter 已由渲染层剥离；否定式清到 1 条；
    #    色号 8 处 → 2 处；「写给工具链的话」全部撤掉）。压缩不碰三样东西：
    #    ① 画布锚定的字号规格（12%-14% 等）——2026-07 修过的真 bug，去掉会复发
    #      （第 81 篇 L1 只有画布高 8%，主次颠倒）；测试钉的是锚点契约本身。
    #    ② 主题色胶囊 78%-85% 不透明 + 哑光磨砂（2026-07-28 定案，辨识度主要来源）。
    #    ③ logo 否定式——唯一保留的否定：画出品牌字是法律/品牌风险，宁可无效不可漏写。
    #    banned terms 门（largest / extra-black / ultra-black）依旧有效，改词时避开。
    return (
        _frontmatter(fields)
        + "\n\nCreate a polished dark editorial montage for a WeChat article cover.\n\n"
        + _native_raster_contract(
            "the cover's dark editorial typography, lighting and registered palette"
        )
        + "\n\n"
        "## LAYOUT\n"
        f"- One unified deep-charcoal canvas, exact color {background}, exact 2.35:1 "
        "landscape, generous margins and negative space; one upper-left 45-degree key "
        "light, soft shadows lower-right.\n"
        "- A slightly larger left text zone, a slightly smaller right evidence collage, "
        "one narrow quiet gutter between them.\n\n"
        "## VISIBLE TEXT (exhaustive)\n"
        # 🔴 字号必须锚在**画布**上，不能只给相对 L1 的百分比（第 81 篇实测教训）。
        f"- Main Chinese headline: {title} -- pure white, heaviest weight, the single "
        "dominant element. Its cap height MUST be 12%-14% of the canvas height, its "
        "line spans 70%-90% of the left zone width, compact and vertically centered "
        "in the left zone.\n"
        f"- Supporting Chinese subtitle: {subtitle or '(none)'} -- semibold white, one "
        f"line, 58%-64% of the headline cap height; ONLY {accent_hint} is set in the "
        f"accent color {accent}, every headline character stays pure white.\n"
        f"- Tags {tags} -- exactly these two, in ONE auto-fit pill under the subtitle: "
        "that same accent fill at 78%-85% opacity, a FLAT MATTE frosted body, matte "
        "like clay rather than glossy like glass, white tag text at 30%-34% of "
        "headline cap height with thin dividers.\n"
        "These are the only visible characters on the canvas; collage, badges and "
        "background stay textless, purely pictorial: abstract lines and low-contrast "
        "shapes.\n\n"
        "## RIGHT COLLAGE\n"
        "One dominant flat-vector metaphor object drawn from the facts below -- thin "
        "physical depth, same-hue halftone, upper-left highlight, soft lower-right "
        "contact shadow -- plus exactly three much smaller near-black badges with "
        "hairline borders in that same accent hue and one tiny textless pictogram "
        "each, linked by restrained curved dashed arrows. Speak through objects, "
        "curves, facilities, maps or service nodes; a small faceless silhouette only "
        "where a fact requires a person.\n\n"
        "No brand name, account name, issue number or signature text; the logo is "
        "added later.\n\n"
        "## PICTORIAL BRIEF\n"
        "Express these source facts as TEXTLESS visual evidence -- their objects, "
        "spaces, paths and relationships:\n"
        f"{pictorial_facts or '- Derive textless evidence objects from the approved title.'}\n"
    )


def _clay_palette(recipe: dict) -> str:
    """claymation 的配色约束（hero 与信息图共用同一段，避免两处各写一版而漂移）。

    早期版本只给了一串 `Avoid dark background, navy, brick red, mustard yellow...`
    的负面清单。实测**负面清单压不住**：图里照样出现砖橙标签条、芥末黄金币、蓝齿轮。
    根因在于凡是「左右对比 / 两组对照」的题材，只给一个主色时，模型必然自己发明
    第二个色相去区分两边 —— 它不是没看见禁令，是没有别的手段可用。
    所以这里改成**正面清单 + 明确给出区分两组的替代手段**（同色深浅、形状、材质）。
    """
    background = (recipe or {}).get("background") or "#F7F2E9"
    accent = (recipe or {}).get("accent") or "#79AA95"
    accent_shadow = (recipe or {}).get("accent_shadow") or "#5F8775"
    neutrals = ", ".join(
        (recipe or {}).get("neutrals") or ["#FCFAF5", "#DDD7CC", "#8A8178"]
    )
    # 🔴 下面这句必须原样包含配方 required_prompt_groups 要求的词：
    # `warm ivory` / `bright light palette` / `soft clay` / `diffuse light`。
    # pipeline.py 的 visual_route 门是**逐字子串比对**，写同义表述（如
    # "bright diffuse studio light"）过不了 —— 而且因为 prompt_sha256 是硬校验，
    # 改一个字就得整批重渲，代价不小。改这段前先跑 tests/test_visual_route.py。
    # 🔴 2026-08-15 精简：色值从 prompt 里撤掉，只留描述词。
    #    实测抓到一次「模型把 #F7F2E9 / #79AA95 这串色号连同调色板说明一起渲进了
    #    画面底部」—— hex 字符串对图像模型是纯噪声，它认得的是 warm ivory 这类词，
    #    而看到一串字符就有概率把它当成要写的文字。色值仍由 visual_contracts.py
    #    持有并用于像素级 QA，那才是它该待的地方。
    #    TONE OWNERSHIP 那段（「Baoyu 可以选结构但不许改配色」）同样撤掉：
    #    模型不知道 Baoyu 是谁，那是写给工具链的归属声明。
    # 🔴 visual_route 的逐字比对**大小写敏感**：必需短语是小写的 `warm ivory` /
    #    `diffuse light`，写成句首大写的 "Warm ivory" / "Diffuse light" 就过不了门。
    #    精简时改句式很容易把词推到句首 —— 本次实测就这么破了两组，
    #    由 tests/test_prompt_required_phrases.py 当场抓到。别把它们放句首。
    return (
        "A warm ivory background with a high-key pastel palette: matte soft clay "
        "everywhere, one pale pastel jade accent, pale warm neutrals, and soft clay skin "
        "and wood tones for figures. Lit by diffuse light, very low contrast, "
        "feather-soft shadows. Warm ivory covers most of the canvas; the jade stays an "
        "accent and large titles stay pale or mid-tone. Tell two groups apart with two "
        "tints of that same jade, or with shape, size and position."
    )


def _clay_typography() -> str:
    """Baoyu claymation 的文字材质合同，Hero 与信息图只维护这一份。"""
    # 🔴 2026-08-15 精简：600 → 330 字符，4 条否定式清零。
    #    原文用 sculpted / extruded / dimensional / rounded / chunky / physically
    #    embedded / integrated into the clay scene 七个词说同一件事，又用四句
    #    "Never …" 去禁印刷体、手写体、书法、粉笔字和底板 —— 而扩散模型对否定式
    #    基本不敏感（实测连写三轮 no backing plate，照样加底板；改成正面描述
    #    「像标题那样独立立体的黏土字」当轮即对）。
    #    必需短语 extruded clay letters / embedded in the clay scene 原样保留，
    #    visual_route 的逐字门照过（tests/test_visual_route.py 钉住）。
    # 🔴 精简时必须原样保住 visual_contracts.required_prompt_groups 里的
    #    "extruded clay letters" / "dimensional rounded clay text" /
    #    "embedded in the clay scene" 三个**精确串** —— visual_route 是逐字子串比对，
    #    写成 "dimensional, rounded, chunky" 就过不了门（本次实测被测试当场抓到）。
    return (
        "Text is sculpted as extruded clay letters: the dimensional rounded clay text is "
        "chunky and softly irregular, with complete standard Simplified-Chinese glyphs, "
        "embedded in the clay scene with the same matte material and light as the objects. "
        "Title largest, labels smaller, standing free with open background around them."
    )


def _native_raster_contract(material: str) -> str:
    """把可见文字留在与画面同一次栅格渲染里。

    🔴 2026-08-15 精简：原文有 450 字符，内容是「不要输出 SVG / HTML / Canvas /
    CSS / 向量文字，不要用 Pillow / Jimp / Sharp / ImageMagick 后期贴字」。
    这段话是**写给工具链看的，不是写给图像模型看的** —— 图像模型的 API 只返回
    inlineData 位图，它既不可能返回 SVG，也不会去调 Pillow。真正的防线在
    `render_visuals._validate_native_raster_output()`：出图后按字节校验 PNG 签名，
    伪装成 PNG 的 SVG 当场拒收。prompt 里再喊一遍纯属无效负载，还占着模型的注意力
    （实测有一张把 prompt 里的技术规格直接渲进了画面）。

    只留一句对模型真正有意义的：文字要和画面同材质、长在同一张图里。
    """
    return (
        "The visible Chinese glyphs are part of the picture itself, sculpted from "
        f"{material}, lit by the same light and sitting in the same space as the objects."
    )


def _hero_prompt(item: dict, style: str, recipe: dict) -> str:
    expected = [str(item.get("title") or "").strip()]
    pictorial_facts = "\n".join(
        f"- {str(fact).strip()}" for fact in item.get("visual_facts") or [] if str(fact).strip()
    )
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": [VISUAL_PRODUCER],
        "method_sources": [BAOYU_ARTICLE_METHOD],
        "stage": "hero",
        "style": style,
        "aspect_ratio": "1:1",
        "expected_text_sha256": _expected_text_digest(expected),
    }
    if recipe:
        fields.update(
            {
                "visual_profile": recipe["name"],
                "visual_profile_sha256": recipe["sha256"],
                "visual_contract_owner": recipe.get("contract_owner", ""),
                "visual_contract_revision": recipe.get("contract_revision", ""),
                "palette_background": recipe["background"],
                "palette_accent": recipe["accent"],
            }
        )
    palette = (
        _clay_palette(recipe)
        if style == "claymation"
        else "Use a warm Morandi / 莫兰迪柔色 palette: warm cream #F5F0E6 background "
        "with muted sage #7BA3A8, terracotta "
        "#D4956A and charcoal-brown #4A4540. Hand-drawn doodle, organic imperfect "
        "ink lines, restrained washi tape and clean-sketch bullet journal composition. "
        "No photographs, stock illustration, torn-paper scrapbook, watercolor scene "
        "panels, flat vector icons, strict corporate grid, pure-white background or neon."
    )
    typography = _clay_typography() if style == "claymation" else ""
    return (
        _frontmatter(fields)
        + "\n\n"
        + f"Create a square article Hero in {style} style. {palette}\n"
        + (f"{typography}\n" if typography else "")
        + _native_raster_contract(
            "the same dimensional matte-clay material, lighting and registered palette as the scene"
        )
        + "\n"
        +
        "Show one unmistakable visual hierarchy.\n\n"
        "## VISIBLE TEXT ALLOWLIST\n"
        f"- {expected[0]}\n"
        "Render this title EXACTLY ONCE, in one top title area only. Do not repeat it in a "
        "bottom banner, card, ribbon or caption. No data labels, fact sentences, extra words, "
        "logos, watermarks or invented interface. Keep every Chinese glyph complete and "
        "highly legible.\n\n"
        "## PICTORIAL BRIEF\n"
        "Build one clean metaphor from the approved title and the following source facts. "
        "Use facts only as textless objects, spaces and causal relations; never render any "
        "fact sentence, number, label or proper noun as visible text. Keep all essential "
        "objects inside a generous 8% crop-safe margin and include one clear dotted frame.\n"
        f"{pictorial_facts or '- Use a single textless causal metaphor.'}\n"
    )


def _infographic_prompt(item: dict, style: str, recipe: dict) -> str:
    title = str(item.get("title") or "").strip()
    expected = [
        value
        for value in (title, *[str(value) for value in item.get("expected_text") or []])
        if value
    ]
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": [VISUAL_PRODUCER],
        "method_sources": [BAOYU_INFOGRAPHIC_METHOD],
        "stage": "infographic",
        "id": str(item.get("id") or ""),
        "position": str(item.get("position") or ""),
        "style": style,
        # 🔴 layout 不进 frontmatter。渲染器把**整个 prompt 文件**（含 frontmatter）
        # 原样发给模型，所以 frontmatter 里的中文一样会被读到、被画进图里。
        # layout 只在正文的 COMPOSITION GUIDANCE 段出现一次，且那一段带着
        # 「绝不可渲染为可见文字」的显式禁令；放两处等于把禁令稀释掉。
        # 溯源不受影响：guidance 段本身就在同一份 canonical prompt 里，照样入 SHA。
        "aspect_ratio": str(item.get("aspect_ratio") or ""),
        "expected_text_sha256": _expected_text_digest(expected),
    }
    if recipe:
        fields.update(
            {
                "visual_profile": recipe["name"],
                "visual_profile_sha256": recipe["sha256"],
                "visual_contract_owner": recipe.get("contract_owner", ""),
                "visual_contract_revision": recipe.get("contract_revision", ""),
                "palette_background": recipe["background"],
                "palette_accent": recipe["accent"],
            }
        )
    labels = "\n".join(f"- {value}" for value in expected[1:])
    layout_type = str(item.get("layout_type") or "linear-progression")
    layout_contract = INFOGRAPHIC_LAYOUTS[layout_type]
    palette = (
        _clay_palette(recipe)
        if style == "claymation"
        else "Use a warm Morandi / 莫兰迪柔色 palette: warm cream background #F5F0E6; "
        "muted sage #7BA3A8 for headers and "
        "frames, terracotta #D4956A for highlights, charcoal-brown #4A4540 line art, "
        "and pale yellow #F5E6C8 only for soft accents. Use hand-drawn doodle "
        "illustrations with organic imperfect ink lines, restrained washi tape, dotted "
        "frames, curved arrows, rounded note cards and a clean-sketch bullet journal "
        "hierarchy. No flat vector icons. No stock illustration style. No strict grid "
        "layout. No pure white background. No photographic collage, aged parchment, "
        "torn-paper scrapbook, watercolor scene panels, digital corporate dashboard, "
        "metal, chrome or neon."
    )
    typography = _clay_typography() if style == "claymation" else ""
    return (
        _frontmatter(fields)
        + "\n\n"
        # 🔴 2026-08-16 第二轮精简（G 组生产验收后）。
        #    第一轮把 4855 压到 2224，验收实测首过率 67%；而同内容、同 allowlist、
        #    同 SCENE 的 1112 字符手写版是 92%。唯一变量就是长度 —— 说明还得再压。
        #    这里去掉「using the reviewed editorial composition contract」这类
        #    对模型无意义的流程话术，并把 native-raster 那句并进排版段（它讲的
        #    本来就是同一件事：字与画同材质、长在一张图里）。
        + f"A high-information Chinese infographic in {style} style. {palette}\n"
        + (f"{typography}\n" if typography else "")
        # 🔴 2026-08-15 精简（对照实验后）：这一段原本有 1200 字符、18 条否定式。
        #    ① BAOYU LAYOUT CONTRACT 那行是结构术语（linear-progression 之类），
        #       模型看了没用，而 SCENE 段已经把同一件事讲成了画面。删。
        #    ② "COMPOSITION GUIDANCE — Never render this guidance…" 这个 130 字符
        #       的前缀，是在告诉模型「下面这段别画」。与其反复叮嘱别画，不如直接
        #       改成祈使句「照这个搭出来」—— 实测同样不会被渲成文字，还省下注意力。
        #       （layout 里的中文仍由 LAYOUT_CJK_MAX=24 拦，那条门没动。）
        #    ③ 字形段的七条 "Never …" 合并成两句正面表述。
        #    ④ CONTENT BOUNDARY 段是在向模型解释「为什么不给你 facts」——
        #       模型不需要知道这件事。删。
        + f"SCENE — build this arrangement out of clay: {item.get('layout')}\n"
        # 🔴 中文字形是这条链上最脆弱的一环：糊字既不报错、又会被看图模型「脑补」成
        # 通顺句子而漏检（实测 hero 图渲成「重置不是祸利，是昀家公司付溻针」，
        # 复核仍判 text_match 通过）。所以这里要求宁可放大、减量，也不许把字画歪。
        "Every Chinese character must be a complete, correct Simplified glyph; render "
        "text large enough that every stroke stays intact. Each line below appears in "
        "exactly one place, inside crop-safe margins. "
        # 🔴 这一条**故意保留否定式**。其余禁令都改成了正面描述（模型对否定式不敏感），
        #    但画出真实公司 logo 是合规风险不是审美问题：代价是 60 个字符，
        #    风险是一张带真商标的图发出去。宁可写了无效，不可漏写。
        "Any emblem on a prop is a generic invented shape, never a real company or "
        "product logo.\n\n"
        "## VISIBLE TEXT ALLOWLIST — EXHAUSTIVE\n"
        f"- {title}\n"
        f"{labels}\n"
        "These lines are the only text anywhere in the image.\n"
    )


def compile_visual_plan(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    plan, errors = _load_json(cwd / VISUAL_PLAN_FILE, VISUAL_PLAN_FILE)
    meta, meta_errors = _load_meta(cwd)
    errors.extend(meta_errors)
    errors.extend(validate_visual_plan(plan))
    _, cover_text_errors = cover_text_contract(meta)
    errors.extend(cover_text_errors)
    recipe, recipe_errors = _recipe(meta)
    errors.extend(recipe_errors)

    # 🔴 Baoyu 依赖硬门（2026-08-02）：本仓的信息图版式语言必须整体取自
    # baoyu-infographic 的 Layout Gallery，且枚举从磁盘实时解析、不在此硬编码。
    # 这样 producer_chain 才不再是自说自话的字符串——Baoyu 缺失、换版本、
    # 或本地版式语言偏离枚举，都会在编译期硬失败。
    errors.extend(baoyu_contract.validate_layout_types(sorted(INFOGRAPHIC_LAYOUTS)))
    try:
        baoyu_anchors = baoyu_contract.build_anchors()
    except baoyu_contract.BaoyuContractError as exc:
        errors.append(str(exc))
        baoyu_anchors = {}

    if errors:
        return None, errors

    style = str(meta["infographic_style"])
    prompt_dir = cwd / "素材" / "prompts" / "final"
    evidence_dir = cwd / "素材" / "infographic"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    prompt_specs: list[tuple[str, str, str, str]] = []
    cover_prompt = prompt_dir / "cover.md"
    cover_recipe = visual_profile("montage-evidence") or {}
    if not cover_recipe:
        return None, ["profile 中缺 montage-evidence 视觉配方"]
    cover_recipe = dict(cover_recipe)
    cover_recipe["sha256"] = stable_digest(cover_recipe)
    cover_prompt.write_text(
        _cover_prompt(plan["cover"], meta, cover_recipe),
        encoding="utf-8",
    )
    prompt_specs.append(("cover", "cover", "2.35:1", "cover.png"))

    hero_prompt = prompt_dir / "hero.md"
    hero_prompt.write_text(
        _hero_prompt(plan["hero"], style, recipe), encoding="utf-8"
    )
    prompt_specs.append(("hero", "hero", "1:1", "hero.png"))

    for item in plan["infographics"]:
        item_id = str(item["id"])
        prompt = prompt_dir / f"infographic-{item_id}.md"
        prompt.write_text(
            _infographic_prompt(item, style, recipe), encoding="utf-8"
        )
        prompt_specs.append(
            (
                f"infographic-{item_id}",
                f"infographic-{item_id}",
                str(item["aspect_ratio"]),
                f"infographic-{item_id}.png",
            )
        )

    analysis_lines = [
        "# Visual Plan Analysis",
        "",
        f"- producer: {VISUAL_PRODUCER}",
        f"- method source: {BAOYU_INFOGRAPHIC_METHOD}",
        f"- style: {style}",
        f"- plan_digest: {stable_digest(plan)}",
        "",
    ]
    structured_lines = [
        "# Structured Visual Content",
        "",
        f"- producer: {VISUAL_PRODUCER}",
        f"- method source: {BAOYU_INFOGRAPHIC_METHOD}",
        f"- style: {style}",
        "",
    ]
    for item in plan["infographics"]:
        analysis_lines.append(
            f"- {item['id']} · {item['position']} · {item['aspect_ratio']} · "
            f"{item['layout_type']} · {item['layout']} · {item['title']} · anchor={item['anchor']}"
        )
        structured_lines.extend(
            [
                f"## {item['id']} · {item['title']}",
                "",
                *[f"- {fact}" for fact in item["facts"]],
                "",
                "图内文字：" + " / ".join(item["expected_text"]),
                "",
            ]
        )
    (evidence_dir / "analysis.md").write_text(
        "\n".join(analysis_lines).rstrip() + "\n", encoding="utf-8"
    )
    (evidence_dir / "structured-content.md").write_text(
        "\n".join(structured_lines).rstrip() + "\n", encoding="utf-8"
    )

    tasks = []
    for task_id, prompt_stem, aspect, image_name in prompt_specs:
        stage = "cover" if task_id == "cover" else (
            "hero" if task_id == "hero" else "infographic"
        )
        producer_chain = [VISUAL_PRODUCER]
        method_sources = []
        # 封面走自建 montage-evidence，不接 baoyu-cover-image（见上方说明）。
        if stage == "hero":
            method_sources.append(BAOYU_ARTICLE_METHOD)
        elif stage == "infographic":
            method_sources.append(BAOYU_INFOGRAPHIC_METHOD)
        tasks.append(
            {
                "id": task_id,
                "promptFiles": [f"prompts/final/{prompt_stem}.md"],
                "image": image_name,
                "ar": aspect,
                "producer_chain": producer_chain,
                "method_sources": method_sources,
            }
        )
    batch = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": [
            VISUAL_PRODUCER,
        ],
        "method_sources": [BAOYU_ARTICLE_METHOD, BAOYU_INFOGRAPHIC_METHOD],
        # Baoyu 依赖的字节级锚点：校验侧会重新解析磁盘上的 Baoyu 文档并比对，
        # 不一致即拒绝发布（producer_chain 字符串本身证明不了任何事）。
        **baoyu_anchors,
        "plan_digest": stable_digest(plan),
        "jobs": 1,
        "tasks": tasks,
    }
    (cwd / "素材" / "render-batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": batch["producer_chain"],
        "method_sources": batch["method_sources"],
        **baoyu_anchors,
        "cover_workflow": {
            "producer": VISUAL_PRODUCER,
            "type": "conceptual",
            "palette": "dark",
            "rendering": "flat-vector",
            "text": "text-rich",
            "mood": "balanced",
            "font": "clean",
            "aspect": "2.35:1",
        },
        "infographic_workflow": [
            {
                "id": str(item["id"]),
                "producer": VISUAL_PRODUCER,
                "method_source": BAOYU_INFOGRAPHIC_METHOD,
                "layout": str(item["layout_type"]),
                "style": style,
                "aspect": str(item["aspect_ratio"]),
            }
            for item in plan["infographics"]
        ],
        "style": style,
        "validator_hashes": {
            "visual_qa.py": _file_sha256(Path(__file__).with_name("visual_qa.py")),
            "visual_qa_codex.py": _file_sha256(
                Path(__file__).with_name("visual_qa_codex.py")
            ),
        },
        "plan_digest": stable_digest(plan),
        "batch": batch,
        "prompt_count": len(tasks),
    }
    (cwd / "素材" / "visual-compile-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result, []
