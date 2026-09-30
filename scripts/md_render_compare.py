#!/usr/bin/env python3
"""对照两份 HTML 的结构：标签、class、内联样式、属性、文字逐项比较，报出第一批差异。

用途：验证 md_render.py 与 baoyu-md 的输出等价（金标准对照），以及 format_layout 之后的最终 HTML 是否一致。
用法：python3 md_render_compare.py A.html B.html [--ignore-attr data-local-path] [--limit 20]
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {"br", "img", "hr", "meta", "link", "input", "ellipse", "circle", "rect", "path", "stop"}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        c = self.cur
        while c is not self.root and c.tag != tag:
            c = c.parent
        if c is not self.root:
            self.cur = c.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.children.append(Node("#text", {"t": re.sub(r"\s+", " ", data).strip()}, self.cur))


def parse(path: Path) -> Node:
    b = Builder()
    b.feed(path.read_text(encoding="utf-8"))
    return b.root


def norm_style(s: str) -> str:
    return "; ".join(sorted(x.strip().lower() for x in s.split(";") if x.strip()))


SKIP_TAGS: set[str] = set()


def flat(n: Node, out: list, depth=0, ignore=()):
    if n.tag in SKIP_TAGS:
        out.append((n.tag, "skipped"))
        return
    if n.tag == "#text":
        out.append(("text", n.attrs["t"]))
        return
    if n.tag in {"style", "head", "meta", "title", "svg", "g", "defs", "ellipse", "circle", "rect", "path"} and n.tag != "#root":
        return
    attrs = {k: (norm_style(v) if k == "style" else v) for k, v in n.attrs.items() if k not in ignore}
    out.append((n.tag, tuple(sorted(attrs.items()))))
    for c in n.children:
        flat(c, out, depth + 1, ignore)
    out.append(("/", n.tag))


def compare(a: Path, b: Path, ignore=(), limit=20) -> list[str]:
    fa, fb = [], []
    flat(parse(a), fa, ignore=ignore)
    flat(parse(b), fb, ignore=ignore)
    diffs = []
    for i in range(max(len(fa), len(fb))):
        x = fa[i] if i < len(fa) else None
        y = fb[i] if i < len(fb) else None
        if x != y:
            diffs.append(f"#{i}\n  A: {str(x)[:300]}\n  B: {str(y)[:300]}")
            if len(diffs) >= limit:
                break
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--ignore-attr", action="append", default=[])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--skip-tag", action="append", default=[], help="整棵子树跳过的标签，如 pre（代码块高亮有意不同）")
    args = ap.parse_args()
    SKIP_TAGS.update(args.skip_tag)
    diffs = compare(Path(args.a), Path(args.b), tuple(args.ignore_attr), args.limit)
    print("\n".join(diffs) if diffs else "结构一致")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
