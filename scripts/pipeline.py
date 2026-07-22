#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — 微信公众号写作流水线管理器
==============================================
在文章工作目录（<数据目录>/{N}-{选题名}/）下运行，管理文章全流程进度。

流程顺序：
  outline → writing+title → cover → infographic → bgm → layout → logo → publish → archive
(2026-06-18: BGM 阶段复活, 引擎 Lyria→MiniMax; 见 references/music.md)
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
  python SKILL/scripts/pipeline.py archive                  发布归档：写 works.yaml + 刷新 articles.md/看板
  python SKILL/scripts/pipeline.py history                  [DEPRECATED] 改用 archive
  python SKILL/scripts/pipeline.py orchestrator on|off      切换编排器并行/串行（默认 on）

示例（$SKILL = 本 skill 根目录，$DATA = 数据目录）：
  cd "$DATA/18-安利读书软件"
  python "$SKILL/scripts/pipeline.py" init
  python "$SKILL/scripts/pipeline.py" status
  python "$SKILL/scripts/pipeline.py" verify layout
  python "$SKILL/scripts/pipeline.py" done publish wechat_url=https://mp.weixin.qq.com/s/xxx
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

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

# ── 常量 ──────────────────────────────────────────────────────
STATE_FILE = ".state.json"
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
# 2026-06-18: 'bgm' stage 复活 (引擎 Lyria→MiniMax music-2.6-free, 方法A 自动写词)

STAGE_LABELS = {
    "outline":     "选题 + 大纲",
    "writing":     "正文写作 + 标题锻造",
    "cover":       "封面图（baoyu-skills:baoyu-cover-image）",
    "infographic": "信息图 ≥ 4 张（baoyu-skills:baoyu-infographic / baoyu-diagram）",
    "bgm":         "主题音乐（generate_article_bgm.py · MiniMax 方法A）",
    "layout":      "微信排版（baoyu-skills:baoyu-markdown-to-html + format_layout.py）",
    "logo":        "品牌水印（add_logo.js）",
    "publish":     "发布草稿箱（baoyu-skills:baoyu-post-to-wechat）",
    "archive":     "发布后沉淀（pipeline.py archive 写 works.yaml + 自动刷新 articles.md/看板）",
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
        "🔴 实际执行走 gen_img.py（见 image-routing.md §54/§⑥），baoyu-cover-image 为概念名——\n"
        "  python $SKILL/scripts/gen_img.py prompts/cover.md 素材/cover.png gemini-3-pro-image-preview 1024 436\n"
        "  （--provider 默认 google；勿再走历史上的 baoyu quick 封面路径——早已 404 废弃）\n"
        "  输出 素材/cover.png。完成后：pipeline.py verify cover"
    ),
    "infographic": (
        "运行 /baoyu-skills:baoyu-infographic ≥ 4 张（开篇 9:16 + 中间 16:9×N + 结尾 9:16），\n"
        "  输出 素材/infographic-01-主题.png .. infographic-04-主题.png（命名铁律 infographic-NN-主题.png，"
        "见 image-routing.md §194；精确流程图走 baoyu-diagram）。\n"
        "  完成后：pipeline.py verify infographic"
    ),
    "bgm": (
        f'python "{_skill_path("scripts/generate_article_bgm.py")}" .\n'
        "  （MiniMax music-2.6-free 方法A：Claude 提炼诗意意象 → 自动写词 → 生成中文人声主题曲；V2 去 Gemini\n"
        "   舒缓空灵 4 风格 / 男女声奇偶交替 / 自动插 AUDIO-CARD 引导卡片。不需图片输入）\n"
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
        "  完成后：pipeline.py done logo"
    ),
    "publish": (
        "🔴 推送前先过素材门：pipeline.py verify publish --pre（cover + hero + ≥4 信息图 + 定稿.html，只判定不标 done）\n"
        "🔴 公众号草稿标题 = 「{对外分类中文名} | {正式标题}」，例：洞察 | Loop：硅谷最会用 AI 的人已经不写提示词了\n"
        "   （对外分类=article-meta.yaml 的 outward_category：tutorial→教程/news→资讯/picks→精选/insight→洞察/essay→随笔/industry→行业；\n"
        "    作品库 title 存干净标题不带前缀，前缀只挂公众号发布标题。post-to-wechat 支持 --title 就传带前缀标题，否则先改 定稿.html 的 <title> 再推）\n"
        "  /baoyu-skills:baoyu-post-to-wechat 定稿.html\n"
        "  微信后台手动发布，获得链接后：pipeline.py done publish wechat_url=https://mp.weixin.qq.com/s/xxx"
    ),
    "archive": (
        # 二期C：发布即写 works.yaml（单一数据源），自动分配 code + 刷新 articles.md/看板
        "先确认 article-meta.yaml 已填 category（AIT/TUT/OBS/ROB/KID/ESS）/ outward_category（对外6类，AIT/OBS 必填）/ tags / digest，然后：\n"
        f'  python "{_skill_path("scripts/pipeline.py")}" archive\n'
        "  （写入 <数据目录>/works.yaml + 自动刷新 articles.md 与 works-dashboard.html）\n"
        "  完成后：pipeline.py verify archive"
    ),
}

STATUS_ICON = {
    "pending": "⬜",
    "doing":   "🔄",
    "done":    "✅",
    "skip":    "⏭ ",
    "failed":  "❌",
}

