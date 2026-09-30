"""Independent final-candidate QA for the explicit Stylebook article route."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, _peer, _immutable, digest, generation_requests, selected, sha
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, _peer, _immutable, digest, generation_requests, selected, sha


DELIVERY_CHECKS = [
    "Every planned text line is legible and clear of image outlines, arrows, icons and other text; no clipping or collisions.",
    "Every visible software logo or brand mark is explicitly requested in the content brief; no unrequested brand marks.",
]


def production_inputs(cwd: Path, production_path: Path) -> tuple[dict, dict, dict]:
    """Validate a production snapshot without regenerating or repairing it."""
    cwd = Path(cwd).resolve()
    production_path = Path(production_path).resolve()
    record = json.loads(production_path.read_text())
    if not selected(record) or record.get("producer") != PRODUCER or record.get("status") != "produced_pending_qa":
        raise ValueError("只接受正式制作入口的待验收候选")
    identity = {key: value for key, value in record.items() if key not in ("production_id", "files")}
    if digest(identity) != record.get("production_id"):
        raise ValueError("制作凭证已改变")
    expected_dir = cwd / "素材/stylebook-final" / record["request_id"] / record["id"] / record["production_id"]
    if production_path != expected_dir / "production.json":
        raise ValueError("制作凭证不在本篇不可变候选目录")
    raw_receipt = cwd / record["raw_receipt"]
    if sha(raw_receipt) != record["raw_receipt_sha256"]:
        raise ValueError("原始回收凭证已改变")
    raw = json.loads(raw_receipt.read_text())
    try:
        from .stylebook_reuse import validate_raw
    except ImportError:
        from stylebook_reuse import validate_raw
    origin_files = validate_raw(cwd, raw_receipt)
    host_path = cwd / raw["host_request_path"]
    host = json.loads(host_path.read_text())
    pending, errors = generation_requests(cwd, only={item["id"] for item in host["requests"]})
    if errors:
        raise ValueError("；".join(errors))
    if {k: v for k, v in pending.items() if k != "path"} != host or record["request_id"] != pending["request_id"]:
        raise ValueError("最终候选对应的制作请求已失效")
    batch_path = cwd / "素材/render-batch.json"
    batch = json.loads(batch_path.read_text())
    task = next(item for item in batch["tasks"] if item["id"] == record["id"])
    if digest(task) != record["task_digest"]:
        raise ValueError("最终候选与当前完整任务不一致")
    dependencies = record["dependencies_sha256"]
    manifest = task["manifest"]
    if "text_layout" in record:
        try:
            from . import stylebook_layout
        except ImportError:
            import stylebook_layout
        layout_path = (cwd / record["text_layout"]["path"]).resolve()
        layout = json.loads(layout_path.read_text())
        expected_path = cwd / "素材/stylebook-layouts" / f"{digest(layout)}.json"
        if (layout_path != expected_path or sha(layout_path) != record["text_layout"]["sha256"]
                or record.get("production_method") != "refit_generated_raw_lettering"
                or str(layout_path) not in dependencies
                or str(Path(stylebook_layout.__file__).resolve()) not in dependencies):
            raise ValueError("排字调整缺确切布局及实际制作方法绑定")
        manifest = stylebook_layout.apply_layout(manifest, layout)
    if manifest != record["manifest"]:
        raise ValueError("最终候选文字或内容与当前任务及排字调整不一致")
    task = {**task, "manifest": manifest}
    try:
        from . import stylebook_source
    except ImportError:
        import stylebook_source
    source = stylebook_source.current_source(cwd, batch, json.loads((cwd / "visual-plan.json").read_text()))
    required = [source, Path(stylebook_source.__file__).resolve(), cwd / "visual-plan.json", batch_path, raw_receipt,
                cwd / raw["raw_path"], host_path]
    if not isinstance(dependencies, dict) or any(str(path.resolve()) not in dependencies for path in required):
        raise ValueError("制作凭证缺少原文、计划、原始输出或请求依赖")
    if any(sha(Path(path)) != value for path, value in dependencies.items()):
        raise ValueError("制作输入、字体或方法文件已改变")
    files = {"production": production_path, **{f"input:{path}": Path(path) for path in dependencies}}
    files.update({f"origin:{path}": target for path, target in origin_files.items()})
    if set(record["files"]) != set(record["outputs"]) or "main" not in record["files"]:
        raise ValueError("最终候选输出清单缺项")
    for key, path in record["files"].items():
        target = (cwd / path).resolve()
        if target.parent != expected_dir or sha(target) != record["outputs"][key]["sha256"]:
            raise ValueError("最终候选图片路径或字节已改变")
        files[f"output:{key}"] = target
    return record, task, files


def review_candidate(cwd: Path, production_path: Path) -> tuple[dict | None, list[str]]:
    """Invoke an independent reviewer and retain both passing and failing QA."""
    cwd = Path(cwd).resolve()
    try:
        record, task, files = production_inputs(cwd, production_path)
        root, _ = _peer()
        contracts = importlib.import_module("stylebook.contract")
        qa = importlib.import_module("stylebook.qa")
        reviewer = importlib.import_module("stylebook.qa.reviewer")
        binding = importlib.import_module("stylebook.qa.binding")
        data = importlib.import_module("stylebook.data")
        exporter = importlib.import_module("stylebook.export")
        manifest = task["manifest"]
        contract = contracts.load(manifest["style"])
        pinned = f"{contract['code']}@r{contract['revision']}"
        if manifest["style"] != pinned:
            raise ValueError("最终候选样式修订与实际合同不同")
        files["contract"] = Path(contract["_path"])
        contract = {**contract, **qa.content_expectations(manifest["content"])}
        contract["qa"] = copy.deepcopy(contract["qa"])
        contract["qa"]["must_see"] += DELIVERY_CHECKS
        # Some styles override checks by text mode. Apply delivery checks to
        # every active branch without changing the published style contract.
        for override in contract["qa"].get("mode_overrides", {}).values():
            override["must_see"] += DELIVERY_CHECKS
        spec = manifest.get("text", {})
        expected = [item["text"] for item in spec.get("items", []) if item.get("text")]
        mode = spec.get("mode", "native" if expected else "none")
        fmt = manifest["format"]
        format_def = data.formats()[fmt]
        image = files["output:main"]
        previews = image.parent / "qa-previews"
        if format_def.get("safe_zone", {}).get("center_square"):
            previews.mkdir(exist_ok=True)
            square = exporter.center_square_preview(image, previews / "square.png")
            files["square"] = square
            contract["_square_crop_expectation"] = str(square)
        px = format_def.get("thumbnail_px")
        if px:
            from PIL import Image
            previews.mkdir(exist_ok=True)
            thumb = previews / f"thumbnail-{int(px)}.png"
            with Image.open(image) as im:
                im.convert("RGB").resize((int(px), int(px)), Image.Resampling.LANCZOS).save(thumb)
            files["thumbnail"] = thumb
            contract["_thumbnail_expectation"] = str(thumb)
        for module in (qa, reviewer, binding, contracts, data, exporter):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(root):
                raise ValueError("验收模块与选定画风手册本体不同")
            files[f"qa-code:{path}"] = path
        files["adapter"] = Path(__file__).resolve()
        backend = reviewer.source()
        values = {"production_id": record["production_id"], "contract": contract,
                  "expected_text": expected, "mode": mode, "format": fmt, "backend": backend,
                  "review_mode": "independent_call"}
        snapshot = binding.snapshot("image", files=files, values=values)
        review = reviewer.review(image, contract, expected, mode)
        if not str(review.get("_reviewer", "")).strip():
            raise ValueError("独立复核缺少实际模型标识")
        verdict = qa.judge(image, contract, review, expected, mode, fmt, manifest)
        binding.verify(snapshot, kind="image", files=files, values=values)
        production_inputs(cwd, production_path)
        report = {"schema_version": 2, "workflow": WORKFLOW, "producer": PRODUCER,
                  "status": "qa_passed" if verdict.passed else "qa_failed", "passed": verdict.passed,
                  "production_id": record["production_id"], "id": record["id"],
                  "production_path": str(Path(production_path).resolve().relative_to(cwd)),
                  "binding": snapshot, "binding_paths": {key: str(path) for key, path in files.items()},
                  "binding_values": values, "review_backend": backend, "actual_reviewer": review["_reviewer"],
                  "verdict": verdict.to_dict()}
        destination = image.parent / "qa-reports" / f"{digest(report)}.json"
        _immutable(destination, report)
        return {**report, "report_path": str(destination)}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, RuntimeError) as exc:
        return None, [f"画风手册独立验收失败：{exc}"]


def verify_candidate_review(cwd: Path, report_path: Path, *, require_passed: bool = True) -> dict:
    """Consumer check: a prior green report cannot survive changed inputs."""
    cwd = Path(cwd).resolve()
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text())
    if not selected(report) or report.get("producer") != PRODUCER:
        raise ValueError("不是画风手册正式候选验收报告")
    identity = {key: value for key, value in report.items() if key != "report_path"}
    record, task, expected_files = production_inputs(cwd, cwd / report["production_path"])
    expected_parent = (cwd / record["files"]["main"]).parent / "qa-reports"
    if report_path.parent != expected_parent or report_path.stem != digest(identity):
        raise ValueError("验收报告已改变或不属于本张最终候选")
    if report["production_id"] != record["production_id"]:
        raise ValueError("验收报告未绑定本张制作快照")
    if report.get("id") != record["id"] or report.get("actual_reviewer") != report.get("verdict", {}).get("review", {}).get("_reviewer"):
        raise ValueError("验收报告图片身份或实际复核模型不一致")
    if report.get("status") != ("qa_passed" if report.get("passed") is True else "qa_failed"):
        raise ValueError("验收状态与结论不一致")
    root, _ = _peer()
    reviewer = importlib.import_module("stylebook.qa.reviewer")
    binding = importlib.import_module("stylebook.qa.binding")
    qa = importlib.import_module("stylebook.qa")
    contracts = importlib.import_module("stylebook.contract")
    data = importlib.import_module("stylebook.data")
    exporter = importlib.import_module("stylebook.export")
    if report.get("review_backend") not in reviewer.INDEPENDENT_SOURCES or report["binding_values"].get("review_mode") != "independent_call":
        raise ValueError("不能用手工、预览或来源未知的报告代替独立验收")
    manifest = task["manifest"]
    contract = contracts.load(manifest["style"])
    expected_files["contract"] = Path(contract["_path"])
    contract = {**contract, **qa.content_expectations(manifest["content"])}
    contract["qa"] = copy.deepcopy(contract["qa"])
    contract["qa"]["must_see"] += DELIVERY_CHECKS
    for override in contract["qa"].get("mode_overrides", {}).values():
        override["must_see"] += DELIVERY_CHECKS
    spec = manifest.get("text", {})
    expected = [item["text"] for item in spec.get("items", []) if item.get("text")]
    mode, fmt = spec.get("mode", "native" if expected else "none"), manifest["format"]
    format_def = data.formats()[fmt]
    image = expected_files["output:main"]
    if format_def.get("safe_zone", {}).get("center_square"):
        path = image.parent / "qa-previews/square.png"
        expected_files["square"] = path
        contract["_square_crop_expectation"] = str(path)
    if format_def.get("thumbnail_px"):
        path = image.parent / "qa-previews" / f"thumbnail-{int(format_def['thumbnail_px'])}.png"
        expected_files["thumbnail"] = path
        contract["_thumbnail_expectation"] = str(path)
    for module in (qa, reviewer, binding, contracts, data, exporter):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root):
            raise ValueError("验收模块本体变化")
        expected_files[f"qa-code:{path}"] = path
    expected_files["adapter"] = Path(__file__).resolve()
    expected_values = {"production_id": record["production_id"], "contract": contract,
                       "expected_text": expected, "mode": mode, "format": fmt,
                       "backend": report["review_backend"], "review_mode": "independent_call"}
    if report["binding_paths"] != {key: str(path) for key, path in expected_files.items()} or report["binding_values"] != expected_values:
        raise ValueError("验收报告缺少实际依赖或当前判断条件不一致")
    binding.verify(report["binding"], kind="image",
                   files=expected_files, values=expected_values)
    verdict = qa.judge(image, contract, report["verdict"]["review"], expected, mode, fmt, manifest)
    if verdict.to_dict() != report["verdict"] or verdict.passed != report.get("passed"):
        raise ValueError("验收结论与原始独立看图判断不一致")
    if require_passed and (report.get("passed") is not True or report.get("status") != "qa_passed"):
        raise ValueError("最终候选独立验收未通过")
    return report
