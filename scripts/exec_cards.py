#!/usr/bin/env python3
"""执行卡与源文档的同步守护（2026-09-23 审计 E1）。

规则文档总量已超出一篇文章能忠实读完的范围，所以按文体做「执行卡」：每张 ≤10 KB，
从大文档提炼，每条规则注明出处 ``（出处：writing.md §三条直球守则）``。大文档降为查阅库。

提炼物最怕的是源文档改了、卡还停在旧说法上。这里把每条出处对应的源章节做摘要，
记在 ``references/执行卡-sources.json``；源章节一变，``check`` 就报出是哪张卡、哪一节，
逼着回头复核卡片，复核完再 ``refresh`` 更新摘要。

    python3 scripts/exec_cards.py check            # 全部检查（测试也跑这个）
    python3 scripts/exec_cards.py check --no-digest  # 起草时只查出处能否唯一解析
    python3 scripts/exec_cards.py refresh          # 复核完卡片后更新摘要
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REFERENCES = SKILL_DIR / "references"
CARD_GLOB = "执行卡-*.md"
MANIFEST = REFERENCES / "执行卡-sources.json"
MAX_BYTES = 10 * 1024

_CITATION_GROUP = re.compile(r"[（(]出处[：:]([^）)]+)[）)]")
_CITATION_ITEM = re.compile(r"^\s*([\w\-.]+\.md)\s*§\s*(.+?)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 全文篇幅上限（作者不设字数目标或上限；组件本身的字位约束不在此列）
_WORD_CAP = re.compile(r"(?:全文|正文|文章|篇幅|通篇)[^\n。；]{0,10}?\d{3,5}\s*字|字数上限|字数目标")


def cards(root: Path = REFERENCES) -> list[Path]:
    return sorted(p for p in root.glob(CARD_GLOB) if p.suffix == ".md")


def parse_citations(text: str) -> list[tuple[str, str]]:
    """``（出处：a.md §甲；b.md §乙）`` → ``[("a.md", "甲"), ("b.md", "乙")]``，保持首次出现顺序。"""
    found: list[tuple[str, str]] = []
    for group in _CITATION_GROUP.findall(text):
        for part in re.split(r"[；;]", group):
            match = _CITATION_ITEM.match(part)
            if match and (match.group(1), match.group(2)) not in found:
                found.append((match.group(1), match.group(2)))
    return found


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    heads, fenced = [], False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else _HEADING.match(line)
        if match:
            heads.append((index, len(match.group(1)), match.group(2)))
    return heads


def section_text(path: Path, heading: str) -> tuple[str | None, str]:
    """取 ``heading`` 所在章节（到下一个同级或更高级标题为止）。返回 ``(文本, 问题)``。"""
    if not path.is_file():
        return None, f"源文件不存在：{path.name}"
    lines = path.read_text(encoding="utf-8").splitlines()
    heads = _headings(lines)
    hits = [h for h in heads if heading in h[2]]
    if not hits:
        return None, f"{path.name} 里找不到标题含「{heading}」的章节"
    if len(hits) > 1:
        return None, f"{path.name} 里有 {len(hits)} 个标题含「{heading}」，出处要写到唯一"
    start, level, _ = hits[0]
    end = next((i for i, lv, _ in heads if i > start and lv <= level), len(lines))
    return "\n".join(line.rstrip() for line in lines[start:end]).strip() + "\n", ""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def current_manifest(root: Path = REFERENCES) -> tuple[dict, list[str]]:
    manifest: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    for card in cards(root):
        entries: dict[str, str] = {}
        for filename, heading in parse_citations(card.read_text(encoding="utf-8")):
            text, problem = section_text(root / filename, heading)
            if problem:
                problems.append(f"{card.name}：{problem}")
            else:
                entries[f"{filename} §{heading}"] = digest(text)
        manifest[card.name] = entries
    return manifest, problems


def check(root: Path = REFERENCES, *, manifest_path: Path | None = None,
          digests: bool = True) -> list[str]:
    problems: list[str] = []
    found = cards(root)
    if not found:
        return [f"{root} 下没有执行卡"]
    for card in found:
        raw = card.read_bytes()
        if len(raw) > MAX_BYTES:
            problems.append(f"{card.name} 有 {len(raw)} 字节，超过 {MAX_BYTES}")
        text = raw.decode("utf-8")
        if not parse_citations(text):
            problems.append(f"{card.name} 没有任何「（出处：文件 §章节）」")
        for match in _WORD_CAP.finditer(text):
            problems.append(f"{card.name} 出现全文字数限定：「{match.group(0)}」（不设字数目标或上限）")
    current, resolve_problems = current_manifest(root)
    problems += resolve_problems
    if not digests:
        return problems
    manifest_path = manifest_path or root / MANIFEST.name
    try:
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return problems + [f"缺 {manifest_path.name} 或无法解析；复核卡片后运行 exec_cards.py refresh"]
    for card, entries in current.items():
        old = recorded.get(card) or {}
        for key, value in entries.items():
            if key not in old:
                problems.append(f"{card}：新出处 {key} 未登记摘要；复核后 refresh")
            elif old[key] != value:
                problems.append(f"{card}：源章节 {key} 已改动，复核卡片里对应的规则后 refresh")
        for key in old:
            if key not in entries:
                problems.append(f"{card}：摘要表里的 {key} 卡片已不再引用；refresh 清理")
    for card in recorded:
        if card not in current:
            problems.append(f"摘要表里的 {card} 已不存在；refresh 清理")
    return problems


def refresh(root: Path = REFERENCES, *, manifest_path: Path | None = None) -> list[str]:
    current, problems = current_manifest(root)
    if problems:
        return problems
    (manifest_path or root / MANIFEST.name).write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="执行卡与源文档同步守护")
    parser.add_argument("action", choices=["check", "refresh"])
    parser.add_argument("--no-digest", action="store_true", help="只查出处能否唯一解析、体积与字数限定")
    args = parser.parse_args(argv)
    problems = check(digests=not args.no_digest) if args.action == "check" else refresh()
    for problem in problems:
        print(f"❌ {problem}")
    if not problems:
        print("✅ 执行卡出处齐全" + ("" if args.action == "check" else "，摘要已更新"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
