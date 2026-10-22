"""Validate host-attested edits without presenting them as fresh canonical generation."""
from __future__ import annotations

import hashlib
from pathlib import Path


def verify(submitted: dict, base_dir: Path) -> dict[str, Path]:
    steps = submitted.get("refinements")
    if steps is None:
        if "base_output" in submitted:
            raise ValueError("宿主返修缺实际编辑链")
        return {}
    if not isinstance(steps, list) or not steps:
        raise ValueError("宿主返修须为非空的实际编辑链")
    if not submitted.get("base_tool_output"):
        raise ValueError("宿主返修缺原始生成的工具输出")
    files = {str(Path(__file__).resolve()): Path(__file__).resolve()}

    def image(record):
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("宿主返修缺实际图像记录")
        if not Path(record["path"]).is_absolute():
            raise ValueError("宿主返修图像须记录绝对路径，以便跨快照重验")
        p = (base_dir / record["path"]).resolve()
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != record.get("sha256"):
            raise ValueError("宿主返修图像缺失或字节已改变")
        from PIL import Image
        with Image.open(p) as im:
            if im.format != "PNG":
                raise ValueError("宿主返修须保留原始 PNG")
            im.verify()
        files[str(p)] = p
        return p

    previous = image(submitted.get("base_output"))
    for step in steps:
        call = step.get("call", {})
        if (step.get("backend") != "image_gen.imagegen" or step.get("invocation_status") != "succeeded"
                or not step.get("tool_output") or not str(call.get("prompt", "")).strip()
                or call.get("referenced_image_paths") != [str(previous)]):
            raise ValueError("宿主返修必须记录实际调用，并引用上一张实际输出")
        previous = image(step.get("output"))
    if previous != image(submitted.get("output")):
        raise ValueError("宿主返修最终输出不是实际编辑链末图")
    return files
