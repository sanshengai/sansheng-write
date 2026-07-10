#!/usr/bin/env python3
"""
🎨 SVG → PNG 转换器（Playwright 后端）
==========================================================================
专门为 baoyu-diagram 输出的 SVG 文件转成 PNG，再嵌入微信公众号。

为什么用 Playwright 而不是 cairosvg / rsvg-convert / inkscape：
- cairosvg 在 Windows 上需要 GTK+ runtime，依赖重
- rsvg-convert / inkscape 不在默认 PATH 上
- Playwright 已是本 skill 的 HTML→PNG 现成基础设施
- Playwright 渲染保真度高（包括 SVG 字体、CSS @media、深色模式）

使用：
    python svg_to_png.py <svg_file> [-o <png_file>] [--scale 2] [--check-brand]

参数：
    -o / --output    输出 PNG 路径，默认与 SVG 同目录同名
    --scale          DPR（device pixel ratio），默认 2 = 高清
    --width          强制输出宽度（px），等比缩放，默认按 SVG viewBox
    --check-brand    校验 SVG 内只用主题色（默认 #2F6F8F + 黑/白/灰），违规报错
"""

import argparse
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


# 主题色白名单（小写 hex / rgb 名）。默认中性 slate；换主题后可按需扩这里。
ALLOWED_COLORS = {
    # 主题色系
    "#2F6F8F",
    "#B6D2DE",       # 浅色（信息图辅助）
    "#e9f2f5",       # 极浅色
    "#12252E",       # 深色
    # 黑白灰
    "#000000", "#ffffff",
    "#1a1a1a", "#0e0e10", "#030712",  # 深色底
    "#2a2a30", "#2c2c2c",              # 深灰
    "#444444", "#666666", "#999999",   # 中灰
    "#cccccc", "#eeeeee", "#f5f5f5",   # 浅灰
    # 颜色关键字（CSS 命名色）
    "none", "transparent", "currentcolor", "inherit",
    "white", "black",
    "gray", "grey", "darkgray", "darkgrey", "lightgray", "lightgrey",
    "silver", "dimgray", "dimgrey",
}


def parse_svg_dimensions(svg_content: str) -> tuple[int, int]:
    """从 SVG 内容提取宽高"""
    # 优先 viewBox
    vb = re.search(r'viewBox\s*=\s*["\']\s*([\d\.\s\-]+)\s*["\']', svg_content)
    if vb:
        parts = vb.group(1).split()
        if len(parts) == 4:
            return int(float(parts[2])), int(float(parts[3]))
    # fallback 到 width/height（去单位）
    w = re.search(r'\bwidth\s*=\s*["\']?(\d+)', svg_content)
    h = re.search(r'\bheight\s*=\s*["\']?(\d+)', svg_content)
    if w and h:
        return int(w.group(1)), int(h.group(1))
    return 1200, 800  # 兜底


def check_brand_colors(svg_content: str) -> list[str]:
    """扫描 SVG 内的颜色，返回违规颜色清单"""
    # 匹配 stroke= / fill= / color= / stop-color= / 内联 style 里的颜色
    pat = r'(?:stroke|fill|color|stop-color)\s*[:=]\s*["\']?(#[0-9a-fA-F]{3,8}|rgb\([^)]+\)|rgba\([^)]+\)|[a-zA-Z]+)'
    found: set[str] = set()
    for m in re.finditer(pat, svg_content):
        c = m.group(1).strip().lower()
        # #RGB → #RRGGBB
        if re.match(r'^#[0-9a-f]{3}$', c):
            c = "#" + "".join(ch * 2 for ch in c[1:])
        # rgb(r,g,b) → #hhhhhh
        m2 = re.match(r'rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)', c)
        if m2:
            r, g, b = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            c = f"#{r:02x}{g:02x}{b:02x}"
        found.add(c)

    violations = sorted(c for c in found if c not in ALLOWED_COLORS)
    return violations


