#!/usr/bin/env python3
"""独立视觉复核适配器 · Claude Code CLI 后端。

`pipeline.py visual-qa` 按固定契约调用本脚本：

    python visual_qa_claude.py --request <_visual-qa-request.json> --output <candidate.json>

与 `visual_qa_codex.py` 完全同一套验收合同（提示词、schema、逐项判据、信道自检全部
复用那边的实现），只把「看图的独立进程」从 codex 换成 `claude -p`（Claude Code 无头模式）。
Claude 自己就能看图，不能生图；看图这道闸不需要等 Codex 额度（2026-09-19 作者拍板：
「Claude Code 自己看图就好」，起因是 Codex 当天额度用尽把发布链卡了两小时）。

独立性：
- 每张图各起一个全新的 `claude -p` 进程，不带本会话上下文；只给它图片路径和合同提示词。
- 复核模型默认 `claude-opus-5`，与生图模型（`codex-image-gen` / gpt-image 系）不同族；
  `visual_qa.py::validate_qa_result` 仍会拿 reviewer.model 和 generation.model 求交集。
- 只转述、不裁决：模型说 false 就写 false，脚本不修正任何结论（红线同 codex 适配器）。

环境变量：

- `SANSHENG_WRITE_VISUAL_QA_MODEL`   复核模型，默认 `claude-opus-5`
- `SANSHENG_WRITE_VISUAL_QA_JOBS`    并发看图进程数，默认 3
- `SANSHENG_WRITE_VISUAL_QA_CLAUDE`  claude 可执行文件，默认 `~/.local/bin/claude`，其次 PATH 里的 `claude`
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_paths import PROCESS_DIR, process_file  # noqa: E402
from visual_qa import _fully_segmented_by_allowed  # noqa: E402
from visual_qa_codex import (  # noqa: E402
    _build_prompt,
    _build_schema,
    _loose,
    _normalized,
    _sha256_file,
)

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_JOBS = 3
PER_ASSET_TIMEOUT = 420
RETRY_TIMEOUT = 240
RETRY_PAUSE = 10


def _resolve_claude(name: str) -> str:
    if name and (os.path.sep in name or (os.path.altsep and os.path.altsep in name)):
        return str(Path(name).expanduser())
    home_bin = Path.home() / ".local" / "bin" / "claude"
    if home_bin.is_file():
        return str(home_bin)
    return shutil.which(name or "claude") or (name or "claude")


def _extract_json(text: str) -> dict[str, Any] | None:
    """`--output-format json` 的外层是 Claude Code 的结果信封；结论在 result 字段里。
    容错：信封解析失败时直接在全文里找第一个顶层 JSON 对象。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        envelope = json.loads(text)
        if isinstance(envelope, dict):
            structured = envelope.get("structured_output")
            if isinstance(structured, dict):
                return structured
            inner = envelope.get("result")
            if isinstance(inner, dict):
                return inner
            if isinstance(inner, str):
                text = inner.strip()
            elif "checks" in envelope:
                return envelope
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _review_one(
    asset: dict[str, Any],
    *,
    article_dir: Path,
    claude_bin: str,
    model: str,
) -> dict[str, Any]:
    rel = str(asset["path"])
    image_path = (article_dir / rel).resolve()
    if not image_path.is_file():
        return {"path": rel, "_error": f"图片不存在：{image_path}"}

    required_checks = list(asset.get("required_checks") or [])
    schema = _build_schema(required_checks)
    prompt = (
        _build_prompt(asset)
        + "\n\n## 图片位置\n"
        + f"待验收的图片在本机路径：{image_path}\n"
        + "先用 Read 工具把这张图完整看一遍（只读这一个文件，不要读别的文件、不要运行命令），"
        + "再按上面的合同逐项判定。"
    )
    workdir = Path(tempfile.mkdtemp(prefix="visual-qa-claude-"))
    try:
        cmd = [
            claude_bin,
            "-p",
            "--model", model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--tools", "Read",
            # 只放行这张图所在目录：进程 cwd 是临时空目录，不加 --add-dir 时 Read 图片会被
            # dontAsk 静默拒绝，模型只能凭空瞎答（信道自检会拦，但先把路修通）。
            "--add-dir", str(image_path.parent),
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
            "--strict-mcp-config",
        ]
        completed = None
        for budget in (PER_ASSET_TIMEOUT, RETRY_TIMEOUT):
            if completed is not None:
                time.sleep(RETRY_PAUSE)
            completed = subprocess.run(
                cmd,
                cwd=str(workdir),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=budget,
                check=False,
            )
            if completed.returncode == 0:
                break
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-600:]
            return {"path": rel, "_error": f"claude exit={completed.returncode}（含重试一次）：{tail}"}
        payload = _extract_json(completed.stdout)
        if payload is None:
            return {"path": rel, "_error": f"结论不是合法 JSON；原文前 300 字：{completed.stdout[:300]}"}

        checks = payload.get("checks")
        if not isinstance(checks, dict) or any(
            not isinstance(checks.get(name), bool) for name in required_checks
        ):
            return {"path": rel, "_error": f"checks 不完整，需要 {required_checks}"}
        evidence = payload.get("visual_evidence")
        if not isinstance(evidence, list) or not evidence:
            return {"path": rel, "_error": "缺 visual_evidence（只回布尔值不放行）"}

        required_traits = (asset.get("style_contract") or {}).get("required_visual_traits") or []
        if required_traits:
            echoed = {_loose(str(item.get("trait", ""))) for item in evidence if isinstance(item, dict)}
            echoed.discard("")
            missing_traits = [t for t in required_traits if _loose(t) not in echoed]
            if missing_traits:
                return {
                    "path": rel,
                    "_error": (
                        "复核结论没有逐条原样复述 required_visual_traits："
                        f"{missing_traits}；判定提示词未完整送达或复核未按合同执行"
                    ),
                }

        return {
            "path": rel,
            "sha256": _sha256_file(image_path),
            "observed_text": [str(t) for t in (payload.get("observed_text") or []) if str(t).strip()],
            "observed_layout": str(payload.get("observed_layout") or ""),
            "visual_evidence": evidence,
            "checks": {name: bool(checks[name]) for name in required_checks},
            "notes": str(payload.get("notes") or ""),
        }
    except subprocess.TimeoutExpired:
        return {"path": rel, "_error": f"claude 超时（>{PER_ASSET_TIMEOUT}s）"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Code 后端的独立视觉复核适配器")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    # 请求文件在 过程记录/ 里时，文章目录是它的上一级（审计 E4）
    article_dir = request_path.parent.parent if request_path.parent.name == PROCESS_DIR else request_path.parent
    assets = request.get("assets") or []
    if not assets:
        print("request 里没有资产", file=sys.stderr)
        return 2

    model = os.getenv("SANSHENG_WRITE_VISUAL_QA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    claude_bin = _resolve_claude(os.getenv("SANSHENG_WRITE_VISUAL_QA_CLAUDE", "").strip())
    if not Path(claude_bin).is_file():
        print(f"找不到 claude 可执行文件：{claude_bin}", file=sys.stderr)
        return 2
    try:
        jobs = max(1, int(os.getenv("SANSHENG_WRITE_VISUAL_QA_JOBS", str(DEFAULT_JOBS))))
    except ValueError:
        jobs = DEFAULT_JOBS

    generation_models = {
        str((a.get("generation") or {}).get("model") or "").strip() for a in assets
    }
    if model in generation_models:
        print(f"复核模型 {model} 与生图模型重合，视觉闸失效", file=sys.stderr)
        return 2

    print(f"▶ 独立视觉复核（Claude Code）：{len(assets)} 张图 / 模型 {model} / 并发 {jobs}", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(
            pool.map(
                lambda a: _review_one(a, article_dir=article_dir, claude_bin=claude_bin, model=model),
                assets,
            )
        )

    qa = {
        "schema_version": 1,
        "status": "pass",
        "request_sha256": _sha256_file(request_path),
        "reviewer": {
            "role": "independent-visual-reviewer",
            "model": model,
            "run_id": str(uuid.uuid4()),
            "independent": True,
            "backend": "claude-code-cli",
        },
        "assets": [r for r in results if "_error" not in r],
    }

    failures: list[str] = []
    by_path = {str(a["path"]): a for a in assets}
    for result in results:
        rel = result["path"]
        if "_error" in result:
            failures.append(f"{rel}：{result['_error']}")
            print(f"  ✗ {rel}  {result['_error']}", file=sys.stderr)
            continue
        required_checks = set(by_path[rel].get("required_checks") or [])
        bad = [name for name, ok in result["checks"].items() if name in required_checks and not ok]
        observed = [_normalized(t) for t in result["observed_text"]]
        joined = "".join(observed)
        allowed = {
            _normalized(t) for t in by_path[rel].get("expected_text") or [] if _normalized(t)
        }
        unexpected = [
            value
            for value in observed
            if value
            and not any(value == item or value in item for item in allowed)
            and not _fully_segmented_by_allowed(value, allowed)
        ]
        missing = [
            t
            for t in by_path[rel].get("required_text") or []
            if _normalized(t) not in observed and _normalized(t) not in joined
        ]
        # 以下确定性判据与 visual_qa_codex.py 逐条同源：能用代码判死的不留给模型。
        garbled = [t for t in result["observed_text"] if "□" in t]
        seen_once: dict[str, int] = {}
        for value in result["observed_text"]:
            key = _normalized(value)
            if key:
                seen_once[key] = seen_once.get(key, 0) + 1
        repeated = sorted(k for k, n in seen_once.items() if n > 1)
        required_not_once = [
            value
            for value in by_path[rel].get("required_text") or []
            if joined.count(_normalized(value)) != 1
        ]
        if bad:
            failures.append(f"{rel} 未通过：{'、'.join(bad)} —— {result['notes']}")
        if garbled:
            failures.append(f"{rel} 转写里有无法辨认的字（坏字）：{garbled}")
        if required_not_once:
            failures.append(f"{rel} 必须文字没有恰好出现一次：{required_not_once}")
        if "text_match" in required_checks and missing:
            failures.append(f"{rel} 缺文字：{missing}")
        if repeated and "text_match" in required_checks:
            failures.append(f"{rel} 同一句渲染多遍：{repeated}")
        if unexpected and "no_unexpected_text" in required_checks:
            failures.append(f"{rel} 白名单外文字：{unexpected}")
        ok = not (
            bad
            or (missing if "text_match" in required_checks else [])
            or garbled
            or required_not_once
            or (repeated if "text_match" in required_checks else [])
            or (unexpected if "no_unexpected_text" in required_checks else [])
        )
        print(
            f"  {'✓' if ok else '✗'} {rel}"
            + (f"  未过：{'、'.join(bad)}" if bad else "")
            + (f"  重复：{repeated}" if repeated else "")
            + (f"  缺字：{missing}" if missing else ""),
            file=sys.stderr,
        )

    if failures:
        qa["status"] = "fail"
        qa["failures"] = failures

    # raw 永远落盘：候选 JSON 校验不过会被上游删除，raw 是事后排查的唯一线索。
    process_file(article_dir, "_visual-qa.raw.json", for_write=True).write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.output).write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        print("\n未通过明细：", file=sys.stderr)
        for item in failures:
            print(f"  • {item}", file=sys.stderr)
        # 仍返回 0：不合格结论交给 visual_qa.py 的校验器统一裁决（与 codex 适配器同语义）。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
