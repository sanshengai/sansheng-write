#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — 微信公众号写作流水线管理器
==============================================
在文章工作目录（<数据目录>/{N}-{选题名}/）下运行，管理文章全流程进度。

流程顺序：
  outline → writing+title → cover → infographic → bgm → layout → logo → publish → archive
  BGM 以文章本地 _music-manifest.json 为来源真源；自动生成、网页生成和复用成品共用同一硬门。
  writing 阶段内部还含 prep_writing→开头盲选→内容增强→磨稿→冷读外审 五个无状态子步骤，
  不在 STAGE_ORDER 记账，详见 autopilot.md。

用法（在文章目录下执行）：
  python SKILL/scripts/pipeline.py init                     初始化 .state.json
  python SKILL/scripts/pipeline.py status                   查看进度 + 下一步建议
  python SKILL/scripts/pipeline.py next                     打印下一阶段操作说明
  python SKILL/scripts/pipeline.py verify <stage>           验证阶段是否完成（通过则自动标 done）
  python SKILL/scripts/pipeline.py done <stage> [k=v ...]   手动标记完成 + 写入元数据
  python SKILL/scripts/pipeline.py skip <stage>             跳过某阶段
  python SKILL/scripts/pipeline.py reset <stage>            重置阶段为 pending
  python SKILL/scripts/pipeline.py log <stage> <tool> ...   记录生图来源到 .gen-log.jsonl
  python SKILL/scripts/pipeline.py release-to-draft         唯一草稿发布事务
  python SKILL/scripts/pipeline.py wechat-published-audio-check <wechat_url> --confirm-audition
                                                            草稿被回收后的正式文章补验
  python SKILL/scripts/pipeline.py archive                  发布归档：写解析后的作品库 + 刷新派生视图
  python SKILL/scripts/pipeline.py finalize <wechat_url>    正式发布收尾：登记链接 + 归档 + 验证
  python SKILL/scripts/pipeline.py history                  [DEPRECATED] 改用 archive
  python SKILL/scripts/pipeline.py orchestrator on|off      切换编排器并行/串行（默认 on）

示例（$SKILL = 本 skill 根目录，$DATA = 数据目录）：
  cd "$DATA/18-安利读书软件"
  python "$SKILL/scripts/pipeline.py" init
  python "$SKILL/scripts/pipeline.py" status
  python "$SKILL/scripts/pipeline.py" verify layout
  python "$SKILL/scripts/pipeline.py" finalize https://mp.weixin.qq.com/s/xxx
"""

import json
import copy
import os
import re
import subprocess
import sys
import argparse
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Windows 控制台 GBK 兜底：强制 stdout/stderr UTF-8，避免 emoji 触发 UnicodeEncodeError
# （否则 Windows 上每次都要手动 PYTHONUTF8=1，这里内置根治）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

# 让 pipeline.py 从文章目录被调用时也能 import 兄弟模块 works_registry / render_*
import os as _os
_SCRIPTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from evidence import (  # noqa: E402
    CHECKPOINT_RECEIPT_FILE,
    FINAL_PROMPT_PREFIX,
    PUBLISH_READY_FILE,
    PUBLISH_RECEIPT_FILE,
    VISUAL_RECEIPT_FILE,
    build_publish_manifest,
    checkpoint_artifact,
    cover_prompt_banned_terms,
    files_digest,
    norm_relpath as _evidence_norm_relpath,
    seal_visual_receipt,
    sha256_file,
    stable_digest,
    verify_checkpoint_receipt,
    verify_publish_receipt,
    verify_publish_ready,
    verify_visual_receipt,
    write_checkpoint_receipt,
    write_publish_receipt,
    write_publish_ready,
)
from profile_config import brand  # noqa: E402

# ── 常量 ──────────────────────────────────────────────────────
STATE_FILE = ".state.json"
FINALIZE_STATE_FILE = "_finalize-state.json"
FINALIZE_STATE_SCHEMA = 2
SKILL_DIR = Path(__file__).resolve().parent.parent   # 本 skill 根目录
# (HISTORY_FILE 常量已随 cmd_history 死代码一并移除 2026-06-20；history.yaml 已被 works.yaml 取代，
#  仅 migrate_to_works.py 一次性迁移工具读它、且自带独立路径)

STAGE_ORDER = [
    "outline",
    "writing",
    "cover",
    "infographic",
    "bgm",
    "layout",
    "logo",
    "publish",
    "archive",
]
STAGE_LABELS = {
    "outline":     "选题 + 大纲",
    "writing":     "正文写作 + 标题锻造",
    "cover":       "视觉任务单 + 封面（sansheng-write.visual-planner）",
    "infographic": "Hero + 信息图 ≥ 4 张（visual planner 编译，baoyu-image-gen 渲染）",
    "bgm":         "主题音乐（_music-manifest.json 绑定真实来源）",
    "layout":      "微信排版（baoyu-skills:baoyu-markdown-to-html + format_layout.py）",
    "logo":        "品牌水印（add_logo.js）",
    "publish":     "草稿事务（预检 + draft/add + 官方 draft/get 读回）",
    "archive":     "发布后沉淀（pipeline.py archive 写作品库 + 自动刷新 articles.md/看板/推荐）",
}

def _skill_path(rel: str) -> str:
    return str(SKILL_DIR / rel).replace("\\", "/")

STAGE_HINTS = {
    "outline": (
        "读取 references/outline.md，完成选题快评 + 大纲，输出 大纲.md。\n"
        "  完成后：pipeline.py verify outline"
    ),
    "writing": (
        "读取 references/writing.md 展开正文，完成后读 references/title.md 锻造标题。\n"
        "  完成后：pipeline.py done writing title_final='文章标题'"
    ),
    "cover": (
        "🔁 进配图前回扣 checklist：确认 开头盲选已停顿（_opening-choice.md）/ "
        "content_enhance 已产出 / 冷读外审 _stutter-list.md 已生成（跨会话恢复时这三步无状态记账，易静默漏）。\n"
        "写 visual-plan.json，然后执行 pipeline.py compile-visuals 与 render-visuals。\n"
        "  业务 producer 固定为 sansheng-write.visual-planner；外部 renderer 只负责像素。\n"
        "  完成后：pipeline.py verify cover"
    ),
    "infographic": (
        "核验 visual-plan 编译出的信息图 ≥ 4 张（开篇 9:16 + 中间 16:9×N + 结尾 9:16）；\n"
        "  精确数据图走独立本地代码路径；封面、Hero、信息图均由 visual planner 编译并经 baoyu-image-gen 渲染。\n"
        "  完成后：pipeline.py verify infographic"
    ),
    "bgm": (
        "读取 references/music.md 选择真实通道：Lyria 可自动生成；网页生成或复用成品\n"
        "  用 music_manifest.py create 绑定实际文件、provider/model/mode 与注册表引用。\n"
        "  已有 manifest 时先 verify --probe-duration；不得按文件名、时间戳或候选 MP3 猜来源。\n"
        "  🔴 必须在 layout（MD→HTML）之前跑：先插卡进 定稿.md，排版才会渲染出音频卡片。\n"
        "  完成后：pipeline.py verify bgm"
    ),
    "layout": (
        f'⓪ python "{_skill_path("scripts/normalize_cjk_punctuation.py")}" 定稿.md'
        "（中文半角标点转全角，MD→HTML 前置；done writing 已自动跑过则 0 处、空跑）\n"
        "① /baoyu-skills:baoyu-markdown-to-html 定稿.md --theme default --color '#2F6F8F' --keep-title\n"
        "     🔴 必带 --keep-title：本 skill 正文无 H1（标题在 frontmatter），baoyu 默认会把首个 H2 当标题吃掉\n"
        "        → H2 少一个、format_layout 报「H2≠part_subtitles」退出（详见 layout.md，曾两次踩坑）\n"
        f'  ② python "{_skill_path("scripts/format_layout.py")}" 定稿.html --all \\\n'
        "       --lead-line1 '...' --lead-line2 '...' --lead-subtitle '...' --lead-tag1 '...' --lead-tag2 '...'\n"
        "  完成后：pipeline.py verify layout"
    ),
    "logo": (
        f'node "{_skill_path("scripts/add_logo.js")}" "素材/*.png"\n'
        f'  python "{_skill_path("scripts/compress_images.py")}" 素材/ --max-mb 2\n'
        "  执行 pipeline.py visual-qa（独立看图进程产 _visual-qa.json），再 seal visual\n"
        "  完成后：pipeline.py done logo"
    ),
    "publish": (
        "🔴 唯一入口：pipeline.py release-to-draft。\n"
        "  命令内部完成 release job、publish preflight、草稿创建与官方 draft/get 读回；不可拆开。\n"
        "🔴 article-meta.yaml 的 title 已是最终对外标题，必须自带「{对外分类中文名} | 」前缀；发布、作品库、网站/RSS 共用这一份，不得二次拼接。\n"
        "   对外分类由 outward_category 决定；发布直接使用 article-meta.title。\n"
        "  微信后台手动发布，获得链接后：pipeline.py finalize https://mp.weixin.qq.com/s/xxx"
    ),
    "archive": (
        # 二期C：发布即写作品库（单一数据源），自动分配 code + 刷新派生视图
        "先确认 article-meta.yaml 已填 category（AIT/TUT/OBS/ROB/KID/ESS）/ outward_category（对外6类，AIT/OBS 必填）/ tags / digest，然后：\n"
        f'  python "{_skill_path("scripts/pipeline.py")}" finalize https://mp.weixin.qq.com/s/xxx\n'
        "  （串起登记永久链接 → 写作品库 → 刷新 articles.md / works-dashboard.html / recommend_articles.html → 验证）"
    ),
}

STATUS_ICON = {
    "pending": "⬜",
    "doing":   "🔄",
    "done":    "✅",
    "skip":    "⏭ ",
    "failed":  "❌",
    "dirty":   "🟡",
    "adopted": "📥",
    "waiting_author": "⏸ ",
}

# ── 生图路由白名单 ─────────────────────────────────────────────
# 在本 skill 流水线内，封面图/信息图/数据图三类必须走受控入口，
# 禁用通用 generate_image 工具（它只会输出 1:1 方图，AR 无法控制）。
#
# producer / method source / renderer 三层分离。最终文章视觉只认本仓 planner；
# 宝玉文章配图与信息图是方法来源，像素后端只认 baoyu-image-gen。
VISUAL_PRODUCER = "sansheng-write.visual-planner"
IMAGE_TOOL_WHITELIST = {
    # 公众号文章的 cover / hero / infographic 语义合同由本仓 visual planner 编译。
    # baoyu-image-gen 只作为 renderer，不再要求宿主模型跨 Skill 调语义 producer。
    "cover":       {VISUAL_PRODUCER},
    "infographic": {VISUAL_PRODUCER},
    "illustrator": {VISUAL_PRODUCER},
    "chart":       {"matplotlib", "pyecharts", "plot_local"},  # 数据图必须本地脚本渲染
}
IMAGE_TOOL_BLACKLIST = {"generate_image", "internal_image_gen", "imagine"}
_ALLOWED_INFO_STYLES = ("claymation", "morandi-journal", "craft-handmade")


def _infographic_style_error(record: dict) -> str:
    """Validate the structured renderer contract, with legacy CLI-log fallback."""
    style = str(record.get("style") or "").strip()
    cmd_str = str(record.get("cmd") or "")
    if not style:
        match = re.search(r"--style\s+[\"']?([^\s\"']+)", cmd_str)
        style = match.group(1) if match else ""
    if not style:
        return (
            "infographic 生成记录缺 style。信息图统一用 "
            "claymation / morandi-journal 二选一（image-routing.md），不可漂移"
        )
    if style not in _ALLOWED_INFO_STYLES:
        return (
            f"infographic 使用了 style={style}，不在允许集 "
            "{claymation / morandi-journal / craft-handmade}。"
            "image-routing.md 已固化 claymation/morandi-journal 二选一"
            "（craft-handmade 仅历史兼容）"
        )
    return ""
IMAGE_RENDERER_WHITELIST = {"baoyu-image-gen"}

GEN_LOG_FILE = ".gen-log.jsonl"


# ── State 读写 ────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ── 生图日志 ──────────────────────────────────────────────────
def _read_gen_log(cwd: Path, stage: str) -> list:
    """读取 .gen-log.jsonl，返回某 stage 对应的所有生图记录。"""
    log_path = cwd / GEN_LOG_FILE
    if not log_path.exists():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rec = json.loads(line)
            if rec.get("stage") == stage:
                records.append(rec)
        except json.JSONDecodeError:
            continue
    return records


def _image_metadata(png_path: Path) -> dict:
    """读取 PNG 的宽、高、长边。Pillow 未装或文件损坏时返回 {}。"""
    try:
        from PIL import Image
        with Image.open(png_path) as img:
            w, h = img.size
            return {"w": w, "h": h, "long_edge": max(w, h), "ratio_wh": w / h}
    except Exception:
        return {}


def _norm_relpath(value: str) -> str:
    """把日志/JSON 里的 Windows 或 POSIX 相对路径归一成可比较形式。"""
    return str(value or "").replace("\\", "/").removeprefix("./")


def _visual_recipe(name: str = "") -> dict:
    """读取当前 profile 的视觉配方，并附上可复验的稳定摘要。"""
    from profile_config import visual_profile

    recipe = visual_profile(name)
    if not recipe:
        return {}
    recipe = copy.deepcopy(recipe)
    recipe["sha256"] = stable_digest(recipe)
    return recipe


def _prompt_frontmatter(text: str) -> dict:
    if _yaml is None:
        return {}
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|$)", text, flags=re.S)
    if not match:
        return {}
    try:
        value = _yaml.safe_load(match.group(1)) or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _visual_prompt_errors(prompt_text: str, recipe: dict, label: str) -> list[str]:
    """校验 canonical prompt 是否真的携带浅色配方，而非只写 style 名。"""
    if not recipe:
        return [f"{label} 无法解析视觉配方"]
    errors: list[str] = []
    frontmatter = _prompt_frontmatter(prompt_text)
    expected = {
        "visual_profile": recipe.get("name"),
        "visual_profile_sha256": recipe.get("sha256"),
        "visual_contract_owner": recipe.get("contract_owner"),
        "visual_contract_revision": recipe.get("contract_revision"),
        "palette_background": recipe.get("background"),
        "palette_accent": recipe.get("accent"),
    }
    missing_or_drifted = [
        f"{key}={frontmatter.get(key) or '(空)'}"
        for key, value in expected.items()
        if str(frontmatter.get(key) or "").strip().lower()
        != str(value or "").strip().lower()
    ]
    if missing_or_drifted:
        errors.append(
            f"{label} 视觉配方元数据缺失或漂移：{missing_or_drifted}；"
            f"应绑定 {recipe.get('name')} / {recipe.get('sha256', '')[:12]}"
        )

    body_match = re.match(
        r"\A---\s*\r?\n.*?\r?\n---(?:\s*\r?\n|$)(.*)\Z",
        prompt_text,
        flags=re.S,
    )
    body = body_match.group(1) if body_match else prompt_text
    body_lower = body.lower()
    missing_groups = []
    for group in recipe.get("required_prompt_groups") or []:
        choices = [str(item) for item in group if str(item).strip()]
        if choices and not any(choice.lower() in body_lower for choice in choices):
            missing_groups.append("/".join(choices))
    if missing_groups:
        errors.append(f"{label} 视觉配方正文缺关键词组：{missing_groups}")

    negative_marker = re.compile(
        r"\b(?:avoid|without|no|not|never|forbid(?:den)?)\b|不要|禁止|避免|严禁",
        flags=re.I,
    )
    forbidden_hits = set()
    for line in body.splitlines():
        if negative_marker.search(line):
            continue
        low = line.lower()
        for term in recipe.get("forbidden_prompt_terms") or []:
            if str(term).lower() in low:
                forbidden_hits.add(str(term))
    if forbidden_hits:
        errors.append(f"{label} 命中浅色视觉配方禁用色/材质：{sorted(forbidden_hits)}")
    conflicting_phrases = sorted(
        {
            str(phrase)
            for phrase in recipe.get("forbidden_prompt_phrases") or []
            if str(phrase).strip() and str(phrase).lower() in body_lower
        }
    )
    if conflicting_phrases:
        errors.append(f"{label} 命中视觉风格冲突短语：{conflicting_phrases}")
    return errors


def _image_tone_metrics(path: Path) -> dict:
    """以最终像素估算亮度、暗部面积和饱和度；透明区按白底合成。"""
    try:
        from PIL import Image

        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, rgba).convert("RGB")
            image.thumbnail((256, 256))
            pixels = list(image.getdata())
    except Exception:
        return {}
    if not pixels:
        return {}

    lumas = []
    saturations = []
    for red, green, blue in pixels:
        lumas.append(0.2126 * red + 0.7152 * green + 0.0722 * blue)
        high = max(red, green, blue)
        low = min(red, green, blue)
        saturations.append(0.0 if high == 0 else (high - low) / high)
    return {
        "mean_luma": sum(lumas) / len(lumas),
        "mean_saturation": sum(saturations) / len(saturations),
        "lumas": lumas,
    }


def _visual_tone_errors(path: Path, recipe: dict, label: str) -> list[str]:
    metrics = _image_tone_metrics(path)
    if not metrics:
        return [f"{label} 无法读取最终像素，不能执行视觉配方色调门"]
    thresholds = recipe.get("thresholds") or {}
    dark_luma = float(thresholds.get("dark_pixel_luma", 80))
    dark_ratio = (
        sum(1 for value in metrics["lumas"] if value < dark_luma)
        / len(metrics["lumas"])
    )
    mean_luma = float(metrics["mean_luma"])
    mean_saturation = float(metrics["mean_saturation"])
    failed = (
        mean_luma < float(thresholds.get("mean_luma_min", 178))
        or dark_ratio > float(thresholds.get("dark_pixel_ratio_max", 0.18))
        or mean_saturation > float(thresholds.get("mean_saturation_max", 0.30))
    )
    if not failed:
        return []
    return [
        f"{label} 未通过 {recipe.get('name')} 色调门："
        f"平均亮度={mean_luma:.1f}，暗部占比={dark_ratio:.1%}，"
        f"平均饱和度={mean_saturation:.1%}"
    ]


def _visual_route_errors(cwd: Path, *, allow_postprocessed: bool = False) -> list:
    """校验信息图视觉路由的整条证据链，而不只检查 style 是否在枚举里。

    SSOT 是 article-meta.yaml 的 infographic_subject + infographic_style：
    ai-product -> claymation；phenomenon -> morandi-journal。最终图片、final-set、
    最新精确 output 日志、日志引用的 prompt frontmatter 必须全部与 SSOT 一致。
    """
    errors = []
    meta_path = cwd / "article-meta.yaml"
    if not meta_path.exists():
        return ["缺 article-meta.yaml，无法判定信息图视觉路由"]
    if _yaml is None:
        return ["PyYAML 未安装，无法校验信息图视觉路由"]
    try:
        meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"article-meta.yaml 解析失败，无法校验信息图视觉路由：{exc}"]

    style = str(meta.get("infographic_style") or "").strip()
    profile_name = str(meta.get("visual_profile") or "").strip()
    # 全站统一粘土风，不再按 infographic_subject 做风格路由（见 visual_workflow.py 注释）
    if style != "claymation":
        errors.append(
            f"infographic_style 必须是 claymation（全站统一粘土风）；"
            f"当前为 {style or '(空)'}"
        )

    recipe = {}
    profile_by_style = {
        "claymation": "warm-light-clay",
        "morandi-journal": "morandi-journal",
    }
    expected_profile = profile_by_style.get(style, "")
    if style == "claymation" and not profile_name:
        errors.append(
            "article-meta.yaml 缺 visual_profile；必须显式写 "
            "visual_profile: warm-light-clay"
        )
    if expected_profile:
        if profile_name and profile_name != expected_profile:
            errors.append(
                f"infographic_style={style} 的 visual_profile 必须为 "
                f"{expected_profile}，当前为 {profile_name}"
            )
        recipe = _visual_recipe(expected_profile)
        if not recipe:
            errors.append(
                f"visual_profile={expected_profile} 无法解析；"
                f"{style} 必须绑定可复验视觉配方"
            )
        elif recipe.get("style") != style:
            errors.append(
                f"visual_profile={recipe.get('name')} 只适用于 {recipe.get('style')}，当前为 {style}"
            )
    elif profile_name:
        errors.append(
            f"infographic_style={style or '(空)'} 不支持 visual_profile={profile_name}"
        )

    for rel in ("素材/infographic/analysis.md", "素材/infographic/structured-content.md"):
        p = cwd / Path(rel)
        if not p.exists():
            errors.append(f"缺 {rel}，视觉路由证据链不完整")
        elif style and style not in p.read_text(encoding="utf-8"):
            errors.append(f"{rel} 未声明 meta 指定 style={style}")

    mat = cwd / "素材"
    final_paths = sorted(mat.glob("infographic*.png")) if mat.exists() else []
    final_rel = [_norm_relpath(str(p.relative_to(cwd))) for p in final_paths]

    final_set_path = mat / "infographic" / "final-set.json"
    final_set_by_path = {}
    if not final_set_path.exists():
        errors.append("缺 素材/infographic/final-set.json，无法核对最终图组")
    else:
        try:
            payload = json.loads(final_set_path.read_text(encoding="utf-8"))
            for item in payload.get("images", []):
                if isinstance(item, dict):
                    final_set_by_path[_norm_relpath(item.get("path", ""))] = item
        except Exception as exc:
            errors.append(f"final-set.json 解析失败：{exc}")

    logs = _read_gen_log(cwd, "infographic")
    latest_by_output = {}
    for rec in logs:
        out = _norm_relpath(rec.get("output", ""))
        if out:
            latest_by_output[out] = rec

    seen_styles = set()
    for rel in final_rel:
        item = final_set_by_path.get(rel)
        if not item:
            errors.append(f"final-set.json 缺最终图 {rel}")
        else:
            item_style = str(item.get("style") or "")
            seen_styles.add(item_style)
            if style and item_style != style:
                errors.append(f"{rel} 的 final-set style={item_style or '(空)'}，应为 {style}")

        rec = latest_by_output.get(rel)
        if not rec:
            errors.append(f"{rel} 缺精确 output 的最新 gen-log 记录")
            continue
        producer = str(rec.get("producer") or rec.get("tool") or "").strip()
        renderer = str(rec.get("renderer") or "").strip()
        model = str(rec.get("model") or "").strip()
        if producer not in IMAGE_TOOL_WHITELIST["infographic"]:
            errors.append(
                f"{rel} producer={producer or '(空)'}；必须经 "
                f"{VISUAL_PRODUCER}"
            )
        if renderer != "baoyu-image-gen":
            errors.append(f"{rel} renderer={renderer or '(空)'}；最终像素必须经 baoyu-image-gen")
        if not model:
            errors.append(f"{rel} 缺 model，生成记录不可复现")
        cmd = str(rec.get("cmd") or "")
        m = re.search(r"--style\s+([^\s]+)", cmd)
        log_style = str(rec.get("style") or (m.group(1).strip("\"'") if m else ""))
        seen_styles.add(log_style)
        if style and log_style != style:
            errors.append(f"{rel} 最新 gen-log style={log_style or '(空)'}，应为 {style}")

        prompt_rel = _norm_relpath(rec.get("prompt", ""))
        if not prompt_rel:
            pm = re.search(r"(?:素材[/\\]prompts[/\\][^\s\"']+\.md)", cmd)
            prompt_rel = _norm_relpath(pm.group(0)) if pm else ""
        if not prompt_rel:
            errors.append(f"{rel} 最新 gen-log 未引用 prompt 文件，无法核对 frontmatter style")
            continue
        if not prompt_rel.startswith(FINAL_PROMPT_PREFIX):
            errors.append(
                f"{rel} 最终 prompt 必须位于 {FINAL_PROMPT_PREFIX}，当前为 {prompt_rel}"
            )
        prompt_path = cwd / Path(prompt_rel)
        if not prompt_path.exists():
            errors.append(f"{rel} 日志引用的 prompt 不存在：{prompt_rel}")
            continue
        prompt_text = prompt_path.read_text(encoding="utf-8")
        if rec.get("prompt_sha256") != sha256_file(prompt_path):
            errors.append(f"{rel} prompt_sha256 与当前 canonical prompt 不一致")
        output_path = cwd / Path(rel)
        if (not allow_postprocessed
                and rec.get("output_sha256") != sha256_file(output_path)):
            errors.append(f"{rel} output_sha256 与当前渲染器输出不一致")
        sm = re.search(r"(?m)^style:\s*[\"']?([^\"'\s]+)", prompt_text)
        prompt_style = sm.group(1) if sm else ""
        seen_styles.add(prompt_style)
        if style and prompt_style != style:
            errors.append(f"{prompt_rel} frontmatter style={prompt_style or '(空)'}，应为 {style}")
        if recipe:
            errors.extend(_visual_prompt_errors(prompt_text, recipe, prompt_rel))
            logged_profile = str(rec.get("visual_profile") or "")
            logged_profile_sha = str(rec.get("visual_profile_sha256") or "")
            logged_owner = str(rec.get("visual_contract_owner") or "")
            logged_revision = str(rec.get("visual_contract_revision") or "")
            if (
                logged_profile != str(recipe.get("name") or "")
                or logged_profile_sha != str(recipe.get("sha256") or "")
                or logged_owner != str(recipe.get("contract_owner") or "")
                or logged_revision != str(recipe.get("contract_revision") or "")
            ):
                errors.append(
                    f"{rel} gen-log 视觉配方={logged_profile or '(空)'} / "
                    f"{logged_profile_sha[:12] or '(空)'} / "
                    f"{logged_owner or '(空)'} / {logged_revision or '(空)'}，应为 "
                    f"{recipe.get('name')} / {recipe.get('sha256', '')[:12]} / "
                    f"{recipe.get('contract_owner')} / {recipe.get('contract_revision')}"
                )
            errors.extend(_visual_tone_errors(output_path, recipe, rel))

    nonempty_styles = {s for s in seen_styles if s}
    if len(nonempty_styles) > 1:
        errors.append(f"最终信息图证据链混入多种 style：{sorted(nonempty_styles)}")

    if recipe:
        hero = mat / "hero.png"
        if hero.exists():
            hero_rel = "素材/hero.png"
            errors.extend(_visual_tone_errors(hero, recipe, hero_rel))
            hero_logs = {
                _norm_relpath(rec.get("output", "")): rec
                for rec in _read_gen_log(cwd, "hero")
                if rec.get("output")
            }
            hero_rec = hero_logs.get(hero_rel)
            if not hero_rec:
                errors.append(
                    f"{hero_rel} 缺生成日志，无法证明 Hero 继承 {recipe.get('name')} 视觉配方"
                )
            else:
                hero_prompt_rel = _norm_relpath(hero_rec.get("prompt", ""))
                hero_prompt = cwd / Path(hero_prompt_rel) if hero_prompt_rel else None
                if not hero_prompt or not hero_prompt.exists():
                    errors.append(f"{hero_rel} 缺 canonical prompt，无法核验视觉配方")
                else:
                    errors.extend(_visual_prompt_errors(
                        hero_prompt.read_text(encoding="utf-8"),
                        recipe,
                        hero_prompt_rel,
                    ))
                    if (
                        str(hero_rec.get("visual_profile") or "") != str(recipe.get("name") or "")
                        or str(hero_rec.get("visual_profile_sha256") or "")
                        != str(recipe.get("sha256") or "")
                        or str(hero_rec.get("visual_contract_owner") or "")
                        != str(recipe.get("contract_owner") or "")
                        or str(hero_rec.get("visual_contract_revision") or "")
                        != str(recipe.get("contract_revision") or "")
                    ):
                        errors.append(
                            f"{hero_rel} gen-log 视觉配方未绑定 "
                            f"{recipe.get('name')} / {recipe.get('sha256', '')[:12]}"
                        )
    return errors


def _cover_route_errors(cwd: Path, *, allow_postprocessed: bool = False) -> list:
    """校验封面语义生产者、像素后端、canonical prompt 与字节证据链。"""
    rel = "素材/cover.png"
    output = cwd / Path(rel)
    if not output.exists():
        return [f"缺 {rel}"]
    latest = {}
    for rec in _read_gen_log(cwd, "cover"):
        out = _norm_relpath(rec.get("output", ""))
        if out:
            latest[out] = rec
    rec = latest.get(rel)
    if not rec:
        return [f"{rel} 缺精确 output 的最终 gen-log 记录"]

    errors = []
    producer = str(rec.get("producer") or rec.get("tool") or "").strip()
    renderer = str(rec.get("renderer") or "").strip()
    model = str(rec.get("model") or "").strip()
    if producer != VISUAL_PRODUCER:
        errors.append(f"{rel} producer={producer or '(空)'}；必须经 {VISUAL_PRODUCER}")
    if renderer != "baoyu-image-gen":
        errors.append(f"{rel} renderer={renderer or '(空)'}；最终像素必须经 baoyu-image-gen")
    if not model:
        errors.append(f"{rel} 缺 model，生成记录不可复现")

    prompt_rel = _norm_relpath(rec.get("prompt", ""))
    if not prompt_rel:
        match = re.search(
            r"(?:素材[/\\]prompts[/\\][^\s\"']+\.md)", str(rec.get("cmd") or "")
        )
        prompt_rel = _norm_relpath(match.group(0)) if match else ""
    if not prompt_rel:
        errors.append(f"{rel} 最终日志缺 prompt 路径")
        return errors
    if not prompt_rel.startswith(FINAL_PROMPT_PREFIX):
        errors.append(f"{rel} 最终 prompt 必须位于 {FINAL_PROMPT_PREFIX}，当前为 {prompt_rel}")
    prompt = cwd / Path(prompt_rel)
    if not prompt.exists():
        errors.append(f"{rel} prompt 不存在：{prompt_rel}")
        return errors
    if rec.get("prompt_sha256") != sha256_file(prompt):
        errors.append(f"{rel} prompt_sha256 与当前 canonical prompt 不一致")
    if (not allow_postprocessed
            and rec.get("output_sha256") != sha256_file(output)):
        errors.append(f"{rel} output_sha256 与当前渲染器输出不一致")
    banned = cover_prompt_banned_terms(prompt.read_text(encoding="utf-8"))
    if banned:
        errors.append(f"封面 canonical prompt 含禁词：{banned}")
    return errors


def _visual_qa_evidence_errors(cwd: Path) -> list:
    """证据层：QA 记录必须存在、可解析，且最终字节 == 复核时的字节。**一律硬拦。**

    字节证据与看图判定分层计算只为精确报错；两层都没有授权旁路。
    """
    qa_path = cwd / "_visual-qa.json"
    if not qa_path.exists():
        return ["缺 _visual-qa.json：生成后必须由独立看图进程验收"]
    try:
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"_visual-qa.json 解析失败：{exc}"]
    try:
        from visual_qa import final_byte_errors
    except ImportError:  # pragma: no cover
        from scripts.visual_qa import final_byte_errors
    return final_byte_errors(cwd, payload)


def _visual_qa_errors(cwd: Path) -> list:
    """发布前视觉 QA 凭证门：只认独立审阅进程产出的结构化合同。"""
    qa_path = cwd / "_visual-qa.json"
    if not qa_path.exists():
        return ["缺 _visual-qa.json：生成后必须由独立看图进程验收"]
    try:
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"_visual-qa.json 解析失败：{exc}"]
    try:
        from visual_qa import validate_qa_result
    except ImportError:  # pragma: no cover
        from scripts.visual_qa import validate_qa_result
    return validate_qa_result(cwd, payload)


def load_state(cwd: Path) -> dict:
    state_path = cwd / STATE_FILE
    if not state_path.exists():
        sys.exit(
            f"❌ 未找到 {STATE_FILE}。\n"
            f"   请先运行：python pipeline.py init"
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    changed = False
    if int(state.get("schema_version") or 1) < 2:
        state["schema_version"] = 2
        # article-meta.yaml 是内容配置 SSOT；state 只保存流水线状态。
        state.pop("style", None)
        state.pop("lead_params", None)
        for info in state.get("stages", {}).values():
            old = info.get("finished_at")
            if old and not info.get("first_completed_at"):
                info["first_completed_at"] = old
            if old and not info.get("last_verified_at"):
                info["last_verified_at"] = old
        changed = True
    # v2 起 article-meta.yaml 是内容配置唯一真源；即使手工回填也自动清理。
    for duplicate in ("style", "lead_params"):
        if duplicate in state:
            state.pop(duplicate, None)
            changed = True
    if not state.get("run_id"):
        state["run_id"] = str(uuid.uuid4())
        changed = True
    if changed:
        save_state(cwd, state)
    return state


def save_state(cwd: Path, state: dict):
    state["updated_at"] = _now_iso()
    (cwd / STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cmd_init(cwd: Path):
    state_path = cwd / STATE_FILE
    if state_path.exists():
        ans = input(f"⚠️  {STATE_FILE} 已存在，覆盖？(y/N) ").strip().lower()
        if ans != "y":
            print("已取消。")
            return
    topic_id = cwd.name
    state = {
        "schema_version": 2,
        "topic_id": topic_id,
        "topic_dir": str(cwd),
        "run_id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "stages": {s: {"status": "pending"} for s in STAGE_ORDER},
        "notes": [],
    }
    # P0.2：编排重构契约字段（只新增，不改既有阶段语义）
    # - orchestrator：全局回滚开关。init 即重置为默认 on；重 init 的保护
    #   由上面的"覆盖?"确认提示负责，不在此层（此处 state 是新建字面量）
    # - state_writer：单一状态写者标记
    state["orchestrator"] = "on"
    state["state_writer"] = "orchestrator"
    save_state(cwd, state)
    print(f"✅ 已初始化 {state_path}")
    print(f"   主题：{topic_id}")
    print(f"   下一步：pipeline.py status")


# ── Verify 逻辑 ───────────────────────────────────────────────
def _checkpoint_errors(stage: str, cwd: Path) -> list:
    """profile 启用的人工闸门断言（brand.yaml workflow.checkpoints，
    见 profile_config.workflow_checkpoints）。未启用返回空 = 原全自动行为。

    锚点文件 = 作者拍板的可恢复证据（选定项 / 改动意见 / 时间；作者明说
    「免检 / 一路到底」时写入免检授权同样放行），杜绝跨会话恢复静默跳闸。
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from profile_config import workflow_checkpoints
        cps = workflow_checkpoints()
    except Exception:
        return []
    gates = {
        "outline": ("blueprint", "_blueprint-approval.md",
                    "蓝图闸：把「大纲 + 5 标题/封面方案 + 开头候选 + 视觉路由」一包交作者拍板"),
        "writing": ("draft", "_draft-approval.md",
                    "定稿闸：磨稿 + 外审修复后的 定稿.md 交作者审读"),
    }
    gate = gates.get(stage)
    if not gate:
        return []
    name, anchor, desc = gate
    if name in cps and not (cwd / anchor).exists():
        return [f"checkpoint:{name} 未过 -- {desc}，作者回复后把结论落 {anchor} 再继续"
                f"（作者明说免检时写入『作者免检授权』放行）"]
    if name == "blueprint" and name in cps:
        text = (cwd / anchor).read_text(encoding="utf-8")
        if "作者免检授权" not in text:
            missing = []
            has_five = all(re.search(rf"方案\s*{n}", text) for n in range(1, 6))
            if not has_five and "作者指定标题" not in text:
                missing.append("5 套标题+封面文案（或作者指定标题）")
            if "开头" not in text:
                missing.append("开头选择")
            if "大纲" not in text:
                missing.append("大纲结论")
            if "封面风格" not in text:
                missing.append("封面风格")
            # 信息图主题/风格不再进闸门：全站统一粘土风，没有可选项，
            # 再要求写一遍只是仪式。「信息图主题」正是当初诱导判断出错的那个字段。
            if missing:
                return [
                    f"checkpoint:blueprint 锚点结构不完整：缺 {missing}；"
                    f"补齐 {anchor} 后再继续"
                ]
    if name in cps:
        receipt_errors = verify_checkpoint_receipt(cwd, name)
        if receipt_errors:
            return [f"checkpoint:{name} receipt 未通过 -- {e}" for e in receipt_errors]
    return []