# ── 生图路由白名单 ─────────────────────────────────────────────
# 在本 skill 流水线内，封面图/信息图/数据图三类必须走受控入口，
# 禁用通用 generate_image 工具（它只会输出 1:1 方图，AR 无法控制）。
#
# 🔴 2026-07-16 修正：加入 `gen_img`（scripts/gen_img.py）。
# 根因 = 文档与代码脱节：image-routing.md 路由表与 `pipeline.py status` 的提示早已把
# 封面/信息图的实际执行入口迁到 `gen_img.py`（"baoyu-cover-image 为概念名，旧 baoyu quick
# 封面路径早已 404 废弃"），但本白名单仍停在 baoyu-* 时代，导致按文档正确执行反而被
# 判"不在白名单"。旧 baoyu-* 名保留作历史文章向后兼容。
IMAGE_TOOL_WHITELIST = {
    "cover":       {"gen_img", "baoyu-cover-image"},
    "infographic": {"gen_img", "baoyu-infographic", "baoyu-diagram"},  # 3e 信息图 + 3g 精确图
    "illustrator": {"gen_img", "baoyu-article-illustrator", "baoyu-image-gen"},  # baoyu-skills v2.0 起 baoyu-imagine 改名回 baoyu-image-gen
    "chart":       {"matplotlib", "pyecharts", "plot_local"},  # 数据图必须本地脚本渲染
}
IMAGE_TOOL_BLACKLIST = {"generate_image", "internal_image_gen", "imagine"}

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


