"""Reuse an attested raw image without claiming another generator invocation."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable, generation_requests
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable, generation_requests


# 两条出图路线各自的请求形态与证明强度：宿主自报（host）只能是 host_attested；
# 画风库服务由本流水线直接调用（service），记为 pipeline_invoked。互不借用对方的字段。
BACKENDS = {
    "image_gen.imagegen": {"prefix": "host", "status": "pending_host",
                           "strength": "host_attested", "verified": False},
    "stylebook-service": {"prefix": "service", "status": "pending_service",
                          "strength": "pipeline_invoked", "verified": True},
}


def _within(cwd: Path, relative: str, parent: Path) -> Path:
    path = (cwd / relative).resolve()
    if not path.is_relative_to(parent.resolve()):
        raise ValueError("底图来源路径超出本篇保存目录")
    return path


def _snapshot(cwd: Path, path: Path, final: Path | None = None) -> tuple[dict, dict, dict, dict]:
    """Check saved historical bytes; old authoring methods need not be current.

    final：凭证尚在临时文件里、要落盘的目标路径；位置与摘要文件名按它核对（落盘前校验用）。
    """
    path = path.resolve()
    final = path if final is None else Path(final).resolve()
    raw = json.loads(path.read_text())
    if (raw.get("schema_version") != 2 or raw.get("workflow") != WORKFLOW
            or raw.get("producer") != PRODUCER or raw.get("status") != "raw_collected_pending_production"):
        raise ValueError("缺正式原始底图凭证")
    parent = cwd / "素材/stylebook-results" / raw["request_id"] / raw["id"]
    if final.parent != parent or final.stem != digest(raw):
        raise ValueError("原始底图凭证路径或摘要已改变")
    host_path = _within(cwd, raw["host_request_path"], cwd / "素材/stylebook-requests")
    host = json.loads(host_path.read_text())
    route = BACKENDS.get(host.get("backend"))
    if (route is None or host_path.name != f"{route['prefix']}-{digest(host)}.json"
            or raw["host_request_digest"] != digest(host)
            or host.get("request_id") != raw["request_id"] or host.get("status") != route["status"]
            or raw.get("backend") != host.get("backend")):
        raise ValueError("保存的宿主请求已改变")
    compiled_path = cwd / "素材/stylebook-requests" / f"{raw['request_id']}.json"
    compiled = json.loads(compiled_path.read_text())
    if digest(compiled) != raw["request_id"] or compiled.get("producer") != PRODUCER:
        raise ValueError("历史编译请求已改变")
    task = next((t for t in compiled["tasks"] if t["id"] == raw["id"]), None)
    host_task = next((t for t in host["requests"] if t["id"] == raw["id"]), None)
    if task is None or host_task is None:
        raise ValueError("历史底图没有对应的完整任务")
    call = {"prompt": task["compiled"]["prompt"], "transparent_background": False}
    refs = [r["path"] for r in task["compiled"]["references"]]
    if refs:
        call["referenced_image_paths"] = refs
    if (host_task["call"] != call or host_task["task_digest"] != digest(task)
            or raw["task_digest"] != digest(task) or raw["actual_call_digest"] != digest(call)):
        raise ValueError("底图未绑定保存的完整调用")
    if set(task["reference_sha256"]) != set(refs):
        raise ValueError("底图缺实际参考图字节记录")
    raw_path = _within(cwd, raw["raw_path"], cwd / "素材/stylebook-raw" / raw["request_id"])
    if sha(raw_path) != raw["raw_sha256"]:
        raise ValueError("保存的原始图片字节已改变")
    from PIL import Image
    with Image.open(raw_path) as picture:
        if picture.format != "PNG" or list(picture.size) != raw["dimensions"]:
            raise ValueError("保存的底图格式或尺寸不同")
        picture.verify()
    source = _within(cwd, compiled["source_snapshot"], cwd / "素材/stylebook-sources")
    if sha(source) != compiled["source"]["sha256"]:
        raise ValueError("历史原文快照已改变")
    files = {str(p): p for p in (path, host_path, compiled_path, raw_path, source)}
    return raw, task, host_task, files


def validate_raw(cwd: Path, path: Path, final: Path | None = None) -> dict[str, Path]:
    """Actual final QA consumer checks invocation or explicit reuse provenance."""
    cwd = Path(cwd).resolve()
    raw, task, host_task, files = _snapshot(cwd, Path(path), final)
    files[str(Path(__file__).resolve())] = Path(__file__).resolve()
    reuse = raw.get("reuse")
    origin = raw
    actual_task = host_task
    if reuse is not None:
        if (not isinstance(reuse, dict) or reuse.get("new_invocation") is not False
                or raw.get("source_strength") != "host_attested_reused"
                or reuse.get("method_sha256") != sha(Path(__file__))):
            raise ValueError("复用须明确没有新调用并绑定实际复用方法")
        origin_path = _within(cwd, reuse["origin_receipt"], cwd / "素材/stylebook-results")
        if sha(origin_path) != reuse["origin_receipt_sha256"]:
            raise ValueError("复用的原始来源凭证已改变")
        origin, old_task, old_host_task, old_files = _snapshot(cwd, origin_path)
        if "origin_backend" in reuse and reuse["origin_backend"] != origin.get("backend"):
            raise ValueError("复用记录写的原始出图路线与实际来源凭证不同")
        actual_task = old_host_task
        if "reuse" in origin:
            raise ValueError("复用必须直接指向实际宿主回收来源")
        if (host_task["call"] != old_host_task["call"]
                or task["reference_sha256"] != old_task["reference_sha256"]
                or raw["raw_sha256"] != origin["raw_sha256"]
                or raw["submitted_result"] != origin["submitted_result"]
                or raw["submitted_result_sha256"] != origin["submitted_result_sha256"]):
            raise ValueError("复用的完整调用、参考图或原始回执不同")
        files.update(old_files)
        files[str(Path(__file__).resolve())] = Path(__file__).resolve()
    submitted = origin["submitted_result"]
    route = BACKENDS.get(origin.get("backend"))
    if (route is None or origin.get("source_strength") != route["strength"]
            or origin.get("independent_invocation_verified") is not route["verified"]
            or origin.get("actual_model") is not None or origin.get("actual_cost") is not None
            or submitted.get("schema_version") != 1 or submitted.get("backend") != origin.get("backend")
            or submitted.get("invocation_status") != "succeeded"
            or not isinstance(submitted.get("tool_output"), str) or not submitted["tool_output"].strip()
            or submitted.get("request_id") != origin["request_id"] or submitted.get("id") != origin["id"]
            or not isinstance(submitted.get("host_request_path"), str)
            or (cwd / submitted["host_request_path"]).resolve() != (cwd / origin["host_request_path"]).resolve()
            or submitted.get("host_request_digest") != origin["host_request_digest"]
            or submitted.get("call") != actual_task["call"]
            or submitted.get("output", {}).get("sha256") != origin["raw_sha256"]):
        raise ValueError("原始宿主回执与实际保存调用不一致")
    verified = False if reuse is not None else route["verified"]
    if (raw.get("independent_invocation_verified") is not verified
            or raw.get("actual_model") is not None or raw.get("actual_cost") is not None):
        raise ValueError("不能提高复用来源的证明强度或虚构模型费用")
    for ref, expected in task["reference_sha256"].items():
        if sha(Path(ref)) != expected:
            raise ValueError("原始调用的参考图字节已改变")
        files[ref] = Path(ref)
    return files


def reuse_raw(cwd: Path, origin_path: Path, image_id: str) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        origin_path = Path(origin_path).resolve()
        origin = json.loads(origin_path.read_text())
        if "reuse" in origin:
            raise ValueError("请选择实际宿主回收的原始凭证")
        before = {key: sha(value) for key, value in validate_raw(cwd, origin_path).items()}
        pending, errors = generation_requests(cwd, only={image_id})
        if errors:
            return None, errors
        host = {k: v for k, v in pending.items() if k != "path"}
        current = host["requests"][0]
        batch = json.loads((cwd / "素材/render-batch.json").read_text())
        new_task = next(t for t in batch["tasks"] if t["id"] == image_id)
        _, old_task, old_host_task, _ = _snapshot(cwd, origin_path)
        if (current["call"] != old_host_task["call"]
                or new_task["reference_sha256"] != old_task["reference_sha256"]):
            raise ValueError("当前提示词、调用或参考图字节不同，不能复用底图")
        source = cwd / origin["raw_path"]
        destination = cwd / "素材/stylebook-raw" / host["request_id"] / f"{image_id}-{origin['raw_sha256']}.png"
        payload = source.read_bytes()
        record = {**origin, "request_id": host["request_id"], "id": image_id,
                  "host_request_path": str(Path(pending["path"]).relative_to(cwd)), "host_request_digest": digest(host),
                  "task_digest": current["task_digest"], "actual_call_digest": digest(current["call"]),
                  "raw_path": str(destination.relative_to(cwd)), "source_strength": "host_attested_reused",
                  # 复用没有新调用：即使原始来源是服务路线（已核实调用），这条记录也不得继承该证明。
                  "independent_invocation_verified": False,
                  # backend 沿用原回执（请求核对需要）；真正的出图路线单独写在 origin_backend，避免被误读成「复用也走了服务」。
                  "reuse": {"new_invocation": False, "origin_receipt": str(origin_path.relative_to(cwd)),
                            "origin_receipt_sha256": sha(origin_path), "origin_backend": origin["backend"],
                            "method_sha256": sha(Path(__file__))}}
        path = cwd / "素材/stylebook-results" / host["request_id"] / image_id / f"{digest(record)}.json"
        if destination.exists() and destination.read_bytes() != payload:
            raise ValueError("复用目录已有底图损坏，拒绝覆盖")
        # 先校验后落盘：底图和回执先放成临时文件/本次新建文件，整条来源核对通过才改名生效，失败全部撤回，
        # 不在真实文章目录里留下不合格的回执。
        created_raw = False
        temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with destination.open("xb") as stream:
                        created_raw = True  # 只有真由本次创建的底图，失败时才由本次删除
                        stream.write(payload)
                except FileExistsError:  # 另一个进程刚写入同一张底图：内容一致就共用，绝不删它
                    if destination.read_bytes() != payload:
                        raise ValueError("复用目录已有底图损坏，拒绝覆盖")
            if path.exists():
                if json.loads(path.read_text()) != record:
                    raise ValueError(f"历史复用凭证不一致，拒绝覆盖：{path}")
                validate_raw(cwd, path)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                validate_raw(cwd, temp, final=path)
                if any(sha(Path(key)) != value for key, value in before.items()):
                    raise ValueError("复用期间历史来源已改变")
                checked, errors = generation_requests(cwd, only={image_id})
                if errors or checked != pending:
                    raise ValueError("复用期间当前请求已改变")
                os.replace(temp, path)
        except BaseException:
            if created_raw and destination.exists():
                destination.unlink()
            raise
        finally:
            if temp.exists():
                temp.unlink()
        return {**record, "receipt_path": str(path)}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as exc:
        return None, [f"画风库底图复用失败：{exc}"]
