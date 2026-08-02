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
    from .evidence import stable_digest
    from .profile_config import visual_profile
except ImportError:  # pragma: no cover - direct script execution
    from evidence import stable_digest
    from profile_config import visual_profile


VISUAL_PLAN_FILE = "visual-plan.json"
VISUAL_PRODUCER = "sansheng-write.visual-planner"
BAOYU_COVER_PRODUCER = "baoyu-cover-image"
BAOYU_ARTICLE_PRODUCER = "baoyu-article-illustrator"
BAOYU_INFOGRAPHIC_PRODUCER = "baoyu-infographic"
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
    lead = meta.get("lead") if isinstance(meta.get("lead"), dict) else {}
    line1 = str(lead.get("line1") or item.get("title") or "").strip()
    line2 = str(lead.get("line2") or item.get("subtitle") or "").strip()
    # subtitle 可写成字符串（单条）或 YAML 列表（2-4 个短标签）。
    # 用列表而不是「拿分隔符切一个长字符串」，是因为标签自身就可能含 `/`
    # （如「5h/7d 额度」），切了必错。
    raw_subtitle = lead.get("subtitle")
    if isinstance(raw_subtitle, (list, tuple)):
        tags = [str(v).strip() for v in raw_subtitle if str(v or "").strip()][:4]
    else:
        tags = [str(raw_subtitle).strip()] if str(raw_subtitle or "").strip() else []
    # 主题色落点：meta 显式指定优先。不指定就让模型自己挑 L2 的收尾短语 ——
    # 能出图，但落点会飘（同一批封面里有的染动词、有的染名词）。
    # 显式写死才能让「哪几个字是绿的」在标题阶段就拍板，见 references/title.md。
    accent_phrase = str(lead.get("accent") or "").strip()
    return {
        "line1": line1,
        "line2": line2,
        "tags": tags,
        "accent_phrase": accent_phrase,
    }


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
        "producer_chain": [VISUAL_PRODUCER, BAOYU_COVER_PRODUCER],
        "stage": "cover",
        "style": "montage-evidence",
        "visual_profile": recipe["name"],
        "visual_profile_sha256": recipe["sha256"],
        "aspect_ratio": "2.35:1",
        "expected_text_sha256": _expected_text_digest(expected),
    }
    tags = " / ".join(text["tags"]) or "(none)"
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
    return (
        _frontmatter(fields)
        + "\n\nCreate a polished dark editorial montage for a WeChat article cover.\n\n"
        "## LAYOUT\n"
        "- One unified deep-charcoal canvas, exact 2.35:1 landscape.\n"
        "- Put the text in a slightly larger left zone, the evidence collage in a slightly "
        "smaller right zone, and separate them with one narrow quiet gutter. Preserve "
        "generous outer safe margins and abundant negative space.\n"
        "- Keep the Chinese title block compact and vertically centered in the left zone. "
        "Never center it across the full canvas or place it along the bottom.\n"
        "- One upper-left 45-degree key light only; all soft shadows fall lower-right.\n\n"
        "## ONLY VISIBLE TEXT ALLOWLIST\n"
        f"- Main Chinese headline: {title}\n"
        f"- Supporting Chinese subtitle: {subtitle or '(none)'}\n"
        f"- Quiet pill tags: {tags}\n"
        # 🔴 字号必须锚在**画布**上，不能只给相对 L1 的百分比。
        # 旧版写的是「L1 at 100% scale」+ 其余按 L1 的比例 —— 但 100% 相对谁没定义，
        # 模型可以把 L1 定成任意大小，整组跟着缩。实测第 81 篇 L1 只有画布高 8%，
        # 比 ghost 还小，主次颠倒；而同一份提示词在第 76/80 篇却给出 12% 的 L1。
        # 同理 ghost 旧值 145%-155% of L1 等于**规范本身在要求英文比中文大**。
        "- The main headline is the single dominant element on the entire canvas: "
        "pure white, heaviest weight, first reading focus. Its cap height MUST be "
        "12%-14% of the canvas height, and its line MUST span 70%-90% of the width "
        "of the left text zone. No other high-contrast text may be set larger than it.\n"
        "- The supporting subtitle is 58%-64% of the headline cap height: semibold white, "
        f"one line only, with ONLY {accent_hint} rendered in the muted emerald accent. "
        "Never colour any part of the main headline — it earns dominance through size, not hue.\n"
        f"- Descriptor tags: {tags}. Render them at "
        "30%-34% of headline cap height inside the pill; tags never compete with the headline.\n"
        "- Keep the background purely pictorial: abstract lines and low-contrast shapes only. "
        "Do not render ghost words, watermark text, letters or numbers behind the Chinese block.\n"
        # 🔴 品牌胶囊（2026-07-28 sandy 拍板）。她认可的两张封面里，底部这条
        # 主题色标签胶囊是**辨识度的主要来源**——但满色 100% 不透明太抢眼，
        # 会跟 L1 争视觉焦点。故降到 ~80% 并加一点哑光磨砂。
        # ⚠️ 「磨砂」≠「毛玻璃」：下面 STRICT FORBIDDEN 里的 glassmorphism /
        # glossy reflections 依然全图有效，这里要的是**半透明 + 细微颗粒的哑光**，
        # 不是高光条、镜面反射或彩虹边。两者一旦混淆就会渲成廉价的玻璃按钮。
        "- Put all tags in ONE auto-fit pill sitting directly under L2. Fill the pill "
        "with the muted emerald accent at 78%-85% opacity over the dark canvas, so it "
        "reads as a soft branded chip rather than a bright solid block. Give it a FLAT "
        "MATTE frosted body: slight translucency plus a very faint grain. No border, no "
        "glow, no drop shadow, no specular highlight, no rim light, no gradient sheen, "
        "no reflection. Frosted here means matte translucency only, NOT glassmorphism.\n"
        "- Separate the tags with thin vertical dividers or a slash. Tag text is pure "
        "white. Two to four tags maximum; never wrap the pill onto a second line.\n\n"
        "## RIGHT COLLAGE\n"
        "- Use one dominant flat-vector metaphor object derived from the verified facts, "
        "plus exactly three much smaller dark evidence badges and restrained curved dashed "
        "arrows. The main object must be the first visual focus.\n"
        "- No photographs, recognisable faces or hands. A small faceless athlete silhouette is allowed "
        "when it is directly required by a source fact; otherwise use objects, curves, facilities, "
        "maps or service nodes to express the argument.\n"
        "- Main object: flat-vector editorial form with thin physical depth, same-hue "
        "halftone, upper-left highlight and soft lower-right contact shadow.\n"
        "- Badges: very dark charcoal fill, a hairline emerald border, rounded corners; never white cards.\n\n"
        "## COLOR & BACKGROUND\n"
        "- Canvas base: deep charcoal.\n"
        "- Only visible accent hue: muted emerald; other foreground text is pure white.\n"
        "- Deep surfaces use only near-black charcoal shades.\n"
        "- No hard split-color panels; no bright, beige, photographic or scrapbook canvas.\n\n"
        "## STRICT FORBIDDEN\n"
        "- No recognisable faces, detailed hands, photorealistic stock imagery, robots, glowing brains, "
        "generic gear piles, code, file paths, UI, grids, stars, particles or random letters.\n"
        "- No brand name, account name, issue number or signature text; logo is added later.\n"
        "- No pure black, extra accent hues, neon, chrome, glassmorphism, glossy reflections, "
        "centered giant headline, bottom title bar or crowded poster composition.\n"
        "- Never render layout guides, measurements or percentages. Never render the facts "
        "below, color names, hex codes, layout labels or instruction words as visible text.\n"
        "- The allowlist above is exhaustive: every other visible letter, word or number is "
        "forbidden. Evidence badges must be pictorial and textless.\n\n"
        "## PICTORIAL BRIEF\n"
        "Build the right-side collage from the following source facts as TEXTLESS visual "
        "evidence only: interpret their objects, spaces, paths and relationships; never "
        "render any sentence, number, label or proper noun from this list as visible text.\n"
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
    background = (recipe or {}).get("background") or "#F5F0E6"
    accent = (recipe or {}).get("accent") or "#0E926F"
    neutrals = ", ".join((recipe or {}).get("neutrals") or ["#FBF8F2", "#D8D2C7", "#5A554F"])
    # 🔴 下面这句必须原样包含配方 required_prompt_groups 要求的词：
    # `warm ivory` / `bright light palette` / `soft clay` / `diffuse light`。
    # pipeline.py 的 visual_route 门是**逐字子串比对**，写同义表述（如
    # "bright diffuse studio light"）过不了 —— 而且因为 prompt_sha256 是硬校验，
    # 改一个字就得整批重渲，代价不小。改这段前先跑 tests/test_visual_route.py。
    return (
        "Warm ivory background with a bright light palette. "
        "STRICT PALETTE — use these colours and nothing else: warm ivory; "
        "a single muted jade-green accent; soft warm stone-gray neutrals; "
        "plus soft natural clay skin and wood tones for figures and props. "
        "Matte soft clay material, diffuse light, low contrast, soft shadows.\n"
        "Never introduce a SECOND HUE. When two groups, sides or outcomes must be told "
        "apart, distinguish them with light versus dark tints of the SAME accent green, "
        "or with shape, size, texture and position — never by giving one side a different "
        "colour. This applies to label bars, arrows, containers, highlights and props alike.\n"
        "Forbidden anywhere in the image: orange, terracotta, brick red, mustard yellow, "
        "navy, steel blue, purple, dark or black background, metallic, chrome, neon, "
        "high-contrast or photorealistic surfaces."
    )


def _clay_typography() -> str:
    """Baoyu claymation 的文字材质合同，Hero 与信息图只维护这一份。"""
    return (
        "CLAY TYPOGRAPHY CONTRACT — all allowlisted Chinese text must be sculpted as "
        "extruded clay letters: dimensional, rounded, chunky and softly irregular, with "
        "complete standard Simplified-Chinese glyphs. The dimensional rounded clay text "
        "must be physically embedded in the clay scene and integrated into the clay scene "
        "with the same matte material language as nearby objects. Preserve a clear title > "
        "section > detail hierarchy through scale and spacing. Never render flat printed "
        "business typography, handwriting, brush lettering, calligraphy or chalk text. "
        "The title and at least half of all labels must be freestanding clay letters with "
        "NO backing plate, box, ribbon, banner or card behind them. Never enclose all or "
        "most text items; use open space, direct placement on the scene and object grouping "
        "instead."
    )


def _hero_prompt(item: dict, style: str, recipe: dict) -> str:
    expected = [str(item.get("title") or "").strip()]
    pictorial_facts = "\n".join(
        f"- {str(fact).strip()}" for fact in item.get("visual_facts") or [] if str(fact).strip()
    )
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": [VISUAL_PRODUCER, BAOYU_ARTICLE_PRODUCER],
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
        "producer_chain": [VISUAL_PRODUCER, BAOYU_INFOGRAPHIC_PRODUCER],
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
        + f"Create a high-information Chinese infographic in {style} style using the "
        f"reviewed editorial composition contract. {palette}\n"
        + (f"{typography}\n" if typography else "")
        +
        f"BAOYU LAYOUT CONTRACT — {layout_type}: {layout_contract}. "
        "This is structural guidance only and must never become visible text.\n"
        # 🔴 layout 是中文的排布说明，必须显式声明「只描述构图、不得当作可见文字」。
        # 早期版本把它直接嵌在这句里（`... template X (中文排布说明)`），模型会把这句
        # 中文当成标题画进图里——实测出现过整句排布说明被渲成图上大标题，
        # 而下一段才说「白名单外任何可见文字都禁止」，两条指令互相打架。
        "COMPOSITION GUIDANCE — describes arrangement only. Never render this guidance, "
        "or any word from it, as visible text in the image: "
        f"{item.get('layout')}\n"
        "The graphic must communicate the silent facts below, not merely decorate them. "
        # 🔴 中文字形是这条链上最脆弱的一环：糊字既不报错、又会被看图模型「脑补」成
        # 通顺句子而漏检（实测 hero 图渲成「重置不是祸利，是昀家公司付溻针」，
        # 复核仍判 text_match 通过）。所以这里要求宁可放大、减量，也不许把字画歪。
        "Render every allowlisted line exactly once in readable Simplified Chinese. "
        "CHARACTER ACCURACY IS CRITICAL: every Chinese character must be a complete, "
        "correct, standard Simplified glyph. Never approximate a character, never invent "
        "or merge strokes, never output a character that does not exist. If a line cannot "
        "be rendered accurately at the planned size, render it LARGER and simpler rather "
        "than distorting the glyphs — losing decoration is acceptable, a broken character "
        "is not. "
        "Each allowlisted line must appear EXACTLY ONCE — never repeat a line as both a "
        "badge and a caption, and never echo it on a nearby surface. "
        "Do not invent numbers, labels, logos, watermarks, product UI or additional text. "
        "Never draw any real company or product logo, even in the illustration style. "
        "Keep all labels inside crop-safe margins and make the title > sections > details "
        "hierarchy obvious at thumbnail size.\n\n"
        "## VISIBLE TEXT ALLOWLIST — EXHAUSTIVE\n"
        f"- {title}\n"
        f"{labels}\n"
        "Every other visible letter, word or number is forbidden.\n\n"
        "## CONTENT BOUNDARY\n"
        "Use the allowlisted title and labels themselves to determine the visual structure. "
        "SOURCE FACTS ARE NOT PROVIDED TO THE RENDERER because they must never become "
        "accidental visible labels or numbers.\n"
    )