def _visual_route_errors(cwd: Path) -> list:
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

    subject = str(meta.get("infographic_subject") or "").strip()
    style = str(meta.get("infographic_style") or "").strip()
    expected = {"ai-product": "claymation", "phenomenon": "morandi-journal"}
    if subject not in expected:
        errors.append(
            "article-meta.yaml 缺合法 infographic_subject（ai-product / phenomenon）；"
            "产品/模型是否承担信息架构主轴必须显式落盘"
        )
    elif style != expected[subject]:
        errors.append(
            f"infographic_subject={subject} 必须使用 {expected[subject]}，当前为 {style or '(空)'}"
        )
    if style not in {"claymation", "morandi-journal"}:
        errors.append(
            f"infographic_style={style or '(空)'} 非法；新文章只允许 claymation / morandi-journal"
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
        cmd = str(rec.get("cmd") or "")
        m = re.search(r"--style\s+([^\s]+)", cmd)
        log_style = m.group(1).strip("\"'") if m else ""
        seen_styles.add(log_style)
        if style and log_style != style:
            errors.append(f"{rel} 最新 gen-log style={log_style or '(空)'}，应为 {style}")

        pm = re.search(r"(?:素材[/\\]prompts[/\\][^\s\"']+\.md)", cmd)
        if not pm:
            errors.append(f"{rel} 最新 gen-log 未引用 prompt 文件，无法核对 frontmatter style")
            continue
        prompt_rel = _norm_relpath(pm.group(0))
        prompt_path = cwd / Path(prompt_rel)
        if not prompt_path.exists():
            errors.append(f"{rel} 日志引用的 prompt 不存在：{prompt_rel}")
            continue
        prompt_text = prompt_path.read_text(encoding="utf-8")
        sm = re.search(r"(?m)^style:\s*[\"']?([^\"'\s]+)", prompt_text)
        prompt_style = sm.group(1) if sm else ""
        seen_styles.add(prompt_style)
        if style and prompt_style != style:
            errors.append(f"{prompt_rel} frontmatter style={prompt_style or '(空)'}，应为 {style}")

    nonempty_styles = {s for s in seen_styles if s}
    if len(nonempty_styles) > 1:
        errors.append(f"最终信息图证据链混入多种 style：{sorted(nonempty_styles)}")
    return errors


def _visual_qa_errors(cwd: Path) -> list:
    """发布前视觉 QA 凭证门：机器查结构，审美与逐字核验由 Agent 看图后打卡。"""
    qa_path = cwd / "_visual-qa.md"
    if not qa_path.exists():
        return ["缺 _visual-qa.md：生成后必须逐张看图验收，不能把草稿箱当第一道视觉 QA"]
    text = qa_path.read_text(encoding="utf-8")
    errors = []
    checked = len(re.findall(r"(?m)^\s*- \[x\]", text, flags=re.I))
    cover_terms = ("封面", "主标题", "杂字", "裁切")
    info_terms = ("信息图", "图 1", "图 4", "逐字")
    missing_cover = [term for term in cover_terms if term not in text]
    missing_info = [term for term in info_terms if term not in text]
    if missing_cover:
        errors.append(f"_visual-qa.md 封面检查不完整，缺：{missing_cover}")
    if missing_info:
        errors.append(f"_visual-qa.md 信息图检查不完整，缺：{missing_info}")
    if checked < 8:
        errors.append(f"_visual-qa.md 已勾选项仅 {checked} 条（需 ≥8，覆盖封面与四张信息图）")
    if "通过" not in text:
        errors.append("_visual-qa.md 缺最终结论“通过”")
    return errors


def load_state(cwd: Path) -> dict:
    state_path = cwd / STATE_FILE
    if not state_path.exists():
        sys.exit(
            f"❌ 未找到 {STATE_FILE}。\n"
            f"   请先运行：python pipeline.py init"
        )
    return json.loads(state_path.read_text(encoding="utf-8"))


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
        "topic_id": topic_id,
        "topic_dir": str(cwd),
        "style": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "stages": {s: {"status": "pending"} for s in STAGE_ORDER},
        "lead_params": {"line1": "", "line2": "", "subtitle": "", "tag1": "", "tag2": ""},
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
        if "作者免检授权" in text:
            return []
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
        if not re.search(r"信息图主题.*(?:ai-product|phenomenon)", text):
            missing.append("信息图主题 ai-product/phenomenon")
        if not re.search(r"信息图风格.*(?:claymation|morandi-journal)", text):
            missing.append("信息图风格")
        if missing:
            return [
                f"checkpoint:blueprint 锚点结构不完整（视觉路由不可省）：缺 {missing}；"
                f"补齐 {anchor} 后再继续"
            ]
    return []


def verify_stage(stage: str, cwd: Path, state: dict, legacy: bool = False) -> tuple:
    """返回 (passed: bool, errors: list[str])。
    legacy=True 时跳过 2026-04 之后新增的严格断言（供旧文章迁移使用）。
    """
    errors = []

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
                if bd.get("verdict") != "ok":
                    errors.append(
                        f"verify_bold_density verdict={bd.get('verdict')} "
                        f"({bd.get('bold_count', 0)}/{bd.get('bold_limit', 0)}，"
                        f"整段加粗 {bd.get('integral_bold_count', 0)})"
                    )

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
        # 封面图元数据校验：在正常（非 legacy）路径执行；legacy（旧文章迁移）放宽个别断言。
        # 2026-05-30 修：原先这三组校验误嵌在 else(legacy) 分支 + 内层 `if not legacy` 恒为假 = 死代码，
        # 导致正常路径只查了 hero 文件名、AR/分辨率/白名单全不查（虚假绿灯）。
        if covers:
            meta = _image_metadata(covers[0])
            if not meta:
                # Pillow 未装或文件损坏——2026-04 起不再静默跳过
                if not legacy:
                    errors.append(
                        "无法读取 cover 图像元数据（Pillow 未装？请 `pip install Pillow`，或加 --legacy 跳过）"
                    )
            else:
                # 1) AR 比例 2.35:1（允许 2.1 ~ 2.6）
                if not legacy and not (2.1 <= meta["ratio_wh"] <= 2.6):
                    errors.append(
                        f"cover.png 宽高比 {meta['ratio_wh']:.2f} 不符合 2.35:1（允许 2.1~2.6）。"
                        f"最常见原因：误用了 `generate_image`（只出 1:1），应走 /baoyu-cover-image"
                    )
                # 2) 分辨率 ≥1K（长边 1000px 判定）
                if not legacy and meta["long_edge"] < 1000:
                    errors.append(
                        f"cover.png 分辨率过低（长边 {meta['long_edge']}px < 1000px）。"
                        f"baoyu-cover-image 默认 1K，是否漏传 `--quality 1k`？"
                    )
            # 3) 生图来源白名单（.gen-log.jsonl 有记录时才检查）
            if not legacy:
                logs = _read_gen_log(cwd, "cover")
                if logs:
                    last = logs[-1]
                    tool = last.get("tool", "")
                    if tool in IMAGE_TOOL_BLACKLIST:
                        errors.append(
                            f"cover 使用了禁用工具 `{tool}`。封面图必须走 `/baoyu-cover-image`"
                        )
                    elif tool and tool not in IMAGE_TOOL_WHITELIST["cover"]:
                        errors.append(
                            f"cover 使用的 `{tool}` 不在白名单（应为 baoyu-cover-image）"
                        )

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
                            f"{p.name} 分辨率过低（长边 {meta['long_edge']}px < 1000px），漏传 `--quality 1k`？"
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
                                f"infographic 使用了禁用工具 `{tool}`。信息图必须走 `/baoyu-infographic`"
                            )
                            break
                        elif tool and tool not in IMAGE_TOOL_WHITELIST["infographic"]:
                            errors.append(
                                f"infographic 使用的 `{tool}` 不在白名单（必须用 baoyu-infographic skill，禁直接调 baoyu-image-gen 等底层工具）"
                            )
                            break
                        # 🔴 曾踩坑：信息图风格漂移
                        # 对齐 image-routing.md：合法 style = claymation / morandi-journal
                        # 二选一（craft-handmade 仅历史兼容），维持整体调性，不可漂移到其他 style
                        _ALLOWED_INFO_STYLES = ("claymation", "morandi-journal", "craft-handmade")
                        if tool == "baoyu-infographic" and cmd_str:
                            if "--style" not in cmd_str:
                                errors.append(
                                    f"infographic 命令缺少 `--style` 参数（cmd: `{cmd_str[:80]}...`）。"
                                    f"信息图统一用 claymation / morandi-journal 二选一（image-routing.md），不可漂移"
                                )
                                break
                            elif not any(s in cmd_str for s in _ALLOWED_INFO_STYLES):
                                style_m = re.search(r"--style\s+(\S+)", cmd_str)
                                got = style_m.group(1) if style_m else "(未知)"
                                errors.append(
                                    f"infographic 用了 `--style {got}`，不在允许集 {{claymation / morandi-journal / craft-handmade}}。"
                                    f"image-routing.md 2026-05-26 已固化 claymation/morandi-journal 二选一（craft-handmade 仅历史兼容）"
                                )
                                break
                else:
                    # 没有 gen-log 记录但素材里有 PNG → 说明跳过了 baoyu-infographic skill（如手写 SVG / 直接放图）
                    # 这种情况风格/工具完全不可追溯，必须拦下
                    errors.append(
                        f"infographic 没有 .gen-log.jsonl 记录，但 素材/ 里有 {len(infos)} 张 infographic*.png。"
                        f"说明跳过了 baoyu-infographic skill 流程（如手写 SVG 或直接放图）。"
                        f"必须经由 baoyu-infographic 出图并 `pipeline.py log infographic baoyu-infographic ...` 记录，"
                        f"以保证风格统一可追溯（详见 iron-rules.md 信息图铁律）"
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
        if url and url.startswith("https://mp.weixin.qq.com"):
            pass  # 正式发布完成
        elif draft_id:
            pass  # 草稿箱已推送，待人工正式发布后补 wechat_url
        else:
            errors.append(
                "publish 既无 draft_media_id 也无 wechat_url。"
                "草稿箱推送成功后：pipeline.py done publish draft_media_id=<media_id>；"
                "正式发布后补：pipeline.py done publish wechat_url=https://mp.weixin.qq.com/s/xxx"
            )

    elif stage == "archive":
        # 二期C：按 seq 查 works.yaml（不再靠 articles.md 标题子串）
        try:
            from works_registry import load_works
            seq_str = cwd.name.split("-")[0]
            seq = int(seq_str) if seq_str.isdigit() else None
            rec = next((w for w in load_works() if w.get("seq") == seq), None)
            if rec is None:
                errors.append(f"works.yaml 未找到 seq={seq} 的记录 — 请先跑：pipeline.py archive")
            elif not rec.get("code"):
                errors.append(f"seq={seq} 记录缺 code（分类未分配，检查 article-meta.yaml 的 category）")
        except Exception as e:
            errors.append(f"works.yaml 校验失败：{e}")

    return (len(errors) == 0, errors)


# ── 命令实现 ──────────────────────────────────────────────────
def _cross_check(cwd: Path, state: dict) -> list:
    """扫四份状态文件，返回不一致项列表（仅警告，不阻断）。

    检查项：
    1. .state.json 的 style vs article-meta.yaml 的 style
    2. .state.json writing.title_final vs article-meta.yaml 的 title
    3. article-meta.yaml part_subtitles 数量 vs 定稿.md H2 数量
       （format_layout.py --all 会在排版前 sys.exit(3) 阻断，这里提前发现）
    4. stages 顺序逻辑（done 但前序未完成）
    5. publish=done 但 wechat_url 缺失或非微信链接
    6. archive=done 但 <数据目录>/works.yaml 未找到对应 seq 记录
    """
    warnings = []

    # 1 & 2. .state.json vs article-meta.yaml 字段一致性
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
        s_style = state.get("style", "")
        m_style = meta.get("style", "")
        if s_style and m_style and s_style != m_style:
            warnings.append(
                f"风格不一致：.state.json={s_style!r} vs article-meta.yaml={m_style!r}"
            )

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
    stages = state.get("stages", {})
    prev_done = True
    for s in STAGE_ORDER:
        status = stages.get(s, {}).get("status", "pending")
        if status == "done" and not prev_done:
            warnings.append(f"{s}=done 但前序阶段未完成（顺序异常，可能是手动 skip 残留）")
        if status not in ("done", "skip"):
            prev_done = False

    # 5. publish=done 但 wechat_url 缺失
    pub = stages.get("publish", {})
    if pub.get("status") == "done":
        url = pub.get("wechat_url", "")
        if not url:
            warnings.append("publish=done 但 wechat_url 字段为空（archive 时会找不到链接）")
        elif not url.startswith("https://mp.weixin.qq.com"):
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


def cmd_status(cwd: Path):
    state = load_state(cwd)
    style = state.get("style") or "未选"
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
        if status in ("pending", "failed") and next_stage is None:
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
            "\n📝 当前为草稿态（draft_media_id 已推送），正式发布后补 wechat_url 才能 archive：\n"
            "   pipeline.py done publish wechat_url=https://mp.weixin.qq.com/s/xxx"
        )

    if next_stage:
        print(f"\n▶ 下一步：{next_stage}\n  {STAGE_HINTS[next_stage]}\n")
    else:
        print("\n🎉 全流程完成！\n")


