#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已发布的公众号页面找回文章目录里缺失的正文图。

老文章的 `素材/` 常常只剩封面（早期流水线没把配图镜像回成品目录），而 `定稿.md` 还引用着它们。
公众号页面（mp.weixin.qq.com/s/…）里的图是唯一还在的副本（微信会压到 1080 宽，够 X / 网站用）。

用法：
    python3 recover_images_from_wechat.py <文章目录> [--url <公众号链接>] [--apply "1:素材/a.webp,2:素材/b.webp"]

不带 --apply 时只下载到 `<文章目录>/dist/wx-images/` 并打印两张清单（页面图序号 + 尺寸 / 定稿里缺的引用），
再拼一张对照表 `dist/wx-images/sheet.jpg` 供人眼确认映射；带 --apply 按「页面序号:目标路径」落盘（转 webp）。
公众号链接缺省从 `_website-sync-receipt.json` 的 wechat_url 读。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150 Safari/537.36"


def fetch(url: str, referer: str = "") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Referer": referer} if referer else {})})
    return urllib.request.urlopen(req, timeout=40).read()


def page_images(html: str) -> list[str]:
    return [u for u in re.findall(r'<img[^>]+data-src="([^"]+)"', html) if u.startswith("http")]


def missing_refs(article_dir: Path) -> list[str]:
    md = (article_dir / "定稿.md").read_text(encoding="utf-8")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    return [r for r in refs if not (article_dir / r).is_file()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("article_dir")
    ap.add_argument("--url", default="")
    ap.add_argument("--apply", default="", help='"页面序号:目标相对路径,…"，按此落盘')
    a = ap.parse_args()
    ad = Path(a.article_dir).resolve()
    url = a.url
    if not url:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from article_paths import process_file
        f = process_file(ad, "_website-sync-receipt.json")
        if f.is_file():
            url = json.loads(f.read_text(encoding="utf-8")).get("wechat_url", "")
    if not url:
        print("没有公众号链接：--url 或回执里的 wechat_url"); return 2
    out = ad / "dist" / "wx-images"; out.mkdir(parents=True, exist_ok=True)
    html = fetch(url).decode("utf-8", "replace")
    urls = page_images(html)
    files: list[tuple[int, Path, tuple[int, int]]] = []
    for i, u in enumerate(urls):
        cached = next(out.glob(f"{i:02d}.*"), None)
        if cached is None:
            data = fetch(u, referer="https://mp.weixin.qq.com/")
            im = Image.open(io.BytesIO(data)); im.load()
            ext = "jpg" if im.format == "JPEG" else (im.format or "png").lower()
            cached = out / f"{i:02d}.{ext}"; cached.write_bytes(data)
        im = Image.open(cached)
        files.append((i, cached, im.size))
    if a.apply:
        for pair in a.apply.split(","):
            idx, target = pair.split(":", 1)
            src = next(p for i, p, _ in files if i == int(idx))
            dst = ad / target.strip(); dst.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(src).convert("RGB")
            if dst.suffix.lower() == ".webp":
                im.save(dst, "WEBP", quality=90, method=6)
            else:
                im.save(dst)
            print(f"  {src.name} → {target} {im.size}")
        left = missing_refs(ad)
        print("仍缺:", left or "无"); return 0 if not left else 1
    print(f"页面图 {len(files)} 张：")
    for i, p, size in files:
        print(f"  {i:02d}  {size[0]}x{size[1]}  {p.name}")
    miss = missing_refs(ad)
    print(f"定稿缺 {len(miss)} 张：")
    for r in miss:
        print("  ", r)
    # 对照表
    thumbs = [Image.open(p).convert("RGB") for _, p, _ in files]
    w = 260; thumbs = [t.resize((w, max(1, int(t.height * w / t.width)))) for t in thumbs]
    cols = 5; rows = (len(thumbs) + cols - 1) // cols; H = max((t.height for t in thumbs), default=1)
    sheet = Image.new("RGB", (cols * (w + 10) + 10, rows * (H + 30) + 10), (40, 40, 40))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, t in enumerate(thumbs):
        x, y = 10 + (i % cols) * (w + 10), 10 + (i // cols) * (H + 30)
        sheet.paste(t, (x, y + 20)); dr.text((x, y + 2), f"{i:02d} {files[i][2][0]}x{files[i][2][1]}", fill=(255, 255, 255))
    sheet.save(out / "sheet.jpg", quality=70)
    print("对照表:", out / "sheet.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
