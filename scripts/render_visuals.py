#!/usr/bin/env python3
"""Render compiled visual tasks through a capability-checked external renderer.

The article visual rules and canonical prompts belong to sansheng-write.  This
adapter delegates pixels only, currently to baoyu-image-gen's CLI contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .visual_workflow import VISUAL_PRODUCER
except ImportError:  # pragma: no cover - direct script execution
    from visual_workflow import VISUAL_PRODUCER


REQUIRED_CAPABILITIES = {
    "--batchfile",
    "--jobs",
    "--json",
    "--promptfiles",
    "--image",
    "--provider",
    "--model",
    "--ar",
    "--quality",
    "--imageSize",
}

NATIVE_GOOGLE_PROVIDER = "sansheng-google"
NATIVE_GOOGLE_TEXT_SAFE_PROVIDER = "sansheng-google-text-safe"
NATIVE_PROVIDERS = {NATIVE_GOOGLE_PROVIDER, NATIVE_GOOGLE_TEXT_SAFE_PROVIDER}
TARGET_DIMENSIONS = {
    "2.35:1": (1024, 436),
    "1:1": (1024, 1024),
    "9:16": (576, 1024),
    "16:9": (1024, 576),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_output(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        # Some launchers print a harmless prefix. Prefer the last JSON object.
        starts = [index for index, char in enumerate(text) if char == "{"]
        for index in reversed(starts):
            try:
                value = json.loads(text[index:])
            except json.JSONDecodeError:
                continue
            return value if isinstance(value, dict) else None
    return None


def probe_renderer(command: list[str]) -> dict[str, Any]:
    """Verify the renderer exposes the exact non-interactive batch contract."""
    try:
        completed = subprocess.run(
            [*command, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "renderer": "baoyu-image-gen",
            "capabilities": [],
            "error": f"renderer probe 失败：{exc}",
        }
    help_text = f"{completed.stdout}\n{completed.stderr}"
    found = sorted(flag for flag in REQUIRED_CAPABILITIES if flag in help_text)
    missing = sorted(REQUIRED_CAPABILITIES.difference(found))
    return {
        "ok": completed.returncode == 0 and not missing,
        "renderer": "baoyu-image-gen",
        "capabilities": found,
        "missing": missing,
        "returncode": completed.returncode,
        "error": (
            ""
            if completed.returncode == 0 and not missing
            else f"缺少 renderer capability：{', '.join(missing) or 'help 执行失败'}"
        ),
    }


def _candidate_renderer_dirs() -> list[Path]:
    explicit = os.getenv("BAOYU_IMAGE_GEN_DIR", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    home = Path.home()
    patterns = [
        ".codex/plugins/cache/baoyu-skills/**/skills/baoyu-image-gen",
        ".claude/plugins/cache/baoyu-skills/**/skills/baoyu-image-gen",
        ".agents/skills/baoyu-image-gen",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(home.glob(pattern))
    return sorted(
        {path.resolve() for path in candidates if (path / "scripts/main.ts").is_file()},
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )


def resolve_renderer_command() -> tuple[list[str] | None, str, list[str]]:
    """Resolve an installed baoyu-image-gen without embedding a cache version."""
    override = os.getenv("SANSHENG_WRITE_IMAGE_COMMAND", "").strip()
    if override:
        command = shlex.split(override, posix=os.name != "nt")
        return (command or None), "configured-command", ([] if command else ["配置命令为空"])

    candidates = _candidate_renderer_dirs()
    if not candidates:
        return None, "", [
            "未找到 baoyu-image-gen；请安装插件或设置 BAOYU_IMAGE_GEN_DIR"
        ]
    entrypoint = candidates[0] / "scripts/main.ts"
    bun = shutil.which("bun")
    if bun:
        command = [bun, str(entrypoint)]
    else:
        npx = shutil.which("npx")
        if not npx:
            return None, "", ["未找到 bun 或 npx，无法执行 baoyu-image-gen"]
        command = [npx, "-y", "bun", str(entrypoint)]
    return command, _renderer_revision(candidates[0]), []


def _renderer_revision(renderer_dir: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(renderer_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    revision = completed.stdout.strip()
    if completed.returncode == 0 and revision:
        return revision
    return f"main.ts-sha256:{_sha256(renderer_dir / 'scripts/main.ts')}"


def _load_policy(cwd: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = cwd / "renderer-policy.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [], [f"renderer-policy.json 无法读取：{exc}"]
        renderers = payload.get("renderers") if isinstance(payload, dict) else None
        if not isinstance(renderers, list) or not renderers:
            return [], ["renderer-policy.json 必须包含非空 renderers 数组"]
    else:
        renderers = [
            {
                "id": "baoyu-default",
                "provider": None,
                "model": None,
                "quality": "2k",
                "imageSize": "1K",
            }
        ]

    allowed = {"id", "provider", "model", "quality", "imageSize"}
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(renderers):
        if not isinstance(item, dict):
            errors.append(f"renderers[{index}] 必须是对象")
            continue
        unknown = sorted(set(item).difference(allowed))
        if unknown:
            errors.append(f"renderers[{index}] 含未知字段：{', '.join(unknown)}")
            continue
        renderer_id = str(item.get("id") or f"attempt-{index + 1}").strip()
        normalized.append(
            {
                "id": renderer_id,
                "provider": item.get("provider") or None,
                "model": item.get("model") or None,
                "quality": item.get("quality") or "2k",
                "imageSize": item.get("imageSize") or "1K",
            }
        )
    return normalized, errors


def _load_batch(cwd: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = cwd / "素材/render-batch.json"
    try:
        batch = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["缺少 素材/render-batch.json；先运行 compile-visuals"]
    except json.JSONDecodeError as exc:
        return None, [f"render-batch.json 不是合法 JSON：{exc}"]
    if not isinstance(batch, dict) or batch.get("producer") != VISUAL_PRODUCER:
        return None, [f"render batch producer 必须是 {VISUAL_PRODUCER}"]
    tasks = batch.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None, ["render batch 必须包含非空 tasks"]
    required = {"id", "promptFiles", "image", "ar"}
    errors = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not required.issubset(task):
            errors.append(f"tasks[{index}] 缺少字段：{sorted(required)}")
    return (batch if not errors else None), errors


def _stage(task_id: str) -> str:
    if task_id == "cover":
        return "cover"
    if task_id == "hero":
        return "hero"
    return "infographic"


def _prompt_meta(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        value = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def _run_native_google_task(
    cwd: Path,
    task: dict[str, Any],
    renderer: dict[str, Any],
) -> dict[str, Any]:
    """Render one canonical prompt through the skill-owned Google/Vertex client."""
    aspect = str(task.get("ar") or "")
    dimensions = TARGET_DIMENSIONS.get(aspect)
    task_id = str(task.get("id") or "")
    if (
        renderer.get("provider") == NATIVE_GOOGLE_TEXT_SAFE_PROVIDER
        and task_id != "cover"
    ):
        asset_id = "hero" if task_id == "hero" else task_id.removeprefix("infographic-")
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("render_text_safe_visual.py")),
                str(cwd),
                asset_id,
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        output = cwd / "素材" / str(task.get("image") or "")
        success = completed.returncode == 0 and output.is_file()
        return {
            "id": task_id,
            "provider": "local",
            "model": "Pillow-text-safe",
            "renderer": "deterministic-compositor",
            "outputPath": str(output),
            "success": success,
            "attempts": 1,
            "error": None if success else (completed.stderr or completed.stdout)[-1200:],
        }
    if not dimensions:
        return {
            "id": task_id,
            "success": False,
            "error": f"native Google 不支持 aspect={aspect}",
        }
    prompt_files = task.get("promptFiles") or []
    if not prompt_files:
        return {"id": task_id, "success": False, "error": "缺 promptFiles"}
    prompt = cwd / "素材" / str(prompt_files[0])
    output = cwd / "素材" / str(task.get("image") or "")
    model = str(renderer.get("model") or "").strip()
    if not model:
        return {
            "id": task_id,
            "success": False,
            "error": "sansheng-google renderer 必须显式配置 model",
        }
    width, height = dimensions
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("gen_img.py")),
            str(prompt),
            str(output),
            model,
            str(width),
            str(height),
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    combined = "\n".join(
        value.strip()
        for value in (completed.stdout or "", completed.stderr or "")
        if value.strip()
    )
    used_match = re.search(r"\(model=([^)]+)\)", combined)
    used_model = used_match.group(1).strip() if used_match else model
    success = completed.returncode == 0 and output.is_file()
    return {
        "id": task_id,
        "provider": "google",
        "model": used_model,
        "renderer": "gen_img",
        "outputPath": str(output),
        "success": success,
        "attempts": 1,
        "error": None if success else (combined[-1200:] or f"exit={completed.returncode}"),
    }


def _render_native_google(
    cwd: Path,
    tasks: list[dict[str, Any]],
    renderer: dict[str, Any],
    jobs: int,
) -> dict[str, Any]:
    """Run bounded native Google tasks concurrently and return batch-shaped results."""
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(jobs or 1), len(tasks)))) as pool:
        futures = {
            pool.submit(_run_native_google_task, cwd, task, renderer): str(task["id"])
            for task in tasks
        }
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive process boundary
                results.append(
                    {"id": task_id, "success": False, "error": str(exc)}
                )
    return {
        "returncode": 0 if all(item.get("success") for item in results) else 1,
        "results": results,
    }


def render_visuals(
    cwd: Path,
    *,
    renderer_command: list[str] | None = None,
    renderer_revision: str = "",
    native_google_renderer: Callable[
        [Path, list[dict[str, Any]], dict[str, Any], int], dict[str, Any]
    ] = _render_native_google,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Render all compiled tasks and record immutable, truthful provenance."""
    cwd = cwd.resolve()
    batch, errors = _load_batch(cwd)
    if errors or batch is None:
        return None, errors
    policy, policy_errors = _load_policy(cwd)
    if policy_errors:
        return None, policy_errors

    command = renderer_command
    revision = renderer_revision
    uses_baoyu = any(
        renderer.get("provider") not in NATIVE_PROVIDERS for renderer in policy
    )
    if uses_baoyu:
        if command is None:
            command, revision, resolve_errors = resolve_renderer_command()
            if resolve_errors or command is None:
                return None, resolve_errors
        probe = probe_renderer(command)
        if not probe["ok"]:
            return None, [probe["error"]]
    if not revision:
        native_script = Path(__file__).with_name("gen_img.py")
        revision = (
            f"gen_img.py-sha256:{_sha256(native_script)}"
            if not uses_baoyu
            else "configured-command"
        )

    material = cwd / "素材"
    tasks_by_id = {str(task["id"]): task for task in batch["tasks"]}
    pending = list(tasks_by_id)
    successes: dict[str, dict[str, Any]] = {}
    attempt_reports: list[dict[str, Any]] = []
    last_errors: dict[str, str] = {}

    for attempt_number, renderer in enumerate(policy, start=1):
        attempt_tasks = []
        for task_id in pending:
            original = tasks_by_id[task_id]
            rendered = dict(original)
            rendered.update(
                {
                    key: value
                    for key, value in {
                        "provider": renderer["provider"],
                        "model": renderer["model"],
                        "quality": renderer["quality"],
                        "imageSize": renderer["imageSize"],
                    }.items()
                    if value is not None
                }
            )
            attempt_tasks.append(rendered)
        attempt_batch = {
            "tasks": attempt_tasks,
            "jobs": batch.get("jobs") or 4,
        }
        attempt_path = material / f".render-attempt-{attempt_number:02d}.json"
        attempt_path.write_text(
            json.dumps(attempt_batch, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if renderer.get("provider") in NATIVE_PROVIDERS:
            native_report = native_google_renderer(
                cwd,
                attempt_tasks,
                renderer,
                int(attempt_batch["jobs"]),
            )
            returncode = int(native_report.get("returncode") or 0)
            results = native_report.get("results") or []
        else:
            assert command is not None
            completed = subprocess.run(
                [
                    *command,
                    "--batchfile",
                    str(attempt_path),
                    "--jobs",
                    str(attempt_batch["jobs"]),
                    "--json",
                ],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                check=False,
            )
            returncode = completed.returncode
            payload = _parse_json_output(completed.stdout)
            results = payload.get("results", []) if payload else []
        by_id = {
            str(result.get("id")): result
            for result in results
            if isinstance(result, dict) and result.get("id")
        }
        next_pending = []
        for task_id in pending:
            result = by_id.get(task_id)
            if result and result.get("success"):
                successes[task_id] = {
                    **result,
                    "policy_id": renderer["id"],
                    "attempt_id": attempt_number,
                }
            else:
                next_pending.append(task_id)
                last_errors[task_id] = (
                    str(result.get("error"))
                    if result
                    else f"renderer 无结构化结果（exit={returncode}）"
                )
        attempt_reports.append(
            {
                "attempt_id": attempt_number,
                "policy_id": renderer["id"],
                "task_ids": pending,
                "returncode": returncode,
                "succeeded": sorted(set(pending).difference(next_pending)),
                "failed": sorted(next_pending),
            }
        )
        pending = next_pending
        if not pending:
            break

    if pending:
        errors = [
            f"{task_id} 所有已配置 renderer 均失败：{last_errors.get(task_id, '未知错误')}"
            for task_id in pending
        ]
        return None, errors

    records: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for task in batch["tasks"]:
        task_id = str(task["id"])
        result = successes[task_id]
        output = material / str(task["image"])
        prompt = material / str(task["promptFiles"][0])
        if not output.is_file():
            return None, [f"renderer 报告成功但输出不存在：{output.relative_to(cwd)}"]
        if not prompt.is_file():
            return None, [f"canonical prompt 不存在：{prompt.relative_to(cwd)}"]
        output_rel = output.relative_to(cwd).as_posix()
        prompt_rel = prompt.relative_to(cwd).as_posix()
        prompt_meta = _prompt_meta(prompt)
        actual_renderer = str(result.get("renderer") or "baoyu-image-gen")
        record = {
            "schema_version": 3,
            "record_id": f"render-{task_id}-{_sha256(output)[:12]}",
            "timestamp": _now(),
            "stage": _stage(task_id),
            "producer": VISUAL_PRODUCER,
            "tool": VISUAL_PRODUCER,
            "renderer": actual_renderer,
            "renderer_revision": revision,
            "provider": result.get("provider") or "",
            "model": result.get("model") or "",
            "attempt_id": result["attempt_id"],
            "policy_id": result["policy_id"],
            "output": output_rel,
            "output_sha256": _sha256(output),
            "prompt": prompt_rel,
            "prompt_sha256": _sha256(prompt),
            "aspect_ratio": task["ar"],
            "style": str(prompt_meta.get("style") or ""),
            "visual_profile": str(prompt_meta.get("visual_profile") or ""),
            "visual_profile_sha256": str(
                prompt_meta.get("visual_profile_sha256") or ""
            ),
            "cmd": (
                "gen_img.py <canonical-prompt> <output> <model> <width> <height>"
                if actual_renderer == "gen_img"
                else "baoyu-image-gen --batchfile <sealed-attempt> --json"
            ),
        }
        records.append(record)
        images.append(
            {
                "path": output_rel,
                "aspect": task["ar"],
                "bytes": output.stat().st_size,
                "producer": VISUAL_PRODUCER,
                "renderer": actual_renderer,
                "style": str(prompt_meta.get("style") or ""),
            }
        )

    with (cwd / ".gen-log.jsonl").open("a", encoding="utf-8") as fp:
        for record in records:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    infographic_images = [
        image for task, image in zip(batch["tasks"], images) if _stage(str(task["id"])) == "infographic"
    ]
    final_set = {
        "schema_version": 2,
        "producer": VISUAL_PRODUCER,
        "images": infographic_images,
    }
    infographic_dir = material / "infographic"
    infographic_dir.mkdir(parents=True, exist_ok=True)
    (infographic_dir / "final-set.json").write_text(
        json.dumps(final_set, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    renderers_used = sorted({record["renderer"] for record in records})
    receipt = {
        "schema_version": 1,
        "status": "done",
        "producer": VISUAL_PRODUCER,
        "renderer": renderers_used[0] if len(renderers_used) == 1 else "mixed",
        "renderer_revision": revision,
        "batch_sha256": _sha256(material / "render-batch.json"),
        "attempts": attempt_reports,
        "assets": records,
        "created_at": _now(),
    }
    (material / "render-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt, []


def main() -> None:
    receipt, errors = render_visuals(Path.cwd())
    if errors:
        print("❌ 图片渲染失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(
        f"✅ 已渲染 {len(receipt['assets'])} 张图；"
        f"renderer={receipt['renderer']} revision={receipt['renderer_revision'][:12]}"
    )


if __name__ == "__main__":
    main()