def cmd_next(cwd: Path):
    state = load_state(cwd)
    for s in STAGE_ORDER:
        status = state["stages"].get(s, {}).get("status", "pending")
        if status in ("pending", "failed"):
            print(f"\n▶ 下一阶段：{s} — {STAGE_LABELS[s]}\n")
            print(f"  {STAGE_HINTS[s]}\n")
            return
    print("🎉 全流程完成！")


def _pre_publish_errors(cwd: Path) -> list:
    """publish --pre 素材齐备门（2026-07-21 实战固化）：推送前专用。
    iron-rules「发布前硬闸」的落地 -- 只查素材/文件齐备，不查推送证据
    （draft_media_id / wechat_url 归 `verify publish` 推送后验证）。"""
    errors = []
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
    route_errors = _visual_route_errors(cwd)
    errors.extend(f"visual_route: {e}" for e in route_errors)
    qa_errors = _visual_qa_errors(cwd)
    errors.extend(qa_errors)
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
    return errors


def cmd_verify(stage: str, cwd: Path, legacy: bool = False, pre: bool = False):
    if pre:
        if stage != "publish":
            print("⚠️ --pre 仅 publish 阶段使用（推送前素材齐备门）")
            return
        errors = _pre_publish_errors(cwd)
        if errors:
            print("❌ publish --pre 素材门未过：")
            for e in errors:
                print(f"   • {e}")
        else:
            print("✅ publish --pre 素材齐备门通过（cover + hero + ≥4 信息图 + 定稿.html + 嵌入契约）")
        return  # --pre 只判定不标 done
    state = load_state(cwd)
    passed, errors = verify_stage(stage, cwd, state, legacy=legacy)
    if passed:
        state["stages"][stage]["status"] = "done"
        state["stages"][stage]["finished_at"] = _now_iso()
        # 通过后清零 fail_count，避免历史失败计数误导
        state["stages"][stage]["fail_count"] = 0
        save_state(cwd, state)
        print(f"✅ {stage} 验证通过，已标记 done" + ("（legacy 模式）" if legacy else ""))
    else:
        state["stages"][stage]["status"] = "failed"
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
    state = load_state(cwd)
    # 记录是否首次 done（status 从非 done 变 done）
    was_done_before = state["stages"].get(stage, {}).get("status") == "done"
    # 写入附加元数据
    for kv in extras:
        if "=" in kv:
            k, v = kv.split("=", 1)
            state["stages"][stage][k.strip()] = v.strip()
    # 先跑 verify
    passed, errors = verify_stage(stage, cwd, state, legacy=legacy)
    if not passed:
        print(f"⚠️  {stage} 自动检查未全部通过：")
        for e in errors:
            print(f"   • {e}")
        if not force:
            import sys
            # 2026-04-23 收紧：isatty() 在 Claude Code Bash / MSYS / CI 里偶尔返回
            # True 但 stdin 已关闭，input() 直接抛 EOFError 脚本崩溃。
            # 这里把 input() 放进 try/except，任何读不到输入都当作"否，不强制"。
            answered_yes = False
            if sys.stdin.isatty():
                try:
                    ans = input("  仍然强制标记为 done？(y/N) ").strip().lower()
                    answered_yes = (ans == "y")
                except (EOFError, KeyboardInterrupt):
                    print("  （stdin 不可读，已跳过确认。如需强制标记请加 --force）")
            else:
                print("  （非交互模式，已跳过确认。如需强制标记请加 --force）")

            if not answered_yes:
                # 累计 fail_count（与 cmd_verify 一致，触发"连错 3 次"告警）
                state["stages"][stage]["status"] = "failed"
                prev_count = state["stages"][stage].get("fail_count", 0)
                new_count = prev_count + 1
                state["stages"][stage]["fail_count"] = new_count
                save_state(cwd, state)
                if new_count >= 3:
                    print()
                    print(f"⚠️  此阶段已连续失败 {new_count} 次。"
                          f"按 autopilot 失败 SOP，应停下回报用户。")
                return
    state["stages"][stage]["status"] = "done"
    state["stages"][stage]["finished_at"] = _now_iso()
    state["stages"][stage]["fail_count"] = 0  # done = 通过，清零
    save_state(cwd, state)
    print(f"✅ {stage} 已标记 done")

    # 2026-04-28 新增：writing 阶段触发 learn_edits 飞轮（首次快照 / 再次 diff）
    # 任何异常都不会影响上面的 done 标记
    if stage == "writing":
        # 实证（整篇几百处半角标点靠手动救）：done writing
        # 自动把 定稿.md 中文紧邻的半角标点转全角，作为 MD→HTML 的确定性前置 ——
        # 半角标点门（format_layout）从此基本是空跑安全网，不再到排版才 exit 2。
        # 必须在 _maybe_trigger_learn_edits 之前，让飞轮基线快照是已归一化版本。
        try:
            _auto_normalize_punctuation(cwd)
        except Exception as e:
            print(f"⚠️  自动标点归一化出错（不影响 done 标记）：{e}")
        try:
            _maybe_trigger_learn_edits(cwd)
        except Exception as e:
            print(f"⚠️  learn_edits 飞轮触发出错（不影响 done 标记）：{e}")


