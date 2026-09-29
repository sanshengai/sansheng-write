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
        if cover.get("style") != group.get("style") or cover.get("palette") != group.get("palette"):
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
        root, modules = _peer()
        problems, warnings = modules["plan"].check(plan["article_plan"], base_path=cwd)
        if problems:
            return None, problems
        manifests = [("cover", copy.deepcopy(plan["cover"]))]
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
                    "source": plan["source"], "plan_digest": digest(plan), "method_source": anchor,
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
        if sha(cwd / "定稿.md") != batch["source"]["sha256"]:
            raise ValueError("原文已改变，编译请求失效")
        anchor = batch["method_source"]
        root = Path(anchor["root"])
        if anchor["digest"] != digest(anchor["files"]) or any(sha(root / rel) != value for rel, value in anchor["files"].items()):
            raise ValueError("画风手册方法或合同已改变，编译请求失效")
        if batch["adapter_sha256"] != sha(Path(__file__)):
            raise ValueError("write 画风适配器已改变，须重新编译")
        if plan["renderer"]["backend"] != "host-imagegen":
            return None, ["stylebook-service 的正式生成适配尚未实现；不能自动换后端"]
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
            requests.append({"id": task["id"], "call": call, "task_digest": digest(task),
                             "raw_destination": f"素材/stylebook-raw/{batch['request_id']}/{task['id']}.png"})
        receipt = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                   "status": "pending_host", "request_id": batch["request_id"],
                   "backend": "image_gen.imagegen", "actual_model": None, "actual_cost": None,
                   "requests": requests}
        dest = cwd / "素材/stylebook-requests" / f"host-{digest(receipt)}.json"
        _immutable(dest, receipt)
        return {**receipt, "path": str(dest)}, []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [f"画风手册实际生成请求失败：{exc}"]
