#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已定稿文章搬成 X（Twitter）文章：Markdown → X 编辑器块 → CDP 驱动填入 → 可选发布。

背景（2026-09-18 第 99 篇）：X 文章编辑器只认自己的几种块（标题/副标题/正文/引用/列表/
链接/图片/视频），公众号那套 HTML 版式贴进去会被剥成纯文本，表格压成一行。所以这里
从 ``定稿.md`` 出发做"内容零改动、结构层级对应"的翻译，不追求长得一样：

- ``##`` → h1（编辑器「标题」），``###`` → h2（「副标题」）；粗体/链接保留；``<mark>`` 转粗体
- 表格 → 「字段：值」无序列表（X 表格粘不进去，自动化填单元格太脆）
- ``>`` 引用与 ``` 代码块 → 一行一个引用块（编辑器会把多段引用合成一行）
- 图片按原位插入；竖长图（宽高比 < 3:4）两侧补边缘色垫成 3:4，否则 X 会居中裁掉上下
- 文末追加「信息来源」（解析 SANSHENG-SOURCES 块）和网站全文链接
- 主题曲：X 不能上传音频。``--theme`` 才把 ``素材/bgm_cover.png`` + 主题曲 MP3 合成静帧 MP4
  插在正文第一个大标题前；默认不放（sandy 2026-09-19：不必强行合成视频），播客也不放

粘贴走合成的 ClipboardEvent（Draft.js 会把 <h1>/<strong>/<blockquote> 解析成对应块），
图片和视频走「插入 → 媒体」真实路径。每一步落完都用文本长度 / 图片数校验并重试，
全部贴完后把编辑器 157 个块和源文件逐块 diff，零差异才算通过。

用法::

    python3 x_article.py <文章目录> [--cdp http://127.0.0.1:9333] [--dry-run]
                         [--theme] [--publish] [--caption-file 说明.txt]

产物落在 ``<文章目录>/dist/x/``：垫边图、theme.mp4、receipt.json（草稿 id / 帖子 URL）。
Chrome 需用 baoyu 的 profile 带 ``--remote-debugging-port`` 启动并已登录 X。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html as H
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SITE_ROOT = "https://sanshengai.top/articles/"
XYZ_SHOW = "https://www.xiaoyuzhoufm.com/podcast/69f1a2c798fa520797d8a4e4"  # 叁笙早安AI 节目主页
PASTE_JS = """(html)=>{const el=document.activeElement; const dt=new DataTransfer();
dt.setData('text/html',html); dt.setData('text/plain',html.replace(/<[^>]+>/g,''));
el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));}"""
TEXT_LEN_JS = "()=>document.querySelector('[data-testid=composer]').innerText.length"
BLOCKS_JS = ("()=>[...document.querySelectorAll('[data-testid=composer] [data-block=true]')]"
             ".map(e=>e.className.includes('longform-')? e.innerText.trim():'[MEDIA]')")


# ---------------------------------------------------------------- Markdown → 块
def _inline(s: str) -> str:
    s = H.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"&lt;mark&gt;(.+?)&lt;/mark&gt;", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)  # 编辑器无行内代码样式
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def _sources(md: str) -> list[str]:
    """解析 SANSHENG-SOURCES 机器块：每条 = 名称 / 说明 / URL 三个 section。"""
    m = re.search(r"<!-- SANSHENG-SOURCES -->(.*?)<!-- /SANSHENG-SOURCES -->", md, re.S)
    if not m:
        m = re.search(r"<!-- SANSHENG-SOURCES -->(.*?)<!-- AUDIO-CARD-START -->", md, re.S)
    if not m:
        return []
    items = []
    for block in re.findall(r'<section style="padding:1[24]px[^"]*">(.*?)</section>\s*</section>', m.group(1), re.S):
        # 外层匹配吃掉了最后一个 </section>，补回来再拆三段
        parts = [re.sub(r"<[^>]+>", "", p).strip()
                 for p in re.findall(r"<section[^>]*>(.*?)</section>", block + "</section>", re.S)]
        parts = [p for p in parts if p]
        if len(parts) >= 2 and parts[-1].startswith("http"):
            name, url = parts[0], parts[-1]
            desc = "：" + "；".join(parts[1:-1]) if len(parts) > 2 else ""
            items.append(f"{_inline(name)}{_inline(desc)} {url}")
    return items


def parse_article(article_dir: Path) -> dict:
    md = (article_dir / "定稿.md").read_text(encoding="utf-8")
    description = fm_title = ""
    if md.startswith("---"):
        head, _, md = md.split("---", 2)[1], None, md.split("---", 2)[2]
        for line in head.splitlines():
            if line.strip().startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"').strip("'")
            if line.strip().startswith("title:"):
                fm_title = line.split(":", 1)[1].strip().strip('"').strip("'")
    sources = _sources(md)
    body = re.split(r"<!-- SANSHENG-DEEP-READ -->|<!-- SANSHENG-SOURCES -->|<!-- AUDIO-CARD-START -->", md)[0]
    body = re.sub(r"<!-- SANSHENG-VISUAL-(START|END):\d+ -->\n?", "", body)

    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    extra_sources: list[str] = []
    title = ""
    lines = body.splitlines()

    def flush():
        if buf:
            blocks.append(("html", "".join(buf)))
            buf.clear()

    i = 0
    while i < len(lines):
        st = lines[i].strip()
        if not st:
            i += 1
            continue
        if st.startswith("# "):
            title = st[2:].strip()
            i += 1
            continue
        if st.startswith("## "):
            buf.append(f"<h1>{_inline(st[3:])}</h1>")
            i += 1
            continue
        if st.startswith("### "):
            buf.append(f"<h2>{_inline(st[4:])}</h2>")
            i += 1
            continue
        if st == "---":
            i += 1
            continue
        if st.startswith("<!--"):
            i += 1
            continue
        if re.match(r"<(section|div|table|p[ >])", st):
            # 旧篇目里的裸 HTML 卡片：来源列表转成列表，链接卡转成一行，其余（DEEP READ / 音频卡）丢弃
            depth, raw = 0, []
            while i < len(lines):
                raw.append(lines[i])
                depth += len(re.findall(r"<(section|div|table)\b", lines[i])) - len(re.findall(r"</(section|div|table)>", lines[i]))
                i += 1
                if depth <= 0:
                    break
            html_blob = "\n".join(raw)
            if "信息来源" in html_blob or "SOURCES" in html_blob:
                for para in re.findall(r"<p[^>]*>(.*?)</p>", html_blob, re.S):
                    text = re.sub(r"<br\s*/?>", " ", para)
                    text = re.sub(r"<[^>]+>", "", text).strip()
                    if text and "信息来源" not in text:
                        extra_sources.append(H.escape(re.sub(r"^\d+\.\s*", "", text), quote=False))
            elif "🔗" in html_blob and "http" in html_blob:
                texts = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<(?:span|section)[^>]*>(.*?)</(?:span|section)>", html_blob, re.S)]
                texts = [t for t in texts if t and "复制到浏览器" not in t]
                url = next((t for t in texts if t.startswith("http")), "")
                label = " ".join(t for t in texts if not t.startswith("http"))
                if url:
                    buf.append(f'<p>{_inline(label)}：<a href="{url}">{url}</a></p>')
            continue
        if st.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1
            buf.append("".join(f"<blockquote>{H.escape(c) or ' '}</blockquote>" for c in code))
            continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", st)
        if m:
            flush()
            src = (article_dir / m.group(2)).resolve()
            blocks.append(("image", str(src)))
            cap = m.group(1).strip()
            nxt = next((ln.strip() for ln in lines[i + 1:] if ln.strip()), "")
            own_caption = nxt.startswith(("*", "图注", "_")) or (cap and cap[:8] in nxt)
            if cap and "infographic" not in m.group(2) and not own_caption:  # 信息图标题已画在图里；正文自带图注就不重复
                buf.append(f"<p><em>{_inline(cap)}</em></p>")
            i += 1
            continue
        if st.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            head_row, data = rows[0], rows[1:]
            if head_row[0] == "":  # 对比表：首列是维度，其余列是方案
                items = []
                for r in data:
                    parts = "；".join(f"{head_row[k]}：{r[k]}" for k in range(1, len(r)))
                    items.append(f"<li><strong>{_inline(r[0])}</strong> — {_inline(parts)}</li>")
            else:
                items = [f"<li><strong>{_inline(r[0])}</strong>：{_inline('，'.join(r[1:]))}</li>" for r in data]
            buf.append("<ul>" + "".join(items) + "</ul>")
            continue
        if st.startswith(">"):
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            inner = [("• " + _inline(x[2:])) if x.startswith("- ") else _inline(x) for x in q if x]
            buf.append("".join(f"<blockquote>{x}</blockquote>" for x in inner))
            continue
        if re.match(r"^(- |\d+\. )", st):
            ordered = bool(re.match(r"^\d+\. ", st))
            items = []
            while i < len(lines) and re.match(r"^(- |\d+\. )", lines[i].strip()):
                items.append(f"<li>{_inline(re.sub(r'^(- |\\d+\\. )', '', lines[i].strip()))}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            buf.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        para = [st]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|!\[|\||>|- |\d+\. |---|```)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        buf.append(f"<p>{_inline(' '.join(para))}</p>")
    flush()

    # 导读：frontmatter description 或正文第一个引用块，作为文章卡片摘要的来源
    title = title or fm_title
    return {"title": re.sub(r"^\S+ \| ", "", title), "raw_title": title,
            "description": description, "blocks": blocks, "sources": sources or extra_sources}