def cmd_log(stage: str, tool: str, cwd: Path, output: str = "", cmd: str = ""):
    """追加一条生图记录到 .gen-log.jsonl（供后续 verify 回溯用哪个工具）。"""
    rec = {
        "stage": stage,
        "tool": tool,
        "output": output,
        "cmd": cmd,
        "timestamp": _now_iso(),
    }
    log_path = cwd / GEN_LOG_FILE
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # 路由白名单提示（不 fail，仅 warn——让 verify 阶段 fail）
    if tool in IMAGE_TOOL_BLACKLIST:
        print(f"⚠️  工具 `{tool}` 在黑名单中，verify {stage} 会 fail")
    elif stage in IMAGE_TOOL_WHITELIST and tool not in IMAGE_TOOL_WHITELIST[stage]:
        print(f"⚠️  工具 `{tool}` 不在 {stage} 白名单 {IMAGE_TOOL_WHITELIST[stage]}")
    print(f"📝 已记录：{stage} / {tool} → {output or '(no output path)'}")


def cmd_history(cwd: Path, extras: list):
    """[DEPRECATED] 旧的写 history.yaml 命令，已被 archive 取代（二期：works.yaml 是单一数据源）。

    2026-06-20 审查 F/G：return 之后的旧逻辑是不可达死代码（恒被上面的 return 拦下），已删除。
    history.yaml 已冻结，归档一律走 cmd_archive。
    """
    print("⚠️ pipeline.py history 已废弃 -- <数据目录>/works.yaml 才是单一数据源（含创作记忆）。")
    print("   请改用：pipeline.py archive（写 works.yaml + 自动刷新 articles.md/看板）。")
    print("   未写入 history.yaml（避免污染已冻结的旧文件）。")
    return