def _archive_metadata(cwd: Path, state: dict, *, require_url: bool = False,
                      override: dict | None = None) -> tuple[dict, dict, list[str]]:
    """读取并校验归档元数据，供发布前门、archive 与 verify archive 共用。"""
    from works_registry import (CATEGORY_CODES, OUTWARD_CATEGORIES, TAG_VOCAB,
                                suggest_outward)

    override = override or {}
    errors: list[str] = []
    meta_path = cwd / "article-meta.yaml"
    meta: dict = {}
    if not meta_path.exists():
        errors.append("article-meta.yaml 不存在")
    elif _yaml is None:
        errors.append("缺少 PyYAML，无法读取 article-meta.yaml")
    else:
        try:
            loaded = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                errors.append("article-meta.yaml 顶层必须是对象")
            else:
                meta = loaded
        except Exception as exc:
            errors.append(f"article-meta.yaml 解析失败：{exc}")

    category = override.get("category") or meta.get("category", "")
    if category not in CATEGORY_CODES:
        errors.append(f"category 缺失或非法（需 {sorted(CATEGORY_CODES)}）")

    outward = override.get("outward_category") or meta.get("outward_category", "")
    if not outward and category in CATEGORY_CODES:
        suggested, needs_review = suggest_outward(category)
        if suggested and not needs_review:
            outward = suggested
        else:
            errors.append(
                f"outward_category 未填且 category={category} 需人工判（需 {sorted(OUTWARD_CATEGORIES)}）"
            )
    elif outward not in OUTWARD_CATEGORIES:
        errors.append(f"outward_category={outward!r} 非法（需 {sorted(OUTWARD_CATEGORIES)}）")

    tags = meta.get("tags", []) or []
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        errors.append("tags 必须是字符串列表")
        tags = []
    else:
        bad_tags = [tag for tag in tags if tag not in TAG_VOCAB]
        if bad_tags:
            errors.append(
                f"tags 含受控词表外标签 {bad_tags}；请改 article-meta.yaml，"
                "或明确扩充 works_registry.TAG_VOCAB"
            )
        if len(tags) != len(set(tags)):
            errors.append("tags 含重复项")

    # article-meta.yaml 是正式对外标题 SSOT；state 只做交叉检查，不参与归档兜底，
    # 否则“发布用 meta、入库用 state”会把同一篇文章悄悄拆成两个标题。
    title = meta.get("title", "")
    if not str(title).strip():
        errors.append("article-meta.yaml title 缺失（正式标题只认这一处）")
    elif outward in OUTWARD_CATEGORIES:
        expected_prefix = f"{OUTWARD_CATEGORIES[outward]} | "
        if not str(title).startswith(expected_prefix):
            errors.append(
                f"title 必须与 outward_category 同源并带前缀 {expected_prefix!r}；"
                "不要在发布时临时二次拼接"
            )

    digest = override.get("digest") or meta.get("digest", "") or ""
    if not str(digest).strip():
        errors.append("digest 缺失")

    url = (
        override.get("wechat_url")
        or state.get("stages", {}).get("publish", {}).get("wechat_url", "")
    )
    if require_url and not url:
        errors.append("publish.wechat_url 为空（草稿态不归档）")
    elif url and not re.match(r"^https://mp\.weixin\.qq\.com/s/[^\s]+$", str(url)):
        errors.append(f"wechat_url 不是合法公众号永久链接：{str(url)[:80]}")

    fields = {
        "category": category,
        "outward_category": outward,
        "tags": tags,
        "title": str(title).strip(),
        "digest": str(digest).strip(),
        "wechat_url": str(url).strip(),
    }
    return meta, fields, errors


def _log_archive_event(cwd: Path, event: str, verdict: str, detail: str,
                       *, error_count: int = 0) -> None:
    """把发布后闭环纳入自省日志；遥测失败不得影响主流程。"""
    try:
        from contracts import log_observation
        log_observation(
            "archive", event, verdict, detail, cwd.name,
            issue_codes=([f"archive.{event}.fail"] if verdict == "fail" else []),
            metrics={"errors": error_count},
        )
    except Exception:
        pass


def _log_audio_event(cwd: Path, event: str, verdict: str, detail: str,
                     *, error_count: int = 0) -> None:
    """Record podcast/WeChat audio gates without making telemetry critical-path."""
    try:
        from contracts import log_observation
        log_observation(
            "audio", event, verdict, detail, cwd.name,
            issue_codes=([f"audio.{event}.fail"] if verdict == "fail" else []),
            metrics={"errors": error_count},
        )
    except Exception:
        pass


def _archive_source_errors(cwd: Path) -> list[str]:
    """Check folder identity and golden-line source before archive writes anything."""
    from profile_config import golden_lines_file

    errors: list[str] = []
    seq_text = cwd.name.split("-", 1)[0]
    if not seq_text.isdigit():
        errors.append("无法从文件夹名解析 seq（应形如 47-选题名）")

    golden = golden_lines_file()
    marker = f"*({cwd.name})*"
    if not golden.exists():
        errors.append(
            f"金句库不存在：{golden}（可用 SANSHENG_WRITE_GOLDEN_LINES_FILE 指向现有真源）"
        )
    elif marker not in golden.read_text(encoding="utf-8"):
        errors.append(
            f"金句库缺本篇来源标记 {marker}（文件：{golden}）；"
            f"请先追加：- <本篇金句> {marker}"
        )
    return errors


def _finalize_preflight_errors(cwd: Path, wechat_url: str) -> list[str]:
    """Fail before touching state/registries when the close-out cannot finish."""
    state = load_state(cwd)
    _, _, errors = _archive_metadata(
        cwd,
        state,
        require_url=True,
        override={"wechat_url": wechat_url},
    )
    errors.extend(_archive_source_errors(cwd))
    try:
        import distribute as _distribute_audio
        if _distribute_audio.podcast_wechat_embed_enabled():
            from release_to_draft import (
                AUDIO_RECEIPT_FILE,
                PUBLISHED_AUDIO_RECEIPT_FILE,
                compare_wechat_audio_receipts,
                compare_wechat_published_audio_receipts,
                verify_wechat_audio,
                verify_wechat_published_audio,
            )
            published_receipt_path = cwd / PUBLISHED_AUDIO_RECEIPT_FILE
            receipt_path = cwd / AUDIO_RECEIPT_FILE
            if published_receipt_path.is_file():
                try:
                    published_receipt = json.loads(
                        published_receipt_path.read_text(encoding="utf-8")
                    )
                    fresh_receipt, fresh_errors = verify_wechat_published_audio(
                        cwd, wechat_url, persist=False
                    )
                    errors.extend(
                        f"正式文章远端复核失败：{error}" for error in fresh_errors
                    )
                    if fresh_receipt is not None:
                        errors.extend(compare_wechat_published_audio_receipts(
                            published_receipt,
                            fresh_receipt,
                            expected_wechat_url=wechat_url,
                        ))
                except (json.JSONDecodeError, OSError) as exc:
                    errors.append(f"正式文章双音频凭证损坏：{exc}")
            elif not receipt_path.is_file():
                errors.append(
                    "双音频尚无官方读回凭证；草稿仍存在时运行 pipeline.py "
                    "wechat-audio-check --confirm-audition；若文章已正式发布、草稿已被回收，"
                    f"运行 pipeline.py wechat-published-audio-check {wechat_url} "
                    "--confirm-audition"
                )
            else:
                try:
                    audio_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    expected_media = str(
                        (state.get("stages", {}).get("publish", {}) or {}).get("draft_media_id") or ""
                    )
                    fresh_receipt, fresh_errors = verify_wechat_audio(cwd, persist=False)
                    for error in fresh_errors:
                        detail = f"正式发布前远端复核失败：{error}"
                        if "40007" in str(error) or "invalid media_id" in str(error):
                            detail += (
                                "；草稿已被微信回收时，改用 pipeline.py "
                                f"wechat-published-audio-check {wechat_url} "
                                "--confirm-audition"
                            )
                        errors.append(detail)
                    if fresh_receipt is not None:
                        errors.extend(compare_wechat_audio_receipts(
                            audio_receipt,
                            fresh_receipt,
                            expected_media_id=expected_media,
                        ))
                except (json.JSONDecodeError, OSError) as exc:
                    errors.append(f"双音频草稿凭证损坏：{exc}")
    except Exception as exc:
        errors.append(f"双音频 finalize 检查异常：{exc}")
    return errors


def _upstream_stage_errors(state: dict, stage: str) -> list[str]:
    """Return hard ordering errors; stages may never complete out of order."""

    errors: list[str] = []
    for upstream in STAGE_ORDER[:STAGE_ORDER.index(stage)]:
        status = state.get("stages", {}).get(upstream, {}).get("status", "pending")
        if status not in {"done", "adopted"}:
            errors.append(f"上游阶段 {upstream}={status}；{stage} 不得越序完成")
    return errors


