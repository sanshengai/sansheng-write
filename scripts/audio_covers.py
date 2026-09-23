#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题曲封面与播客封面：缺哪张生成哪张，产物放在文章编号文件夹第一层。

背景（2026-09-14）：主题曲封面原来由 Lyria 自动链顺手生成；主题曲改走
MiniMax 网页手工生成后这一步就断了，播客封面流水线里从来没有。作者要在微信
编辑器里给两条音频各配一张封面，结果连着两篇都得事后补。现在把两张封面收进
``handoff-assets`` 的前置步骤：交付上传文件前先保证它们存在。

改版（2026-09-22，schema 2）：两张封面在官网里只有 46–66 CSS px（迷你播放器 46、
歌单 62、播客 66），微信音频卡也只是一小块，之前「场景 + 标题 + 副标题」的编辑
式封面缩到那个尺寸只剩一团暗色；连续几篇更是清一色书桌台灯落日窗，分不出
哪首是哪首。现在按 **图标逻辑** 出图：

- 不要任何文字，主体自己说话；
- 只有一个主体，居中占画面约 2/3，整个剪影在框内，背景是纯色深底 + 柔和暗角；
- 主体必须来自歌名 / 歌词（主题曲）或文章核心对象（播客），两张主体不同；
- 每张指定一组「深底 + 一个强调色」调色板，两张不同，主题曲封面还要避开前三篇
  用过的调色板，缩略图一排看过去先靠颜色分开、再靠剪影认出来。

- 主题曲封面：``音乐封面.png``，歌名来自 ``_music-manifest.json``。
- 播客封面：``播客封面.png``，仅当 ``dist/podcast/audio.manifest.json``
  存在（即本篇真的有播客）时生成。
- 旧稿若只有 ``素材/bgm_cover.png`` / ``素材/podcast_cover.png``，沿用该文件，不另造一张。
- 渲染器只走 ``baoyu-image-gen``，provider/model 按文章目录的 ``renderer-policy.json``
  逐项降级，与信息图同一条链；封面图不加品牌水印（与 music.md 既有约定一致）。
- 已存在且非空的封面不重生成；``--force`` 才覆盖。
- 出图后写 ``_audio-cover-thumbs.png``：两张封面按 256 / 128 / 64 / 46 px 排一行，
  Agent 看这张做视觉验收，不看原图 1024 的效果。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    from .article_paths import PODCAST_COVER, THEME_COVER, cover_output
    from .music_manifest import MUSIC_MANIFEST_FILE
    from .render_visuals import _load_policy, resolve_renderer_command
except ImportError:  # pragma: no cover - direct script execution
    from article_paths import PODCAST_COVER, THEME_COVER, cover_output
    from music_manifest import MUSIC_MANIFEST_FILE
    from render_visuals import _load_policy, resolve_renderer_command

try:
    # 46px 盲配（references/music.md §验收：盲配测试）；依赖链最终会拉到 Pillow
    # （经 visual_qa_claude → visual_qa）。公开 Skill 用户可能没装全这条链，
    # 任何 import 失败都不该拖垮本模块的基本出图能力，所以整体降级为 None，
    # 调用处按「盲配不可用」处理（warning，不拦交付）。
    try:
        from .cover_blind_match import recheck_existing as recheck_blind_match, run_blind_match
    except ImportError:
        from cover_blind_match import recheck_existing as recheck_blind_match, run_blind_match
except Exception:  # pragma: no cover - 环境缺依赖时的兜底
    run_blind_match = None
    recheck_blind_match = None

PODCAST_MANIFEST = Path("dist/podcast/audio.manifest.json")
PROMPT_DIR = Path("素材/prompts")
GEN_LOG = ".gen-log.jsonl"
COVER_PLAN = "_audio-cover-plan.json"
COVER_THUMBS = "_audio-cover-thumbs.png"
MUSIC_BRIEF = "MiniMax-主题曲生成单.md"
PLAN_SCHEMA = 3
# 调色板回避时仍认的旧规划（schema 2 也有 palette 字段）。
PALETTE_SCHEMAS = (2, 3)
# 主题曲封面调色板回避范围：往前看几篇。
RECENT_PALETTE_WINDOW = 3
# 官网实际显示尺寸（CSS px）：迷你播放器 46、歌单条目 62、播客条目 66；再加 256/128 看形。
THUMB_SIZES = (256, 128, 64, 46)
# codex-cli 出图机器级串行锁；另一篇文章在渲时等它放锁，别当失败。
LOCK_BUSY_MARK = "lock_busy"
LOCK_RETRY_LIMIT = 12
LOCK_RETRY_SECONDS = 60

