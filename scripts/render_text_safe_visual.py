#!/usr/bin/env python3
"""Deterministic Chinese text compositor for morandi-journal visuals.

Image models are used only when free-form illustration is valuable.  This
fallback owns every visible glyph locally, so a weak renderer cannot invent,
drop, or misspell Chinese labels.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BG = "#F5F0E6"
INK = "#4A4540"
SAGE = "#7BA3A8"
TERRA = "#D4956A"
PALE = "#F5E6C8"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold and FONT_BOLD.is_file() else FONT
    return ImageFont.truetype(str(path), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, face, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=face)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) >= 2 and len(lines[-1]) <= 2 and len(lines[-2]) >= 6:
        combined = lines[-2] + lines[-1]
        split = (len(combined) + 1) // 2
        lines[-2:] = [combined[:split], combined[split:]]
    return lines


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    face,
    *,
    fill: str = INK,
    spacing: int = 8,
) -> None:
    x1, y1, x2, y2 = box
    lines = wrap(draw, text, face, x2 - x1)
    heights = [draw.textbbox((0, 0), line, font=face)[3] for line in lines]
    total = sum(heights) + spacing * max(0, len(lines) - 1)
    y = y1 + (y2 - y1 - total) // 2
    for line, height in zip(lines, heights):
        width = draw.textbbox((0, 0), line, font=face)[2]
        draw.text((x1 + (x2 - x1 - width) // 2, y), line, font=face, fill=fill)
        y += height + spacing


def sketch_round_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str = INK,
    radius: int = 24,
    seed: int,
) -> None:
    rng = random.Random(seed)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)
    for _ in range(2):
        dx, dy = rng.randint(-2, 2), rng.randint(-2, 2)
        shifted = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
        draw.rounded_rectangle(shifted, radius=radius, outline=outline, width=1)


def tape(draw: ImageDraw.ImageDraw, cx: int, y: int, color: str) -> None:
    draw.polygon(
        [(cx - 58, y), (cx + 54, y + 3), (cx + 48, y + 28), (cx - 62, y + 24)],
        fill=color,
    )
    for offset in range(-48, 49, 16):
        draw.line((cx + offset, y + 4, cx + offset + 8, y + 21), fill="#FFFFFF66", width=2)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line((*start, *end), fill=SAGE, width=5)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) > abs(ey - sy):
        direction = 1 if ex > sx else -1
        draw.polygon([(ex, ey), (ex - 16 * direction, ey - 9), (ex - 16 * direction, ey + 9)], fill=SAGE)
    else:
        direction = 1 if ey > sy else -1
        draw.polygon([(ex, ey), (ex - 9, ey - 16 * direction), (ex + 9, ey - 16 * direction)], fill=SAGE)


def render_infographic(item: dict, output: Path) -> None:
    portrait = item["aspect_ratio"] == "9:16"
    size = (576, 1024) if portrait else (1024, 576)
    image = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(image)
    title_face = font(30 if portrait else 39, bold=True)
    label_face = font(26 if portrait else 24, bold=False)
    title_h = 132 if portrait else 92
    centered_text(draw, (34, 18, size[0] - 34, title_h), item["title"], title_face)
    draw.line((45, title_h, size[0] - 45, title_h), fill=TERRA, width=5)

    labels = list(item.get("expected_text") or [])
    fills = ("#E4ECE7", PALE, "#E8DED5", "#DCE8E8")
    if portrait:
        boxes = [(45, 165 + index * 200, 531, 325 + index * 200) for index in range(4)]
        for index, (label, box) in enumerate(zip(labels, boxes)):
            sketch_round_rect(draw, box, fill=fills[index], seed=100 + index)
            tape(draw, (box[0] + box[2]) // 2, box[1] - 13, TERRA if index % 2 else SAGE)
            centered_text(draw, (box[0] + 26, box[1] + 24, box[2] - 26, box[3] - 18), label, label_face)
            if index < 3:
                arrow(draw, (288, box[3] + 8), (288, boxes[index + 1][1] - 16))
    else:
        boxes = [
            (48, 125, 476, 300),
            (548, 125, 976, 300),
            (48, 355, 476, 530),
            (548, 355, 976, 530),
        ]
        for index, (label, box) in enumerate(zip(labels, boxes)):
            sketch_round_rect(draw, box, fill=fills[index], seed=200 + index)
            tape(draw, (box[0] + box[2]) // 2, box[1] - 12, SAGE if index % 2 else TERRA)
            centered_text(draw, (box[0] + 24, box[1] + 22, box[2] - 24, box[3] - 18), label, label_face)
        arrow(draw, (486, 212), (538, 212))
        arrow(draw, (762, 310), (762, 345))
        arrow(draw, (538, 442), (486, 442))
        arrow(draw, (262, 345), (262, 310))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)


def render_hero(item: dict, output: Path) -> None:
    image = Image.new("RGB", (1024, 1024), BG)
    draw = ImageDraw.Draw(image)
    centered_text(draw, (75, 55, 949, 270), item["title"], font(52, bold=True))
    draw.line((100, 290, 924, 290), fill=TERRA, width=6)
    # Three clean turning curves and textless journal motifs.
    for index, color in enumerate((SAGE, TERRA, INK)):
        points = [(110, 770 - index * 95), (330, 690 - index * 30), (520, 740 - index * 95), (760, 530 - index * 55), (900, 450 - index * 35)]
        draw.line(points, fill=color, width=10, joint="curve")
        ex, ey = points[-1]
        draw.polygon([(ex, ey), (ex - 35, ey + 4), (ex - 15, ey + 30)], fill=color)
    sketch_round_rect(draw, (135, 390, 345, 560), fill="#E4ECE7", seed=301)
    sketch_round_rect(draw, (405, 505, 615, 675), fill=PALE, seed=302)
    sketch_round_rect(draw, (675, 330, 885, 500), fill="#E8DED5", seed=303)
    tape(draw, 240, 375, SAGE)
    tape(draw, 510, 490, TERRA)
    tape(draw, 780, 315, SAGE)
    # Textless doodles: shrinking school, family-care node, community service hub.
    draw.rectangle((190, 445, 290, 525), outline=INK, width=5)
    draw.polygon([(180, 445), (240, 405), (300, 445)], outline=INK)
    draw.line((235, 525, 235, 485), fill=INK, width=5)
    for x in (455, 510, 565):
        draw.ellipse((x, 545, x + 24, 569), outline=INK, width=4)
        draw.line((x + 12, 570, x + 12, 625), fill=INK, width=4)
    draw.rectangle((725, 385, 835, 465), outline=INK, width=5)
    draw.polygon([(715, 385), (780, 345), (845, 385)], outline=INK)
    draw.ellipse((765, 405, 795, 435), outline=SAGE, width=4)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("article_dir", type=Path)
    parser.add_argument("asset_id", help="hero or infographic id such as 02")
    args = parser.parse_args()
    article = args.article_dir.resolve()
    plan = json.loads((article / "visual-plan.json").read_text(encoding="utf-8"))
    if args.asset_id == "hero":
        render_hero(plan["hero"], article / "素材/hero.png")
    else:
        item = next(
            value for value in plan["infographics"] if str(value["id"]) == args.asset_id
        )
        render_infographic(item, article / f"素材/infographic-{args.asset_id}.png")


if __name__ == "__main__":
    main()
