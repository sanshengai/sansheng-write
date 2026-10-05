"""Versioned article visual contract for the explicitly selected Stylebook route.

Compilation creates immutable requests, never a successful rendering receipt.
The existing Baoyu contract remains owned by visual_workflow.py.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WORKFLOW = "stylebook-v1"
PRODUCER = "sansheng-stylebook"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def selected(plan: dict) -> bool:
    return isinstance(plan, dict) and type(plan.get("schema_version")) is int and plan["schema_version"] == 2 and plan.get("workflow") == WORKFLOW


def selected_at(cwd: Path) -> bool:
    try:
        value = json.loads((Path(cwd) / "visual-plan.json").read_text())
        return isinstance(value, dict) and (value.get("schema_version") == 2 or value.get("workflow") == WORKFLOW)
    except (OSError, ValueError):
        return False


def validate(plan: dict) -> list[str]:
    errors = []
    if not selected(plan):
        return ["画风手册视觉合同必须为 schema_version=2, workflow=stylebook-v1"]
    article_plan = plan.get("article_plan")
    if not isinstance(article_plan, dict):
        return ["缺 article_plan 对象"]
    if article_plan.get("version") != 3 or article_plan.get("scene") != "wxillus":
        errors.append("article_plan 必须为 v3 wxillus 全文计划")
    def obj(value):
        return value if isinstance(value, dict) else {}
    source = plan.get("source")
    if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and
            re.fullmatch(r"[a-f0-9]{64}", source[k]) for k in ("sha256", "author_content_sha256")):
        errors.append("source 须绑定确切原文字节及 author_content_sha256")
    elif obj(article_plan.get("source")).get("sha256") != source["sha256"]:
        errors.append("source 与 article_plan 原文摘要不一致")
    group = plan.get("group")
    if not isinstance(group, dict) or not re.fullmatch(r"[CS]\d{2}@r[1-9]\d*", str(group.get("style", ""))):
        errors.append("group.style 必须锁定样式修订，例如 C31@r4")
    else:
        if obj(article_plan.get("style")).get("code") != group["style"]:
            errors.append("article_plan 样式与整组锁不一致")
        if article_plan.get("palette") != group.get("palette"):
            errors.append("article_plan 色调与整组锁不一致")
    renderer = plan.get("renderer")
    if not isinstance(renderer, dict) or renderer.get("backend") not in ("host-imagegen", "stylebook-service"):
        errors.append("renderer.backend 只接受 host-imagegen 或 stylebook-service")
    cover = plan.get("cover")
    if not isinstance(cover, dict) or cover.get("format") != "wechat-cover-head":
        errors.append("cover 必须是 wechat-cover-head 编译清单")
    elif isinstance(group, dict):
        if cover.get("own_style") is True:
            # 封面单独选画风（如 C90 深色系列封面）：只允许画风手册「封面」用途里的画风，编译时对照本体核实
            if not re.fullmatch(r"[CS]\d{2}@r[1-9]\d*", str(cover.get("style", ""))):
                errors.append("封面单独选画风时 cover.style 也必须锁定样式修订，例如 C90@r1")
        elif "own_style" in cover:
            errors.append("cover.own_style 只接受 true；不单独选画风时省略")
        elif cover.get("style") != group.get("style") or cover.get("palette") != group.get("palette"):
            errors.append("封面样式/色调与整组锁不一致")
        if obj(cover.get("source")).get("sha256") != obj(source).get("sha256"):
            errors.append("封面原文摘要与文章不一致")
    items = article_plan.get("items")
    if not isinstance(items, list):
        errors.append("article_plan.items 必须是列表，可为零张正文图")
    else:
        ids = set()
        for item in items:
            image_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(image_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", image_id) or image_id == "cover" or image_id in ids:
                errors.append("正文图片 ID 必须唯一、路径安全，且不能占用 cover")
            ids.add(image_id if isinstance(image_id, str) else "")
    return errors


def _peer():
    try:
        from .stylebook_preview import _skill_root
    except ImportError:
        from stylebook_preview import _skill_root
    root = _skill_root(os.environ.get("SANSHENG_STYLEBOOK_ROOT"))
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    modules = {name: importlib.import_module(f"stylebook.{name}") for name in ("plan", "compile")}
    if any(not Path(module.__file__).resolve().is_relative_to(root) for module in modules.values()):
        raise ValueError("画风手册已加载模块与选定本体不同")
    return root, modules


def _immutable(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"历史编译请求不一致，拒绝覆盖：{path}")
        return
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def compile_plan(cwd: Path, plan: dict) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    errors = validate(plan)
    if errors:
        return None, errors
    try:
        try:
            from .assemble_release import author_content_sha256
            from .stylebook_preview import _method_anchor
        except ImportError:
            from assemble_release import author_content_sha256
            from stylebook_preview import _method_anchor
        article = cwd / "定稿.md"
        if not article.is_file() or not article.read_bytes():
            return None, ["缺非空 定稿.md"]
        if sha(article) != plan["source"]["sha256"] or author_content_sha256(article.read_text()) != plan["source"]["author_content_sha256"]:
            return None, ["定稿.md 已变化，新视觉计划失效"]
        source_path = Path(plan["article_plan"]["source"]["path"])
        if (cwd / source_path).resolve() != article:
            return None, ["article_plan.source.path 必须指向当前 定稿.md"]
        try:
            from . import stylebook_source
        except ImportError:
            import stylebook_source
        frozen = stylebook_source.freeze_source(cwd, plan["source"])
        root, modules = _peer()
        problems, warnings = modules["plan"].check(plan["article_plan"], base_path=cwd)
        if problems:
            return None, problems
        cover = copy.deepcopy(plan["cover"])
        if cover.pop("own_style", False):
            data = importlib.import_module("stylebook.data")
            if Path(data.__file__).resolve().parent != Path(modules["plan"].__file__).resolve().parent:
                raise ValueError("画风手册已加载模块与选定本体不同")
            code = cover["style"].split("@")[0]
            if code not in data.styles_for_use("封面"):
                return None, [f"封面单独选画风只允许画风手册「封面」用途里的画风，{code} 不在其中"]
        manifests = [("cover", cover)]
        for manifest in modules["plan"].manifests(plan["article_plan"]):
            manifests.append((manifest.pop("_id"), manifest))
        tasks = []
        for image_id, manifest in manifests:
            for ref in manifest.get("references", []):
                ref["path"] = str((cwd / ref["path"]).resolve())
            result = modules["compile"].compile_manifest(manifest).to_dict()
            references = {}
            for ref in result["references"]:
                path = Path(ref["path"])
                if not path.is_file() or not path.read_bytes():
                    raise ValueError(f"参考图缺失或为空：{path}")
                references[str(path)] = sha(path)
            tasks.append({"id": image_id, "manifest": manifest, "compiled": result,
                          "actual_prompt_sha256": hashlib.sha256(result["prompt"].encode()).hexdigest(),
                          "reference_sha256": references,
                          "output": "素材/cover.png" if image_id == "cover" else f"素材/infographic-{image_id}.png"})
        styles = {manifest["style"].split("@")[0] for _, manifest in manifests}
        anchor = _method_anchor(root, set())
        contracts = importlib.import_module("stylebook.contract")
        for style in sorted(styles):
            contract_path = Path(contracts.load(style)["_path"]).resolve()
            if contract_path.is_relative_to(root):
                key = str(contract_path.relative_to(root))
            else:
                key = str(contract_path)
            anchor["files"][key] = sha(contract_path)
        # Bind actual production code used in generation/export/QA as well as the editorial method.
        for rel in ["scripts/stylebook/overlay.py", "scripts/stylebook/export.py", "scripts/stylebook/qa/__init__.py",
                    "scripts/stylebook/qa/binding.py", "scripts/stylebook/qa/reviewer.py"]:
            anchor["files"][rel] = sha(root / rel)
        anchor["digest"] = digest(anchor["files"])
        identity = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                    "status": "compiled_pending_render", "renderer": plan["renderer"],
                    "source": plan["source"], "source_snapshot": str(frozen.relative_to(cwd)),
                    "source_methods": stylebook_source.methods(),
                    "plan_digest": digest(plan), "method_source": anchor,
                    "adapter_sha256": sha(Path(__file__)), "warnings": warnings, "tasks": tasks}
        request_id = digest(identity)
        dest = cwd / "素材" / "stylebook-requests" / f"{request_id}.json"
        _immutable(dest, identity)
        active = {**identity, "request_id": request_id, "request_path": str(dest.relative_to(cwd))}
        (cwd / "素材" / "render-batch.json").write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n")
        (cwd / "素材" / "visual-compile-receipt.json").write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n")
        return {"producer": PRODUCER, "prompt_count": len(tasks), "status": identity["status"],
                "request_id": request_id, "request_path": str(dest)}, []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [f"画风手册正式任务编译失败：{exc}"]


def generation_requests(cwd: Path, only: set[str] | None = None) -> tuple[dict | None, list[str]]:
    """Prepare exact host calls, while keeping rendering explicitly pending."""
    cwd = Path(cwd).resolve()
    try:
        plan = json.loads((cwd / "visual-plan.json").read_text())
        errors = validate(plan)
        if errors:
            return None, errors
        batch = json.loads((cwd / "素材/render-batch.json").read_text())
        identity = {key: value for key, value in batch.items() if key not in ("request_id", "request_path")}
        if digest(identity) != batch.get("request_id") or json.loads((cwd / batch["request_path"]).read_text()) != identity:
            raise ValueError("编译请求已改变，须重新 compile-visuals")
        if batch.get("producer") != PRODUCER or not selected(batch) or batch.get("plan_digest") != digest(plan):
            raise ValueError("编译请求不属于当前画风手册计划")
        try:
            from .stylebook_source import current_source
        except ImportError:
            from stylebook_source import current_source
        current_source(cwd, batch, plan)
        anchor = batch["method_source"]
        root = Path(anchor["root"])
        if anchor["digest"] != digest(anchor["files"]) or any(sha(root / rel) != value for rel, value in anchor["files"].items()):
            raise ValueError("画风手册方法或合同已改变，编译请求失效")
        if batch["adapter_sha256"] != sha(Path(__file__)):
            raise ValueError("write 画风适配器已改变，须重新编译")
        backend = plan["renderer"]["backend"]
        ids = {item["id"] for item in batch["tasks"]}
        if only is not None and (not only or not only <= ids):
            raise ValueError("--only 必须选择本组实际图片 ID")
        requests = []
        for task in batch["tasks"]:
            if only is not None and task["id"] not in only:
                continue
            prompt = task["compiled"]["prompt"]
            if hashlib.sha256(prompt.encode()).hexdigest() != task["actual_prompt_sha256"]:
                raise ValueError(f"{task['id']} 提示词已改变")
            if any(sha(Path(ref)) != value for ref, value in task["reference_sha256"].items()):
                raise ValueError(f"{task['id']} 参考图已改变")
            call = {"prompt": prompt, "transparent_background": False}
            refs = [ref["path"] for ref in task["compiled"]["references"]]
            if refs:
                call["referenced_image_paths"] = refs
            request = {"id": task["id"], "call": call, "task_digest": digest(task),
                       "raw_destination": f"素材/stylebook-raw/{batch['request_id']}/{task['id']}.png"}
            if backend == "stylebook-service":  # 服务后端要按编译时的画幅出图；宿主后端的工具自己决定
                request["generation"] = {"aspect": task["compiled"]["aspect"], "size": list(task["compiled"]["size"])}
            requests.append(request)
        receipt = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                   "status": "pending_service" if backend == "stylebook-service" else "pending_host",
                   "request_id": batch["request_id"],
                   "backend": "stylebook-service" if backend == "stylebook-service" else "image_gen.imagegen",
                   "actual_model": None, "actual_cost": None, "requests": requests}
        dest = cwd / "素材/stylebook-requests" / f"{'service' if backend == 'stylebook-service' else 'host'}-{digest(receipt)}.json"
        _immutable(dest, receipt)
        return {**receipt, "path": str(dest)}, []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [f"画风手册实际生成请求失败：{exc}"]


def collect_host_result(cwd: Path, result_path: Path) -> tuple[dict | None, list[str]]:
    """Collect a host-attested raw result; this is neither final QA nor a seal.

    The tool runs in the calling agent, outside this CLI's process. A submitted
    tool response is an attestation, not cryptographic proof of its invocation.
    """
    cwd = Path(cwd).resolve()
    try:
        from PIL import Image
        result_path = Path(result_path).resolve()
        submitted_bytes = result_path.read_bytes()
        submitted = json.loads(submitted_bytes)
        if not isinstance(submitted, dict) or type(submitted.get("schema_version")) is not int or submitted["schema_version"] != 1:
            raise ValueError("宿主结果须为 schema_version=1 对象")
        if submitted.get("backend") not in ("image_gen.imagegen", "stylebook-service") or submitted.get("invocation_status") != "succeeded":
            raise ValueError("缺实际生图成功回执；pending/失败不能回收")
        if not isinstance(submitted.get("tool_output"), str) or not submitted["tool_output"].strip():
            raise ValueError("缺宿主工具实际返回的 output_hint/输出说明")
        host_path = (cwd / submitted["host_request_path"]).resolve()
        if host_path.parent != (cwd / "素材/stylebook-requests").resolve():
            raise ValueError("宿主请求必须是本篇保存的不可变请求")
        host = json.loads(host_path.read_text())
        ids = {item["id"] for item in host["requests"]}
        expected, errors = generation_requests(cwd, only=ids)
        if errors:
            return None, errors
        expected = {key: value for key, value in expected.items() if key != "path"}
        if host != expected or submitted.get("host_request_digest") != digest(expected):
            raise ValueError("宿主请求已改变或与当前编译输入不一致")
        if submitted.get("backend") != expected["backend"]:
            raise ValueError("回执的后端与请求的后端不一致")
        image_id = submitted["id"]
        task = next((item for item in expected["requests"] if item["id"] == image_id), None)
        if task is None or submitted.get("request_id") != expected["request_id"] or submitted.get("call") != task["call"]:
            raise ValueError("宿主实际调用参数/图片 ID 与完整请求不一致")
        output = submitted.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("path"), str):
            raise ValueError("缺实际输出文件")
        source = (result_path.parent / output["path"]).resolve()
        raw = source.read_bytes()
        raw_sha = hashlib.sha256(raw).hexdigest()
        if not raw or output.get("sha256") != raw_sha:
            raise ValueError("实际输出缺失/为空/摘要不一致")
        with Image.open(source) as picture:
            if picture.format != "PNG":
                raise ValueError("宿主原始输出必须是 PNG，不得将成品转换后冒充原始输出")
            dimensions = list(picture.size)
            picture.verify()
        # Retain every candidate, even when the same task is regenerated.
        parent = cwd / Path(task["raw_destination"]).parent
        destination = parent / f"{image_id}-{raw_sha}.png"
        parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError("已有原始输出损坏，拒绝覆盖")
        else:
            with destination.open("xb") as stream:
                stream.write(raw)
        if source.read_bytes() != raw or result_path.read_bytes() != submitted_bytes:
            raise ValueError("回收期间宿主结果或源图片已改变")
        identity = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                    "status": "raw_collected_pending_production", "request_id": expected["request_id"],
                    "id": image_id, "backend": expected["backend"], "actual_model": None, "actual_cost": None,
                    "source_strength": "pipeline_invoked" if expected["backend"] == "stylebook-service" else "host_attested",
                    "independent_invocation_verified": expected["backend"] == "stylebook-service",
                    "host_request_path": str(host_path.relative_to(cwd)), "host_request_digest": digest(expected),
                    "task_digest": task["task_digest"], "actual_call_digest": digest(task["call"]),
                    "submitted_result": submitted, "submitted_result_sha256": hashlib.sha256(submitted_bytes).hexdigest(),
                    "raw_path": str(destination.relative_to(cwd)), "raw_sha256": raw_sha, "dimensions": dimensions}
        receipt = cwd / "素材/stylebook-results" / expected["request_id"] / image_id / f"{digest(identity)}.json"
        # Do not let a timestamp turn an identical re-import into a new result.
        _immutable(receipt, identity)
        return {**identity, "receipt_path": str(receipt),
                "collected_at": datetime.now(timezone.utc).isoformat()}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f"画风手册宿主结果回收失败：{exc}"]


def run_service(cwd: Path, only: set[str] | None = None, *, timeout: int = 1800, jobs: int = 4,
                runner=None) -> tuple[dict | None, list[str]]:
    """无人值守出图：对每份请求调用画风手册的 raw-generate（默认走 Codex 订阅额度），再按同一套回收规则收进来。

    流水线自己发起调用，所以回执标 pipeline_invoked；它仍不是最终成品、QA 或 seal。
    runner 仅供测试注入（签名同 subprocess.run 的最小子集）。
    """
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    cwd = Path(cwd).resolve()
    requests, errors = generation_requests(cwd, only)
    if errors:
        return None, errors
    if requests["backend"] != "stylebook-service":
        return None, ["renderer.backend 不是 stylebook-service；host-imagegen 须由宿主自己调用内置生图工具"]
    try:
        root, _ = _peer()
    except (ValueError, OSError, ImportError) as exc:
        return None, [f"找不到画风手册本体：{exc}"]
    host_path = Path(requests["path"])
    expected = {k: v for k, v in requests.items() if k != "path"}
    out_dir = cwd / "素材/stylebook-service-results" / expected["request_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run = runner or subprocess.run

    def one(request: dict) -> tuple[dict | None, list[str]]:
        image_id = request["id"]
        prompt_file = out_dir / f"{image_id}-{stamp}.prompt.txt"
        prompt_file.write_text(request["call"]["prompt"], encoding="utf-8")
        raw = out_dir / f"{image_id}-{stamp}.png"
        gen = request["generation"]
        cmd = [sys.executable, str(root / "scripts/sb.py"), "raw-generate", "--prompt-file", str(prompt_file),
               "--aspect", gen["aspect"], "--size", f"{gen['size'][0]}x{gen['size'][1]}", "-o", str(raw), "--tag", f"write:{image_id}"]
        for ref in request["call"].get("referenced_image_paths", []):
            cmd += ["--ref", ref]
        try:
            done = run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, [f"{image_id} 出图调用失败：{exc}"]
        lines = [x for x in (done.stdout or "").splitlines() if x.strip().startswith("{")]
        meta = json.loads(lines[-1]) if lines else {}
        if done.returncode != 0 or not meta.get("ok") or not raw.is_file():
            return None, [f"{image_id} 出图失败：{meta.get('kind', done.returncode)} {meta.get('error', (done.stderr or '')[-160:])}"]
        submitted = {"schema_version": 1, "backend": "stylebook-service", "invocation_status": "succeeded",
                     "host_request_path": str(host_path.relative_to(cwd)), "host_request_digest": digest(expected),
                     "request_id": expected["request_id"], "id": image_id, "call": request["call"],
                     "tool_output": json.dumps({k: meta.get(k) for k in ("provider", "model", "seconds", "attempts", "tokens")}, ensure_ascii=False),
                     "output": {"path": raw.name, "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}}
        result_json = out_dir / f"{image_id}-{stamp}.result.json"
        result_json.write_text(json.dumps(submitted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return collect_host_result(cwd, result_json)

    with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(expected["requests"])))) as pool:
        outcomes = list(pool.map(one, expected["requests"]))
    problems = [e for _, errs in outcomes for e in errs]
    collected = [r for r, _ in outcomes if r]
    if problems:
        return ({"status": "partial", "collected": collected} if collected else None), problems
    return {"status": "raw_collected_pending_production", "request_id": expected["request_id"], "collected": collected}, []


def produce_candidate(cwd: Path, raw_receipt_path: Path) -> tuple[dict | None, list[str]]:
    """Make a versioned final candidate from a current raw receipt, pending QA."""
    cwd = Path(cwd).resolve()
    try:
        raw_receipt_path = Path(raw_receipt_path).resolve()
        receipt = json.loads(raw_receipt_path.read_text())
        if not selected(receipt) or receipt.get("producer") != PRODUCER or receipt.get("status") != "raw_collected_pending_production":
            raise ValueError("须选择画风手册实际回收的原始候选凭证")
        expected_parent = cwd / "素材/stylebook-results" / receipt["request_id"] / receipt["id"]
        if raw_receipt_path.parent != expected_parent or raw_receipt_path.stem != digest(receipt):
            raise ValueError("原始候选凭证已改变或不在本篇不可变结果目录")
        host_path = cwd / receipt["host_request_path"]
        host = json.loads(host_path.read_text())
        pending, errors = generation_requests(cwd, only={item["id"] for item in host["requests"]})
        if errors:
            return None, errors
        current_host = {key: value for key, value in pending.items() if key != "path"}
        if host != current_host or digest(host) != receipt["host_request_digest"] or pending["request_id"] != receipt["request_id"]:
            raise ValueError("原始候选对应的计划/请求已失效，不能制作")
        batch = json.loads((cwd / "素材/render-batch.json").read_text())
        task = next(item for item in batch["tasks"] if item["id"] == receipt["id"])
        host_task = next(item for item in host["requests"] if item["id"] == receipt["id"])
        if digest(task) != receipt["task_digest"] or digest(host_task["call"]) != receipt["actual_call_digest"]:
            raise ValueError("原始候选未绑定当前完整制作任务")
        raw = (cwd / receipt["raw_path"]).resolve()
        if not raw.is_relative_to((cwd / "素材/stylebook-raw" / receipt["request_id"]).resolve()) or sha(raw) != receipt["raw_sha256"]:
            raise ValueError("原始图片路径或字节已改变")
        root, _ = _peer()
        export = importlib.import_module("stylebook.export")
        overlay_module = importlib.import_module("stylebook.overlay")
        textspec = importlib.import_module("stylebook.textspec")
        formats = importlib.import_module("stylebook.data").formats()
        manifest = task["manifest"]
        spec = manifest.get("text", {})
        mode = spec.get("mode", formats[manifest["format"]].get("text", {}).get("default", "none"))
        overlay = spec if mode in ("overlay", "hybrid") else None
        dependencies = {str(raw): sha(raw), str(raw_receipt_path): sha(raw_receipt_path),
                        str(host_path): sha(host_path), str(Path(__file__).resolve()): sha(Path(__file__))}
        try:
            from . import stylebook_source
        except ImportError:
            import stylebook_source
        plan = json.loads((cwd / "visual-plan.json").read_text())
        source = stylebook_source.current_source(cwd, batch, plan)
        for path in (source, Path(stylebook_source.__file__).resolve(), cwd / "visual-plan.json", cwd / "素材/render-batch.json"):
            dependencies[str(path)] = sha(path)
        dependencies.update({str((root / path).resolve()): value for path, value in batch["method_source"]["files"].items()})
        # Bind the actual font files selected by the same resolver used to draw.
        fonts = []
        if overlay:
            for item in textspec.overlay_items(overlay):
                family, weight = item.get("font_family", "sans"), item.get("weight", "regular")
                font = overlay_module._font(weight, item.get("font_px", 48), family)
                path = Path(font.path).resolve()
                dependencies[str(path)] = sha(path)
                fonts.append({"family": family, "weight": weight, "path": str(path), "index": font.index})
            for layer in overlay.get("image_layers", []):
                path = (cwd / layer["path"]).resolve()
                if not path.is_relative_to(cwd):
                    raise ValueError("图层路径越出文章目录")
                dependencies[str(path)] = sha(path)
        for module in (export, overlay_module, textspec):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(root):
                raise ValueError("实际制作模块与选定画风手册不同")
            dependencies[str(path)] = sha(path)
        import PIL
        with tempfile.TemporaryDirectory(prefix="stylebook-production-", dir=cwd / "素材") as scratch:
            produced = export.export(raw, manifest["format"], Path(scratch) / "final.png", overlay=overlay, overlay_root=cwd)
            if any(sha(Path(path)) != value for path, value in dependencies.items()):
                raise ValueError("最终制作过程中输入或制作方法改变")
            try:
                stylebook_source.current_source(cwd, batch, plan)
            except ValueError as exc:
                raise ValueError(f"最终制作过程中原文或装配内容改变：{exc}") from exc
            outputs = {"main": {"sha256": sha(produced.main)}}
            outputs.update({f"extra-{n}": {"sha256": sha(path)} for n, path in enumerate(produced.extras)})
            identity = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                        "status": "produced_pending_qa", "request_id": batch["request_id"], "id": receipt["id"],
                        "raw_receipt": str(raw_receipt_path.relative_to(cwd)), "raw_receipt_sha256": sha(raw_receipt_path),
                        "task_digest": digest(task), "manifest": manifest, "dependencies_sha256": dependencies,
                        "fonts": fonts, "pillow_version": PIL.__version__, "warnings": produced.warnings, "outputs": outputs}
            production_id = digest(identity)
            dest = cwd / "素材/stylebook-final" / batch["request_id"] / receipt["id"] / production_id
            dest.mkdir(parents=True, exist_ok=True)
            files = [("main", produced.main)] + [(f"extra-{n}", path) for n, path in enumerate(produced.extras)]
            for key, path in files:
                target = dest / path.name
                payload = path.read_bytes()
                if target.exists():
                    if target.read_bytes() != payload:
                        raise ValueError("已保存最终候选被改变，拒绝覆盖")
                else:
                    with target.open("xb") as stream:
                        stream.write(payload)
            record = {**identity, "production_id": production_id,
                      "files": {key: str((dest / path.name).relative_to(cwd)) for key, path in files}}
            _immutable(dest / "production.json", record)
        return {**record, "receipt_path": str(dest / "production.json")}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as exc:
        return None, [f"画风手册最终候选制作失败：{exc}"]