# 调色板：全部深底，只有一个强调色。名字进规划文件，描述进 prompt。
PALETTES: dict[str, dict[str, str]] = {
    "ink":   {"bg": "near-black indigo (#0F1524)", "accent": "cool silver-white"},
    "ember": {"bg": "charcoal with a brown undertone (#1A1210)", "accent": "warm amber"},
    "moss":  {"bg": "deep forest green (#0F1F17)", "accent": "pale sage"},
    "plum":  {"bg": "deep aubergine (#1E1020)", "accent": "rose pink"},
    "ocean": {"bg": "deep navy (#0B1A2E)", "accent": "aqua cyan"},
    "rust":  {"bg": "oxblood (#24100E)", "accent": "coral orange"},
    "slate": {"bg": "cold graphite (#15181C)", "accent": "mustard yellow"},
    "sand":  {"bg": "dark olive-brown (#1C1A10)", "accent": "cream gold"},
}
# 渲染质感：可选，默认 sculpted；同一篇两张可不同，用来再拉开区别。
RENDERS: dict[str, str] = {
    "sculpted": "a matte sculpted object with soft studio lighting, like a premium app icon",
    "papercut": "layered paper cut-out with soft drop shadows between the layers",
    "flat":     "flat vector illustration, two or three tones, crisp edges, no gradients inside shapes",
    "painted":  "thick gouache brushwork on a plain ground, edges soft but the mass unmistakable",
}
DEFAULT_RENDER = "sculpted"
# 缩略图里认不出来、又被前几篇反复用烂的通用道具；只有歌词 / 正文依据里真出现了才允许。
GENERIC_PROPS = ("窗", "台灯", "灯", "书桌", "桌", "书本", "书页", "书架", "河", "船", "日落", "夕阳", "落日",
                 "耳机", "麦克风", "话筒", "咖啡", "茶杯", "云朵", "星空", "月亮")
# 主体描述里不该出现的「文字类」意图：封面不放任何字。
TEXT_WORDS = ("文字", "标题", "字样", "歌名", "字体", "字母", "logo", "Logo", "LOGO", "水印", "副标题", "slogan")
# 2026-09-23 复盘：价签（砍半价）、路标（方向相反）这类「论点隐喻」道具换到任何一篇
# 讲取舍 / 降价 / 选择的文章都成立，作者看了认不出是哪篇。封面画标题里的锚点（专名本身），
# 不画冒号后面那句论点。只有标题或歌名里字面出现这个词时才允许。
ABSTRACT_METAPHORS = ("天平", "天秤", "路标", "岔路", "十字路口", "价签", "吊牌", "台阶", "楼梯", "梯子",
                      "钥匙", "锁", "灯泡", "齿轮", "拼图", "沙漏", "指南针", "罗盘", "桥", "箭头",
                      "靶", "放大镜", "跷跷板", "砝码")
# 封面怎样让人一眼联想到锚点：四条路线，按优先级（见 music.md）。
IDENTITY_ROUTES = ("实物外形", "名字字面义", "官方视觉", "标号")
# 唯一允许的文字：锚点里的短标号（版本号 / 单字），非空白字符不超过 4 个。
GLYPH_MAX = 4
GLYPH_SHAPE_WORDS = ("字母", "字样", "字体")


def _article_context(article_dir: Path) -> tuple[str, str, str]:
    """meta 为配置真源；兼容正文 frontmatter 与普通 H1，保留正文作取材依据。"""
    draft = article_dir / "定稿.md"
    if not draft.is_file():
        return "", "", ""
    text = draft.read_text(encoding="utf-8", errors="replace")
    meta_path = article_dir / "article-meta.yaml"
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    meta = meta if isinstance(meta, dict) else {}
    front: dict = {}
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if match:
        parsed = yaml.safe_load(match.group(1))
        front = parsed if isinstance(parsed, dict) else {}
        text = text[match.end():]
    h1 = re.search(r"^#\s+(.+)$", text, re.M)
    title = str(meta.get("title") or front.get("title") or (h1.group(1) if h1 else "")).strip()
    digest = str(meta.get("digest") or meta.get("description") or front.get("description") or front.get("digest") or "").strip()
    return title, digest, text


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _article_number(article_dir: Path) -> int | None:
    match = re.match(r"(\d+)-", article_dir.name)
    return int(match.group(1)) if match else None


