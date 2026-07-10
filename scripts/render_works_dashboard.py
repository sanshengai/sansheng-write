#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_works_dashboard.py — 把 works.yaml 渲染成自包含的 HTML 作品看板（只读视图）。

不回写数据，权威源始终是 works.yaml。
输出 <数据目录>/works-dashboard.html，封面相对路径解析到 <数据目录>/ 下，浏览器/手机直接打开可看。
"""
import os
import sys
import html as _html

try:  # Windows GBK 控制台兜底，避免 print emoji 抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(__file__))
from works_registry import load_works, WORKS_FILE

try:
    from profile_config import brand as _brand, colors as _colors
    _PRIMARY = _colors().get("primary") or "#2F6F8F"
    _BRAND_NAME = _brand().get("name") or "作品库"
except Exception:
    _PRIMARY, _BRAND_NAME = "#2F6F8F", "作品库"

DASHBOARD_FILE = WORKS_FILE.parent / "works-dashboard.html"

CATEGORY_CN = {"AIT": "实测", "TUT": "教程", "OBS": "观察", "ROB": "硬件", "KID": "育儿", "ESS": "随笔"}
CATEGORY_COLOR = {"AIT": _PRIMARY, "TUT": "#2563eb", "OBS": "#b45309",
                  "ROB": "#7c3aed", "KID": "#db2777", "ESS": "#475569"}
GREEN = _PRIMARY  # 看板主强调色 = profile 主题色（默认中性 slate）
CATS = ["AIT", "TUT", "OBS", "ROB", "KID", "ESS"]


def cover_src(cover):
    """作品库封面路径(<数据目录>/...) → 相对看板(<数据目录>/works-dashboard.html)的路径。"""
    if not cover:
        return ""
    prefix = "<数据目录>/"
    return cover[len(prefix):] if cover.startswith(prefix) else cover


def _card(w):
    cat = w.get("category") or ""
    cn = CATEGORY_CN.get(cat, cat or "未分类")
    color = CATEGORY_COLOR.get(cat, "#475569")
    code = w.get("code") or "草稿"
    title = _html.escape(w.get("title") or "(无标题)")
    date = w.get("date") or "未发布"
    src = cover_src(w.get("cover") or "")
    if src:
        media = f'<img loading="lazy" src="{_html.escape(src)}" alt="">'
    else:
        media = f'<div class="ph" style="background:{color}">{_html.escape(cn)}</div>'
    chips = ['<span class="chip pub">已发</span>'] if w.get("status") == "published" \
        else ['<span class="chip draft">草稿</span>']
    chips.append('<span class="chip">📄文</span>')
    if (w.get("video") or {}).get("status") in ("scripted", "published"):
        chips.append('<span class="chip vid">🎬视</span>')
    tags = "".join(f'<span class="tag">{_html.escape(t)}</span>' for t in (w.get("tags") or []))
    wurl = w.get("wechat_url") or ""
    link = f'<a class="link" href="{_html.escape(wurl)}" target="_blank">公众号 ↗</a>' if wurl else ""
    seq = w.get("seq")
    seq_label = f'<span class="seq">{seq}</span>' if seq is not None else ""
    return f'''<article class="card" data-category="{_html.escape(cat)}" data-status="{w.get('status','')}">
  <div class="media">{media}<span class="badge" style="background:{color}">{_html.escape(code)}</span></div>
  <div class="body">
    <h3>{seq_label}{title}</h3>
    <div class="meta"><span>{_html.escape(cn)}</span><span>{_html.escape(date)}</span></div>
    <div class="chips">{''.join(chips)}</div>
    <div class="tags">{tags}</div>
    {link}
  </div>
</article>'''


def build_html(works):
    pub = sorted([w for w in works if w.get("date")], key=lambda w: w["date"], reverse=True)
    draft = [w for w in works if not w.get("date")]
    ordered = pub + draft
    total = len(works)
    npub = sum(1 for w in works if w.get("status") == "published")
    nvid = sum(1 for w in works if (w.get("video") or {}).get("status") in ("scripted", "published"))
    cat_counts = {c: sum(1 for w in works if w.get("category") == c) for c in CATS}
    filters = '<button class="fbtn active" data-f="all">全部</button>' + "".join(
        f'<button class="fbtn" data-f="{c}">{CATEGORY_CN[c]} {cat_counts[c]}</button>' for c in CATS
    )
    cards = "\n".join(_card(w) for w in ordered)
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_BRAND_NAME}作品库</title>
<style>
:root{{--green:{GREEN}}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f7;color:#1c1c1c}}
header{{background:#fff;border-bottom:3px solid var(--green);padding:18px 24px;position:sticky;top:0;z-index:10}}
header h1{{margin:0 0 8px;font-size:20px}}
header h1 .g{{color:var(--green)}}
.stats{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
.stats .pill{{background:#eef2f4;color:var(--green);font-size:13px;padding:3px 10px;border-radius:20px;font-weight:600}}
.filters{{display:flex;gap:6px;flex-wrap:wrap}}
.fbtn{{border:1px solid #ddd;background:#fff;border-radius:20px;padding:5px 12px;font-size:13px;cursor:pointer;color:#444}}
.fbtn.active{{background:var(--green);color:#fff;border-color:var(--green)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;padding:20px 24px}}
.card{{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);display:flex;flex-direction:column}}
.media{{position:relative;aspect-ratio:16/10;background:#eee}}
.media img{{width:100%;height:100%;object-fit:cover;display:block}}
.media .ph{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;font-weight:700;opacity:.9}}
.badge{{position:absolute;left:8px;top:8px;color:#fff;font-size:12px;font-weight:700;padding:2px 8px;border-radius:6px;letter-spacing:.3px}}
.body{{padding:12px 14px;display:flex;flex-direction:column;gap:8px;flex:1}}
.body h3{{margin:0;font-size:15px;line-height:1.5}}
.seq{{display:inline-block;background:#eef2f4;color:var(--green);font-weight:700;font-size:12px;padding:0 6px;border-radius:5px;margin-right:6px;vertical-align:1px}}
.meta{{display:flex;justify-content:space-between;color:#888;font-size:12px}}
.chips{{display:flex;gap:5px;flex-wrap:wrap}}
.chip{{font-size:11px;padding:1px 7px;border-radius:5px;background:#f0f0f0;color:#555}}
.chip.pub{{background:#e6f0f4;color:var(--green)}}
.chip.draft{{background:#fdeaea;color:#c0392b}}
.chip.vid{{background:#efe7fb;color:#7c3aed}}
.tags{{display:flex;gap:5px;flex-wrap:wrap}}
.tag{{font-size:11px;color:#999}}
.tag::before{{content:"#"}}
.link{{margin-top:auto;font-size:13px;color:var(--green);text-decoration:none;font-weight:600}}
footer{{text-align:center;color:#aaa;font-size:12px;padding:16px}}
</style></head><body>
<header>
  <h1>{_BRAND_NAME}<span class="g">作品库</span></h1>
  <div class="stats">
    <span class="pill">总数 {total}</span>
    <span class="pill">已发布 {npub}</span>
    <span class="pill">有视频 {nvid}</span>
  </div>
  <div class="filters">{filters}</div>
</header>
<main class="grid" id="grid">
{cards}
</main>
<footer>只读视图 · 由 works.yaml 渲染生成 · 改数据请改 YAML</footer>
<script>
const btns=document.querySelectorAll('.fbtn');
btns.forEach(b=>b.addEventListener('click',()=>{{
  btns.forEach(x=>x.classList.remove('active'));b.classList.add('active');
  const f=b.dataset.f;
  document.querySelectorAll('.card').forEach(c=>{{
    c.style.display=(f==='all'||c.dataset.category===f)?'':'none';
  }});
}}));
</script>
</body></html>'''


if __name__ == "__main__":
    works = load_works()
    DASHBOARD_FILE.write_text(build_html(works), encoding="utf-8")
    print(f"✅ 作品看板 → {DASHBOARD_FILE}  ({len(works)} 条)")
