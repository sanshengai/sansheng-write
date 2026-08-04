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
import uuid
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

# 🔴 并发数默认 2，不是 4。
# 图像模型的配额按「每分钟请求数」算，一批通常 6 张（封面 + Hero + 4 张信息图），
# 4 并发会在几秒内把一分钟的额度打满，症状是「总有两三张 429，重跑又换成另外几张」。
# gen_img.py 自己是串行设计（注释里写着「多组按输入顺序串行，避免并发打到 429」），
# 但这里每张图起一个独立进程，那份保护绕不过来——所以要在这一层限流。
# 配合 gen_img 的 429 退避重试，2 并发实测能把一批 6 张一次跑完。
# 需要更快可在 render-batch.json 里显式写 jobs，但先确认账号配额撑得住。
_DEFAULT_JOBS = 2

NATIVE_GOOGLE_PROVIDER = "sansheng-google"
NATIVE_GOOGLE_TEXT_SAFE_PROVIDER = "sansheng-google-text-safe"
NATIVE_TEMPLATE_SAFE_PROVIDER = "sansheng-template-safe"
# 文字必须由本次模型原生生成在图内；本地/Pillow 模板不再是自动或手动 fallback。
NATIVE_PROVIDERS = {NATIVE_GOOGLE_PROVIDER}
BLOCKED_LOCAL_PROVIDERS = {
    NATIVE_GOOGLE_TEXT_SAFE_PROVIDER,
    NATIVE_TEMPLATE_SAFE_PROVIDER,
}
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
    direct_candidates = [
        home / ".codex/skills/baoyu-image-gen",
        home / ".claude/skills/baoyu-image-gen",
        home / ".gemini/config/skills/baoyu-image-gen",
        home / "Cowork/skills/baoyu-image-gen",
    ]
    patterns = [
        ".codex/plugins/cache/baoyu-skills/**/skills/baoyu-image-gen",
        ".claude/plugins/cache/baoyu-skills/**/skills/baoyu-image-gen",
        ".agents/skills/baoyu-image-gen",
    ]
    candidates: list[Path] = list(direct_candidates)
    for pattern in patterns:
        candidates.extend(home.glob(pattern))
    resolved: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not (path / "scripts/main.ts").is_file():
            continue
        real = path.resolve()
        if real in seen:
            continue
        seen.add(real)
        resolved.append(real)
    return resolved


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

    allowed = {"id", "provider", "model", "quality", "imageSize", "override_baoyu_reason"}
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
        provider = item.get("provider") or None
        if provider in BLOCKED_LOCAL_PROVIDERS:
            errors.append(
                f"renderers[{index}]={provider} 会用本地模板绘制图中文字；"
                "当前合同要求由生成模型原生出字，请改为 sansheng-google 或外部生成式 renderer"
            )
            continue
        # 🔴 2026-08-02：不带 provider 才走 baoyu-image-gen（本文件 _load_policy 的 else 分支）。
        # 任何显式 provider 都会绕开 Baoyu 视觉链，属于对既定契约的例外，必须写明理由。
        # 实证：照模板复制一份 policy（模板曾预置 sansheng-google）就会静默换掉渲染器，
        # 并把封面从 1584×672 降到 1024×436，而所有发布门都照常放行。
        if provider and not str(item.get("override_baoyu_reason") or "").strip():
            errors.append(
                f"renderers[{index}] 显式配置 provider={provider}，会绕开 baoyu-image-gen 视觉链；"
                "若确需如此，请在该项补 override_baoyu_reason 写明理由（会记入发布证据），"
                "否则请删除 provider 字段回到 Baoyu 默认链路"
            )
            continue
        normalized.append(
            {
                "id": renderer_id,
                "provider": provider,
                "model": item.get("model") or None,
                "quality": item.get("quality") or "2k",
                "imageSize": item.get("imageSize") or "1K",
                "override_baoyu_reason": str(
                    item.get("override_baoyu_reason") or ""
                ).strip()
                or None,
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
    provider = renderer.get("provider")
    use_local_template = provider == NATIVE_TEMPLATE_SAFE_PROVIDER or (
        provider == NATIVE_GOOGLE_TEXT_SAFE_PROVIDER and task_id != "cover"
    )
    if use_local_template:
        asset_id = (
            task_id
            if task_id in {"cover", "hero"}
            else task_id.removeprefix("infographic-")
        )
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
            "model": "Pillow-reviewed-template",
            "renderer": "deterministic-template-compositor",
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


def _candidate_manifest_path(cwd: Path) -> Path:
    return cwd / "素材" / "candidates" / "candidate-set.json"


def _render_visual_candidates(
    cwd: Path,
    *,
    candidate_count: int,
    only: set[str] | None,
    renderer_command: list[str] | None,
    renderer_revision: str,
    native_google_renderer: Callable[[Path, list[dict[str, Any]], dict[str, Any], int], dict[str, Any]],
    google_route_preflight: Callable[[str], str] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Generate several truthful candidates, but never silently choose one as final."""
    if candidate_count < 2 or candidate_count > 4:
        return None, ["--candidates 只允许 2 到 4；避免无界消耗图片配额"]
    batch, errors = _load_batch(cwd)
    if errors or batch is None:
        return None, errors
    material = cwd / "素材"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = material / "candidates" / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = _candidate_manifest_path(cwd)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    batch_sha256 = _sha256(material / "render-batch.json")
    initial_manifest = {
        "schema_version": 1,
        "status": "rendering",
        "created_at": _now(),
        "candidate_count": 0,
        "requested_candidate_count": candidate_count,
        "run_id": run_id,
        "run_dir": run_dir.relative_to(cwd).as_posix(),
        "batch_sha256": batch_sha256,
        "plan_digest": batch.get("plan_digest") or "",
        "tasks": {},
    }
    manifest_path.write_text(
        json.dumps(initial_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    candidates: dict[str, list[dict[str, Any]]] = {}
    last_receipt: dict[str, Any] | None = None
    for number in range(1, candidate_count + 1):
        receipt, run_errors = render_visuals(
            cwd,
            only=only,
            renderer_command=renderer_command,
            renderer_revision=renderer_revision,
            native_google_renderer=native_google_renderer,
            google_route_preflight=google_route_preflight,
            candidate_count=1,
        )
        if run_errors or receipt is None:
            # Keep already-rendered candidates selectable after a later
            # candidate hits a transient quota/rate-limit error.  Losing the
            # manifest here strands valid images and tempts callers to bypass
            # explicit selection; the command still returns non-zero below.
            manifest = {
                **initial_manifest,
                "status": "incomplete",
                "candidate_count": number - 1,
                "tasks": candidates,
                "partial_failure": run_errors or ["候选图渲染未返回凭证"],
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return None, run_errors or ["候选图渲染未返回凭证"]
        last_receipt = receipt
        for record in receipt["assets"]:
            task_id = Path(str(record["output"])).stem
            source = cwd / Path(str(record["output"]))
            destination = run_dir / f"{task_id}-candidate-{number:02d}.png"
            shutil.copy2(source, destination)
            stored = dict(record)
            stored.update(
                {
                    "candidate": number,
                    "path": destination.relative_to(cwd).as_posix(),
                    "sha256": _sha256(destination),
                }
            )
            candidates.setdefault(task_id, []).append(stored)
    manifest = {
        "schema_version": 1,
        "status": "selection-required",
        "created_at": _now(),
        "candidate_count": candidate_count,
        "requested_candidate_count": candidate_count,
        "run_id": run_id,
        "run_dir": run_dir.relative_to(cwd).as_posix(),
        "batch_sha256": batch_sha256,
        "plan_digest": batch.get("plan_digest") or "",
        "tasks": candidates,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **(last_receipt or {}),
        "status": "selection-required",
        "candidate_manifest": manifest_path.relative_to(cwd).as_posix(),
    }, []


def select_visual_candidates(cwd: Path, selections: dict[str, int]) -> tuple[dict[str, Any] | None, list[str]]:
    """Promote explicitly selected generated candidates to final asset paths."""
    cwd = cwd.resolve()
    path = _candidate_manifest_path(cwd)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["缺素材/candidates/candidate-set.json；先用 render-visuals --candidates 生成候选"]
    except json.JSONDecodeError as exc:
        return None, [f"candidate-set.json 解析失败：{exc}"]
    tasks = manifest.get("tasks") if isinstance(manifest, dict) else None
    if not isinstance(tasks, dict) or not tasks:
        return None, ["candidate-set.json 缺 tasks"]
    batch_path = cwd / "素材" / "render-batch.json"
    if (
        not batch_path.is_file()
        or manifest.get("batch_sha256") != _sha256(batch_path)
    ):
        return None, ["candidate-set.json 未绑定当前 render-batch.json"]
    requested_count = int(manifest.get("requested_candidate_count") or manifest.get("candidate_count") or 0)
    actual_count = int(manifest.get("candidate_count") or 0)
    if requested_count and actual_count < requested_count:
        return None, [
            "候选生成不完整，禁止把单一残留候选标成已选择："
            f"请求 {requested_count}，实际 {actual_count}"
        ]
    incomplete = [
        task_id for task_id, choices in tasks.items()
        if not isinstance(choices, list) or len(choices) < max(2, requested_count)
    ]
    if incomplete:
        return None, [f"候选不足，禁止选择：{sorted(incomplete)}"]
    if set(selections) != set(tasks):
        return None, [
            "必须为每张图显式选择一个候选："
            f"需要 {sorted(tasks)}，收到 {sorted(selections)}"
        ]
    selected_records: list[dict[str, Any]] = []
    for task_id, choices in tasks.items():
        chosen = next(
            (
                item for item in choices
                if isinstance(item, dict) and int(item.get("candidate") or 0) == selections[task_id]
            ),
            None,
        )
        if not chosen:
            return None, [f"{task_id} 没有候选 {selections[task_id]}"]
        source = cwd / Path(str(chosen.get("path") or ""))
        target = cwd / Path(str(chosen.get("output") or ""))
        if not source.is_file() or not str(chosen.get("output") or ""):
            return None, [f"{task_id} 候选文件或目标路径缺失"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if _sha256(target) != str(chosen.get("sha256") or ""):
            return None, [f"{task_id} 候选复制后摘要不一致"]
        record = dict(chosen)
        record.update(
            {
                "record_id": f"selected-{task_id}-{_sha256(target)[:12]}",
                "timestamp": _now(),
                "output": target.relative_to(cwd).as_posix(),
                "output_sha256": _sha256(target),
                "selected_candidate": selections[task_id],
                "cmd": "select-visuals <task>=<candidate>",
            }
        )
        record.pop("path", None)
        record.pop("sha256", None)
        selected_records.append(record)
    with (cwd / ".gen-log.jsonl").open("a", encoding="utf-8") as fp:
        for record in selected_records:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    infographic_images = [
        {
            "path": record["output"],
            "aspect": str(record.get("aspect_ratio") or ""),
            "bytes": (cwd / Path(record["output"])).stat().st_size,
            "producer": VISUAL_PRODUCER,
            "renderer": str(record.get("renderer") or ""),
            "style": str(record.get("style") or ""),
        }
        for record in selected_records
        if _stage(Path(record["output"]).stem) == "infographic"
    ]
    info_dir = cwd / "素材" / "infographic"
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / "final-set.json").write_text(
        json.dumps({"schema_version": 2, "producer": VISUAL_PRODUCER, "images": infographic_images}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["status"] = "selected"
    manifest["selected_at"] = _now()
    manifest["selections"] = selections
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "status": "done",
        "producer": VISUAL_PRODUCER,
        "renderer": "selected-generated-candidates",
        "assets": selected_records,
        "candidate_manifest": path.relative_to(cwd).as_posix(),
        "created_at": _now(),
    }
    (cwd / "素材" / "render-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt, []


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
    only: set[str] | None = None,
    renderer_command: list[str] | None = None,
    renderer_revision: str = "",
    native_google_renderer: Callable[
        [Path, list[dict[str, Any]], dict[str, Any], int], dict[str, Any]
    ] = _render_native_google,
    google_route_preflight: Callable[[str], str] | None = None,
    candidate_count: int = 1,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Render all compiled tasks and record immutable, truthful provenance."""
    cwd = cwd.resolve()
    if candidate_count > 1:
        return _render_visual_candidates(
            cwd,
            candidate_count=candidate_count,
            only=only,
            renderer_command=renderer_command,
            renderer_revision=renderer_revision,
            native_google_renderer=native_google_renderer,
            google_route_preflight=google_route_preflight,
        )
    batch, errors = _load_batch(cwd)
    if errors or batch is None:
        return None, errors
    policy, policy_errors = _load_policy(cwd)
    if policy_errors:
        return None, policy_errors

    # 404 的根因若是 Vertex 项目路由少了 /publishers/google，首张之前就必须停。
    # 这只校验本次真实 renderer 的 URL 合同，不发网络请求、不消耗图片配额。
    google_models = sorted(
        {
            str(renderer.get("model") or "").strip()
            for renderer in policy
            if renderer.get("provider") == NATIVE_GOOGLE_PROVIDER
        }
    )
    if google_models:
        if google_route_preflight is None:
            try:
                from gen_img import validate_google_route
            except ImportError:  # pragma: no cover - package execution fallback
                from scripts.gen_img import validate_google_route
            google_route_preflight = validate_google_route
        route_errors: list[str] = []
        for model in google_models:
            try:
                google_route_preflight(model)
            except SystemExit as exc:
                route_errors.append(str(exc))
            except Exception as exc:  # pragma: no cover - defensive boundary
                route_errors.append(str(exc))
        if route_errors:
            return None, [
                "Google/Vertex 图片端点预检失败（未发送任何出图请求）："
                + "；".join(route_errors)
            ]

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
        native_script = (
            Path(__file__).with_name("render_text_safe_visual.py")
            if not uses_baoyu
            and all(
                renderer.get("provider") == NATIVE_TEMPLATE_SAFE_PROVIDER
                for renderer in policy
            )
            else Path(__file__).with_name("gen_img.py")
        )
        revision = (
            f"{native_script.name}-sha256:{_sha256(native_script)}"
            if not uses_baoyu
            else "configured-command"
        )

    material = cwd / "素材"
    tasks_by_id = {str(task["id"]): task for task in batch["tasks"]}

    # 🔴 选渲：只重渲点名的几张，其余沿用磁盘上已有的图。
    # 为什么需要：生成式渲染是逐张掷骰子，一批 6 张常常 5 张满意、1 张中文糊了。
    # 没有选渲的话，为补那 1 张必须整批重跑，把已经满意的 5 张一起掷掉 ——
    # 实测为补一张连跑七轮，每轮都在毁掉上一轮的好结果。
    #
    # 证据不会因此被伪造：.gen-log.jsonl 按 output 路径追加、消费方取最新一条，
    # 所以没重渲的图**自动**沿用它自己那条真实记录（renderer/model/prompt 摘要全是
    # 当初真实生成时写下的）。这里只需保证 receipt 仍覆盖全部资产。
    # 若点名了不存在的 id，或某张没渲过又没有历史产物，一律硬失败，不静默略过。
    if only:
        unknown = sorted(set(only) - set(tasks_by_id))
        if unknown:
            return None, [f"--only 指定了不存在的任务 id：{unknown}；可选：{sorted(tasks_by_id)}"]
        reuse_ids = [tid for tid in tasks_by_id if tid not in only]
        missing_outputs = [
            tid for tid in reuse_ids if not (material / str(tasks_by_id[tid]["image"])).is_file()
        ]
        if missing_outputs:
            return None, [
                f"--only 会沿用未点名的资产，但这些还没有产物：{missing_outputs}；"
                "先跑一次完整 render-visuals，再用 --only 补渲个别图"
            ]
        pending = [tid for tid in tasks_by_id if tid in only]
    else:
        reuse_ids = []
        pending = list(tasks_by_id)

    successes: dict[str, dict[str, Any]] = {}
    written_records: dict[str, dict[str, Any]] = {}
    attempt_reports: list[dict[str, Any]] = []
    last_errors: dict[str, str] = {}

    def persist_success(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """A successful render is evidence even when another task later fails.

        Persist it immediately so a quota/error-interrupted batch can resume without
        regenerating already valid assets.
        """
        task = tasks_by_id[task_id]
        output = material / str(task["image"])
        prompt = material / str(task["promptFiles"][0])
        if not output.is_file():
            raise RuntimeError(f"renderer 报告成功但输出不存在：{output.relative_to(cwd)}")
        if not prompt.is_file():
            raise RuntimeError(f"canonical prompt 不存在：{prompt.relative_to(cwd)}")
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
            "producer_chain": list(task.get("producer_chain") or [VISUAL_PRODUCER]),
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
            # 🔴 2026-08-03 补：这两个字段 canonical prompt 的 frontmatter 里本来就有
            # （visual_workflow.py 的 _hero_prompt / _infographic_prompt 都会写），
            # 但渲染记录一直没落盘，导致 pipeline.py 的 Hero 校验
            # （要求 profile / sha256 / contract_owner / contract_revision 四项全等）
            # 永远拿不到后两项 → hero 恒报「gen-log 视觉配方未绑定」，且无法通过重渲自愈。
            # 数据源仍是 prompt frontmatter，不新增任何推断。
            "visual_contract_owner": str(
                prompt_meta.get("visual_contract_owner") or ""
            ),
            "visual_contract_revision": str(
                prompt_meta.get("visual_contract_revision") or ""
            ),
            "cmd": (
                "gen_img.py <canonical-prompt> <output> <model> <width> <height>"
                if actual_renderer == "gen_img"
                else (
                    "render_text_safe_visual.py <canonical-prompt> <output>"
                    if actual_renderer == "deterministic-template-compositor"
                    else "baoyu-image-gen --batchfile <sealed-attempt> --json"
                )
            ),
        }
        with (cwd / ".gen-log.jsonl").open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        written_records[task_id] = record
        return record

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
            "jobs": batch.get("jobs") or _DEFAULT_JOBS,
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
                success = {
                    **result,
                    "policy_id": renderer["id"],
                    "attempt_id": attempt_number,
                }
                successes[task_id] = success
                try:
                    persist_success(task_id, success)
                except RuntimeError as exc:
                    next_pending.append(task_id)
                    successes.pop(task_id, None)
                    last_errors[task_id] = str(exc)
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

    # 沿用的资产：从 .gen-log.jsonl 取该 output 最新那条真实记录，原样带进新 receipt。
    # 不重新编造 renderer/model/attempt —— 那些字段只有当初真正生成它的那一次说了算。
    reused_records: dict[str, dict[str, Any]] = {}
    if reuse_ids:
        log_path = cwd / ".gen-log.jsonl"
        by_output: dict[str, dict[str, Any]] = {}
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict) and entry.get("output"):
                    by_output[str(entry["output"])] = entry  # 后写的覆盖先写的 = 取最新
        for task_id in reuse_ids:
            task = tasks_by_id[task_id]
            output = material / str(task["image"])
            rel = output.relative_to(cwd).as_posix()
            prior = by_output.get(rel)
            if not prior:
                return None, [
                    f"{rel} 没有历史生成记录，无法沿用；先跑一次完整 render-visuals"
                ]
            if prior.get("output_sha256") != _sha256(output):
                return None, [
                    f"{rel} 的文件内容与历史记录对不上（可能被手工替换过）；"
                    "证据链不接受来历不明的图，请重渲该张"
                ]
            reused_records[task_id] = prior

    records: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for task in batch["tasks"]:
        task_id = str(task["id"])
        if task_id in reused_records:
            records.append(reused_records[task_id])
            reused_output = material / str(task["image"])
            images.append(
                {
                    "path": reused_output.relative_to(cwd).as_posix(),
                    "aspect": task["ar"],
                    "bytes": reused_output.stat().st_size,
                    "producer": VISUAL_PRODUCER,
                    "renderer": str(reused_records[task_id].get("renderer") or ""),
                    "style": str(reused_records[task_id].get("style") or ""),
                }
            )
            continue
        output = material / str(task["image"])
        prompt = material / str(task["promptFiles"][0])
        record = written_records[task_id]
        output_rel = output.relative_to(cwd).as_posix()
        prompt_meta = _prompt_meta(prompt)
        actual_renderer = str(record.get("renderer") or "baoyu-image-gen")
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
        "producer_chain": list(batch.get("producer_chain") or [VISUAL_PRODUCER]),
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
    candidate_manifest = _candidate_manifest_path(cwd)
    if candidate_manifest.is_file():
        candidate_manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "direct-render",
                    "created_at": _now(),
                    "batch_sha256": _sha256(material / "render-batch.json"),
                    "plan_digest": batch.get("plan_digest") or "",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
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
