#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已定稿文章搬成 X（Twitter）文章：Markdown → X 编辑器块 → CDP 驱动填入 → 校验 → 发布 → 回读。

背景（2026-09-18 起）：X 文章编辑器只认自己的几种块（标题/副标题/正文/引用/列表/
链接/图片/视频/分割线），公众号那套 HTML 版式贴进去会被剥成纯文本，表格压成一行。所以这里
从 ``定稿.md`` 出发做"内容零改动、结构层级对应"的翻译，不追求长得一样：

- ``##`` → h1（编辑器「标题」），``###`` → h2（「副标题」）；粗体/链接保留；``<mark>`` 转粗体
- 表格 → 「字段：值」无序列表（X 表格粘不进去，自动化填单元格太脆）
- ``>`` 引用与 ``` 代码块 → 一行一个引用块（编辑器会把多段引用合成一行）
- ``---`` → 「插入 → 分割线」
- 图片按原位插入；上传前 EXIF 转正、长边压到 2000、JPEG q85；竖长图（宽高比 < 3:4）
  两侧补边缘色垫成 3:4，否则 X 会居中裁掉上下
- 文末追加「信息来源」（解析 SANSHENG-SOURCES 块）和「继续阅读」（网站全文 / 公众号原文 /
  小宇宙单集，缺哪个不放哪个）
- 主题曲：X 不能上传音频。``--theme`` 才把 ``音乐封面.png`` + 主题曲 MP3 合成静帧 MP4
  插在正文第一个大标题前；默认不放（作者 2026-09-19 定：不必强行合成视频），播客也不放

建稿：整篇一次粘贴（合成 ClipboardEvent，Draft.js 解析 <h1>/<strong>/<blockquote>/<ul>），
媒体与分割线位置先放 ``XIMGPH_n`` / ``XDIVPH_n`` 占位段，再逐个走「插入 → 媒体 / 分割线」
替换。全部落完把编辑器块序列和源文件逐块 diff（文本 + 块类型计数 + 空块），零差异才允许发布。

用法::

    python3 x_article.py <文章目录> [--cdp URL] [--dry-run] [--theme]
                         [--publish [--yes]] [--caption-file 说明.txt]
                         [--draft-url 草稿URL] [--readback]

产物落在 ``<文章目录>/dist/x/``：压缩/垫边图、theme.mp4、preview-*.png、receipt.json
（草稿 URL / 帖子 URL / 图片数 / diff 数 / published_at / caption_sha256）、snapshots.jsonl
（``--readback`` 追加的互动快照，append-only）。Chrome 探不到调试端口时会用 baoyu profile
自动拉起；同一篇同时只允许一个进程（``dist/x/.lock``），总时长超过 40 分钟自杀。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html as H
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE_DEFAULT = Path.home() / "Library/Application Support/baoyu-skills/chrome-profile"
CDP_DEFAULT = "http://127.0.0.1:9333"
MAX_RUNTIME_SECONDS = 40 * 60
CAPTION_WEIGHT_LIMIT = 256
# 裸域名（sanshengai.top / example.com）X 也会自动转成 t.co 链接，和贴 URL 一样压流
DOMAIN_TLDS = r"(?:com|net|org|top|cn|io|ai|me|app|dev|xyz|co|cc|info|site|online|tech|blog|fm|tv|so|link|run)"  # X 发布说明文字：中文/表情按 2 算
IMG_MAX_EDGE = 2000
IMG_JPEG_QUALITY = 85
IMG_MAX_BYTES = 3 * 1024 * 1024

# 界面文案集中在这里，X 换语言或改文案时只改这一处（预留 en 键）
UI = {
    "zh": {
        "title_field": 'textarea[name="文章标题"]',
        "write": "撰写",
        "not_found": "该页面不存在",
        "preview": "预览",
        "publish": "发布",
        "delete": "删除",
        "more": '[aria-label="更多"]',
        "insert_menu": '[aria-label="添加媒体内容"]',
        "menu_media": "媒体",
        "menu_divider": "分割线",
        "processing": "正在处理媒体",
        "saved": "最后保存",
        "back": '[aria-label="返回"], [aria-label="Back"]',
    },
}
T = UI["zh"]

PASTE_JS = """(html)=>{const el=document.activeElement; const dt=new DataTransfer();
dt.setData('text/html',html); dt.setData('text/plain',html.replace(/<[^>]+>/g,''));
el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));}"""
TEXT_LEN_JS = "()=>document.querySelector('[data-testid=composer]').innerText.length"
BLOCKS_JS = ("()=>[...document.querySelectorAll('[data-testid=composer] [data-block=true]')]"
             ".map(e=>{const c=e.className.split(' ')[0]; if(c) return c+'|'+e.innerText.trim();"
             " return (e.querySelector('[role=separator]')?'divider':'media')+'|'+e.innerText.trim();})")
SAVE_STATUS_JS = """()=>{const e=[...document.querySelectorAll('span,div')].find(e=>e.children.length==0 && /最后保存|保存中/.test(e.innerText)); return e? e.innerText:''}"""
LIST_ITEM_RE = re.compile(r"^(- |\d+\. )")
IMG_PH = "XIMGPH_{n}"
DIV_PH = "XDIVPH_{n}"


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
        # 旧格式没有闭合标记：止于下一个 HTML 注释（推荐阅读 / AUDIO-CARD / 任何机器块），
        # 否则会一路吃到音频卡，把「推荐阅读」的三条站内链接当成信息来源（实跑实证）
        m = re.search(r"<!-- SANSHENG-SOURCES -->(.*?)(?=<!--)", md, re.S)
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


def parse_markdown(md: str, article_dir: Path) -> dict:
    """纯函数：定稿 Markdown → {title, description, blocks, sources}。blocks 元素：
    ("html", 片段) / ("image", 绝对路径) / ("divider", "")。"""
    description = fm_title = ""
    if md.startswith("---"):
        head, md = md.split("---", 2)[1], md.split("---", 2)[2]
        for line in head.splitlines():
            if line.strip().startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"').strip("'")
            if line.strip().startswith("title:"):
                fm_title = line.split(":", 1)[1].strip().strip('"').strip("'")
    sources = _sources(md)
    # 音频卡 / 播客卡可能在正文开头（podcast.wechat_embed 时固定在导读后面）：先整块剜掉，再按尾块截止；
    # 以前直接在 AUDIO-CARD-START 处截断，卡在开头的篇目会把整篇截空（09-20 两篇实证）
    md_body = re.sub(r"<!-- (AUDIO|PODCAST)-CARD-START -->.*?<!-- \1-CARD-END -->\n?", "", md, flags=re.S)
    body = re.split(r"<!-- SANSHENG-DEEP-READ -->|<!-- SANSHENG-SOURCES -->|<!-- (?:AUDIO|PODCAST)-CARD-START -->", md_body)[0]
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
            flush()
            blocks.append(("divider", ""))
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
            lang = st[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1
            if lang:  # 保留语言标签行（宝玉做法），读者知道这是段什么
                code.insert(0, f"[{lang}]")
            # 代码里的空行不留：贴进去是一个空引用块，校验会把它算成多余空块（09-20 实证）
            buf.append("".join(f"<blockquote>{H.escape(c)}</blockquote>" for c in code if c.strip()))
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
            while i < len(lines) and LIST_ITEM_RE.match(lines[i].strip()):
                items.append(f"<li>{_inline(LIST_ITEM_RE.sub('', lines[i].strip(), count=1))}</li>")
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

    title = title or fm_title
    return {"title": re.sub(r"^\S+ \| ", "", title), "raw_title": title,
            "description": description, "blocks": blocks, "sources": sources or extra_sources}


X_VARIANT = "定稿.x.md"


def article_source(article_dir: Path) -> Path:
    """X 版适配（删公众号专属段落、标美元、补大陆专有词解释）写在 `定稿.x.md`，存在就优先用它；
    公众号定稿 `定稿.md` 不动。两份的图片都指向同一个 素材/。"""
    x = article_dir / X_VARIANT
    return x if x.is_file() else article_dir / "定稿.md"


def parse_article(article_dir: Path) -> dict:
    src = article_source(article_dir)
    parsed = parse_markdown(src.read_text(encoding="utf-8"), article_dir)
    parsed["source"] = src.name
    return parsed


# ---------------------------------------------------------------- 素材预处理
def prepare_image(src: Path, out_dir: Path) -> Path:
    """EXIF 转正 → 竖长图（宽高比 < 0.75）两侧补边缘中位色垫成 3:4 → 长边压到 2000 →
    JPEG q85（带透明通道才留 PNG）。X 最终都转成 JPEG，PNG 直传只是让「正在处理媒体」更慢。"""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(src))
    has_alpha = im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255
    im = im.convert("RGBA" if has_alpha else "RGB")
    w, h = im.size
    if w / h < 0.75:
        W = round(h * 0.75)
        px = [im.getpixel((x, y))[:3] for x in list(range(0, 4)) + list(range(w - 4, w)) for y in range(0, h, 7)]
        bg = tuple(int(statistics.median(c[k] for c in px)) for k in range(3))
        canvas = Image.new(im.mode, (W, h), bg + ((255,) if has_alpha else ()))
        canvas.paste(im, ((W - w) // 2, 0))
        im = canvas
    im.thumbnail((IMG_MAX_EDGE, IMG_MAX_EDGE), Image.LANCZOS)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = hashlib.sha1(str(src).encode()).hexdigest()[:8] + "-" + src.stem
    if has_alpha:
        dst = out_dir / f"{stem}.png"
        im.save(dst, optimize=True)
    else:
        dst = out_dir / f"{stem}.jpg"
        im.save(dst, "JPEG", quality=IMG_JPEG_QUALITY, optimize=True, progressive=True)
    if dst.stat().st_size > IMG_MAX_BYTES:
        raise SystemExit(f"图片压缩后仍 >3 MB，拒绝上传：{src}")
    return dst


def find_cover(article_dir: Path) -> Path | None:
    """封面查找链：frontmatter cover_image/cover/image → 素材/cover.* → 素材/hero.*。"""
    md = (article_dir / "定稿.md").read_text(encoding="utf-8") if (article_dir / "定稿.md").is_file() else ""
    if md.startswith("---"):
        for line in md.split("---", 2)[1].splitlines():
            m = re.match(r"\s*(cover_image|cover|image):\s*(.+)", line)
            if m:
                cand = (article_dir / m.group(2).strip().strip('"').strip("'")).resolve()
                if cand.is_file():
                    return cand
    for name in ("cover", "hero"):
        for ext in ("png", "jpg", "jpeg", "webp"):
            cand = article_dir / "素材" / f"{name}.{ext}"
            if cand.is_file():
                return cand
    return None


def theme_video(article_dir: Path, out_dir: Path) -> tuple[Path, str] | None:
    """主题曲 MP3 + 音乐封面 → 静帧 MP4（X 不收音频）。返回 (mp4, 歌名)。"""
    try:
        from article_paths import is_podcast_audio_name, process_file, resolve_cover
    except ImportError:  # pragma: no cover
        from .article_paths import is_podcast_audio_name, process_file, resolve_cover

    manifest = process_file(article_dir, "_music-manifest.json")
    cover = resolve_cover(article_dir, kind="theme")
    if cover is None:
        return None
    if not manifest.is_file():  # 2026-09 之前的篇目没有 manifest：根目录唯一一个非播客 MP3 就是主题曲
        mp3s = [f for f in article_dir.glob("*.mp3") if not is_podcast_audio_name(f.name)]
        if len(mp3s) != 1:
            return None
        return _render_theme(mp3s[0], cover, out_dir), mp3s[0].stem
    theme = json.loads(manifest.read_text(encoding="utf-8")).get("theme") or {}
    mp3 = article_dir / str((theme.get("playback") or {}).get("path") or "")
    if not mp3.is_file():
        return None
    return _render_theme(mp3, cover, out_dir), str(theme.get("title") or mp3.stem)


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


# ---------------------------------------------------------------- 渠道配置（brand.yaml distribute.channels.x）
def x_config(article_dir: Path) -> dict:
    """网站链接模板 / 播客节目页 / 署名行 / CDP 端口 / Chrome profile 都是私有但非密的品牌值，
    放 profile 而不是写死在脚本里；未配置时全部为空 = 文末不放对应项。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import profile_config as pc

        pc.bind_workspace(article_dir)
        cfg = dict(pc.distribute_channel("x") or {})
    except Exception:
        cfg = {}
    cfg.setdefault("article_url_template", "")
    cfg.setdefault("podcast_show_url", "")
    cfg.setdefault("podcast_episode_prefix", "深聊 | ")
    cfg.setdefault("tail_line", "")
    cfg.setdefault("cdp", CDP_DEFAULT)
    cfg["chrome_profile"] = cfg.get("chrome_profile") or str(CHROME_PROFILE_DEFAULT)
    return cfg


# ---------------------------------------------------------------- 链接
def _process_file(article_dir: Path, name: str) -> Path:
    try:
        from article_paths import process_file
    except ImportError:  # pragma: no cover
        from .article_paths import process_file
    return process_file(article_dir, name)


def article_code(article_dir: Path) -> str:
    for name in ("_website-sync-receipt.json", "_publish-receipt.json"):
        f = _process_file(article_dir, name)
        if f.is_file():
            m = re.search(r'"code":\s*"([A-Z]+-\d+)"', f.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
    return ""


def site_url(article_dir: Path, template: str) -> str:
    code = article_code(article_dir)
    return template.replace("{code}", code.lower()) if (template and code) else ""


def wechat_url(article_dir: Path) -> str:
    f = _process_file(article_dir, "_website-sync-receipt.json")
    if f.is_file():
        m = re.search(r'"wechat_url":\s*"(https://mp\.weixin\.qq\.com/s/[^"]+)"', f.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def xiaoyuzhou_url(article_dir: Path, title: str, show_url: str, prefix: str = "深聊 | ") -> str:
    """本篇有播客（dist/podcast/audio.mp3）且配置了小宇宙节目页时，到节目页按「前缀 + 标题」匹配单集；
    匹配不到（页面只列最近 15 集）就退回节目主页。抓不到网络时返回节目主页，不阻塞发布。"""
    if not show_url or not (article_dir / "dist" / "podcast" / "audio.mp3").is_file():
        return ""
    try:
        req = urllib.request.Request(show_url, headers={"User-Agent": "Mozilla/5.0"})
        html_text = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S)
        episodes = json.loads(m.group(1))["props"]["pageProps"]["podcast"].get("episodes") or []
        key = (prefix + title)[:16]
        for ep in episodes:
            if key and key in str(ep.get("title") or ""):
                return f"https://www.xiaoyuzhoufm.com/episode/{ep['eid']}"
        return show_url
    except Exception:
        return show_url


def tail_links(article_dir: Path, title: str, site: str, cfg: dict) -> str:
    """文末「继续阅读」：网站全文 / 公众号原文 / 小宇宙播客，缺哪个不放哪个。链接放正文里不放主帖。"""
    items = []
    if site:
        items.append(f'<li>网页版全文（含来源链接）：<a href="{site}">{site}</a></li>')
    wx = wechat_url(article_dir)
    if wx:
        items.append(f'<li>公众号原文：<a href="{wx}">{wx}</a></li>')
    xyz = xiaoyuzhou_url(article_dir, title, cfg.get("podcast_show_url", ""), cfg.get("podcast_episode_prefix", "深聊 | "))
    if xyz:
        items.append(f'<li>播客版（小宇宙）：<a href="{xyz}">{xyz}</a></li>')
    return "<h1>继续阅读</h1><ul>" + "".join(items) + "</ul>" if items else ""


# ---------------------------------------------------------------- 说明文字 / 校验（纯函数，可测）
def caption_weight(text: str) -> int:
    """X 发布说明文字的权重字数：CJK、全角标点、表情按 2，其余按 1。"""
    return sum(2 if (ord(c) > 0x2E80) else 1 for c in text)


def check_caption(text: str) -> list[str]:
    """本地预检：超限、带 URL、hashtag ≥2、互动诱饵。返回问题列表（空 = 通过）。"""
    problems = []
    w = caption_weight(text)
    if w > CAPTION_WEIGHT_LIMIT:
        problems.append(f"说明文字 {w} 权重字符，超过上限 {CAPTION_WEIGHT_LIMIT}（中文按 2 算，约 128 个汉字）")
    if re.search(r"https?://|www\.", text) or re.search(r"(?<![\w.])[\w-]+(\.[\w-]+)*\." + DOMAIN_TLDS + r"(?![\w.])", text, re.I):
        problems.append("说明文字里有 URL 或裸域名（X 会自动转成链接）：外链压流，链接放文章末尾或回复")
    if len(re.findall(r"(?<!\S)#\S+", text)) >= 2:
        problems.append("hashtag ≥2 会被降权")
    if re.search(r"(点赞|转发|关注|收藏|评论区见|你怎么看|欢迎讨论)", text):
        problems.append("互动诱饵词（点赞/转发/关注/你怎么看）会被降权，结尾要落地")
    return problems


def expected_blocks(media_plan: list) -> tuple[list[str], dict]:
    """把计划展开成期望的块文本序列和块类型计数。媒体/分割线统一记 [MEDIA]。"""
    exp, want = [], {"h1": 0, "h2": 0, "blockquote": 0, "li": 0}
    for kind, val in media_plan:
        if kind != "html":
            exp.append("[MEDIA]")
            continue
        for frag in re.findall(r"<(?:h1|h2|p|li|blockquote)>(.*?)</(?:h1|h2|p|li|blockquote)>", val):
            t = H.unescape(re.sub(r"<[^>]+>", "", frag)).replace("• ", "").strip()
            if t:
                exp.append(t)
        for tag in want:
            want[tag] += len(re.findall(rf"<{tag}>", val))
    return exp, want


def diff_blocks(media_plan: list, got_blocks: list[str]) -> list[str]:
    """got_blocks 每项形如 'longform-unstyled|文本' / 'media|…' / 'divider|'。返回差异列表（空 = 通过）。"""
    exp, want = expected_blocks(media_plan)
    got = []
    for b in got_blocks:
        cls, text = b.split("|", 1)
        if cls in ("media", "divider"):
            got.append("[MEDIA]")
        elif text.strip():
            got.append(text.replace("• ", "").strip())
    diffs = [d for d in difflib.unified_diff(exp, got, lineterm="", n=0)
             if d.startswith(("+", "-")) and not d.startswith(("+++", "---"))]
    have: dict[str, int] = {}
    for b in got_blocks:
        cls = b.split("|", 1)[0]
        have[cls] = have.get(cls, 0) + 1
    got_types = {"h1": have.get("longform-header-one", 0), "h2": have.get("longform-header-two", 0),
                 "blockquote": have.get("longform-blockquote", 0),
                 "li": have.get("longform-unordered-list-item", 0) + have.get("longform-ordered-list-item", 0)}
    for tag in want:  # 只比文本抓不住"正文被当成标题"（09-19 实证）
        if want[tag] != got_types[tag]:
            diffs.append(f"块类型 {tag}: 计划 {want[tag]} 实际 {got_types[tag]}")
    bad_empties = 0
    for i, b in enumerate(got_blocks):
        cls, text = b.split("|", 1)
        if cls in ("media", "divider") or text.strip():
            continue
        last = i == len(got_blocks) - 1
        between_atomic = 0 < i < len(got_blocks) - 1 and \
            got_blocks[i - 1].split("|", 1)[0] in ("media", "divider") and got_blocks[i + 1].split("|", 1)[0] in ("media", "divider")
        if not (last or between_atomic):
            bad_empties += 1
    if bad_empties:
        diffs.append(f"多余空块 {bad_empties} 个（只允许文末 1 个和两个媒体块之间的间隔）")
    if any(re.search(r"\|X(IMG|DIV)PH_\d+", b) for b in got_blocks):
        diffs.append("编辑器里还有占位符残留")
    return diffs


# ---------------------------------------------------------------- Chrome / 锁
def ensure_cdp(cdp: str, chrome_profile: str = "") -> None:
    """探调试端口；探不到就用配置的 Chrome profile 拉起（子进程脱离本进程，命令结束不会被杀）。"""
    def alive() -> bool:
        try:
            urllib.request.urlopen(cdp + "/json/version", timeout=3).read()
            return True
        except Exception:
            return False

    if alive():
        return
    port = re.search(r":(\d+)$", cdp).group(1)
    subprocess.Popen(
        [CHROME_BIN, f"--remote-debugging-port={port}", f"--user-data-dir={chrome_profile or CHROME_PROFILE_DEFAULT}",
         "--no-first-run",
         # Chrome 的 Gemini 按钮按国家白名单显示，国家码来自 Finch 种子；这个 profile 拿到的种子国家为空时
         # 按钮会消失（09-19 实证），显式指定国家。该开关不持久化，每次拉起都要带。
         "--variations-override-country=us",
         "https://x.com/compose/articles"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    for _ in range(40):
        time.sleep(0.5)
        if alive():
            time.sleep(3)
            return
    raise SystemExit(f"拉起 Chrome 后 {cdp} 仍不通")


class ArticleLock:
    """同一篇同时只允许一个进程驱动编辑器；锁文件记 pid，pid 不在了视作过期。"""

    def __init__(self, out_dir: Path):
        self.path = out_dir / ".lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            try:
                pid = int(self.path.read_text().strip() or 0)
                os.kill(pid, 0)
                raise SystemExit(f"另一个进程（pid {pid}）正在处理这篇，退出")
            except (ValueError, ProcessLookupError, PermissionError):
                pass
        self.path.write_text(str(os.getpid()))

        def _timeout(*_):
            raise SystemExit("超过 40 分钟，自杀")

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(MAX_RUNTIME_SECONDS)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: sys.exit(130))
        return self

    def __exit__(self, *exc):
        signal.alarm(0)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- 编辑器驱动
def _wait_media(page, limit_s: int = 900):
    for _ in range(limit_s * 2):
        page.wait_for_timeout(500)
        if page.get_by_text(T["processing"]).count() == 0:
            return
    raise SystemExit("媒体处理超时")


def _wait_saved(page, limit_s: int = 30):
    """改动后状态栏会先清空（约 3 秒），自动保存落地才回到「刚刚最后保存」。媒体插入前后和发布前
    必须等到：编辑器处理完媒体重渲染时会回滚到上一份保存快照，把没保存的段落吞掉（09-19 实证）。"""
    for _ in range(3):
        if not (page.evaluate(SAVE_STATUS_JS) or ""):
            break
        page.wait_for_timeout(500)
    for _ in range(limit_s * 2):
        if T["saved"] in (page.evaluate(SAVE_STATUS_JS) or ""):
            return
        page.wait_for_timeout(500)


def _blocks(page) -> list[str]:
    return page.evaluate(BLOCKS_JS)


def _wait_blocks_stable(page, at_least: int, limit_s: int = 20) -> int:
    """粘贴后块数连续两次相同且 ≥ at_least 才算渲染完（乔木做法），不用固定 sleep。"""
    prev = -1
    for _ in range(limit_s * 2):
        page.wait_for_timeout(500)
        n = len(_blocks(page))
        if n == prev and n >= at_least:
            return n
        prev = n
    return prev


def _placeholder_block(page, name: str):
    return page.locator('[data-testid="composer"] [data-block="true"]', has_text=re.compile(rf"^{name}$")).first


def _insert_at(page, name: str, kind: str, path: Path | None):
    """光标放在占位块末尾，走「插入 → 媒体 / 分割线」；新块落在占位块正下方。然后逐字退格删掉
    占位文字，若占位块上方是文字块再退格一次并入上一块；上方是媒体块时退格无效，留一个空块当间隔。"""
    if kind == "image":
        sel = '[data-testid="composer"] img'
    elif kind == "video":
        sel = '[data-testid="composer"] video'
    else:
        sel = '[data-testid="composer"] [role="separator"]'
    _wait_saved(page)
    blk = _placeholder_block(page, name)
    blk.scroll_into_view_if_needed()
    blk.click()
    page.keyboard.press("End")
    page.wait_for_timeout(200)
    before = page.locator(sel).count()
    page.locator(T["insert_menu"]).first.click()
    page.wait_for_timeout(700)
    if kind == "divider":
        page.locator("[role=menuitem]", has_text=T["menu_divider"]).first.click()
    else:
        page.locator("[role=menuitem]", has_text=T["menu_media"]).first.click()
        page.wait_for_selector("input[type=file][multiple]", state="attached", timeout=8000)
        page.locator("input[type=file][multiple]").first.set_input_files(str(path))
    for _ in range(120):
        page.wait_for_timeout(500)
        if page.locator(sel).count() > before:
            break
    else:
        raise SystemExit(f"{name} 插入后没出现：{kind} {path}")
    if kind != "divider":
        _wait_media(page)
        page.wait_for_timeout(4000)  # 媒体落地后编辑器还会重渲染一次
    _wait_saved(page)
    blk = _placeholder_block(page, name)
    if not blk.count():
        raise SystemExit(f"{name} 占位块在插入后消失")
    blocks_before = _blocks(page)
    idx = next(i for i, b in enumerate(blocks_before) if b.endswith("|" + name))
    prev_is_text = idx > 0 and blocks_before[idx - 1].split("|", 1)[0] not in ("media", "divider")
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
        raise SystemExit(f"{name} 清理占位时块数变了")


def _delete_same_title_drafts(page, title: str):
    for _ in range(5):  # 删掉本篇上次没跑完的同名草稿，别的草稿不动
        cell = page.locator('[data-testid="cellInnerDiv"]', has_text=title).first
        if not cell.count():
            break
        cell.locator(T["more"]).first.click()
        page.wait_for_timeout(700)
        page.locator("[role=menuitem]", has_text=T["delete"]).first.click()
        page.wait_for_timeout(800)
        page.locator('[data-testid="confirmationSheetConfirm"]').click()
        page.wait_for_timeout(1500)


def build_draft(page, parsed: dict, plan: list, cover: Path) -> str:
    """整篇一次粘贴（块样式最保真），媒体/分割线位置先放占位段，再逐个替换。"""
    page.goto("https://x.com/compose/articles")
    page.wait_for_timeout(4000)
    if T["not_found"] in page.inner_text("body"):
        raise SystemExit("文章列表页 404：账号当前没有 Articles 权限（Premium+ 失效或在审查中）。"
                         "先在 X 设置 → Premium 与 Grok 应用里核对订阅和账号绑定，再重跑。")
    _delete_same_title_drafts(page, parsed["title"])
    page.get_by_text(T["write"], exact=True).first.click()
    page.wait_for_timeout(6000)
    draft_url = page.url
    page.locator(T["title_field"]).click()
    page.keyboard.type(parsed["title"], delay=8)
    page.wait_for_timeout(800)
    page.locator('input[data-testid="fileInput"]:not([multiple])').first.set_input_files(str(cover))
    page.wait_for_timeout(3000)
    ap = page.locator('[data-testid="applyButton"]')
    if ap.count():
        ap.click()
        page.wait_for_timeout(2000)
    _wait_media(page)

    html_parts, items = [], []
    n_img = n_div = 0
    for kind, val in plan:
        if kind == "html":
            html_parts.append(val)
        elif kind == "divider":
            n_div += 1
            items.append((DIV_PH.format(n=n_div), "divider", None))
            html_parts.append(f"<p>{items[-1][0]}</p>")
        else:
            n_img += 1
            items.append((IMG_PH.format(n=n_img), kind, Path(val)))
            html_parts.append(f"<p>{items[-1][0]}</p>")
    full_html = "".join(html_parts)
    exp_blocks, _ = expected_blocks(plan)
    ed = page.locator('[contenteditable=true][data-testid="composer"]').first
    for attempt in range(3):
        ed.click()
        page.wait_for_timeout(300)
        page.evaluate(PASTE_JS, full_html)
        _wait_blocks_stable(page, at_least=int(len(exp_blocks) * 0.9))
        found = sum(1 for b in _blocks(page) if re.search(r"\|X(IMG|DIV)PH_\d+$", b))
        if found == len(items) and page.evaluate(TEXT_LEN_JS) > len(full_html) // 8:
            break
        print(f"   整篇粘贴重试 {attempt}: 占位 {found}/{len(items)}")
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(500)
    else:
        raise SystemExit("整篇粘贴失败")
    _wait_saved(page)
    for i, (name, kind, path) in enumerate(items):
        _insert_at(page, name, kind, path)
        print(f"  {i + 1:>3}/{len(items)} {kind} {path.name if path else ''}")
    page.wait_for_timeout(2000)
    return draft_url


def build_draft_with_retry(page, parsed: dict, plan: list, cover: Path, tries: int = 3) -> str:
    """占位块在媒体落地后消失、插入超时这类编辑器抽风（09-20 实证：同一篇连着两次失败、第三次全过），
    整篇重建比人工介入便宜；重建前会删同名旧草稿。只对这类瞬态错误重试，其它错误照常抛。"""
    transient = ("占位块在插入后消失", "插入后没出现", "没删干净", "块数变了", "Timeout")
    last = None
    for attempt in range(1, tries + 1):
        try:
            return build_draft(page, parsed, plan, cover)
        except (SystemExit, Exception) as e:  # noqa: BLE001 - 只放行瞬态错误
            msg = str(e)
            if not any(k in msg for k in transient) or attempt == tries:
                raise
            last = msg
            print(f"  建稿失败（{msg[:60]}），第 {attempt + 1}/{tries} 次重建…")
            page.wait_for_timeout(5000)
    raise SystemExit(last or "建稿失败")


def verify(page, plan: list) -> list[str]:
    return diff_blocks(plan, _blocks(page))


def preview_shots(page, out_dir: Path) -> list[str]:
    """校验通过后开预览截头/中/尾三张，留给人工复核。"""
    _wait_saved(page)
    page.get_by_text(T["preview"], exact=True).first.click()
    page.wait_for_timeout(4000)
    shots = []
    for tag, dy in (("top", 0), ("mid", 6000), ("end", 100000)):
        if dy:
            page.mouse.wheel(0, dy)
            page.wait_for_timeout(1200)
        f = out_dir / f"preview-{tag}.png"
        page.screenshot(path=str(f))
        shots.append(str(f))
    page.locator(T["back"]).first.click()
    page.wait_for_timeout(2000)
    return shots


def publish(page, caption: str, title: str = "") -> str:
    _wait_saved(page)
    page.get_by_role("button", name=T["publish"]).first.click()
    page.wait_for_timeout(3000)
    dlg = page.locator("[role=dialog]").first
    if caption:
        ed = dlg.locator("[contenteditable=true], textarea").first
        ed.click()
        page.wait_for_timeout(300)
        page.keyboard.insert_text(caption)
        page.wait_for_timeout(1200)
    btn = dlg.get_by_role("button", name=T["publish"]).first
    if btn.get_attribute("aria-disabled") == "true":
        raise SystemExit("发布按钮被禁用：说明文字超限或内容不合规")
    btn.click()
    # 先等跳转 / 成功提示里的链接；拿不到再退回抓主页首条
    for _ in range(30):
        page.wait_for_timeout(500)
        if "/status/" in page.url:
            return page.url.split("?")[0]
        link = page.locator('a[href*="/status/"]').first
        if link.count():
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://x.com" + href
            if re.search(r"/status/\d+$", href):
                return href
    page.goto("https://x.com/home")
    page.wait_for_timeout(3000)
    handle = page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').inner_text()
    m = re.search(r"@(\w+)", handle)
    page.goto(f"https://x.com/{m.group(1)}")
    page.wait_for_timeout(6000)
    first = page.locator("article").first
    text = first.inner_text() if first.count() else ""
    if not post_matches(text, caption, title):
        raise SystemExit("发布未确认：主页首条帖子和本次说明文字 / 标题对不上，不能把别人的帖当成本篇。"
                         "去 X 上核对是否真的发出（Premium+ 失效时发布按钮会静默失败）。")
    links = first.evaluate("a=>[...a.querySelectorAll('a[href*=\"/status/\"]')].map(x=>x.href)")
    return next((l for l in links if "/analytics" not in l), "")


def post_matches(post_text: str, caption: str, title: str) -> bool:
    """回退抓主页首条时的防误报：帖子文本里得有本次说明文字的开头或文章标题。"""
    norm = lambda t: re.sub(r"\s+", "", t or "")
    pt = norm(post_text)
    head = norm(caption)[:20]
    return bool(pt) and ((bool(head) and head in pt) or (bool(norm(title)) and norm(title)[:20] in pt))


def account_handle(page) -> str:
    try:
        text = page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').inner_text()
        m = re.search(r"@(\w+)", text)
        return "@" + m.group(1) if m else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- 回读快照
MATURITY_STEPS = ((6, "early"), (24, "day1"), (72, "day3"), (168, "week1"), (720, "month1"))


def maturity(hours: float) -> str:
    for limit, label in MATURITY_STEPS:
        if hours < limit:
            return label
    return "plateau"


def _metric(page, testid: str) -> int | None:
    """帖子页四个按钮的 aria-label 形如「3 次点赞」；拿不到记 null，不写 0。"""
    el = page.locator(f'article [data-testid="{testid}"]').first
    if not el.count():
        return None
    label = el.get_attribute("aria-label") or ""
    m = re.search(r"(\d[\d,]*)", label)
    return int(m.group(1).replace(",", "")) if m else 0


def readback(page, receipt: dict, out_dir: Path) -> dict:
    url = receipt.get("post_url") or ""
    if not url:
        raise SystemExit("receipt 里没有 post_url，先发布")
    page.goto(url)
    page.wait_for_timeout(7000)
    published_at = receipt.get("published_at") or receipt.get("at")
    hours = None
    if published_at:
        try:
            hours = round((datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600, 1)
        except ValueError:
            hours = None
    snap = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "post_url": url,
        "hours_since_publish": hours,
        "maturity": maturity(hours) if hours is not None else None,
        "replies": _metric(page, "reply"),
        "reposts": _metric(page, "retweet"),
        "likes": _metric(page, "like"),
        "bookmarks": _metric(page, "bookmark"),
        "article_card": bool(page.locator('article a[href*="/article/"], article [data-testid="card.wrapper"]').count()),
        "qualifiers": "exact",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "snapshots.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return snap


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("article_dir")
    ap.add_argument("--cdp", default="", help="Chrome 调试端口，默认取 profile distribute.channels.x.cdp")
    ap.add_argument("--dry-run", action="store_true", help="只打印块序列，不碰浏览器")
    ap.add_argument("--theme", action="store_true", help="把主题曲合成静帧 MP4 插进正文（默认不放）")
    ap.add_argument("--publish", action="store_true", help="校验通过后发布（需 --yes 或交互确认）")
    ap.add_argument("--yes", action="store_true", help="跳过发布确认卡（授权只在本次命令有效）")
    ap.add_argument("--caption-file", help="发布时的帖子说明文字（文件）")
    ap.add_argument("--site-url", default="", help="网页版全文链接，默认按作品编号推")
    ap.add_argument("--draft-url", default="", help="不重建，直接校验并发布这个已有草稿")
    ap.add_argument("--readback", action="store_true", help="只回读 receipt 里帖子的互动数据，追加到 snapshots.jsonl")
    args = ap.parse_args()

    article_dir = Path(args.article_dir).resolve()
    out_dir = article_dir / "dist" / "x"
    receipt_path = out_dir / "receipt.json"
    cfg = x_config(article_dir)
    cdp = args.cdp or cfg["cdp"]

    if args.readback:
        if not receipt_path.is_file():
            raise SystemExit("没有 receipt.json")
        from playwright.sync_api import sync_playwright

        ensure_cdp(cdp, cfg["chrome_profile"])
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp)
            pages = [pg for pg in browser.contexts[0].pages if "x.com" in pg.url]
            page = pages[0] if pages else browser.contexts[0].new_page()
            snap = readback(page, json.loads(receipt_path.read_text(encoding="utf-8")), out_dir)
        print(json.dumps(snap, ensure_ascii=False))
        return 0

    parsed = parse_article(article_dir)
    url = args.site_url or site_url(article_dir, cfg["article_url_template"])
    cover = find_cover(article_dir)
    if not cover:
        raise SystemExit("找不到封面：frontmatter cover / 素材/cover.* / 素材/hero.*")

    plan: list = []
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
            plan.append(("image", val if args.dry_run else str(prepare_image(Path(val), out_dir))))
        else:
            plan.append((kind, val))
    tail = ""
    if parsed["sources"]:
        tail += "<h1>信息来源</h1><ul>" + "".join(f"<li>{s}</li>" for s in parsed["sources"]) + "</ul>"
    tail += tail_links(article_dir, parsed["title"], url, cfg)
    if cfg["tail_line"]:
        tail += f"<p>{H.escape(cfg['tail_line'], quote=False)}</p>"
    if tail:
        plan.append(("html", tail))

    caption = Path(args.caption_file).read_text(encoding="utf-8").strip() if args.caption_file else ""
    caption_problems = check_caption(caption) if caption else []
    if args.publish and caption_problems:
        for pr in caption_problems:
            print("❌", pr)
        return 2

    if args.dry_run:
        print("TITLE:", parsed["title"], "| source:", parsed["source"], "| cover:", cover)
        for k, v in plan:
            print(k, v[:160] if k == "html" else v)
        if caption:
            print("CAPTION weight:", caption_weight(caption))
        return 0

    from playwright.sync_api import sync_playwright

    ensure_cdp(cdp, cfg["chrome_profile"])
    with ArticleLock(out_dir), sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp)
        pages = [pg for pg in browser.contexts[0].pages if "x.com" in pg.url]
        page = pages[0] if pages else browser.contexts[0].new_page()
        cover_ready = prepare_image(cover, out_dir)
        if args.draft_url:
            page.goto(args.draft_url)
            page.wait_for_timeout(7000)
            draft_url = args.draft_url
        else:
            draft_url = build_draft_with_retry(page, parsed, plan, cover_ready)
        diffs = verify(page, plan)
        n_img = page.locator('[data-testid="composer"] img').count()
        n_vid = page.locator('[data-testid="composer"] video').count()
        print(f"draft: {draft_url} | images={n_img} videos={n_vid} | diffs={len(diffs)}")
        for d in diffs[:20]:
            print("   ", d[:120])
        receipt = {"at": datetime.now(timezone.utc).isoformat(), "draft_url": draft_url,
                   "title": parsed["title"], "source": parsed["source"],
                   "images": n_img, "videos": n_vid, "diffs": len(diffs),
                   "site_url": url, "post_url": "", "account": account_handle(page)}
        out_dir.mkdir(parents=True, exist_ok=True)
        if diffs:
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            return 2
        receipt["preview"] = preview_shots(page, out_dir)
        if args.publish:
            print("\n==== 发布确认 ====")
            print(f"账号：{receipt['account']}\n标题：{parsed['title']}\n说明：{caption or '（无）'}\n"
                  f"图片：{n_img}  链接：{url or '-'} / 公众号 {'有' if wechat_url(article_dir) else '无'}\n预览：{receipt['preview'][0]}")
            if not args.yes:
                ans = input("确认发布？输入 yes：").strip().lower() if sys.stdin.isatty() else ""
                if ans != "yes":
                    print("未发布（加 --yes 可跳过确认）")
                    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
                    return 3
            receipt["post_url"] = publish(page, caption, parsed["title"])
            receipt["published_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            receipt["caption_sha256"] = hashlib.sha256(caption.encode("utf-8")).hexdigest() if caption else ""
            print("published:", receipt["post_url"])
            print("⏰ 发后 30–60 分钟守在评论区：30 分钟内 3 条以上实质回复触发二次分发；30 分钟内别编辑。")
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