def _recent_theme_palettes(article_dir: Path, window: int = RECENT_PALETTE_WINDOW) -> dict[str, str]:
    """前 ``window`` 篇（按编号）主题曲封面用过的调色板：{目录名: palette}。

    只认 schema 2 的规划；旧篇没有调色板字段就不参与回避。
    """
    current = _article_number(article_dir)
    if current is None:
        return {}
    found: list[tuple[int, str, str]] = []
    for plan_path in article_dir.parent.glob("[0-9]*-*/" + COVER_PLAN):
        number = _article_number(plan_path.parent)
        if number is None or number >= current:
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(plan, dict) or plan.get("schema_version") not in PALETTE_SCHEMAS:
            continue
        theme = plan.get("theme_cover")
        palette = theme.get("palette") if isinstance(theme, dict) else None
        if isinstance(palette, str) and palette:
            found.append((number, plan_path.parent.name, palette))
    found.sort(reverse=True)
    return {name: palette for _, name, palette in found[:window]}


def _check_identity(stage: str, item: dict, *, title: str, song: str) -> None:
    """封面必须指向标题（播客）或歌名 / 标题（主题曲）里的锚点，而不是论点隐喻。"""
    identity = item.get("identity")
    if not isinstance(identity, dict):
        raise ValueError(
            f"{stage}.identity 必填：{{anchor, route, reason}}；封面画标题里的锚点（专名本身），"
            "不画冒号后那句论点"
        )
    anchor = identity.get("anchor")
    names = _normalize(title) if stage == "podcast_cover" else _normalize(title + song)
    where = "文章标题" if stage == "podcast_cover" else "歌名或文章标题"
    if not isinstance(anchor, str) or len(_normalize(anchor)) < 2 or _normalize(anchor) not in names:
        raise ValueError(f"{stage}.identity.anchor 必须是{where}里原样出现的专名（至少 2 字），当前：{anchor!r}")
    if identity.get("route") not in IDENTITY_ROUTES:
        raise ValueError(f"{stage}.identity.route 必须是 {' / '.join(IDENTITY_ROUTES)} 之一")
    reason = identity.get("reason")
    if not isinstance(reason, str) or len(_normalize(reason)) < 8:
        raise ValueError(f"{stage}.identity.reason 至少 8 字：看到标题旁这张图，读者凭什么立刻想到「{anchor}」")
    glyph = item.get("glyph")
    if glyph is not None:
        if not isinstance(glyph, str) or not glyph.strip():
            raise ValueError(f"{stage}.glyph 要么省略，要么是非空短标号")
        if len(re.sub(r"\s", "", glyph)) > GLYPH_MAX:
            raise ValueError(f"{stage}.glyph 最多 {GLYPH_MAX} 个非空白字符（版本号 / 单字），不是标题")
        for token in glyph.split():
            if _normalize(token) not in names:
                raise ValueError(f"{stage}.glyph 的「{token}」没有出现在{where}里；标号只能取锚点本身")
    subject = str(item.get("subject") or "")
    for word in ABSTRACT_METAPHORS:
        if word in subject and word not in names:
            raise ValueError(
                f"{stage}.subject 用了论点隐喻道具「{word}」；它换到任何一篇讲取舍 / 降价的文章都成立，"
                f"读者认不出是这篇。改画锚点「{anchor}」本身（music.md §封面画锚点）"
            )


