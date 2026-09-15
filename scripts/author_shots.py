"""作者截图模式（`infographic_mode: author-shots`）。

信息图 ≥4 张的硬门守的是「贯穿全文的视觉切分」，不是「必须由生图模型画」。
截图密集的教程文（2026-09-15 第 101 篇：15 张作者截图）再叠 4 张粘土图只是凑数。
这个模式把同一保障换成另一种兑现方式：作者供图 ≥4 张、正文实际引用、文件真实存在。

- `article-meta.yaml` 写 `infographic_mode: author-shots` 才启用；默认 `generated` 行为不变。
- 启用后 `visual-plan.json` 的 `infographics` 必须为空（封面与 Hero 照常生成）；
  想同时要信息图就回到 `generated`，那条 ≥4 的合同不放宽。
- 作者供图只认两种形态：路径在 `素材/作者素材/` 之下，或文件名以 `shot-` 开头
  （image-routing.md「作者供图」既有约定）。生成图目录 `素材/*.png` 不算。
- 不是 skip：`verify infographic` 在该模式下改验作者供图，仍然会拒绝。
"""
from __future__ import annotations

import re
from pathlib import Path

MODE_KEY = "infographic_mode"
MODE_GENERATED = "generated"
MODE_AUTHOR_SHOTS = "author-shots"
MODES = (MODE_GENERATED, MODE_AUTHOR_SHOTS)
MIN_AUTHOR_SHOTS = 4
AUTHOR_DIR_PREFIX = "素材/作者素材/"
AUTHOR_FILE_PREFIX = "shot-"

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HTML_IMG_RE = re.compile(r"<img[^>]+src=\"([^\"]+)\"", re.I)


def infographic_mode(meta: dict | None) -> str:
    value = str((meta or {}).get(MODE_KEY) or MODE_GENERATED).strip()
    return value or MODE_GENERATED


def mode_errors(meta: dict | None) -> list[str]:
    mode = infographic_mode(meta)
    if mode not in MODES:
        return [f"{MODE_KEY} 只能是 {' / '.join(MODES)}；当前为 {mode}"]
    return []


def is_author_shot(ref: str) -> bool:
    ref = ref.replace("\\", "/").strip()
    if ref.startswith("./"):
        ref = ref[2:]
    if ref.startswith(AUTHOR_DIR_PREFIX):
        return True
    return Path(ref).name.startswith(AUTHOR_FILE_PREFIX)


def image_refs(markdown: str) -> list[str]:
    """正文里实际引用的图片路径（Markdown 与内联 <img> 都算），保持出现顺序去重。"""
    refs: list[str] = []
    for pattern in (_IMAGE_RE, _HTML_IMG_RE):
        for match in pattern.finditer(markdown):
            ref = match.group(1).strip()
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def author_shot_refs(markdown: str) -> list[str]:
    return [ref for ref in image_refs(markdown) if is_author_shot(ref)]


def verify_author_shots(cwd: Path, markdown: str, *, minimum: int = MIN_AUTHOR_SHOTS) -> list[str]:
    """作者截图模式的硬门：正文引用 ≥minimum 张作者供图，且每张在磁盘上存在。"""
    cwd = Path(cwd)
    refs = author_shot_refs(markdown)
    errors: list[str] = []
    if len(refs) < minimum:
        errors.append(
            f"{MODE_AUTHOR_SHOTS} 模式要求正文引用 ≥{minimum} 张作者供图"
            f"（{AUTHOR_DIR_PREFIX}… 或 {AUTHOR_FILE_PREFIX}* 命名），实际 {len(refs)} 张；"
            f"截图不够就改回 {MODE_GENERATED} 出信息图"
        )
    missing = [ref for ref in refs if not (cwd / ref.replace("\\", "/")).is_file()]
    if missing:
        errors.append("作者供图在磁盘上不存在：" + ", ".join(missing[:5]))
    return errors