def verify_stage(stage: str, cwd: Path, state: dict, legacy: bool = False) -> tuple:
    """返回 (passed: bool, errors: list[str])。"""
    if legacy:
        return False, ["--legacy 已停用：任何历史迁移也不得绕过当前合同"]
    errors = _upstream_stage_errors(state, stage)

    if stage == "outline":
        f = cwd / "大纲.md"
        if not f.exists():
            errors.append("大纲.md 不存在")
        elif len(f.read_text(encoding="utf-8")) < 200:
            errors.append("大纲.md 内容过短（< 200 字）")
        if not legacy:
            errors.extend(_checkpoint_errors("outline", cwd))

    elif stage == "writing":
        f = cwd / "定稿.md"
        if not f.exists():
            errors.append("定稿.md 不存在")
        elif len(f.read_text(encoding="utf-8")) < 1500:
            errors.append("定稿.md 内容过短（< 1500 字）")
        title = state["stages"].get("writing", {}).get("title_final", "")
        if not title:
            errors.append(
                "title_final 未写入 state，请：pipeline.py done writing title_final='文章标题'"
            )
        if not legacy:
            errors.extend(_checkpoint_errors("writing", cwd))

        # ⚠️ 非阻断 WARNING（2026-06-20 审查 B-2）：开头盲选锚点 _opening-choice.md 是
        # autopilot 唯一法定停顿点，但它不在 STAGE_ORDER 记账、无 verify 硬门。跨会话恢复时
        # 新会话见 writing=done 即直奔配图，盲选停顿被静默跳过。这里只提醒、不 fail——
        # 历史文章无此文件，加硬门会破坏既有 verify/golden 测试。
        if not legacy and not (cwd / "_opening-choice.md").exists():
            print(
                "⚠️ 未见开头盲选锚点 _opening-choice.md（autopilot 唯一法定停顿点，"
                "跨会话恢复时易静默跳过）—— 若本篇确已做盲选，可忽略；否则补回再继续。"
            )

        # ⚠️ 非阻断 WARNING（2026-07-21 实战固化）：大纲 PART 标题 vs 定稿 H2 漂移提醒。
        # 改稿改了 H2 没同步大纲是常态，这里只提示不 fail（大纲格式不一，PART 行抓不到就跳过）。
        _ol = cwd / "大纲.md"
        if not legacy and f.exists() and _ol.exists():
            _draft_h2 = re.findall(r'(?m)^## (.+?)\s*$', f.read_text(encoding="utf-8"))
            _ol_parts = re.findall(r'(?m)^#{2,3}\s*PART\s*\d+\s*·\s*(.+?)\s*$',
                                   _ol.read_text(encoding="utf-8"))
            # 归一化：剥「」/引号/空白，防「猝死演练」vs 猝死演练 这类假阳性
            _norm = lambda s: re.sub(r'[「」""\'\'\s]', '', s)
            if (_ol_parts and _draft_h2
                    and [_norm(x) for x in _ol_parts] != [_norm(x) for x in _draft_h2]):
                print(
                    f"⚠️ 大纲 PART 标题与定稿 H2 不一致——改稿后请同步大纲\n"
                    f"   大纲={_ol_parts}\n   定稿={_draft_h2}"
                )

        # 🔴 Round 3.5（2026-05-21 Team refs-activation 收敛）：
        # writing 阶段只保留 2 道「诚实硬门」—— verify_pos_ratio / verify_bold_density。
        # 它们直接量成稿 定稿.md 的字符特征（形/副词比例、加粗计数），不依赖任何自证 marker。
        # 已删除：① verify_compact_strokes（假验证：grep 招式术语名，正文永不逐字出现，恒 fail）
        #         ② refs_loaded marker 检查（自证打卡：Claude 不读也能 mark true）
        # 风格招式是否被吸收，本质无法机械验证，不再假装能验——改由 B-主门黑名单兜底显性 AI 腔。
        if not legacy and f.exists():
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from contracts import (verify_pos_ratio, verify_bold_density,
                                        verify_h2_subtitle_align)
                text = f.read_text(encoding="utf-8")

                pr = verify_pos_ratio(text)
                if pr.get("verdict") == "suspicious":
                    errors.append(
                        f"verify_pos_ratio verdict=suspicious "
                        f"(ratio={pr.get('ratio', 0):.2f}，形/副词过密，AI 味嫌疑)"
                    )

                bd = verify_bold_density(text)
                # 🔴 2026-08-14 放宽（sandy 拍板）：软硬双阈值。
                #    'soft_over' = 略超软上限，只提示不阻断（"稍微超就超一点"）；
                #    只有真刷屏（超硬上限）或整句加粗超额才拦。
                _bd_verdict = bd.get("verdict")
                if _bd_verdict in ("bold_over", "integral_bold_violation",
                                   "both_violations"):
                    errors.append(
                        f"verify_bold_density verdict={_bd_verdict} "
                        f"({bd.get('bold_count', 0)}/硬上限 {bd.get('bold_hard_limit', 0)}，"
                        f"整句加粗 {bd.get('integral_bold_count', 0)}/"
                        f"{bd.get('integral_bold_allowance', 0)})"
                    )
                elif _bd_verdict == "soft_over":
                    print(f"   ℹ️ {bd.get('notes', '')}")

                # H2/part_subtitles 对齐（前移自 format_layout exit 3 —— 写完正文即拦，
                # 不要等到排版阶段才发现漏写标题）
                align = verify_h2_subtitle_align(str(cwd))
                if align.get("verdict") == "fail":
                    errors.append(align.get("notes", "H2/part_subtitles 不对齐"))

                # skill 自省：3 道门结果追加到 _skill-observations.jsonl
                try:
                    from contracts import log_observation as _logobs
                    _art = cwd.name
                    _logobs('verify_writing', 'verify_pos_ratio',
                            str(pr.get('verdict', '')),
                            f"ratio={pr.get('ratio', '')}", _art)
                    _logobs('verify_writing', 'verify_bold_density',
                            str(bd.get('verdict', '')),
                            f"{bd.get('bold_count', '')}/{bd.get('bold_limit', '')}", _art)
                    _logobs('verify_writing', 'verify_h2_subtitle_align',
                            str(align.get('verdict', '')),
                            (align.get('notes', '') or '')[:100], _art)
                except Exception:
                    pass
            except Exception as e:
                errors.append(f"contracts 校验异常：{e}")

    elif stage == "cover":
        mat = cwd / "素材"
        covers = list(mat.glob("cover*.png")) if mat.exists() else []
        if not covers:
            errors.append("素材/cover*.png 不存在")
        # 🔴 曾踩坑：封面 prompt frontmatter 写 output:"../hero.png" 把 1:1 装饰 hero 覆盖了
        # cover stage 输出必须是 素材/cover.png，不允许写到 hero.png
        if not legacy:
            prompts_dir = mat / "prompts" if mat.exists() else None
            if prompts_dir and prompts_dir.exists():
                for pf in prompts_dir.glob("*cover*.md"):
                    try:
                        head = pf.read_text(encoding="utf-8")[:600]
                        m = re.search(r"^output:\s*\"?([^\"\n]+)\"?\s*$", head, re.MULTILINE)
                        if m:
                            out_path = m.group(1).strip()
                            base = os.path.basename(out_path).lower()
                            if "hero" in base:
                                errors.append(
                                    f"{pf.name} frontmatter `output: {out_path}` 把封面图错写到 hero 文件名。"
                                    f"封面图必须输出到 `素材/cover.png`，hero.png 是 1:1 无文字装饰图（独立产物）"
                                )
                            elif base != "cover.png" and "cover" not in base:
                                errors.append(
                                    f"{pf.name} frontmatter `output: {out_path}` 输出文件名不规范。"
                                    f"封面图必须输出到 `素材/cover.png`"
                                )
                    except Exception:
                        pass
        # 封面图元数据校验。legacy 已在函数入口拒绝，以下条件只保留调用兼容性。
        if covers:
            meta = _image_metadata(covers[0])
            if not meta:
                # Pillow 未装或文件损坏——2026-04 起不再静默跳过
                if not legacy:
                    errors.append(
                        "无法读取 cover 图像元数据（Pillow 未装？请 `pip install Pillow`）"
                    )
            else:
                # 1) AR 比例 2.35:1（允许 2.1 ~ 2.6）
                if not legacy and not (2.1 <= meta["ratio_wh"] <= 2.6):
                    errors.append(
                        f"cover.png 宽高比 {meta['ratio_wh']:.2f} 不符合 2.35:1（允许 2.1~2.6）。"
                        f"请检查 visual-plan 封面比例或 renderer 输出参数"
                    )
                # 2) 分辨率 ≥1K（长边 1000px 判定）
                if not legacy and meta["long_edge"] < 1000:
                    errors.append(
                        f"cover.png 分辨率过低（长边 {meta['long_edge']}px < 1000px）。"
                        f"请检查当前 renderer 的目标尺寸参数与后处理是否正确。"
                    )
            # 3) 生图来源白名单（.gen-log.jsonl 有记录时才检查）
            if not legacy:
                logs = _read_gen_log(cwd, "cover")
                if logs:
                    last = logs[-1]
                    tool = last.get("tool", "")
                    if tool in IMAGE_TOOL_BLACKLIST:
                        errors.append(
                            f"cover 使用了未登记的宿主工具 `{tool}`；必须由 {VISUAL_PRODUCER} 编译并经 renderer adapter 渲染"
                        )
                    elif tool and tool not in IMAGE_TOOL_WHITELIST["cover"]:
                        errors.append(
                            f"cover producer={tool}；必须为 {VISUAL_PRODUCER}"
                        )
        if not legacy:
            errors.extend(_cover_route_errors(cwd))

    elif stage == "infographic":
        mat = cwd / "素材"
        if not mat.exists():
            errors.append("素材/ 目录不存在")
        else:
            infos = sorted(mat.glob("infographic*.png"))
            # 2026-05-04 新规则：信息图 ≥ 4 张（开篇 + 中间多张 + 结尾）
            if len(infos) < 4:
                errors.append(
                    f"信息图数量不足（找到 {len(infos)} 张，需要 ≥ 4 张：开篇 9:16 ×1 + 中间 16:9 ×N + 结尾 9:16 ×1）"
                )
            if not legacy:
                # 分类统计 9:16（portrait）和 16:9（landscape）
                portrait_count = 0
                landscape_count = 0
                for p in infos:
                    meta = _image_metadata(p)
                    if not meta:
                        errors.append(f"{p.name}：无法读取元数据（Pillow 问题？）")
                        continue
                    ratio = meta["ratio_wh"]
                    # 9:16 = 0.5625（允许 0.50–0.60）
                    # 16:9 = 1.7778（允许 1.70–1.85）
                    is_portrait = 0.50 <= ratio <= 0.60
                    is_landscape = 1.70 <= ratio <= 1.85
                    if is_portrait:
                        portrait_count += 1
                    elif is_landscape:
                        landscape_count += 1
                    else:
                        errors.append(
                            f"{p.name} 宽高比 {ratio:.2f} 既不是 9:16（竖）也不是 16:9（横）。"
                            f"layout.md 3e 要求：开篇/结尾用 portrait（9:16），中间用 landscape（16:9）"
                        )
                    if meta["long_edge"] < 1000:
                        errors.append(
                            f"{p.name} 分辨率过低（长边 {meta['long_edge']}px < 1000px），请检查 renderer 的目标尺寸参数。"
                        )
                # 至少 2 张 9:16（开篇 + 结尾）
                if portrait_count < 2:
                    errors.append(
                        f"9:16 portrait 信息图数量不足（找到 {portrait_count} 张，开篇 + 结尾共需 ≥ 2 张）"
                    )
                # 至少 2 张 16:9（中间）
                if landscape_count < 2:
                    errors.append(
                        f"16:9 landscape 信息图数量不足（找到 {landscape_count} 张，中间需 ≥ 2 张）"
                    )
                # 生图来源严格白名单（2026-05-04 修：不在白名单视为违规）
                logs = _read_gen_log(cwd, "infographic")
                if logs:
                    for rec in logs:
                        tool = rec.get("tool", "")
                        cmd_str = rec.get("cmd", "")
                        if tool in IMAGE_TOOL_BLACKLIST:
                            errors.append(
                                f"infographic 使用了未登记的宿主工具 `{tool}`；必须走 visual planner"
                            )
                            break
                        elif tool and tool not in IMAGE_TOOL_WHITELIST["infographic"]:
                            errors.append(
                                f"infographic producer={tool} 不在白名单；必须为 {VISUAL_PRODUCER}"
                            )
                            break
                        # 新合同把 style 写进结构化日志；旧日志才从命令行回读。
                        if tool == VISUAL_PRODUCER:
                            style_error = _infographic_style_error(rec)
                            if style_error:
                                errors.append(style_error)
                                break
                else:
                    # 没有 gen-log 记录但素材里有 PNG：来源不可追溯，必须拦下。
                    errors.append(
                        f"infographic 没有 .gen-log.jsonl 记录，但 素材/ 里有 {len(infos)} 张 infographic*.png。"
                        f"必须经 {VISUAL_PRODUCER} 编译、renderer adapter 渲染并记录，"
                        f"以保证风格统一可追溯（详见 iron-rules.md §视觉 第 1/3 条）"
                    )

                # 新文章严格核对：meta 路由 → analysis/structured → prompt →
                # 最新精确 output 日志 → final-set。仅“style 在允许枚举里”不代表选对。
                if not legacy:
                    route_errors = _visual_route_errors(cwd)
                    errors.extend(route_errors)
                    try:
                        sys.path.insert(0, str(Path(__file__).parent))
                        from contracts import log_observation as _logobs_visual
                        _logobs_visual(
                            "verify_infographic", "visual_route",
                            "fail" if route_errors else "ok",
                            f"errors={len(route_errors)}", cwd.name,
                        )
                    except Exception:
                        pass

    elif stage == "bgm":
        # 脚本默认输出到文章根目录（song_name.mp3），--output 可指定到素材/
        mp3s = list(cwd.glob("*.mp3")) + list((cwd / "素材").glob("*.mp3"))
        if not mp3s:
            errors.append("未找到 .mp3 文件（文章根目录或素材/目录）")
        draft = cwd / "定稿.md"
        if not draft.exists():
            errors.append("定稿.md 不存在")
        elif "本文主题曲" not in draft.read_text(encoding="utf-8"):
            errors.append("定稿.md 中未找到音频引导卡片（关键字「本文主题曲」缺失）")

    elif stage == "layout":
        html_file = cwd / "定稿.html"
        if not html_file.exists():
            errors.append("定稿.html 不存在")
        else:
            html = html_file.read_text(encoding="utf-8")
            checks = [
                ("H2 格式标记",        "PART_H2_STYLE" in html or "TIMELINE_H2_STYLE" in html),
                ("导读栏",             "display: table-cell; width: 64%" in html),
                ("关注卡片组件",       "mp-common-profile" in html),
                ("关注卡片 data-id",   bool(re.search(r'<mp-common-profile[^>]*\bdata-id="[^"]+"', html))),
                ("无蓝色 #0F4C81 残留", "#0F4C81" not in html),
                ("无灰色 blockquote",  "#f7f7f7" not in html),
            ]
            for label, ok in checks:
                if not ok:
                    errors.append(f"检查失败：{label}")

            if not legacy:
                # 堆叠导读栏检测：table-cell width:64% 全 HTML 只能出现一次（文章导读 = 1 份）
                import re as _re
                lead_count = len(_re.findall(r"display:\s*table-cell;\s*width:\s*64%", html))
                if lead_count > 1:
                    errors.append(
                        f"检测到 {lead_count} 个导读栏实例（应为 1）。"
                        f"format_layout.py --lead 须先 purge 旧实例再注入"
                    )
                # mp-common-profile 关注卡片也应唯一
                profile_count = html.count("<mp-common-profile")
                if profile_count > 1:
                    errors.append(f"检测到 {profile_count} 个关注卡片（应为 1）")

                # 定稿.md 中 H3 未闭合 `**` 检测（虚线消失根因）
                md_file = cwd / "定稿.md"
                if md_file.exists():
                    md_lines = md_file.read_text(encoding="utf-8").splitlines()
                    bad_h3 = []
                    for i, line in enumerate(md_lines, 1):
                        if line.startswith("### "):
                            # 统计该行 ** 的数量，奇数即未闭合
                            if line.count("**") % 2 != 0:
                                bad_h3.append(f"L{i}: {line[:60]}")
                    if bad_h3:
                        errors.append(
                            "定稿.md 中 H3 标题存在未闭合的 `**`（会导致 format_layout.py 跳过虚线绘制）："
                        )
                        for x in bad_h3[:3]:
                            errors.append(f"  {x}")

                # 🔴 发布前「防裂图门」。
                # 盲区实录：verify cover / infographic 全绿，但导读栏 hero.png 没生成、
                # 发布时才发现裂图——因为 cover/infographic 门只查自己那几张，没人查
                # 「html 里真正引用的图是否都在」。这一门扫 定稿.html 所有 data-local-path，
                # 把 hero / 信息图等本文配图的缺失一网打尽。
                # 只为「本文自身资产」负责（路径落在 cwd 文章目录内）：推荐阅读卡引用的是别篇
                # 文章封面、名片 logo 走 brand/ 固定资产，二者各有存在性保障/降级（见
                # generate_recommend_html.py 的 _has_cover 降级），不纳入本门，免得别人目录
                # 被清理时误拦本文发布（对抗审查补强）。
                dlps = re.findall(r'data-local-path="([^"]+)"', html)
                cwd_prefix = str(Path(cwd).resolve())
                missing_imgs = []
                for p in dlps:
                    if p.startswith(("http://", "https://")):
                        continue
                    try:
                        own_asset = str(Path(p).resolve()).startswith(cwd_prefix)
                    except (OSError, ValueError):
                        own_asset = False
                    if own_asset and not Path(p).exists():
                        missing_imgs.append(p)
                if missing_imgs:
                    errors.append(
                        f"定稿.html 有 {len(missing_imgs)} 张本文配图的 data-local-path 指向不存在的文件"
                        f"（发布会裂图，常见：导读栏 hero、信息图）："
                    )
                    for p in missing_imgs[:6]:
                        errors.append(f"  缺：{p}")
                # cover.png 不在正文 <img>（走 frontmatter coverImage 当头图），单独校验素材到位
                if not (cwd / "素材" / "cover.png").exists():
                    errors.append("素材/cover.png 不存在（微信头图必需，发布前必须就位）")

                # 🔴 2026-07-07 产物关：verify_final_html 独立断言最终 HTML 无「破渲染」平台违规
                # （style/script/position/grid/var/@media 等；flex/class/<div> 合法不查）+ 四周虚线 WARN。
                # 与组件层 process_wechat_compat「相信剥干净」互补，防剥漏 / 手改注入。
                try:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from contracts import verify_final_html
                    vf = verify_final_html(str(html_file))
                    for e in vf.get("errors", []):
                        errors.append(f"verify_final_html: {e}")
                    for w in vf.get("warnings", []):
                        print(f"  ⚠️ [layout] {w}")
                    try:
                        from contracts import log_observation as _logobs2
                        _logobs2('verify_layout', 'verify_final_html',
                                 str(vf.get('verdict', '')),
                                 f"hits={vf.get('hits', 0)}", cwd.name)
                    except Exception:
                        pass
                except Exception as e:
                    errors.append(f"verify_final_html 异常：{e}")

                # 🔴 2026-07-11 裸 URL 门：正文里完整 URL 必须走 link-card / deep-read 模板
                # （word-break 浅框），裸放在正文段落 / 划重点 / 文末手敲段 → 微信分散对齐、
                # 读者无法复制。规则原只在 layout-reference.md，被绕过后升格为发布硬门。
                try:
                    from contracts import verify_no_bare_url
                    vb = verify_no_bare_url(str(html_file))
                    for e in vb.get("errors", []):
                        errors.append(f"verify_no_bare_url: {e} → 挪进 link-card.html（单条）或 deep-read-section.html（文末/多条）")
                    try:
                        from contracts import log_observation as _logobs3
                        _logobs3('verify_layout', 'verify_no_bare_url',
                                 str(vb.get('verdict', '')),
                                 f"hits={vb.get('hits', 0)}", cwd.name)
                    except Exception:
                        pass
                except Exception as e:
                    errors.append(f"verify_no_bare_url 异常：{e}")

    elif stage == "logo":
        # add_logo.js 原地覆盖图片，无法通过文件元数据判断；
        # 只验证 AI 生图文件存在（确保 add_logo.js 有东西可处理）
        mat = cwd / "素材"
        pngs = list(mat.glob("*.png")) if mat.exists() else []
        if not pngs:
            errors.append("素材/ 下无 PNG 文件，add_logo.js 无输入")

    elif stage == "publish":
        # 🔴 拆「草稿箱已推送」与「正式发布」两态。
        # autopilot 跑到 baoyu-post-to-wechat 草稿箱即终态，此时只有 media_id、没有公开
        # url（url 要人工在后台点「发布」才生成）。原来只认 wechat_url，会把「草稿已成功
        # 推送」误判成未完成、卡住 done。现在：有 wechat_url=正式发布完成；退而有
        # draft_media_id=草稿箱已推送（autopilot 阶段性通过）；两者皆无才报错。
        # 注意：archive 仍严格要求 wechat_url —— 草稿态不归档，正式发布后才入库。
        pub = state["stages"].get("publish", {})
        url = pub.get("wechat_url", "")
        draft_id = pub.get("draft_media_id", "")
        if not legacy and not draft_id:
            errors.append(
                "新流程的 publish 必须先有 draft_media_id + publish receipt；"
                "历史文章也不得跳过 release-to-draft 证据链"
            )
        elif url and not url.startswith("https://mp.weixin.qq.com"):
            errors.append(f"wechat_url 不是微信公众号链接：{url[:80]}")
        elif not url and not draft_id:
            errors.append(
                "publish 既无 draft_media_id 也无 wechat_url。"
                "草稿箱必须通过 pipeline.py release-to-draft 创建并读回；"
                "正式发布后收尾：pipeline.py finalize https://mp.weixin.qq.com/s/xxx"
            )
        if draft_id and not legacy:
            receipt, receipt_errors = verify_publish_receipt(cwd, draft_id)
            errors.extend(f"publish_receipt: {e}" for e in receipt_errors)
            if receipt and int(receipt.get("schema_version") or 1) < 2:
                errors.append(
                    "publish_receipt: 新流程只认 release-to-draft 生成的 v2 官方读回凭证"
                )

    elif stage == "archive":
        # 按 seq 查作品库，并校验本篇字段与全部派生视图；不能只凭“记录存在”发绿灯。
        try:
            from works_registry import load_works, validate_works
            import render_articles_md as RAM
            import render_works_dashboard as RWD
            from profile_config import golden_lines_file, works_file

            seq_str = cwd.name.split("-")[0]
            seq = int(seq_str) if seq_str.isdigit() else None
            works = load_works()
            rec = next((w for w in works if w.get("seq") == seq), None)
            if rec is None:
                errors.append(f"{works_file()} 未找到 seq={seq} 的记录 -- 请先跑：pipeline.py archive")
            else:
                _, fields, meta_errors = _archive_metadata(cwd, state, require_url=True)
                errors.extend(f"archive_meta: {error}" for error in meta_errors)
                for key in ("category", "outward_category", "tags", "title", "digest", "wechat_url"):
                    if rec.get(key) != fields.get(key):
                        errors.append(
                            f"作品库字段 {key} 与当前 meta/state 不一致："
                            f"registry={rec.get(key)!r}, current={fields.get(key)!r}"
                        )
                errors.extend(f"作品库校验：{error}" for error in validate_works(works))

                expected_articles = RAM.render_md(works)
                if not RAM.ARTICLES_MD.exists():
                    errors.append(f"派生视图不存在：{RAM.ARTICLES_MD}")
                elif RAM.ARTICLES_MD.read_text(encoding="utf-8") != expected_articles:
                    errors.append(f"派生视图已过期：{RAM.ARTICLES_MD}")

                expected_dashboard = RWD.build_html(works)
                if not RWD.DASHBOARD_FILE.exists():
                    errors.append(f"派生看板不存在：{RWD.DASHBOARD_FILE}")
                elif RWD.DASHBOARD_FILE.read_text(encoding="utf-8") != expected_dashboard:
                    errors.append(f"派生看板已过期：{RWD.DASHBOARD_FILE}")

                golden = golden_lines_file()
                marker = f"*({cwd.name})*"
                if not golden.exists():
                    errors.append(
                        f"金句库不存在：{golden}（可用 SANSHENG_WRITE_GOLDEN_LINES_FILE 指向现有真源）"
                    )
                elif marker not in golden.read_text(encoding="utf-8"):
                    errors.append(f"金句库尚未沉淀本篇：缺标记 {marker}（文件：{golden}）")
        except Exception as e:
            errors.append(f"归档校验失败：{e}")

    if stage == "archive":
        _log_archive_event(
            cwd, "verify_closed_loop", "fail" if errors else "ok",
            f"errors={len(errors)}", error_count=len(errors),
        )
    return (len(errors) == 0, errors)