def _check_subject(stage: str, item: dict, evidence: str) -> None:
    subject = item.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError(f"{stage}.subject 必须非空：一句话写清唯一主体是什么、在做什么")
    compact = _normalize(subject)
    if len(compact) < 4:
        raise ValueError(f"{stage}.subject 太短，写清主体的形状与动作（至少 4 字）")
    if len(compact) > 80:
        raise ValueError(f"{stage}.subject 超过 80 字，缩略图只装得下一个主体，不要写成场景描述")
    if subject.count("、") >= 2 or subject.count("，") >= 3:
        raise ValueError(f"{stage}.subject 罗列了多个物件；封面只能有一个主体，把别的去掉")
    # 声明了 glyph（短标号）时，主体里可以提到「字母 / 字样 / 字体」来描述这个标号怎么做；
    # 标题、歌名、logo、水印、slogan 仍一律不许。
    allowed = GLYPH_SHAPE_WORDS if item.get("glyph") else ()
    for word in TEXT_WORDS:
        if word in subject and word not in allowed:
            raise ValueError(f"{stage}.subject 含「{word}」；封面只允许 glyph 里的短标号，主体本身要能说明主题")
    compact_evidence = _normalize(evidence)
    for prop in GENERIC_PROPS:
        if prop in subject and prop not in compact_evidence:
            raise ValueError(
                f"{stage}.subject 用了通用道具「{prop}」，但歌词 / 正文依据里没有它；"
                "换成能指向本篇的主体（前几篇已经连着出了五次书桌台灯落日窗）"
            )


def _cover_plan(
    article_dir: Path, stages: list[str], body: str, *, title: str = "", song: str = ""
) -> dict[str, dict]:
    path = article_dir / COVER_PLAN
    if not path.is_file():
        raise ValueError(f"缺 {COVER_PLAN}；先按 music.md 写明两张封面的唯一主体、依据与调色板")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError(
            f"{COVER_PLAN} 的 schema_version 必须为 {PLAN_SCHEMA}（画锚点：identity 必填，单主体、调色板）；"
            "旧规划按 music.md §封面画锚点 重写"
        )
    brief_path = article_dir / MUSIC_BRIEF
    brief = _normalize(brief_path.read_text(encoding="utf-8", errors="replace")) if brief_path.is_file() else ""
    compact_body = _normalize(body)
    for stage in stages:
        item = plan.get(stage)
        if not isinstance(item, dict):
            raise ValueError(f"{COVER_PLAN} 缺 {stage}")
        anchor = item.get("article_anchor")
        if not isinstance(anchor, str) or not anchor.strip():
            raise ValueError(f"{stage}.article_anchor 必须非空")
        if len(_normalize(anchor)) < 8 or _normalize(anchor) not in compact_body:
            raise ValueError(f"{stage}.article_anchor 必须引用正文中的具体内容（至少 8 字符），不能只填产品名")
        evidence = anchor
        if stage == "theme_cover":
            lyric = item.get("lyric_anchor")
            if not isinstance(lyric, str) or len(_normalize(lyric)) < 4:
                raise ValueError("theme_cover.lyric_anchor 必须是歌名或歌词里的一句（至少 4 字）；主体要从它长出来")
            if brief and _normalize(lyric) not in brief:
                raise ValueError(f"theme_cover.lyric_anchor 在 {MUSIC_BRIEF} 里找不到，只能引用真实歌名或歌词")
            evidence += lyric
        identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
        _check_subject(stage, item, evidence + str(identity.get("reason") or ""))
        _check_identity(stage, item, title=title, song=song)
        palette = item.get("palette")
        if palette not in PALETTES:
            raise ValueError(f"{stage}.palette 必须是 {', '.join(PALETTES)} 之一，当前：{palette!r}")
        render = item.get("render", DEFAULT_RENDER)
        if render not in RENDERS:
            raise ValueError(f"{stage}.render 必须是 {', '.join(RENDERS)} 之一，当前：{render!r}")
        if "display_title" in item or "scene" in item:
            raise ValueError(f"{stage} 仍带 scene / display_title；schema {PLAN_SCHEMA} 只认 subject，文字只允许 glyph 短标号")
    # 即使只补一张，也核对规划中两张图主体、调色板都不同。
    both = [plan.get(key) for key in ("theme_cover", "podcast_cover")]
    if all(isinstance(item, dict) for item in both):
        theme, podcast = both
        if isinstance(theme.get("subject"), str) and isinstance(podcast.get("subject"), str) \
                and _normalize(theme["subject"]) == _normalize(podcast["subject"]):
            raise ValueError("主题曲与播客封面不能使用同一主体；分别表现歌曲意象和文章核心对象")
        if theme.get("palette") and theme.get("palette") == podcast.get("palette"):
            raise ValueError("主题曲与播客封面不能用同一调色板；两张并排时先靠颜色分开")
    if "theme_cover" in stages:
        palette = plan["theme_cover"]["palette"]
        recent = _recent_theme_palettes(article_dir)
        clash = [name for name, used in recent.items() if used == palette]
        if clash:
            raise ValueError(
                f"theme_cover.palette「{palette}」前 {RECENT_PALETTE_WINDOW} 篇刚用过（{', '.join(clash)}）；"
                f"换一个：{', '.join(k for k in PALETTES if k not in recent.values())}"
            )
    return plan


