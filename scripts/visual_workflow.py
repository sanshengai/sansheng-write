#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile a restricted article visual plan into canonical renderer prompts."""

from __future__ import annotations

import hashlib
import json
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
        for field in ("id", "position", "aspect_ratio", "title", "layout"):
            if not str(item.get(field) or "").strip():
                errors.append(f"{label}.{field} 不能为空")
        if not _nonempty_list(item.get("expected_text")):
            errors.append(f"{label}.expected_text 必须是非空字符串列表")
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
    if style != "claymation":
        if meta.get("visual_profile"):
            errors.append("morandi-journal 不得填写 visual_profile")
        return {}, errors
    name = str(meta.get("visual_profile") or "")
    if name != "warm-light-clay":
        errors.append("claymation 必须 visual_profile: warm-light-clay")
        return {}, errors
    recipe = visual_profile(name) or {}
    if not recipe:
        errors.append("profile 中缺 warm-light-clay 视觉配方")
        return {}, errors
    recipe = dict(recipe)
    recipe["sha256"] = stable_digest(recipe)
    return recipe, errors


def _cover_prompt(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    subtitle = str(item.get("subtitle") or "").strip()
    facts = "\n".join(f"- {value}" for value in item.get("visual_facts") or [])
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "stage": "cover",
        "style": "montage-evidence",
        "aspect_ratio": "2.35:1",
        "title_block_height": "20%",
        "expected_text_sha256": _expected_text_digest(
            [value for value in (title, subtitle) if value]
        ),
    }
    return (
        _frontmatter(fields)
        + "\n"
        + "\nCreate a bright editorial evidence montage for a WeChat article cover.\n"
        "Composition: a restrained 2-4 fragment collage that visualizes the supplied facts, "
        "with generous negative space and a clear left-to-right hierarchy.\n"
        "Typography: render only the exact Chinese title and subtitle below. "
        "The complete title block must occupy 18%-22% of image height; keep all text inside "
        "the central crop-safe region. No extra words, logos, watermarks, fake UI, dark "
        "technology background, neon, extra-black or ultra-black type.\n\n"
        f"Exact title: {title}\n"
        f"Exact subtitle: {subtitle or '(none)'}\n"
        f"Verified visual facts:\n{facts}\n"
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
    facts = "\n".join(f"- {value}" for value in item.get("visual_facts") or [])
    palette = (
        "Warm beige light palette, matte soft clay, bright diffuse studio light, "
        "low contrast and soft shadows. No metallic, photorealistic, navy, black, "
        "neon or high-contrast surface."
        if recipe
        else "Muted Morandi pastel palette, tactile editorial paper collage, soft natural "
        "light and restrained contrast. No dark technology background or neon."
    )
    return (
        _frontmatter(fields)
        + "\n\n"
        + f"Create a square article Hero in {style} style. {palette}\n"
        "Show one unmistakable visual hierarchy and render only the exact Chinese title. "
        "No extra words, logos, watermarks or invented interface.\n\n"
        f"Exact title: {expected[0]}\nVerified visual facts:\n{facts}\n"
    )


def _infographic_prompt(item: dict, style: str, recipe: dict) -> str:
    expected = [str(value) for value in item.get("expected_text") or []]
    fields = {
        "schema_version": 1,
        "producer": VISUAL_PRODUCER,
        "stage": "infographic",
        "id": str(item.get("id") or ""),
        "position": str(item.get("position") or ""),
        "style": style,
        "layout": str(item.get("layout") or ""),
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
    facts = "\n".join(f"- {value}" for value in item.get("facts") or [])
    labels = "\n".join(f"- {value}" for value in expected)
    palette = (
        "Warm beige or warm ivory background, bright light palette, matte soft clay "
        "information objects, diffuse light, low contrast and soft shadows. Avoid dark "
        "background, navy, steel blue, brick red, mustard yellow, metallic, chrome, "
        "neon and photorealistic surfaces."
        if recipe
        else "Muted Morandi pastel editorial journal, tactile paper collage, quiet warm "
        "background, restrained saturation and soft natural light. Avoid dark technology "
        "backgrounds, neon, chrome and photorealistic stock imagery."
    )
    return (
        _frontmatter(fields)
        + "\n\n"
        + f"Create a high-information Chinese infographic in {style} style using the "
        f"{item.get('layout')} layout. {palette}\n"
        "The graphic must communicate the verified facts below, not merely decorate them. "
        "Render every expected label exactly once in readable Simplified Chinese. "
        "Do not invent numbers, labels, logos, watermarks, product UI or additional text. "
        "Keep all labels inside crop-safe margins and make the title > sections > details "
        "hierarchy obvious at thumbnail size.\n\n"
        f"Exact title: {item.get('title')}\n"
        f"Expected labels:\n{labels}\n"
        f"Verified facts:\n{facts}\n"
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
    cover_prompt.write_text(_cover_prompt(plan["cover"]), encoding="utf-8")
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
