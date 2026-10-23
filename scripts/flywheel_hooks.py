"""写作飞轮的自动捕获：存 AI 初稿快照、定稿时自动比对、把待学习的改稿排队。

为什么需要它：飞轮学的是「AI 初稿 → 作者终稿」的差异，可初稿一旦被作者改动就没了原件，
导致 2026-07 之后经验库再没有新增（lessons.yaml 最后一条停在 07-02）。这里让脚本在流水线里
顺手存下初稿，不靠 Agent 自觉；定稿时自动出 diff 并排队，下一篇开写前再提炼、由作者确认。

规范版本 1（与画风库的 flywheel 同版本）：只存字段与产物路径；提炼出的规则必须经作者确认才写入。
"""
from __future__ import annotations

import argparse
import os
import hashlib
import json
import subprocess
import sys
import uuid
from contextlib import contextmanager
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


def _learning_dir(cwd: Path) -> Path:
    root = Path(cwd).resolve()
    folder = (root / "过程记录" / "learning").resolve()
    if not folder.is_relative_to(root):
        raise ValueError("学习目录越出文章目录")
    return folder


def _read_rows(fh) -> list[dict]:
    fh.seek(0)
    return [json.loads(line) for line in fh if line.strip()]


@contextmanager
def _locked_queue():
    folder = _flywheel_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".pending-learn.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.seek(0, 2) == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with (folder / "pending_learn.jsonl").open("a+", encoding="utf-8") as fh:
                yield fh
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _append(fh, item: dict) -> None:
    fh.seek(0, 2)
    fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    fh.flush()


def _local_file(cwd: Path, value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else cwd / path).resolve()
    if not path.is_relative_to(cwd.resolve()) or not path.is_file():
        raise ValueError("学习来源必须是文章目录内的真实文件")
    if not path.read_bytes().strip():
        raise ValueError("学习来源或作者证据不能为空")
    return path


