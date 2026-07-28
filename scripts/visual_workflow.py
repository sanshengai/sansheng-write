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
SUPPORTED_STYLES = {"claymation", "morandi-journal"}
STYLE_BY_SUBJECT = {
    "ai-product": "claymation",
    "phenomenon": "morandi-journal",
}
PROFILE_BY_STYLE = {
    "claymation": "warm-light-clay",
    "morandi-journal": "morandi-journal",
}
TEMPLATE_IDS_BY_POSITION = {
    "opening": {"curve-convergence"},
    "middle": {"service-map", "tiered-network"},
    "closing": {"experience-loop"},
}
_SUSPICIOUS_DOUBLE_CHARACTER_CLUSTER = re.compile(
    r"([\u4e00-\u9fff])\1([\u4e00-\u9fff])\2"
)


def _nonempty_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


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
            "layout",
            "template_id",
        ):
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}.{field} 不能为空")
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
        template_id = str(item.get("template_id") or "")
        allowed_templates = TEMPLATE_IDS_BY_POSITION.get(position, set())
        if template_id and template_id not in allowed_templates:
            errors.append(
                f"{label}.template_id={template_id} 不适用于 position={position}；"
                f"只允许 {sorted(allowed_templates)}"
            )
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
        else:
            lines.append(f"{key}: {_quoted(value)}")
    lines.append("---")
    return "\n".join(lines)


def _expected_text_digest(values: list[str]) -> str:
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _recipe(meta: dict) -> tuple[dict, list[str]]:
    style = str(meta.get("infographic_style") or "")
    subject = str(meta.get("infographic_subject") or "")
    errors: list[str] = []
    if subject not in STYLE_BY_SUBJECT:
        errors.append("infographic_subject 必须为 ai-product 或 phenomenon")
    elif style != STYLE_BY_SUBJECT[subject]:
        errors.append(
            f"infographic_subject={subject} 必须使用 {STYLE_BY_SUBJECT[subject]}"
        )
    if style not in SUPPORTED_STYLES:
        errors.append("infographic_style 只允许 claymation / morandi-journal")
    expected_name = PROFILE_BY_STYLE.get(style, "")
    declared_name = str(meta.get("visual_profile") or "").strip()
    if style == "claymation" and declared_name != expected_name:
        errors.append("claymation 必须 visual_profile: warm-light-clay")
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
    uppercase = re.findall(
        r"(?<![A-Za-z0-9])[A-Z][A-Z0-9-]*(?![A-Za-z0-9])",
        str(meta.get("cover_keywords") or ""),
    )
    ghost = " × ".join(uppercase[-3:]) if len(uppercase) >= 3 else ""
    # 主题色落点：meta 显式指定优先。不指定就让模型自己挑 L2 的收尾短语 ——
    # 能出图，但落点会飘（同一批封面里有的染动词、有的染名词）。
    # 显式写死才能让「哪几个字是绿的」在标题阶段就拍板，见 references/title.md。
    accent_phrase = str(lead.get("accent") or "").strip()
    return {
        "line1": line1,
        "line2": line2,
        "tags": tags,
        "ghost": ghost,
        "accent_phrase": accent_phrase,
    }