def _theme_title(article_dir: Path) -> str:
    manifest = article_dir / MUSIC_MANIFEST_FILE
    if not manifest.is_file():
        return ""
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    theme = payload.get("theme") if isinstance(payload, dict) else None
    return str((theme or {}).get("title") or "").strip()


def _icon_rules(plan: dict) -> str:
    palette = PALETTES[plan["palette"]]
    render = RENDERS[plan.get("render", DEFAULT_RENDER)]
    glyph = str(plan.get("glyph") or "").strip()
    identity = plan.get("identity") or {}
    if glyph:
        text_rule = (
            f"The ONLY legible characters in the whole image are \"{glyph}\", large and bold, formed as part of "
            "the subject in the same material and light, readable at 46 pixels. No other letters, words, "
            "titles, lyrics, logos, labels, watermarks, signatures or UI elements.\n"
        )
    else:
        text_rule = (
            "Strictly no text of any kind: no letters, numerals, titles, lyrics, logos, labels, watermarks, "
            "signatures or UI elements.\n"
        )
    return (
        f"Identity: a viewer who sees the title next to this icon must think of \"{identity.get('anchor', '')}\" "
        f"at once ({identity.get('route', '')}: {identity.get('reason', '')}). Evoke public colours and basic "
        "shapes if needed, but never reproduce a real company logo.\n"
        f"ONE subject only (a tight pair counts as one when the anchor names two things): {plan['subject']}\n"
        "Composition: the subject is centered and fills roughly two thirds of the frame; its whole "
        "silhouette stays inside the frame, nothing cropped. Nothing else is in the picture: no room, "
        "window, table, landscape, sky, floor scene, secondary props, particles or decorative border.\n"
        f"Background: a flat {palette['bg']} field with only a soft vignette.\n"
        f"Light and colour: a single {palette['accent']} key light; the subject reads as one bright, simple "
        "shape against the dark ground. Large smooth forms, strong silhouette contrast, no fine texture, "
        "thin lines, tiny parts or busy detail — it must still be recognizable at 64 pixels.\n"
        f"Rendering: {render}.\n" + text_rule
    )


def build_theme_cover_prompt(song_title: str, digest: str, *, article_title: str, plan: dict) -> str:
    return (
        f'Square 1:1 cover artwork for the Mandarin song "{song_title}" (from the article "{article_title}"). '
        "It is shown as a 46–66 pixel icon in a music player, so design it like an app icon: one bold "
        "silhouette, one colour, no words.\n"
        f"What the subject stands for: the lyric \"{plan['lyric_anchor']}\"; article evidence: "
        f"\"{plan['article_anchor']}\"; article summary: {digest}\n" + _icon_rules(plan)
    )


def build_podcast_cover_prompt(article_title: str, digest: str, *, plan: dict) -> str:
    return (
        f'Square 1:1 cover artwork for a Mandarin talk podcast episode about the article "{article_title}". '
        "It is shown as a 46–66 pixel icon in a podcast list, so design it like an app icon: one bold "
        "silhouette, one colour, no words.\n"
        f"What the subject stands for: the article's core object or question — \"{plan['article_anchor']}\"; "
        f"article summary: {digest}\n" + _icon_rules(plan)
    )