# ── 命令实现 ──────────────────────────────────────────────────
def _cross_check(cwd: Path, state: dict) -> list:
    """扫四份状态文件，返回不一致项列表（仅警告，不阻断）。

    检查项：
    1. .state.json writing.title_final vs article-meta.yaml 的 title
    3. article-meta.yaml part_subtitles 数量 vs 定稿.md H2 数量
       （format_layout.py --all 会在排版前 sys.exit(3) 阻断，这里提前发现）
    4. stages 顺序逻辑（done 但前序未完成）
    5. publish=done 但 wechat_url 缺失或非微信链接
    6. archive=done 但 works_file() 解析出的作品库未找到对应 seq 记录
    """
    warnings = []

    # article-meta.yaml 是内容配置 SSOT；state 只保留流程字段。
    meta_path = cwd / "article-meta.yaml"
    meta = {}
    if meta_path.exists():
        if _yaml:
            try:
                meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except Exception as e:
                warnings.append(f"article-meta.yaml 解析失败: {e}")
        else:
            warnings.append("PyYAML 未装，无法验证 article-meta.yaml（pip install pyyaml）")

    if meta:
        s_title = state.get("stages", {}).get("writing", {}).get("title_final", "")
        m_title = meta.get("title", "")
        if s_title and m_title and s_title != m_title:
            warnings.append(
                f"标题不一致：.state.json={s_title!r} vs article-meta.yaml={m_title!r}"
            )

    # 3. part_subtitles 数量 vs 定稿.md H2 数量
    draft = cwd / "定稿.md"
    if draft.exists() and meta:
        subs = meta.get("part_subtitles", []) or []
        h2_count = 0
        for line in draft.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                h2_count += 1
        if subs and h2_count and len(subs) != h2_count:
            warnings.append(
                f"part_subtitles 数量({len(subs)}) ≠ 定稿.md H2 数量({h2_count}) "
                f"— format_layout.py --all 排版前会 sys.exit(3) 阻断，先在大纲/写作阶段对齐"
            )

    # 4. stages 顺序逻辑（不强制阻断，只提醒）
    # 🔴 2026-08-14：release-from-final 模式下 outline 被标 adopted（不是 done），
    #    于是它后面每个 done 阶段都会刷一条「可能是手动 skip 残留」——
    #    89 号实跑一次刷了 8 行，全是误报，我还专门去查了一遍才确认无事。
    #    这种模式下的顺序本来就与常规不同，不该套用同一句猜测性文案。
    stages = state.get("stages", {})
    is_release_from_final = state.get("mode") == "release-from-final"
    prev_done = True
    for s in STAGE_ORDER:
        entry = stages.get(s, {})
        status = entry.get("status", "pending")
        if status == "done" and not prev_done:
            if is_release_from_final:
                # 该模式下 outline=adopted 是正常状态，不提示；
                # 只有真正被 skip 的前序才值得说一句。
                skipped = [
                    x for x in STAGE_ORDER[: STAGE_ORDER.index(s)]
                    if stages.get(x, {}).get("status") == "skip"
                ]
                if skipped:
                    warnings.append(
                        f"{s}=done，但前序 {skipped} 是 skip 状态（release-from-final 模式）"
                    )
            else:
                warnings.append(
                    f"{s}=done 但前序阶段未完成（顺序异常，可能是手动 skip 残留）"
                )
        if status not in ("done", "skip", "adopted"):
            prev_done = False

    # 5. publish=done 但 wechat_url 缺失
    pub = stages.get("publish", {})
    if pub.get("status") == "done":
        url = pub.get("wechat_url", "")
        if not url and not pub.get("draft_media_id"):
            warnings.append("publish=done 但 wechat_url 字段为空（archive 时会找不到链接）")
        elif url and not url.startswith("https://mp.weixin.qq.com"):
            warnings.append(f"publish=done 但 wechat_url 不是微信公众号链接：{url[:50]}")

    # 6. archive=done 但 works.yaml 未记录（二期C：单一数据源改查作品库）
    arch = stages.get("archive", {})
    if arch.get("status") == "done":
        try:
            from works_registry import load_works
            seq_str = cwd.name.split("-")[0]
            seq = int(seq_str) if seq_str.isdigit() else None
            if seq is not None:
                found = any(w.get("seq") == seq for w in load_works())
                if not found:
                    warnings.append(
                        f"archive=done 但 works.yaml 未找到 seq={seq} 的记录 "
                        f"— 可能漏跑 `pipeline.py archive`"
                    )
        except Exception:
            warnings.append("works.yaml 解析失败，无法验证归档完整性")

    return warnings


def _stage_artifact_digest(cwd: Path, stage: str) -> str:
    """返回阶段关键产物摘要；只含本阶段拥有的稳定输入/输出。"""
    if stage == "outline":
        artifact, _ = checkpoint_artifact(cwd, "blueprint")
        return stable_digest(artifact) if artifact else ""
    if stage == "writing":
        artifact, _ = checkpoint_artifact(cwd, "draft")
        return stable_digest(artifact) if artifact else ""
    if stage in {"cover", "infographic"}:
        rows = []
        prefix = "素材/cover.png" if stage == "cover" else "素材/infographic"
        for rec in _read_gen_log(cwd, stage):
            output = _norm_relpath(rec.get("output", ""))
            if output == prefix or (stage == "infographic" and output.startswith(prefix)):
                prompt_rel = _norm_relpath(rec.get("prompt", ""))
                prompt_path = cwd / Path(prompt_rel) if prompt_rel else None
                rows.append({
                    "output": output,
                    "producer": rec.get("producer") or rec.get("tool") or "",
                    "renderer": rec.get("renderer") or "",
                    "model": rec.get("model") or "",
                    "provenance_mode": rec.get("provenance_mode") or "rendered",
                    "prompt": prompt_rel,
                    "prompt_sha256": rec.get("prompt_sha256") or "",
                    "prompt_current_sha256": (
                        sha256_file(prompt_path)
                        if prompt_path and prompt_path.exists() else "missing"
                    ),
                    "output_sha256": rec.get("output_sha256") or "",
                    "record_id": rec.get("record_id") or "",
                })
        latest = {row["output"]: row for row in rows}
        return stable_digest([latest[k] for k in sorted(latest)]) if latest else ""
    if stage == "bgm":
        rels = [str(p.relative_to(cwd)) for p in cwd.glob("*.mp3")]
        rels += [str(p.relative_to(cwd)) for p in (cwd / "素材").glob("*.mp3")]
        rels += [str(p.relative_to(cwd)) for p in (cwd / "素材").glob("*bgm*.png")]
        return files_digest(cwd, rels)
    if stage == "layout":
        return files_digest(cwd, ["定稿.html"])
    if stage == "logo":
        rels = ["素材/cover.png", "素材/hero.png"]
        rels += [str(p.relative_to(cwd)) for p in (cwd / "素材").glob("infographic*.png")]
        rels += ["_visual-qa.json", "_visual-qa-request.json", VISUAL_RECEIPT_FILE]
        return files_digest(cwd, rels)
    if stage == "publish":
        return files_digest(cwd, [PUBLISH_RECEIPT_FILE])
    if stage == "archive":
        try:
            from works_registry import load_works
            seq_str = cwd.name.split("-")[0]
            seq = int(seq_str) if seq_str.isdigit() else None
            rec = next((w for w in load_works() if w.get("seq") == seq), None)
            if rec is not None:
                return stable_digest({"record": rec})
        except Exception:
            pass
        pub = load_state(cwd).get("stages", {}).get("publish", {})
        return stable_digest({"wechat_url": pub.get("wechat_url", "")})
    return ""


def _invalidate_downstream(state: dict, stage: str, reason: str) -> None:
    start = STAGE_ORDER.index(stage) + 1
    for downstream in STAGE_ORDER[start:]:
        info = state["stages"].setdefault(downstream, {"status": "pending"})
        if info.get("status") in {"done", "skip", "dirty"}:
            info["status"] = "dirty"
            info["dirty"] = True
            info["dirty_reason"] = reason


def _record_stage_success(cwd: Path, state: dict, stage: str) -> None:
    upstream_errors = _upstream_stage_errors(state, stage)
    if upstream_errors:
        raise ValueError("；".join(upstream_errors))
    info = state["stages"].setdefault(stage, {})
    previous_status = str(info.get("status") or "pending")
    now = _now_iso()
    digest = _stage_artifact_digest(cwd, stage)
    old_digest = str(info.get("artifact_digest") or "")
    if old_digest and digest and old_digest != digest:
        _invalidate_downstream(state, stage, f"上游 {stage} 产物摘要已变化")
    info["status"] = "done"
    info["dirty"] = False
    info.pop("dirty_reason", None)
    info.setdefault("first_completed_at", now)
    # finished_at 保留作 v1 兼容字段，但只写首次，不再被重复 verify 覆盖。
    info.setdefault("finished_at", info["first_completed_at"])
    info["last_verified_at"] = now
    info["attempt_count"] = int(info.get("attempt_count") or 0) + 1
    info["artifact_digest"] = digest
    info["fail_count"] = 0
    for key in (
        "waiting_since",
        "last_waiting_at",
        "waiting_checkpoint",
        "waiting_reason",
        "required_author_action",
    ):
        info.pop(key, None)
    if previous_status == "waiting_author":
        _log_stage_transition(
            cwd,
            stage,
            previous_status,
            "done",
            "作者拍板证据已验证，阶段恢复完成",
        )


def _checkpoint_wait(errors: list) -> bool:
    """Only a human checkpoint may be a wait; mixed errors remain failures."""
    return bool(errors) and all(
        isinstance(error, str) and error.startswith("checkpoint:")
        for error in errors
    )


def _checkpoint_names(errors: list) -> list[str]:
    names: list[str] = []
    for error in errors:
        match = re.match(r"checkpoint:([\w-]+)", str(error))
        if match and match.group(1) not in names:
            names.append(match.group(1))
    return names


def _log_stage_transition(
    cwd: Path,
    stage: str,
    previous_status: str,
    next_status: str,
    detail: str,
) -> None:
    """Record state transitions without making telemetry critical-path."""
    try:
        from contracts import log_observation

        log_observation(
            f"verify_{stage}",
            "stage_state_transition",
            "waiting_author" if next_status == "waiting_author" else "ok",
            f"from={previous_status} to={next_status}; {detail}",
            cwd.name,
            issue_codes=(
                ["workflow.checkpoint.waiting_author"]
                if next_status == "waiting_author"
                else []
            ),
            metrics={
                "waiting_author": 1 if next_status == "waiting_author" else 0,
            },
        )
    except Exception:
        pass


def _record_stage_waiting_author(
    cwd: Path, state: dict, stage: str, errors: list[str]
) -> None:
    """Persist an author-action wait without manufacturing a failed attempt."""
    info = state["stages"].setdefault(stage, {})
    previous_status = str(info.get("status") or "pending")
    now = _now_iso()
    checkpoints = _checkpoint_names(errors)
    reason = "；".join(str(error) for error in errors)
    info["status"] = "waiting_author"
    info.setdefault("waiting_since", now)
    info["last_waiting_at"] = now
    info["waiting_checkpoint"] = checkpoints
    info["waiting_reason"] = reason
    info["required_author_action"] = (
        "请作者完成拍板并把结论写入审批锚点，再执行 approve 与 verify"
    )
    # A checkpoint wait terminates any consecutive machine-failure streak.  This
    # also repairs old state files where a missing author approval was counted as
    # a failed retry.
    info["fail_count"] = 0
    info.pop("last_failed_at", None)
    _invalidate_downstream(state, stage, f"上游 {stage} 正等待作者拍板")
    save_state(cwd, state)
    _log_stage_transition(
        cwd,
        stage,
        previous_status,
        "waiting_author",
        f"checkpoints={','.join(checkpoints) or 'unknown'}",
    )


def _reconcile_artifact_drift(cwd: Path, state: dict) -> bool:
    """跨会话恢复时发现已完成阶段产物漂移，自动作废它和所有已完成下游。"""
    changed = False
    for stage in STAGE_ORDER:
        info = state["stages"].get(stage, {})
        if info.get("status") != "done" or not info.get("artifact_digest"):
            continue
        current = _stage_artifact_digest(cwd, stage)
        if current != info.get("artifact_digest"):
            info["status"] = "dirty"
            info["dirty"] = True
            info["dirty_reason"] = f"{stage} 产物自上次验证后发生变化"
            _invalidate_downstream(state, stage, info["dirty_reason"])
            changed = True
    if changed:
        save_state(cwd, state)
    return changed


def cmd_status(cwd: Path):
    state = load_state(cwd)
    _reconcile_artifact_drift(cwd, state)
    meta = {}
    meta_path = cwd / "article-meta.yaml"
    if meta_path.exists() and _yaml:
        try:
            meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    style = meta.get("style") or "未选"
    print(f"\n📋 {state['topic_id']}  风格：{style}")
    print("─" * 55)
    next_stage = None
    for s in STAGE_ORDER:
        info = state["stages"].get(s, {})
        status = info.get("status", "pending")
        icon = STATUS_ICON.get(status, "?")
        extra = ""
        if s == "writing" and info.get("title_final"):
            extra = f"  「{info['title_final']}」"
        if s == "bgm":
            manifest_path = cwd / "_music-manifest.json"
            if manifest_path.is_file():
                try:
                    music_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    theme = music_payload.get("theme") or {}
                    origin = theme.get("origin") or {}
                    music_parts = [
                        str(value).strip()
                        for value in (origin.get("provider"), origin.get("model"))
                        if str(value or "").strip()
                    ]
                    music_name = str(theme.get("title") or "").strip()
                    if music_name or music_parts:
                        extra = "  " + (
                            f"《{music_name}》 · " if music_name else ""
                        ) + " / ".join(music_parts)
                except (OSError, json.JSONDecodeError, AttributeError):
                    pass
        if s == "publish" and info.get("wechat_url"):
            url = info["wechat_url"]
            extra = f"  {url[:45]}{'...' if len(url) > 45 else ''}"
        # 显示连续失败次数（≥1 才显示，≥3 标红警示）
        fc = info.get("fail_count", 0)
        if fc >= 3:
            extra += f"  ⚠️失败 {fc} 次"
        elif fc >= 1:
            extra += f"  失败 {fc} 次"
        print(f"  {icon} {s:<13} {STAGE_LABELS[s]}{extra}")
        if status in ("pending", "failed", "dirty", "waiting_author") and next_stage is None:
            next_stage = s
    print("─" * 55)

    # 2026-04-28 新增：交叉一致性检查（仅警告，不阻断）
    warnings = _cross_check(cwd, state)
    if warnings:
        print("\n⚠️  状态文件交叉检查发现不一致（不阻断流程，仅提醒）：")
        for w in warnings:
            print(f"   • {w}")

    # 2026-06-20 审查 B：草稿态自解释提示。publish 只有 draft_media_id、无 wechat_url 时，
    # archive 会拒绝归档（草稿态不入库）；这里提前点明真因，省得 status 的「下一步：archive」
    # 误导用户以为可直接归档。
    pub = state["stages"].get("publish", {})
    if pub.get("draft_media_id") and not pub.get("wechat_url"):
        print(
            "\n📝 当前为草稿态（draft_media_id 已推送），正式发布后用永久链接完成闭环：\n"
            "   pipeline.py finalize https://mp.weixin.qq.com/s/xxx"
        )

    if next_stage == "archive" and pub.get("draft_media_id") and not pub.get("wechat_url"):
        print("\n⏸ 下一步等待作者在微信后台正式发布并补 wechat_url；当前不可 archive。\n")
    elif next_stage and state["stages"].get(next_stage, {}).get("status") == "waiting_author":
        waiting = state["stages"].get(next_stage, {})
        print(f"\n⏸ 下一步：等待作者拍板（{STAGE_LABELS[next_stage]}）")
        print(f"   {waiting.get('required_author_action', '请作者完成检查点拍板后再继续。')}")
        if waiting.get("waiting_reason"):
            print(f"   当前卡点：{waiting['waiting_reason']}\n")
    elif next_stage:
        print(f"\n▶ 下一步：{next_stage}\n  {STAGE_HINTS[next_stage]}\n")
    else:
        print("\n🎉 微信公众号文章链已完成（正式链接 + 归档均已验证）。")
        print("   网站部署与朋友圈发布属于可选外部收尾，不纳入本 state。\n")


def cmd_next(cwd: Path):
    state = load_state(cwd)
    _reconcile_artifact_drift(cwd, state)
    for s in STAGE_ORDER:
        status = state["stages"].get(s, {}).get("status", "pending")
        if status in ("pending", "failed", "dirty", "waiting_author"):
            pub = state["stages"].get("publish", {})
            if s == "archive" and pub.get("draft_media_id") and not pub.get("wechat_url"):
                print("⏸ 当前是微信草稿态；正式发布并补 wechat_url 后才能 archive。")
                return
            if status == "waiting_author":
                info = state["stages"].get(s, {})
                print(f"\n⏸ 下一阶段等待作者拍板：{s} — {STAGE_LABELS[s]}")
                print(f"  {info.get('required_author_action', '请作者完成检查点拍板后再继续。')}")
                if info.get("waiting_reason"):
                    print(f"  当前卡点：{info['waiting_reason']}")
                print()
                return
            print(f"\n▶ 下一阶段：{s} — {STAGE_LABELS[s]}\n")
            print(f"  {STAGE_HINTS[s]}\n")
            return
    print("🎉 微信公众号文章链已完成；网站部署与朋友圈发布为可选外部收尾。")


def _pre_publish_errors(cwd: Path, state: dict | None = None) -> list:
    """publish --pre 素材齐备门（2026-07-21 实战固化）：推送前专用。
    iron-rules「发布前硬闸」的落地 -- 只查素材/文件齐备，不查推送证据
    （draft_media_id / wechat_url 归 `verify publish` 推送后验证）。"""
    errors = []
    if state is None and (cwd / STATE_FILE).exists():
        state = load_state(cwd)
    if state is not None:
        # 发布前就拦住归档必填项和受控标签，避免正式发布后才发现元数据不能入库。
        _, _, meta_errors = _archive_metadata(cwd, state, require_url=False)
        errors.extend(f"archive_meta: {error}" for error in meta_errors)
        for upstream in STAGE_ORDER[:STAGE_ORDER.index("publish")]:
            status = state.get("stages", {}).get(upstream, {}).get("status", "pending")
            if status not in {"done", "adopted"}:
                errors.append(f"上游阶段 {upstream}={status}；全部 done 后才可生成 publish-ready")
    mat = cwd / "素材"
    if not (mat / "cover.png").exists():
        errors.append("缺 素材/cover.png（微信头图）")
    if not (mat / "hero.png").exists():
        errors.append("缺 素材/hero.png（导读栏小图）")
    infos = list(mat.glob("infographic*.png")) if mat.exists() else []
    if len(infos) < 4:
        errors.append(f"信息图 infographic*.png 仅 {len(infos)} 张（需 ≥4）")
    if not (cwd / "定稿.html").exists():
        errors.append("缺 定稿.html（先走 layout 阶段）")
    else:
        try:
            import distribute as _distribute_audio
            if _distribute_audio.podcast_wechat_embed_enabled():
                html_text = (cwd / "定稿.html").read_text(encoding="utf-8")
                theme_pos = html_text.find("<!-- AUDIO-CARD-START -->")
                podcast_pos = html_text.find("<!-- PODCAST-CARD-START -->")
                if theme_pos < 0 or podcast_pos < 0:
                    errors.append(
                        "定稿.html 缺双音频卡（先完成 podcast-pregen，再重跑完整排版）"
                    )
                elif theme_pos > podcast_pos:
                    errors.append("定稿.html 双音频卡顺序错误（主题曲应在播客版之前）")
        except Exception as exc:
            errors.append(f"定稿.html 双音频卡检查异常：{exc}")
    cover_route_errors = _cover_route_errors(cwd, allow_postprocessed=True)
    errors.extend(f"cover_route: {e}" for e in cover_route_errors)
    route_errors = _visual_route_errors(cwd, allow_postprocessed=True)
    errors.extend(f"visual_route: {e}" for e in route_errors)
    qa_evidence_errors = _visual_qa_evidence_errors(cwd)
    errors.extend(f"visual_qa: {e}" for e in qa_evidence_errors)
    qa_errors = _visual_qa_errors(cwd) if not qa_evidence_errors else []
    errors.extend(f"visual_qa: {e}" for e in qa_errors)
    _, receipt_errors = verify_visual_receipt(cwd)
    errors.extend(f"visual_receipt: {e}" for e in receipt_errors)
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contracts import log_observation as _logobs_visual
        _logobs_visual(
            "verify_publish", "visual_qa",
            "fail" if qa_errors else "ok",
            f"errors={len(qa_errors)}", cwd.name,
        )
    except Exception:
        pass
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contracts import verify_publish_assets
        res = verify_publish_assets(str(cwd))
        for e in res.get("errors", []):
            errors.append(f"verify_publish_assets: {e}")
    except Exception as e:
        errors.append(f"verify_publish_assets 异常：{e}")
    _, manifest_errors = build_publish_manifest(cwd)
    errors.extend(f"publish_manifest: {e}" for e in manifest_errors)
    return errors


def cmd_verify(stage: str, cwd: Path, legacy: bool = False, pre: bool = False):
    if legacy:
        print("❌ --legacy 已停用：阶段合同不允许绕过")
        raise SystemExit(2)
    if pre:
        if stage != "publish":
            print("⚠️ --pre 仅 publish 阶段使用（推送前素材齐备门）")
            raise SystemExit(2)
        errors = _pre_publish_errors(cwd)
        if errors:
            print("❌ publish --pre 素材门未过：")
            for e in errors:
                print(f"   • {e}")
            raise SystemExit(2)
        else:
            ready, ready_errors = write_publish_ready(cwd)
            if ready_errors:
                print("❌ publish-ready 封存失败：")
                for e in ready_errors:
                    print(f"   • {e}")
                raise SystemExit(2)
            print(
                "✅ publish --pre 通过并写入事前凭证 "
                f"{PUBLISH_READY_FILE}（digest={ready['manifest_digest'][:12]}）"
            )
        return  # --pre 只判定不标 done
    state = load_state(cwd)
    _t0 = time.perf_counter()
    passed, errors = verify_stage(stage, cwd, state, legacy=legacy)
    waiting_author = (not passed) and _checkpoint_wait(errors)
    # 每条 verify 命令记一笔整体耗时（2026-08-16 审计：观察日志从不记耗时，
    # 阶段耗时画像只能靠 mtime 考古）。失败静默由 log_observation 自身保证。
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contracts import log_observation as _logobs_elapsed
        _logobs_elapsed(
            f"verify_{stage}", "verify_stage_elapsed",
            "ok" if passed else ("waiting_author" if waiting_author else "fail"),
            f"errors={len(errors)}", cwd.name,
            metrics={
                "errors": len(errors),
                "stage_status": (
                    "done" if passed else
                    "waiting_author" if waiting_author else
                    "failed"
                ),
            },
            elapsed_ms=(time.perf_counter() - _t0) * 1000,
        )
    except Exception:
        pass
    if passed:
        _record_stage_success(cwd, state, stage)
        save_state(cwd, state)
        print(f"✅ {stage} 验证通过，已标记 done")
    elif waiting_author:
        _record_stage_waiting_author(cwd, state, stage, errors)
        print(f"⏸ {stage} 已进入 waiting_author；这不是内容失败，也不累计失败次数：")
        for e in errors:
            print(f"   • {e}")
        raise SystemExit(2)
    else:
        state["stages"][stage]["status"] = "failed"
        state["stages"][stage]["last_failed_at"] = _now_iso()
        _invalidate_downstream(state, stage, f"上游 {stage} 验证失败")
        # 累计 fail_count（feedback_autopilot_never_skip_on_failure：连错 3 次才告警）
        prev_count = state["stages"][stage].get("fail_count", 0)
        new_count = prev_count + 1
        state["stages"][stage]["fail_count"] = new_count
        save_state(cwd, state)
        print(f"❌ {stage} 验证失败（连续第 {new_count} 次）：")
        for e in errors:
            print(f"   • {e}")
        if new_count >= 3:
            print()
            print(f"⚠️  此阶段已连续失败 {new_count} 次。")
            print(f"   按 autopilot 失败 SOP，应停下回报用户：")
            print(f"   • 阶段：{stage}")
            print(f"   • 失败原因：见上方")
            print(f"   • 已尝试过哪些恢复方式（请填写）")
            print(f"   禁止用 `pipeline.py skip {stage}` 绕过。"
                  f"如确认是误判，verify 通过即可清零计数。")
        raise SystemExit(2)


