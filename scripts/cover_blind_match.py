#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音频封面 46px 盲配测试（`references/music.md` §验收：盲配测试）。

背景：图标式封面（无字、单主体、深底）只有在旁边那行标题的辅助下才需要被认出——
所以验收方式是把两张封面缩到官网实际显示的 46 px，交给一个**没有本文上下文**的
看图进程，连同打乱顺序的候选标题（本篇 + 作品库最近几篇）一起问「这张是哪篇」。
两张（或当篇仅有的那一张）都配对成功才算过；配错说明封面画的是通用隐喻而不是
锚点本身，需要回 `_audio-cover-plan.json` 改 subject/identity 后 `--force` 重出。

这件事原先靠人工派子 Agent 做（曾有一版「太阳 + 星芒」被认成另一篇同样画太阳的文章），
本模块把它自动接进 `audio_covers.ensure_audio_covers`：本次真的新出了封面（或 `--force`）
时跑，机器凭证写 `_audio-cover-blindmatch.json`（绑定封面 SHA-256）、人读摘要追加进
`_audio-cover-review.md`（不覆盖已有内容）；封面没变时由 `recheck_existing` 沿用已有结论，
配错不会因为重跑 handoff 而消失。

设计上把「纯逻辑」与「调用外部进程」分开，方便不联网、不起子进程也能测完整判定路径：

- 纯逻辑：`build_candidates`（取标题 + 打乱，种子取文章目录名的哈希，可复现）、
  `_judge`（拿模型解析后的 JSON 和候选表判定对错）。
- 调用：`_invoke_model` 是唯一起 `claude -p` 子进程的函数，复用
  `visual_qa_claude.py` 里已经验证过的手法——同样的 `--output-format json` /
  `--json-schema` / `--tools Read` / `--add-dir` / `dontAsk` 组合，以及它的
  `_resolve_claude`（找 claude 可执行文件）与 `_extract_json`（拆 Claude Code
  CLI 的结果信封）两个纯函数，直接复用、不改动那边任何行为。

环境变量：

- `SANSHENG_WRITE_BLIND_MATCH=off`         显式关闭盲配（记 skipped_by_env，不拦交付）
- `SANSHENG_WRITE_BLIND_MATCH_MODEL`       盲配用的模型，默认 `claude-sonnet-5`
  （比 `visual_qa_claude.DEFAULT_MODEL` 的 opus 更便宜；这是一次简单判断，不是精修视觉复核）
- `SANSHENG_WRITE_VISUAL_QA_CLAUDE`        claude 可执行文件，复用视觉 QA 同一个变量
  （公开 Skill 用户如果没配 Claude Code CLI，两处一起找不到，一起跳过，不新增一条配置）

找不到 claude 可执行文件、或 Pillow 缺失，都不拦交付：写一条 warning，凭证里记
`skipped`（`skipped_by_env` / `claude_cli_not_found` / `pillow_missing`）。作品库不可用
时不算跳过，而是退化为「本篇 + 占位干扰标题」继续跑（结果里注明 `degraded`）。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from .article_paths import process_file, process_rel
    from .visual_qa_claude import _extract_json, _resolve_claude
    from . import profile_config as pc
    from . import works_registry
except ImportError:  # pragma: no cover - direct script execution
    from article_paths import process_file, process_rel
    from visual_qa_claude import _extract_json, _resolve_claude
    import profile_config as pc
    import works_registry

BLINDMATCH_FILE = "_audio-cover-blindmatch.json"
REVIEW_FILE = "_audio-cover-review.md"
# 与 audio_covers.COVER_PLAN 同一个字面量；这里不反向 import audio_covers，
# 避免 audio_covers ⇄ cover_blind_match 互相 import 造成循环依赖。
COVER_PLAN_FILENAME = "_audio-cover-plan.json"

ENV_OFF = "SANSHENG_WRITE_BLIND_MATCH"
ENV_MODEL = "SANSHENG_WRITE_BLIND_MATCH_MODEL"
ENV_CLAUDE = "SANSHENG_WRITE_VISUAL_QA_CLAUDE"
DEFAULT_MODEL = "claude-sonnet-5"