def _build_html(svg_content: str, width: int, height: int) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; padding: 0; background: white; }}
  body {{ width: {width}px; height: {height}px; overflow: hidden; }}
  svg {{ display: block; width: {width}px; height: {height}px; }}
</style></head><body>
{svg_content}
</body></html>"""


def convert(svg_path: Path, png_path: Path, scale: int = 2, force_width: int | None = None) -> tuple[int, int]:
    """单 SVG 转 PNG。批量转多个文件时请用 convert_batch（共享 browser，免冷启动）。"""
    return convert_batch([(svg_path, png_path)], scale=scale, force_width=force_width)[0]


def convert_batch(jobs: list[tuple[Path, Path]], scale: int = 2, force_width: int | None = None) -> list[tuple[int, int]]:
    """批量 SVG → PNG，共享同一个 browser 实例。

    chromium 冷启动 ~2s，多文件并行场景会浪费严重。这里启 1 个 browser，
    每个文件开新 context（保证 viewport 独立），转完关 page 不关 browser。
    """
    results: list[tuple[int, int]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for svg_path, png_path in jobs:
                svg_content = svg_path.read_text(encoding="utf-8")
                width, height = parse_svg_dimensions(svg_content)
                if force_width:
                    ratio = force_width / width
                    width = force_width
                    height = int(height * ratio)

                html = _build_html(svg_content, width, height)
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=scale,
                )
                page = context.new_page()
                try:
                    page.set_content(html, wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path=str(png_path), full_page=True, omit_background=False)
                finally:
                    context.close()
                results.append((width, height))
        finally:
            browser.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="SVG → PNG via Playwright")
    parser.add_argument("svg", nargs="+", help="输入 SVG 文件路径（可多个，批量共享 browser）")
    parser.add_argument("-o", "--output", help="单文件模式输出 PNG；多文件模式忽略此项，按 .svg 同名替换")
    parser.add_argument("--scale", type=int, default=2, help="DPR (default 2 = 高清)")
    parser.add_argument("--width", type=int, help="强制输出宽度 px（等比缩放）")
    parser.add_argument("--check-brand", action="store_true", help="校验品牌色（违规则失败）")
    args = parser.parse_args()

    svg_paths = [Path(s) for s in args.svg]
    for sp in svg_paths:
        if not sp.exists():
            print(f"❌ SVG 不存在: {sp}", file=sys.stderr)
            return 1

    # 品牌色校验（多文件时全跑一遍，任一不通过即失败）
    if args.check_brand:
        any_violation = False
        for sp in svg_paths:
            violations = check_brand_colors(sp.read_text(encoding="utf-8"))
            if violations:
                any_violation = True
                print(f"❌ {sp.name} 品牌色校验失败 -- 发现非允许颜色：", file=sys.stderr)
                for c in violations:
                    print(f"   - {c}", file=sys.stderr)
        if any_violation:
            print(f"\n💡 修复建议：让 baoyu-diagram 的 prompt 显式覆写所有 stroke/fill 为主题色 #2F6F8F", file=sys.stderr)
            return 1
        print(f"✅ 品牌色校验通过 ({len(svg_paths)} 个 SVG)")

    # 构建 jobs 列表
    if len(svg_paths) == 1 and args.output:
        png_path = Path(args.output)
        jobs = [(svg_paths[0], png_path)]
    else:
        if args.output and len(svg_paths) > 1:
            print(f"⚠️  多文件模式忽略 --output，按 .svg 同名替换", file=sys.stderr)
        jobs = [(sp, sp.with_suffix(".png")) for sp in svg_paths]

    for _, png_path in jobs:
        png_path.parent.mkdir(parents=True, exist_ok=True)

    # 批量转换（共享 browser）
    sizes = convert_batch(jobs, scale=args.scale, force_width=args.width)
    for (svg_path, png_path), (w, h) in zip(jobs, sizes):
        print(f"✅ {svg_path.name} → {png_path.name}  ({w}×{h} @ DPR{args.scale} = {w*args.scale}×{h*args.scale}px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