def cmd_archive(cwd: Path, extras: list) -> bool:
    """二期C 归档：把本篇写入 works.yaml（自动分类编码）+ 自动刷新 articles.md/看板。

    返回 True＝归档成功；返回 False＝abort（缺 seq/category/wechat_url）。
    2026-07-01：main 分发层据此返回值决定退出码（abort → sys.exit(1)），
    让上游 `&&`/退出码判断能检测归档失败。cmd 本身不 sys.exit（保持可被
    tests 直接调用、断言 capsys 而不触发 SystemExit）。
    """
    from works_registry import (upsert_work, load_works, validate_works,
                                CATEGORY_CODES, TAG_VOCAB,
                                OUTWARD_CATEGORIES, suggest_outward)
    import render_articles_md as RAM
    import render_works_dashboard as RWD

    state = load_state(cwd)
    meta = {}
    meta_path = cwd / "article-meta.yaml"
    if meta_path.exists() and _yaml:
        try:
            meta = _yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    override = {}
    for kv in extras:
        if "=" in kv:
            k, v = kv.split("=", 1)
            override[k.strip()] = v.strip()

    seq_str = cwd.name.split("-")[0]
    seq = int(seq_str) if seq_str.isdigit() else None
    if seq is None:
        print("❌ 无法从文件夹名解析 seq（应形如 47-选题名）")
        return False

    category = override.get("category") or meta.get("category", "")
    if category not in CATEGORY_CODES:
        print(f"❌ article-meta.yaml 缺 category 或非法（需 {sorted(CATEGORY_CODES)}）")
        print("   请先在 article-meta.yaml 填 category，再重跑 pipeline.py archive")
        return False

    # 对外分类（读者可见：外标题「标签 | 」前缀 + 网站/RSS）。正常在标题阶段（title.md 第一步）
    # 定好并回填 meta，此处直接复用；仅历史文章 / 漏填时才按 category 兜底：
    # TUT→教程 / ESS·KID→随笔 / ROB→资讯 自动补，AIT/OBS 语义跨多类必须人工填。
    outward = override.get("outward_category") or meta.get("outward_category", "")
    if not outward:
        sug, need_review = suggest_outward(category)
        if sug and not need_review:
            outward = sug
            print(f"ℹ️ outward_category 未填，按 category={category} 自动取默认：{outward}（{OUTWARD_CATEGORIES[outward]}）")
        else:
            print(f"❌ outward_category 未填且 category={category} 需人工判（走裁决链，选 {sorted(OUTWARD_CATEGORIES)}）")
            print("   请在 article-meta.yaml 填 outward_category，再重跑 pipeline.py archive")
            return False
    if outward not in OUTWARD_CATEGORIES:
        print(f"❌ outward_category={outward!r} 非法（需 {sorted(OUTWARD_CATEGORIES)}）")
        return False

    title = (state.get("stages", {}).get("writing", {}).get("title_final", "")
             or override.get("title", "") or meta.get("title", ""))
    url = state.get("stages", {}).get("publish", {}).get("wechat_url", "")
    if not url:
        # 2026-06-20 审查 B：草稿态不归档（archive 硬要 wechat_url 是有意设计）。
        # 2026-07-01：三个 abort 分支统一 `return False`，由 main 分发层转 sys.exit(1)——
        # cmd 内不直接 sys.exit（保留可被 tests 直接调用 + 断言 capsys 而不触发 SystemExit）。
        print("❌ publish.wechat_url 为空（草稿态不归档）。")
        print("   正式发布后执行：pipeline.py done publish wechat_url=https://mp.weixin.qq.com/s/xxx，再重跑 archive")
        return False

    cover_rel = ""
    if (cwd / "素材" / "cover.png").exists():
        cover_rel = f"<数据目录>/{cwd.name}/素材/cover.png"

    draft = cwd / "定稿.md"
    wc = len(draft.read_text(encoding="utf-8")) if draft.exists() else 0

    record = {
        "seq": seq,
        "category": category,
        "outward_category": outward,
        "tags": meta.get("tags", []) or [],
        "series": meta.get("series", "") or "",
        "merged_into": "",
        "date": override.get("date") or datetime.now().strftime("%Y-%m-%d"),
        "title": title,
        "digest": override.get("digest") or meta.get("digest", "") or "",
        "cover": cover_rel,
        "wechat_url": url,
        "status": "published",
        "style": meta.get("style", state.get("style", "")) or "",
        "logic_bone": meta.get("logic_bone", "") or "",
        "dimensions": meta.get("dimensions", []) or [],
        "closing_type": meta.get("closing_type", "") or "",
        "cover_keywords": meta.get("cover_keywords", "") or "",
        "cover_style": meta.get("cover_style", "") or "",
        "word_count": wc,
        "video": {"status": "none", "url": "", "platform": "",
                  "script_path": "", "hook_type": "", "duration_sec": 0, "shots": 0},
    }
    bad_tags = [t for t in record["tags"] if t not in TAG_VOCAB]
    if bad_tags:
        print(f"⚠️ 标签不在受控词表：{bad_tags} -- 请改 article-meta.yaml 的 tags，或在 works_registry.TAG_VOCAB 扩词（仍会写入，但 verify 会报错）")
    saved = upsert_work(record)
    works = load_works()
    errors = validate_works(works)
    # 自动刷新视图（articles.md + 看板）
    RAM.ARTICLES_MD.write_text(RAM.render_md(works), encoding="utf-8")
    RWD.DASHBOARD_FILE.write_text(RWD.build_html(works), encoding="utf-8")
    print(f"✅ 已写入作品库：{saved.get('code')} · {title}")
    print(f"   已自动刷新 articles.md + works-dashboard.html")
    print(f"   🌐 下一步·同步个人网站：bash 个人网站/web/scripts/publish-to-website.sh {saved.get('code') or '<CODE>'}")
    print(f"      （archive 只把文章标 published＝网站收录前提；真正「上网站＋推这篇配图」要跑上面这步。"
          f"每日 vps-sync cron 会 import+build 但部署 --exclude=article-assets 不传文章图，故新文章首发必须手动跑，否则网站封面图是破的）")
    print(f"   💬 最后一拍·朋友圈文案：上网站之后产出一条朋友圈文案给作者复制（只一版、每句句首带 emoji、"
          f"3-4 行=钩子→价值→profile 引流尾巴；不自动发、朋友圈无 API）。规格见 references/publish.md §发布后·朋友圈文案。"
          f"⚠ 这是发布链最后一拍、也是最易漏的一拍——机器不产出它、只提醒，产出后一并交付作者。")
    if errors:
        print("⚠️ 作品库校验有问题（请修 works.yaml）：")
        for e in errors:
            print("   " + e)

    # 金句沉淀留痕（非阻断 warning）。归档时比对金句库的 mtime 是否晚于本篇发布日，
    # 否则提醒尚未沉淀——让 autopilot 日志显式留痕，不再静默跳过沉淀环。
    # 金句库走 profile 覆盖层（profile/corpus/golden-lines.md）。参考 publish.md §发布后沉淀第4步。
    try:
        from profile_config import corpus_dir
        jf = corpus_dir() / "golden-lines.md"
        pub_date = record.get("date") or datetime.now().strftime("%Y-%m-%d")
        if jf.exists():
            jf_date = datetime.fromtimestamp(jf.stat().st_mtime).strftime("%Y-%m-%d")
            if jf_date < pub_date:
                print(
                    f"⚠️ 本篇尚未沉淀金句到 profile/corpus/golden-lines.md（库 mtime={jf_date} < 发布日={pub_date}，"
                    "参考 publish.md §发布后沉淀第4步）"
                )
        else:
            print("⚠️ 未找到 profile/corpus/golden-lines.md，无法核对金句沉淀（参考 publish.md §发布后沉淀第4步）")
    except Exception:
        pass

    return True