def compile_visual_plan(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    plan, errors = _load_json(cwd / VISUAL_PLAN_FILE, VISUAL_PLAN_FILE)
    meta, meta_errors = _load_meta(cwd)
    errors.extend(meta_errors)
    errors.extend(validate_visual_plan(plan))
    recipe, recipe_errors = _recipe(meta)
    errors.extend(recipe_errors)
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
        f"- producer chain: {VISUAL_PRODUCER} → {BAOYU_INFOGRAPHIC_PRODUCER}",
        f"- style: {style}",
        f"- plan_digest: {stable_digest(plan)}",
        "",
    ]
    structured_lines = [
        "# Structured Visual Content",
        "",
        f"- producer chain: {VISUAL_PRODUCER} → {BAOYU_INFOGRAPHIC_PRODUCER}",
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
        if stage == "cover":
            producer_chain.append(BAOYU_COVER_PRODUCER)
        elif stage == "hero":
            producer_chain.append(BAOYU_ARTICLE_PRODUCER)
        elif stage == "infographic":
            producer_chain.append(BAOYU_INFOGRAPHIC_PRODUCER)
        tasks.append(
            {
                "id": task_id,
                "promptFiles": [f"prompts/final/{prompt_stem}.md"],
                "image": image_name,
                "ar": aspect,
                "producer_chain": producer_chain,
            }
        )
    batch = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "producer_chain": [
            VISUAL_PRODUCER,
            BAOYU_COVER_PRODUCER,
            BAOYU_INFOGRAPHIC_PRODUCER,
        ],
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
        "cover_workflow": {
            "producer": BAOYU_COVER_PRODUCER,
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
                "producer": BAOYU_INFOGRAPHIC_PRODUCER,
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