def _cover_prompt(item: dict, meta: dict, recipe: dict) -> str:
    text = _cover_text(meta, item)
    title = text["line1"]
    subtitle = text["line2"]
    expected = [
        value
        for value in (title, subtitle, *text["tags"], text["ghost"])
        if value
    ]
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "stage": "cover",
        "style": "montage-evidence",
        "visual_profile": recipe["name"],
        "visual_profile_sha256": recipe["sha256"],
        "aspect_ratio": "2.35:1",
        "expected_text_sha256": _expected_text_digest(expected),
    }
    tags = " / ".join(text["tags"]) or "(none)"
    ghost = text["ghost"] or "(derive three article-specific English keywords)"
    accent = recipe["accent"]
    accent_hint = (
        f"the exact characters 「{text['accent_phrase']}」"
        if text.get("accent_phrase")
        else "its final 2-5 characters (the semantic landing phrase of the line)"
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
        f"- Chinese L1: {title}\n"
        f"- Chinese L2: {subtitle or '(none)'}\n"
        f"- Quiet pill tags: {tags}\n"
        f"- OVERSIZED GHOST-WATERMARK behind the Chinese title: {ghost}\n"
        # 🔴 字号必须锚在**画布**上，不能只给相对 L1 的百分比。
        # 旧版写的是「L1 at 100% scale」+ 其余按 L1 的比例 —— 但 100% 相对谁没定义，
        # 模型可以把 L1 定成任意大小，整组跟着缩。实测第 81 篇 L1 只有画布高 8%，
        # 比 ghost 还小，主次颠倒；而同一份提示词在第 76/80 篇却给出 12% 的 L1。
        # 同理 ghost 旧值 145%-155% of L1 等于**规范本身在要求英文比中文大**。
        "- L1 is the headline and the single dominant element on the entire canvas: "
        "pure white, heaviest weight, first reading focus. Its cap height MUST be "
        "12%-14% of the canvas height, and the L1 line MUST span 70%-90% of the width "
        "of the left text zone. No other high-contrast text may be set larger than L1.\n"
        "- L2 is a supporting subtitle at 58%-64% of L1 cap height: semibold white, "
        f"one line only, with ONLY {accent_hint} rendered in the muted emerald accent. "
        "Never colour any part of L1 — L1 earns dominance through size, not hue.\n"
        f"- Descriptor tags: {tags}. Render them at "
        "30%-34% of L1 cap height inside the pill; tags never compete with the headline.\n"
        "- The ghost is industrial condensed uppercase at 105%-120% of L1 cap height, "
        "in a near-background dark tone at 8%-12% opacity, partly overlapped by the Chinese "
        "block. It is BACKGROUND TEXTURE, never a headline — if it reads as the loudest "
        "element, the cover is wrong. Fitting the ghost must never shrink L1: L1's size is "
        "fixed by the canvas rule above and takes precedence.\n"
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
        "plus two or three much smaller dark evidence badges and restrained curved dashed "
        "arrows. The main object must be the first visual focus.\n"
        "- No photographs and no people, faces or hands. Use objects, curves, facilities, "
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
        "- No people, faces, hands, photorealistic stock imagery, robots, glowing brains, "
        "generic gear piles, code, file paths, UI, grids, stars, particles or random letters.\n"
        "- No brand name, account name, issue number or signature text; logo is added later.\n"
        "- No pure black, extra accent hues, neon, chrome, glassmorphism, glossy reflections, "
        "centered giant headline, bottom title bar or crowded poster composition.\n"
        "- Never render layout guides, measurements or percentages. Never render the facts "
        "below, color names, hex codes, L1/L2, TITLE or SUBTITLE as visible text.\n"
        "- The allowlist above is exhaustive: every other visible letter, word or number is "
        "forbidden. Evidence badges must be pictorial and textless.\n\n"
        "## PICTORIAL BRIEF\n"
        "Use abstract curves and textless evidence objects suggested by the approved title. "
        "SOURCE FACTS ARE NOT PROVIDED TO THE RENDERER because they must never become "
        "accidental visible labels.\n"
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


def _hero_prompt(item: dict, style: str, recipe: dict) -> str:
    expected = [str(item.get("title") or "").strip()]
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
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
    return (
        _frontmatter(fields)
        + "\n\n"
        + f"Create a square article Hero in {style} style. {palette}\n"
        "Show one unmistakable visual hierarchy.\n\n"
        "## VISIBLE TEXT ALLOWLIST\n"
        f"- {expected[0]}\n"
        "This title is the only visible text. No data labels, fact sentences, extra words, "
        "logos, watermarks or invented interface.\n\n"
        "## PICTORIAL BRIEF\n"
        "Build one clean metaphor from the approved title alone. SOURCE FACTS ARE NOT "
        "PROVIDED TO THE RENDERER because they must never become accidental visible text.\n"
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
        "stage": "infographic",
        "id": str(item.get("id") or ""),
        "position": str(item.get("position") or ""),
        "style": style,
        # 🔴 layout 不进 frontmatter。渲染器把**整个 prompt 文件**（含 frontmatter）
        # 原样发给模型，所以 frontmatter 里的中文一样会被读到、被画进图里。
        # layout 只在正文的 COMPOSITION GUIDANCE 段出现一次，且那一段带着
        # 「绝不可渲染为可见文字」的显式禁令；放两处等于把禁令稀释掉。
        # 溯源不受影响：guidance 段本身就在同一份 canonical prompt 里，照样入 SHA。
        "template_id": str(item.get("template_id") or ""),
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
    return (
        _frontmatter(fields)
        + "\n\n"
        + f"Create a high-information Chinese infographic in {style} style using the "
        f"reviewed template {item.get('template_id')}. {palette}\n"
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
        f"- producer: {VISUAL_PRODUCER}",
        f"- style: {style}",
        f"- plan_digest: {stable_digest(plan)}",
        "",
    ]
    structured_lines = [
        "# Structured Visual Content",
        "",
        f"- producer: {VISUAL_PRODUCER}",
        f"- style: {style}",
        "",
    ]
    for item in plan["infographics"]:
        analysis_lines.append(
            f"- {item['id']} · {item['position']} · {item['aspect_ratio']} · "
            f"{item['layout']} · {item['title']}"
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
        tasks.append(
            {
                "id": task_id,
                "promptFiles": [f"prompts/final/{prompt_stem}.md"],
                "image": image_name,
                "ar": aspect,
            }
        )
    batch = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "plan_digest": stable_digest(plan),
        "jobs": 4,
        "tasks": tasks,
    }
    (cwd / "素材" / "render-batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "style": style,
        "plan_digest": stable_digest(plan),
        "batch": batch,
        "prompt_count": len(tasks),
    }
    (cwd / "素材" / "visual-compile-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result, []
