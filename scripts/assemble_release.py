#!/usr/bin/env python3
"""Deterministically insert compiled infographic references into 定稿.md."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .visual_workflow import validate_visual_plan
except ImportError:  # pragma: no cover - direct script execution
    from visual_workflow import validate_visual_plan


VISUAL_BLOCK_RE = re.compile(
    r"(?ms)(?:\r?\n)?"
    r"<!-- SANSHENG-VISUAL-START:([A-Za-z0-9_.-]+) -->\r?\n"
    r".*?"
    r"<!-- SANSHENG-VISUAL-END:\1 -->"
    r"(?:\r?\n)?"
)
AUDIO_BLOCK_RE = re.compile(
    r"(?ms)(?:\r?\n)?"
    r"<!-- AUDIO-CARD-START -->.*?<!-- AUDIO-CARD-END -->"
    r"(?:\r?\n)?"
)
LEGACY_VISUAL_REF_RE = re.compile(
    r"(?m)^[ \t]*!\[[^\]\r\n]*\]"
    r"\((?:\./)?素材/infographic-?\d+\.png(?:\s+[\"'][^\"']*[\"'])?\)"
    r"[ \t]*(?:\r?\n)?"
)


def strip_machine_assembly(text: str) -> str:
    """Return author-controlled text, excluding registered machine blocks."""
    normalized = text.replace("\r\n", "\n")
    normalized = VISUAL_BLOCK_RE.sub("", normalized)
    normalized = LEGACY_VISUAL_REF_RE.sub("", normalized)
    normalized = AUDIO_BLOCK_RE.sub("", normalized)
    # Machine blocks occupy whole paragraphs; insertion/removal may leave one extra
    # blank line. Normalize only repeated blank lines, never author prose bytes.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.rstrip() + "\n"


def author_content_sha256(text: str) -> str:
    return hashlib.sha256(strip_machine_assembly(text).encode("utf-8")).hexdigest()


def _visual_block(item: dict[str, Any]) -> str:
    item_id = str(item["id"])
    title = str(item["title"]).strip()
    return (
        f"<!-- SANSHENG-VISUAL-START:{item_id} -->\n"
        f"![{title}](素材/infographic-{item_id}.png)\n"
        f"<!-- SANSHENG-VISUAL-END:{item_id} -->"
    )


def _load_plan(cwd: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = cwd / "visual-plan.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["缺 visual-plan.json；先生成并 compile-visuals"]
    except json.JSONDecodeError as exc:
        return None, [f"visual-plan.json 解析失败：{exc}"]
    errors = validate_visual_plan(plan)
    return (plan if not errors else None), errors


def assemble_release_markdown(
    cwd: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Insert opening/middle/closing images without changing author prose."""
    cwd = Path(cwd).resolve()
    plan, errors = _load_plan(cwd)
    if errors or plan is None:
        return None, errors
    draft = cwd / "定稿.md"
    try:
        original = draft.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ["缺 定稿.md"]

    author_hash_before = author_content_sha256(original)
    clean = VISUAL_BLOCK_RE.sub("", original.replace("\r\n", "\n"))
    clean = LEGACY_VISUAL_REF_RE.sub("", clean)
    if "SANSHENG-VISUAL-START:" in clean or "SANSHENG-VISUAL-END:" in clean:
        return None, ["定稿.md 含不配对的 SANSHENG-VISUAL marker"]

    audio_match = AUDIO_BLOCK_RE.search(clean)
    audio = audio_match.group(0).strip() if audio_match else ""
    body = AUDIO_BLOCK_RE.sub("", clean).rstrip()
    headings = list(re.finditer(r"(?m)^##\s+.+$", body))
    items = list(plan["infographics"])
    opening = [item for item in items if item["position"] == "opening"]
    middle = [item for item in items if item["position"] == "middle"]
    closing = [item for item in items if item["position"] == "closing"]
    if len(opening) != 1 or len(closing) != 1:
        return None, ["visual-plan 必须恰有 1 张 opening 与 1 张 closing 信息图"]

    insertions: dict[int, list[str]] = {}

    def add(index: int, item: dict[str, Any]) -> None:
        insertions.setdefault(index, []).append(_visual_block(item))

    opening_index = headings[0].start() if headings else len(body)
    add(opening_index, opening[0])
    for index, item in enumerate(middle):
        if headings:
            heading_index = round((index + 1) * len(headings) / (len(middle) + 1))
            heading_index = min(max(heading_index, 0), len(headings) - 1)
            add(headings[heading_index].start(), item)
        else:
            add(len(body), item)
    add(len(body), closing[0])

    assembled = body
    for index in sorted(insertions, reverse=True):
        blocks = "\n\n".join(insertions[index])
        before = assembled[:index].rstrip()
        after = assembled[index:].lstrip()
        assembled = f"{before}\n\n{blocks}\n\n{after}".rstrip()
    if audio:
        assembled = f"{assembled}\n\n{audio}"
    assembled = assembled.rstrip() + "\n"

    author_hash_after = author_content_sha256(assembled)
    if author_hash_after != author_hash_before:
        return None, ["装配改变了作者正文；拒绝写入"]
    changed = assembled != original.replace("\r\n", "\n")
    if changed:
        draft.write_text(assembled, encoding="utf-8")
    return {
        "schema_version": 1,
        "changed": changed,
        "image_count": len(items),
        "author_content_sha256": author_hash_after,
    }, []


def main() -> None:
    result, errors = assemble_release_markdown(Path.cwd())
    if errors:
        print("❌ 发布 Markdown 装配失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    action = "已更新" if result["changed"] else "无需更新"
    print(f"✅ {action}定稿.md：嵌入 {result['image_count']} 张信息图")


if __name__ == "__main__":
    main()