# ---------------------------------------------------------------- 素材预处理
def pad_portrait(src: Path, out_dir: Path) -> Path:
    """竖长图（宽高比 < 0.75）两侧补边缘中位色垫成 3:4；其余原样返回。含 EXIF 方向修正。"""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = im.size
    if w / h >= 0.75:
        return src
    W = round(h * 0.75)
    px = [im.getpixel((x, y)) for x in list(range(0, 4)) + list(range(w - 4, w)) for y in range(0, h, 7)]
    bg = tuple(int(statistics.median(c[k] for c in px)) for k in range(3))
    canvas = Image.new("RGB", (W, h), bg)
    canvas.paste(im, ((W - w) // 2, 0))
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (hashlib.sha1(str(src).encode()).hexdigest()[:8] + "-" + src.stem + ".png")
    canvas.save(dst, optimize=True)
    return dst


def theme_video(article_dir: Path, out_dir: Path) -> tuple[Path, str] | None:
    """主题曲 MP3 + 素材/bgm_cover.png → 静帧 MP4（X 不收音频）。返回 (mp4, 歌名)。"""
    manifest = article_dir / "_music-manifest.json"
    cover = article_dir / "素材" / "bgm_cover.png"
    if not cover.is_file():
        return None
    if not manifest.is_file():  # 2026-09 之前的篇目没有 manifest：根目录唯一一个非播客 MP3 就是主题曲
        mp3s = [f for f in article_dir.glob("*.mp3") if f.name != "podcast.mp3"]
        if len(mp3s) != 1:
            return None
        return _render_theme(mp3s[0], cover, out_dir), mp3s[0].stem
    theme = json.loads(manifest.read_text(encoding="utf-8")).get("theme") or {}
    mp3 = article_dir / str((theme.get("playback") or {}).get("path") or "")
    if not mp3.is_file():
        return None
    title = str(theme.get("title") or mp3.stem)
    return _render_theme(mp3, cover, out_dir), title


def _render_theme(mp3: Path, cover: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / "theme.mp4"
    if not mp4.is_file():
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(cover), "-i", str(mp3),
            "-c:v", "libx264", "-tune", "stillimage", "-r", "10", "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4),
        ], check=True)
    return mp4


def site_url(article_dir: Path) -> str:
    for name in ("_website-sync-receipt.json", "_publish-receipt.json"):
        f = article_dir / name
        if f.is_file():
            m = re.search(r'"code":\s*"([A-Z]+-\d+)"', f.read_text(encoding="utf-8"))
            if m:
                return SITE_ROOT + m.group(1).lower() + "/"
    return ""


def wechat_url(article_dir: Path) -> str:
    f = article_dir / "_website-sync-receipt.json"
    if f.is_file():
        m = re.search(r'"wechat_url":\s*"(https://mp\.weixin\.qq\.com/s/[^"]+)"', f.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def xiaoyuzhou_url(article_dir: Path, title: str) -> str:
    """本篇有播客（dist/podcast/audio.mp3）时，到小宇宙节目页按「深聊 | 标题」匹配单集；
    匹配不到（页面只列最近 15 集）就退回节目主页。抓不到网络时返回空串，不阻塞发布。"""
    if not (article_dir / "dist" / "podcast" / "audio.mp3").is_file():
        return ""
    import urllib.request

    try:
        req = urllib.request.Request(XYZ_SHOW, headers={"User-Agent": "Mozilla/5.0"})
        html_text = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S)
        episodes = json.loads(m.group(1))["props"]["pageProps"]["podcast"].get("episodes") or []
        key = title[:12]
        for ep in episodes:
            if key and key in str(ep.get("title") or ""):
                return f"https://www.xiaoyuzhoufm.com/episode/{ep['eid']}"
        return XYZ_SHOW
    except Exception:
        return XYZ_SHOW


def tail_links(article_dir: Path, title: str, site: str) -> str:
    """文末「继续阅读」：网站全文 / 公众号原文 / 小宇宙播客，缺哪个不放哪个。链接放正文里不放主帖。"""
    items = []
    if site:
        items.append(f'<li>网页版全文（含来源链接）：<a href="{site}">{site}</a></li>')
    wx = wechat_url(article_dir)
    if wx:
        items.append(f'<li>公众号原文：<a href="{wx}">{wx}</a></li>')
    xyz = xiaoyuzhou_url(article_dir, title)
    if xyz:
        items.append(f'<li>播客版（小宇宙）：<a href="{xyz}">{xyz}</a></li>')
    return "<h1>继续阅读</h1><ul>" + "".join(items) + "</ul>" if items else ""


# ---------------------------------------------------------------- 编辑器驱动
def _wait_media(page, limit_s: int = 900):
    for _ in range(limit_s * 2):
        page.wait_for_timeout(500)
        if page.get_by_text("正在处理媒体").count() == 0:
            return
    raise SystemExit("媒体处理超时")


SAVE_STATUS_JS = """()=>{const e=[...document.querySelectorAll('span,div')].find(e=>e.children.length==0 && /最后保存|保存中/.test(e.innerText)); return e? e.innerText:''}"""
PLACEHOLDER = "XIMGPH_{n}"


def _wait_saved(page, limit_s: int = 30):
    """改动后状态栏会先清空（约 3 秒），自动保存落地才回到「刚刚最后保存」。媒体插入前后和发布前
    必须等到：编辑器处理完媒体重渲染时会回滚到上一份保存快照，把没保存的段落吞掉（09-19 实证）。
    先等它清空（改动被登记），再等它回来；1.5 秒内没清空视作无待保存改动。"""
    for _ in range(3):
        if not (page.evaluate(SAVE_STATUS_JS) or ""):
            break
        page.wait_for_timeout(500)
    for _ in range(limit_s * 2):
        if "最后保存" in (page.evaluate(SAVE_STATUS_JS) or ""):
            return
        page.wait_for_timeout(500)


def _blocks(page) -> list[str]:
    return page.evaluate("()=>[...document.querySelectorAll('[data-testid=composer] [data-block=true]')].map(e=>(e.className.split(' ')[0]||'media')+'|'+e.innerText.trim())")


def _placeholder_block(page, name: str):
    return page.locator('[data-testid="composer"] [data-block="true"]', has_text=re.compile(rf"^{name}$")).first


def _insert_media_at(page, name: str, path: Path, kind: str):
    """光标放在占位块末尾，走「插入 → 媒体」；媒体落在占位块正下方。然后逐字退格删掉占位文字，
    若占位块上方是文字块再退格一次并入上一块；上方是媒体块时退格无效，留一个空块当间隔（实测行为）。"""
    sel = '[data-testid="composer"] img' if kind == "image" else '[data-testid="composer"] video'
    _wait_saved(page)
    blk = _placeholder_block(page, name)
    blk.scroll_into_view_if_needed()
    blk.click()
    page.keyboard.press("End")
    page.wait_for_timeout(200)
    before = page.locator(sel).count()
    page.locator('[aria-label="添加媒体内容"]').first.click()
    page.wait_for_timeout(700)
    page.locator("[role=menuitem]", has_text="媒体").first.click()
    page.wait_for_selector("input[type=file][multiple]", state="attached", timeout=8000)
    page.locator("input[type=file][multiple]").first.set_input_files(str(path))
    for _ in range(120):
        page.wait_for_timeout(500)
        if page.locator(sel).count() > before:
            break
    else:
        raise SystemExit(f"{name} 媒体未出现：{path}")
    _wait_media(page)
    page.wait_for_timeout(4000)  # 媒体落地后编辑器还会重渲染一次
    _wait_saved(page)
    blk = _placeholder_block(page, name)
    if not blk.count():
        raise SystemExit(f"{name} 占位块在插图后消失")
    blocks_before = _blocks(page)
    idx = next(i for i, b in enumerate(blocks_before) if b.endswith("|" + name))
    prev_is_text = idx > 0 and not blocks_before[idx - 1].startswith("media|")
    blk.click()
    page.keyboard.press("End")
    for _ in range(len(name)):
        page.keyboard.press("Backspace")
    page.wait_for_timeout(300)
    if prev_is_text:
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)
    if _placeholder_block(page, name).count():
        raise SystemExit(f"{name} 占位文字没删干净")
    if page.locator(sel).count() != before + 1:
        raise SystemExit(f"{name} 清理占位时媒体数变了")