def _maybe_trigger_learn_edits(cwd: Path):
    """writing 阶段标 done 时的飞轮触发器（0 破坏性）：
    - 首次（无 .writing-snapshot.md）→ 把当前 定稿.md 快照为 .writing-snapshot.md，作为 agent 版基线
    - 之后再跑 done writing（用户已手改 定稿.md）→ 自动 diff，输出给 Agent 提示提取 pattern

    这个机制让 lessons 飞轮真正转起来——首次写完不打扰，
    用户改完后再次确认 done 时才触发学习，且失败时不影响 done 标记本身。
    """
    draft = cwd / "定稿.md"
    snapshot = cwd / ".writing-snapshot.md"

    if not draft.exists():
        return  # 没定稿（前置 verify 已警告），跳过飞轮

    if not snapshot.exists():
        # 首次：保存基线快照，不打扰
        try:
            import shutil
            shutil.copy2(draft, snapshot)
            print()
            print(f"📸 已快照 agent 版定稿到 .writing-snapshot.md（用于后续 learn_edits 对比）")
            print(f"   下次你手改 定稿.md 后再跑 `pipeline.py done writing`，会自动触发学习。")
        except Exception as e:
            # 快照失败不影响 done，仅提示
            print(f"⚠️  保存 .writing-snapshot.md 失败：{e}（不影响 done 标记）")
        return

    # 已有快照：检查是否有 diff
    try:
        import filecmp
        if filecmp.cmp(draft, snapshot, shallow=False):
            return  # 内容相同，无需学习
    except Exception:
        pass  # 比较失败时仍尝试跑 diff

    # 有 diff：调用 learn_edits.py diff
    learn_edits = SKILL_DIR / "scripts" / "learn_edits.py"
    if not learn_edits.exists():
        print(f"\n⚠️  learn_edits.py 未找到（{learn_edits}），跳过飞轮触发")
        return

    print()
    print("🔍 检测到 .writing-snapshot.md 与当前 定稿.md 存在差异，触发 learn_edits 飞轮：")
    print("─" * 55)
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(learn_edits), "diff",
             "--draft", str(snapshot), "--final", str(draft)],
            capture_output=False, text=True, encoding="utf-8",
            timeout=30,
        )
        if result.returncode != 0:
            print(f"⚠️  learn_edits.py 退出码 {result.returncode}（不影响 done 标记）")
    except subprocess.TimeoutExpired:
        print("⚠️  learn_edits.py 超时 30s（不影响 done 标记）")
    except Exception as e:
        print(f"⚠️  learn_edits.py 调用失败：{e}（不影响 done 标记）")
        print(f"   你可以手动跑：python \"{learn_edits}\" diff "
              f"--draft \".writing-snapshot.md\" --final \"定稿.md\"")
        return

    print("─" * 55)
    print("📝 接下来 Agent 应该：")
    print("   1. 阅读上面 Diff，按 references/learn-edits.md Step 3 提取 pattern")
    print("   2. 追加到 $SKILL/lessons.yaml 的 lessons: 列表")
    print("   3. 跑 `python $SKILL/scripts/learn_edits.py build` 重建 playbook.md")
    print("   完成后如想重置基线：删除 .writing-snapshot.md 即可，下次 done 会重新快照")


def _auto_normalize_punctuation(cwd: Path):
    """done writing 自动前置（2026-06-10）：把 定稿.md 中文紧邻的半角 ,;:!?
    转全角（半角标点门的确定性逆操作，零误伤代码/URL/时间/.mp4）。在 MD→HTML
    之前跑，避免半角带进 HTML、到排版门才 exit 2。0 处命中时静默跳过。"""
    draft = cwd / "定稿.md"
    if not draft.exists():
        return
    sys.path.insert(0, str(Path(__file__).parent))
    from normalize_cjk_punctuation import normalize, _count_hits
    original = draft.read_text(encoding="utf-8")
    hits = _count_hits(original)
    if hits == 0:
        return
    draft.write_text(normalize(original), encoding="utf-8")
    print(f"🔤 已自动归一化中文标点：{hits} 处半角 → 全角（定稿.md，MD→HTML 前置）")


def cmd_done(stage: str, cwd: Path, extras: list, force: bool = False, legacy: bool = False):
    if force or legacy:
        flag = "--force" if force else "--legacy"
        print(f"❌ {flag} 已停用：done 只能由当前阶段验证成功产生")
        raise SystemExit(2)
    # 中文标点归一化必须发生在 draft 审批和摘要校验之前；若它改变正文，旧审批应失效。
    if stage == "writing":
        try:
            _auto_normalize_punctuation(cwd)
        except Exception as e:
            print(f"⚠️  自动标点归一化出错：{e}")
    state = load_state(cwd)
    candidate = copy.deepcopy(state)
    publish_receipt_path = cwd / PUBLISH_RECEIPT_FILE
    publish_receipt_existed = publish_receipt_path.exists()
    publish_receipt_before = (
        publish_receipt_path.read_bytes() if publish_receipt_existed else b""
    )
    publish_receipt_written = False
    explicit_draft_id = any(
        value.split("=", 1)[0].strip() == "draft_media_id"
        for value in extras
        if "=" in value
    )
    if stage == "publish" and explicit_draft_id and not legacy:
        print(
            "❌ 禁止手工登记 draft_media_id；新流程必须使用 "
            "pipeline.py release-to-draft 完成预检、推送和官方读回"
        )
        raise SystemExit(2)

    def restore_publish_receipt():
        if not publish_receipt_written:
            return
        if publish_receipt_existed:
            publish_receipt_path.write_bytes(publish_receipt_before)
        else:
            publish_receipt_path.unlink(missing_ok=True)
    # 写入附加元数据
    for kv in extras:
        if "=" in kv:
            k, v = kv.split("=", 1)
            candidate["stages"][stage][k.strip()] = v.strip()

    # P0：发布前门必须内联执行，不存在绕过参数。只有本地证据链通过，才把
    # 这批确切 HTML/hero/视觉字节绑定到微信返回的 draft_media_id。
    if (
        stage == "publish"
        and explicit_draft_id
        and candidate["stages"][stage].get("draft_media_id")
    ):
        candidate_url = candidate["stages"][stage].get("wechat_url", "")
        if candidate_url and not candidate_url.startswith("https://mp.weixin.qq.com"):
            print(f"❌ wechat_url 不是微信公众号链接：{candidate_url[:80]}")
            raise SystemExit(2)
        _, ready_errors = verify_publish_ready(cwd)
        pre_errors = ready_errors + _pre_publish_errors(cwd, state=candidate)
        if pre_errors:
            info = state["stages"][stage]
            if info.get("status") != "done":
                info["status"] = "failed"
            info["last_failed_at"] = _now_iso()
            info["fail_count"] = int(info.get("fail_count") or 0) + 1
            save_state(cwd, state)
            print("❌ publish 内联素材门未过，不得绕过：")
            for e in pre_errors:
                print(f"   • {e}")
            raise SystemExit(2)
        _, receipt_errors = write_publish_receipt(
            cwd, candidate["stages"][stage]["draft_media_id"]
        )
        if receipt_errors:
            print("❌ 无法写入 publish receipt：")
            for e in receipt_errors:
                print(f"   • {e}")
            raise SystemExit(2)
        publish_receipt_written = True
    # 先跑 verify
    passed, errors = verify_stage(stage, cwd, candidate, legacy=legacy)
    if not passed:
        restore_publish_receipt()
        if _checkpoint_wait(errors):
            _record_stage_waiting_author(cwd, state, stage, errors)
            print(f"⏸ {stage} 已进入 waiting_author；这不是内容失败，也不累计失败次数：")
            for e in errors:
                print(f"   • {e}")
            raise SystemExit(2)
        print(f"⚠️  {stage} 自动检查未全部通过：")
        for e in errors:
            print(f"   • {e}")
        info = state["stages"][stage]
        if not (stage == "publish" and info.get("status") == "done"):
            info["status"] = "failed"
            _invalidate_downstream(state, stage, f"上游 {stage} 完成检查失败")
        info["last_failed_at"] = _now_iso()
        prev_count = info.get("fail_count", 0)
        new_count = prev_count + 1
        info["fail_count"] = new_count
        save_state(cwd, state)
        if new_count >= 3:
            print()
            print(f"⚠️  此阶段已连续失败 {new_count} 次。"
                  f"按 autopilot 失败 SOP，应停下回报用户。")
        raise SystemExit(2)
    try:
        _record_stage_success(cwd, candidate, stage)
        save_state(cwd, candidate)
    except Exception:
        restore_publish_receipt()
        raise
    print(f"✅ {stage} 已标记 done")

    # 2026-04-28 新增：writing 阶段触发 learn_edits 飞轮（首次快照 / 再次 diff）
    # 任何异常都不会影响上面的 done 标记
    if stage == "writing":
        # 实证（整篇几百处半角标点靠手动救）：done writing
        # 自动把 定稿.md 中文紧邻的半角标点转全角，作为 MD→HTML 的确定性前置 ——
        # 半角标点门（format_layout）从此基本是空跑安全网，不再到排版才 exit 2。
        # 必须在 _maybe_trigger_learn_edits 之前，让飞轮基线快照是已归一化版本。
        try:
            _maybe_trigger_learn_edits(cwd)
        except Exception as e:
            print(f"⚠️  learn_edits 飞轮触发出错（不影响 done 标记）：{e}")


def cmd_log(stage: str, tool: str, cwd: Path, output: str = "", cmd: str = "",
            prompt: str = "", renderer: str = "", model: str = "",
            provenance_mode: str = "rendered", style: str = "",
            host_agent: str = "", extend_sha256: str = ""):
    """追加 v2 生图证据：producer、renderer、model、prompt/output 字节摘要。"""
    output = _norm_relpath(output)
    prompt = _norm_relpath(prompt)
    is_final = (
        (stage == "cover" and output == "素材/cover.png")
        or (stage == "hero" and output == "素材/hero.png")
        or (stage == "infographic" and output.startswith("素材/infographic")
            and output.endswith(".png"))
    )
    if is_final:
        print(
            "❌ 最终文章视觉禁止手工 log-render；必须由 render-visuals 调用 "
            "baoyu-image-gen 并自动写入不可变证据"
        )
        raise SystemExit(2)
    prompt_style = ""
    prompt_meta = {}
    prompt_path = cwd / Path(prompt) if prompt else None
    if prompt_path and prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding="utf-8")
        match = re.search(
            r"(?m)^style:\s*[\"']?([^\"'\s]+)",
            prompt_text,
        )
        prompt_style = match.group(1) if match else ""
        prompt_meta = _prompt_frontmatter(prompt_text)
    if style and prompt_style and style != prompt_style:
        print(f"❌ --style={style} 与 prompt frontmatter style={prompt_style} 不一致")
        raise SystemExit(2)
    style = style or prompt_style
    problems = []
    if is_final:
        if tool not in IMAGE_TOOL_WHITELIST.get(stage, set()):
            problems.append(f"producer={tool} 不在 {stage} 白名单")
        if renderer not in IMAGE_RENDERER_WHITELIST:
            problems.append(f"renderer={renderer or '(空)'} 不在允许像素后端")
        if not model:
            problems.append("缺 --model")
        if stage == "infographic" and style not in {"claymation", "morandi-journal"}:
            problems.append("final infographic prompt 缺合法 style frontmatter")
        if not prompt.startswith(FINAL_PROMPT_PREFIX):
            problems.append(f"--prompt 必须位于 {FINAL_PROMPT_PREFIX}")
        if not prompt or not (cwd / Path(prompt)).exists():
            problems.append(f"prompt 不存在：{prompt or '(空)'}")
        if not (cwd / Path(output)).exists():
            problems.append(f"output 不存在：{output}")

    if (
        style == "claymation"
        and stage in {"infographic", "hero"}
        and prompt_path
        and prompt_path.exists()
    ):
        meta = {}
        meta_path = cwd / "article-meta.yaml"
        if meta_path.exists() and _yaml is not None:
            try:
                meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        explicit_profile = str(meta.get("visual_profile") or "").strip()
        recipe = (
            _visual_recipe(explicit_profile)
            if explicit_profile
            else _visual_recipe()
        )
        if not recipe:
            problems.append("无法解析 claymation 视觉配方")
        else:
            problems.extend(_visual_prompt_errors(
                prompt_path.read_text(encoding="utf-8"),
                recipe,
                prompt,
            ))
            output_path = cwd / Path(output) if output else None
            if output_path and output_path.exists():
                problems.extend(_visual_tone_errors(output_path, recipe, output))

    if problems:
        print("❌ 最终视觉产物日志不完整：")
        for problem in problems:
            print(f"   • {problem}")
        raise SystemExit(2)
    rec = {
        "schema_version": 2,
        "record_id": str(uuid.uuid4()),
        "stage": stage,
        "producer": tool,
        "producer_chain": [
            str(value)
            for value in (prompt_meta.get("producer_chain") or [])
            if str(value).strip()
        ],
        "tool": tool,
        "output": output,
        "output_sha256": sha256_file(cwd / Path(output)) if output and (cwd / Path(output)).exists() else "",
        "prompt": prompt,
        "prompt_sha256": sha256_file(cwd / Path(prompt)) if prompt and (cwd / Path(prompt)).exists() else "",
        "renderer": renderer,
        "model": model,
        "style": style,
        "visual_profile": str(prompt_meta.get("visual_profile") or ""),
        "visual_profile_sha256": str(prompt_meta.get("visual_profile_sha256") or ""),
        "visual_contract_owner": str(prompt_meta.get("visual_contract_owner") or ""),
        "visual_contract_revision": str(prompt_meta.get("visual_contract_revision") or ""),
        "host_agent": host_agent or os.environ.get("SANSHENG_HOST_AGENT", ""),
        "orchestrator_skill": "sansheng-write",
        "extend_sha256": extend_sha256,
        "provenance_mode": provenance_mode,
        "cmd": cmd,
        "recorded_at": _now_iso(),
        "timestamp": _now_iso(),  # v1 consumer compatibility
    }
    log_path = cwd / GEN_LOG_FILE
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # 路由白名单提示（不 fail，仅 warn——让 verify 阶段 fail）
    if tool in IMAGE_TOOL_BLACKLIST:
        print(f"⚠️  工具 `{tool}` 在黑名单中，verify {stage} 会 fail")
    elif stage in IMAGE_TOOL_WHITELIST and tool not in IMAGE_TOOL_WHITELIST[stage]:
        print(f"⚠️  工具 `{tool}` 不在 {stage} 白名单 {IMAGE_TOOL_WHITELIST[stage]}")
    print(
        f"📝 已记录：{stage} / producer={tool} / renderer={renderer or '(未填)'}"
        f" → {output or '(no output path)'}"
    )


def cmd_visual_contract(cwd: Path) -> None:
    """打印当前文章应复制进信息图与 Hero canonical prompt 的视觉合同。"""
    meta_path = cwd / "article-meta.yaml"
    if not meta_path.exists() or _yaml is None:
        raise SystemExit("缺 article-meta.yaml 或 PyYAML，无法生成视觉合同")
    meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    style = str(meta.get("infographic_style") or "").strip()
    profile_name = str(meta.get("visual_profile") or "").strip()
    if style != "claymation":
        raise SystemExit("visual-contract 当前只用于 claymation 浅色视觉配方")
    recipe = _visual_recipe(profile_name) if profile_name else _visual_recipe()
    if not recipe:
        raise SystemExit(f"无法解析 visual_profile={profile_name or '(空)'}")
    print("# 复制到每个信息图与 Hero canonical prompt 的 frontmatter")
    print(f"visual_profile: {recipe['name']}")
    print(f"visual_profile_sha256: {recipe['sha256']}")
    print(f"visual_contract_owner: {recipe.get('contract_owner', '')}")
    print(f"visual_contract_revision: {recipe.get('contract_revision', '')}")
    print(f'palette_background: "{recipe["background"]}"')
    print(f'palette_accent: "{recipe["accent"]}"')
    print("\n# Prompt 正文同时保留：暖米黄/浅色调/哑光软黏土/柔和漫射光。")


def cmd_approve(gate: str, cwd: Path, source_mode: str, note: str = ""):
    receipt, errors = write_checkpoint_receipt(cwd, gate, source_mode, note)
    if errors:
        print(f"❌ {gate} 审批对象未就绪：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(
        f"✅ 已封存 {gate} 审批：source_mode={source_mode} "
        f"digest={receipt['artifact_digest'][:12]}"
    )


