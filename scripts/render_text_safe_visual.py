#!/usr/bin/env python3
"""Reviewed deterministic visual templates with exact local Chinese typography.

The model chooses only a registered ``template_id``.  This renderer owns the
layout, glyphs, crop margins, palette, and structural evidence.  Every output
gets a bound ``.design.json`` manifest so a weak visual reviewer cannot approve
an image whose requested layout was silently ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont


SCALE = 2
BG = "#F5F0E6"
PAPER = "#FFFDF8"
INK = "#4A4540"
INK_SOFT = "#716A63"
SAGE = "#7BA3A8"
SAGE_LIGHT = "#DDE9E5"
TERRA = "#D4956A"
TERRA_LIGHT = "#F0D8C7"
PALE = "#F5E6C8"
GREEN = "#0E926F"
DARK = "#0E0E10"
DARK_CARD = "#191A1D"
DARK_LINE = "#2A2C31"
WHITE = "#FFFFFF"

FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
FONT_KAI = Path(r"C:\Windows\Fonts\simkai.ttf")

TEMPLATE_IDS = {
    "curve-convergence",
    "service-map",
    "tiered-network",
    "experience-loop",
}


def _s(value: int | float) -> int:
    return int(round(float(value) * SCALE))


def _box(value: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(_s(part) for part in value)


def _point(value: tuple[int, int]) -> tuple[int, int]:
    return _s(value[0]), _s(value[1])


def _font(size: int, *, bold: bool = False, handwritten: bool = False):
    path = FONT_KAI if handwritten and FONT_KAI.is_file() else FONT_BOLD if bold else FONT_REGULAR
    if not path.is_file():
        path = FONT_REGULAR
    return ImageFont.truetype(str(path), _s(size))


def _font_for_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    preferred: int,
    minimum: int,
    *,
    bold: bool = False,
    handwritten: bool = False,
) -> ImageFont.FreeTypeFont:
    for size in range(preferred, minimum - 1, -1):
        face = _font(size, bold=bold, handwritten=handwritten)
        if draw.textbbox((0, 0), text, font=face)[2] <= _s(max_width):
            return face
    return _font(minimum, bold=bold, handwritten=handwritten)


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    face: ImageFont.FreeTypeFont,
    max_width: int,
    *,
    max_lines: int = 3,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in str(text):
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=face)[2] > _s(max_width):
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


def _draw_text_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    preferred: int,
    minimum: int = 15,
    bold: bool = False,
    handwritten: bool = False,
    fill: str = INK,
    align: str = "center",
    max_lines: int = 3,
    spacing: int = 6,
) -> None:
    x1, y1, x2, y2 = box
    max_width = x2 - x1
    face = _font_for_width(
        draw,
        text,
        max_width,
        preferred,
        minimum,
        bold=bold,
        handwritten=handwritten,
    )
    lines = _wrap(draw, text, face, max_width, max_lines=max_lines)
    while True:
        extents = [draw.textbbox((0, 0), line, font=face) for line in lines]
        heights = [extent[3] - extent[1] for extent in extents]
        total = sum(heights) + _s(spacing) * max(0, len(lines) - 1)
        if (
            len(lines) <= max_lines
            and total <= _s(y2 - y1)
        ) or int(face.size / SCALE) <= minimum:
            break
        face = _font(
            max(minimum, int(face.size / SCALE) - 1),
            bold=bold,
            handwritten=handwritten,
        )
        lines = _wrap(draw, text, face, max_width, max_lines=max_lines)
    y = _s(y1) + (_s(y2 - y1) - total) // 2
    for line, extent, height in zip(lines, extents, heights):
        width = extent[2] - extent[0]
        x = _s(x1) if align == "left" else _s(x1) + (_s(x2 - x1) - width) // 2
        draw.text((x, y), line, font=face, fill=fill)
        y += height + _s(spacing)


def _paper_texture(draw: ImageDraw.ImageDraw, size: tuple[int, int], *, dark: bool = False) -> None:
    rng = random.Random(20260724)
    width, height = size
    line = "#17181B" if dark else "#E8E0D4"
    speck = "#22242A" if dark else "#DDD4C7"
    for y in range(18, height, 32):
        draw.line((_s(0), _s(y), _s(width), _s(y + rng.choice((-1, 0, 1)))), fill=line, width=1)
    for _ in range(max(80, width * height // 9000)):
        x, y = rng.randrange(width), rng.randrange(height)
        radius = rng.choice((1, 1, 2))
        draw.ellipse((_s(x), _s(y), _s(x + radius), _s(y + radius)), fill=speck)


def _washi(draw: ImageDraw.ImageDraw, cx: int, y: int, width: int = 96, *, color: str = SAGE) -> None:
    points = [
        (cx - width // 2 - 5, y + 3),
        (cx + width // 2, y),
        (cx + width // 2 + 4, y + 22),
        (cx - width // 2, y + 25),
    ]
    draw.polygon([_point(point) for point in points], fill=color)
    for offset in range(-width // 2 + 8, width // 2 - 2, 14):
        draw.line((_s(cx + offset), _s(y + 4), _s(cx + offset + 7), _s(y + 20)), fill="#F8F3E8", width=_s(1))


def _note(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str = PAPER,
    tape_color: str | None = None,
    seed: int = 1,
    radius: int = 20,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(_box((x1 + 5, y1 + 7, x2 + 7, y2 + 9)), radius=_s(radius), fill="#D8CFC2")
    draw.rounded_rectangle(_box(box), radius=_s(radius), fill=fill, outline=INK, width=_s(2))
    rng = random.Random(seed)
    for _ in range(2):
        dx, dy = rng.choice((-1, 0, 1)), rng.choice((-1, 0, 1))
        draw.rounded_rectangle(
            _box((x1 + dx, y1 + dy, x2 + dx, y2 + dy)),
            radius=_s(radius),
            outline=INK_SOFT,
            width=1,
        )
    if tape_color:
        _washi(draw, (x1 + x2) // 2, y1 - 10, max(72, min(112, (x2 - x1) // 3)), color=tape_color)


def _dotted_frame(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, color: str = SAGE) -> None:
    x1, y1, x2, y2 = box
    for x in range(x1, x2, 12):
        draw.line((_s(x), _s(y1), _s(min(x + 6, x2)), _s(y1)), fill=color, width=_s(2))
        draw.line((_s(x), _s(y2), _s(min(x + 6, x2)), _s(y2)), fill=color, width=_s(2))
    for y in range(y1, y2, 12):
        draw.line((_s(x1), _s(y), _s(x1), _s(min(y + 6, y2))), fill=color, width=_s(2))
        draw.line((_s(x2), _s(y), _s(x2), _s(min(y + 6, y2))), fill=color, width=_s(2))


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = SAGE,
    width: int = 4,
) -> None:
    draw.line((*_point(start), *_point(end)), fill=color, width=_s(width))
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (
        end[0] - 13 * math.cos(angle - math.pi / 6),
        end[1] - 13 * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - 13 * math.cos(angle + math.pi / 6),
        end[1] - 13 * math.sin(angle + math.pi / 6),
    )
    draw.polygon([_point(end), _point(left), _point(right)], fill=color)


def _curved_arrow(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    start_angle: int,
    end_angle: int,
    color: str = SAGE,
    width: int = 4,
) -> None:
    draw.arc(_box(box), start=start_angle, end=end_angle, fill=color, width=_s(width))
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    rx, ry = (box[2] - box[0]) / 2, (box[3] - box[1]) / 2
    angle = math.radians(end_angle)
    end = (int(cx + rx * math.cos(angle)), int(cy + ry * math.sin(angle)))
    tangent = angle + math.pi / 2
    p1 = (end[0] - 12 * math.cos(tangent - 0.5), end[1] - 12 * math.sin(tangent - 0.5))
    p2 = (end[0] - 12 * math.cos(tangent + 0.5), end[1] - 12 * math.sin(tangent + 0.5))
    draw.polygon([_point(end), _point(p1), _point(p2)], fill=color)


def _icon_school(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    w, h = int(80 * scale), int(62 * scale)
    draw.rectangle(_box((x, y + 22, x + w, y + h)), outline=INK, width=_s(3))
    draw.polygon([_point((x - 6, y + 22)), _point((x + w // 2, y)), _point((x + w + 6, y + 22))], outline=INK, fill=PALE)
    draw.rectangle(_box((x + w // 2 - 9, y + h - 27, x + w // 2 + 9, y + h)), outline=INK, width=_s(2))
    draw.line((_s(x + 18), _s(y + 34), _s(x + 18), _s(y + 46)), fill=SAGE, width=_s(3))
    draw.line((_s(x + w - 18), _s(y + 34), _s(x + w - 18), _s(y + 46)), fill=SAGE, width=_s(3))


def _icon_people(draw: ImageDraw.ImageDraw, x: int, y: int, count: int = 3, scale: float = 1.0) -> None:
    gap = int(28 * scale)
    for index in range(count):
        cx = x + index * gap
        r = int(8 * scale)
        draw.ellipse(_box((cx - r, y - r, cx + r, y + r)), outline=INK, width=_s(2))
        draw.line((_s(cx), _s(y + r), _s(cx), _s(y + 38 * scale)), fill=INK, width=_s(3))
        draw.line((_s(cx), _s(y + 18 * scale), _s(cx - 10 * scale), _s(y + 30 * scale)), fill=INK, width=_s(2))
        draw.line((_s(cx), _s(y + 18 * scale), _s(cx + 10 * scale), _s(y + 30 * scale)), fill=INK, width=_s(2))


def _icon_home(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    w, h = int(76 * scale), int(58 * scale)
    draw.rectangle(_box((x, y + 22, x + w, y + h)), outline=INK, width=_s(3))
    draw.polygon([_point((x - 7, y + 22)), _point((x + w // 2, y)), _point((x + w + 7, y + 22))], outline=INK, fill=SAGE_LIGHT)
    draw.ellipse(_box((x + w // 2 - 8, y + 32, x + w // 2 + 8, y + 48)), outline=TERRA, width=_s(3))


def _icon_service(draw: ImageDraw.ImageDraw, x: int, y: int, kind: int, scale: float = 1.0) -> None:
    r = int(24 * scale)
    draw.ellipse(_box((x - r, y - r, x + r, y + r)), fill=PAPER, outline=INK, width=_s(2))
    if kind == 0:  # companion / clock
        draw.ellipse(_box((x - 11 * scale, y - 11 * scale, x + 11 * scale, y + 11 * scale)), outline=TERRA, width=_s(2))
        draw.line((_s(x), _s(y), _s(x + 7 * scale), _s(y - 6 * scale)), fill=INK, width=_s(2))
    elif kind == 1:  # bath / drop
        draw.polygon([_point((x, y - 14 * scale)), _point((x - 10 * scale, y + 7 * scale)), _point((x + 10 * scale, y + 7 * scale))], fill=SAGE)
    elif kind == 2:  # shopping
        draw.rectangle(_box((x - 12 * scale, y - 5 * scale, x + 12 * scale, y + 13 * scale)), outline=TERRA, width=_s(2))
        draw.arc(_box((x - 8 * scale, y - 13 * scale, x + 8 * scale, y + 3 * scale)), 180, 360, fill=INK, width=_s(2))
    else:  # care manager clipboard
        draw.rounded_rectangle(_box((x - 12 * scale, y - 14 * scale, x + 12 * scale, y + 15 * scale)), radius=_s(3), outline=INK, width=_s(2))
        draw.line((_s(x - 7 * scale), _s(y - 3 * scale), _s(x + 7 * scale), _s(y - 3 * scale)), fill=SAGE, width=_s(2))
        draw.line((_s(x - 7 * scale), _s(y + 5 * scale), _s(x + 4 * scale), _s(y + 5 * scale)), fill=TERRA, width=_s(2))


def _icon_ai(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    r = int(25 * scale)
    draw.rounded_rectangle(_box((x - r, y - r, x + r, y + r)), radius=_s(9), fill=SAGE_LIGHT, outline=INK, width=_s(2))
    for angle in range(0, 360, 45):
        dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        draw.line((_s(x + dx * 8), _s(y + dy * 8), _s(x + dx * 18), _s(y + dy * 18)), fill=GREEN, width=_s(2))
    draw.ellipse(_box((x - 5, y - 5, x + 5, y + 5)), fill=GREEN)


def _icon_shield(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    points = [
        (x, y - 28 * scale),
        (x + 24 * scale, y - 17 * scale),
        (x + 19 * scale, y + 17 * scale),
        (x, y + 31 * scale),
        (x - 19 * scale, y + 17 * scale),
        (x - 24 * scale, y - 17 * scale),
    ]
    draw.polygon([_point(point) for point in points], fill=TERRA_LIGHT, outline=INK)
    draw.line((_s(x - 10 * scale), _s(y), _s(x - 2 * scale), _s(y + 9 * scale)), fill=GREEN, width=_s(3))
    draw.line((_s(x - 2 * scale), _s(y + 9 * scale), _s(x + 13 * scale), _s(y - 10 * scale)), fill=GREEN, width=_s(3))


def _base(size: tuple[int, int], *, dark: bool = False) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (_s(size[0]), _s(size[1])), DARK if dark else BG)
    draw = ImageDraw.Draw(image)
    _paper_texture(draw, size, dark=dark)
    return image, draw


def _save(
    image: Image.Image,
    output: Path,
    *,
    template_id: str,
    safe_bounds: tuple[int, int, int, int],
    text_boxes: list[dict[str, Any]],
    visual_elements: list[str],
    extra: dict[str, Any] | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    final = image.resize((image.width // SCALE, image.height // SCALE), Image.Resampling.LANCZOS)
    final.save(output, optimize=True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "renderer": "deterministic-template-compositor",
        "template_id": template_id,
        "image_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "safe_bounds": list(safe_bounds),
        "text_boxes": text_boxes,
        "visual_elements": visual_elements,
    }
    if extra:
        payload.update(extra)
    output.with_suffix(".design.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _title(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    text: str,
    *,
    portrait: bool,
    box: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    target = box or (
        (42, 25, size[0] - 42, 116)
        if portrait
        else (46, 35, size[0] - 46, 95)
    )
    _draw_text_box(
        draw,
        target,
        text,
        preferred=31 if portrait else 37,
        minimum=23,
        bold=True,
        fill=INK,
        max_lines=2,
    )
    y = target[3] + 5
    draw.line((_s(target[0]), _s(y), _s(target[2]), _s(y)), fill=TERRA, width=_s(4))
    return target


def render_cover(item: dict[str, Any], output: Path) -> None:
    size = (1024, 436)
    image, draw = _base(size, dark=True)
    accent = GREEN
    # A single canvas with a quiet gutter, not split-color panels.
    draw.line((_s(598), _s(38), _s(598), _s(398)), fill=DARK_LINE, width=_s(1))
    line1 = str(item.get("line1") or "")
    line2 = str(item.get("line2") or "")
    descriptor = str(item.get("descriptor") or "")
    ghost = str(item.get("ghost") or "")

    if ghost:
        face = _font_for_width(draw, ghost, 505, 68, 42, bold=True)
        draw.text((_s(48), _s(62)), ghost, font=face, fill="#12372F")
    line1_box = (60, 126, 545, 215)
    line2_box = (62, 216, 480, 273)
    descriptor_box = (62, 302, 510, 342)
    _draw_text_box(draw, line1_box, line1, preferred=72, minimum=48, bold=True, fill=WHITE, align="left", max_lines=1)
    # Secondary line is deliberately smaller and subordinate.
    l2_face = _font_for_width(draw, line2, line2_box[2] - line2_box[0], 43, 32, bold=True)
    width = draw.textbbox((0, 0), line2, font=l2_face)[2]
    draw.text((_s(line2_box[0]), _s(line2_box[1] + 2)), line2, font=l2_face, fill=accent)
    draw.line((_s(line2_box[0]), _s(line2_box[3] - 3), _s(line2_box[0]) + width, _s(line2_box[3] - 3)), fill=accent, width=_s(2))
    draw.rounded_rectangle(_box(descriptor_box), radius=_s(20), fill="#17191C")
    _draw_text_box(draw, (78, 307, 494, 337), descriptor, preferred=21, minimum=16, fill="#C7CAC9", align="left", max_lines=1)

    # Right evidence montage: three curves converge into a service-node card.
    card = (704, 95, 876, 340)
    draw.rounded_rectangle(_box((card[0] + 9, card[1] + 12, card[2] + 12, card[3] + 15)), radius=_s(25), fill="#08090A")
    draw.rounded_rectangle(_box(card), radius=_s(25), fill=DARK_CARD, outline="#4A4D53", width=_s(2))
    for index, color in enumerate(("#64716E", accent, "#B8BBB8")):
        points = [
            (630, 290 - index * 52),
            (690, 265 - index * 33),
            (742, 280 - index * 46),
            (812, 205 - index * 35),
            (862, 180 - index * 24),
        ]
        draw.line([_point(point) for point in points], fill=color, width=_s(6), joint="curve")
    _arrow(draw, (830, 202), (865, 167), color=accent, width=6)
    # Textless badges: school, care network, community hub.
    for cx, cy, color in ((670, 122, SAGE), (914, 116, TERRA), (900, 330, SAGE)):
        draw.rounded_rectangle(_box((cx - 36, cy - 31, cx + 36, cy + 31)), radius=_s(10), fill="#151719", outline=accent, width=_s(1))
        if cy == 122:
            draw.polygon([_point((cx - 18, cy - 2)), _point((cx, cy - 18)), _point((cx + 18, cy - 2))], outline=color)
            draw.rectangle(_box((cx - 14, cy - 2, cx + 14, cy + 17)), outline=color, width=_s(2))
        elif cy == 116:
            draw.ellipse(_box((cx - 20, cy - 12, cx - 4, cy + 4)), outline=color, width=_s(2))
            draw.ellipse(_box((cx + 4, cy - 12, cx + 20, cy + 4)), outline=color, width=_s(2))
            draw.arc(_box((cx - 25, cy - 2, cx + 25, cy + 22)), 180, 360, fill=color, width=_s(2))
        else:
            draw.rectangle(_box((cx - 18, cy - 8, cx + 18, cy + 16)), outline=color, width=_s(2))
            draw.polygon([_point((cx - 22, cy - 8)), _point((cx, cy - 23)), _point((cx + 22, cy - 8))], outline=color)
    # Restrained dashed orbital evidence line.
    for angle in range(205, 520, 18):
        rad = math.radians(angle)
        x = 801 + math.cos(rad) * 155
        y = 220 + math.sin(rad) * 145
        draw.ellipse(_box((x - 2, y - 2, x + 2, y + 2)), fill="#4C514F")

    _save(
        image,
        output,
        template_id="montage-evidence-v2",
        safe_bounds=(42, 34, 982, 402),
        text_boxes=[
            {"role": "line1", "text": line1, "box": list(line1_box)},
            {"role": "line2", "text": line2, "box": list(line2_box)},
            {"role": "descriptor", "text": descriptor, "box": list(descriptor_box)},
        ],
        visual_elements=[
            "unified-deep-charcoal-canvas",
            "left-primary-secondary-descriptor-hierarchy",
            "right-evidence-collage",
            "three-converging-curves",
            "three-textless-evidence-badges",
            "ghost-watermark",
        ],
        extra={
            "text_roles": {"line1": "primary", "line2": "secondary", "descriptor": "tertiary"},
            "font_scale_ratio": {"line2_to_line1": 0.60},
            "composition": "left-50-gap-6-right-44",
        },
    )


def render_hero(item: dict[str, Any], output: Path) -> None:
    size = (1024, 1024)
    image, draw = _base(size)
    title_box = (92, 62, 932, 220)
    _draw_text_box(draw, title_box, str(item.get("title") or ""), preferred=52, minimum=38, bold=True, fill=INK, max_lines=2)
    draw.line((_s(120), _s(245), _s(904), _s(245)), fill=TERRA, width=_s(5))
    # Three turning curves and three journal evidence islands.
    curve_sets = [
        ([(110, 760), (315, 700), (520, 742), (735, 558), (900, 500)], SAGE),
        ([(110, 660), (315, 650), (520, 624), (735, 505), (900, 455)], TERRA),
        ([(110, 565), (315, 620), (520, 535), (735, 455), (900, 415)], INK),
    ]
    for points, color in curve_sets:
        draw.line([_point(point) for point in points], fill=color, width=_s(8), joint="curve")
        _arrow(draw, points[-2], points[-1], color=color, width=8)
    for index, (box, fill, tape_color) in enumerate(
        (
            ((130, 355, 365, 555), SAGE_LIGHT, SAGE),
            ((395, 520, 630, 720), PALE, TERRA),
            ((665, 310, 900, 510), TERRA_LIGHT, SAGE),
        )
    ):
        _note(draw, box, fill=fill, tape_color=tape_color, seed=400 + index)
    _icon_school(draw, 205, 425, 1.1)
    _icon_people(draw, 465, 590, 3, 1.25)
    _icon_home(draw, 740, 380, 1.25)
    _save(
        image,
        output,
        template_id="hero-convergence",
        safe_bounds=(55, 45, 969, 965),
        text_boxes=[{"role": "title", "text": str(item.get("title") or ""), "box": list(title_box)}],
        visual_elements=[
            "three-turning-curves",
            "school-doodle",
            "family-care-doodle",
            "community-hub-doodle",
            "washi-note-islands",
        ],
    )


def _render_curve_convergence(item: dict[str, Any], output: Path) -> None:
    size = (576, 1024)
    image, draw = _base(size)
    title_box = _title(draw, size, item["title"], portrait=True)
    labels = list(item.get("expected_text") or [])[:4]
    boxes = [
        (48, 150, 528, 245),
        (42, 340, 278, 478),
        (298, 340, 534, 478),
        (52, 760, 524, 904),
    ]
    _note(draw, boxes[0], fill=PAPER, tape_color=SAGE, seed=11)
    _draw_text_box(draw, (68, 165, 508, 230), labels[0], preferred=23, minimum=18, bold=True, max_lines=2)
    # Two population ends visually converge.
    _icon_school(draw, 95, 535, 0.9)
    _icon_people(draw, 397, 563, 4, 0.82)
    draw.line([_point(point) for point in ((80, 670), (190, 620), (286, 700))], fill=SAGE, width=_s(6), joint="curve")
    draw.line([_point(point) for point in ((496, 650), (390, 610), (286, 700))], fill=TERRA, width=_s(6), joint="curve")
    draw.ellipse(_box((270, 684, 302, 716)), fill=PALE, outline=INK, width=_s(2))
    for index, box in enumerate(boxes[1:3], start=1):
        _note(draw, box, fill=SAGE_LIGHT if index == 1 else TERRA_LIGHT, tape_color=TERRA if index == 1 else SAGE, seed=11 + index)
        _draw_text_box(draw, (box[0] + 18, box[1] + 22, box[2] - 18, box[3] - 18), labels[index], preferred=20, minimum=16, max_lines=3)
    # Three-stage staircase is the requested temporal structure.
    steps = [(92, 735, 200, 710), (200, 710, 328, 672), (328, 672, 478, 620)]
    for index, (x1, y1, x2, y2) in enumerate(steps):
        draw.rectangle(_box((x1, y2, x2, y1)), fill=(SAGE_LIGHT, PALE, TERRA_LIGHT)[index], outline=INK, width=_s(2))
    _note(draw, boxes[3], fill=PAPER, tape_color=TERRA, seed=15)
    _draw_text_box(draw, (76, 780, 500, 884), labels[3], preferred=21, minimum=17, bold=True, max_lines=3)
    text_boxes = [{"role": "title", "text": item["title"], "box": list(title_box)}]
    text_boxes.extend({"role": f"label-{index + 1}", "text": label, "box": list(boxes[index])} for index, label in enumerate(labels))
    _save(
        image,
        output,
        template_id="curve-convergence",
        safe_bounds=(34, 20, 542, 986),
        text_boxes=text_boxes,
        visual_elements=[
            "school-doodle",
            "four-person-group-doodle",
            "two-stage-resource-lines",
            "three-stage-staircase",
            "washi-note-cards",
        ],
    )


def _render_service_map(item: dict[str, Any], output: Path) -> None:
    size = (1024, 576)
    image, draw = _base(size)
    title_box = _title(draw, size, item["title"], portrait=False)
    labels = list(item.get("expected_text") or [])[:4]
    boxes = [
        (55, 120, 365, 230),
        (620, 112, 970, 230),
        (70, 404, 430, 526),
        (590, 398, 955, 524),
    ]
    # Asymmetric family-to-service orbit, avoiding a rigid 2x2 corporate grid.
    _note(draw, boxes[0], fill=PAPER, tape_color=TERRA, seed=21)
    _draw_text_box(draw, (74, 138, 346, 215), labels[0], preferred=20, minimum=16, bold=True, max_lines=3)
    center = (500, 286)
    draw.ellipse(_box((420, 208, 580, 368)), fill=PALE, outline=INK, width=_s(3))
    _icon_people(draw, 455, 265, 3, 0.95)
    for index, (cx, cy) in enumerate(((390, 160), (610, 160), (390, 365), (610, 365))):
        _icon_service(draw, cx, cy, index, 0.9)
        _curved_arrow(draw, (center[0] - 140, center[1] - 130, center[0] + 140, center[1] + 130), start_angle=205 + index * 68, end_angle=255 + index * 68, color=SAGE if index % 2 == 0 else TERRA, width=3)
    _note(draw, boxes[1], fill=SAGE_LIGHT, tape_color=SAGE, seed=22)
    _draw_text_box(draw, (644, 131, 946, 214), labels[1], preferred=19, minimum=15, max_lines=3)
    for index, box in enumerate(boxes[2:], start=2):
        _note(draw, box, fill=TERRA_LIGHT if index == 2 else SAGE_LIGHT, tape_color=TERRA if index == 2 else SAGE, seed=23 + index)
        _draw_text_box(draw, (box[0] + 22, box[1] + 20, box[2] - 22, box[3] - 18), labels[index], preferred=19, minimum=15, max_lines=3)
    _arrow(draw, (430, 460), (576, 460), color=INK_SOFT, width=3)
    _icon_shield(draw, 520, 455, 0.8)
    text_boxes = [{"role": "title", "text": item["title"], "box": list(title_box)}]
    text_boxes.extend({"role": f"label-{index + 1}", "text": label, "box": list(boxes[index])} for index, label in enumerate(labels))
    _save(
        image,
        output,
        template_id="service-map",
        safe_bounds=(35, 18, 989, 558),
        text_boxes=text_boxes,
        visual_elements=[
            "family-core",
            "service-orbit",
            "four-service-doodles",
            "buyer-payment-bridge",
            "asymmetric-journal-notes",
        ],
    )


def _render_tiered_network(item: dict[str, Any], output: Path) -> None:
    size = (1024, 576)
    image, draw = _base(size)
    title_box = _title(draw, size, item["title"], portrait=False)
    labels = list(item.get("expected_text") or [])[:4]
    boxes = [
        (48, 124, 330, 228),
        (350, 112, 824, 190),
        (56, 428, 670, 530),
        (720, 354, 974, 526),
    ]
    _note(draw, boxes[0], fill=SAGE_LIGHT, tape_color=SAGE, seed=31)
    _draw_text_box(draw, (66, 141, 312, 215), labels[0], preferred=18, minimum=14, max_lines=3)
    # Three visible service levels, each with a distinct doodle.
    tiers = [
        ((365, 335, 680, 405), TERRA_LIGHT),
        ((410, 260, 635, 330), PALE),
        ((460, 195, 590, 255), SAGE_LIGHT),
    ]
    for index, (box, fill) in enumerate(tiers):
        draw.polygon(
            [
                _point((box[0], box[3])),
                _point((box[2], box[3])),
                _point((box[2] - 24, box[1])),
                _point((box[0] + 24, box[1])),
            ],
            fill=fill,
            outline=INK,
        )
    _icon_home(draw, 492, 206, 0.65)
    _icon_people(draw, 475, 287, 3, 0.62)
    _icon_shield(draw, 525, 367, 0.72)
    _note(draw, boxes[1], fill=PAPER, tape_color=TERRA, seed=32)
    _draw_text_box(draw, (374, 129, 800, 177), labels[1], preferred=20, minimum=15, bold=True, max_lines=2)
    # Three constraint gates plus the action note.
    for x, color in ((150, SAGE), (235, TERRA), (320, SAGE)):
        draw.line((_s(x), _s(335), _s(x), _s(412)), fill=color, width=_s(6))
        draw.arc(_box((x - 24, 315, x + 24, 363)), 180, 360, fill=color, width=_s(5))
    _note(draw, boxes[2], fill=PAPER, tape_color=TERRA, seed=33)
    _draw_text_box(draw, (80, 446, 646, 514), labels[2], preferred=19, minimum=15, max_lines=3)
    _note(draw, boxes[3], fill=TERRA_LIGHT, tape_color=SAGE, seed=34)
    _draw_text_box(draw, (742, 372, 952, 506), labels[3], preferred=17, minimum=14, bold=True, max_lines=4)
    text_boxes = [{"role": "title", "text": item["title"], "box": list(title_box)}]
    text_boxes.extend({"role": f"label-{index + 1}", "text": label, "box": list(boxes[index])} for index, label in enumerate(labels))
    _save(
        image,
        output,
        template_id="tiered-network",
        safe_bounds=(34, 18, 990, 558),
        text_boxes=text_boxes,
        visual_elements=[
            "three-level-pyramid",
            "community-node-doodle",
            "regional-hub-doodle",
            "professional-care-shield",
            "three-constraint-gates",
            "action-note",
        ],
    )


def _render_experience_loop(item: dict[str, Any], output: Path) -> None:
    size = (576, 1024)
    image, draw = _base(size)
    title_box = _title(draw, size, item["title"], portrait=True)
    labels = list(item.get("expected_text") or [])[:4]
    boxes = [
        (48, 155, 350, 278),
        (228, 330, 530, 455),
        (48, 516, 350, 642),
        (226, 700, 530, 835),
    ]
    fills = (SAGE_LIGHT, PALE, TERRA_LIGHT, PAPER)
    tape_colors = (SAGE, TERRA, SAGE, TERRA)
    for index, box in enumerate(boxes):
        _note(draw, box, fill=fills[index], tape_color=tape_colors[index], seed=41 + index)
        _draw_text_box(draw, (box[0] + 20, box[1] + 22, box[2] - 20, box[3] - 18), labels[index], preferred=20, minimum=15, bold=index in (0, 3), max_lines=4)
    # Central experience-to-product loop with four distinct evidence doodles.
    center = (288, 510)
    draw.ellipse(_box((226, 448, 350, 572)), fill=PAPER, outline=INK, width=_s(3))
    _icon_people(draw, 263, 492, 2, 0.9)
    _icon_ai(draw, 122, 387, 0.9)
    _icon_service(draw, 448, 565, 3, 0.95)
    _icon_shield(draw, 120, 770, 0.95)
    for arc, start, end, color in (
        ((84, 245, 492, 690), 205, 292, SAGE),
        ((84, 245, 492, 690), 302, 392, TERRA),
        ((84, 245, 492, 690), 402, 487, SAGE),
        ((84, 245, 492, 690), 498, 575, TERRA),
    ):
        _curved_arrow(draw, arc, start_angle=start, end_angle=end, color=color, width=4)
    text_boxes = [{"role": "title", "text": item["title"], "box": list(title_box)}]
    text_boxes.extend({"role": f"label-{index + 1}", "text": label, "box": list(boxes[index])} for index, label in enumerate(labels))
    _save(
        image,
        output,
        template_id="experience-loop",
        safe_bounds=(34, 20, 542, 986),
        text_boxes=text_boxes,
        visual_elements=[
            "expert-doodle",
            "ai-spark",
            "knowledge-product",
            "institution-clipboard",
            "rights-shield",
            "four-part-curved-loop",
        ],
    )


def render_infographic(item: dict[str, Any], output: Path) -> None:
    template_id = str(item.get("template_id") or "").strip()
    if template_id not in TEMPLATE_IDS:
        raise ValueError(
            f"未审核 template_id={template_id or '(空)'}；只允许 {sorted(TEMPLATE_IDS)}"
        )
    labels = item.get("expected_text")
    if not isinstance(labels, list) or len(labels) != 4:
        raise ValueError("确定性模板要求 expected_text 恰好 4 条")
    expected_aspect = "9:16" if template_id in {"curve-convergence", "experience-loop"} else "16:9"
    if str(item.get("aspect_ratio") or "") != expected_aspect:
        raise ValueError(f"{template_id} 固定 aspect_ratio={expected_aspect}")
    renderer = {
        "curve-convergence": _render_curve_convergence,
        "service-map": _render_service_map,
        "tiered-network": _render_tiered_network,
        "experience-loop": _render_experience_loop,
    }[template_id]
    renderer(item, output)


def _cover_item(plan: dict[str, Any], meta: dict[str, Any]) -> dict[str, str]:
    lead = meta.get("lead") if isinstance(meta.get("lead"), dict) else {}
    keywords = str(meta.get("cover_keywords") or "")
    uppercase = [
        token
        for token in keywords.replace("×", " ").split()
        if token.isascii() and token.replace("-", "").isalpha() and token.upper() == token
    ]
    return {
        "line1": str(lead.get("line1") or plan.get("title") or ""),
        "line2": str(lead.get("line2") or plan.get("subtitle") or ""),
        "descriptor": str(lead.get("subtitle") or ""),
        "ghost": " × ".join(uppercase[-3:]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("article_dir", type=Path)
    parser.add_argument("asset_id", help="cover, hero or infographic id such as 02")
    args = parser.parse_args()
    article = args.article_dir.resolve()
    plan = json.loads((article / "visual-plan.json").read_text(encoding="utf-8"))
    if args.asset_id == "cover":
        meta = yaml.safe_load((article / "article-meta.yaml").read_text(encoding="utf-8")) or {}
        render_cover(_cover_item(plan["cover"], meta), article / "素材/cover.png")
    elif args.asset_id == "hero":
        render_hero(plan["hero"], article / "素材/hero.png")
    else:
        item = next(
            value for value in plan["infographics"] if str(value["id"]) == args.asset_id
        )
        render_infographic(item, article / f"素材/infographic-{args.asset_id}.png")


if __name__ == "__main__":
    main()
