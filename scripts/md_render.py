#!/usr/bin/env python3
"""Markdown → 微信兼容的内联样式 HTML。内置实现，取代 baoyu-markdown-to-html（bun + baoyu-md）。

输出结构与 baoyu-md 的 ``default`` 主题一致（同样的 class 名、同样的内联样式、同样的图片/列表/表格结构），
所以后面的 ``format_layout.py`` 无需改动。样式表来自对 baoyu-md 实际输出的逐项对照（见
``tests/test_md_render.py`` 的金标准夹具），主题样式思路参考 baoyu-skills 的 baoyu-md（MIT，© Jim Liu）。

与 baoyu-md 的有意差别（都不影响公众号呈现）：
- 代码块不做语法高亮，也不带 macOS 三色点小图标（公众号编辑器常剥掉内嵌 SVG）；
- 不支持 KaTeX、PlantUML、Mermaid、脚注、ruby、幻灯片等文章里从没用过的扩展；
- 列表项前缀（``• `` / ``1. ``）、``==高亮==``、图片占位与 ``data-local-path`` 的行为保持一致。

用法：``python3 md_render.py 定稿.md [--color '#2F6F8F'] [--keep-title] [-o 定稿.html]``
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import json
import re
import sys
from pathlib import Path

FONT_SANS = ("-apple-system-font,BlinkMacSystemFont, Helvetica Neue, PingFang SC, Hiragino Sans GB , "
             "Microsoft YaHei UI , Microsoft YaHei ,Arial,sans-serif")
FOREGROUND = "#3f3f3f"
BLOCKQUOTE_BG = "#f7f7f7"
FONT_SIZE = "16px"
DEFAULT_PRIMARY = "#0F4C81"


def styles(primary: str) -> dict[str, str]:
    """各元素的内联样式（baoyu-md default 主题在 juice 内联后的实际结果）。"""
    container = f"font-family: {FONT_SANS}; font-size: {FONT_SIZE}; line-height: 1.75; text-align: left;"
    return {
        "container": container,
        "body": f"padding: 24px; background: #ffffff; max-width: 860px; margin: 0 auto; {container}",
        "h1": f"display: table; padding: 0 1em; border-bottom: 2px solid {primary}; margin: 2em auto 1em; color: {FOREGROUND}; "
              f"font-size: calc({FONT_SIZE} * 1.2); font-weight: bold; text-align: center;",
        "h2": f"display: table; padding: 0 0.2em; margin: 4em auto 2em; color: #fff; background: {primary}; "
              f"font-size: calc({FONT_SIZE} * 1.2); font-weight: bold; text-align: center;",
        "h3": f"padding-left: 8px; border-left: 3px solid {primary}; margin: 2em 8px 0.75em 0; color: {FOREGROUND}; "
              f"font-size: calc({FONT_SIZE} * 1.1); font-weight: bold; line-height: 1.2;",
        "h4": f"margin: 2em 8px 0.5em; color: {primary}; font-size: calc({FONT_SIZE} * 1); font-weight: bold;",
        "h5": f"margin: 1.5em 8px 0.5em; color: {primary}; font-size: calc({FONT_SIZE} * 1); font-weight: bold;",
        "h6": f"margin: 1.5em 8px 0.5em; font-size: calc({FONT_SIZE} * 1); color: {primary};",
        "p": f"margin: 1.5em 8px; letter-spacing: 0.1em; color: {FOREGROUND};",
        "blockquote": f"margin-top: 0; margin-right: 0; margin-left: 0; font-style: normal; padding: 1em; border-left: 4px solid {primary}; "
                      f"border-radius: 6px; color: {FOREGROUND}; background: {BLOCKQUOTE_BG}; margin-bottom: 1em;",
        "blockquote_p": f"display: block; font-size: 1em; letter-spacing: 0.1em; color: {FOREGROUND}; margin: 0;",
        "strong": f"color: {primary}; font-weight: bold; font-size: inherit;",
        "em": "font-style: italic; font-size: inherit;",
        "a": "color: #576b95; text-decoration: none;",
        "codespan": "font-size: 90%; color: #d14; background: rgba(27, 31, 35, 0.05); padding: 3px 5px; border-radius: 4px;",
        "ul": f"list-style: circle; padding-left: 1em; margin-left: 0; color: {FOREGROUND};",
        "ol": f"padding-left: 1em; margin-left: 0; color: {FOREGROUND};",
        "listitem": f"display: block; margin: 0.2em 8px; color: {FOREGROUND};",
        "hr": ("border-style: solid; border-width: 2px 0 0; border-color: rgba(0, 0, 0, 0.1); -webkit-transform-origin: 0 0; "
               "-webkit-transform: scale(1, 0.5); transform-origin: 0 0; transform: scale(1, 0.5); height: 0.4em; margin: 1.5em 0;"),
        "img": "display: block; width: 100%; margin: 1.5em auto;",
        "table": f"color: {FOREGROUND};",
        "thead": f"font-weight: bold; color: {FOREGROUND};",
        "th": f"border: 1px solid #dfdfdf; padding: 0.25em 0.5em; color: {FOREGROUND}; word-break: keep-all; background: rgba(0, 0, 0, 0.05);",
        "td": f"border: 1px solid #dfdfdf; padding: 0.25em 0.5em; color: {FOREGROUND}; word-break: keep-all;",
        "table_wrap": f"{container} max-width: 100%; overflow: auto;",
        "pre": "color: #24292e; background: #fff; font-size: 90%; overflow-x: auto; border-radius: 8px; line-height: 1.5; "
               "margin: 10px 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.05); padding: 0 !important;",
        "code": "font-size: 90%; border-radius: 4px; display: -webkit-box; padding: 0.5em 1em 1em; overflow-x: auto; "
                "text-indent: 0; color: inherit; background: none; white-space: nowrap; margin: 0;",
        "highlight": f"background-color: {primary}; padding: 2px 4px; border-radius: 2px; color: #fff;",
    }


RAW_IMG = "display: block; max-width: 100%; margin: 0.1em auto 0.5em; border-radius: 4px;"  # 手写 <img> 走的主题规则，与 markdown 图片不同


def _decls(style: str) -> list[tuple[str, str]]:
    out = []
    for part in style.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip():
                out.append((k.strip(), v.strip()))
    return out


def merge_style(css: str, inline: str) -> str:
    """主题 CSS 在前、元素自带的行内样式在后；同名属性以行内为准（juice 的效果）。"""
    inl = _decls(inline)
    names = {k.lower() for k, _ in inl}
    merged = [(k, v) for k, v in _decls(css) if k.lower() not in names] + inl
    return "; ".join(f"{k}: {v}" for k, v in merged) + ";" if merged else ""


_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^<>]*?)?)(/?)>", re.S)
_STYLE_ATTR = re.compile(r"\sstyle=(\"([^\"]*)\"|'([^']*)')", re.I)


def style_raw_html(raw: str, s: dict[str, str]) -> str:
    """手写 HTML（section / p / ul / table …）也要吃到主题的类型选择器样式，与 baoyu-md 对齐。"""
    type_styles = {"section": s["container"], "p": s["p"],
                   "h1": s["h1"], "h2": s["h2"], "h3": s["h3"], "h4": s["h4"], "h5": s["h5"], "h6": s["h6"],
                   "blockquote": s["blockquote"], "ul": s["ul"], "ol": s["ol"], "li": s["listitem"], "strong": s["strong"],
                   "em": s["em"], "a": s["a"], "code": s["codespan"], "hr": s["hr"], "img": RAW_IMG, "table": s["table"],
                   "thead": s["thead"], "th": s["th"], "td": s["td"]}
    stack: list[str] = []
    first_child_pending: list[bool] = []

    def repl(m: re.Match[str]) -> str:
        closing, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            while stack and stack[-1] != tag:
                stack.pop(); first_child_pending.pop()
            if stack:
                stack.pop(); first_child_pending.pop()
            return m.group(0)
        pending = bool(stack) and stack[-1] == "section" and first_child_pending[-1]
        if stack:
            first_child_pending[-1] = False
        if tag in type_styles:
            existing = _STYLE_ATTR.search(attrs)
            inline = (existing.group(2) if existing and existing.group(2) is not None else existing.group(3)) if existing else ""
            style = merge_style(type_styles[tag], inline)
            if pending:
                style = merge_style(style, "margin-top: 0 !important")
            attrs = _STYLE_ATTR.sub("", attrs) + f' style="{style}"'
        elif pending:
            existing = _STYLE_ATTR.search(attrs)
            inline = (existing.group(2) if existing and existing.group(2) is not None else existing.group(3)) if existing else ""
            attrs = _STYLE_ATTR.sub("", attrs) + f' style="{merge_style("", inline + ("; " if inline else "") + "margin-top: 0 !important")}"'
        void = tag in {"br", "img", "hr", "meta", "input", "link"} or bool(selfclose)
        if not void:
            stack.append(tag)
            first_child_pending.append(tag == "section")
        return f"<{tag}{attrs}{'/' if selfclose else ''}>"

    def process(segment: str) -> str:
        return _TAG.sub(repl, segment)

    # 注释与 <style> 原样保留
    parts = re.split(r"(<!--.*?-->|<style\b.*?</style>)", raw, flags=re.S | re.I)
    return "".join(p if i % 2 else process(p) for i, p in enumerate(parts))


FIRST_CHILD = " margin-top: 0 !important;"  # baoyu-md: `#output section > :first-child { margin-top: 0 !important }`


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def esc_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- 前置元数据 ----------------
def strip_quotes(value: str) -> str:
    v = value.strip()
    pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"))
    for a, b in pairs:
        if len(v) >= 2 and v.startswith(a) and v.endswith(b):
            return v[1:-1].strip()
    return v


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^\s*---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        i = line.find(":")
        if i <= 0:
            continue
        fm[line[:i].strip()] = strip_quotes(line[i + 1:].strip())
    return fm, m.group(2)


def clean_summary(value: str) -> str:
    v = _html.unescape(strip_quotes(value))
    v = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", v, flags=re.S | re.I)
    v = re.sub(r"<br\s*/?>", " ", v, flags=re.I)
    v = re.sub(r"</?[a-z][a-z0-9:-]*(?:\s+[^>]*)?>", " ", v, flags=re.I)
    return re.sub(r"\s+", " ", v).strip()


def extract_summary(body: str, max_len: int = 120) -> str:
    for line in body.split("\n"):
        t = line.strip()
        if not t or t.startswith(("#", "![", ">", "-", "*", "```")) or re.match(r"^\d+\.", t):
            continue
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"\*(.+?)\*", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        t = re.sub(r"`([^`]+)`", r"\1", t)
        s = clean_summary(t)
        if len(s) > 20:
            return s if len(s) <= max_len else s[: max_len - 3] + "..."
    return ""


def extract_title(body: str) -> str:
    fenced = False
    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        m = None if fenced else re.match(r"^(#{1,2})\s+(.+?)\s*#*\s*$", line)
        if m:
            return strip_quotes(m.group(2))
    return ""


# ---------------- 预处理 ----------------
_FENCE = re.compile(r"^(\s*)(```+|~~~+)")


def _protect_code(text: str) -> tuple[str, list[str]]:
    """把围栏代码块与行内代码换成占位符，避免后续正则误伤。"""
    bucket: list[str] = []

    def keep(s: str) -> str:
        bucket.append(s)
        return f"\u0000CODE{len(bucket) - 1}\u0000"

    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not (lines[j].lstrip().startswith(m.group(2)[0] * 3)):
                j += 1
            out.append(keep("\n".join(lines[i: j + 1])))
            i = j + 1
            continue
        out.append(lines[i])
        i += 1
    joined = "\n".join(out)
    joined = re.sub(r"(`+)(.+?)\1", lambda m: keep(m.group(0)), joined)
    return joined, bucket


def _restore(text: str, bucket: list[str]) -> str:
    return re.sub(r"\u0000CODE(\d+)\u0000", lambda m: bucket[int(m.group(1))], text)


def cjk_friendly_emphasis(text: str) -> str:
    """CommonMark 的加粗 / 斜体规则在中文标点相邻时会失效（``**“词”**中文``）。这里直接改写成 HTML 标签，
    与 baoyu-md 的 remark-cjk-friendly 预处理等效：内部格式被压平成纯文本。"""
    text, bucket = _protect_code(text)
    text = re.sub(r"\*\*(?=\S)([^\n]+?)(?<=\S)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = re.sub(r"(?<![\*\w<])\*(?=[^\s*])([^\n*]+?)(?<=[^\s*])\*(?!\*)", lambda m: f"<em>{m.group(1)}</em>", text)
    return _restore(text, bucket)


def markup_highlight(text: str, primary: str) -> str:
    text, bucket = _protect_code(text)
    style = styles(primary)["highlight"]
    text = re.sub(r"==(?=\S)([^\n=]+?)(?<=\S)==", lambda m: f'<span class="markup-highlight" style="{style}">{m.group(1)}</span>', text)
    return _restore(text, bucket)


_IMG_MD = re.compile(r"!\[([^\]]*)\]\((<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\)")


def images_to_placeholders(text: str, base_dir: Path) -> tuple[str, dict[str, dict[str, str]]]:
    text, bucket = _protect_code(text)
    found: dict[str, dict[str, str]] = {}

    def sub(m: re.Match[str]) -> str:
        alt, href = m.group(1), m.group(2)
        href = href[1:-1] if href.startswith("<") else href
        key = f"MDIMGPH_{len(found) + 1}"
        found[key] = {"alt": alt, "src": href}
        return key

    return _restore(_IMG_MD.sub(sub, text), bucket), found


# ---------------- 渲染 ----------------
class Renderer:
    def __init__(self, primary: str, base_dir: Path, images: dict[str, dict[str, str]]):
        self.s = styles(primary)
        self.base_dir = base_dir
        self.images = images

    # 行内
    def inline(self, children) -> str:
        out, stack = [], []
        for t in children or []:
            k = t.type
            if k == "text":
                out.append(esc(t.content))
            elif k == "softbreak" or k == "hardbreak":
                out.append("<br>")
            elif k == "code_inline":
                out.append(f'<code class="codespan" style="{self.s["codespan"]}">{esc(t.content)}</code>')
            elif k == "html_inline":
                out.append(self.restyle_inline_html(t.content))
            elif k == "strong_open":
                out.append(f'<strong style="{self.s["strong"]}">')
            elif k == "strong_close":
                out.append("</strong>")
            elif k == "em_open":
                out.append(f'<em style="{self.s["em"]}">')
            elif k == "em_close":
                out.append("</em>")
            elif k == "s_open":
                out.append("<del>")
            elif k == "s_close":
                out.append("</del>")
            elif k == "link_open":
                href = t.attrGet("href") or ""
                stack.append(href)
                title = t.attrGet("title")
                out.append(f'<a href="{esc_attr(href)}" title="{{T}}" style="{self.s["a"]}">')
                stack[-1] = (href, len(out) - 1, title)
            elif k == "link_close":
                href, idx, title = stack.pop()
                inner = "".join(out[idx + 1:])
                plain = re.sub(r"<[^>]+>", "", inner)
                if href == _html.unescape(plain):  # 链接文字就是网址：只留文字
                    del out[idx:]
                    out.append(inner)
                else:
                    out[idx] = out[idx].replace("{T}", esc_attr(title or _html.unescape(plain)))
                    out.append("</a>")
            elif k == "image":
                out.append(esc(t.content))
            else:
                out.append(esc(t.content or ""))
        text = "".join(out)
        return self.fill_images(text)

    def restyle_inline_html(self, raw: str) -> str:
        # 行内的 <strong>/<em>（来自加粗预处理）补上主题样式；其余手写行内 HTML 也套主题类型样式
        if raw == "<strong>":
            return f'<strong style="{self.s["strong"]}">'
        if raw == "<em>":
            return f'<em style="{self.s["em"]}">'
        return style_raw_html(raw, self.s)

    def fill_images(self, text: str) -> str:
        def sub(m: re.Match[str]) -> str:
            info = self.images.get(m.group(0))
            if not info:
                return m.group(0)
            src = info["src"]
            local = "" if re.match(r"^(https?:|data:)", src) else f' data-local-path="{esc_attr(str((self.base_dir / src).resolve()))}"'
            return f'<img src="{esc_attr(src)}"{local} alt="{esc_attr(info["alt"])}" style="{self.s["img"]}">'
        return re.sub(r"MDIMGPH_\d+", sub, text)

    # 块
    def render(self, tokens, quote_depth: int = 0) -> str:
        out: list[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            k = t.type
            if k == "heading_open":
                tag = t.tag
                out.append(f'<{tag} class="{tag}" data-heading="true" style="{self.s[tag]}">{self.inline(tokens[i + 1].children)}</{tag}>')
                i += 3
            elif k == "paragraph_open":
                content = self.inline(tokens[i + 1].children)
                if content.strip():
                    st = self.s["blockquote_p"] if quote_depth else self.s["p"]
                    out.append(f'<p class="p" style="{st}">{content}</p>')
                i += 3
            elif k == "blockquote_open":
                j = self.match(tokens, i)
                out.append(f'<blockquote class="blockquote" style="{self.s["blockquote"]}">{self.render(tokens[i + 1:j], quote_depth + 1)}</blockquote>')
                i = j + 1
            elif k in ("bullet_list_open", "ordered_list_open"):
                j = self.match(tokens, i)
                out.append(self.list_html(tokens[i:j + 1]))
                i = j + 1
            elif k in ("fence", "code_block"):
                out.append(self.code_html(t.content, (t.info or "").split(" ")[0] if k == "fence" else ""))
                i += 1
            elif k == "hr":
                out.append(f'<hr class="hr" style="{self.s["hr"]}">')
                i += 1
            elif k == "table_open":
                j = self.match(tokens, i)
                out.append(self.table_html(tokens[i:j + 1]))
                i = j + 1
            elif k == "html_block":
                out.append(style_raw_html(t.content.rstrip("\n"), self.s))
                i += 1
            else:
                i += 1
        return "".join(out)

    @staticmethod
    def match(tokens, i: int) -> int:
        depth = 0
        for j in range(i, len(tokens)):
            depth += tokens[j].nesting
            if depth == 0:
                return j
        return len(tokens) - 1

    def list_html(self, toks) -> str:
        ordered = toks[0].type == "ordered_list_open"
        n = int(toks[0].attrGet("start") or 1) if ordered else 1
        items, nested = [], []
        i = 1
        while i < len(toks) - 1:
            if toks[i].type == "list_item_open":
                j = self.match(toks, i)
                body = toks[i + 1:j]
                first, extra = [], []
                k = 0
                while k < len(body):
                    b = body[k]
                    if b.type == "paragraph_open":
                        first.append(self.inline(body[k + 1].children))
                        k += 3
                    elif b.type in ("bullet_list_open", "ordered_list_open"):
                        e = self.match(body, k)
                        extra.append(self.list_html(body[k:e + 1]))
                        k = e + 1
                    else:
                        k += 1
                prefix = f"{n}. " if ordered else "• "
                items.append(f'<li class="listitem" style="{self.s["listitem"]}">{prefix}{" ".join(first)}</li>' + "".join(extra))
                n += 1
                i = j + 1
            else:
                i += 1
        tag = "ol" if ordered else "ul"
        return f'<{tag} class="{tag}" style="{self.s[tag]}">{"".join(items)}</{tag}>'

    def code_html(self, code: str, lang: str) -> str:
        body = esc(code.rstrip("\n")).replace("\n", "<br>")
        body = re.sub(r"(^|<br>| ) ", lambda m: m.group(1) + "&nbsp;", body)
        return (f'<pre class="hljs code__pre" style="{self.s["pre"]}"><code class="language-{esc_attr(lang)}" '
                f'style="{self.s["code"]}">{body}</code></pre>')

    def table_html(self, toks) -> str:
        head, rows, cur, in_head = [], [], None, False
        i = 0
        while i < len(toks):
            t = toks[i]
            if t.type == "thead_open":
                in_head = True
            elif t.type == "thead_close":
                in_head = False
            elif t.type == "tr_open":
                cur = []
            elif t.type == "tr_close":
                (head if in_head else rows).append(cur)
            elif t.type in ("th_open", "td_open"):
                cur.append((t.type == "th_open", self.inline(toks[i + 1].children)))
            i += 1
        thead = "".join(f'<th class="th" style="{self.s["th"]}">{c}</th>' for _, c in (head[0] if head else []))
        tbody = "".join('<tr class="tr">' + "".join(f'<td class="td" style="{self.s["td"]}">{c}</td>' for _, c in r) + "</tr>" for r in rows)
        return (f'<section style="{self.s["table_wrap"]}"><table class="preview-table" style="{self.s["table"]}{FIRST_CHILD}">'
                f'<thead style="{self.s["thead"]}">{thead}</thead><tbody>{tbody}</tbody></table></section>')


def first_child_margin(html: str) -> str:
    """`section > :first-child { margin-top: 0 !important }`：给 container 的第一个子元素补 margin-top。"""
    m = re.match(r"^(<(?!/)[a-zA-Z][^>]*?\sstyle=\")([^\"]*)(\")", html)
    if not m or "margin-top: 0 !important" in m.group(2):
        return html
    style = re.sub(r"(^|;)\s*margin-top:\s*0\s*;?", lambda k: k.group(1), m.group(2)).strip()  # 旧的 margin-top 让位给 !important 版
    style = (style + ";" if style and not style.endswith(";") else style)
    style += FIRST_CHILD
    return m.group(1) + style + m.group(3) + html[m.end():]


def _markdown_it():
    """优先用随仓内置的 markdown-it-py（scripts/_vendor），不要求用户装包。"""
    vendor = str(Path(__file__).resolve().parent / "_vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from markdown_it import MarkdownIt
    return MarkdownIt


def convert(markdown: str, *, primary: str = DEFAULT_PRIMARY, keep_title: bool = True, base_dir: Path = Path("."),
            default_title: str = "document") -> dict:
    MarkdownIt = _markdown_it()

    fm, body = parse_frontmatter(markdown)
    title = strip_quotes(fm.get("title", "")) or extract_title(body) or default_title
    author = strip_quotes(fm.get("author", ""))
    description = strip_quotes(fm.get("description") or fm.get("summary") or "") or extract_summary(body, 120)

    src = markup_highlight(cjk_friendly_emphasis(body), primary)
    src, images = images_to_placeholders(src, base_dir)
    md = MarkdownIt("commonmark", {"html": True, "breaks": True}).enable(["table", "strikethrough"])
    renderer = Renderer(primary, base_dir, images)
    content = renderer.render(md.parse(src))
    content = first_child_margin(content)
    if not keep_title:
        content = re.sub(r"<h[12][^>]*>.*?</h[12]>", "", content, count=1, flags=re.S)
    s = styles(primary)
    section = f'<section class="container" style="{s["container"]}">{content}</section>'
    head = ["<!doctype html>", "<html>", "<head>", '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">', f"  <title>{esc_attr(title)}</title>"]
    if author:
        head.append(f'  <meta name="author" content="{esc_attr(author)}">')
    if description:
        head.append(f'  <meta name="description" content="{esc_attr(description)}">')
    head += ["</head>", f'<body style="{s["body"]}">', '  <div id="output">', section, "  </div>", "</body>", "</html>"]
    return {"html": "\n".join(head) + "\n", "title": title, "author": author, "summary": description, "images": list(images.values())}


def render_file(path: Path, out: Path | None = None, *, primary: str = DEFAULT_PRIMARY, keep_title: bool = True) -> dict:
    path = Path(path).resolve()
    out = Path(out) if out else path.with_suffix(".html")
    result = convert(path.read_text(encoding="utf-8"), primary=primary, keep_title=keep_title, base_dir=path.parent,
                     default_title=path.stem)
    backup = None
    if out.exists():
        backup = out.with_name(out.name + ".bak-" + _dt.datetime.now().strftime("%Y%m%d%H%M%S"))
        out.rename(backup)
    out.write_text(result["html"], encoding="utf-8")
    return {"title": result["title"], "author": result["author"], "summary": result["summary"], "htmlPath": str(out),
            "backupPath": str(backup) if backup else None, "images": result["images"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("markdown")
    ap.add_argument("--color", default=DEFAULT_PRIMARY, help="主题色，如 '#2F6F8F'")
    ap.add_argument("--keep-title", action="store_true", help="保留正文里第一个 H1/H2（写作流水线默认保留）")
    ap.add_argument("-o", "--output")
    ap.add_argument("--theme", default="default", help="只支持 default，保留参数是为了与旧命令兼容")
    a = ap.parse_args()
    if a.theme != "default":
        print("md_render 只实现 default 主题", file=sys.stderr)
        return 2
    try:
        info = render_file(Path(a.markdown), Path(a.output) if a.output else None, primary=a.color, keep_title=a.keep_title)
    except ImportError as exc:
        print(f"缺内置解析库 scripts/_vendor/markdown_it：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