THUMB_SMALL = 46
THUMB_BIG = 138  # 46 的整数倍（×3），NEAREST 放大后每个原始像素仍是干净的 3×3 色块
CANDIDATE_LIMIT = 5  # 作品库最近 N 篇，加本篇共 N+1 个候选

TIMEOUT = 180
RETRY_TIMEOUT = 90
RETRY_PAUSE = 5

STAGE_LABELS = {"theme_cover": "主题曲封面", "podcast_cover": "播客封面"}

# 占位干扰标题：只在作品库读不到时使用，凑够候选数量，让盲配仍然有意义
# （只给 1 个候选而没有干扰项，模型必然选中，测试就失去意义）。故意写成
# 普通话题，不带任何「占位/测试」字样——那类字样会被模型当成明显的假选项。
PLACEHOLDER_TITLES = [
    "一台旧打印机的最后一次维修",
    "小区门口那家早餐店关门之后",
    "把通勤路上的时间换成读书的三种办法",
    "给父母换手机时最容易忽略的设置",
    "一次差点错过的末班地铁",
]


def _seed_from_name(name: str) -> int:
    """文章目录名 → 稳定种子；同一篇任何时候重跑，候选打乱顺序都一样。"""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _recent_titles(
    article_dir: Path, *, exclude_seq: int | None, limit: int = CANDIDATE_LIMIT
) -> tuple[list[str], str | None]:
    """作品库最近 ``limit`` 篇标题（按 date/seq 取最近，排除本篇）。

    返回 ``(标题列表, 退化原因)``；作品库不存在 / 为空 / 解析失败都归为退化，
    原因写进返回值第二项，调用方据此决定要不要换成占位干扰标题。
    """
    try:
        pc.bind_workspace(article_dir)
    except Exception:
        pass  # 找不到承载工作树时 bind_workspace 本身返回 None，不算错误
    try:
        path = pc.works_file()
    except Exception as exc:
        return [], f"作品库路径未就绪：{exc}"
    try:
        works = works_registry.load_works(path)
    except Exception as exc:
        return [], f"作品库解析失败（{path}）：{exc}"
    if not works:
        return [], f"作品库为空：{path}"

    def sort_key(work: dict[str, Any]) -> tuple[str, int]:
        seq = work.get("seq")
        return (str(work.get("date") or ""), seq if isinstance(seq, int) else -1)

    pool = [
        w for w in works
        if isinstance(w, dict) and str(w.get("title") or "").strip() and w.get("seq") != exclude_seq
    ]
    pool.sort(key=sort_key, reverse=True)
    titles = [str(w["title"]).strip() for w in pool[:limit]]
    if not titles:
        return [], f"作品库没有可用于盲配的其它标题：{path}"
    return titles, None