def build_draft(page, parsed: dict, media_plan: list) -> str:
    """整篇一次粘贴（块样式最保真），媒体位置先放 XIMGPH_n 占位段，再逐个替换。"""
    page.goto("https://x.com/compose/articles")
    page.wait_for_timeout(4000)
    for _ in range(5):  # 删掉本篇上次没跑完的同名草稿，别的草稿不动
        cell = page.locator('[data-testid="cellInnerDiv"]', has_text=parsed["title"]).first
        if not cell.count():
            break
        cell.locator('[aria-label="更多"]').first.click()
        page.wait_for_timeout(700)
        page.locator("[role=menuitem]", has_text="删除").first.click()
        page.wait_for_timeout(800)
        page.locator('[data-testid="confirmationSheetConfirm"]').click()
        page.wait_for_timeout(1500)
    page.get_by_text("撰写", exact=True).first.click()
    page.wait_for_timeout(6000)
    draft_url = page.url
    page.locator('textarea[name="文章标题"]').click()
    page.keyboard.type(parsed["title"], delay=8)
    page.wait_for_timeout(800)
    cover = Path(media_plan[0][1])
    page.locator('input[data-testid="fileInput"]:not([multiple])').first.set_input_files(str(cover))
    page.wait_for_timeout(3000)
    ap = page.locator('[data-testid="applyButton"]')
    if ap.count():
        ap.click()
        page.wait_for_timeout(2000)
    _wait_media(page)

    # 拼整篇 HTML，媒体处放占位段
    html_parts, media_items = [], []
    for kind, val in media_plan[1:]:
        if kind == "html":
            html_parts.append(val)
        else:
            media_items.append((PLACEHOLDER.format(n=len(media_items) + 1), Path(val), kind))
            html_parts.append(f"<p>{media_items[-1][0]}</p>")
    full_html = "".join(html_parts)
    ed = page.locator('[contenteditable=true][data-testid="composer"]').first
    for attempt in range(3):
        ed.click()
        page.wait_for_timeout(300)
        page.evaluate(PASTE_JS, full_html)
        page.wait_for_timeout(2500)
        found = sum(1 for b in _blocks(page) if re.search(r"\|XIMGPH_\d+$", b))
        if found == len(media_items) and page.evaluate(TEXT_LEN_JS) > len(full_html) // 8:
            break
        print(f"   整篇粘贴重试 {attempt}: 占位 {found}/{len(media_items)}")
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(500)
    else:
        raise SystemExit("整篇粘贴失败")
    _wait_saved(page)
    for i, (name, path, kind) in enumerate(media_items):
        _insert_media_at(page, name, path, kind)
        print(f"  {i + 1:>3}/{len(media_items)} {kind} {path.name}")
    page.wait_for_timeout(2000)
    return draft_url


