"""Keep the calling publication's visual defaults when changing renderers."""
from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path

import yaml

try:
    from .profile_config import brand
except ImportError:
    from profile_config import brand


def check(cwd: Path, plan: dict, load_contract) -> dict:
    path = cwd / "article-meta.yaml"
    meta = yaml.safe_load(path.read_text()) if path.is_file() else {}
    if not isinstance(meta, dict):
        raise ValueError("article-meta.yaml 必须是对象")
    visual = brand().get("visual", {})
    policy = visual.get("stylebook", {})
    if not isinstance(policy, dict):
        raise ValueError("visual.stylebook 必须是对象")
    # These are declared publication contracts, not hints to the renderer.
    declarations = {"cover": meta.get("cover_style"), "body": meta.get("visual_profile")}
    selected = {"cover": plan["cover"]["style"], "body": plan["group"]["style"]}
    for role, code in selected.items():
        required = policy.get(role)
        if required is not None:
            if not isinstance(required, str) or not re.fullmatch(r"[CS]\d{2}@r[1-9]\d*", required):
                raise ValueError(f"visual.stylebook.{role} 必须锁定画风修订，不能留空")
            if code != required:
                raise ValueError(f"{role} 画风 {code} 违背 write 作者默认 {required}；切换出图工具不能改默认风格")
        declared = declarations[role]
        if declared in ("montage-evidence", "warm-light-clay"):
            contract = load_contract(code.split("@")[0])
            names = list(contract.get("aliases", [])) + [contract.get("source", {}).get("from", "")]
            if not any(re.search(r"(?<![\w-])" + re.escape(declared) + r"(?![\w-])", str(name)) for name in names):
                raise ValueError(f"{role} 声明 {declared}，实际却选择 {code}；须保留已声明视觉合同，不能只让新计划内部自洽")
    return {"defaults": policy, "declarations": declarations,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def verify_square_source(receipt_path: Path, master: Path, prompt: str) -> None:
    """Verify a host-attested original and up to two real, linked refinements."""
    receipt = json.loads(receipt_path.read_text())
    steps = receipt.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError("方形母版缺完整生成与返修链，最多两次返修")
    previous = None
    for n, step in enumerate(steps):
        call = step.get("call", {})
        output = step.get("output", {})
        path = Path(output.get("path", ""))
        if (step.get("backend") != "image_gen.imagegen" or step.get("invocation_status") != "succeeded"
                or not step.get("tool_output") or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != output.get("sha256")):
            raise ValueError("方形母版生成或返修来源无效")
        if n == 0 and (call.get("prompt") != prompt or call.get("referenced_image_paths")):
            raise ValueError("方形母版初始生成须完整使用当前编译词，且不使用参考图")
        if n and (not str(call.get("prompt", "")).strip()
                  or call.get("referenced_image_paths") != [str(previous)]):
            raise ValueError("方形母版返修必须沿用上一张实际输出")
        previous = path.resolve()
    if previous != master.resolve():
        raise ValueError("方形母版不是返修链的最后输出")