def build_candidates(
    article_dir: Path,
    article_title: str,
    *,
    exclude_seq: int | None = None,
    limit: int = CANDIDATE_LIMIT,
    rng_seed: int | None = None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """本篇 + 作品库最近几篇标题，按固定种子打乱。返回 ``(候选表, 是否退化, 退化原因)``。

    候选表每项 ``{"index": 打乱后的编号, "title": 标题, "is_target": 是否本篇}``；
    打乱前先把「是否本篇」绑死在标题上再一起洗牌，不靠字符串相等去认，避免标题
    偶然撞车（占位干扰标题或作品库里恰好有同名文章）时认错目标。
    """
    recent, reason = _recent_titles(article_dir, exclude_seq=exclude_seq, limit=limit)
    degraded = not recent
    degraded_reason = reason if degraded else None
    pool = recent if not degraded else list(PLACEHOLDER_TITLES[:limit])
    entries: list[tuple[str, bool]] = [(article_title, True)] + [(t, False) for t in pool]
    seed = _seed_from_name(article_dir.name) if rng_seed is None else rng_seed
    random.Random(seed).shuffle(entries)
    candidates = [
        {"index": i + 1, "title": title, "is_target": is_target}
        for i, (title, is_target) in enumerate(entries)
    ]
    return candidates, degraded, degraded_reason


def _make_blind_thumb(src: Path, dest: Path, *, small: int = THUMB_SMALL, big: int = THUMB_BIG) -> None:
    """LANCZOS 缩到 46×46，再 NEAREST 放大到 138×138——和今天手动盲配的做法一致：

    看到的信息量仍然只有 46 px 那么多（NEAREST 不会补出新细节，只是把每个像素
    原样放大成一个色块），放大只是方便看图进程实际"看清"，不是给它更多信息。
    """
    from PIL import Image

    with Image.open(src) as img:
        tiny = img.convert("RGB").resize((small, small), Image.LANCZOS)
    blown = tiny.resize((big, big), Image.NEAREST)
    blown.save(dest)


def _build_prompt(candidates: list[dict[str, Any]], image_keys: list[str]) -> str:
    title_lines = "\n".join(f"{c['index']}. {c['title']}" for c in candidates)
    labels = "、".join(STAGE_LABELS.get(k, k) for k in image_keys)
    return (
        "你现在要做一次「46 像素盲配」测试，判断封面小图分别属于哪篇公众号文章。\n"
        f"你会看到 {len(image_keys)} 张{labels}，原图只有 46×46 像素——这是它们在官网播放器 / "
        "播客列表里的实际显示尺寸。为了方便你看清，已经用最近邻插值放大到 138×138，"
        "放大不会带来比 46 像素更多的细节，边缘就应该是色块状的，不代表原图画质差。\n"
        "你完全不知道这几篇文章写了什么，只能凭图片本身的主体形状、颜色、（如果有）图上出现的文字判断。\n\n"
        "候选标题（编号已经打乱，与图片摆放顺序无关）：\n"
        f"{title_lines}\n\n"
        "对给你的每一张图，独立判断它最可能是哪个编号对应文章的封面：先写清你在图上具体看到了什么"
        "（主体是什么形状、什么颜色、有没有可辨认的文字），再给出选择的编号和置信度"
        "（high/medium/low）。只凭图片内容判断，不要因为编号数字大小或候选顺序做任何猜测。\n"
        "如果给你不止一张图，它们完全可能来自同一篇文章（比如同一篇的主题曲封面和播客封面）——"
        "两张图选到同一个编号是完全正常、经常正确的结果，不是需要避免的重复；"
        "每张图只凭它自己的画面独立判断，不要因为另一张图已经选过某个编号就改选别的编号。"
    )


def _build_schema(image_keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["choices"],
        "properties": {
            "choices": {
                "type": "array",
                "minItems": len(image_keys),
                "maxItems": len(image_keys),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["image", "chosen_index", "confidence", "description"],
                    "properties": {
                        "image": {"type": "string", "enum": list(image_keys)},
                        "chosen_index": {"type": "integer"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "description": {"type": "string"},
                    },
                },
            }
        },
    }


def _invoke_model(
    image_paths: dict[str, Path],
    prompt: str,
    schema: dict[str, Any],
    *,
    model: str,
    claude_bin: str,
    timeout: int = TIMEOUT,
    retry_timeout: int = RETRY_TIMEOUT,
    retry_pause: int = RETRY_PAUSE,
) -> tuple[dict[str, Any] | None, str | None]:
    """唯一起子进程的函数：只负责拼命令、跑、摘取 JSON，不做任何判定。

    与 ``visual_qa_claude.py::_review_one`` 同一手法（同一组 CLI flag、同样重试一次、
    同样用 ``_extract_json`` 拆结果信封），独立成一份是因为这里一次要送两张图、
    schema 也和视觉 QA 的检查项完全不同，硬塞回那边的单资产循环反而不清楚。
    """
    if not image_paths:
        return None, "没有需要盲配的封面图"
    add_dirs = sorted({str(Path(p).parent) for p in image_paths.values()})
    location_lines = "\n".join(
        f"- {STAGE_LABELS.get(key, key)}（{key}）：{path}" for key, path in image_paths.items()
    )
    full_prompt = (
        prompt
        + "\n\n## 图片位置\n" + location_lines
        + "\n\n先用 Read 工具把每一张图都完整看一遍（只读这些图片，不要读别的文件、不要运行命令），"
        "再按上面的要求逐张判断并回 JSON。"
    )
    cmd = [
        claude_bin, "-p", "--model", model,
        "--output-format", "json",
        "--json-schema", json.dumps(schema, ensure_ascii=False),
        "--tools", "Read",
        "--permission-mode", "dontAsk",
        "--no-session-persistence",
        "--strict-mcp-config",
    ]
    for add_dir in add_dirs:
        cmd += ["--add-dir", add_dir]
    workdir = Path(tempfile.mkdtemp(prefix="cover-blind-match-run-"))
    try:
        completed = None
        last_error = ""
        for attempt, budget in enumerate((timeout, retry_timeout)):
            if attempt:
                time.sleep(retry_pause)
            try:
                completed = subprocess.run(
                    cmd, cwd=str(workdir), input=full_prompt, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=budget, check=False,
                )
            except subprocess.TimeoutExpired:
                # 超时同样重试一次：首轮超时多半是冷启动或临时拥堵
                completed, last_error = None, f"claude 超时（>{budget}s）"
                continue
            if completed.returncode == 0:
                break
            tail = (completed.stderr or completed.stdout or "").strip()[-600:]
            last_error = f"claude exit={completed.returncode}：{tail}"
        if completed is None or completed.returncode != 0:
            return None, f"{last_error}（含重试一次）"
        payload = _extract_json(completed.stdout)
        if payload is None:
            return None, f"结论不是合法 JSON；原文前 300 字：{completed.stdout[:300]}"
        return payload, None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _judge(
    payload: Any, candidates: list[dict[str, Any]], image_keys: list[str]
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """纯逻辑：拿模型解析后的 JSON 和候选表判定每张图对不对、整体是否通过。"""
    if not isinstance(payload, dict):
        return [], False, f"模型返回不是 JSON 对象：{payload!r}"
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return [], False, "结论缺 choices 数组"
    by_image: dict[str, dict[str, Any]] = {}
    for item in choices:
        if isinstance(item, dict) and item.get("image") in image_keys:
            by_image[item["image"]] = item
    missing = [k for k in image_keys if k not in by_image]
    if missing:
        return [], False, f"choices 缺少 {missing} 的判断"
    index_lookup = {c["index"]: c for c in candidates}
    results: list[dict[str, Any]] = []
    all_correct = True
    for key in image_keys:
        item = by_image[key]
        chosen_index = item.get("chosen_index")
        chosen = index_lookup.get(chosen_index)
        if chosen is None:
            return [], False, f"{key}.chosen_index={chosen_index!r} 不在候选编号 {sorted(index_lookup)} 里"
        correct = bool(chosen.get("is_target"))
        all_correct = all_correct and correct
        results.append({
            "image": key,
            "chosen_index": chosen_index,
            "chosen_title": chosen["title"],
            "confidence": str(item.get("confidence") or ""),
            "description": str(item.get("description") or ""),
            "correct": correct,
        })
    return results, all_correct, None


def _cover_digests(stage_covers: dict[str, Path]) -> dict[str, str]:
    return {key: hashlib.sha256(Path(path).read_bytes()).hexdigest() for key, path in stage_covers.items()}


def _failure_message(results: list[dict[str, Any]], plan_rel: str = COVER_PLAN_FILENAME) -> str:
    detail = [
        f"{STAGE_LABELS.get(r['image'], r['image'])}盲配未通过：模型判给了「{r.get('chosen_title')}」"
        f"（置信度 {r.get('confidence')}），看到的是：{r.get('description')}"
        for r in results if not r.get("correct")
    ]
    detail.append(f"改 {plan_rel} 对应封面的 subject/identity 后 --force 重出")
    return "；".join(detail)


def _write_credential(article_dir: Path, record: dict[str, Any]) -> None:
    path = process_file(article_dir, BLINDMATCH_FILE, for_write=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _beijing_display(iso_utc: str) -> str:
    """给人看的时间戳用北京时间；凭证 JSON 里的 ``at`` 仍是 UTC ISO 不受影响。"""
    try:
        dt = datetime.fromisoformat(iso_utc)
    except ValueError:
        return iso_utc
    try:
        from zoneinfo import ZoneInfo

        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:
        dt = dt.astimezone(timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M")


def _append_review(article_dir: Path, record: dict[str, Any]) -> None:
    """追加一段人读摘要；已有内容（人工写的历史版本）一律保留，只在末尾追加。"""
    path = process_file(article_dir, REVIEW_FILE, for_write=True)
    exists = path.is_file()
    when = _beijing_display(str(record.get("at") or ""))
    parts: list[str] = []
    if not exists:
        parts.append("# 音频封面核对\n")
    parts.append(f"## 自动盲配（{when}，{record.get('model')}）\n")
    cand_lines = "\n".join(
        f"{c['index']}. {'🎯 ' if c.get('is_target') else ''}{c['title']}"
        for c in record.get("candidates", [])
    )
    if cand_lines:
        parts.append(f"候选（种子 {record.get('seed')} 打乱顺序，🎯=本篇）：\n\n{cand_lines}\n")
    if record.get("degraded"):
        parts.append(f"⚠️ 作品库不可用，已用占位干扰标题：{record.get('degraded_reason')}\n")
    result_lines = [
        f"- {STAGE_LABELS.get(r['image'], r['image'])} → 「{r.get('chosen_title')}」，"
        f"信心 {r.get('confidence')}：{r.get('description')}"
        f" {'✅' if r.get('correct') else '❌ 配错'}"
        for r in record.get("results", [])
    ]
    if result_lines:
        parts.append("\n".join(result_lines) + "\n")
    verdict = {"pass": "通过", "fail": "未通过", "error": "未取得结论"}.get(
        record.get("status"), str(record.get("status"))
    )
    reason = record.get("reason")
    parts.append(f"结论：{verdict}" + (f"（{reason}）" if reason else "") + "\n")
    text = "\n".join(parts)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("\n" + text) if exists else text)


def run_blind_match(
    article_dir: Path,
    stage_covers: dict[str, Path],
    *,
    article_title: str,
    exclude_seq: int | None = None,
) -> dict[str, Any]:
    """盲配总控：跳过 / 退化 / 调用 / 判定 / 落盘，一次跑完。

    返回 ``{"status": ..., "errors": [...], "warnings": [...]}``；``errors`` 非空时
    调用方（``audio_covers.ensure_audio_covers``）应把它们并入自己的错误列表，
    使交接因此停下——公开 Skill 用户没配 Claude CLI 的场景走的是 ``warnings``
    而不是 ``errors``，不拦交付。
    """
    at = datetime.now(timezone.utc).isoformat()
    try:
        digests = _cover_digests(stage_covers)
    except OSError:
        digests = {}

    off = os.getenv(ENV_OFF, "").strip().lower()
    if off in ("off", "0", "false", "no"):
        _write_credential(article_dir, {"schema_version": 1, "at": at, "status": "skipped", "skipped_reason": "skipped_by_env"})
        return {"status": "skipped", "errors": [], "warnings": [f"{ENV_OFF}=off，已跳过 46px 盲配"]}

    claude_bin = _resolve_claude(os.getenv(ENV_CLAUDE, "").strip())
    if not claude_bin or not Path(claude_bin).is_file():
        _write_credential(article_dir, {"schema_version": 1, "at": at, "status": "skipped", "skipped_reason": "claude_cli_not_found"})
        return {
            "status": "skipped", "errors": [],
            "warnings": [
                f"找不到可用的 claude 可执行文件，已跳过 46px 盲配（不拦交付；"
                f"可通过 {ENV_CLAUDE} 指定路径，或安装 Claude Code CLI 后自动启用）"
            ],
        }

    if not stage_covers:
        _write_credential(article_dir, {"schema_version": 1, "at": at, "status": "skipped", "skipped_reason": "no_covers"})
        return {"status": "skipped", "errors": [], "warnings": ["没有可供盲配的封面"]}

    image_keys = list(stage_covers.keys())
    candidates, degraded, degraded_reason = build_candidates(
        article_dir, article_title, exclude_seq=exclude_seq,
    )
    model = os.getenv(ENV_MODEL, "").strip() or DEFAULT_MODEL
    seed = _seed_from_name(article_dir.name)
    base: dict[str, Any] = {
        "schema_version": 1, "at": at, "model": model, "seed": seed,
        "cover_sha256": digests,
        "candidates": candidates, "degraded": degraded, "degraded_reason": degraded_reason,
    }

    workdir = Path(tempfile.mkdtemp(prefix="cover-blind-thumbs-"))
    try:
        thumbs: dict[str, Path] = {}
        for key, src in stage_covers.items():
            dest = workdir / f"{key}.png"
            try:
                _make_blind_thumb(src, dest)
            except ImportError as exc:
                base["status"], base["skipped_reason"] = "skipped", f"pillow_missing:{exc}"
                _write_credential(article_dir, base)
                return {"status": "skipped", "errors": [], "warnings": [f"缺 Pillow，已跳过 46px 盲配：{exc}"]}
            except Exception as exc:
                base["status"], base["reason"] = "error", f"{key} 缩略图生成失败（{src}）：{exc}"
                _write_credential(article_dir, base)
                return {"status": "error", "errors": [str(base["reason"])], "warnings": []}
            thumbs[key] = dest

        prompt = _build_prompt(candidates, image_keys)
        schema = _build_schema(image_keys)
        payload, error = _invoke_model(thumbs, prompt, schema, model=model, claude_bin=claude_bin)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if error:
        base["status"], base["reason"] = "error", error
        _write_credential(article_dir, base)
        return {"status": "error", "errors": [f"46px 盲配未取得结论：{error}"], "warnings": []}

    results, all_correct, judge_error = _judge(payload, candidates, image_keys)
    if judge_error:
        base["status"], base["reason"], base["raw_payload"] = "error", judge_error, payload
        _write_credential(article_dir, base)
        return {"status": "error", "errors": [f"46px 盲配结论无法判读：{judge_error}"], "warnings": []}

    base["results"] = results
    base["status"] = "pass" if all_correct else "fail"
    if not all_correct:
        base["reason"] = "有封面配错"
    _write_credential(article_dir, base)
    _append_review(article_dir, base)

    if all_correct:
        return {"status": "pass", "errors": [], "warnings": []}

    return {"status": "fail", "errors": [_failure_message(results, process_rel(article_dir, COVER_PLAN_FILENAME))],
            "warnings": []}


def recheck_existing(
    article_dir: Path,
    stage_covers: dict[str, Path],
    *,
    article_title: str,
    exclude_seq: int | None = None,
) -> dict[str, Any]:
    """封面都已就位、本次没出新图时调用，让已有的盲配结论继续生效。

    - 没有凭证：历史文章或当时没跑盲配，不补跑（不牵动已发布图片）；
    - 凭证绑定的封面哈希与当前一致：``fail`` 继续拦——配错后直接重跑 handoff
      不能绕过；``pass`` / ``skipped`` 放行；``error``（上次没取得结论）重新盲配；
    - 哈希不一致（封面被换过）或凭证缺哈希：重新盲配。
    """
    path = process_file(article_dir, BLINDMATCH_FILE)
    if not path.is_file():
        return {"status": "absent", "errors": [], "warnings": []}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record = {}
    off = os.getenv(ENV_OFF, "").strip().lower() in ("off", "0", "false", "no")
    try:
        same = bool(record.get("cover_sha256")) and record.get("cover_sha256") == _cover_digests(stage_covers)
    except OSError:
        same = False
    status = record.get("status")
    if same and not off:
        if status == "fail":
            return {"status": "fail", "warnings": [],
                    "errors": [_failure_message(record.get("results") or [], process_rel(article_dir, COVER_PLAN_FILENAME))]}
        if status in ("pass", "skipped"):
            return {"status": status, "errors": [], "warnings": []}
    if not article_title:
        return {"status": "skipped", "errors": [], "warnings": ["缺文章标题，无法重新盲配"]}
    return run_blind_match(article_dir, stage_covers, article_title=article_title, exclude_seq=exclude_seq)
