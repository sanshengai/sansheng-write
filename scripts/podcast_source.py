"""Versioned podcast input: preserve prose/captions, bind local still images by pixels."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

SOURCE_REPRESENTATION = "local-image-pixels-v1"
LEGACY_REPRESENTATION = "author-markdown-v1"
_IMAGE = re.compile(r'''(?P<head>[ \t]{0,3}!\[[^\]\r\n]*\]\()(?P<path><[^>\r\n]+>|[^()\s]+)(?P<tail>(?:[ \t]+["'][^\r\n]*["'])?\)[ \t]*)''')
_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")


def image_identity(article: Path, reference: str) -> str | None:
    """No downloads, missing-file guesses or animated-frame equivalence."""
    reference = reference.strip("<>")
    try:
        parsed = urlsplit(reference)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    root = article.resolve()
    path = (root / unquote(parsed.path)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) != 1:
                return None
            icc = image.info.get("icc_profile") or b""
            rgba = ImageOps.exif_transpose(image).convert("RGBA")
            payload = str(rgba.size).encode() + b"\0" + icc + b"\0" + rgba.tobytes()
            return "podcast-image-pixels:" + hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, TypeError, ImportError):
        return None


def normalized_source(article: Path, text: str) -> str:
    """Only standalone Markdown still images; unsupported syntax stays exact."""
    from assemble_release import strip_machine_assembly
    text = strip_machine_assembly(text)
    lines = []
    fence = ""
    fence_length = 0
    in_pre = False
    for line in text.splitlines(keepends=True):
        marker = _FENCE.match(line)
        if marker:
            value = marker.group(1)
            if not fence:
                fence, fence_length = value[0], len(value)
            elif value[0] == fence and len(value) >= fence_length and not line[marker.end():].strip():
                fence = ""
            lines.append(line)
            continue
        if re.search(r"<pre\b", line, re.I):
            in_pre = True
        match = None if fence or in_pre else _IMAGE.fullmatch(line.rstrip("\r\n"))
        if match:
            identity = image_identity(article, match.group("path"))
            if identity:
                line = match.group("head") + identity + match.group("tail") + ("\n" if line.endswith("\n") else "")
        lines.append(line)
        if re.search(r"</pre\s*>", line, re.I):
            in_pre = False
    return "".join(lines)
