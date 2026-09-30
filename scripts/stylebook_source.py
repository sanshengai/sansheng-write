"""Immutable editorial source and exact, reproducible image-reference insertion."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_source(cwd: Path, source: dict) -> Path:
    cwd = Path(cwd).resolve()
    draft = cwd / "定稿.md"
    data = draft.read_bytes()
    if not data or hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError("原文已改变，不能冻结为本次制作来源")
    target = cwd / "素材/stylebook-sources" / f"{source['sha256']}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("已冻结原文损坏，拒绝覆盖")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    return target


def assembled_text(original: str, plan: dict) -> str:
    """Insert only registered blocks; preserve every original character in order."""
    try:
        from .assemble_release import safe_anchor_insertion_index, author_content_sha256
    except ImportError:
        from assemble_release import safe_anchor_insertion_index, author_content_sha256
    if "SANSHENG-VISUAL-START:" in original or "SANSHENG-VISUAL-END:" in original:
        raise ValueError("冻结原文已含旧机器配图块；须先明确新的编辑原文和计划")
    insertions = {}
    for item in plan["article_plan"]["items"]:
        match = re.fullmatch(r"「(.+)」(之后|之前)", item["position"], flags=re.S)
        if not match:
            raise ValueError(f"图片 {item['id']} 须给出确切引用句的之前/之后位置")
        anchor, direction = match.groups()
        hits = list(re.finditer(re.escape(anchor), original))
        if len(hits) != 1:
            raise ValueError(f"图片 {item['id']} 位置引用须唯一命中，当前 {len(hits)} 次")
        hit = hits[0]
        if direction == "之后":
            index = safe_anchor_insertion_index(original.rstrip(), hit)
            if index is None:
                raise ValueError(f"图片 {item['id']} 的位置引用须落在段末")
        else:
            boundary = original.rfind("\n\n", 0, hit.start())
            start = boundary + 2 if boundary >= 0 else 0
            if original[start:hit.start()].strip():
                raise ValueError(f"图片 {item['id']} 的之前位置须落在段首")
            index = start
        image_id = item["id"]
        block = (f"<!-- SANSHENG-VISUAL-START:{image_id} -->\n"
                 f"![](素材/infographic-{image_id}.png)\n"
                 f"<!-- SANSHENG-VISUAL-END:{image_id} -->")
        insertions.setdefault(index, []).append(block)
    output = original
    for index in sorted(insertions, reverse=True):
        # Add characters only: do not trim author prose, move audio or rewrite line endings.
        output = output[:index] + "\n\n" + "\n\n".join(insertions[index]) + "\n\n" + output[index:]
    if author_content_sha256(output) != author_content_sha256(original):
        raise ValueError("装配改变作者正文，拒绝交付")
    return output


def methods() -> dict:
    return {"source": file_sha(Path(__file__).resolve()),
            "assembly_helpers": file_sha(Path(__file__).resolve().with_name("assemble_release.py"))}


def current_source(cwd: Path, batch: dict, plan: dict) -> Path:
    """Require frozen bytes and either the exact source or its exact canonical assembly."""
    cwd = Path(cwd).resolve()
    expected = cwd / "素材/stylebook-sources" / f"{batch['source']['sha256']}.md"
    snapshot = batch.get("source_snapshot")
    if not isinstance(snapshot, str) or (cwd / snapshot).resolve() != expected:
        raise ValueError("缺本篇确切冻结原文；须重新编译，不自动迁移旧凭证")
    if file_sha(expected) != batch["source"]["sha256"]:
        raise ValueError("冻结原文字节已改变")
    if batch.get("source_methods") != methods():
        raise ValueError("原文与装配核对方法已改变；须重新编译")
    draft = cwd / "定稿.md"
    if file_sha(draft) != batch["source"]["sha256"]:
        # Exact bytes matter: a matching author hash alone cannot authenticate inserted blocks.
        try:
            expected_bytes = assembled_text(expected.read_bytes().decode("utf-8"), plan).encode("utf-8")
        except ValueError as exc:
            raise ValueError(f"原文与装配内容无法核对：{exc}") from exc
        if draft.read_bytes() != expected_bytes:
            raise ValueError("原文或装配内容已改变，编译请求失效")
    return expected