def cmd_seal(kind: str, cwd: Path):
    if kind != "visual":  # argparse choices 已拦，保留函数级防护
        raise SystemExit(f"未知 seal 类型：{kind}")
    qa_errors = _visual_qa_errors(cwd)
    if qa_errors:
        print("❌ 视觉 QA 未通过，禁止封存：")
        for error in qa_errors:
            print(f"   • {error}")
        raise SystemExit(2)
    receipt, errors = seal_visual_receipt(cwd)
    if errors:
        print("❌ visual receipt 封存失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(f"✅ 已封存最终视觉字节：digest={receipt['manifest_digest'][:12]}")


def cmd_history(cwd: Path, extras: list):
    """[DEPRECATED] 旧的写 history.yaml 命令，已被 archive 取代（二期：works.yaml 是单一数据源）。

    2026-06-20 审查 F/G：return 之后的旧逻辑是不可达死代码（恒被上面的 return 拦下），已删除。
    history.yaml 已冻结，归档一律走 cmd_archive。
    """
    print(f"⚠️ pipeline.py history 已废弃 -- {works_file()} 才是单一数据源（含创作记忆）。")
    print("   请改用：pipeline.py archive（写作品库 + 自动刷新 articles.md/看板/推荐）。")
    print("   未写入 history.yaml（避免污染已冻结的旧文件）。")
    return


def cmd_archive(cwd: Path, extras: list) -> bool:
    """归档：校验候选记录后写作品库，并自动刷新派生视图与推荐卡。

    返回 True＝归档成功；返回 False＝abort（缺 seq/category/wechat_url）。
    2026-07-01：main 分发层据此返回值决定退出码（abort → sys.exit(1)），
    让上游 `&&`/退出码判断能检测归档失败。cmd 本身不 sys.exit（保持可被
    tests 直接调用、断言 capsys 而不触发 SystemExit）。
    """
    from works_registry import (build_upserted_works, load_works, save_works,
                                validate_works, WORKS_FILE)
    import render_articles_md as RAM
    import render_works_dashboard as RWD
    import generate_recommend_html as GRH
    from profile_config import brand, data_dir

    state = load_state(cwd)

    override = {}
    for kv in extras:
        if "=" in kv:
            k, v = kv.split("=", 1)
            override[k.strip()] = v.strip()

    meta, fields, meta_errors = _archive_metadata(
        cwd, state, require_url=True, override=override
    )
    preflight_errors = [*meta_errors, *_archive_source_errors(cwd)]
    if preflight_errors:
        _log_archive_event(
            cwd,
            "preflight",
            "fail",
            f"preflight_errors={len(preflight_errors)}",
            error_count=len(preflight_errors),
        )
        print("❌ 归档前置检查未通过（作品库未写入）：")
        for error in preflight_errors:
            print(f"   • {error}")
        return False

    seq = int(cwd.name.split("-", 1)[0])

    category = fields["category"]
    outward = fields["outward_category"]
    title = fields["title"]
    url = fields["wechat_url"]

    cover_rel = ""
    if (cwd / "素材" / "cover.png").exists():
        cover_rel = f"<数据目录>/{cwd.name}/素材/cover.png"

    draft = cwd / "定稿.md"
    wc = len(draft.read_text(encoding="utf-8")) if draft.exists() else 0
    current_works = load_works()
    existing = next((work for work in current_works if work.get("seq") == seq), None) or {}
    default_video = {"status": "none", "url": "", "platform": "",
                     "script_path": "", "hook_type": "", "duration_sec": 0, "shots": 0}

    record = {
        "seq": seq,
        "category": category,
        "outward_category": outward,
        "tags": fields["tags"],
        "series": meta.get("series", "") or existing.get("series", "") or "",
        "merged_into": existing.get("merged_into", "") or "",
        "date": override.get("date") or existing.get("date") or datetime.now().strftime("%Y-%m-%d"),
        "title": title,
        "digest": fields["digest"],
        "cover": cover_rel or existing.get("cover", "") or "",
        "wechat_url": url,
        "status": "published",
        "style": meta.get("style", "") or existing.get("style", "") or "",
        "logic_bone": meta.get("logic_bone", "") or existing.get("logic_bone", "") or "",
        "dimensions": meta.get("dimensions", []) or existing.get("dimensions", []) or [],
        "closing_type": meta.get("closing_type", "") or existing.get("closing_type", "") or "",
        "cover_keywords": meta.get("cover_keywords", "") or existing.get("cover_keywords", "") or "",
        "cover_style": meta.get("cover_style", "") or existing.get("cover_style", "") or "",
        "word_count": wc or existing.get("word_count", 0) or 0,
        "video": existing.get("video") or default_video,
    }
    works, saved = build_upserted_works(current_works, record)
    errors = validate_works(works)
    if errors:
        _log_archive_event(cwd, "registry_write", "fail",
                           f"registry_errors={len(errors)}", error_count=len(errors))
        print(f"❌ 候选作品库校验失败，未写入 {WORKS_FILE}：")
        for error in errors:
            print(f"   • {error}")
        return False

    # 全部派生产物先在内存生成；候选数据无误后才落盘，避免半成功。
    articles_html = RAM.render_md(works)
    dashboard_html = RWD.build_html(works)
    recommend_result = GRH.generate_recommend_html(GRH.articles_from_works(works))

    save_works(works)
    RAM.ARTICLES_MD.write_text(articles_html, encoding="utf-8")
    RWD.DASHBOARD_FILE.write_text(dashboard_html, encoding="utf-8")
    recommend_path = data_dir() / "recommend_articles.html"
    if recommend_result is not None:
        recommend_html, recommended = recommend_result
        recommend_path.write_text(recommend_html, encoding="utf-8")
    else:
        recommended = []

    print(f"✅ 已写入作品库：{saved.get('code')} · {title}")
    print(f"   作品库：{WORKS_FILE}")
    print(f"   派生视图：{RAM.ARTICLES_MD}；{RWD.DASHBOARD_FILE}")
    if recommended:
        print(f"   推荐卡：{recommend_path}（{' / '.join(item['title'] for item in recommended)}）")
    else:
        print("   推荐卡：有效封面文章不足 5 篇，本轮未生成（不阻断归档）")

    _log_archive_event(cwd, "registry_write", "ok", f"code={saved.get('code')}")
    return True


def _archived_code(cwd: Path) -> str:
    """Read CODE from this worktree's 作品库.yaml. Fail closed.

    不得回落到全局 WORKS_FILE：那份指针常钉在主仓，子 worktree 归档后主仓
    读出来是空的。2026-08-21 OBS-30 因此以空 CODE 跑完官网同步——HTML 上线，
    article-assets / song-assets 仍受保护没上传，封面、正文图、主题曲全 404。
    """
    seq_text = cwd.name.split("-", 1)[0]
    if not seq_text.isdigit():
        raise ValueError(f"文章目录名读不出序号：{cwd.name}")
    works_path = cwd.parent / "作品库.yaml"
    if not works_path.is_file():
        raise FileNotFoundError(f"本 worktree 找不到作品库：{works_path}")
    if _yaml is None:
        raise RuntimeError("需要 PyYAML 才能读取作品库")
    data = _yaml.safe_load(works_path.read_text(encoding="utf-8")) or {}
    seq = int(seq_text)
    record = next(
        (item for item in (data.get("works") or []) if item.get("seq") == seq),
        None,
    )
    code = str((record or {}).get("code") or "").strip()
    if not code:
        raise RuntimeError(f"作品库 {works_path} 里序号 {seq} 没有 CODE")
    return code


# 构建工具的进度行（git checkout / npm / rsync 都会刷成千上万行），它们在
# capture_output 下不会被 \r 覆盖，而是原样堆进 stdout。
_PROGRESS_NOISE = re.compile(
    r"^\s*(?:Updating files:|Receiving objects:|Resolving deltas:|"
    r"remote: (?:Counting|Compressing|Total)|\[?=+>?\s*\]?\s*\d+%|"
    r"\d+(?:\.\d+)?%\s*$)"
)


def _diagnostic_tail(*streams: str, lines: int = 25, limit: int = 2000) -> str:
    """取**尾部**若干条有效行 —— 报错在末尾，不在开头。

    🔴 2026-08-14 第 89 篇实跑教训：原实现是
    ``(stderr or stdout).strip()[:500]``，从**开头**截 500 字。而
    ``git worktree add`` 会先刷几百行 ``Updating files: NN%``，于是屏幕上
    永远只有进度条，真正的失败原因（世界史 canonical 门禁）一次都没露过面。
    实测为了看到那一行，多跑了两轮共二十多分钟。

    截头还是截尾不是风格问题：命令行工具的诊断信息**总在末尾**。
    """
    body = ""
    for stream in streams:
        if (stream or "").strip():
            body = stream
            break
    if not body.strip():
        return "（命令没有任何输出）"
    kept = [
        line.rstrip()
        for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip() and not _PROGRESS_NOISE.match(line)
    ]
    if not kept:
        kept = [line.rstrip() for line in body.split("\n") if line.strip()]
    text = "\n".join(f"   {line}" for line in kept[-lines:])
    return text[-limit:] if len(text) > limit else text


def _append_website_sync_attempt(receipt_path: Path, attempt: dict) -> None:
    """Preserve website retry history instead of overwriting the last failure."""
    previous: dict = {}
    if receipt_path.is_file():
        try:
            previous = json.loads(receipt_path.read_text(encoding="utf-8")) or {}
        except Exception:
            previous = {}
    attempts = list(previous.get("attempts") or [])
    if not attempts and previous.get("created_at"):
        attempts.append(
            {key: value for key, value in previous.items() if key != "attempts"}
        )
    attempts.append(attempt)
    payload = {
        "schema_version": 2,
        "status": attempt.get("status", "failed"),
        "latest": attempt,
        "attempts": attempts[-20:],
    }
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_website_command(command: str) -> tuple[str, str]:
    """Resolve Git Bash explicitly on Windows; return (command, error)."""
    if os.name != "nt" or not re.match(r"^\s*bash(?:\.exe)?(?:\s|$)", command, re.I):
        return command, ""
    candidates = [
        shutil.which("bash"),
        str(Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"),
        str(Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/bash.exe"),
        str(Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Git/bin/bash.exe"),
    ]
    bash = next((Path(value) for value in candidates if value and Path(value).is_file()), None)
    if bash is None:
        return "", (
            "website_command 需要 bash，但当前进程 PATH 与常见 Git for Windows 目录均未找到；"
            "请安装 Git Bash，或把 profile.publish.website_command 改成 PowerShell 命令"
        )
    rest = re.sub(r"^\s*bash(?:\.exe)?", "", command, count=1, flags=re.I)
    return f'"{bash}"{rest}', ""


def _uncommitted_archive_outputs(cwd: Path, website_cwd: Path) -> list[str]:
    """列出还没提交的归档产物（官网构建看不见它们）。

    🔴 2026-08-04：官网发布走「从指定 commit 建隔离工作树再构建」，构建器只认
    commit 里的内容。而 ``archive`` 只把作品库、articles.md、看板、推荐卡**写到
    工作区**，不提交。结果构建读到一份没有本篇的旧作品库，文章页压根没生成，
    最后在 ``build-site-release.ps1`` 的产物校验处以「文章页面未进入构建产物：
    <CODE>」失败 —— 那时已经白跑了一万九千多个文件的 checkout 加一次完整构建，
    十几分钟。所以这个检查必须前置到几秒内完成。

    不是 git 仓库、git 不可用或路径不在仓内时返回空列表（不拦）。
    """
    try:
        from profile_config import works_file
        works = Path(works_file())
    except Exception:                                            # noqa: BLE001
        return []
    targets = [works, cwd]
    for name in ("articles.md", "works-dashboard.html", "recommend_articles.html"):
        targets.append(works.parent / name)
    args = ["git", "-C", str(website_cwd), "status", "--porcelain", "--"]
    args += [str(t) for t in targets]
    try:
        probe = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if probe.returncode != 0:
        return []
    # 🔴 2026-08-16 第 90 篇实跑修：**本检查自己写的回执要排除掉**。
    #    `_append_website_sync_attempt` 每次失败都会更新 `_website-sync-receipt.json`，
    #    而它就在被扫描的文章目录里 —— 于是「提交回执 → 重跑 → 回执又被更新 → 又判未提交」
    #    形成死循环，实测卡了三轮才靠人工绕开。回执是**本次运行的产物**，不是
    #    官网构建需要的归档产物（构建只读作品库与派生视图），扫它没有意义。
    _SELF_WRITTEN = ("_website-sync-receipt.json", "_finalize-state.json")
    return [
        line.strip()
        for line in (probe.stdout or "").splitlines()
        if line.strip() and not any(name in line for name in _SELF_WRITTEN)
    ]


def _run_website_sync(
    cwd: Path,
    wechat_url: str,
    *,
    runner=subprocess.run,
) -> bool:
    """Run the profile-owned website command only after archive verification."""
    publish = brand().get("publish") or {}
    template = str(publish.get("website_command") or "").strip()
    configured_cwd = (
        os.getenv("SANSHENG_WRITE_WEBSITE_CWD", "").strip()
        or str(publish.get("website_cwd") or "").strip()
    )
    receipt_path = cwd / "_website-sync-receipt.json"
    if not template:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "skipped",
                "reason": "profile.publish.website_command 未配置",
                "created_at": _now_iso(),
            },
        )
        print("⏭ 官网同步未配置，已记录 skipped（不影响公开 Skill 使用）")
        return True

    website_cwd = Path(configured_cwd).expanduser() if configured_cwd else cwd
    if not website_cwd.is_dir():
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "website_cwd_not_found",
                "cwd": str(website_cwd),
                "created_at": _now_iso(),
            },
        )
        print(f"❌ 官网同步工作目录不存在：{website_cwd}")
        return False
    try:
        code = str(_archived_code(cwd) or "").strip()
    except Exception as exc:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "article_code_missing",
                "detail": str(exc)[:300],
                "created_at": _now_iso(),
            },
        )
        print(f"❌ 官网同步拿不到文章 CODE：{exc}")
        print("   空 CODE 会让 HTML 上线而封面/正文图/主题曲全部 404。")
        return False
    if not code:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "article_code_missing",
                "created_at": _now_iso(),
            },
        )
        print("❌ 官网同步拒绝空 CODE：不传编号时资产仍受保护，不会上传。")
        return False
    values = {
        "code": code,
        "article_dir": str(cwd),
        "wechat_url": wechat_url,
    }
    try:
        command = template.format(**values)
    except (KeyError, ValueError) as exc:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "website_command_template_error",
                "detail": str(exc)[:300],
                "created_at": _now_iso(),
            },
        )
        print(f"❌ website_command 模板字段错误：{exc}")
        return False
    command, resolution_error = _resolve_website_command(command)
    if resolution_error:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "website_command_unavailable",
                "detail": resolution_error,
                "created_at": _now_iso(),
            },
        )
        print(f"❌ 官网同步前置检查失败：{resolution_error}")
        return False
    pending = _uncommitted_archive_outputs(cwd, website_cwd)
    if pending:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "archive_outputs_uncommitted",
                "pending": pending[:20],
                "created_at": _now_iso(),
            },
        )
        print("❌ 官网同步前置检查失败：归档产物还没提交，构建会看不见本篇。")
        for line in pending[:12]:
            print(f"     {line}")
        print("   官网发布从 commit 建隔离工作树，只认 commit 里的内容；"
              "留在工作区的作品库等于没写。")
        print("   先用显式 pathspec 提交，再重跑 finalize："
              "git add <上列文件> && git commit -m \"chore(write): <N> 号归档产物入库\"")
        return False
    try:
        completed = runner(
            command,
            cwd=str(website_cwd),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            # 🔴 2026-08-15 实测：一次真实授权发布（全站构建+素材打包上传+激活+CDN
            # 失效+逐篇封面验证）约 20 分钟，900s 会把发布进程在构建/上传中途杀掉，
            # OBS-27 的 finalize 就是这么超时的（还留下 locked 构建 worktree 残留）。
            # 留足余量到 40 分钟；发布器内部各环节有自己的失败路径，不靠这里兜底。
            timeout=int(os.getenv("SANSHENG_WRITE_WEBSITE_TIMEOUT", "2400")),
            check=False,
        )
    except Exception as exc:
        _append_website_sync_attempt(
            receipt_path,
            {
                "status": "failed",
                "reason": "website_command_exception",
                "detail": str(exc)[:500],
                "command_sha256": stable_digest({"command": command}),
                "cwd": str(website_cwd),
                "created_at": _now_iso(),
            },
        )
        print(f"❌ 官网同步命令异常：{str(exc)[:500]}")
        return False
    receipt = {
        "status": "done" if completed.returncode == 0 else "failed",
        "created_at": _now_iso(),
        "code": values["code"],
        "wechat_url": wechat_url,
        "command_sha256": stable_digest({"command": command}),
        "cwd": str(website_cwd),
        "returncode": completed.returncode,
        "stdout_sha256": stable_digest({"stdout": completed.stdout or ""}),
        "stderr_sha256": stable_digest({"stderr": completed.stderr or ""}),
    }
    if completed.returncode != 0:
        # 失败时把可读的尾部一并落盘。只存 sha256 等于把唯一一份诊断信息扔了：
        # 命令是 capture_output 跑的，输出不在任何终端里，重跑一次要十几分钟。
        receipt["tail"] = _diagnostic_tail(completed.stderr, completed.stdout)
    _append_website_sync_attempt(receipt_path, receipt)
    if completed.returncode != 0:
        print(f"❌ 官网同步失败（exit={completed.returncode}）：")
        print(receipt["tail"])
        print(f"   完整回执：{receipt_path}")
        return False
    print(f"✅ 官网同步完成：code={values['code'] or '(无编号)'}")
    return True


def _write_moments_copy(cwd: Path, wechat_url: str) -> str:
    """Generate the 3-paragraph Moments handoff; never repeat the WeChat URL."""
    meta = {}
    meta_path = cwd / "article-meta.yaml"
    if meta_path.is_file() and _yaml is not None:
        meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    profile = brand()
    title = str(meta.get("title") or "").strip()
    digest = str(meta.get("digest") or meta.get("description") or "").strip()
    cta = str((profile.get("writing") or {}).get("moments_cta") or "").strip()
    site = str((profile.get("identity") or {}).get("site") or "").strip()
    tail = cta or site or "打开上方文章卡片阅读全文"
    site_host = urlparse(site).netloc.lower().removeprefix("www.") if site else ""
    if site and site not in tail and (not site_host or site_host not in tail.lower()):
        tail = f"{tail} · {site}"
    lines = [f"🔥 {title}", f"🧭 {digest}", f"👉 {tail}"]
    # 朋友圈交付是纯文本协议：首句直接起始、段落之间一个空行，去除
    # 普通空白及常见不可见字符，避免 Markdown/富文本复制后出现首行缩进。
    clean_lines = [
        line.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
        .strip()
        for line in lines
    ]
    clean_lines = [line for line in clean_lines if line]
    text = "\n\n".join(clean_lines) + "\n"
    out = cwd / "_moments-copy.md"
    # 🔴 2026-08-04：本函数产出的是**基线**（title + digest + 引流三行拼接），
    # 按 publish.md §朋友圈内容协议还要被改写成终稿。finalize 是可续跑的，
    # 续跑时绝不能把改写后的终稿冲回模板 —— 只在文件不存在、为空、或内容仍是
    # 模板原样时才写盘。要重新取基线就先删掉该文件再跑。
    if out.is_file():
        existing = out.read_text(encoding="utf-8")
        if existing.strip() and existing != text:
            print("⏭ _moments-copy.md 已按内容协议改写过，保留现有终稿，不覆盖为模板基线。")
            return existing
    out.write_text(text, encoding="utf-8")
    print(
        "✅ 已生成朋友圈文案基线：_moments-copy.md"
        "（模板拼接，非终稿 -- 交付前须按 publish.md §朋友圈内容协议改写并写回；不自动发朋友圈）"
    )
    return text


# 收尾链的顺序（后面的步骤依赖前面的产物，别单独手跑中间某步就当收尾完了）
FINALIZE_STEPS: tuple[tuple[str, str], ...] = (
    ("publish_link", "登记永久链接"),
    ("archive", "归档进作品库"),
    ("archive_verify", "校验归档"),
    ("moments_copy", "生成朋友圈文案"),
    ("distribution", "分发（播客等）"),
    ("website_sync", "同步官网并推配图/音频"),
)


def _report_finalize_abort(state: dict, failed_step: str) -> None:
    """中断时把**后面还没跑的步骤**点名喊出来。

    🔴 2026-08-14 第 89 篇实跑教训：finalize 在 distribution（播客）上
    SystemExit(3) 退出，屏幕上只有一行播客的报错。人看到播客失败就以为
    「补跑一次播客即可」，手动补跑后收工 —— 而 website_sync 排在它后面，
    从头到尾没执行过。结果是文章正文被别的部署顺带带上了线、配图和音频
    却从没上传，线上整页破图，且**零报警**。

    失败本身不是问题，问题是失败时没说清「这条链还剩什么没做」。
    """
    names = [key for key, _ in FINALIZE_STEPS]
    if failed_step not in names:
        return
    done = state.get("steps") or {}
    remaining = [
        (key, label) for key, label in FINALIZE_STEPS[names.index(failed_step) + 1:]
        if (done.get(key) or {}).get("status") != "done"
    ]
    print(f"\n🔴 finalize 在「{failed_step}」中断，收尾链**没有走完**。")
    if remaining:
        print("   后面这些步骤一次都没执行：")
        for key, label in remaining:
            print(f"     · {key} -- {label}")
        print("   修好中断原因后请**重跑 finalize**（可续跑，已完成的步骤会跳过）；")
        print("   只手动补跑失败的那一步不会把后面的步骤带起来。")
    else:
        print("   后续步骤此前已完成，只需修好本步。")


def cmd_moments_copy(cwd: Path) -> None:
    """Milliseconds-only handoff for an existing article; no finalize side effects."""
    _write_moments_copy(cwd, "")


def _finalize_input_digest(cwd: Path, wechat_url: str) -> str:
    watched = [
        "article-meta.yaml",
        "定稿.md",
        "定稿.html",
        PUBLISH_RECEIPT_FILE,
        "_wechat-audio-receipt.json",
        "_wechat-published-audio-receipt.json",
    ]
    files = {
        rel: sha256_file(cwd / rel) if (cwd / rel).is_file() else ""
        for rel in watched
    }
    return stable_digest(
        {
            "contract_revision": FINALIZE_STATE_SCHEMA,
            "wechat_url": wechat_url,
            "files": files,
        }
    )


def _load_or_reset_finalize_state(cwd: Path, wechat_url: str) -> dict:
    path = cwd / FINALIZE_STATE_FILE
    digest = _finalize_input_digest(cwd, wechat_url)
    previous: dict = {}
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            previous = {}
    if previous.get("input_digest") == digest:
        return previous

    history = list(previous.get("history") or [])
    if previous.get("input_digest"):
        history.append(
            {
                "input_digest": previous.get("input_digest"),
                "updated_at": previous.get("updated_at"),
                "steps": previous.get("steps") or {},
            }
        )
    state = {
        "schema_version": FINALIZE_STATE_SCHEMA,
        "input_digest": digest,
        "wechat_url": wechat_url,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "steps": {},
        "history": history[-10:],
    }
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


def _finalize_step_done(state: dict, step: str) -> bool:
    return (state.get("steps") or {}).get(step, {}).get("status") == "done"