# 🔴 铁律 stage：不允许 skip（iron-rules.md 强约束）
# 曾踩坑：infographic 被 skip 后整篇文章漏了整组贯穿全文信息图
NEVER_SKIP_STAGES = {
    "writing",       # 没正文还发什么
    "cover",         # 没封面无法推草稿
    "infographic",   # iron-rules.md 强制：≥4 张贯穿全文信息图（开篇/结尾 9:16 各 1 + 中间 16:9 ≥2）
    "layout",        # 没排版的 md 不可发布
    "publish",       # 没推草稿就没发布
}


def cmd_skip(stage: str, cwd: Path, force: bool = False):
    if stage in NEVER_SKIP_STAGES and not force:
        print(f"🔴 拒绝 skip：`{stage}` 是铁律 stage（详见 references/iron-rules.md）")
        print(f"   - cover/layout/publish 是发布前置硬性产物，不可绕过")
        print(f"   - infographic 是文末知识图（≥4 张：开篇 9:16 + 中间 16:9 ×N + 结尾 9:16），缺了会被 publish verify 拦截")
        print(f"   - writing 是正文，不可能 skip")
        print(f"   如果是合理场景（如复刻历史文章），加 `--force` 显式确认承担后果")
        sys.exit(2)
    state = load_state(cwd)
    state["stages"][stage]["status"] = "skip"
    save_state(cwd, state)
    suffix = " (--force 强制跳过铁律)" if force and stage in NEVER_SKIP_STAGES else ""
    print(f"⏭  {stage} 已跳过{suffix}")
    # 2026-06-20 审查 B-3/B-4：bgm（及其它非黑名单可选阶段）不进 NEVER_SKIP_STAGES——
    # iron-rules 明确兼容无 BGM 的特殊文章，硬拦会误伤合法文章。改为显式区分「有意省略」与
    # 「失败绕过」：不静默放行，打印一条提示，提醒别拿 skip 绕过生成失败。
    if stage == "bgm":
        print("   本文将无主题曲卡片；若因生成失败而 skip，请按 autopilot.md 失败恢复 SOP 先重试/换风格，勿用 skip 绕过失败。")
    elif stage not in NEVER_SKIP_STAGES:
        print(f"   {stage} 为可选阶段；若因生成失败而 skip，请按 autopilot.md 失败恢复 SOP 先重试，勿用 skip 绕过失败。")


def cmd_reset(stage: str, cwd: Path):
    state = load_state(cwd)
    state["stages"][stage] = {"status": "pending"}
    save_state(cwd, state)
    print(f"🔄 {stage} 已重置为 pending")