def capture_author_revision(cwd: Path, source: Path, *, evidence: Path,
                            source_kind: str) -> dict:
    """按明确作者来源封存原件；author-directed 仅学习意见，不作为声纹。"""
    cwd = Path(cwd).resolve()
    if source_kind not in {"author-edited", "author-directed"}:
        raise ValueError("source_kind 必须为 author-edited 或 author-directed")
    source = _local_file(cwd, source)
    evidence = _local_file(cwd, evidence)
    data, evidence_data = source.read_bytes(), evidence.read_bytes()
    folder = _learning_dir(cwd)
    folder.mkdir(parents=True, exist_ok=True)
    identity = folder / "identity.json"
    if not identity.exists():
        try:
            with identity.open("x", encoding="utf-8") as fh:
                json.dump({"article_uid": "learn-" + str(uuid.uuid4())}, fh)
        except FileExistsError:
            pass
    article_uid = json.loads(identity.read_text())["article_uid"]
    digest = _sha(data)
    revision_id = _sha((article_uid + ":" + digest + ":" + source_kind).encode())
    revision_dir = folder / revision_id
    revision_dir.mkdir(exist_ok=True)
    # 摘要命名且绝不覆盖；来源文件后来变化不改变已封存样本。
    for name, payload in [("author.md", data), ("evidence-" + _sha(evidence_data) + ".md", evidence_data)]:
        target = revision_dir / name
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError("既有作者学习快照已变化，拒绝覆盖")
        else:
            with target.open("xb") as fh:
                fh.write(payload)
    receipt = {
        "spec": 2, "article_uid": article_uid, "revision_id": revision_id,
        "source_kind": source_kind, "source_original": source.relative_to(cwd).as_posix(),
        "source_file": (revision_dir / "author.md").relative_to(cwd).as_posix(),
        "source_sha256": digest,
        "evidence_file": (revision_dir / ("evidence-" + _sha(evidence_data) + ".md")).relative_to(cwd).as_posix(),
        "evidence_sha256": _sha(evidence_data),
        "voice_eligible": source_kind == "author-edited",
    }
    (folder / "current.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def _author_revision(cwd: Path) -> tuple[dict | None, str]:
    receipt_path = _learning_dir(cwd) / "current.json"
    if not receipt_path.is_file():
        return None, "缺已登记的作者原件；发布审批不等于作者亲笔证明"
    try:
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("source_kind") not in {"author-edited", "author-directed"}:
            raise ValueError("作者来源类型无效")
        for key in ("source", "evidence"):
            path = _local_file(cwd, receipt[key + "_file"])
            if _sha(path.read_bytes()) != receipt[key + "_sha256"]:
                raise ValueError("作者原件或来源证据摘要不匹配")
        identity = json.loads((_learning_dir(cwd) / "identity.json").read_text())["article_uid"]
        expected = _sha((identity + ":" + receipt["source_sha256"] + ":" + receipt["source_kind"]).encode())
        if receipt.get("article_uid") != identity or receipt.get("revision_id") != expected:
            raise ValueError("作者修订身份不匹配")
        return receipt, ""
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, str(exc)


def _pending_rows(rows: list[dict]) -> list[dict]:
    pending: dict[str, dict] = {}
    for index, row in enumerate(rows):
        status = row.get("status")
        key = row.get("learning_id") or "legacy:" + str(index)
        if status == "pending":
            pending[key] = row
        elif status in {"done", "dismissed"}:
            if "learning_ids" in row:
                for learning_id in row["learning_ids"]:
                    pending.pop(learning_id, None)
            else:
                # v1 没有修订身份：只结清该条之前的同名待办，不吞将来的修订。
                pending = {k: v for k, v in pending.items() if v.get("article") != row.get("article")}
    return list(pending.values())


def queue_learning(cwd: Path, final: Path | None = None) -> dict:
    """只比较已登记作者原件；final 保留调用兼容，不作为作者来源证据。"""
    cwd = Path(cwd).resolve()
    item = {"spec": 2, "at": _now(), "article": cwd.name, "status": "pending"}
    snap = _process_path(cwd, SNAPSHOT)
    revision, error = _author_revision(cwd)
    if not snap.is_file():
        item.update(status="no_baseline", note="没有 AI 初稿快照，这一篇无法比对")
    elif revision is None:
        item.update(status="needs_author_evidence", note=error)
    else:
        d_bytes = snap.read_bytes()
        author = _local_file(cwd, revision["source_file"])
        f_bytes = author.read_bytes()
        item.update(revision)
        item.update(draft_sha256=_sha(d_bytes), final_sha256=_sha(f_bytes))
        item["learning_id"] = _sha((revision["revision_id"] + ":" + _sha(d_bytes)).encode())
        if d_bytes == f_bytes:
            item.update(status="unchanged", note="作者原件与初稿相同，无需学习")
        else:
            with _locked_queue() as fh:
                rows = _read_rows(fh)
                existing = next((r for r in rows if r.get("learning_id") == item["learning_id"]
                                 and r.get("status") in {"pending", "unchanged"}), None)
                if existing:
                    live = {r.get("learning_id") for r in _pending_rows(rows)}
                    return {**existing, "status": "already_queued" if item["learning_id"] in live else "already_learned"}
                diff_path = _learning_dir(cwd) / revision["revision_id"] / ("diff-" + _sha(d_bytes) + ".txt")
                out = subprocess.run([sys.executable, str(_learn_script()), "diff", "--draft", str(snap),
                                      "--final", str(author), "--no-promote-voice"], capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", check=False)
                if out.returncode != 0:
                    item.update(status="diff_failed", note=(out.stderr or "")[-160:])
                else:
                    if diff_path.exists() and diff_path.read_text() != out.stdout:
                        raise ValueError("既有修订 diff 已变化，拒绝覆盖")
                    diff_path.write_text(out.stdout, encoding="utf-8")
                    item.update(diff=str(diff_path), diff_chars=len(out.stdout),
                                note="按封存作者来源提炼；未经核实不提升为声音样本")
                _append(fh, item)
            return item
    with _locked_queue() as fh:
        rows = _read_rows(fh)
        if item.get("learning_id") and any(r.get("learning_id") == item["learning_id"] for r in rows):
            return {**item, "status": "already_learned"}
        _append(fh, item)
    return item


def pending_items() -> list[dict]:
    queue = _flywheel_dir() / "pending_learn.jsonl"
    if not queue.is_file():
        return []
    with _locked_queue() as fh:
        return _pending_rows(_read_rows(fh))


def mark(article: str, status: str) -> None:
    """接受目录名、article_uid 或 learning_id；同名多身份时拒绝模糊结清。"""
    if status not in {"done", "dismissed"}:
        raise ValueError("status 只能是 done 或 dismissed")
    with _locked_queue() as fh:
        pending = _pending_rows(_read_rows(fh))
        matched = [r for r in pending if article in {r.get("article"), r.get("article_uid"), r.get("learning_id")}]
        identities = {r.get("article_uid") for r in matched if r.get("article_uid")}
        if len(identities) > 1:
            raise ValueError("同名文章对应多个身份，请传 article_uid 或 learning_id")
        ids = [r["learning_id"] for r in matched if r.get("learning_id")]
        # 兼容 v1 历史待办；顺序消费保证这条结清记录不影响后来的待办。
        if any(not r.get("learning_id") for r in matched):
            _append(fh, {"spec": 1, "at": _now(), "article": article, "status": status})
        if ids:
            _append(fh, {"spec": 2, "at": _now(), "article": article, "status": status, "learning_ids": ids})


def stalled(limit: int = 5) -> bool:
    """连续 limit 篇定稿都没有可比对的基线 → 飞轮断了。"""
    queue = _flywheel_dir() / "pending_learn.jsonl"
    if not queue.is_file():
        return False
    rows = [json.loads(x) for x in queue.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if r.get("status") in {"pending", "no_baseline", "unchanged", "diff_failed"}][-limit:]
    return len(rows) >= limit and all(r["status"] in {"no_baseline", "diff_failed"} for r in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="封存有来源的作者修订并排入学习队列")
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("action", choices=["capture-author"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-kind", choices=["author-edited", "author-directed"], required=True)
    args = parser.parse_args()
    import profile_config
    profile_config.bind_workspace(args.dir)
    try:
        capture_author_revision(args.dir, args.source, evidence=args.evidence, source_kind=args.source_kind)
        print(json.dumps(queue_learning(args.dir), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