def _log(article_dir: Path, record: dict[str, Any]) -> None:
    record = {"at": datetime.now(timezone.utc).isoformat(), **record}
    with (article_dir / GEN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_thumb_sheet(article_dir: Path, covers: list[Path]) -> Path | None:
    """把封面按官网实际显示尺寸排成一张核对图；PIL 缺失或图片无效时静默跳过，不拦交付。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover
        return None
    labels = {THEME_COVER.name: "theme cover", PODCAST_COVER.name: "podcast cover"}
    rows = []
    for path in covers:
        try:
            # PIL 默认字体没有中文，标签用英文名。
            rows.append((labels.get(path.name, path.stem), Image.open(path).convert("RGB")))
        except Exception:
            continue
    if not rows:
        return None
    gap, label_h = 24, 18
    width = sum(THUMB_SIZES) + gap * (len(THUMB_SIZES) + 1)
    row_h = THUMB_SIZES[0] + label_h + gap
    sheet = Image.new("RGB", (width, row_h * len(rows)), "#F4F4F2")
    draw = ImageDraw.Draw(sheet)
    for row, (name, image) in enumerate(rows):
        y = row * row_h
        draw.text((gap, y + 2), name, fill="#333333")
        x = gap
        for size in THUMB_SIZES:
            thumb = image.resize((size, size), Image.LANCZOS)
            sheet.paste(thumb, (x, y + label_h + (THUMB_SIZES[0] - size)))
            draw.text((x, y + label_h + THUMB_SIZES[0] + 2), f"{size}px", fill="#666666")
            x += size + gap
    out = article_dir / COVER_THUMBS
    sheet.save(out)
    return out


def _render_one(
    article_dir: Path,
    *,
    stage: str,
    prompt_file: Path,
    output: Path,
    command: list[str],
    renderers: list[dict[str, Any]],
) -> list[str]:
    """按策略顺序尝试；每个 renderer 内部只对 lock_busy 重试。"""
    errors: list[str] = []
    for renderer in renderers:
        args = list(command) + [
            "--promptfiles", str(prompt_file),
            "--image", str(output),
            "--quality", str(renderer.get("quality") or "2k"),
            "--imageSize", str(renderer.get("imageSize") or "1K"),
        ]
        if renderer.get("provider"):
            args += ["--provider", str(renderer["provider"])]
        if renderer.get("model"):
            args += ["--model", str(renderer["model"])]
        for attempt in range(1, LOCK_RETRY_LIMIT + 1):
            completed = subprocess.run(
                args, cwd=str(article_dir), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=900, check=False,
            )
            combined = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
                _log(article_dir, {
                    "stage": stage, "renderer": "baoyu-image-gen",
                    "provider": renderer.get("provider"), "model": renderer.get("model"),
                    "attempt": attempt, "output": str(output.relative_to(article_dir)),
                    "prompt": str(prompt_file.relative_to(article_dir)),
                })
                return []
            if LOCK_BUSY_MARK in combined and attempt < LOCK_RETRY_LIMIT:
                time.sleep(LOCK_RETRY_SECONDS)
                continue
            errors.append(
                f"{stage} renderer {renderer.get('id')} 失败（exit={completed.returncode}）："
                f"{combined.strip()[-300:]}"
            )
            break
    return errors


def _recheck_blind_match(article_dir: Path, stage_paths: dict[str, Path]) -> list[str]:
    """封面都已存在时沿用已有盲配结论：配错的结论不因重跑 handoff 而消失。"""
    if recheck_blind_match is None:
        return []
    try:
        title = _article_context(article_dir)[0]
    except (OSError, ValueError, yaml.YAMLError):
        title = ""
    outcome = recheck_blind_match(
        article_dir, stage_paths, article_title=title, exclude_seq=_article_number(article_dir),
    )
    for warning in outcome.get("warnings") or []:
        print(f"⚠️ {warning}", file=sys.stderr)
    return list(outcome.get("errors") or [])


def ensure_audio_covers(
    article_dir: Path, *, force: bool = False
) -> tuple[list[Path], list[str]]:
    """保证主题曲封面（必需）与播客封面（有播客才需要）存在；返回 (就位文件, 错误)。"""
    article_dir = Path(article_dir).resolve()
    if not article_dir.is_dir():
        return [], [f"文章目录不存在：{article_dir}"]
    song = _theme_title(article_dir)

    jobs: list[tuple[str, str]] = []
    if not song:
        return [], [f"缺 {MUSIC_MANIFEST_FILE} 或其中无歌名，无法生成主题曲封面"]
    jobs.append(("theme_cover", "theme"))
    if (article_dir / PODCAST_MANIFEST).is_file():
        jobs.append(("podcast_cover", "podcast"))

    ready: list[Path] = []
    pending: list[tuple[str, Path]] = []
    stage_paths: dict[str, Path] = {}
    for stage, kind in jobs:
        target = cover_output(article_dir, kind=kind, force=force)
        if target.is_file() and target.stat().st_size > 0 and not force:
            ready.append(target)
            stage_paths[stage] = target
        else:
            pending.append((stage, target))
    if not pending:
        write_thumb_sheet(article_dir, ready)
        return ready, _recheck_blind_match(article_dir, stage_paths)

    try:
        title, digest, body = _article_context(article_dir)
        if not title or not body.strip():
            raise ValueError("缺文章标题或正文，不能用通用场景代替音频封面的主题")
        plan = _cover_plan(article_dir, [stage for stage, _ in pending], body, title=title, song=song)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return ready, [str(exc)]

    command, _revision, errors = resolve_renderer_command()
    if errors or command is None:
        return ready, errors
    renderers, policy_errors = _load_policy(article_dir)
    if policy_errors:
        return ready, policy_errors
    (article_dir / PROMPT_DIR).mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    newly_generated: dict[str, Path] = {}
    for stage, target in pending:
        prompt = (build_theme_cover_prompt(song, digest, article_title=title, plan=plan[stage])
                  if stage == "theme_cover" else
                  build_podcast_cover_prompt(title, digest, plan=plan[stage]))
        prompt_file = article_dir / PROMPT_DIR / f"{target.stem}.md"
        prompt_file.write_text(prompt + "\n", encoding="utf-8")
        item_errors = _render_one(
            article_dir, stage=stage, prompt_file=prompt_file,
            output=target, command=command, renderers=renderers,
        )
        if item_errors:
            failures.extend(item_errors)
        else:
            ready.append(target)
            stage_paths[stage] = target
            newly_generated[stage] = target
    if failures:
        return ready, failures

    write_thumb_sheet(article_dir, ready)

    # 只有本次真的新出了封面（含 --force 重出）才跑盲配（references/music.md
    # §验收：盲配测试）；单纯复用已有封面时 pending 早已在上面清空并直接 return，
    # 走不到这里。盲配对象是当前就位的两张（或仅有的那一张），不止新出的那张——
    # 判断力是「两张放在一起分不分得开」，只测新的那张会漏掉「新旧两张现在撞了」。
    if newly_generated:
        if run_blind_match is None:
            print("⚠️ cover_blind_match 不可用（依赖缺失），已跳过 46px 盲配", file=sys.stderr)
        else:
            outcome = run_blind_match(
                article_dir, stage_paths, article_title=title, exclude_seq=_article_number(article_dir),
            )
            for warning in outcome.get("warnings") or []:
                print(f"⚠️ {warning}", file=sys.stderr)
            blind_errors = outcome.get("errors") or []
            if blind_errors:
                failures.extend(blind_errors)
    return ready, failures


def _main() -> int:
    parser = argparse.ArgumentParser(description="生成缺失的音乐封面 / 播客封面（文章编号文件夹第一层）")
    parser.add_argument("article_dir", nargs="?", default=".")
    parser.add_argument("--force", action="store_true", help="已存在也重新生成")
    parser.add_argument("--thumbs", action="store_true", help="只重排 _audio-cover-thumbs.png 核对图，不出图")
    args = parser.parse_args()
    article_dir = Path(args.article_dir).resolve()
    if args.thumbs:
        covers = [p for p in (article_dir / THEME_COVER, article_dir / PODCAST_COVER) if p.is_file()]
        out = write_thumb_sheet(article_dir, covers)
        print(f"✅ {out}" if out else "❌ 没有可排的封面")
        return 0 if out else 2
    ready, errors = ensure_audio_covers(article_dir, force=args.force)
    for path in ready:
        print(f"✅ {path}")
    thumbs = article_dir / COVER_THUMBS
    if thumbs.is_file():
        print(f"👀 缩略核对图：{thumbs}")
    if errors:
        print("❌ 封面生成失败：")
        for error in errors:
            print(f"   • {error}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
