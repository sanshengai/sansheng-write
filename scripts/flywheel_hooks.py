"""写作飞轮的自动捕获：存 AI 初稿快照、定稿时自动比对、把待学习的改稿排队。

为什么需要它：飞轮学的是「AI 初稿 → 作者终稿」的差异，可初稿一旦被作者改动就没了原件，
导致 2026-07 之后经验库再没有新增（lessons.yaml 最后一条停在 07-02）。这里让脚本在流水线里
顺手存下初稿，不靠 Agent 自觉；定稿时自动出 diff 并排队，下一篇开写前再提炼、由作者确认。

规范版本 1（与画风手册的 flywheel 同版本）：只存字段与产物路径；提炼出的规则必须经作者确认才写入。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SPEC_VERSION = 1
SNAPSHOT = "_ai-draft.md"
SNAPSHOT_META = "_ai-draft.json"
DIFF_FILE = "_learn-diff.txt"
MIN_CHARS = 600  # 骨架或占位稿不算初稿


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _flywheel_dir() -> Path:
    import profile_config as PC
    return PC.flywheel_dir()


def _process_path(cwd: Path, name: str, *, for_write: bool = False) -> Path:
    from article_paths import process_file
    return process_file(cwd, name, for_write=for_write)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_ai_draft(cwd: Path, *, force: bool = False, basis: str = "first_pipeline_call") -> dict | None:
    """存下当前 定稿.md 作为 AI 初稿基线。已存在则不覆盖（force 才重存），已批准的稿不再存。"""
    cwd = Path(cwd)
    draft = cwd / "定稿.md"
    if not draft.is_file():
        return None
    data = draft.read_bytes()
    if len(data.decode("utf-8", "ignore")) < MIN_CHARS:
        return None
    target = _process_path(cwd, SNAPSHOT)
    approved = _process_path(cwd, "_draft-approval.md").exists()
    if target.exists() and not force:
        return None
    if approved and not force:  # 作者已拍板，这时的稿子多半是终稿，存了会把终稿当初稿
        return None
    target = _process_path(cwd, SNAPSHOT, for_write=True)
    target.write_bytes(data)
    meta = {"spec": SPEC_VERSION, "at": _now(), "sha256": _sha(data), "chars": len(data.decode("utf-8", "ignore")), "basis": basis}
    _process_path(cwd, SNAPSHOT_META, for_write=True).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def _learn_script() -> Path:
    return Path(__file__).resolve().parent / "learn_edits.py"


def queue_learning(cwd: Path, final: Path | None = None) -> dict:
    """定稿时调用：有初稿基线就自动出 diff 并排队；没有基线就如实记一条“缺基线”，让断流看得见。"""
    cwd = Path(cwd)
    final = Path(final) if final else cwd / "定稿.md"
    fdir = _flywheel_dir()
    fdir.mkdir(parents=True, exist_ok=True)
    queue = fdir / "pending_learn.jsonl"
    item = {"spec": SPEC_VERSION, "at": _now(), "article": cwd.name, "status": "pending"}
    snap = _process_path(cwd, SNAPSHOT)
    if not snap.is_file() or not final.is_file():
        item.update(status="no_baseline", note="没有 AI 初稿快照，这一篇无法比对")
    else:
        d_bytes, f_bytes = snap.read_bytes(), final.read_bytes()
        if _sha(d_bytes) == _sha(f_bytes):
            item.update(status="unchanged", note="定稿与初稿相同，作者没有改动")
        else:
            out = subprocess.run([sys.executable, str(_learn_script()), "diff", "--draft", str(snap), "--final", str(final),
                                  "--no-promote-voice"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            diff_path = _process_path(cwd, DIFF_FILE, for_write=True)
            diff_path.write_text(out.stdout, encoding="utf-8")
            item.update(draft_sha256=_sha(d_bytes), final_sha256=_sha(f_bytes), diff=str(diff_path), diff_chars=len(out.stdout),
                        note="作者改过稿：下一篇开写前提炼 1–2 条候选规则，请作者确认后再写入经验库")
            if out.returncode != 0:
                item.update(status="diff_failed", note=(out.stderr or "")[-160:])
    with queue.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def pending_items() -> list[dict]:
    queue = _flywheel_dir() / "pending_learn.jsonl"
    if not queue.is_file():
        return []
    rows = [json.loads(x) for x in queue.read_text(encoding="utf-8").splitlines() if x.strip()]
    done = {r["article"] for r in rows if r.get("status") in {"done", "dismissed"}}
    return [r for r in rows if r.get("status") == "pending" and r["article"] not in done]


def mark(article: str, status: str) -> None:
    if status not in {"done", "dismissed"}:
        raise ValueError("status 只能是 done 或 dismissed")
    queue = _flywheel_dir() / "pending_learn.jsonl"
    with queue.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"spec": SPEC_VERSION, "at": _now(), "article": article, "status": status}, ensure_ascii=False) + "\n")


def stalled(limit: int = 5) -> bool:
    """连续 limit 篇定稿都没有可比对的基线 → 飞轮断了。"""
    queue = _flywheel_dir() / "pending_learn.jsonl"
    if not queue.is_file():
        return False
    rows = [json.loads(x) for x in queue.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if r.get("status") in {"pending", "no_baseline", "unchanged", "diff_failed"}][-limit:]
    return len(rows) >= limit and all(r["status"] in {"no_baseline", "diff_failed"} for r in rows)
