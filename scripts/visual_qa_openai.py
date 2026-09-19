#!/usr/bin/env python3
"""OpenAI 兼容接口后端的独立视觉复核适配器。

契约与 `visual_qa_codex.py` 完全一致（`--request` / `--output`、同一套提示词、
同一套结构化裁决），只把「codex exec 看图」换成对任意 OpenAI 兼容
`/chat/completions` 端点的视觉调用。用途：Codex 订阅额度被生图或别的任务打满时，
复核这道闸不必跟着停 —— 2026-09-19 第 105 篇实跑：生图已切到中转，复核却仍卡在
Codex 的 usage limit 上等两小时，就是本文件的由来。

配置（仓根 .env 或 shell env）：
  SANSHENG_WRITE_VISUAL_QA_COMMAND=["python3","-X","utf8","<绝对路径>/scripts/visual_qa_openai.py"]
  SANSHENG_WRITE_VISUAL_QA_MODEL     复核模型（默认 gpt-5.6-terra；必须 ≠ 生图模型）
  SANSHENG_WRITE_VISUAL_QA_BASE_URL  默认取 OPENAI_BASE_URL（如 https://api.vectorengine.cn/v1）
  SANSHENG_WRITE_VISUAL_QA_API_KEY   默认取 OPENAI_API_KEY
  SANSHENG_WRITE_VISUAL_QA_JOBS      并发数（默认 3）

实现上复用 codex 适配器的全部提示词、schema 与裁决逻辑：只替换它的 `_review_one`
（看图这一步）和可执行文件探测；裁决、白名单比对、坏字/重复检测一行不改，避免两份
实现再次分叉（2026-08-14 那次就是两处各写一遍、改一处漏一处）。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import visual_qa_codex as codex_adapter  # noqa: E402

DEFAULT_MODEL = "gpt-5.6-terra"
PER_ASSET_TIMEOUT = 300
RETRY_PAUSE = 8


def _endpoint() -> tuple[str, str]:
    base = (
        os.getenv("SANSHENG_WRITE_VISUAL_QA_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    key = os.getenv("SANSHENG_WRITE_VISUAL_QA_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    return base + "/chat/completions", key


def _post(url: str, key: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _review_one_openai(
    asset: dict[str, Any],
    *,
    article_dir: Path,
    codex_bin: str,  # 签名对齐 codex 适配器，本后端不用
    model: str,
) -> dict[str, Any]:
    rel = str(asset["path"])
    image_path = (article_dir / rel).resolve()
    if not image_path.is_file():
        return {"path": rel, "_error": f"图片不存在：{image_path}"}

    required_checks = list(asset.get("required_checks") or [])
    schema = codex_adapter._build_schema(required_checks)
    prompt = codex_adapter._build_prompt(asset)
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    url, key = _endpoint()
    if not key:
        return {"path": rel, "_error": "缺 API key（SANSHENG_WRITE_VISUAL_QA_API_KEY / OPENAI_API_KEY）"}

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
            ],
        }
    ]
    # 首选 json_schema 强约束；中转不支持时（400）退到 json_object，提示词本身已要求只输出 JSON。
    formats: list[dict[str, Any]] = [
        {"type": "json_schema", "json_schema": {"name": "visual_qa", "schema": schema, "strict": True}},
        {"type": "json_object"},
    ]
    last_err = ""
    raw = ""
    for fmt in formats:
        for attempt in range(2):
            body = {"model": model, "messages": messages, "response_format": fmt, "temperature": 0}
            try:
                resp = _post(url, key, body, PER_ASSET_TIMEOUT)
                raw = str(((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
                if raw.strip():
                    break
                last_err = f"空响应：{json.dumps(resp, ensure_ascii=False)[:300]}"
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last_err = f"HTTP {exc.code}：{detail}"
                if exc.code == 400 and fmt["type"] == "json_schema":
                    break  # 换下一种 response_format
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = f"网络错误：{exc}"
            time.sleep(RETRY_PAUSE)
        if raw.strip():
            break
    if not raw.strip():
        return {"path": rel, "_error": f"复核模型无有效返回（含重试）：{last_err}"}

    try:
        payload = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        return {"path": rel, "_error": f"结论不是合法 JSON：{exc}；原文前 300 字：{raw[:300]}"}
    if not isinstance(payload, dict):
        return {"path": rel, "_error": "结论 JSON 顶层必须是对象"}

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
        echoed = {codex_adapter._loose(str(item.get("trait", ""))) for item in evidence}
        echoed.discard("")
        missing_traits = [t for t in required_traits if codex_adapter._loose(t) not in echoed]
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
        "sha256": codex_adapter._sha256_file(image_path),
        "observed_text": [str(t) for t in (payload.get("observed_text") or []) if str(t).strip()],
        "observed_layout": str(payload.get("observed_layout") or ""),
        "visual_evidence": evidence,
        "checks": {name: bool(checks[name]) for name in required_checks},
        "notes": str(payload.get("notes") or ""),
    }


def main() -> int:
    # 复用 codex 适配器的 main（参数解析、并发、裁决、落盘），只替换看图与可执行探测。
    codex_adapter._review_one = _review_one_openai
    codex_adapter._resolve_codex = lambda name: sys.executable  # is_file 探测用
    codex_adapter.DEFAULT_MODEL = DEFAULT_MODEL
    url, _ = _endpoint()
    print(f"▶ 复核后端：OpenAI 兼容端点 {url}", file=sys.stderr)
    return codex_adapter.main()


if __name__ == "__main__":
    raise SystemExit(main())