def verify(page, media_plan: list) -> list[str]:
    exp = []
    for kind, val in media_plan:
        if kind != "html":
            exp.append("[MEDIA]")
            continue
        for frag in re.findall(r"<(?:h1|h2|p|li|blockquote)>(.*?)</(?:h1|h2|p|li|blockquote)>", val):
            t = H.unescape(re.sub(r"<[^>]+>", "", frag)).replace("• ", "").strip()
            if t:
                exp.append(t)
    got = [g.replace("• ", "").strip() for g in page.evaluate(BLOCKS_JS) if g.strip()]
    diffs = [d for d in difflib.unified_diff(exp, got, lineterm="", n=0)
             if d.startswith(("+", "-")) and not d.startswith(("+++", "---"))]
    # 块类型也要对：09-19 曾出现整段正文被当成标题而文本比对全绿
    want = {"h1": 0, "h2": 0, "blockquote": 0, "li": 0}
    for kind, val in media_plan:
        if kind == "html":
            for tag in want:
                want[tag] += len(re.findall(rf"<{tag}>", val))
    have = page.evaluate("()=>[...document.querySelectorAll('[data-testid=composer] [data-block=true]')].map(e=>e.className.split(' ')[0]).reduce((a,c)=>(a[c]=(a[c]||0)+1,a),{})")
    got_types = {"h1": have.get("longform-header-one", 0), "h2": have.get("longform-header-two", 0),
                 "blockquote": have.get("longform-blockquote", 0),
                 "li": have.get("longform-unordered-list-item", 0) + have.get("longform-ordered-list-item", 0)}
    for tag in want:
        if want[tag] != got_types[tag]:
            diffs.append(f"块类型 {tag}: 计划 {want[tag]} 实际 {got_types[tag]}")
    blocks = _blocks(page)
    bad_empties = 0
    for i, b in enumerate(blocks):
        if b.startswith("media|") or b.split("|", 1)[1].strip():
            continue
        last = i == len(blocks) - 1
        between_media = 0 < i < len(blocks) - 1 and blocks[i - 1].startswith("media|") and blocks[i + 1].startswith("media|")
        if not (last or between_media):
            bad_empties += 1
    if bad_empties:
        diffs.append(f"多余空块 {bad_empties} 个（只允许文末 1 个和两张图之间的间隔）")
    return diffs


