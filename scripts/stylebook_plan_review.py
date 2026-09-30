"""Full-article editorial review, including a separately judged cover brief."""
from __future__ import annotations

import copy
import importlib
import json
import os
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, _peer, _immutable, digest, generation_requests, selected
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, _peer, _immutable, digest, generation_requests, selected


def context(cwd: Path, backend: str) -> tuple[dict, dict, dict]:
    if backend not in ("ark_agent_plan", "claude_cli"):
        raise ValueError("全文复核须使用独立调用后端")
    cwd = Path(cwd).resolve()
    pending, errors = generation_requests(cwd)
    if errors:
        raise ValueError("；".join(errors))
    root, modules = _peer()
    plan = json.loads((cwd / "visual-plan.json").read_text())
    try:
        from . import stylebook_source
    except ImportError:
        import stylebook_source
    batch = json.loads((cwd / "素材/render-batch.json").read_text())
    article = stylebook_source.current_source(cwd, batch, plan)
    adapted = copy.deepcopy(plan["article_plan"])
    adapted["source"]["path"] = str(article.relative_to(cwd))
    errors, _ = modules["plan"].check(adapted, base_path=cwd)
    if errors:
        raise ValueError("；".join(errors))
    quote = plan["cover"].get("source", {}).get("quote")
    if not isinstance(quote, str) or not quote.strip() or quote not in article.read_text():
        raise ValueError("封面须给出可在全文中核对的依据原句")
    adapted["cover_brief"] = plan["cover"]
    files = {"article": article, "visual_plan": cwd / "visual-plan.json",
             "adapter": Path(__file__).resolve()}
    for name in ("stylebook.plan", "stylebook.qa.plan_review", "stylebook.qa.reviewer", "stylebook.qa.binding"):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root):
            raise ValueError("全文复核模块与选定画风手册不同")
        files[name] = path
    for path in batch["method_source"]["files"]:
        files[f"method:{path}"] = (root / path).resolve()
    for task in batch["tasks"]:
        for path in task["reference_sha256"]:
            files[f"reference:{path}"] = Path(path)
    values = {"review_plan": adapted, "request_id": pending["request_id"],
              "backend": backend, "review_mode": "independent_full_article_and_cover"}
    return adapted, files, values


def qualified(review: dict, plan: dict) -> bool:
    peer = importlib.import_module("stylebook.qa.plan_review")
    return (peer._complete(review, plan) and not review["missed_positions"]
            and all(peer._item_passes(item) for item in review["items"])
            and all(review["cover_review"].get(key) is True for key in
                    ("fidelity_ok", "theme_ok", "no_unrequested_claims")))


def review_article_plan(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        backend = os.environ.get("STYLEBOOK_PLAN_REVIEW_BACKEND") or os.environ.get("STYLEBOOK_QA_BACKEND", "claude_cli")
        plan, files, values = context(cwd, backend)
        peer = importlib.import_module("stylebook.qa.plan_review")
        binding = importlib.import_module("stylebook.qa.binding")
        snapshot = binding.snapshot("article-plan", files=files, values=values)
        review = peer.review(plan, files["article"])
        if not str(review.get("_reviewer", "")).strip():
            raise ValueError("全文独立复核缺实际模型标识")
        passed = qualified(review, plan)
        binding.verify(snapshot, kind="article-plan", files=files, values=values)
        # Also verify the actual source, methods and compile request after review.
        _, current_files, current_values = context(cwd, backend)
        if current_files != files or current_values != values:
            raise ValueError("全文复核期间制作输入改变")
        record = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                  "status": "plan_review_passed" if passed else "plan_review_failed", "passed": passed,
                  "request_id": values["request_id"], "backend": backend,
                  "actual_reviewer": review["_reviewer"], "review": review,
                  "binding": snapshot, "binding_paths": {key: str(path) for key, path in files.items()},
                  "binding_values": values, "existing_visual_assessment": "editorial_text_context_only"}
        destination = cwd / "素材/stylebook-plan-reviews" / f"{digest(record)}.json"
        _immutable(destination, record)
        return {**record, "report_path": str(destination)}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        return None, [f"画风手册全文计划复核失败：{exc}"]


def verify_plan_review(cwd: Path, report_path: Path, *, require_passed: bool = True) -> dict:
    cwd = Path(cwd).resolve()
    report_path = Path(report_path).resolve()
    record = json.loads(report_path.read_text())
    if not selected(record) or record.get("producer") != PRODUCER:
        raise ValueError("须使用正式全文计划复核报告")
    if report_path.parent != cwd / "素材/stylebook-plan-reviews" or report_path.stem != digest(record):
        raise ValueError("全文复核报告已改变或不属于本篇")
    plan, files, values = context(cwd, record["backend"])
    if values != record["binding_values"] or {key: str(path) for key, path in files.items()} != record["binding_paths"]:
        raise ValueError("全文复核未绑定当前完整计划和制作请求")
    binding = importlib.import_module("stylebook.qa.binding")
    binding.verify(record["binding"], kind="article-plan", files=files, values=values)
    passed = qualified(record["review"], plan)
    if record.get("passed") is not passed or record.get("actual_reviewer") != record["review"].get("_reviewer"):
        raise ValueError("全文复核结论与原始判断不一致")
    if record.get("status") != ("plan_review_passed" if passed else "plan_review_failed"):
        raise ValueError("全文复核状态与结论不一致")
    if require_passed and not passed:
        raise ValueError("全文计划或封面复核未通过")
    return record
