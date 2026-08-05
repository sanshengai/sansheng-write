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


COVER_TEXT_CONTRACT_REVISION = "montage-cover-text/1"


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
    cover tag.  Cover tags come from ``lead.tag1`` and ``lead.tag2`` only.
    """

    errors: list[str] = []
    lead = meta.get("lead") if isinstance(meta.get("lead"), dict) else {}
    if not lead:
        return {}, ["article-meta.yaml 缺 lead，无法建立封面文字合同"]

    values: dict[str, str] = {}
    for key in ("line1", "line2", "accent", "tag1", "tag2"):
        raw = lead.get(key)
        if raw is not None and not isinstance(raw, str):
            errors.append(f"lead.{key} 必须是字符串")
            values[key] = ""
        else:
            values[key] = str(raw or "").strip()

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

    tags = [values["tag1"], values["tag2"]]
    for index, tag in enumerate(tags, start=1):
        if tag and visual_text_width(tag) > 4:
            errors.append(f"lead.tag{index} 超过 4 个汉字位，封面胶囊会失稳")
    if all(tags) and tags[0] == tags[1]:
        errors.append("lead.tag1 与 lead.tag2 不得重复")

    return {
        "contract_revision": COVER_TEXT_CONTRACT_REVISION,
        "line1": values["line1"],
        "line2": values["line2"],
        "accent_phrase": values["accent"],
        "tags": tags,
    }, errors