def publish(page, caption: str) -> str:
    _wait_saved(page)
    page.get_by_role("button", name="发布").first.click()
    page.wait_for_timeout(3000)
    dlg = page.locator("[role=dialog]").first
    if caption:
        ed = dlg.locator("[contenteditable=true], textarea").first
        ed.click()
        page.wait_for_timeout(300)
        page.keyboard.insert_text(caption)
        page.wait_for_timeout(1200)
    btn = dlg.get_by_role("button", name="发布").first
    if btn.get_attribute("aria-disabled") == "true":
        raise SystemExit("发布按钮被禁用：说明文字超限（上限 256 权重字符，中文按 2 算，约 128 个汉字）")
    btn.click()
    page.wait_for_timeout(10000)
    page.goto("https://x.com/home")
    page.wait_for_timeout(3000)
    handle = page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').inner_text()
    m = re.search(r"@(\w+)", handle)
    page.goto(f"https://x.com/{m.group(1)}")
    page.wait_for_timeout(6000)
    links = page.evaluate("()=>[...document.querySelectorAll('article a[href*=\"/status/\"]')].map(a=>a.href)")
    return next((l for l in links if "/analytics" not in l), "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("article_dir")
    ap.add_argument("--cdp", default="http://127.0.0.1:9333")
    ap.add_argument("--dry-run", action="store_true", help="只打印块序列，不碰浏览器")
    ap.add_argument("--theme", action="store_true", help="把主题曲合成静帧 MP4 插进正文（默认不放，2026-09-19 sandy 定：太重）")
    ap.add_argument("--publish", action="store_true", help="校验通过后直接发布")
    ap.add_argument("--caption-file", help="发布时的帖子说明文字（文件）")
    ap.add_argument("--site-url", default="", help="网页版全文链接，默认按作品编号推")
    ap.add_argument("--draft-url", default="", help="不重建，直接校验并发布这个已有草稿")
    args = ap.parse_args()

    article_dir = Path(args.article_dir).resolve()
    out_dir = article_dir / "dist" / "x"
    parsed = parse_article(article_dir)
    url = args.site_url or site_url(article_dir)

    # 组装最终块序列：封面 → 正文（主题曲视频插在第一个大标题前）→ 来源 → 网站链接
    plan: list = [("cover", str(article_dir / "素材" / "cover.png"))]
    theme = theme_video(article_dir, out_dir) if args.theme else None
    inserted_theme = False
    for kind, val in parsed["blocks"]:
        if kind == "html" and theme and not inserted_theme and "<h1>" in val:
            head, rest = val.split("<h1>", 1)
            if head:
                plan.append(("html", head))
            plan.append(("html", f"<p>🎵 本文主题曲《{H.escape(theme[1])}》，边读边听：</p>"))
            plan.append(("video", str(theme[0])))
            plan.append(("html", "<h1>" + rest))
            inserted_theme = True
        elif kind == "image":
            plan.append(("image", str(pad_portrait(Path(val), out_dir))))
        else:
            plan.append((kind, val))
    tail = ""
    if parsed["sources"]:
        tail += "<h1>信息来源</h1><ul>" + "".join(f"<li>{s}</li>" for s in parsed["sources"]) + "</ul>"
    tail += tail_links(article_dir, parsed["title"], url)
    tail += "<p>叁笙早安 AI · 把最新技术真正用进生活与工作的实测与教程。</p>"
    plan.append(("html", tail))

    if args.dry_run:
        print("TITLE:", parsed["title"])
        for k, v in plan:
            print(k, v[:160] if k in ("html",) else v)
        return 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        pages = [pg for pg in browser.contexts[0].pages if "x.com" in pg.url]
        page = pages[0] if pages else browser.contexts[0].new_page()
        if args.draft_url:
            page.goto(args.draft_url)
            page.wait_for_timeout(7000)
            draft_url = args.draft_url
        else:
            draft_url = build_draft(page, parsed, list(plan))
        diffs = verify(page, plan[1:])
        n_img = page.locator('[data-testid="composer"] img').count()
        n_vid = page.locator('[data-testid="composer"] video').count()
        print(f"draft: {draft_url} | images={n_img} videos={n_vid} | diffs={len(diffs)}")
        for d in diffs[:20]:
            print("   ", d[:120])
        receipt = {"at": datetime.now(timezone.utc).isoformat(), "draft_url": draft_url,
                   "title": parsed["title"], "images": n_img, "videos": n_vid, "diffs": len(diffs),
                   "site_url": url, "post_url": ""}
        if diffs:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            return 2
        if args.publish:
            caption = Path(args.caption_file).read_text(encoding="utf-8").strip() if args.caption_file else ""
            receipt["post_url"] = publish(page, caption)
            print("published:", receipt["post_url"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
