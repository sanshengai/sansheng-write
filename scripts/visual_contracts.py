#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Code-owned signature visual contracts.

These contracts are product identity, not per-account theme tokens.  A private
profile may change the website/article accent colour, but it must not silently
turn the article illustration system into a different palette or material.
"""

from __future__ import annotations

import copy
import re


COVER_TEXT_CONTRACT_REVISION = "montage-cover-text/3"

# 封面 ghost 层：标题后方那行半隐英文。2026-07-28 曾整层删除（当时 ghost 比 L1 还大、
# 抢走视觉主体），2026-09-16 作者复核后恢复 —— 要的是「低对比背景纹理」，不是删掉。
# 文案必须显式声明在 lead.ghost，禁止模型自拟（旧版从 cover_keywords 抽词，取不到
# 就让模型自编，实测编出过重复词）。格式：2--3 个全大写 ASCII 词组，用「×」连接。
COVER_GHOST_SEPARATOR = "×"
COVER_GHOST_TERM_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &'-]*$")
COVER_GHOST_MIN_TERMS = 2
COVER_GHOST_MAX_TERMS = 3
COVER_GHOST_TERM_MAX_CHARS = 14
COVER_GHOST_MAX_CHARS = 32
# 胶囊标签：2 项必填，第 3 项可选（作者认可的第 75/76 篇封面都是三标签）。
COVER_TAG_MAX_COUNT = 3


def cover_ghost_terms(value: object) -> tuple[list[str], list[str]]:
    """Split ``lead.ghost`` into its uppercase terms and report contract errors."""

    errors: list[str] = []
    raw = str(value or "").strip()
    if not raw:
        return [], ["lead.ghost 不能为空（封面标题后方的半隐英文，2--3 个全大写词组，用 × 连接）"]
    terms = [part.strip() for part in raw.split(COVER_GHOST_SEPARATOR)]
    if any(not term for term in terms):
        errors.append("lead.ghost 有空的词组（× 两侧都要有内容）")
        terms = [term for term in terms if term]
    if not (COVER_GHOST_MIN_TERMS <= len(terms) <= COVER_GHOST_MAX_TERMS):
        errors.append(
            f"lead.ghost 必须是 {COVER_GHOST_MIN_TERMS}--{COVER_GHOST_MAX_TERMS} 个词组"
            f"（用 {COVER_GHOST_SEPARATOR} 连接），当前 {len(terms)} 个"
        )
    for term in terms:
        if not COVER_GHOST_TERM_RE.match(term):
            errors.append(
                f"lead.ghost 词组 {term!r} 只能用大写英文字母、数字、空格、& 和连字符"
            )
        if len(term) > COVER_GHOST_TERM_MAX_CHARS:
            errors.append(
                f"lead.ghost 词组 {term!r} 超过 {COVER_GHOST_TERM_MAX_CHARS} 个字符，单行放不下"
            )
    canonical = f" {COVER_GHOST_SEPARATOR} ".join(terms)
    if len(canonical) > COVER_GHOST_MAX_CHARS:
        errors.append(
            f"lead.ghost 整行超过 {COVER_GHOST_MAX_CHARS} 个字符（{len(canonical)}），会被迫折行或缩小"
        )
    return terms, errors


SIGNATURE_VISUAL_PROFILES = {
    "warm-light-clay": {
        "contract_owner": "sansheng-write",
        "contract_revision": "warm-light-clay/2",
        "baoyu_role": "content-analysis-and-layout-only",
        "style": "claymation",
        "background": "#F7F2E9",
        # Deliberately independent from brand.colors.primary.  The account theme
        # green (#0E926F at the time of this fix) was too dark once rendered as
        # chunky clay type and caused visible cross-article drift.
        "accent": "#79AA95",
        "accent_shadow": "#5F8775",
        "neutrals": ["#FCFAF5", "#DDD7CC", "#8A8178"],
        "material": "matte soft clay, no metallic or photorealistic surface",
        "lighting": "high-key diffuse studio light, very low contrast, feather-soft shadows",
        "tone_policy": {
            "light_surface_ratio_min": 0.72,
            "dark_design_area_ratio_max": 0.08,
            "accent_usage": "pastel jade is an accent only; never a dark field or dominant mass",
            "darkest_tone_usage": "micro-details and contact shadows only; never large headings or panels",
        },
        "required_prompt_groups": [
            ["warm ivory", "暖象牙白", "暖米白"],
            ["high-key pastel palette", "浅色粉彩", "高明度浅色调"],
            ["pale pastel jade", "light muted jade", "浅玉绿色"],
            ["matte clay", "soft clay", "哑光黏土", "软黏土"],
            ["diffuse light", "soft lighting", "柔和漫射", "低对比"],
            ["extruded clay letters", "dimensional rounded clay text", "立体黏土字"],
            ["embedded in the clay scene", "integrated into the clay scene", "嵌入黏土场景"],
        ],
        "forbidden_prompt_terms": [
            "charcoal background",
            "dark background",
            "black background",
            "navy",
            "steel blue",
            "brick red",
            "mustard yellow",
            "forest green",
            "dark green",
            "deep jade",
            "saturated green",
            "metallic",
            "chrome",
            "neon",
            "high contrast",
            "deep background",
        ],
        "forbidden_prompt_phrases": [
            "handwritten editorial marker",
            "brush-pen character",
            "not playful toy art",
            "not cartoonish",
            "serious business publication",
        ],
        "required_visual_traits": [
            "high-key warm-ivory miniature editorial scene made from matte soft clay",
            "pastel jade-green appears only as a light accent; most of the canvas remains warm ivory and pale neutral",
            "all visible Chinese title and labels use extruded dimensional rounded chunky clay letters",
            "large clay headings use pale or mid-tone clay, never dark forest-green or near-black",
            "visible text is physically embedded into the clay scene with the same material language as nearby objects",
            "subtle hand-sculpted or fingerprint texture with diffuse low-contrast light and feather-soft shadows",
            "clear title greater than section greater than detail hierarchy with generous crop-safe spacing",
        ],
        "forbidden_visual_traits": [
            "flat printed geometric or corporate sans-serif headings and labels",
            "handwritten marker, brush-pen, calligraphy or chalk lettering",
            "all or most text items enclosed by backing plates, boxes, ribbons or cards",
            "glossy plastic, metallic, chrome, glass, neon or photorealistic surfaces",
            "dark background or a second design hue outside pastel jade-green and warm neutrals",
            "large dark-green headings, arrows, panels or continuous paths dominating the page",
            "large near-black or deep-colour surfaces exceeding small contact shadows and micro-details",
        ],
        "thresholds": {
            "mean_luma_min": 192,
            "dark_pixel_luma": 96,
            "dark_pixel_ratio_max": 0.09,
            "mean_saturation_max": 0.24,
        },
    }
}


def signature_visual_profile(name: str) -> dict:
    """Return an immutable product-level profile, or an empty dict."""
    raw = SIGNATURE_VISUAL_PROFILES.get(str(name or "").strip())
    return copy.deepcopy(raw) if raw else {}


def visual_text_width(value: object) -> float:
    """Return the visual width used by the cover/lead contracts.

    CJK glyphs count as one unit, ASCII and other glyphs as half a unit, and
    whitespace does not consume a slot.  This deliberately matches the lead
    audit in ``contracts.py`` so the same metadata cannot pass one consumer and
    fail another.
    """

    width = 0.0
    for char in str(value or ""):
        if char.isspace():
            continue
        width += 1.0 if re.match(r"[\u4e00-\u9fff]", char) else 0.5
    return width


def cover_text_contract(meta: dict) -> tuple[dict, list[str]]:
    """Resolve and validate the only supported montage-cover text schema.

    ``lead.subtitle`` is the article lead subtitle.  It is intentionally not a
    cover tag.  Cover tags come from ``lead.tag1`` / ``lead.tag2`` (required) and
    ``lead.tag3`` (optional).  ``lead.ghost`` is the subdued uppercase English
    line rendered behind the headline; it must be declared, never model-invented.
    """

    errors: list[str] = []
    lead = meta.get("lead") if isinstance(meta.get("lead"), dict) else {}
    if not lead:
        return {}, ["article-meta.yaml 缺 lead，无法建立封面文字合同"]

    values: dict[str, str] = {}
    for key in ("line1", "line2", "accent", "tag1", "tag2", "tag3", "ghost"):
        raw = lead.get(key)
        if raw is not None and not isinstance(raw, str):
            errors.append(f"lead.{key} 必须是字符串")
            values[key] = ""
        else:
            values[key] = str(raw or "").strip()

    identity = meta.get("cover_identity")
    if identity is not None and not isinstance(identity, str):
        errors.append("cover_identity 必须是字符串")
        identity = ""
    identity = str(identity or "").strip()
    if identity and identity not in (values.get("line1", "") + values.get("line2", "")):
        errors.append(
            f"cover_identity={identity!r} 必须显式进入封面 L1/L2；底部小标签不算"
        )

    subtitle = lead.get("subtitle")
    if subtitle is not None and not isinstance(subtitle, str):
        errors.append(
            "lead.subtitle 必须是字符串；封面标签只使用 lead.tag1 / lead.tag2"
        )

    required = {
        "line1": "封面 L1",
        "line2": "封面 L2",
        "accent": "封面 L2 主题色落点",
        "tag1": "封面胶囊标签 1",
        "tag2": "封面胶囊标签 2",
        "ghost": "封面标题后方的半隐英文",
    }
    for key, label in required.items():
        if not values[key]:
            errors.append(f"lead.{key} 不能为空（{label}）")

    if values["line1"] and visual_text_width(values["line1"]) > 8:
        errors.append("lead.line1 超过 8 个汉字位，封面主标题会被迫缩小")
    if values["line2"] and visual_text_width(values["line2"]) > 12:
        errors.append("lead.line2 超过 12 个汉字位，封面副标题无法保持单行")

    accent_width = visual_text_width(values["accent"])
    if values["accent"] and not (2 <= accent_width <= 5):
        errors.append("lead.accent 必须为 2--5 个汉字位")
    if (
        values["accent"]
        and values["line2"]
        and not values["line2"].endswith(values["accent"])
    ):
        errors.append("lead.accent 必须是 lead.line2 的结尾子串")

    # tag3 可选：填了就进胶囊，空着就是两标签。
    tags = [values["tag1"], values["tag2"]] + (
        [values["tag3"]] if values["tag3"] else []
    )
    for index, tag in enumerate(tags, start=1):
        if tag and visual_text_width(tag) > 4:
            errors.append(f"lead.tag{index} 超过 4 个汉字位，封面胶囊会失稳")
    filled = [tag for tag in tags if tag]
    if len(set(filled)) != len(filled):
        errors.append("lead.tag1 / tag2 / tag3 不得重复")

    ghost_terms: list[str] = []
    if values["ghost"]:  # 缺失已由上面的必填检查报过，不重复报
        ghost_terms, ghost_errors = cover_ghost_terms(values["ghost"])
        errors.extend(ghost_errors)
    ghost = f" {COVER_GHOST_SEPARATOR} ".join(ghost_terms) if ghost_terms else ""

    return {
        "contract_revision": COVER_TEXT_CONTRACT_REVISION,
        "line1": values["line1"],
        "line2": values["line2"],
        "accent_phrase": values["accent"],
        "tags": tags,
        "ghost": ghost,
        "ghost_terms": ghost_terms,
    }, errors
