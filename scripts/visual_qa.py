#!/usr/bin/env python3
"""Structured visual QA contract for final, post-processed article images."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat
import yaml

try:
    from .evidence import build_visual_manifest, sha256_file
    from .profile_config import identity, load_secret, visual_profile
    from .evidence import stable_digest
except ImportError:  # pragma: no cover - direct script execution
    from evidence import build_visual_manifest, sha256_file
    from profile_config import identity, load_secret, visual_profile
    from evidence import stable_digest


QA_REQUEST_FILE = "_visual-qa-request.json"
QA_FILE = "_visual-qa.json"
QA_MARKDOWN_FILE = "_visual-qa.md"
REQUIRED_CHECKS = (
    "text_match",
    "crop_safe",
    "semantic_hierarchy",
    "style_consistent",
    "no_unexpected_text",
    "style_contract_match",
    "brand_palette_match",
)
COVER_REQUIRED_CHECKS = (*REQUIRED_CHECKS, "composition_contract_match")


def _normalized_text(value: object) -> str:
    return "".join(str(value or "").split()).casefold()


def _pixel_metrics(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        stat = ImageStat.Stat(rgb)
        width, height = rgb.size
        grayscale = rgb.convert("L")
        histogram = grayscale.histogram()
        pixels = max(1, width * height)
        dark = sum(histogram[:48])
        light = sum(histogram[224:])
        return {
            "width": width,
            "height": height,
            "aspect_ratio": round(width / height, 6),
            "mean_rgb": [round(value, 2) for value in stat.mean],
            "mean_luma": round(ImageStat.Stat(grayscale).mean[0], 2),
            "dark_pixel_ratio": round(dark / pixels, 6),
            "light_pixel_ratio": round(light / pixels, 6),
        }


def _expected_text_by_path(cwd: Path) -> tuple[dict[str, list[str]], list[str]]:
    path = cwd / "visual-plan.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, ["缺 visual-plan.json，无法建立 expected_text 合同"]
    except json.JSONDecodeError as exc:
        return {}, [f"visual-plan.json 解析失败：{exc}"]
    expected: dict[str, list[str]] = {}
    cover = plan.get("cover") or {}
    meta = {}
    try:
        meta = yaml.safe_load(
            (cwd / "article-meta.yaml").read_text(encoding="utf-8")
        ) or {}
    except (FileNotFoundError, yaml.YAMLError):
        pass
    lead = meta.get("lead") if isinstance(meta.get("lead"), dict) else {}
    uppercase = re.findall(
        r"(?<![A-Za-z0-9])[A-Z][A-Z0-9-]*(?![A-Za-z0-9])",
        str(meta.get("cover_keywords") or ""),
    )
    ghost = " × ".join(uppercase[-3:]) if len(uppercase) >= 3 else ""
    brand_name = str(identity().get("nickname") or "").strip()
    expected["素材/cover.png"] = [
        str(value).strip()
        for value in (
            lead.get("line1") or cover.get("title"),
            lead.get("line2") or cover.get("subtitle"),
            lead.get("subtitle"),
            ghost,
            brand_name,
        )
        if str(value or "").strip()
    ]
    hero = plan.get("hero") or {}
    expected["素材/hero.png"] = [
        str(value).strip()
        for value in (hero.get("title"),)
        if str(value or "").strip()
    ]
    for item in plan.get("infographics") or []:
        image_id = str(item.get("id") or "").strip()
        if not image_id:
            continue
        expected[f"素材/infographic-{image_id}.png"] = [
            str(value).strip()
            for value in (item.get("title"), *(item.get("expected_text") or []))
            if str(value or "").strip()
        ]
        if brand_name:
            expected[f"素材/infographic-{image_id}.png"].append(brand_name)
    return expected, []


def _template_id_by_path(cwd: Path) -> tuple[dict[str, str], list[str]]:
    try:
        plan = json.loads((cwd / "visual-plan.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, ["缺 visual-plan.json，无法建立模板合同"]
    except json.JSONDecodeError as exc:
        return {}, [f"visual-plan.json 解析失败：{exc}"]
    templates = {
        "素材/cover.png": "montage-evidence-v2",
        "素材/hero.png": "hero-convergence",
    }
    for item in plan.get("infographics") or []:
        image_id = str(item.get("id") or "").strip()
        template_id = str(item.get("template_id") or "").strip()
        if image_id and template_id:
            templates[f"素材/infographic-{image_id}.png"] = template_id
    return templates, []


def _validate_design_manifest(
    cwd: Path,
    asset: dict[str, Any],
    *,
    expected_template_id: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    rel = str(asset["path"])
    manifest_path = (cwd / Path(rel)).with_suffix(".design.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{rel} 缺 bound design manifest：{manifest_path.name}"]
    except json.JSONDecodeError as exc:
        return None, [f"{rel} design manifest 解析失败：{exc}"]
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append(f"{rel} design manifest schema_version 必须为 1")
    if manifest.get("template_id") != expected_template_id:
        errors.append(
            f"{rel} design manifest template_id={manifest.get('template_id') or '(空)'}；"
            f"应为 {expected_template_id}"
        )
    render_sha = str(asset.get("render_sha256") or "")
    if not render_sha or manifest.get("image_sha256") != render_sha:
        errors.append(f"{rel} design manifest 未绑定渲染时图片字节")
    safe = manifest.get("safe_bounds")
    text_boxes = manifest.get("text_boxes")
    elements = manifest.get("visual_elements")
    if not isinstance(safe, list) or len(safe) != 4:
        errors.append(f"{rel} design manifest 缺 safe_bounds")
    if not isinstance(text_boxes, list) or not text_boxes:
        errors.append(f"{rel} design manifest 缺 text_boxes")
    elif isinstance(safe, list) and len(safe) == 4:
        sx1, sy1, sx2, sy2 = safe
        for box in text_boxes:
            coords = box.get("box") if isinstance(box, dict) else None
            if not isinstance(coords, list) or len(coords) != 4:
                errors.append(f"{rel} design manifest 存在非法 text box")
                continue
            x1, y1, x2, y2 = coords
            if not (sx1 <= x1 < x2 <= sx2 and sy1 <= y1 < y2 <= sy2):
                errors.append(f"{rel} design manifest 文字框越出安全区：{coords}")
    if not isinstance(elements, list) or len(elements) < 4:
        errors.append(f"{rel} design manifest 视觉结构不足（visual_elements < 4）")
    return (manifest if not errors else None), errors


def _style_contracts(cwd: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    try:
        meta = yaml.safe_load(
            (cwd / "article-meta.yaml").read_text(encoding="utf-8")
        ) or {}
    except FileNotFoundError:
        return {}, ["缺 article-meta.yaml，无法建立目标风格合同"]
    except yaml.YAMLError as exc:
        return {}, [f"article-meta.yaml 解析失败：{exc}"]
    style = str(meta.get("infographic_style") or "").strip()
    profile_name = {
        "claymation": "warm-light-clay",
        "morandi-journal": "morandi-journal",
    }.get(style, "")
    cover_recipe = visual_profile("montage-evidence") or {}
    body_recipe = visual_profile(profile_name) or {}
    if not cover_recipe or not body_recipe:
        return {}, ["profile 缺封面或正文视觉配方，无法建立目标风格合同"]

    def summarize(recipe: dict, *, layout: str = "") -> dict[str, Any]:
        bound = dict(recipe)
        digest = stable_digest(bound)
        return {
            "visual_profile": bound.get("name"),
            "visual_profile_sha256": digest,
            "layout": layout or bound.get("layout") or "",
            "palette": {
                "background": bound.get("background"),
                "accent": bound.get("accent"),
                "neutrals": bound.get("neutrals") or [],
            },
            "required_visual_traits": bound.get("required_visual_traits") or [],
            "forbidden_visual_traits": bound.get("forbidden_visual_traits") or [],
        }

    contracts = {
        "cover": {
            "target_style": "montage-evidence",
            "required_checks": list(COVER_REQUIRED_CHECKS),
            "style_contract": summarize(
                cover_recipe, layout="left-50-gap-6-right-44"
            ),
        },
        "hero": {
            "target_style": style,
            "required_checks": list(REQUIRED_CHECKS),
            "style_contract": summarize(body_recipe),
        },
        "infographic": {
            "target_style": style,
            "required_checks": list(REQUIRED_CHECKS),
            "style_contract": summarize(body_recipe),
        },
    }
    return contracts, []


def build_qa_request(cwd: Path) -> tuple[dict[str, Any] | None, list[str]]:
    cwd = cwd.resolve()
    manifest, errors = build_visual_manifest(
        cwd, strict=True, allow_postprocessed=True
    )
    expected, expected_errors = _expected_text_by_path(cwd)
    errors.extend(expected_errors)
    contracts, contract_errors = _style_contracts(cwd)
    errors.extend(contract_errors)
    template_ids, template_errors = _template_id_by_path(cwd)
    errors.extend(template_errors)
    assets = []
    for asset in manifest.get("assets", []):
        rel = str(asset["path"])
        if rel not in expected or not expected[rel]:
            errors.append(f"{rel} 缺 expected_text")
            continue
        image_path = cwd / Path(rel)
        try:
            metrics = _pixel_metrics(image_path)
        except Exception as exc:
            errors.append(f"{rel} 无法读取像素：{exc}")
            continue
        contract = copy.deepcopy(contracts.get(str(asset["stage"])) or {})
        design_manifest = None
        if asset.get("renderer") in {
            "deterministic-compositor",
            "deterministic-template-compositor",
        }:
            expected_template_id = template_ids.get(rel, "")
            if not expected_template_id:
                errors.append(f"{rel} 缺 template_id 合同")
                continue
            design_manifest, design_errors = _validate_design_manifest(
                cwd,
                asset,
                expected_template_id=expected_template_id,
            )
            errors.extend(design_errors)
            if design_errors:
                continue
            style_contract = contract.get("style_contract") or {}
            style_contract["variant"] = "reviewed-template-text-safe"
            style_contract["layout"] = expected_template_id
            style_contract["required_visual_traits"] = [
                *(style_contract.get("required_visual_traits") or []),
                *[str(value) for value in design_manifest.get("visual_elements") or []],
                "exact local Chinese typography inside crop-safe registered boxes",
            ]
            contract["style_contract"] = style_contract
        assets.append(
            {
                "path": rel,
                "sha256": asset["sha256"],
                "stage": asset["stage"],
                "expected_text": expected[rel],
                "pixel_metrics": metrics,
                "generation": {
                    "producer": asset.get("producer") or "",
                    "renderer": asset.get("renderer") or "",
                    "model": asset.get("model") or "",
                },
                **({"design_manifest": design_manifest} if design_manifest else {}),
                **contract,
            }
        )
    if errors:
        return None, errors
    request = {
        "schema_version": 1,
        "contract": {
            "reviewer_role": "independent-visual-reviewer",
            "required_checks": list(REQUIRED_CHECKS),
            "stage_specific_checks": {
                "cover": list(COVER_REQUIRED_CHECKS),
                "hero": list(REQUIRED_CHECKS),
                "infographic": list(REQUIRED_CHECKS),
            },
            "all_checks_must_pass": True,
            "expected_text_must_be_observed": True,
        },
        "assets": assets,
    }
    return request, []


def _request_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_qa_result(
    cwd: Path,
    qa: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
) -> list[str]:
    cwd = cwd.resolve()
    errors: list[str] = []
    request_path = cwd / QA_REQUEST_FILE
    if request is None:
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [f"缺 {QA_REQUEST_FILE}"]
        except json.JSONDecodeError as exc:
            return [f"{QA_REQUEST_FILE} 解析失败：{exc}"]
    if qa.get("schema_version") != 1:
        errors.append("visual QA schema_version 必须为 1")
    if qa.get("status") != "pass":
        errors.append("visual QA status 必须为 pass")
    if not request_path.exists() or qa.get("request_sha256") != _request_sha256(
        request_path
    ):
        errors.append("visual QA 未绑定当前 request 字节")

    reviewer = qa.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("visual QA 缺 reviewer")
        reviewer = {}
    if reviewer.get("role") != "independent-visual-reviewer":
        errors.append("visual QA reviewer.role 必须为 independent-visual-reviewer")
    if reviewer.get("independent") is not True:
        errors.append("visual QA 必须由独立运行完成")
    reviewer_model = str(reviewer.get("model") or "").strip()
    if not reviewer_model:
        errors.append("visual QA 缺 reviewer.model")
    if not str(reviewer.get("run_id") or "").strip():
        errors.append("visual QA 缺 reviewer.run_id")
    generation_models = {
        str(asset.get("generation", {}).get("model") or "").strip()
        for asset in request.get("assets", [])
    }
    generation_models.discard("")
    if reviewer_model and reviewer_model in generation_models:
        errors.append("视觉复核模型必须独立于生图模型")

    expected_assets = {
        str(asset["path"]): asset for asset in request.get("assets", [])
    }
    qa_assets = qa.get("assets")
    if not isinstance(qa_assets, list):
        return errors + ["visual QA assets 必须为列表"]
    actual_assets = {
        str(asset.get("path") or ""): asset
        for asset in qa_assets
        if isinstance(asset, dict)
    }
    if set(actual_assets) != set(expected_assets):
        errors.append(
            "visual QA 资产集合与 request 不一致："
            f"expected={sorted(expected_assets)} actual={sorted(actual_assets)}"
        )
    for rel, expected_asset in expected_assets.items():
        actual = actual_assets.get(rel)
        if not actual:
            continue
        image_path = cwd / Path(rel)
        if not image_path.is_file() or sha256_file(image_path) != expected_asset["sha256"]:
            errors.append(f"{rel} 最终图片字节已变化（sha256 不一致）")
        if actual.get("sha256") != expected_asset["sha256"]:
            errors.append(f"{rel} QA 记录 sha256 与 request 不一致")
        checks = actual.get("checks")
        if not isinstance(checks, dict):
            errors.append(f"{rel} 缺 checks")
        else:
            required_checks = expected_asset.get("required_checks") or list(
                REQUIRED_CHECKS
            )
            for check in required_checks:
                if checks.get(check) is not True:
                    errors.append(f"{rel} check.{check} 未通过")
        observed_values = [
            _normalized_text(value) for value in actual.get("observed_text") or []
        ]
        observed = set(observed_values)
        observed_joined = "".join(observed_values)
        missing = [
            value
            for value in expected_asset.get("expected_text") or []
            if (
                _normalized_text(value) not in observed
                and _normalized_text(value) not in observed_joined
            )
        ]
        if missing:
            errors.append(f"{rel} observed_text 缺 expected_text：{missing}")
    return errors


def _write_markdown(cwd: Path, qa: dict[str, Any]) -> None:
    reviewer = qa["reviewer"]
    lines = [
        "# 视觉验收记录",
        "",
        "> 此文件由 _visual-qa.json 派生；发布授权只认 JSON 与最终图片字节。",
        "",
        f"- 审阅模型：{reviewer['model']}",
        f"- 独立运行：{reviewer['run_id']}",
        "",
    ]
    for asset in qa["assets"]:
        lines.extend(
            [
                f"## {asset['path']}",
                "",
                f"- ✅ 文字：{' / '.join(asset.get('observed_text') or [])}",
                *[
                    f"- {'✅' if asset['checks'][check] else '❌'} {check}"
                    for check in asset["checks"]
                ],
                f"- 备注：{asset.get('notes') or '无'}",
                "",
            ]
        )
    lines.extend(["## 结论", "", "✅ 通过", ""])
    (cwd / QA_MARKDOWN_FILE).write_text("\n".join(lines), encoding="utf-8")


def _resolve_reviewer_command() -> tuple[list[str] | None, list[str]]:
    # 读取顺序 shell env → 仓根 .env（与 profile/data 指针、各家 key 同一个配置面，
    # 换机复刻只需拷一份 .env）。这里刻意**不**给默认复核器：
    # 谁来看图必须由使用者显式指定，skill 自己指派一个复核器就等于自己给自己发合格证。
    raw = load_secret("SANSHENG_WRITE_VISUAL_QA_COMMAND", required=False).strip()
    if not raw:
        return None, [
            "缺 SANSHENG_WRITE_VISUAL_QA_COMMAND；视觉 QA 必须交给独立看图进程"
            "（可用适配器：scripts/visual_qa_codex.py，见 references/release-runtime.md §4）"
        ]
    try:
        if raw.startswith("["):
            value = json.loads(raw)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value, []
            return None, ["SANSHENG_WRITE_VISUAL_QA_COMMAND JSON 必须是字符串数组"]
        return shlex.split(raw, posix=os.name != "nt"), []
    except (ValueError, json.JSONDecodeError) as exc:
        return None, [f"SANSHENG_WRITE_VISUAL_QA_COMMAND 解析失败：{exc}"]


def run_visual_qa(
    cwd: Path,
    *,
    reviewer_command: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    cwd = cwd.resolve()
    request, errors = build_qa_request(cwd)
    if errors or request is None:
        return None, errors
    request_path = cwd / QA_REQUEST_FILE
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    command = reviewer_command
    if command is None:
        command, resolve_errors = _resolve_reviewer_command()
        if resolve_errors or command is None:
            return None, resolve_errors
    candidate = cwd / "_visual-qa.candidate.json"
    if candidate.exists():
        candidate.unlink()
    completed = subprocess.run(
        [*command, "--request", str(request_path), "--output", str(candidate)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        return None, [
            f"独立视觉复核进程失败（exit={completed.returncode}）："
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        ]
    try:
        qa = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["独立视觉复核没有产出 JSON"]
    except json.JSONDecodeError as exc:
        return None, [f"独立视觉复核 JSON 解析失败：{exc}"]
    if not isinstance(qa, dict):
        return None, ["独立视觉复核 JSON 顶层必须为对象"]
    validation_errors = validate_qa_result(cwd, qa, request=request)
    if validation_errors:
        candidate.unlink(missing_ok=True)
        return None, validation_errors
    final_path = cwd / QA_FILE
    candidate.replace(final_path)
    _write_markdown(cwd, qa)
    return qa, []


def main() -> None:
    qa, errors = run_visual_qa(Path.cwd())
    if errors:
        print("❌ 视觉 QA 未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(f"✅ 独立视觉 QA 通过：{len(qa['assets'])} 张最终图片")


if __name__ == "__main__":
    main()