def cmd_orchestrator(mode: str, cwd: Path):
    """全局编排开关。仅改 orchestrator / state_writer 两键并回写，
    不触碰任何既有阶段语义或既有字段。

    P1 已落地（2026-05-22）：本命令只切 state 字段。orchestrator=on 后，真正的
    fan-out 并行由主 Claude 按 orchestration.md §编排器 fan-out 实操手册执行
    （一条消息发 N 个 Agent 工具调用）。pipeline.py 自身始终只做状态记账 + verify，
    不 spawn subagent —— Agent 是 Claude 的工具，不是 Python 函数。"""
    state = load_state(cwd)
    state["orchestrator"] = mode
    state["state_writer"] = "orchestrator"
    save_state(cwd, state)
    print(f"🎛  orchestrator 已设为 {mode}")
    if mode == "on":
        print("🛠 主 Claude 将按 orchestration.md §编排器 fan-out 实操手册，")
        print("   在 fan-out 阶段（信息图/封面/调研等）一条消息发 N 个 Agent 真并行")


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
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init",   help="初始化 .state.json")
    sub.add_parser("status", help="查看当前进度 + 下一步建议")
    sub.add_parser("next",   help="打印下一阶段操作说明")

    p_v = sub.add_parser("verify", help="验证阶段完成情况（通过则自动标 done）")
    p_v.add_argument("stage", choices=STAGE_ORDER)
    p_v.add_argument("--legacy", action="store_true",
                     help="跳过 2026-04 之后新增的严格断言（旧文章迁移用）")
    p_v.add_argument("--pre", action="store_true",
                     help="publish 专用：推送前素材齐备门（cover/hero/≥4 信息图/定稿.html），只判定不标 done")

    p_d = sub.add_parser("done", help="标记阶段完成，可附加元数据 k=v")
    p_d.add_argument("stage", choices=STAGE_ORDER)
    p_d.add_argument("extras", nargs="*", metavar="k=v",
                     help="例：title_final=文章标题  wechat_url=https://...")
    p_d.add_argument("--force", "-f", action="store_true",
                     help="跳过 verify 确认直接标记 done（旧文章迁移或 CI 场景）")
    p_d.add_argument("--legacy", action="store_true",
                     help="verify 时跳过 2026-04 之后新增的严格断言")

    p_log = sub.add_parser("log", help="追加一条生图记录到 .gen-log.jsonl")
    # 2026-04-23 扩展：hero / bgm_cover 是独立的组件小图，也要能记录；
    # component 作为"其它未归类组件图"的兜底 stage，避免未来新组件又要回头改白名单
    p_log.add_argument("stage", choices=[
        "cover", "infographic", "illustrator", "chart",
        "hero", "bgm_cover", "component",
    ])
    p_log.add_argument("tool", help="实际调用的工具名，如 baoyu-cover-image / matplotlib")
    p_log.add_argument("--output", help="生成的文件相对路径")
    p_log.add_argument("--cmd", dest="cmd_line", help="实际执行的命令行（可选）")

    # history 子命令保留注册（避免破坏可能的调用方），但已废弃，改用 archive
    p_h = sub.add_parser("history", help="[DEPRECATED] 改用 archive（仅打印废弃提示）")
    p_h.add_argument("extras", nargs="*", metavar="k=v",
                     help="覆盖字段，如 title='文章标题' closing_type='硬切'")

    p_a = sub.add_parser("archive", help="发布归档：写 works.yaml + 刷新 articles.md/看板")
    p_a.add_argument("extras", nargs="*", metavar="k=v",
                     help="覆盖字段，如 category=AIT digest='一句话摘要' date=2026-05-30")

    p_s = sub.add_parser("skip",  help="跳过某阶段")
    p_s.add_argument("stage", choices=STAGE_ORDER)
    p_s.add_argument("--force", action="store_true",
                     help="强制跳过铁律 stage（writing/cover/infographic/layout/publish）。仅在复刻历史文章等明确合理场景使用")

    p_r = sub.add_parser("reset", help="重置阶段为 pending")
    p_r.add_argument("stage", choices=STAGE_ORDER)

    p_o = sub.add_parser("orchestrator", help="全局编排开关（on=启用编排器 / off=回滚到手动）")
    p_o.add_argument("mode", choices=["on", "off"])

    p_rt = sub.add_parser("retitle", help="改标题并连锁同步 meta/定稿/大纲/state（附后续动作提醒）")
    p_rt.add_argument("title", help="新标题")

    args = parser.parse_args()
    cwd = Path.cwd()

    if args.cmd == "init":
        cmd_init(cwd)
    elif args.cmd == "status":
        cmd_status(cwd)
    elif args.cmd == "next":
        cmd_next(cwd)
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
                cmd=getattr(args, "cmd_line", "") or "")
    elif args.cmd == "history":
        cmd_history(cwd, getattr(args, "extras", []))
    elif args.cmd == "archive":
        # 2026-07-01：archive abort（缺 seq/category/wechat_url）→ 非零退出码，
        # 让上游 `&&`/退出码判断能检测归档失败（cmd_archive 返回 False 即 abort）。
        if not cmd_archive(cwd, getattr(args, "extras", [])):
            sys.exit(1)
    elif args.cmd == "skip":
        cmd_skip(args.stage, cwd, force=getattr(args, "force", False))
    elif args.cmd == "reset":
        cmd_reset(args.stage, cwd)
    elif args.cmd == "orchestrator":
        cmd_orchestrator(args.mode, cwd)


if __name__ == "__main__":
    main()
