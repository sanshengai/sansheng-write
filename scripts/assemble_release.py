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
THEME_AUDIO_BLOCK_RE = re.compile(
    r"(?ms)(?:\r?\n)?"
    r"<!-- AUDIO-CARD-START -->.*?<!-- AUDIO-CARD-END -->"
    r"(?:\r?\n)?"
)
PODCAST_AUDIO_BLOCK_RE = re.compile(
    r"(?ms)(?:\r?\n)?"
    r"<!-- PODCAST-CARD-START -->.*?<!-- PODCAST-CARD-END -->"
    r"(?:\r?\n)?"
)
AUDIO_BLOCK_RES = (THEME_AUDIO_BLOCK_RE, PODCAST_AUDIO_BLOCK_RE)
INLINE_CLOSING_TAGS_RE = re.compile(
    r"(?i)(?:[ \t]*</(?:a|b|cite|code|del|em|i|ins|kbd|mark|q|s|small|span|strong|sub|sup|u)>)*[ \t]*"
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
    for pattern in AUDIO_BLOCK_RES:
        normalized = pattern.sub("", normalized)
    # Machine blocks occupy whole paragraphs; insertion/removal may leave one extra
    # blank line. Normalize only repeated blank lines, never author prose bytes.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.rstrip() + "\n"


def author_content_sha256(text: str) -> str:
    return hashlib.sha256(strip_machine_assembly(text).encode("utf-8")).hexdigest()


def safe_anchor_insertion_index(text: str, match: re.Match[str]) -> int | None:
    """Return the paragraph-end insertion point after harmless inline closers.

    Visual anchors are authored as visible prose.  When the prose is wrapped in
    inline HTML such as ``<mark>…</mark>``, the closing tag is not part of the
    visible anchor.  Inserting at ``match.end()`` would split that tag pair and
    make machine-block removal change the author-controlled Markdown.
    """
    start = match.end()
    boundary = re.search(r"\n[ \t]*\n|\Z", text[start:])
    if boundary is None:  # defensive; the \Z branch should always match
        return None
    trailing = text[start : start + boundary.start()]
    if INLINE_CLOSING_TAGS_RE.fullmatch(trailing) is None:
        return None
    return start + len(trailing)


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

    audio_blocks = []
    body = clean
    for pattern in AUDIO_BLOCK_RES:
        match = pattern.search(body)
        if match:
            audio_blocks.append(match.group(0).strip())
        body = pattern.sub("", body)
    body = body.rstrip()
    items = list(plan["infographics"])
    opening = [item for item in items if item["position"] == "opening"]
    middle = [item for item in items if item["position"] == "middle"]
    closing = [item for item in items if item["position"] == "closing"]
    if len(opening) != 1 or len(closing) != 1:
        return None, ["visual-plan 必须恰有 1 张 opening 与 1 张 closing 信息图"]

    insertions: dict[int, list[str]] = {}

    def add(index: int, item: dict[str, Any]) -> None:
        insertions.setdefault(index, []).append(_visual_block(item))

    # 不能再用 H2 数量均分猜图位：它会把“看似插进正文”的图放到错误论证段。
    # visual-plan 的 anchor 是作者正文里唯一、原样可查的锚句；图片永远插在它之后。
    for item in [*opening, *middle, *closing]:
        anchor = str(item.get("anchor") or "")
        hits = [match for match in re.finditer(re.escape(anchor), body)]
        if len(hits) != 1:
            return None, [
                f"信息图 {item.get('id')} 的 anchor 必须在定稿.md 作者正文中唯一命中 1 次；"
                f"当前命中 {len(hits)} 次：{anchor!r}"
            ]
        insertion_index = safe_anchor_insertion_index(body, hits[0])
        if insertion_index is None:
            return None, [
                f"信息图 {item.get('id')} 的 anchor 必须落在段末；"
                f"当前锚句后仍有可见正文：{anchor!r}"
            ]
        add(insertion_index, item)

    assembled = body
    for index in sorted(insertions, reverse=True):
        blocks = "\n\n".join(insertions[index])
        before = assembled[:index].rstrip()
        after = assembled[index:].lstrip()
        assembled = f"{before}\n\n{blocks}\n\n{after}".rstrip()
    if audio_blocks:
        assembled = f"{assembled}\n\n" + "\n\n".join(audio_blocks)
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
