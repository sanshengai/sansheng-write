#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Code-owned signature visual contracts.

These contracts are product identity, not per-account theme tokens.  A private
profile may change the website/article accent colour, but it must not silently
turn the article illustration system into a different palette or material.
"""

from __future__ import annotations

import copy


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

