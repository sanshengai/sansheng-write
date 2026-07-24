#!/usr/bin/env python3
"""Structured visual QA contract for final, post-processed article images."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

try:
    from .evidence import build_visual_manifest, sha256_file
except ImportError:  # pragma: no cover - direct script execution
    from evidence import build_visual_manifest, sha256_file


QA_REQUEST_FILE = "_visual-qa-request.json"
QA_FILE = "_visual-qa.json"
QA_MARKDOWN_FILE = "_visual-qa.md"
REQUIRED_CHECKS = (
    "text_match",
    "crop_safe",
    "semantic_hierarchy",
    "style_consistent",
    "no_unexpected_text",
)


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
    expected["素材/cover.png"] = [
        str(value).strip()
        for value in (cover.get("title"), cover.get("subtitle"))
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
            str(value).strip() for value in item.get("expected_text") or []
        ]
    return expected, []


def build_qa_request(cwd: Path) -> tuple[dict[str, Any] | None, list[str]]:
    cwd = cwd.resolve()
    manifest, errors = build_visual_manifest(
        cwd, strict=True, allow_postprocessed=True
    )
    expected, expected_errors = _expected_text_by_path(cwd)
    errors.extend(expected_errors)
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
            }
        )
    if errors:
        return None, errors
    request = {
        "schema_version": 1,
        "contract": {
            "reviewer_role": "independent-visual-reviewer",
            "required_checks": list(REQUIRED_CHECKS),
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
            for check in REQUIRED_CHECKS:
                if checks.get(check) is not True:
                    errors.append(f"{rel} check.{check} 未通过")
        observed = {
            _normalized_text(value) for value in actual.get("observed_text") or []
        }
        missing = [
            value
            for value in expected_asset.get("expected_text") or []
            if _normalized_text(value) not in observed
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
                    for check in REQUIRED_CHECKS
                ],
                f"- 备注：{asset.get('notes') or '无'}",
                "",
            ]
        )
    lines.extend(["## 结论", "", "✅ 通过", ""])
    (cwd / QA_MARKDOWN_FILE).write_text("\n".join(lines), encoding="utf-8")


def _resolve_reviewer_command() -> tuple[list[str] | None, list[str]]:
    raw = os.getenv("SANSHENG_WRITE_VISUAL_QA_COMMAND", "").strip()
    if not raw:
        return None, [
            "缺 SANSHENG_WRITE_VISUAL_QA_COMMAND；视觉 QA 必须交给独立看图进程"
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