def _mark_finalize_step(cwd: Path, state: dict, step: str) -> None:
    state.setdefault("steps", {})[step] = {
        "status": "done",
        "completed_at": _now_iso(),
    }
    state["updated_at"] = _now_iso()
    (cwd / FINALIZE_STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cmd_finalize(wechat_url: str, cwd: Path) -> None:
    """Resumable close-out: link → archive → Moments → podcast → website.

    Moments copy comes right after archive verification on purpose: it only
    needs title/digest/permanent link, so it must not wait behind the podcast
    audio (10-30 min) that the website sync legitimately depends on.
    """
    if not re.match(r"^https://mp\.weixin\.qq\.com/s/[^\s]+$", wechat_url or ""):
        print(f"❌ 不是合法公众号永久链接：{wechat_url!r}")
        raise SystemExit(2)

    preflight_errors = _finalize_preflight_errors(cwd, wechat_url)
    if preflight_errors:
        print("❌ finalize 前置检查未通过（尚未修改发布状态或作品库）：")
        for error in preflight_errors:
            print(f"   • {error}")
        raise SystemExit(2)

    state = _load_or_reset_finalize_state(cwd, wechat_url)

    if _finalize_step_done(state, "publish_link"):
        print("⏭ finalize 续跑：发布链接已登记，跳过。")
    else:
        cmd_done("publish", cwd, [f"wechat_url={wechat_url}"])
        _mark_finalize_step(cwd, state, "publish_link")

    if _finalize_step_done(state, "archive"):
        print("⏭ finalize 续跑：作品库已归档，跳过。")
    else:
        if not cmd_archive(cwd, []):
            raise SystemExit(2)
        _mark_finalize_step(cwd, state, "archive")

    if _finalize_step_done(state, "archive_verify"):
        print("⏭ finalize 续跑：归档已验证，跳过。")
    else:
        cmd_verify("archive", cwd)
        _mark_finalize_step(cwd, state, "archive_verify")

    # 🔴 2026-08-04 作者要求前移：朋友圈文案只依赖标题、摘要和永久链接，
    # 到这一步三样都已就位；它不依赖播客音频，也不依赖官网。原先排在整条链
    # 最后，撞上「官网同步必须等播客音频」那条规则后，作者要等一个 10-30 分钟
    # 的音频才拿到文案 —— 而首发那几小时恰恰是最需要它发朋友圈的时候。
    if _finalize_step_done(state, "moments_copy"):
        print("⏭ finalize 续跑：朋友圈文案已生成，跳过。")
    else:
        _write_moments_copy(cwd, wechat_url)
        _mark_finalize_step(cwd, state, "moments_copy")

    # 自动播客必须在官网同步之前完成。网站 import/prepare-songs 只会把已经
    # 存在于文章目录的 dist/podcast/audio.mp3 带进版本包；旧顺序先部署网站、
    # 最后才生成播客，必然让首发页面只剩主题曲。
    distribution_was_done = _finalize_step_done(state, "distribution")
    website_was_done = _finalize_step_done(state, "website_sync")
    if distribution_was_done:
        print("⏭ finalize 续跑：分发计划已处理，跳过。")
    elif not _handoff_to_distribute(cwd):
        # 显式启用的自动播客没完成就不能先部署一个缺音频的网站版本，
        # 也不能把「plan 已生成」误报成「播客已上线」。
        _report_finalize_abort(state, "distribution")
        raise SystemExit(3)
    else:
        _mark_finalize_step(cwd, state, "distribution")
        # 兼容 v0.12.1 曾经留下的“官网已同步、播客后生成”断点：播客刚落盘时
        # 让 website_sync 失效并重跑，不能沿用那个缺音频的旧成功标记。
        if website_was_done and (cwd / "dist" / "podcast" / "audio.mp3").is_file():
            state.setdefault("steps", {}).pop("website_sync", None)
            state["updated_at"] = _now_iso()
            (cwd / FINALIZE_STATE_FILE).write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print("↻ 检测到播客晚于旧官网步骤生成，官网同步将重新执行。")

    if _finalize_step_done(state, "website_sync"):
        print("⏭ finalize 续跑：官网已同步，跳过。")
    else:
        if not _run_website_sync(cwd, wechat_url):
            raise SystemExit(2)
        _mark_finalize_step(cwd, state, "website_sync")

    print("✅ 发布后闭环完成：归档已验、朋友圈文案已出、播客已处理、官网已同步。")


def _handoff_to_distribute(cwd: Path) -> bool:
    """finalize 只处理有长期授权的播客；社媒必须按篇显式触发。

    小红书 / 微博即使在 profile 中启用，也不会因为文章拿到永久链接就自动规划。
    作者明确说「转小红书 / 发微博」后，Agent 才另行运行
    ``distribute plan --only ...``。RSS 没有发布按钮：profile 的
    ``podcast.auto_after_finalize: true`` 是长期授权，因此必须生成到 receipt
    才算完成。失败返回 False，让 finalize 非零退出；已经完成的归档/官网同步不回滚。
    """
    try:
        import distribute
    except ImportError:
        return True
    enabled = distribute.enabled_channels()
    if "podcast" not in enabled:
        return True
    podcast_cfg = distribute.channel_config("podcast")
    podcast_auto = (
        bool(podcast_cfg.get("auto_after_finalize"))
    )
    if not podcast_auto:
        return True

    try:
        print()
        distribute.cmd_plan(cwd, only="podcast")
    except Exception as e:                                  # noqa: BLE001
        print(f"⚠ 播客分发计划生成失败（不影响已完成的发布收尾）：{str(e)[:200]}")
        return False

    receipt = distribute.channel_dir(cwd, "podcast") / distribute.RECEIPT_FILE
    try:
        import podcast_episode
        podcast_fresh = podcast_episode.generation_is_fresh(cwd, podcast_cfg)
    except Exception:
        podcast_fresh = False
    if (
        receipt.is_file()
        and distribute.get_status(cwd, "podcast") == "dispatched"
        and not distribute._is_drifted(cwd, "podcast")
        and podcast_fresh
    ):
        print("✓ 播客已有与当前定稿一致的 receipt，跳过重复生成。")
        return True

    print()
    print("播客已配置 auto_after_finalize=true，继续自动生成并推送 RSS…")
    try:
        rc = podcast_episode.cmd_generate(cwd)
        if rc != 0:
            print(
                "✗ 播客生成未完成。若提示认证失效，请运行 `nlm login` 后重跑 finalize；"
                "这是重新授权，不是手动生成音频。"
            )
            return False
        rc = podcast_episode.cmd_publish(cwd, confirm=True)
        if rc != 0:
            print("✗ 播客上传或 feed 重建失败；没有 receipt，不算上线。")
            return False
    except Exception as e:                                  # noqa: BLE001
        print(f"✗ 播客自动分发异常：{str(e)[:300]}")
        return False
    return True


def cmd_podcast_pregen(cwd: Path):
    """定稿冻结点预生成播客音频（2026-08-16 审计 P4）。

    NotebookLM 生成实测 ~18 分钟，原本卡在 finalize 串行链中段、堵住后面的
    官网同步（89 篇它一失败，官网晚了 5 小时）。本命令允许在**最后一个会改写
    `定稿.md` 的机械步骤之后**（assemble-release 的信息图机器块 + BGM 的
    AUDIO-CARD 都已注入）生成同级 PODCAST-CARD 与音频；finalize 的 distribution 步靠
    `podcast_episode.cmd_generate` 的预生成短路直接取件。

    为什么闸在两个 marker 上：播客语义摘要会剥离全部机器装配块，但仍必须等
    作者正文冻结；公众号嵌入开启时，PODCAST-CARD 还必须在 Markdown→HTML 前写入。
    标题、正文、提示词或生成参数变化都会让预生成凭证失效。
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import distribute

    if "podcast" not in distribute.enabled_channels():
        print("⚠ podcast 渠道未启用（profile distribute 配置），无事可做")
        return
    final_md = cwd / "定稿.md"
    if not final_md.is_file():
        print("❌ 缺 定稿.md")
        raise SystemExit(2)
    text = final_md.read_text(encoding="utf-8")
    gate_missing = []
    if "<!-- SANSHENG-VISUAL-START:" not in text:
        gate_missing.append("assemble-release 的信息图机器块")
    if "<!-- AUDIO-CARD-START -->" not in text:
        gate_missing.append("BGM 的 AUDIO-CARD")
    if gate_missing:
        _log_audio_event(
            cwd, "podcast_pregen", "fail",
            f"missing_gates={len(gate_missing)}", error_count=len(gate_missing),
        )
        print(f"❌ 定稿尚缺：{'、'.join(gate_missing)}——预生成必须晚于全部")
        print("   会改写 定稿.md 的机械步骤，否则音频与最终定稿哈希不一致，")
        print("   finalize 取件短路失效、还得重生成一遍。先走完视觉链与 BGM。")
        raise SystemExit(2)
    # 先写卡再生成：这样排版可与耗时的 NotebookLM 任务并行；如果生成失败，
    # 发布素材门会因缺同源 audio.mp3/状态凭证而拒绝把空卡推入草稿箱。
    if distribute.podcast_wechat_embed_enabled():
        from audio_cards import upsert_card
        changed = upsert_card(final_md, "podcast", "AI 生成 · 双主持")
        print("✓ 播客卡已写入定稿末尾" if changed else "✓ 播客卡无需更新")

    import podcast_episode
    rc = podcast_episode.cmd_generate(cwd)
    if rc == 0:
        _log_audio_event(cwd, "podcast_pregen", "ok", "generation_receipt=fresh")
        print("✓ 播客预生成完成；现在可排版，finalize 到 distribution 步会直接取件")
    else:
        _log_audio_event(
            cwd, "podcast_pregen", "fail", f"exit_code={rc}", error_count=1
        )
    raise SystemExit(rc)


def _preflight_checks(cwd: Path) -> list[tuple[str, str, str]]:
    """收集所有「纯静态、不依赖昂贵操作」的检查结果。

    返回 [(级别, 检查名, 说明)]，级别 ∈ {"fail", "warn", "ok"}。

    🔴 2026-08-14 第 89 篇实跑后新增。那一篇的实测账本：
    verify_publish 反复 8 轮、verify_layout 6 轮、format_layout 4 轮。
    逐条复盘发现，卡住我的东西全是**纯静态检查**，却被放在链条末端：

      缺 _draft-qc.md      → approve draft 才报（本可在进闸门前）
      缺 _opening-choice.md → done writing 才报（本可在盲选完成时）
      开篇标识不足          → **排版阶段**才报（本可写完正文就扫）
      文末缺 DEEP READ/SOURCES → **排版阶段**才报
      金句库缺来源标记      → **finalize** 才报（迟了整整五个阶段）
      part_subtitles 不对齐 → 排版前置断言才报

    每迟报一个阶段，就意味着「回头改 → 重跑中间所有步骤」。
    本函数把它们集中到一个不花任何配额的命令里，写完正文跑一次即可。
    """
    results: list[tuple[str, str, str]] = []
    draft = cwd / "定稿.md"

    def add(level: str, name: str, detail: str) -> None:
        results.append((level, name, detail))

    # --- 1. 闸门锚点文件 ---
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from profile_config import workflow_checkpoints
        cps = set(workflow_checkpoints())
    except Exception:
        cps = set()

    if "blueprint" in cps:
        add("ok" if (cwd / "_blueprint-approval.md").exists() else "fail",
            "blueprint 锚点",
            "_blueprint-approval.md 存在" if (cwd / "_blueprint-approval.md").exists()
            else "缺 _blueprint-approval.md（蓝图闸启用时必需）")
    if "draft" in cps:
        for fname, why in (
            ("_draft-approval.md", "定稿闸审批锚点"),
            ("_draft-qc.md", "定稿闸质检报告（approve draft 会强制要求）"),
            ("_opening-choice.md", "开头盲选记录（done writing 会检查）"),
        ):
            exists = (cwd / fname).exists()
            add("ok" if exists else "fail", fname,
                "存在" if exists else f"缺失 —— {why}")

    # --- 1b. 标题公式门（可正则判定的那一半，覆盖性仍靠 title.md 7 步质检）---
    try:
        from contracts import verify_title_contract
        tc = verify_title_contract(str(cwd))
        verdict = tc.get("verdict")
        add({"fail": "fail", "warn": "warn"}.get(verdict, "ok"),
            "标题公式（title.md）", tc.get("notes", ""))
    except Exception as exc:
        add("warn", "标题公式（title.md）", f"检查异常：{exc}")

    # --- 1b2. cover_portrait 声明（声明了就得可追溯：文件在、来源与许可齐）---
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import yaml as _yaml
        from cover_portrait import portrait_spec, validate as _validate_portrait

        meta_file = cwd / "article-meta.yaml"
        if meta_file.is_file():
            _meta = _yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
            _spec = portrait_spec(_meta)
            if str(_spec.get("file") or "").strip():
                _errs = _validate_portrait(_spec, cwd)
                add("fail" if _errs else "ok", "封面真实肖像声明（cover_portrait）",
                    "；".join(_errs) if _errs
                    else "文件、来源、许可齐备；渲染后跑 cover_portrait.py 合成")
    except Exception as exc:
        add("warn", "封面真实肖像声明（cover_portrait）", f"检查异常：{exc}")

    # --- 1c. 封面 L1/L2 与外标题的分工（锚点有意重复，那一句不许重复）---
    try:
        from contracts import verify_cover_title_pair
        cp = verify_cover_title_pair(str(cwd))
        add({"fail": "fail", "warn": "warn"}.get(cp.get("verdict"), "ok"),
            "封面/标题分工（title.md）", cp.get("notes", ""))
    except Exception as exc:
        add("warn", "封面/标题分工（title.md）", f"检查异常：{exc}")

    # --- 2. 外审产物 ---
    for fname, why in (
        ("_fact-check.md", "事实复核（独立上下文 subagent）"),
        ("_stutter-list.md", "语义冷读（独立上下文 subagent）"),
    ):
        exists = (cwd / fname).exists()
        add("ok" if exists else "warn", fname,
            "存在" if exists else f"缺失 —— {why}")

    if not draft.exists():
        add("fail", "定稿.md", "不存在，后续检查跳过")
        return results

    text = draft.read_text(encoding="utf-8")

    # --- 3. H2 与 part_subtitles 对齐 ---
    try:
        from contracts import verify_h2_subtitle_align as _align_check
        align = _align_check(str(cwd))
        add("ok" if align.get("verdict") != "fail" else "fail",
            "H2/part_subtitles 对齐",
            align.get("notes", ""))
    except Exception as exc:
        add("warn", "H2/part_subtitles 对齐", f"检查异常：{exc}")

    # --- 4. 加粗密度（软超只提示）---
    try:
        from contracts import verify_bold_density
        bd = verify_bold_density(text)
        verdict = bd.get("verdict")
        level = "fail" if verdict in (
            "bold_over", "integral_bold_violation", "both_violations"
        ) else ("warn" if verdict == "soft_over" else "ok")
        add(level, "加粗密度", bd.get("notes", ""))
    except Exception as exc:
        add("warn", "加粗密度", f"检查异常：{exc}")

    # --- 5. 开篇重点标识（排版阶段的硬门，此处前移）---
    body = re.sub(r"^---.*?---", "", text, count=1, flags=re.DOTALL)
    opening = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]
    paragraphs = [p.strip() for p in opening.split("\n\n") if p.strip()]
    naked = [
        p[:30] for p in paragraphs
        if len(re.sub(r"[^一-鿿]", "", p)) >= 40
        and "**" not in p and "<mark" not in p
        and not p.startswith(("#", "!", "<", "|", ">"))
    ]
    add("fail" if naked else "ok", "开篇重点标识",
        f"{len(naked)} 个实质段零标识 → {naked[:2]}" if naked
        else "开篇区实质段均有词组级标识")

    # --- 6. 文末模块 ---
    try:
        import yaml as _y
        meta = _y.safe_load((cwd / "article-meta.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        meta = {}
    endmatter = (meta or {}).get("endmatter") or {}
    if endmatter.get("deep_read"):
        has = "SANSHENG-DEEP-READ" in text
        add("ok" if has else "fail", "文末 DEEP READ",
            "已使用模板标记" if has
            else "endmatter.deep_read=true 但缺 SANSHENG-DEEP-READ 标记")
    sources_mode = endmatter.get("sources", "auto")
    if sources_mode is True or (
        sources_mode == "auto" and (cwd / "_fact-check.md").exists()
    ):
        has = "SANSHENG-SOURCES" in text
        add("ok" if has else "fail", "文末 SOURCES",
            "已使用模板标记" if has
            else "正文有外部依据但缺 SANSHENG-SOURCES 标记")

    # --- 7. 金句库来源标记（finalize 的前置，迟报五个阶段）---
    try:
        from profile_config import golden_lines_file
        gl = Path(golden_lines_file())
        if gl.exists():
            marker = f"*({cwd.name})*"
            has = marker in gl.read_text(encoding="utf-8")
            add("ok" if has else "fail", "金句库来源标记",
                f"已登记 {marker}" if has
                else f"缺 {marker} —— finalize 会拦，现在补最省事")
    except Exception as exc:
        add("warn", "金句库来源标记", f"检查异常：{exc}")

    # --- 8. 视觉任务单（若已写）---
    plan_path = cwd / "visual-plan.json"
    if plan_path.exists():
        try:
            from visual_workflow import validate_visual_plan
            errs = validate_visual_plan(json.loads(plan_path.read_text(encoding="utf-8")))
            add("ok" if not errs else "fail", "visual-plan.json",
                "通过" if not errs else f"{len(errs)} 条问题，首条：{errs[0][:110]}")
        except Exception as exc:
            add("warn", "visual-plan.json", f"检查异常：{exc}")

    # --- 9. 裸 URL 前移（2026-08-16 第 90 篇实跑：这条本来只在 format_layout 报，
    #        每报一次就要重转一次 HTML 再重排，实测吃掉一整轮 ≈ 8 分钟）---
    if text:
        # Markdown 版等价检查：正文里的完整 URL 必须在 link-card / deep-read 块内。
        stripped = re.sub(r"<section[^>]*>.*?</section>", "", text, flags=re.S)
        stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.S)
        stripped = re.sub(r"\[[^\]]*\]\([^)]*\)", "", stripped)      # MD 链接语法不算裸露
        stripped = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", stripped)
        bare = re.findall(
            r"(?<![\w./@-])(?:https?://)?[\w-]+(?:\.[\w-]+)*"
            r"\.(?:com|cn|net|org|top|io|dev|app|ai|co|xyz|me)/[^\s<>\"'()（）【】，。、；]+",
            stripped,
        )
        add("ok" if not bare else "fail", "裸 URL（前移自排版门）",
            "无裸露 URL" if not bare
            else f"{len(bare)} 处未走 link-card/deep-read：{bare[0][:60]} —— "
                 f"排版门也会拦，现在改省一轮重排")

    # --- 10. DEEP READ 入口兑现（同上，前移自 format_layout 的发布前素材门）---
    if text and "SANSHENG-DEEP-READ" in text:
        try:
            from profile_config import identity
            site = str((identity() or {}).get("site") or "").strip()
        except Exception:
            site = ""
        if site:
            # 取 DEEP READ 标记之后、下一个机器块标记（SOURCES 等）之前的整段。
            # 🔴 别用 `.*?</section>` 非贪婪切：DEEP READ 卡内部有多层嵌套 section，
            #    第一个 </section> 出现在站点入口之前，会把入口切掉 → 正例被误判 fail
            #    （本检查的首版就这么挂了一条测试）。
            start = text.find("<!-- SANSHENG-DEEP-READ -->")
            rest = text[start:]
            nxt = re.search(r"<!-- SANSHENG-(?!DEEP-READ)", rest)
            block = rest[: nxt.start()] if nxt else rest
            has = site.replace("https://", "").replace("http://", "").rstrip("/") in block
            add("ok" if has else "fail", "DEEP READ 入口",
                "已含自有阵地入口" if has
                else f"缺 profile 声明的入口 {site} —— 排版门会拦，现在补省一轮重排")

    # --- 11. 信息图锚点段落边界（前移自 assemble-release：锚点若在段落中间，
    #        装配会把整段劈成两半，判定为「改变作者正文」而拒绝写入）---
    if text and plan_path.exists():
        try:
            from assemble_release import safe_anchor_insertion_index

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            bad = []
            for item in plan.get("infographics") or []:
                anchor = str(item.get("anchor") or "")
                if not anchor:
                    continue
                hits = [m for m in re.finditer(re.escape(anchor), text)]
                if len(hits) != 1:
                    bad.append(f"{item.get('id')}:命中{len(hits)}次")
                    continue
                if safe_anchor_insertion_index(text, hits[0]) is None:
                    bad.append(f"{item.get('id')}:锚点在段落中间")
            add("ok" if not bad else "fail", "信息图锚点",
                "全部唯一且落在安全段末" if not bad
                else f"{'、'.join(bad)} —— assemble-release 会拒绝装配（改变作者正文）")
        except Exception as exc:
            add("warn", "信息图锚点", f"检查异常：{exc}")

    return results


def cmd_preflight(cwd: Path) -> None:
    """把所有静态检查跑一遍，尽早暴露问题。"""
    results = _preflight_checks(cwd)
    fails = [r for r in results if r[0] == "fail"]
    warns = [r for r in results if r[0] == "warn"]

    icon = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}
    print(f"\n🔎 静态预检：{cwd.name}\n" + "─" * 58)
    for level, name, detail in results:
        print(f"  {icon[level]} {name}")
        if level != "ok" and detail:
            print(f"      {detail}")
    print("─" * 58)

    if fails:
        print(f"❌ {len(fails)} 项需要修复，{len(warns)} 项提示")
        print("   这些都是纯静态问题，现在改比等排版/发布阶段被打回省得多。")
        raise SystemExit(2)
    print(f"✅ 静态检查全过（{len(warns)} 项提示）")


def cmd_adopt_final(cwd: Path, final_path: str, meta_path: str) -> None:
    """把作者确认的现成定稿接入 release-only 状态机。"""
    from release_job import adopt_final

    job, errors = adopt_final(cwd, Path(final_path), Path(meta_path))
    if errors:
        print("❌ 作者定稿接管失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(
        "✅ 已接管作者定稿并生成 _release-job.json："
        f"job_id={job['job_id']}，scope={job['scope']}"
    )


def cmd_verify_release_job(cwd: Path) -> None:
    from release_job import validate_release_job

    job, errors = validate_release_job(cwd)
    if errors:
        print("❌ release job 未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(
        "✅ release job 有效："
        f"job_id={job['job_id']}，final={job['final_sha256'][:12]}"
    )


def cmd_release_check(cwd: Path) -> None:
    """Single final binding + publish-preflight command after machine assembly."""
    from release_job import rebind_release_job, validate_release_job

    job, rebound, errors = rebind_release_job(cwd)
    if errors or job is None:
        print("❌ release check 未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    _, validation_errors = validate_release_job(cwd)
    preflight_errors = _pre_publish_errors(cwd)
    all_errors = validation_errors + preflight_errors
    if all_errors:
        print("❌ release check 未通过：")
        for error in all_errors:
            print(f"   • {error}")
        raise SystemExit(2)
    action = "已重绑定机器装配后的定稿字节" if rebound else "定稿绑定无需更新"
    print(f"✅ release check 通过：{action}，可执行 release-to-draft")


def cmd_compile_visuals(cwd: Path) -> None:
    from visual_workflow import compile_visual_plan

    result, errors = compile_visual_plan(cwd)
    if errors:
        print("❌ visual plan 编译失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(
        f"✅ 已由 {result['producer']} 编译 {result['prompt_count']} 份 canonical prompt"
    )


def cmd_assemble_release(cwd: Path) -> None:
    from assemble_release import assemble_release_markdown

    result, errors = assemble_release_markdown(cwd)
    if errors:
        print("❌ 发布 Markdown 装配失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    action = "已更新" if result["changed"] else "无需更新"
    print(f"✅ {action}定稿.md：嵌入 {result['image_count']} 张信息图")


def cmd_render_visuals(cwd: Path, only: str = "", candidates: int = 1) -> None:
    from render_visuals import render_visuals

    selected = {part.strip() for part in only.split(",") if part.strip()} or None
    receipt, errors = render_visuals(cwd, only=selected, candidate_count=candidates)
    if errors:
        print("❌ 图片渲染失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    scope = f"，本轮重渲 {sorted(selected)}，其余沿用" if selected else ""
    candidate_note = (
        f"；已生成 {candidates} 组候选，需运行 select-visuals 后才能进入视觉 QA"
        if candidates > 1 else ""
    )
    print(
        f"✅ 已渲染 {len(receipt['assets'])} 张图{scope}；"
        f"renderer={receipt['renderer']} revision={str(receipt.get('renderer_revision') or '')[:12]}{candidate_note}"
    )


def cmd_select_visuals(cwd: Path, specs: list[str]) -> None:
    from render_visuals import select_visual_candidates

    selections: dict[str, int] = {}
    for spec in specs:
        if "=" not in spec:
            print(f"❌ 候选选择格式必须为 task_id=序号，收到：{spec}")
            raise SystemExit(2)
        task_id, raw = spec.split("=", 1)
        try:
            selections[task_id.strip()] = int(raw)
        except ValueError:
            print(f"❌ 候选序号必须为整数：{spec}")
            raise SystemExit(2)
    receipt, errors = select_visual_candidates(cwd, selections)
    if errors or receipt is None:
        print("❌ 候选图选择失败：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(f"✅ 已选中 {len(receipt['assets'])} 张生成式候选图；现在可运行 visual-qa")


def cmd_visual_qa(cwd: Path) -> None:
    from visual_qa import run_visual_qa

    qa, errors = run_visual_qa(cwd)
    _log_qa_verdict(cwd, qa, errors)
    if errors:
        print("❌ 视觉 QA 未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    print(f"✅ 独立视觉 QA 通过：{len(qa['assets'])} 张最终图片")


def summarize_render_attempts(rows: list) -> dict:
    """把尝试日志汇总成「每张渲了几次 / 浪费了多少」。

    必要量 = 图数（每张至少渲一次）。浪费 = 实际渲染数 − 必要量。
    第 89 篇的真实数字是 45 次调用、6 张图 —— 浪费 39 次，占 87%。
    那次是靠事后手工数出来的；有了这个函数就不用再数。
    """
    renders = [r for r in rows if r.get("kind") == "render"]
    qa_rows = [r for r in rows if r.get("kind") == "qa_verdict"]
    per_label: dict[str, dict] = {}
    for r in renders:
        label = str(r.get("label") or "?")
        slot = per_label.setdefault(
            label, {"renders": 0, "ok": 0, "failed": 0, "qa_fail": 0,
                    "models": set(), "distinct_outputs": set()})
        slot["renders"] += 1
        if r.get("outcome") == "ok":
            slot["ok"] += 1
            if r.get("output_sha256"):
                slot["distinct_outputs"].add(r["output_sha256"])
        else:
            slot["failed"] += 1
        if r.get("model"):
            slot["models"].add(r["model"])
    for r in qa_rows:
        label = str(r.get("label") or "?")
        if label in per_label and r.get("outcome") == "fail":
            per_label[label]["qa_fail"] += 1
    total = len(renders)
    needed = len(per_label)
    return {
        "total_renders": total,
        "assets": needed,
        "necessary": needed,
        "wasted": max(0, total - needed),
        "waste_ratio": (total - needed) / total if total else 0.0,
        "per_label": {
            k: {**v, "models": sorted(v["models"]),
                "distinct_outputs": len(v["distinct_outputs"])}
            for k, v in sorted(per_label.items())
        },
    }


def cmd_render_stats(cwd: Path) -> None:
    """打印本篇的生图重渲统计。数据源是 素材/.render-attempts.jsonl（累积）。"""
    from render_visuals import ATTEMPT_LOG, read_attempts

    rows = read_attempts(cwd)
    if not rows:
        print(f"暂无渲染尝试记录（{ATTEMPT_LOG} 还没有内容）")
        print("  它从 2026-08-16 起才开始记录；更早的文章查不到历史。")
        return
    s = summarize_render_attempts(rows)
    print("=== 生图重渲统计 ===")
    print(f"  实际渲染 {s['total_renders']} 次 ｜ 图 {s['assets']} 张 ｜ "
          f"必要量 {s['necessary']} 次 ｜ 浪费 {s['wasted']} 次"
          f"（{s['waste_ratio'] * 100:.0f}%）")
    print()
    print(f"  {'图':22} {'渲染':>4} {'成功':>4} {'失败':>4} {'QA打回':>6} {'不同产物':>8}")
    print("  " + "-" * 56)
    for label, v in s["per_label"].items():
        print(f"  {label[:20]:22} {v['renders']:4} {v['ok']:4} {v['failed']:4} "
              f"{v['qa_fail']:6} {v['distinct_outputs']:8}")
    worst = max(s["per_label"].items(), key=lambda kv: kv[1]["renders"],
                default=None)
    if worst and worst[1]["renders"] > 1:
        print()
        print(f"  最费的一张：{worst[0]}（{worst[1]['renders']} 次）")
        print("  排查顺序按实测收益：frontmatter 是否泄漏 → SCENE 有没有具体物象 → "
              "文字之间是否共享 ≥2 字 → layout 有没有自带文字的物件")


def _log_qa_verdict(cwd: Path, qa, errors: list) -> None:
    """把 QA 判定追加进渲染尝试日志。

    🔴 这是「重渲」信号里最关键的一半：图渲成功了、但被判不合格，于是又渲一次。
    `_visual-qa.json` 只保存最终通过的那一版，失败的判定连同原因一起消失 ——
    结果就是没人知道某张图被打回过几次、为什么被打回。

    渲染侧的 log_attempt 记的是「渲了几次」，这里记的是「为什么还要再渲」。
    两者拼起来才能回答「45 次里哪些是必要的」。
    """
    try:
        from render_visuals import log_attempt, next_seq, read_attempts
    except ImportError:                                       # pragma: no cover
        return
    try:
        history = read_attempts(cwd)
        assets = (qa or {}).get("assets") or []
        # 逐张记：哪张图的哪几项检查没过
        for asset in assets:
            label = Path(str(asset.get("path") or "")).stem or "?"
            checks = asset.get("checks") or {}
            failed = sorted(
                name for name, value in (checks.items()
                                         if isinstance(checks, dict) else [])
                if (value.get("pass") if isinstance(value, dict) else value) is False
            )
            log_attempt(cwd, {
                "kind": "qa_verdict",
                "ts": _now_iso(),
                "label": label,
                "seq": next_seq(history, label),
                "outcome": "fail" if failed else "ok",
                "failed_checks": failed,
                "reviewer": str(((qa or {}).get("reviewer") or {}).get("model") or ""),
            })
        # 结构性错误（缺记录、字节不符…）不挂在某一张上，单独记一条
        if errors and not assets:
            log_attempt(cwd, {
                "kind": "qa_verdict", "ts": _now_iso(), "label": "(batch)",
                "seq": 0, "outcome": "fail",
                "errors": [str(e)[:200] for e in errors[:10]],
            })
    except Exception:                                         # noqa: BLE001
        # 观测失败绝不改变 QA 的判定结果
        pass


def cmd_release_to_draft(cwd: Path) -> None:
    """唯一草稿箱提交入口：全部本地硬门 + draft/add + draft/get。"""
    from release_job import validate_release_job
    from release_to_draft import release_to_draft, write_audio_handoff

    def preflight(root: Path):
        _, job_errors = validate_release_job(root)
        errors = list(job_errors)
        errors.extend(_pre_publish_errors(root))
        if errors:
            return None, errors
        return write_publish_ready(root)

    receipt, errors = release_to_draft(cwd, preflight=preflight)
    if errors or receipt is None:
        state = load_state(cwd)
        info = state["stages"].setdefault("publish", {})
        if info.get("status") != "done":
            info["status"] = "failed"
        info["last_failed_at"] = _now_iso()
        info["fail_count"] = int(info.get("fail_count") or 0) + 1
        save_state(cwd, state)
        print("❌ release-to-draft 被合同门阻断：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)

    handoff, handoff_errors = write_audio_handoff(cwd, receipt["draft_media_id"])
    if handoff_errors or handoff is None:
        print("❌ 草稿已创建，但双音频人工接管清单生成失败：")
        for error in handoff_errors:
            print(f"   • {error}")
        print("   远端草稿 ID 已保存在 _release-attempt.json；修复后重跑会复用，不会重复创建。")
        raise SystemExit(2)

    state = load_state(cwd)
    candidate = copy.deepcopy(state)
    publish = candidate["stages"].setdefault("publish", {})
    publish.update(
        {
            "draft_media_id": receipt["draft_media_id"],
            "remote_verified": True,
            "formal_publish": False,
            "release_scope": "wechat-draft",
        }
    )
    passed, verify_errors = verify_stage("publish", cwd, candidate)
    if not passed:
        print("❌ 草稿读回凭证未能通过最终状态校验：")
        for error in verify_errors:
            print(f"   • {error}")
        raise SystemExit(2)
    _record_stage_success(cwd, candidate, "publish")
    save_state(cwd, candidate)
    resumed = "（复用既有远端草稿，未重复创建）" if receipt.get("resumed_attempt") else ""
    print(
        f"✅ 微信草稿箱已推送并由 draft/get 读回确认："
        f"{receipt['draft_media_id']}{resumed}"
    )
    if handoff.get("roles"):
        print("⏸ 草稿仍需人工插入音频：")
        for role in handoff["roles"]:
            print(f"   • {role['label']} ← {role['source']}")
        print("   保存后在微信预览分别试听两条音频的开头/结尾 10 秒，再运行：")
        print("   pipeline.py wechat-audio-check --confirm-audition")


def cmd_wechat_audio_check(cwd: Path, *, confirm_audition: bool = False) -> None:
    """人工插入音频后的官方读回门；没有凭证就不得进入 finalize。"""
    from release_to_draft import verify_wechat_audio

    receipt, errors = verify_wechat_audio(
        cwd,
        audition_confirmed=confirm_audition,
    )
    if errors or receipt is None:
        _log_audio_event(
            cwd, "wechat_audio_readback", "fail",
            f"errors={len(errors)}", error_count=len(errors),
        )
        print("❌ 微信双音频读回未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    _log_audio_event(
        cwd, "wechat_audio_readback", "ok",
        f"audio_count={receipt['audio_count']}",
    )
    print(
        f"✅ 微信双音频读回通过：{receipt['audio_count']} 个原生音频组件，"
        "占位文字已清除；现在可正式发布。"
    )


def cmd_wechat_published_audio_check(
    cwd: Path,
    wechat_url: str,
    *,
    confirm_audition: bool = False,
) -> None:
    """草稿已回收时，从官方已发表内容接口生成独立补验凭证。"""
    from release_to_draft import verify_wechat_published_audio

    receipt, errors = verify_wechat_published_audio(
        cwd,
        wechat_url,
        audition_confirmed=confirm_audition,
    )
    if errors or receipt is None:
        _log_audio_event(
            cwd, "wechat_published_audio_readback", "fail",
            f"errors={len(errors)}", error_count=len(errors),
        )
        print("❌ 微信正式文章双音频补验未通过：")
        for error in errors:
            print(f"   • {error}")
        raise SystemExit(2)
    _log_audio_event(
        cwd, "wechat_published_audio_readback", "ok",
        f"article_id={receipt['published_article_id']}",
    )
    print(
        f"✅ 微信正式文章双音频补验通过：{receipt['audio_count']} 个原生音频组件，"
        "已用独立的正式文章凭证绑定永久链接、播放器身份与人工首尾试听。"
    )


# 🔴 铁律 stage：不允许 skip（iron-rules.md 强约束）
# 曾踩坑：infographic 被 skip 后整篇文章漏了整组贯穿全文信息图
NEVER_SKIP_STAGES = {
    "writing",       # 没正文还发什么
    "cover",         # 没封面无法推草稿
    "infographic",   # iron-rules.md 强制：≥4 张贯穿全文信息图（开篇/结尾 9:16 各 1 + 中间 16:9 ≥2）
    "bgm",           # 新文章发布硬门；缺密钥/生成失败必须修复，不能 skip
    "layout",        # 没排版的 md 不可发布
    "publish",       # 没推草稿就没发布
}


def cmd_skip(stage: str, cwd: Path, force: bool = False):
    if force:
        print("🔴 拒绝 --force：skip 不提供绕过模式")
        raise SystemExit(2)
    if stage in NEVER_SKIP_STAGES:
        print(f"🔴 拒绝 skip：`{stage}` 是铁律 stage（详见 references/iron-rules.md）")
        print(f"   - cover/layout/publish 是发布前置硬性产物，不可绕过")
        print(f"   - infographic 是文末知识图（≥4 张：开篇 9:16 + 中间 16:9 ×N + 结尾 9:16），缺了会被 publish verify 拦截")
        print(f"   - writing 是正文，不可能 skip")
        sys.exit(2)
    state = load_state(cwd)
    state["stages"][stage]["status"] = "skip"
    save_state(cwd, state)
    print(f"⏭  {stage} 已跳过")
    if stage not in NEVER_SKIP_STAGES:
        print(f"   {stage} 为可选阶段；若因生成失败而 skip，请按 autopilot.md 失败恢复 SOP 先重试，勿用 skip 绕过失败。")


def cmd_reset(stage: str, cwd: Path):
    state = load_state(cwd)
    state["stages"][stage] = {"status": "pending"}
    _invalidate_downstream(state, stage, f"上游 {stage} 被 reset")
    save_state(cwd, state)
    print(f"🔄 {stage} 已重置为 pending")


def cmd_orchestrator(mode: str, cwd: Path):
    """全局编排开关。仅改 orchestrator / state_writer 两键并回写，
    不触碰任何既有阶段语义或既有字段。

    P1 已落地（2026-05-22）：本命令只切 state 字段。orchestrator=on 后，真正的
    fan-out 并行由当前宿主控制器按 orchestration.md 执行。pipeline.py 自身
    始终只做状态记账 + verify，不启动任何模型任务。"""
    state = load_state(cwd)
    state["orchestrator"] = mode
    state["state_writer"] = "orchestrator"
    save_state(cwd, state)
    print(f"🎛  orchestrator 已设为 {mode}")
    if mode == "on":
        print("🛠 当前宿主控制器可按 orchestration.md 并行独立工作单元；")
        print("   定稿后的发布机械链仍必须单写者串行执行")


# ── 入口 ──────────────────────────────────────────────────────
def cmd_retitle(new_title: str, cwd: Path):
    """改标题连锁同步（2026-07-21 实战固化）：一次改齐
    article-meta.yaml / 定稿.md(frontmatter+H1) / 大纲.md(H1) / .state.json，
    并打印后续必做动作（重排版、重推草稿、删旧草稿）。"""
    changed = []
    meta = cwd / "article-meta.yaml"
    if meta.exists():
        txt, n = re.subn(r'(?m)^title: ".*"$', f'title: "{new_title}"',
                         meta.read_text(encoding="utf-8"), count=1)
        if n:
            meta.write_text(txt, encoding="utf-8")
            changed.append("article-meta.yaml")
    draft = cwd / "定稿.md"
    if draft.exists():
        txt = draft.read_text(encoding="utf-8")
        txt, n1 = re.subn(r'(?m)^title: ".*"$', f'title: "{new_title}"', txt, count=1)
        txt, n2 = re.subn(r'(?m)^# .+$', f'# {new_title}', txt, count=1)
        if n1 or n2:
            draft.write_text(txt, encoding="utf-8")
            changed.append("定稿.md(frontmatter+H1)")
    outline = cwd / "大纲.md"
    if outline.exists():
        txt, n = re.subn(r'(?m)^# .+$', f'# {new_title}',
                         outline.read_text(encoding="utf-8"), count=1)
        if n:
            outline.write_text(txt, encoding="utf-8")
            changed.append("大纲.md(H1)")
    state = load_state(cwd)
    state["stages"].setdefault("writing", {})["title_final"] = new_title
    outline_info = state["stages"].setdefault("outline", {"status": "pending"})
    if outline_info.get("status") == "done":
        outline_info["status"] = "dirty"
        outline_info["dirty"] = True
        outline_info["dirty_reason"] = "标题变更，blueprint 审批对象已变化"
    writing_info = state["stages"].setdefault("writing", {"status": "pending"})
    if writing_info.get("status") == "done":
        writing_info["status"] = "dirty"
        writing_info["dirty"] = True
        writing_info["dirty_reason"] = "标题变更，draft 审批对象已变化"
    _invalidate_downstream(state, "outline", "标题变更，所有下游需重验")
    save_state(cwd, state)
    changed.append(".state.json(title_final)")
    print(f"✅ 标题已改为「{new_title}」，已同步：{'、'.join(changed)}")
    print("⚠️ 后续必做（retitle 不代劳）：")
    print("   ① 自查 lead 导读栏（line1/line2）与 digest 要不要跟着改")
    print("   ② 重跑排版链：normalize → baoyu-markdown-to-html → format_layout.py 定稿.html --all --check")
    print("   ③ 重推草稿箱（会新增草稿而非覆盖，推完去后台删旧草稿）")
    print("   ④ 若已 archive，作品库标题需手动核对")


def main():
    parser = argparse.ArgumentParser(
        description="微信公众号写作流水线管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dir",
        default="",
        metavar="ARTICLE_DIR",
        help="显式指定文章目录；适合 Windows/自动化调用，避免因当前目录错误读不到 state",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init",   help="初始化 .state.json")
    sub.add_parser("status", help="查看当前进度 + 下一步建议")
    sub.add_parser("next",   help="打印下一阶段操作说明")
    sub.add_parser(
        "preflight",
        help="一次跑完所有静态检查（不依赖生图/排版/网络），把晚发现前移。"
             "写完正文就该跑一次，别等排版或 finalize 才被打回",
    )

    p_v = sub.add_parser("verify", help="验证阶段完成情况（通过则自动标 done）")
    p_v.add_argument("stage", choices=STAGE_ORDER)
    p_v.add_argument("--pre", action="store_true",
                     help="publish 专用：推送前素材齐备门（cover/hero/≥4 信息图/定稿.html），只判定不标 done")

    p_d = sub.add_parser(
        "done",
        help="标记阶段完成，附加元数据用 k=v 位置参数（不是 --key 选项）。"
             "例：done writing \"title_final=精选 | 标题\"",
    )
    p_d.add_argument("stage", choices=STAGE_ORDER)
    p_d.add_argument("extras", nargs="*", metavar="k=v",
                     help="例：title_final=文章标题  wechat_url=https://...")

    p_log = sub.add_parser("log", help="追加一条生图记录到 .gen-log.jsonl")
    # 2026-04-23 扩展：hero / bgm_cover 是独立的组件小图，也要能记录；
    # component 作为"其它未归类组件图"的兜底 stage，避免未来新组件又要回头改白名单
    p_log.add_argument("stage", choices=[
        "cover", "infographic", "illustrator", "chart",
        "hero", "bgm_cover", "component",
    ])
    p_log.add_argument("tool", help=f"语义 producer 名；新视觉产物固定为 {VISUAL_PRODUCER}")
    p_log.add_argument("--output", help="生成的文件相对路径")
    p_log.add_argument("--prompt", help="最终使用的 canonical prompt 相对路径")
    p_log.add_argument("--renderer", help="像素渲染后端；最终文章视觉只允许 baoyu-image-gen")
    p_log.add_argument("--model", help="实际渲染模型/版本")
    p_log.add_argument("--style", help="可选；默认从 canonical prompt frontmatter 读取")
    p_log.add_argument(
        "--host-agent",
        default="",
        help="可选；记录本次宿主 Agent（也可用 SANSHENG_HOST_AGENT 环境变量）",
    )
    p_log.add_argument(
        "--extend-sha256",
        default="",
        help="可选；记录实际生效的 baoyu EXTEND.md 摘要",
    )
    p_log.add_argument(
        "--provenance-mode", default="rendered",
        choices=["rendered", "adopted-postprocessed"],
        help="rendered=加 logo 前登记；adopted-postprocessed=仅迁移既有最终图",
    )
    p_log.add_argument("--cmd", dest="cmd_line", help="实际执行的命令行（可选）")

    sub.add_parser(
        "visual-contract",
        help="打印当前文章信息图与 Hero 应绑定的视觉配方 frontmatter",
    )

    p_ap = sub.add_parser("approve", help="把作者确认绑定到当前 blueprint/draft 字节摘要")
    p_ap.add_argument("gate", choices=["blueprint", "draft"])
    p_ap.add_argument(
        "--source-mode", required=True,
        choices=["new-draft", "author-provided-final", "checkpoint-waived"],
        help="本次确认来源，避免把作者提供的定稿误记成新稿审批",
    )
    p_ap.add_argument("--note", default="", help="可选备注")

    p_seal = sub.add_parser("seal", help="封存最终产物字节证据")
    p_seal.add_argument("kind", choices=["visual"])

    # history 子命令保留注册（避免破坏可能的调用方），但已废弃，改用 archive
    p_h = sub.add_parser("history", help="[DEPRECATED] 改用 archive（仅打印废弃提示）")
    p_h.add_argument("extras", nargs="*", metavar="k=v",
                     help="覆盖字段，如 title='文章标题' closing_type='硬切'")

    p_a = sub.add_parser("archive", help="发布归档：写解析后的作品库 + 刷新派生视图")
    p_a.add_argument("extras", nargs="*", metavar="k=v",
                     help="覆盖字段，如 category=AIT digest='一句话摘要' date=2026-05-30")

    p_f = sub.add_parser("finalize", help="正式发布收尾：登记永久链接 + 归档 + 验证")
    p_f.add_argument("wechat_url", help="微信永久链接，如 https://mp.weixin.qq.com/s/xxx")

    sub.add_parser(
        "moments-copy",
        help="只生成朋友圈文案；不查网、不归档、不部署、不调用 finalize",
    )

    p_adopt = sub.add_parser(
        "adopt-final",
        help="把作者确认的现成定稿绑定为 release job，不重跑写作前半程",
    )
    p_adopt.add_argument("--final", default="定稿.md", help="文章目录内的定稿文件")
    p_adopt.add_argument(
        "--meta", default="article-meta.yaml", help="文章目录内的元数据文件"
    )
    sub.add_parser(
        "verify-release-job",
        help="校验 _release-job.json 与当前定稿/meta/state 是否仍一致",
    )
    sub.add_parser(
        "release-check",
        help="机器装配后重绑定定稿字节并一次完成发布前硬门",
    )
    sub.add_parser(
        "compile-visuals",
        help="把受限 visual-plan.json 编译为 canonical prompts 与 render batch",
    )
    sub.add_parser(
        "assemble-release",
        help="按 visual-plan 位置幂等装配信息图引用，不改变作者正文",
    )
    p_rv = sub.add_parser(
        "render-visuals",
        help="探测并调用已配置 renderer 渲染视觉资产，失败时只按配置降级",
    )
    p_rv.add_argument(
        "--only",
        default="",
        metavar="ID[,ID...]",
        help="只重渲点名的资产（如 --only infographic-02 或 --only cover,hero），"
             "其余沿用磁盘已有产物与其历史生成记录。用于生成式渲染逐张掷骰子时"
             "补渲个别不满意的图，避免整批重跑把已满意的一起掷掉。",
    )
    p_rv.add_argument(
        "--candidates",
        type=int,
        default=1,
        metavar="N",
        help="每张图生成 2-4 个候选；必须随后 select-visuals 显式选中，默认 1",
    )
    p_sv = sub.add_parser(
        "select-visuals",
        help="把显式选中的生成式候选提升为最终图；格式 cover=1 hero=2 infographic-01=1",
    )
    p_sv.add_argument("selections", nargs="+", metavar="TASK=候选序号")
    sub.add_parser(
        "visual-qa",
        help="调用独立看图进程，生成结构化 _visual-qa.json",
    )
    sub.add_parser(
        "render-stats",
        help="本篇生图重渲统计（每张渲了几次、浪费多少、谁最费）",
    )
    sub.add_parser(
        "release-to-draft",
        help="唯一草稿发布入口：预检 → draft/add → draft/get → 远端凭证",
    )
    p_handoff = sub.add_parser(
        "handoff-assets",
        help="从正式回执导出封面、主题曲及可选播客的可验证手工上传包",
    )
    p_handoff.add_argument(
        "--target-root",
        default="",
        help="覆盖 SANSHENG_WRITE_HANDOFF_DIR / .env 中的浅层交接根目录",
    )
    p_handoff.add_argument(
        "--revision",
        default="",
        help="目标已有不同快照时使用新的 revision 标识，如 r2",
    )
    p_wechat_audio = sub.add_parser(
        "wechat-audio-check",
        help="人工插入主题曲/播客音频后，用官方 draft/get 复核再允许正式发布",
    )
    p_wechat_audio.add_argument(
        "--confirm-audition",
        action="store_true",
        help="确认已在微信预览分别试听两条音频的开头 10 秒和结尾 10 秒",
    )
    p_wechat_published_audio = sub.add_parser(
        "wechat-published-audio-check",
        help="草稿已发布回收后，用官方已发表内容接口补验双音频",
    )
    p_wechat_published_audio.add_argument(
        "wechat_url",
        help="已正式发布的公众号永久链接",
    )
    p_wechat_published_audio.add_argument(
        "--confirm-audition",
        action="store_true",
        help="确认已在正式文章分别试听两条音频的开头 10 秒和结尾 10 秒",
    )

    p_s = sub.add_parser("skip",  help="跳过某阶段")
    p_s.add_argument("stage", choices=STAGE_ORDER)

    p_r = sub.add_parser("reset", help="重置阶段为 pending")
    p_r.add_argument("stage", choices=STAGE_ORDER)

    p_o = sub.add_parser("orchestrator", help="全局编排开关（on=启用编排器 / off=回滚到手动）")
    p_o.add_argument("mode", choices=["on", "off"])

    p_rt = sub.add_parser("retitle", help="改标题并连锁同步 meta/定稿/大纲/state（附后续动作提醒）")
    p_rt.add_argument("title", help="新标题")

    # 一稿多投分发层（finalize 之后的第二段链路，见 references/distribute.md）
    # 子命令与参数由 distribute.py 自己解析，这里只做转发，避免两处重复定义。
    p_dist = sub.add_parser(
        "distribute",
        help="一稿多投：小红书 / 微博 / 播客（子命令 status|plan|verify|dispatch）",
    )
    p_dist.add_argument("rest", nargs=argparse.REMAINDER,
                        help="转发给 distribute.py 的参数")
    sub.add_parser(
        "podcast-pregen",
        help="定稿冻结点后台预生成播客音频；finalize 到点直接取件（省 ~18 分钟阻塞）",
    )

    # 同时接受 `--dir X finalize ...` 与 `finalize ... --dir X`，降低 Windows
    # 终端/自动化调用时“站错目录却读到缺 state”的概率。
    for command_parser in sub.choices.values():
        command_parser.add_argument(
            "--dir",
            dest="command_dir",
            default="",
            metavar="ARTICLE_DIR",
            help=argparse.SUPPRESS,
        )

    args = parser.parse_args()
    selected_dir = getattr(args, "command_dir", "") or args.dir
    cwd = Path(selected_dir).expanduser().resolve() if selected_dir else Path.cwd()
    if not cwd.is_dir():
        parser.error(f"文章目录不存在：{cwd}")
    # 路径配置可能使用 @workspace/...。必须等文章目录确定后再绑定，
    # 且要早于 distribute 等延迟 import，避免同一进程把数据静默写回 main。
    import profile_config as _profile_config
    try:
        _profile_config.bind_workspace(cwd)
    except _profile_config.WorkspaceBindingError as exc:
        parser.error(str(exc))

    if args.cmd == "distribute":
        import distribute
        os.chdir(cwd)
        sys.exit(distribute.main(args.rest or ["status"]))
    elif args.cmd == "podcast-pregen":
        cmd_podcast_pregen(cwd)
    elif args.cmd == "wechat-audio-check":
        cmd_wechat_audio_check(
            cwd,
            confirm_audition=getattr(args, "confirm_audition", False),
        )
    elif args.cmd == "wechat-published-audio-check":
        cmd_wechat_published_audio_check(
            cwd,
            args.wechat_url,
            confirm_audition=getattr(args, "confirm_audition", False),
        )
    elif args.cmd == "init":
        cmd_init(cwd)
    elif args.cmd == "status":
        cmd_status(cwd)
    elif args.cmd == "next":
        cmd_next(cwd)
    elif args.cmd == "preflight":
        cmd_preflight(cwd)
    elif args.cmd == "verify":
        cmd_verify(args.stage, cwd, legacy=getattr(args, "legacy", False),
                   pre=getattr(args, "pre", False))
    elif args.cmd == "retitle":
        cmd_retitle(args.title, cwd)
    elif args.cmd == "done":
        cmd_done(args.stage, cwd, getattr(args, "extras", []),
                 force=getattr(args, "force", False),
                 legacy=getattr(args, "legacy", False))
    elif args.cmd == "log":
        cmd_log(args.stage, args.tool, cwd,
                output=getattr(args, "output", "") or "",
                cmd=getattr(args, "cmd_line", "") or "",
                prompt=getattr(args, "prompt", "") or "",
                renderer=getattr(args, "renderer", "") or "",
                model=getattr(args, "model", "") or "",
                provenance_mode=getattr(args, "provenance_mode", "rendered"),
                style=getattr(args, "style", "") or "",
                host_agent=getattr(args, "host_agent", "") or "",
                extend_sha256=getattr(args, "extend_sha256", "") or "")
    elif args.cmd == "visual-contract":
        cmd_visual_contract(cwd)
    elif args.cmd == "approve":
        cmd_approve(args.gate, cwd, args.source_mode, args.note)
    elif args.cmd == "seal":
        cmd_seal(args.kind, cwd)
    elif args.cmd == "history":
        cmd_history(cwd, getattr(args, "extras", []))
    elif args.cmd == "archive":
        # 2026-07-01：archive abort（缺 seq/category/wechat_url）→ 非零退出码，
        # 让上游 `&&`/退出码判断能检测归档失败（cmd_archive 返回 False 即 abort）。
        if not cmd_archive(cwd, getattr(args, "extras", [])):
            sys.exit(1)
    elif args.cmd == "finalize":
        cmd_finalize(args.wechat_url, cwd)
    elif args.cmd == "moments-copy":
        cmd_moments_copy(cwd)
    elif args.cmd == "adopt-final":
        cmd_adopt_final(cwd, args.final, args.meta)
    elif args.cmd == "verify-release-job":
        cmd_verify_release_job(cwd)
    elif args.cmd == "release-check":
        cmd_release_check(cwd)
    elif args.cmd == "compile-visuals":
        cmd_compile_visuals(cwd)
    elif args.cmd == "assemble-release":
        cmd_assemble_release(cwd)
    elif args.cmd == "render-visuals":
        cmd_render_visuals(
            cwd,
            getattr(args, "only", "") or "",
            getattr(args, "candidates", 1),
        )
    elif args.cmd == "select-visuals":
        cmd_select_visuals(cwd, args.selections)
    elif args.cmd == "visual-qa":
        cmd_visual_qa(cwd)
    elif args.cmd == "render-stats":
        cmd_render_stats(cwd)
    elif args.cmd == "release-to-draft":
        cmd_release_to_draft(cwd)
    elif args.cmd == "handoff-assets":
        from handoff_assets import export_handoff_assets

        target, status, errors = export_handoff_assets(
            cwd,
            target_root=(
                Path(args.target_root).expanduser()
                if getattr(args, "target_root", "")
                else None
            ),
            revision=getattr(args, "revision", "") or "",
        )
        if errors or target is None:
            print("❌ 手工上传包导出失败：")
            for error in errors:
                print(f"   • {error}")
            sys.exit(2)
        print(f"✅ 手工上传包{('已创建' if status == 'created' else '未变化')}：{target}")
    elif args.cmd == "skip":
        cmd_skip(args.stage, cwd, force=getattr(args, "force", False))
    elif args.cmd == "reset":
        cmd_reset(args.stage, cwd)
    elif args.cmd == "orchestrator":
        cmd_orchestrator(args.mode, cwd)


if __name__ == "__main__":
    main()
