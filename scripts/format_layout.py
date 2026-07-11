#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
format_layout.py — 微信公众号排版自动后处理脚手架
=================================================

职责：将 baoyu-markdown-to-html 输出的原始 HTML 清洗为满足 layout.md 全部规范的最终发布版。
设计原则：
  1. 高幂等性 —— 重复执行不叠加不破坏
  2. 模块化 —— --all 全跑，或 --h2 / --table / --lead / --footer / --colors / --takeaway 按需单跑
  3. 确定性 —— 不依赖 AI 临场发挥，所有替换规则硬编码
  4. 配置持久化 —— 支持从 article-meta.yaml 读取文章个性化参数

用法:
  python format_layout.py 定稿.html --all
  python format_layout.py 定稿.html --table --colors
  python format_layout.py 定稿.html --h2 --lead --footer
  python format_layout.py 定稿.html --check            # 预发布自检
  python format_layout.py 定稿.html --all --check       # 处理 + 自检

版本: 3.0.0  (2026-04-11 增加 article-meta.yaml / --check / --lead-quote)
"""

import os
import sys
import re
import argparse
import subprocess
from pathlib import Path

# Windows 控制台 GBK 兜底：强制 stdout/stderr UTF-8，避免 emoji 触发 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ===== 【第 1 节】Design Tokens · 主题令牌 SSOT =====
#
#  这些常量是**默认值**（中性 slate 配色）。真值来自你的 profile：
#      profile/brand.yaml 的 colors / radius  →  经 profile_config.brand() 覆盖
#  改配色一律改 profile，不要在这里或 templates/*.html 里写死 hex。
#  templates 用的是同一套默认值，排版末尾由 process_theme() 统一换成你的值。
#  未配置 profile 时全部回退到下面的默认值（这是正常路径，不是错误）。
#
#  设计参考：references/design-tokens.md
# ============================================================
try:
    from profile_config import brand as _brand, colors as _colors
    _C = _colors()
    _R = _brand().get("radius", {})
except Exception:  # profile_config 不可用时纯用默认值，绝不因主题问题卡住排版
    _C, _R = {}, {}


def _c(key: str, default: str) -> str:
    v = _C.get(key)
    return v if isinstance(v, str) and v.strip() else default


def _r(key: str, default: str) -> str:
    v = _R.get(key)
    return v if isinstance(v, str) and v.strip() else default


# 一级 / 二级强调（同色相做明度分主次，统一又分级）
BRAND_PRIMARY = _c("primary", "#2F6F8F")      # 主强调：重点突出 / H3 / 表头 / 一级标识
BRAND_SECONDARY = _c("secondary", "#7FB0C4")  # 次强调：次级标识 / 辅助强调（小字正文慎用）

# 圆角（4 档尺度：小件 / 媒体 / 卡片 / 大模块；胶囊用全圆）
RADIUS_SM     = _r("sm", "6px")        # 序号块 / 图标底 / URL 框 等小 UI 件
RADIUS_MEDIA  = _r("media", "8px")     # 图片 / 缩略图
RADIUS_CARD   = _r("card", "10px")     # 卡片 / 表格 / 链接卡 容器
RADIUS_MODULE = _r("module", "12px")   # 大模块（导读 / 深读）
RADIUS_PILL   = _r("pill", "999px")    # 胶囊（标签 / 徽章）

# 浅色底（4 个语义角色：强调卡 / 容器模块 / 内嵌框 / 表格行）
TINT_CARD  = _c("primary_soft", "rgba(47, 111, 143,0.05)")  # 强调卡（要点/金句，带 4px 左竖条）
TINT_SOFT  = _c("surface_soft", "#f2f7f9")                  # 容器模块（深读/链接/音乐，带全边框）
TINT_INSET = _c("surface_inset", "#eaf1f5")                 # 内嵌 URL / 图标框
TINT_ROW   = _c("row_tint", "rgba(47, 111, 143,0.03)")      # 表格交替行（最淡）

# 边框
BORDER_CARD   = _c("border_card", "#d7e3ea")   # 卡片 / 模块外框
BORDER_HAIR   = _c("surface", "#eef0f2")       # 内分隔线 / 表格行分隔
LINE_TIMELINE = "rgba(0,0,0,0.06)"             # 时间线竖线（中性，不随主题）

# 文字
TEXT_BODY  = _c("text_strong", "#333333")   # 正文
TEXT_TITLE = _c("text_title", "#26333a")    # 深色标题 / 引文
TEXT_MUTED = _c("text_mute", "#8a929a")     # 副标题 / 说明 / 出处
TEXT_FAINT = "#b0b6bb"                      # 极弱提示（中性，不随主题）

def _primary_alpha(fmt: str, default: str) -> str:
    """主色衍生半透明：用 BRAND_PRIMARY 的 RGB 填充 fmt（如 "rgba({r}, {g}, {b},0.12)"）。

    模板 / f-string 里有几处「主色 @ 低 alpha」的装饰值（PART 分节线、金句卡发丝线、
    引用块底），它们不是独立令牌、必须随 primary 换算。主色不是 #RRGGBB 时回退 default
    （映射自换自 → no-op），绝不因主题问题卡排版。
    """
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", BRAND_PRIMARY.strip())
    if not m:
        return default
    h = m.group(1)
    return fmt.format(**{k: int(h[i:i + 2], 16) for k, i in (("r", 0), ("g", 2), ("b", 4))})


# 模板里写死的默认值 → 当前主题值 的映射（process_theme 用；值相同则整体 no-op）
# 🔴 全量令牌：13 色令牌 12 个在此（TEXT_FAINT #b0b6bb 设计上不随主题，刻意不映射），
#    另加 4 个「主色衍生 alpha」装饰值。新增模板硬编码色值前先想清楚归哪一行。
_THEME_DEFAULTS = {
    "#2F6F8F": BRAND_PRIMARY,
    "#7FB0C4": BRAND_SECONDARY,
    "#245a75": _c("primary_deep", "#245a75"),
    "#4a6b7a": _c("text_link", "#4a6b7a"),
    "#f2f7f9": TINT_SOFT,
    "#eaf1f5": TINT_INSET,
    "#d7e3ea": BORDER_CARD,
    "#eef0f2": BORDER_HAIR,   # surface：内分隔线 / 表格行分隔（深读条目线等）
    "#26333a": TEXT_TITLE,
    "#8a929a": TEXT_MUTED,
    "#333333": TEXT_BODY,     # text_strong：正文 / PART 标题行 / 时间线正文
    "rgba(47, 111, 143,0.05)": TINT_CARD,
    "rgba(47, 111, 143,0.03)": TINT_ROW,
    # 主色衍生 alpha（随 primary 换算，非独立令牌）：
    "rgba(47, 111, 143,0.12)": _primary_alpha("rgba({r}, {g}, {b},0.12)", "rgba(47, 111, 143,0.12)"),    # H2 PART 底部分节线
    "rgba(47, 111, 143,0.3)": _primary_alpha("rgba({r}, {g}, {b},0.3)", "rgba(47, 111, 143,0.3)"),       # H2 PART 编号右竖线
    "rgba(47, 111, 143,0.14)": _primary_alpha("rgba({r}, {g}, {b},0.14)", "rgba(47, 111, 143,0.14)"),    # 金句卡出处发丝分隔线
    "rgba(47, 111, 143, 0.05)": _primary_alpha("rgba({r}, {g}, {b}, 0.05)", "rgba(47, 111, 143, 0.05)"), # process_colors 引用块底（历史带空格写法）
}


def process_theme(html: str) -> str:
    """把模板里写死的默认色，换成当前 profile 的主题色（E-1：一处改完，全局换皮）。

    默认 profile 下每一项映射都是"自己换自己"，整体 no-op、零行为变更。

    两段式替换（默认值 → 占位符 → 主题值）+ 默认值按长度降序：
      ① 防「主题值恰好等于另一条映射的默认值」时被后续映射二次误替换（如某主题把
         text_title 配成 #333333，直接单遍替换会让标题再被 text_strong 那条错染）；
      ② 防未来出现「一个默认值是另一个默认值的前缀」时短值先替换啃坏长值。
    """
    import re as _re
    pending = []
    for i, (default, active) in enumerate(
            sorted(_THEME_DEFAULTS.items(), key=lambda kv: len(kv[0]), reverse=True)):
        if default == active:
            continue
        placeholder = f"\x00SSTHEME{i}\x00"  # NUL 包裹，正常 HTML 不可能撞车
        html = _re.sub(_re.escape(default), placeholder, html, flags=_re.IGNORECASE)
        pending.append((placeholder, active))
    for placeholder, active in pending:
        html = html.replace(placeholder, active)
    return html

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parent / "templates"

# 默认导读栏文案（用于检测是否被覆盖）
DEFAULT_LEAD_LINE1 = "深度拆解"
DEFAULT_LEAD_LINE2 = "硬核干货"
DEFAULT_LEAD_SUBTITLE = "一篇看懂核心要素与底层逻辑"


# ===== 【第 2 节】通用工具 log =====
def log(msg):
    print(f"  🔧 [FormatLayout] {msg}")


# ========================================
# ===== 【第 3 节】article-meta 配置读取 =====
#  article-meta.yaml 配置读取
# ========================================
def load_article_meta(cwd):
    """从工作目录读取 article-meta.yaml，返回 dict（找不到或解析失败返回空 dict）"""
    if not HAS_YAML:
        return {}
    meta_path = Path(cwd) / "article-meta.yaml"
    if not meta_path.exists():
        return {}
    try:
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            log(f"📋 已读取 article-meta.yaml（{len(data)} 个字段）")
            return data
    except Exception as e:
        log(f"⚠️ article-meta.yaml 解析失败: {e}")
    return {}


def apply_meta_to_args(args, meta):
    """将 article-meta.yaml 中的值填充到 args（CLI 显式传入的值优先）。

    导读栏字段同时支持两种写法，向后兼容：
      - 嵌套：  lead:\\n  line1: ...\\n  line2: ...
      - 扁平：  lead_line1: ...\\n  lead_line2: ...
    """
    lead_nested = meta.get("lead") or {}
    # 嵌套优先取，扁平作为回退，CLI 显式值最高优先级
    mapping = {
        "lead_line1":    lead_nested.get("line1")    or meta.get("lead_line1"),
        "lead_line2":    lead_nested.get("line2")    or meta.get("lead_line2"),
        "lead_subtitle": lead_nested.get("subtitle") or meta.get("lead_subtitle"),
        "lead_tag1":     lead_nested.get("tag1")     or meta.get("lead_tag1"),
        "lead_tag2":     lead_nested.get("tag2")     or meta.get("lead_tag2"),
    }
    for attr, val in mapping.items():
        if val and not getattr(args, attr, None):
            setattr(args, attr, val)

    # part_subtitles
    if meta.get("part_subtitles") and not getattr(args, "part_subtitles", None):
        setattr(args, "part_subtitles", meta["part_subtitles"])


# ========================================
# ===== 【第 4 节】模块10 预发布自检 --check =====
#  模块 10: 预发布自检 (--check)
# ========================================
def check_all(html, cwd, meta=None):
    """预发布自检，返回 (errors, warnings) 两个列表。

    meta: 可选，已读取的 article-meta.yaml dict。外部已读的话直接传入避免重复 log。
    """
    errors = []
    warnings = []

    # 读取 meta 判断是否跳过字符数硬检查（图片 URL 占字符数很常见，默认降为 warning）
    if meta is None:
        meta = load_article_meta(cwd)
    skip_char_count = bool(meta.get("skip_char_count", False))

    # 1. 字符数检查（2026-04-23：默认 warning 不阻断，memory 里固化"图片原因超标但发布正常"）
    content_match = re.search(r'<div id="output">([\s\S]*?)</div>\s*</body>', html)
    if content_match:
        chars = len(content_match.group(1).strip())
        if skip_char_count:
            log(f"📏 Content 字符数: {chars}（article-meta.yaml skip_char_count=true，已跳过检查）")
        else:
            if chars > 19000:
                warnings.append(f"字符数 {chars}/20000 超限（图片 URL 占大头，通常不影响发布；如需硬阻断，移除 yaml 的 skip_char_count）")
            elif chars > 17000:
                warnings.append(f"字符数 {chars}/20000 接近上限")
            log(f"📏 Content 字符数: {chars}/20000")
    else:
        errors.append("严重结构损坏：未找到 <div id=\"output\"> 或 </body>，MD转HTML解析失败")

    # 1b. meta description 安全检查
    # baoyu-md 的 extractSummaryFromBody 不跳过 `<`/`<!--` 开头的裸 HTML 行，
    # BGM 插入 AUDIO-CARD 后若 md 没有 description frontmatter，会把 HTML 吞进
    # <meta name="description" content="...">，head 属性未闭合 → 整个 HTML 崩坏。
    # 这里在 head 匹配该 meta，检查 content 是否含尖括号或注释符。
    head_match = re.search(r'<head[^>]*>([\s\S]*?)</head>', html, re.IGNORECASE)
    if head_match:
        head_block = head_match.group(1)
        desc_match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"',
            head_block,
            re.IGNORECASE,
        )
        if desc_match:
            desc_val = desc_match.group(1)
            if "<" in desc_val or "<!--" in desc_val:
                errors.append(
                    "meta description 含裸 HTML/注释，head 结构将被微信 parser 破坏"
                    "（通常因 BGM 后未给 md 加 description frontmatter），"
                    "请在 定稿.md 顶部加 `---\\ndescription: \"...\"\\n---\\n` 后重跑 MD→HTML"
                )
        # 粗检：head 区块内若出现 <body 或 <div id="output">，说明属性未闭合
        if re.search(r'<body[\s>]', head_block, re.IGNORECASE) or '<div id="output"' in head_block:
            errors.append(
                "head 区块内混入 <body> 或 <div id=\"output\">，"
                "说明上游 meta 属性未闭合，HTML 结构已崩坏"
            )
    else:
        errors.append("缺少 <head>...</head>，HTML 顶层结构异常")

    # 2. 品牌色审计
    bad_blues = len(re.findall(r'#0F4C81', html, re.IGNORECASE))
    bad_reds = len(re.findall(r'#d14\b', html))
    bad_grays = html.count("background: #f7f7f7")
    if bad_blues:
        errors.append(f"{bad_blues} 处蓝色 #0F4C81 残留")
    if bad_reds:
        errors.append(f"{bad_reds} 处红色 #d14 残留")
    if bad_grays:
        warnings.append(f"{bad_grays} 处灰色 blockquote 背景未替换")

    # 3. 组件完整性
    components = {
        "导读栏": "display: table-cell; width: 64%",
        "H2 格式": None,  # 特殊处理
        "推荐阅读": "推荐阅读",
        "关注卡片": "mp-common-profile",
    }
    for name, marker in components.items():
        if name == "H2 格式":
            ok = "PART_H2_STYLE" in html
        else:
            ok = marker in html
        if not ok:
            errors.append(f"缺少{name}组件")

    # 4. 关注卡片 data-id 存在性（biz 来自 profile.identity.biz_id）
    if "mp-common-profile" in html:
        m = re.search(r'<mp-common-profile[^>]*\bdata-id="([^"]*)"', html)
        if not (m and m.group(1).strip()):
            errors.append("关注卡片缺 data-id（公众号 biz 未注入，检查 profile.identity.biz_id）")

    # 5. 图片 data-local-path 检查
    all_imgs = re.findall(r'<img[^>]+>', html)
    missing_dlp = [img for img in all_imgs if 'data-local-path' not in img]
    # 排除推荐阅读卡片中的封面图（它们不需要 data-local-path）
    missing_dlp = [img for img in missing_dlp if 'logo-white' not in img and 'logo-black' not in img]
    if missing_dlp:
        warnings.append(f"{len(missing_dlp)} 个 <img> 缺少 data-local-path")

    # 6. 导读栏是否使用了默认文案
    if DEFAULT_LEAD_LINE1 in html and DEFAULT_LEAD_LINE2 in html:
        # 检查是否在导读栏区域
        lead_region = html[:html.find("PART_H2_STYLE") if "PART_H2_STYLE" in html else 5000]
        if DEFAULT_LEAD_LINE1 in lead_region:
            warnings.append("导读栏仍使用默认占位文案（深度拆解/硬核干货），建议用 --lead-line1/--lead-line2 自定义")

    # 7. 封面图标签是否残留在正文
    # 2026-04-23 收紧：只匹配**本文相对路径**下的 cover（"素材/cover..."），
    # 排除推荐阅读卡片里其他文章的绝对路径 cover（.../<数据目录>/30-xxx/素材/cover.png）
    if re.search(r'<img[^>]*src="(?:\./)?素材[/\\]cover[^"/\\]*"', html, re.IGNORECASE):
        warnings.append("正文中残留本文封面图 <img> 标签（应删除，封面图在微信后台设置）")

    # 8. 表格单元格文字过长（表格内容须大模型精炼、非机械删词）
    long_cells = 0
    for td in re.findall(r'<td[^>]*>([\s\S]*?)</td>', html):
        txt = re.sub(r'<[^>]+>', '', td).strip()
        if len(txt) > 22:
            long_cells += 1
    if long_cells:
        warnings.append(
            f"{long_cells} 个表格单元格文字 >22 字，建议用大模型精炼缩减（保留信息、非机械删词），"
            f"避免手机端挤成多排；必要时配合 article-meta.yaml 的 table_widths 调列宽"
        )

    return errors, warnings


def print_check_results(errors, warnings):
    """打印自检结果，返回是否全部通过"""
    print("\n  ╔══════════════════════════════════════╗")
    print("  ║       预发布自检报告                 ║")
    print("  ╚══════════════════════════════════════╝")
    for e in errors:
        print(f"  ❌ {e}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    if not errors and not warnings:
        print("  ✅ 全部检查通过，可以发布")
    elif not errors:
        print(f"\n  ⚠️  {len(warnings)} 个警告（非阻塞），无错误")
    else:
        print(f"\n  ❌ {len(errors)} 个错误 + {len(warnings)} 个警告")
        print("  请修复所有 ❌ 后再发布")
    print()
    return len(errors) == 0


# ========================================
# ===== 【第 5 节】模块1 H2/H3 转换 =====
#  模块 1: H2 格式转换（PART 编号格式）
# ========================================

def _clean_h2_text(inner):
    """从 H2 标签内容中提取纯净标题文字"""
    text = re.sub(r"<[^>]+>", "", inner).strip()
    # 移除中文序号 "一、" "二、" 等
    text = re.sub(r"^[一二三四五六七八九十]+、\s*", "", text)
    # 移除阿拉伯序号 "1. " "2. " 等
    text = re.sub(r"^\d+\.\s*", "", text)
    # 移除 "PART 01｜" / "PART 02 | " / "part 1|" 等完整 PART 前缀
    # 触发场景：主笔在 MD 里手写 "## PART 01｜标题"，脚本会自动在左侧生成 "01/PART" 小块，
    # 若不剥离前缀则右侧主标题重复显示 "PART 01｜"（曾踩坑：手写 PART 前缀致主标题重复）
    text = re.sub(r"^PART\s*\d+\s*[|｜]?\s*", "", text, flags=re.IGNORECASE)
    # 移除 "01 | " "02｜" 等 PART 编号前缀
    text = re.sub(r"^\d+\s*[|｜]\s*", "", text)
    # 移除裸编号 "01 " "02 "（数字+空格，如 Markdown 中的 "## 01 标题"）。限制为至少2位数字，避免误删 "4 月"。
    text = re.sub(r"^\d{2,}\s+", "", text)
    return text


def _auto_split_h2_subtitle(text):
    """尝试从 H2 文本自动拆解 "副标题[分隔符]主标题" 结构。

    仅用在 article-meta.yaml 未配置 part_subtitles 时的兜底。
    为避免误伤，只匹配中文语境下高辨识度的分隔符，且对左右两段长度有约束。

    支持的分隔符（按优先级）：
    - 中文全角冒号 "："
    - 中文长破折号 "——"
    - 中文单破折号 "—"
    - 中间点 " · "（前后带空格，避免误伤 "Dan·Koe" 这类名字）

    拆解约束：
    - 分隔符左侧 ≤ 10 个字符 且 非空（适合充当小字副标题）
    - 分隔符右侧 ≥ 2 个字符（主标题要有内容）

    返回：(主标题, 副标题) 或 (原文, None)
    """
    separators = [
        r"\s*：\s*",
        r"\s*——\s*",
        r"\s*—\s*",
        r"\s+·\s+",
    ]
    for pattern in separators:
        parts = re.split(pattern, text, maxsplit=1)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            if 1 <= len(left) <= 10 and len(right) >= 2:
                return right, left
    return text, None


def _build_part_h2(text, num, subtitle=None):
    """生成 PART 编号格式 H2

    Args:
        subtitle: 灰色副标题文字，None 则不显示副标题行
    """
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<section style="font-size: 12px; color: {TEXT_MUTED}; '
            f'letter-spacing: 1px; margin-top: 4px;">{subtitle}</section>'
        )
    # 把原始主标题写入注释，便于 _revert_part_h2 反向还原（修复 part_subtitles 后补无效的 bug）
    safe_text = text.replace("--", "-—").replace(">", "&gt;")
    return (
        f'<!-- PART_H2_STYLE:{safe_text} -->'
        f'<section style="margin: 40px 8px 20px; padding: 12px 0; '
        f'border-bottom: 1px solid rgba(47, 111, 143,0.12); overflow: hidden;">'
        f'<section style="float: left; min-width: 56px; text-align: center; '
        f'border-right: 2px solid rgba(47, 111, 143,0.3); padding-right: 14px; margin-right: 14px;">'
        f'<section style="font-size: 28px; font-weight: bold; color: {BRAND_PRIMARY}; line-height: 1;">{num}</section>'
        f'<section style="font-size: 11px; color: {BRAND_PRIMARY}; letter-spacing: 2px;">PART</section>'
        f'</section>'
        f'<section style="overflow: hidden;">'
        f'<section style="font-size: 18px; font-weight: bold; color: #333333; line-height: 1.3;">{text}</section>'
        f'{subtitle_html}'
        f'</section></section>'
    )


def _revert_part_h2(html):
    """把已转换的 PART HTML 块还原成裸 <h2>原文</h2>，便于 process_h2 二次跑时重建。

    触发场景：首次 --all 没有传 part_subtitles 导致 PART 缺副标题，
    后续在 article-meta.yaml 里补了 part_subtitles 再跑 --h2 时能重建。
    依赖 _build_part_h2 在注释里嵌入的原文：<!-- PART_H2_STYLE:原文 -->

    采用 section 平衡解析以精准切出整个 PART 块（内部嵌套 3 层 section）。
    """
    reverted = 0
    marker_re = re.compile(r'<!-- PART_H2_STYLE:([^>]*?) -->\s*<section', flags=re.IGNORECASE)

    while True:
        m = marker_re.search(html)
        if not m:
            break
        raw_text = m.group(1).replace("-—", "--").replace("&gt;", ">")
        start = m.start()
        section_start = m.start() + m.group(0).find('<section')

        depth = 0
        i = section_start
        while i < len(html):
            if html.startswith('<section', i):
                depth += 1
                i += len('<section')
            elif html.startswith('</section>', i):
                depth -= 1
                i += len('</section>')
                if depth == 0:
                    break
            else:
                i += 1

        if depth == 0:
            html = html[:start] + f'<h2>{raw_text}</h2>' + html[i:]
            reverted += 1
        else:
            # 结构异常，不强改，跳过这个 marker 避免死循环
            break

    if reverted > 0:
        log(f"🔁 已把 {reverted} 个已转换的 PART 块还原成裸 H2，将按当前 part_subtitles 重建")
    return html


def process_h2(html, part_subtitles=None):
    """将原生 <h2> 转换为 PART 编号格式。

    副标题解析优先级：
      1. article-meta.yaml / --part-subtitles 手动配置（按 PART 序号对齐）
      2. 从 H2 文本自动拆解 "副标题：主标题" 结构（见 _auto_split_h2_subtitle）
      3. 都没有则不显示副标题，并在日志里列出需要补齐的 PART 编号

    Args:
        html: HTML 内容
        part_subtitles: 各章节的灰色副标题列表，如 ["产品逻辑","行业变局"]

    **幂等性保证**：每次运行先把已转换的 PART 块还原成裸 H2，
    这样在 article-meta.yaml 补了 part_subtitles 后二次运行能真正重建副标题。
    """
    html = _revert_part_h2(html)

    # 2026-04-23 前置断言：H2 数 ≠ part_subtitles 长度就直接失败。
    # iron-rules 里已写但之前没在脚本里落实，导致作者增删 H2 后自己数不到。
    # 只在显式配置了 part_subtitles 时校验（没配的走自动拆解逻辑，不强校验）。
    subtitles = part_subtitles or []
    if subtitles:
        h2_count = len(re.findall(r"<h2\b[^>]*>", html, flags=re.IGNORECASE))
        if h2_count != len(subtitles):
            log(
                f"❌ H2 数量({h2_count}) ≠ part_subtitles 长度({len(subtitles)})，"
                f"请先在 article-meta.yaml 补齐副标题或调整 H2；"
                f"脚本现退出避免错位对齐。（铁律：H2 副标题预填）"
            )
            sys.exit(3)

    counter = [0]
    auto_split_count = [0]
    missing = []

    def replacer(match):
        inner = match.group(1)
        raw_text = _clean_h2_text(inner)
        counter[0] += 1
        num = f"{counter[0]:02d}"
        idx = counter[0] - 1

        manual_subtitle = subtitles[idx] if idx < len(subtitles) else None
        if manual_subtitle:
            text, subtitle = raw_text, manual_subtitle
        else:
            text, subtitle = _auto_split_h2_subtitle(raw_text)
            if subtitle:
                auto_split_count[0] += 1
            else:
                missing.append((counter[0], raw_text))

        return _build_part_h2(text, num, subtitle=subtitle)

    new_html, count = re.subn(r"<h2[^>]*>(.*?)</h2>", replacer, html, flags=re.DOTALL | re.IGNORECASE)
    html = new_html
    if count > 0:
        log(f"✅ 成功将 {count} 个原生 H2 转换为 PART 格式")
        if auto_split_count[0]:
            log(f"   ↳ 其中 {auto_split_count[0]} 个通过分隔符自动拆出了副标题")
        if missing:
            log(f"⚠️  {len(missing)} 个 H2 无副标题（文本不含分隔符且未配置 part_subtitles）：")
            for pnum, txt in missing:
                log(f"     PART {pnum:02d}: 「{txt}」")
            log("     如需补齐，请在 article-meta.yaml 的 part_subtitles 列表中按序填写")
    else:
        log("⏭️ 未发现原生 H2（可能已全部转换）")

    return html


def process_h3(html, style="timeline"):
    """将原生 <h3> 转换为时间线格式。

    视觉规范（H3=方、H4=圆，与有序列表徽章方圆对调）：
    - 主题色【圆角方块】(border-radius:6px, 24px) 内含白色序号数字（1, 2, 3...），按 PART/H2 分节重置
    - 标题文字为主题色粗体
    - 方块下方有浅灰短竖线，仅覆盖该 H3 自身内容段落，不延伸到下一个 H2/H3
    - 与 process_lists 的 H4 圆形编号徽章(20px, border-radius:50%)构成「方=H3 大、圆=H4 小」的层级
    """
    if style != "timeline":
        return html

    MARKER = '<!-- TIMELINE_H3_STYLE -->'
    if html.count(MARKER) > 0:
        log("⚠️ 检测到已有 H3 时间线格式，跳过转换 (避免混合)")
        return html

    # 匹配 H2/H3 和 PART 标记（PART 标记新增了原文后缀：<!-- PART_H2_STYLE:原文 -->），
    # 同时把两个 H3 之间的内容作为独立片段
    parts = re.split(r'(<h[23][^>]*>.*?</h[23]>|<!-- PART_H2_STYLE[^>]*-->)', html, flags=re.DOTALL | re.IGNORECASE)
    result = []
    open_section = False   # 是否有未关闭的 H3 内容 section
    converted = 0
    section_num = 0  # 当前 PART 内的 H3 编号，遇到新 H2/PART 时重置

    def _clean_h3(text):
        """剥离 H3 文本里手写的编号前缀，避免与时间线方块序号重复。
        触发场景：主笔在 MD 里手写 "### 一、独立的侧边栏 UI"，脚本左侧自动生成绿圆角方块
        "1"，若不剥离 "一、" 则视觉上变成 "①一、独立的侧边栏 UI"（曾踩坑）。
        """
        t = re.sub(r'<[^>]+>', '', text).strip()
        # 圈号 ①②③
        t = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
        # 阿拉伯数字 "1. " "2. " 等
        t = re.sub(r'^\d+\.\s*', '', t)
        # 中文数字 + 顿号 "一、" "二、" 等（包括十/十一/十二）
        t = re.sub(r'^[一二三四五六七八九十]+、\s*', '', t)
        # 全角/半角括号编号 "(1)" "（1）" "（一）"
        t = re.sub(r'^[（(]\s*[\d一二三四五六七八九十]+\s*[)）]\s*', '', t)
        # 裸阿拉伯数字 + 空格 "1 标题"（限制 ≥2 位数字防误伤 "4 月"）
        t = re.sub(r'^\d{2,}\s+', '', t)
        return t

    for part in parts:
        if re.match(r'<h3[^>]*>.*?</h3>', part, flags=re.DOTALL | re.IGNORECASE):
            # 遇到新 H3 前，先关闭上一个 H3 的内容区
            if open_section:
                result.append('</section></section>')
            inner = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\1', part, flags=re.DOTALL | re.IGNORECASE)
            text = _clean_h3(inner)
            converted += 1
            section_num += 1
            num = section_num

            card = (
                f'{MARKER}'
                f'<section style="margin: 28px 8px 0; margin-left: 12px;">'
                # 标题行：圆角方块 + 绿色粗体标题（不带竖线）
                f'<section style="line-height: 24px; margin-bottom: 0; padding-left: 18px;">'
                f'<span style="display: inline-block; width: 24px; height: 24px; min-width: 24px; min-height: 24px; '
                f'background-color: {BRAND_PRIMARY}; border-radius: {RADIUS_SM}; '
                f'text-align: center; line-height: 24px; '
                f'color: #ffffff; font-size: 13px; font-weight: bold; '
                f'vertical-align: middle; margin-left: -30px; margin-right: 8px;">{num}</span>'
                f'<span style="font-size: 16px; font-weight: bold; '
                f'color: {BRAND_PRIMARY}; vertical-align: middle;">{text}</span>'
                f'</section>'
                # 暂时不无脑注入带有 border-left 的容器，等待后面处理正文内容时再包裹
            )
            result.append(card)
            open_section = True
        elif re.match(r'<h2[^>]*>.*?</h2>', part, flags=re.DOTALL | re.IGNORECASE) or part.startswith('<!-- PART_H2_STYLE'):
            # 遇到新的 H2 或 PART 大标题，关闭上一个 H3 section 并重置编号
            if open_section:
                result.append('</section></section>')
                open_section = False
            section_num = 0  # 🔑 每个 PART 内的 H3 编号从 1 重新开始
            result.append(part)
        else:
            if open_section:
                # 寻找第一个会打断时间线的块级元素（带有图片的外层标签或表格标签）
                break_pattern = r'(<(p|section|figure|div)[^>]*>[\s\n]*(?:<a[^>]*>[\s\n]*)?<img[^>]*>|<table[^>]*>|<section[^>]*>[\s\n]*<table)'
                match = re.search(break_pattern, part, flags=re.DOTALL | re.IGNORECASE)
                
                content_template = '<section style="border-left: 2px solid ' + LINE_TIMELINE + '; padding-left: 18px; margin-top: 6px; padding-bottom: 2px;">{content}</section>'
                
                if match:
                    cut_pos = match.start()
                    pre_text = part[:cut_pos]
                    
                    # 如果表格前有实际文本，包裹内容并添加左侧竖线
                    if pre_text.strip():
                        result.append(content_template.format(content=pre_text))
                    
                    # 截断时间线（闭合 H3 最外层的 section）
                    result.append('</section>')
                    open_section = False
                    
                    # 追加截断位置及其之后的所有内容（包含表格/图片及后续补充说明），此处不在时间线内
                    result.append(part[cut_pos:])
                else:
                    # 没有打断元素，如果存在实际内容，则全包裹进竖线容器
                    if part.strip():
                        result.append(content_template.format(content=part))
            else:
                result.append(part)

    if open_section:
        result.append('</section>')

    if converted > 0:
        log(f"✅ 成功将 {converted} 个原生 H3 转换为时间线格式（圆角方块编号+绿标题+浅灰竖线，按 PART 分节独立编号）")
    else:
        log("⏭️ 未发现原生 H3")

    return ''.join(result)


# ===== 【第 6 节】模块2 表格品牌化 =====
# ========================================
#  模块 2: 表格品牌化
# ========================================
def _char_weight(text: str) -> int:
    w = 0
    for ch in text:
        w += 2 if ord(ch) > 127 else 1
    return w


def _compute_column_widths(table_body: str, ncols: int) -> list:
    """按每列最长单元格的字符权重（汉字×2, ASCII×1）分配宽度，clamp 到 [12%, 55%]。
    兼容 baoyu 输出里 `<thead><th>…</th><th>…</th></thead>`（无 <tr> 包裹）的情况。
    """
    col_max = [0] * ncols
    # 同时匹配 <thead>…</thead> 与 <tr>…</tr> 两种"一行"的容器
    for block in re.finditer(
        r"<thead[^>]*>(.*?)</thead>|<tr[^>]*>(.*?)</tr>",
        table_body, flags=re.DOTALL,
    ):
        inner = block.group(1) if block.group(1) is not None else block.group(2)
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", inner, flags=re.DOTALL)
        for i, cell in enumerate(cells[:ncols]):
            text = re.sub(r"<[^>]+>", "", cell).strip()
            col_max[i] = max(col_max[i], _char_weight(text))
    if sum(col_max) == 0:
        base = 100 // ncols
        widths = [base] * (ncols - 1) + [100 - base * (ncols - 1)]
        return [f"{w}%" for w in widths]
    # 平方根阻尼分配（踩坑修正）：
    # 旧版按字符权重「线性」分配——某一长内容列（如三列表的「怎么考」34 字）会按比例
    # 独吞 ~55%，把短表头列（「考试」「本质」2 字）starve 到内容挤成 3-4 排。
    # 改用 sqrt(权重) 压缩列间差距：长列仍稍宽但不霸屏，短列拿到够用的最低宽度。
    # 实测三列表 28/44/28（旧 20/55/22）、两列表自然落到 ~33/67~40/60，符合规范。
    import math
    weights = [math.sqrt(max(w, 1)) for w in col_max]
    total = sum(weights)
    raw = [w / total * 100 for w in weights]
    MIN, MAX = 15, 52
    clamped = [max(MIN, min(MAX, v)) for v in raw]
    s = sum(clamped)
    clamped = [v * 100 / s for v in clamped]
    widths = [round(v) for v in clamped[:-1]]
    widths.append(100 - sum(widths))
    return [f"{w}%" for w in widths]


# 横滑表模式的版面常量（多列表缩 11px + 一屏放不下则横滑）
_TABLE_BODY_PX = 345    # 微信正文可用宽度(粗略)：列 px 总和 ≤ 此值 → 放得下、宽 100% 不横滑
_TABLE_MIN_COL_PX = 88  # 11px 字号下一列的基准宽；决定 3 列放得下、≥4 列触发横滑


def _scroll_col_px(table_body: str, ncols: int, ov=None) -> list:
    """≥3 列横滑模式的每列像素宽 list[int]。
    有列宽覆盖(ov, 形如 ['24%','39%',...])则按其比例；否则按各列最长内容的
    sqrt 权重分配，基准画布 = ncols × _TABLE_MIN_COL_PX（每列 ~88px 起步、长列稍宽）。
    与 _compute_column_widths 同源思路（sqrt 阻尼），差异仅在输出 px 而非 %。
    """
    import math
    if ov:
        try:
            weights = [float(str(x).replace("%", "").strip()) for x in ov]
        except (ValueError, TypeError):
            weights = [1.0] * ncols
    else:
        col_max = [0] * ncols
        for block in re.finditer(
            r"<thead[^>]*>(.*?)</thead>|<tr[^>]*>(.*?)</tr>",
            table_body, flags=re.DOTALL,
        ):
            inner = block.group(1) if block.group(1) is not None else block.group(2)
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", inner, flags=re.DOTALL)
            for i, cell in enumerate(cells[:ncols]):
                text = re.sub(r"<[^>]+>", "", cell).strip()
                col_max[i] = max(col_max[i], _char_weight(text))
        weights = [math.sqrt(max(w, 1)) for w in col_max]
    total_w = sum(weights) or ncols
    canvas = ncols * _TABLE_MIN_COL_PX
    return [max(72, round(w / total_w * canvas)) for w in weights]


def _is_term_table(table_body: str) -> bool:
    """判断 2 列表是否为「术语|释义」型（宜转术语卡，2026-07-07 案例二）：
    ≥2 个数据行，左列短(术语，权重≤22≈11 CJK)、右列长(释义，权重≥30≈15 CJK)，
    且右列显著长于左列(≥1.6×)。数据型对称表（如 季度|营收）不命中，保持表格。
    仅统计 <td> 数据行（跳过表头 <th>）。
    """
    c1max = c2max = 0
    n = 0
    for r in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", table_body, flags=re.DOTALL):
        tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", r, flags=re.DOTALL)
        if len(tds) != 2:
            continue
        t1 = re.sub(r"<[^>]+>", "", tds[0]).strip()
        t2 = re.sub(r"<[^>]+>", "", tds[1]).strip()
        c1max = max(c1max, _char_weight(t1))
        c2max = max(c2max, _char_weight(t2))
        n += 1
    if n < 2:
        return False
    return c2max >= 30 and c1max <= 22 and c2max >= c1max * 1.6


def _render_term_cards(table_body: str) -> str:
    """把 2 列术语表渲染为一组「术语卡」（左竖条 + 加粗术语 + 释义），绕开表格。
    仅取 <td> 数据行（跳过表头 <th>）。样式仅用 design-tokens，theme-ready 零硬编码色。
    """
    cards = []
    for r in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", table_body, flags=re.DOTALL):
        tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", r, flags=re.DOTALL)
        if len(tds) != 2:
            continue
        term = tds[0].strip()
        desc = tds[1].strip()
        # 术语标题本就加粗，剥掉整包的 <strong>/<b> 免双重加粗
        term = re.sub(r"^<(strong|b)>([\s\S]*)</\1>$", r"\2", term).strip()
        cards.append(
            f'<section style="border-left: 3px solid {BRAND_PRIMARY}; '
            f'background: {TINT_SOFT}; border-radius: 0 {RADIUS_MEDIA} {RADIUS_MEDIA} 0; '
            f'padding: 10px 14px; margin-bottom: 8px;">'
            f'<p style="margin: 0 0 4px; font-size: 15px; font-weight: bold; '
            f'color: {TEXT_TITLE};">{term}</p>'
            f'<p style="margin: 0; font-size: 14px; line-height: 1.75; '
            f'color: {TEXT_BODY};">{desc}</p>'
            f'</section>'
        )
    return f'<section style="margin: 0 8px 0.8em;">{"".join(cards)}</section>'


def process_table(html, table_widths=None):
    """
    完整的表格品牌化处理（对齐 layout.md 规范）：
    1. 表头 → 主题色背景 + 白字 + 居中（13px 加粗），无单元格边框
    2. 数据行 → border-bottom 分隔线（非四边框）+ 交替行色（12px，比表头小一号）
    3. 注入列宽（写进首行单元格，微信安全；优先用大模型测算的 table_widths 覆盖）
    4. 外层圆角容器（border + border-radius + overflow:hidden）
    5. 清理 baoyu 生成的多余 wrapper section（修复空白行）
    6. 清理 <thead> 上的多余 inline style

    Args:
        table_widths: 可选，来自 article-meta.yaml 的「每个内容表一组列宽」列表，
            按表在文中出现顺序对齐，例：[[38,62],[26,46,28]]。
            列宽改由大模型按内容测算的固定值提供（更协调），
            脚本 `_compute_column_widths` 的 sqrt 启发式降级为兜底（无覆盖时才用）。
    """
    changes = 0

    # 列宽覆盖：按表在文中出现顺序消费 table_widths 的每一组；归一化为 ['x%',...]
    _tbl_idx = [0]

    def _override_widths(ncols):
        """取当前表的列宽覆盖并归一化为 ['x%',...]；无覆盖 / 列数不符返回 None（走兜底）。"""
        if not table_widths or _tbl_idx[0] >= len(table_widths):
            return None
        raw = table_widths[_tbl_idx[0]]
        if not isinstance(raw, (list, tuple)) or len(raw) != ncols:
            return None
        try:
            nums = [float(str(x).replace('%', '').strip()) for x in raw]
        except (ValueError, TypeError):
            return None
        s = sum(nums)
        if s <= 0:
            return None
        pct = [round(v * 100 / s) for v in nums]
        pct[-1] = 100 - sum(pct[:-1])  # 末列吸收四舍五入余量，保证和为 100
        return [f"{p}%" for p in pct]

    # 1. 旧版表头背景色兼容替换
    html, c = re.subn(
        r"background:\s*rgba\(0,\s*0,\s*0,\s*0\.05\)",
        f"background-color: {BRAND_PRIMARY}; color: #fff",
        html,
    )
    changes += c

    # 2. 重写每个 <th>：主题色背景 + 白字，无边框
    def fix_th(m):
        tag_content = m.group(0)
        new_style = (
            f"padding: 8px 6px; "
            f"background-color: {BRAND_PRIMARY}; color: #fff; "
            f"font-size: 13px; line-height: 1.4; text-align: center; font-weight: bold;"
        )
        if 'style="' in tag_content:
            return re.sub(r'style="[^"]*"', f'style="{new_style}"', tag_content)
        else:
            return tag_content.replace("<th", f'<th style="{new_style}"', 1)

    # 🔴 正则必须用 `<th(?:\s[^>]*)?>` 而非 `<th[^>]*>`：后者会把 `<thead>` 也匹配上
    # （`<th`+`ead`+`>`），fix_th 无 style 分支会把它改成 `<th style="绿底">ead>`——
    # 一个无宽度的幽灵绿 th 挤在真表头行前，渲染成「第一列多出一截、颜色高一阶」的鬼影
    # （2026-06-26 排查：旧 step5 的 `<thead style=...>` 清理对不上这种坏形，漏网）。
    # `<th(?:\s[^>]*)?>` 只匹配 `<th>` 与 `<th 属性...>`，不碰 `<thead>`/`<thead style=...>`。
    html_new = re.sub(r"<th(?:\s[^>]*)?>", fix_th, html)
    if html_new != html:
        changes += 1
    html = html_new

    # 3. 重写每个 <td>：只有 border-bottom 做行分隔
    def fix_td(m):
        tag_content = m.group(0)
        new_style = (
            "padding: 8px 6px; "
            f"border-bottom: 1px solid {BORDER_HAIR}; "
            f"color: {TEXT_BODY}; font-size: 12px; line-height: 1.4; text-align: left;"
        )
        if 'style="' in tag_content:
            return re.sub(r'style="[^"]*"', f'style="{new_style}"', tag_content)
        else:
            return tag_content.replace("<td", f'<td style="{new_style}"', 1)

    html_new = re.sub(r"<td[^>]*>", fix_td, html)
    if html_new != html:
        changes += 1
    html = html_new

    # 4. 交替行色：偶数 <tr> 的所有 <td> 加极浅绿背景
    def add_alternating_rows(table_html):
        # 优先处理 tbody 区域；若无 tbody 则处理 thead 之后的所有 tr
        tbody_match = re.search(r"<tbody>(.*?)</tbody>", table_html, re.DOTALL)
        if not tbody_match:
            # 无 tbody：跳过 thead 内的行，处理剩余 tr
            thead_end = re.search(r"</thead>", table_html)
            if not thead_end:
                return table_html
            tbody_start = thead_end.end()
            tbody_end = len(table_html)
            tbody_content = table_html[tbody_start:tbody_end]
        else:
            tbody_start = tbody_match.start(1)
            tbody_end = tbody_match.end(1)
            tbody_content = tbody_match.group(1)

        row_idx = 0
        def color_row(m):
            nonlocal row_idx
            row_idx += 1
            row_html = m.group(0)
            if row_idx % 2 == 0:
                # 偶数行：给每个 td 追加 background-color
                row_html = re.sub(
                    r'(<td[^>]*style=")',
                    rf'\1background-color: {TINT_ROW}; ',
                    row_html,
                )
            return row_html

        new_tbody = re.sub(r"<tr[^>]*>.*?</tr>", color_row, tbody_content, flags=re.DOTALL)
        return table_html[:tbody_start] + new_tbody + table_html[tbody_end:]

    # 5. 清理 <thead> 上的多余 inline style（baoyu 转换器会把 cell 样式误加到 thead 上）
    html = re.sub(r'<thead\s+style="[^"]*">', '<thead>', html)

    # 6. 注入列宽 + 外层容器（2026-07-07 按列数/内容路由：术语卡 / 横滑 11px / 改良表 12px）
    def _inject_first_row_widths(tbody, frow_inner, widths):
        """把 widths（['x%'..] 或 ['88px'..]）写进首行每个单元格；返回新 table_body。
        微信忽略/误渲 colgroup 会在表头冒虚线空行，故宽度直接写进首行单元格。"""
        cells = re.split(r'(</t[hd]>)', frow_inner)
        new_inner = ""
        cell_idx = 0
        for i in range(0, len(cells) - 1, 2):
            cell_open = cells[i]
            cell_close = cells[i + 1]
            w = widths[cell_idx] if cell_idx < len(widths) else "auto"
            if 'style="' in cell_open:
                cell_open = re.sub(r'style="([^"]*)"', f'style="width: {w}; \\1"', cell_open)
            else:
                cell_open = cell_open.replace(">", f' style="width: {w};">', 1)
            new_inner += cell_open + cell_close
            cell_idx += 1
        new_inner += cells[-1]  # trailing empty string or text
        return tbody.replace(frow_inner, new_inner, 1)

    def inject_colgroup_and_wrapper(m):
        full_match = m.group(0)
        table_body = m.group(2)

        # 跳过已处理的表格（外层已有圆角容器）和布局表格（推荐阅读卡片等）
        # 哨兵值必须与 wrapper 的 RADIUS_CARD 同步，否则二次跑检测不到已处理表→重复包裹
        if f"border-radius: {RADIUS_CARD}" in full_match or "border: none" in full_match:
            return full_match

        # 如已有 colgroup 就跳过注入列宽，但仍需重写 table 样式
        has_colgroup = "<colgroup" in table_body

        # 统计列数
        first_row = re.search(r"<tr[^>]*>(.*?)</tr>", table_body, re.DOTALL)
        if not first_row:
            return m.group(0)
        ncols = len(re.findall(r"<t[hd][\s>]", first_row.group(1)))
        if ncols < 2:
            return m.group(0)

        # 列宽覆盖 + 消费索引：每处理一个内容表按文中顺序消费一组（保持原行为：
        # 仅在非 colgroup 表上消费/注入宽度）。三条路由都在此点之后分派，索引不重复消费。
        ov = None
        if not has_colgroup:
            ov = _override_widths(ncols)
            _tbl_idx[0] += 1

        # ---- 路由 A：2 列「术语|释义」型 → 术语卡（绕开表格，2026-07-07 案例二）----
        # 有列宽覆盖=作者显式要表格呈现，不转卡；colgroup 表不转。
        if ncols == 2 and not has_colgroup and ov is None and _is_term_table(table_body):
            return _render_term_cards(table_body)

        # ---- 路由 B：≥3 列 → 11px 横滑；能放下宽 100%(不滚)，放不下 overflow-x 横滑
        #      （2026-07-07 案例一：缩字号 + 一屏尽量多列，列多/内容长则横滑查看）----
        if ncols >= 3:
            col_px = _scroll_col_px(table_body, ncols, ov)
            total_px = sum(col_px)
            fits = total_px <= _TABLE_BODY_PX
            if fits:
                # 放得下：按 px 比例转 % 填满、表宽 100%（不触发滚动）
                s = total_px or ncols
                pct = [round(p * 100 / s) for p in col_px]
                pct[-1] = 100 - sum(pct[:-1])  # 末列吸收余量，和为 100
                widths = [f"{p}%" for p in pct]
                table_width = "100%"
            else:
                widths = [f"{p}px" for p in col_px]
                table_width = f"{total_px}px"
            if not has_colgroup:
                table_body = _inject_first_row_widths(table_body, first_row.group(1), widths)
            # 缩字号到 11px（td 12→11 先、th 13→12 后，避免 13→12→11 链式误改）+ 收紧 padding
            table_body = table_body.replace("font-size: 12px", "font-size: 11px")
            table_body = table_body.replace("font-size: 13px", "font-size: 12px")
            table_body = table_body.replace("padding: 8px 6px", "padding: 6px 7px")
            new_table_tag = (
                f'<table style="width: {table_width}; table-layout: fixed; word-wrap: break-word; '
                'margin: 0; border-collapse: separate; border-spacing: 0; '
                'font-size: 11px; line-height: 1.45;">'
            )
            inner = add_alternating_rows(f"{new_table_tag}{table_body}</table>")
            overflow = "overflow-x: auto" if not fits else "overflow: hidden"
            return (
                f'<section style="border-radius: {RADIUS_CARD}; {overflow}; '
                f'border: 1px solid {BORDER_CARD}; margin: 0 8px 0.8em;">'
                f'{inner}</section>'
            )

        # ---- 路由 C：2 列常规 → 保留改良表（12px，百分比宽度填满）----
        widths = ov or _compute_column_widths(table_body, ncols)
        if not has_colgroup:
            table_body = _inject_first_row_widths(table_body, first_row.group(1), widths)
        new_table_tag = (
            '<table style="width: 100%; table-layout: fixed; word-wrap: break-word; margin: 0; '
            'border-collapse: separate; border-spacing: 0; font-size: 12px; line-height: 1.4;">'
        )
        inner = add_alternating_rows(f"{new_table_tag}{table_body}</table>")
        return (
            f'<section style="border-radius: {RADIUS_CARD}; overflow: hidden; '
            f'border: 1px solid {BORDER_CARD}; margin: 0 8px 0.8em;">'
            f'{inner}</section>'
        )

    # 7. 匹配 baoyu wrapper section + 内部 table，一次性替换
    #    baoyu 会生成：<section style="font-family:...; overflow: auto;"><table ...>...</table></section>
    #    外层 section 的 line-height:1.75 + 空白字符 → 渲染出空行
    #    这里直接把 wrapper+table 整体替换为 inject 处理后的结果
    def replace_wrapped_table(m):
        table_match = re.search(r"(<table[^>]*>)(.*?)</table>", m.group(1), re.DOTALL)
        if not table_match:
            return m.group(0)
        return inject_colgroup_and_wrapper(table_match)

    html = re.sub(
        r'<section style="font-family:[^"]*overflow:\s*auto;">\s*(.*?)</section>',
        replace_wrapped_table,
        html,
        flags=re.DOTALL,
    )

    # 处理未被 baoyu wrapper 包裹的独立 table（兜底）
    # 需要检查 table 前方是否已有我们的圆角容器，防止二次包裹
    # 🔴 2026-07-07：must 同时认 `overflow: hidden`(放得下) 与 `overflow-x: auto`(横滑)
    #    两种 wrapper——否则横滑表经 replace_wrapped_table 包一层后，本兜底因只认
    #    `overflow: hidden` 漏检、又包一层 → 双 section 双边框（真机暴露过）。
    #    统一判 `border-radius:10px; overflow`（radius 紧跟 overflow，够specific 防误跳）。
    def fallback_wrapper(m):
        start = m.start()
        preceding = html_snapshot[max(0, start - 120):start]
        if f"border-radius: {RADIUS_CARD}; overflow" in preceding:
            return m.group(0)  # 已有外层容器（hidden 或 -x:auto），跳过
        return inject_colgroup_and_wrapper(m)

    html_snapshot = html  # 闭包引用，用于检查前方上下文
    html = re.sub(
        r"(<table[^>]*>)(.*?)</table>",
        fallback_wrapper,
        html,
        flags=re.DOTALL,
    )

    if changes > 0 or True:
        log("✅ 表格品牌化完成（绿头/行分隔线/交替行色/圆角容器/空行修复）")
    return html


# ========================================
# ===== 【第 7 节】模块3 导读栏注入 =====
#  模块 3: 导读栏注入
# ========================================
LEAD_START_MARKER = "<!-- LEAD-SECTION-START -->"
LEAD_END_MARKER = "<!-- LEAD-SECTION-END -->"


def _purge_existing_lead(html: str) -> tuple:
    """删除所有已存在的导读栏实例（防止堆叠）。返回 (new_html, purged_count)。

    按顺序尝试：
      1) 带 LEAD-SECTION-START/END 注释锚点的块（新版）
      2) 含 `logo-white.png` 引用的最外层 <section>（兼容旧版）
    """
    purged = 0

    # 新版锚点
    pat = re.compile(
        re.escape(LEAD_START_MARKER) + r"[\s\S]*?" + re.escape(LEAD_END_MARKER),
        flags=re.MULTILINE,
    )
    new_html, n = pat.subn("", html)
    purged += n

    # 兼容：老版本无锚点，靠 logo-white.png 定位最外层 section
    # 模板固定以 `<section style="margin: 16px auto; border-radius: 12px; overflow: hidden; border: 1px solid #eef0f2;` 起头
    legacy_start = '<section style="margin: 16px auto; border-radius: 12px; overflow: hidden; border: 1px solid #eef0f2;'
    while legacy_start in new_html and "logo-white.png" in new_html:
        start_idx = new_html.find(legacy_start)
        if start_idx == -1:
            break
        # 从 start_idx 开始平衡 <section>/</section>
        depth = 0
        i = start_idx
        found_logo = False
        while i < len(new_html):
            if new_html.startswith("<section", i):
                depth += 1
                i += len("<section")
            elif new_html.startswith("</section>", i):
                depth -= 1
                i += len("</section>")
                if depth == 0:
                    break
            else:
                if new_html.startswith("logo-white.png", i):
                    found_logo = True
                i += 1
        if depth == 0 and found_logo:
            new_html = new_html[:start_idx] + new_html[i:]
            purged += 1
        else:
            break

    return new_html, purged


def _purge_orphan_hero_in_body(html):
    """删除正文里散落的 hero.png 引用——hero 的唯一合法位置是导读栏（由 process_lead 自动注入）。

    触发场景：作者在 .md 里手动写了 ![导读图](素材/hero.png)，
    经 markdown→html 转换后变成 <p><img src="素材/hero.png" ...></p>，
    会与导读栏内的 hero 图重复展示（曾踩坑：正文手嵌 hero 与导读栏重复）。

    注意：必须在 _purge_existing_lead 之后、process_lead 重新注入导读栏之前调用，
    避免误清导读栏内的合法 hero。
    """
    # 匹配独立段落的 hero 图（<p>...<img src="...hero...png"...></p>）
    pattern = re.compile(
        r'<p[^>]*>\s*(?:<a[^>]*>\s*)?<img[^>]*src="[^"]*hero[^"]*\.png"[^>]*>(?:\s*</a>)?\s*</p>',
        flags=re.IGNORECASE,
    )
    new_html, n = pattern.subn('', html)
    if n > 0:
        log(f"🧹 已清理正文中 {n} 处散落的 hero 图引用（hero 仅在导读栏出现，禁止 .md 里手动嵌入）")
    return new_html


def _strip_body_h1(html):
    """删除正文里的 <h1> 标题 —— 本 skill 正文**从不用 H1**（标题走 frontmatter / 公众号标题栏）。

    触发场景（多次反馈"开篇标题重复 + 一道横杠"）：主笔在 .md 里写了 `# 标题`
    （常与 frontmatter title 一字不差），经 baoyu-md `--keep-title` 转换后留在正文，渲染成带底部横杠的
    大标题，与公众号文章自带的标题栏重复。正文层级只用 `## PART` / `### 时间线`，H1 一律剥。
    """
    pattern = re.compile(r'<h1[^>]*>.*?</h1>\s*', flags=re.IGNORECASE | re.DOTALL)
    new_html, n = pattern.subn('', html)
    if n > 0:
        log(f"🧹 已剥离正文中 {n} 处 <h1> 标题（正文不用 H1；避免与公众号标题重复 + 横杠，标题走 frontmatter）")
    return new_html


def process_lead(html, cwd, args):
    """注入导读栏卡片到 div#output 内部最前面。
    强制幂等：每次执行都会先 purge 所有已存在实例，再重注入（确保文案最新）。
    """

    # 🔴 2026-04 变更：不再 "检测到就跳过"，改为 "强制 purge + 重注入"
    # 理由：老逻辑遇到文案更新、图片更换时不会重刷；
    # 多轮排版时旧模板残留也会堆叠成两份（复盘问题 #5）
    html, purged = _purge_existing_lead(html)
    if purged > 0:
        log(f"🧹 已清理 {purged} 份旧导读栏")

    # 🔴 2026-04-22 新增：清正文里手动嵌的 hero 图，避免与导读栏内的 hero 重复
    html = _purge_orphan_hero_in_body(html)

    # 🔴 剥正文里的 <h1>（与公众号标题重复 + 横杠）
    html = _strip_body_h1(html)

    tmpl_path = TEMPLATES_DIR / "lead-section.html"
    if not tmpl_path.exists():
        log(f"❌ 导读栏模板不存在: {tmpl_path}")
        return html

    # 模板底栏硬引用 素材/logo-white.png；缺失时从 profile 品牌 logo 自动补齐，
    # 否则发布后导读栏 logo 裂图（verify layout 会拦，但历史上每篇都靠手工拷贝）
    logo_dst = Path(cwd) / "素材" / "logo-white.png"
    if not logo_dst.exists():
        try:
            import profile_config as _pc
            logo_src = Path(_pc.profile_dir()) / "brand" / "logo.png"
            if logo_src.exists():
                import shutil
                logo_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(logo_src, logo_dst)
                log("🧩 已从 profile/brand/logo.png 补齐 素材/logo-white.png（导读栏底栏用）")
            else:
                log("⚠️ 素材/logo-white.png 缺失且 profile 无 brand/logo.png——导读栏底栏 logo 将裂图")
        except Exception as e:
            log(f"⚠️ 自动补齐 logo-white.png 失败：{e}")

    lead = tmpl_path.read_text(encoding="utf-8")

    # 从命令行参数或默认值填充变量
    line1 = getattr(args, "lead_line1", None) or "深度拆解"
    line2 = getattr(args, "lead_line2", None) or "硬核干货"
    subtitle = getattr(args, "lead_subtitle", None) or "一篇看懂核心要素与底层逻辑"
    tag1 = getattr(args, "lead_tag1", None) or "技术评测"
    tag2 = getattr(args, "lead_tag2", None) or "干货实测"

    # 如果全部使用默认值，给出警告
    if not any([getattr(args, "lead_line1", None), getattr(args, "lead_line2", None),
                getattr(args, "lead_subtitle", None)]):
        log("⚠️ 导读栏使用通用默认文案，发布前请传 --lead-line1/--lead-line2/--lead-subtitle 自定义")

    lead = lead.replace("{{HERO_LINE1}}", line1)
    lead = lead.replace("{{HERO_LINE2}}", line2)
    lead = lead.replace("{{HERO_SUBTITLE}}", subtitle)
    lead = lead.replace("{{TAG_1}}", tag1)
    lead = lead.replace("{{TAG_2}}", tag2)

    # Hero 图片：使用素材目录下的 hero 图
    hero_files = list(Path(cwd).glob("素材/hero*.png"))
    if hero_files:
        hero_rel = f"素材/{hero_files[0].name}"
        hero_abs = str(hero_files[0])
    else:
        hero_rel = "素材/hero.png"
        hero_abs = os.path.join(cwd, "素材", "hero.png")

    lead = lead.replace(
        '<img src="{{HERO_IMAGE_URL}}"',
        f'<img src="{hero_rel}" data-local-path="{hero_abs}"',
    )

    # 用 LEAD-SECTION-START/END 注释锚点包裹，方便下次 purge
    wrapped_lead = f"{LEAD_START_MARKER}\n{lead}\n{LEAD_END_MARKER}"
    new_html = html.replace('<div id="output">', f'<div id="output">\n{wrapped_lead}', 1)
    if new_html != html:
        log("✅ 导读栏已注入到 div#output 内最前面（带 purge 锚点）")

    # ============================================================
    # 🎵 音乐栏前置（2026-06-18 BGM 复活，引擎 MiniMax）
    # ------------------------------------------------------------
    # generate_article_bgm.py 把 AUDIO-CARD 块追加在 定稿.md 末尾；排版时
    # 这里把它上移到导读栏（Hero 图）下方渲染（满足「卡片在导读后、正文前」版式）。
    # ============================================================
    audio_card_match = re.search(r'<!-- AUDIO-CARD-START -->[\s\S]*?<!-- AUDIO-CARD-END -->', new_html)
    if audio_card_match:
        audio_card = audio_card_match.group(0)
        new_html = new_html.replace(audio_card, '')
        new_html = new_html.replace(wrapped_lead, f'{wrapped_lead}\n{audio_card}\n', 1)
        log("✅ 音乐栏已前置至导读栏（Hero图）下方")

    return new_html


# ========================================
# ===== 【第 8 节】模块4 底部推荐+名片 =====
#  模块 4: 底部推荐阅读 + 关注名片
# ========================================
def process_footer(html):
    """注入推荐阅读 + 关注卡片到 </div></body> 之前。
    注意：generate_recommend_html.py 的输出已经包含关注卡片，
    所以此处不再重复注入。
    """

    # 幂等检查：全文搜索关注卡片标识
    if "mp-common-profile" in html:
        log("⏭️ 关注名片已在尾部，跳过")
        return html

    # 先运行 generate_recommend_html.py 更新推荐列表
    gen_script = SCRIPT_DIR / "generate_recommend_html.py"
    # 产物落数据目录（SEP-10 修复：它渲染的是你的真实身份卡+文章清单，属个人数据，
    # 不该写进公开仓工作树的 templates/——那里只放中性模板）
    from profile_config import data_dir as _data_dir
    recommend_file = _data_dir() / "recommend_articles.html"

    if gen_script.exists():
        log("正在调用 generate_recommend_html.py 生成最新推荐...")
        result = subprocess.run(
            [sys.executable, str(gen_script), "html"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            # 🔴 强制子进程以 UTF-8 输出。否则 Windows GBK 下
            # generate_recommend_html.py 的 stdout 是 GBK 字节，父进程按 utf-8 解码会
            # UnicodeDecodeError(0xd5) → 被误判 returncode!=0 → 静默跳过文末关注卡片。
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            cwd=str(SCRIPT_DIR),
        )
        if result.returncode != 0:
            # 🔴 生成失败时绝不读取 recommend_articles.html —— 它可能是上一篇文章
            # 留下的陈旧产物，会把别人的推荐卡片贴进本篇。大声报错 + 跳过注入，
            # 把现场暴露给编排器/操作者修复后重跑（fail-fast，不静默贴错内容）。
            err = (result.stderr or result.stdout or "").strip()
            log(
                f"❌ generate_recommend_html.py 失败（returncode={result.returncode}）"
                f"，跳过推荐阅读 + 关注卡片注入以避免贴入陈旧推荐。stderr: {err[:300]}"
            )
            return html

    footer_html = ""
    if recommend_file.exists():
        footer_html = recommend_file.read_text(encoding="utf-8")
        log(f"✅ 已读取推荐阅读 HTML（{len(footer_html)} 字符）")
    else:
        log("⚠️ 未找到 recommend_articles.html，跳过推荐阅读")

    # generate_recommend_html.py 已内含关注卡片，无需重复追加
    injection = f"\n{footer_html}\n"
    new_html = re.sub(
        r"</div>\s*</body>",
        lambda m: f"{injection}</div>\n</body>",
        html,
    )

    if new_html != html:
        log("✅ 推荐阅读 + 关注名片已注入文末（由 generate_recommend_html 统一提供）")
    return new_html


# ========================================
# ===== 【第 9 节】模块5 品牌色全局替换 =====
#  模块 5: 品牌色全局替换
# ========================================
def process_colors(html):
    """全局色值清洗"""
    changes = 0

    # 行内 code 红色 → 主题色
    new, c = re.subn(r"#d14\b", BRAND_PRIMARY, html)
    changes += c
    html = new

    # blockquote 灰底 → 浅绿底
    new = html.replace("background: #f7f7f7", "background: rgba(47, 111, 143, 0.05)")
    if new != html:
        changes += 1
    html = new

    # baoyu 默认蓝色 → 主题色（如未用 --color 参数）
    new, c = re.subn(r"#0F4C81", BRAND_PRIMARY, html, flags=re.IGNORECASE)
    changes += c
    html = new

    # 清理 <strong style="color:#0F4C81"> → <span style="color:#2F6F8F">
    html = re.sub(
        r'<strong\s+style="color:\s*#0F4C81[^"]*">(.*?)</strong>',
        rf'<span style="color:{BRAND_PRIMARY}; font-weight:bold;">\1</span>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 删除正文封面图（src 含 cover 的 img 行）
    html_new = re.sub(r'<p[^>]*>\s*<img[^>]*src="[^"]*cover[^"]*"[^>]*/?\s*>\s*</p>', "", html, flags=re.IGNORECASE)
    if html_new != html:
        changes += 1
        html = html_new

    # 简化 HR 标签（baoyu 默认每个约 247 字符）
    hr_new = '<hr style="border:0;border-top:1px solid rgba(0,0,0,0.1);margin:1.5em 8px;">'
    html_new = re.sub(r'<hr[^>]*class="hr"[^>]*>', hr_new, html)
    if html_new != html:
        changes += 1
        html = html_new

    # 清理字面量 \n（之前脚本 bug 留下的残留）
    html = html.replace("\\n", "\n")

    # 清理写作阶段遗留的方括号占位符段落
    # 包括 [品牌头图位置]、[截图：xxx] 等
    html_new = re.sub(
        r'<p[^>]*>\s*\[[^\]]*(?:品牌头图|截图)[^\]]*\]\s*</p>',
        '', html, flags=re.IGNORECASE
    )
    if html_new != html:
        removed = len(re.findall(r'\[(?:品牌头图|截图)[^\]]*\]', html)) - len(re.findall(r'\[(?:品牌头图|截图)[^\]]*\]', html_new))
        changes += removed
        html = html_new

    if changes > 0:
        log(f"✅ 品牌色清洗完成（{changes} 处替换）")
    else:
        log("⏭️ 色值已符合品牌标准")
    return html


# ========================================
# ===== 【第 10 节】模块6 清 AI 生图提示词 =====
#  模块 6: 清理 AI 生图提示词代码块
# ========================================
def process_prompts(html):
    """
    删除 Markdown 中遗留的 '> **AI生图提示词**' 代码块。
    baoyu-markdown-to-html 转换后的实际结构：
      <blockquote ...><p ...><strong>AI生图提示词</strong>...</p><pre ...>...</pre></blockquote>
    同时也删除紧邻其上的图标题行（如 <p><strong>图1：xxx</strong></p>）。
    """
    total_removed = 0

    # 模式1：删除包含 "AI生图提示词" 的完整 blockquote
    html_new = re.sub(
        r'<blockquote[^>]*>[\s\S]*?AI生图提示词[\s\S]*?</blockquote>',
        '', html, flags=re.IGNORECASE
    )
    if html_new != html:
        total_removed += html.count('AI生图提示词') - html_new.count('AI生图提示词')
        html = html_new

    # 模式2：删除紧邻的图标题行 <p><strong>图N：xxx</strong></p>
    # （图片已经以 <img> 形式存在于素材目录中）
    html_new = re.sub(
        r'<p[^>]*>\s*<strong[^>]*>图\d+：[^<]*</strong>\s*</p>',
        '', html, flags=re.IGNORECASE
    )
    if html_new != html:
        total_removed += 1
        html = html_new

    if total_removed > 0:
        log(f"✅ 已清除 {total_removed} 处 AI 生图提示词及图标题残留")
    else:
        log("⏭️ 未发现 AI 生图提示词残留")
    return html



# ========================================
# ===== 【第 11 节】模块6.5 列表重排版 =====
#  模块 6.5: 列表重排版（箭头无序 / 编号徽章 H4 有序 + 悬挂缩进）
#  样式固化
# ========================================
def process_lists(html):
    """把 baoyu 生成的 <ul class="ul"> / <ol class="ol"> 重排成「marker 独占左列 +
    内容悬挂缩进」的两列 display:table 结构（微信 table-cell 稳定支持）：

    - 无序列表(ul)：小黑点 • → **主题色箭头 ➤**（U+27A4 黑右箭头，glyph；后背微凹、比
      实心三角更有设计感），marker 独占左列；
    - 有序列表(ol)：素服 1.2.3. → **H4 设计格式 = 主题色【圆形】编号徽章**（20px,
      border-radius:50%，比 H3 的圆角方块 24px 略小，构成「方=H3 大、圆=H4 小」的清晰次级
      层次），marker 独占左列；
    - 两者内容列都悬挂缩进：第 2/3 行不顶格，全部对齐在内容列左缘，主次分明。

    背景：① 默认 `• 一句话` 排版主次不清、第二行顶格难看；② 有序编号
    需要一个介于 H3(时间线) 和正文之间的「H4」级设计格式，不能只打 1.2.3.；③
    方圆对调：H3→圆角方块、H4→圆形；无序 marker 用 ➤（U+27A4）glyph 染主题色。
    幂等：转换后不再有 <ul class="ul">/<ol class="ol">，重复跑不会二次处理。
    只匹配 baoyu 正文列表 class，不碰划重点卡片/文末框/导读栏里的自定义 <div> 列表。
    """
    BG = BRAND_PRIMARY  # #2F6F8F

    # 无序 marker：U+27A4 ➤（黑右箭头 glyph）染主题色。dingbat 区，微信/移动端字体覆盖好；
    # 比旧实心 ▸ 更大更有设计感（后背微凹），不依赖 CSS 叠层、无露白风险。
    UL_MARKER = '➤'

    def arrow_row(text):
        return ('<section style="display:table;width:100%;margin:0.5em 0;">'
                '<span style="display:table-cell;width:1.7em;vertical-align:top;'
                f'color:{BG};font-size:15px;line-height:1.85;">{UL_MARKER}</span>'
                f'<span style="display:table-cell;vertical-align:top;color:{TEXT_BODY};'
                f'line-height:1.85;">{text}</span></section>')

    def num_row(n, text):
        return ('<section style="display:table;width:100%;margin:0.6em 0;">'
                '<span style="display:table-cell;width:2.2em;vertical-align:top;">'
                f'<span style="display:inline-block;width:20px;height:20px;line-height:20px;'
                f'background:{BG};color:#fff;border-radius:50%;text-align:center;'
                f'font-size:12px;font-weight:bold;">{n}</span></span>'
                f'<span style="display:table-cell;vertical-align:top;color:{TEXT_BODY};'
                f'line-height:1.85;padding-top:1px;">{text}</span></section>')

    def conv_ul(m):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(0), re.DOTALL)
        rows = ''.join(arrow_row(re.sub(r'^\s*[•·▸►◦\-\*]\s*', '', it.strip())) for it in items)
        return f'<section style="margin:1.1em 8px;">{rows}</section>'

    def conv_ol(m):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(0), re.DOTALL)
        rows = ''.join(num_row(i, re.sub(r'^\s*\d+[\.、]\s*', '', it.strip()))
                       for i, it in enumerate(items, 1))
        return f'<section style="margin:1.1em 8px;">{rows}</section>'

    html, nu = re.subn(r'<ul class="ul"[^>]*>.*?</ul>', conv_ul, html, flags=re.DOTALL)
    html, no = re.subn(r'<ol class="ol"[^>]*>.*?</ol>', conv_ol, html, flags=re.DOTALL)
    if nu or no:
        log(f"✅ 列表重排版完成（{nu} 个无序→绿箭头 ➤、{no} 个有序→H4 圆形编号徽章，均悬挂缩进）")
    return html


# ========================================
# ===== 【第 12 节】模块7 主题色重点文字 =====
#  模块 7: 主题色重点文字（<mark> / ***粗斜体*** → 主题色粗体）
# ========================================
def process_highlights(html):
    """将主题色重点标记转换为内联样式（支持一级 / 二级深浅阶）。

    标记语法（优先级从高到低）：
    1. <mark class="2">次级文字</mark> → **二级主题色 #7FB0C4**（偏浅同色系，区分主次）
    2. <mark>重点文字</mark>          → **一级主题色 #2F6F8F**（主强调）← 推荐，HTML passthrough
    3. ***重点文字***                → 一级（旧版兼容，baoyu 对中文 *** 有吞字 bug）

    写作约定：
    - 主强调（重点突出）用 <mark>关键词</mark>；
    - 次级 / 辅助强调用 <mark class="2">次级词</mark>（同色相、偏浅，主次分明）。
    - 二级绿建议用于加粗短语 / 徽章 / 次级标题；小字正文慎用（对比度略低）。
    🛡 优雅降级：若 baoyu 吞掉了 class（极少数），<mark class="2"> 会退化成一级绿——
       仍是品牌色、可读，只是少了深浅区分，不会出错。
    """
    changes = 0
    replacement = f'<span style="color: {BRAND_PRIMARY}; font-weight: bold;">\\1</span>'
    replacement_2 = f'<span style="color: {BRAND_SECONDARY}; font-weight: bold;">\\1</span>'

    # === 二级绿先处理：<mark class="2"> / class 含 "2" 或 "sub" ===
    # 必须在通用 <mark> 之前，否则会被一级规则先吃掉。
    html, c_sub = re.subn(
        r'<mark[^>]*\bclass=["\'][^"\']*(?:2|sub)[^"\']*["\'][^>]*>([\s\S]*?)</mark>',
        replacement_2, html, flags=re.IGNORECASE
    )

    # === 一级绿：其余所有 <mark> ===
    # 匹配 <mark>text</mark> 或 <mark ...>text</mark>
    html, c_mark = re.subn(
        r'<mark[^>]*>([\s\S]*?)</mark>',
        replacement, html, flags=re.IGNORECASE
    )
    changes += c_mark + c_sub

    # === 兼容旧版 <em><strong> 组合 ===
    # 匹配 <em...><strong...>text</strong></em>
    html, c1 = re.subn(
        r'<em[^>]*>\s*<strong[^>]*>([^<]+)</strong>\s*</em>',
        replacement, html, flags=re.IGNORECASE
    )
    changes += c1

    # 匹配 <strong...><em...>text</em></strong>
    html, c2 = re.subn(
        r'<strong[^>]*>\s*<em[^>]*>([^<]+)</em>\s*</strong>',
        replacement, html, flags=re.IGNORECASE
    )
    changes += c2

    # === 清理 baoyu 转换器 bug 产生的空 <em> 废标签 ===
    # 中文 ***text*** 有时被错误解析为空 <em></em>（文字内容被吞掉）
    html, c_empty = re.subn(
        r'<em[^>]*>\s*</em>',
        '', html, flags=re.IGNORECASE
    )
    if c_empty > 0:
        log(f"🧹 清理了 {c_empty} 个空 <em> 废标签（baoyu 转换器 bug 残留）")

    if changes > 0:
        log(f"✅ 成功将 {changes} 处重点标记转换为主题色文字（{c_mark} 个一级 <mark> + {c_sub} 个二级 <mark class=2> + {c1+c2} 个粗斜体）")
    else:
        log("⏭️ 未发现重点标记（<mark> 或粗斜体）")

    return html


# ========================================
# ===== 【第 13 节】模块8 划重点卡片 =====
#  模块 8: 要点提炼卡片（划重点）转换
# ========================================
def process_takeaway(html):
    """将写作阶段的 '> **划重点**' blockquote 转换为 key-takeaway.html 品牌卡片组件。

    写作阶段的 Markdown 格式：
      > **划重点**
      > - 要点一
      > - 要点二

    baoyu 转换后变成：
      <blockquote>...<strong>划重点</strong>...<li>要点一</li>...

    本函数识别并替换为品牌卡片。要点行悬挂缩进：与 process_lists() 同一套
    display:table 两列约定，第 2/3 行不顶格（卡片内列表与正文 H3/H4 列表统一
    悬挂缩进规则，不再各自为政）。
    """
    # 幂等检查标记
    MARKER = '<!-- KEY_TAKEAWAY -->'
    existing = html.count(MARKER)

    # 匹配包含 "划重点" 或 "核心结论" 或 "核心要点" 的 blockquote
    # 注意：用 (?:(?!<blockquote|<h[12])[\s\S])*? 代替 [\s\S]*? 防止跨越多个 blockquote/H2
    pattern = re.compile(
        r'<blockquote[^>]*>(?:(?!<blockquote|<h[12])[\s\S])*?'
        r'<strong[^>]*>\s*(?:划重点|核心结论|核心要点|Key Takeaway)\s*</strong>'
        r'(?:(?!<blockquote|<h[12])[\s\S])*?</blockquote>',
        re.IGNORECASE
    )

    converted = 0

    def replace_takeaway(m):
        nonlocal converted
        block = m.group(0)

        # 如果已经被转换过（有标记），跳过
        if MARKER in block:
            return block

        # 提取标题
        title_match = re.search(
            r'<strong[^>]*>\s*(划重点|核心结论|核心要点|Key Takeaway)\s*</strong>',
            block, re.IGNORECASE
        )
        title = title_match.group(1) if title_match else '划重点'

        # 提取要点列表项
        items = re.findall(r'<li[^>]*>(.*?)</li>', block, re.DOTALL)

        # 如果没找到 li，尝试匹配 "- 要点" 格式（纯文本形式）
        if not items:
            p_items = re.findall(r'[\-·•]\s*(.+?)(?:<br|</p>|$)', block, re.DOTALL)
            items = [i.strip() for i in p_items
                     if i.strip() and '划重点' not in i and '核心结论' not in i and '核心要点' not in i]

        if not items:
            return block  # 无法提取要点，保留原样

        # 构建卡片 HTML（先清理 HTML 标签和前导圆点/破折号）
        def _clean_item(item):
            text = re.sub(r"<[^>]+>", "", item).strip()
            # 去掉前导的圆点、破折号等列表符号，避免与模板圆点重复
            text = re.sub(r"^[\s·•\-\*►▸▪◆○●]+\s*", "", text)
            return text

        # 悬挂缩进：与 process_lists() 同一套 display:table 两列约定（marker 列独占、
        # 内容列 vertical-align:top），第 2/3 行不再顶格。
        # text-align:left + word-break:break-all：防微信对含长 token（URL / 长英文）的要点行
        # 做两端对齐、把中文撑成大字间距（截图实证的「分散对齐」）。完整 URL 本应走 link-card，
        # 但这里兜底保证即便混进 URL 也不炸版。
        items_html = '\n'.join(
            f'  <section style="display:table; width:100%; font-size: 15px; color: {TEXT_BODY}; '
            f'line-height: 1.75; margin-bottom: 8px;">'
            f'<span style="display:table-cell; width:1em; vertical-align:top; color: {BRAND_PRIMARY}; font-weight: bold;">·</span>'
            f'<span style="display:table-cell; vertical-align:top; text-align:left; word-break:break-all;">{_clean_item(item)}</span></section>'
            for item in items
        )

        card = (
            f'{MARKER}\n'
            f'<section style="margin: 24px 8px; padding: 20px; '
            f'background: {TINT_CARD}; border-radius: {RADIUS_CARD}; '
            f'border-left: 4px solid {BRAND_PRIMARY};">\n'
            f'  <section style="font-size: 14px; font-weight: bold; color: {BRAND_PRIMARY}; '
            f'letter-spacing: 2px; margin-bottom: 12px;">{title}</section>\n'
            f'{items_html}\n'
            f'</section>'
        )
        converted += 1
        return card

    new_html = pattern.sub(replace_takeaway, html)

    if converted > 0:
        log(f"✅ 已将 {converted} 个「划重点」引用块转换为品牌卡片")
    else:
        if existing > 0:
            log(f"⏭️ {existing} 个要点卡片已存在，跳过")
        else:
            log("⏭️ 未发现「划重点」引用块")
    return new_html


# ========================================
# ===== 【第 14 节】模块8.5 结构组件 =====
#  模块 8.5: 结构组件（对比块 / 步骤条 / 数字卡）—— 2026-07-07 P1-4B
#  写作阶段用「自包含 HTML 注释指令」触发（100% 穿过 baoyu、不依赖表格/列表转换
#  的顺序与结构，最稳健）；排版阶段把指令替换为品牌组件。指令被消费即天然幂等。
#  三者样式仅用 design-tokens（theme-ready，零硬编码色）；flex 已实测可用（wechat-compat §1.5）。
# ========================================
def process_stat(html):
    """数字强调卡：`<!-- stat: 300|美元|Google 送的额度 ; 90|天|有效期 -->`
    → 一行 1-3 张数字卡（大号绿数字 + 单位 + 说明）。分隔：`;` 分卡、`|` 分字段（数字|单位|说明）。
    """
    def render(m):
        entries = []
        for part in m.group(1).split(";"):
            fields = [x.strip() for x in part.split("|")]
            if not fields or not fields[0]:
                continue
            entries.append((fields[0],
                            fields[1] if len(fields) > 1 else "",
                            fields[2] if len(fields) > 2 else ""))
        if not entries:
            return m.group(0)
        cards = []
        for num, unit, cap in entries:
            unit_html = (f'<span style="font-size: 13px; font-weight: normal; '
                         f'color: {TEXT_MUTED};"> {unit}</span>') if unit else ""
            cap_html = (f'<p style="margin: 4px 0 0; font-size: 12px; line-height: 1.5; '
                        f'color: {TEXT_MUTED};">{cap}</p>') if cap else ""
            cards.append(
                f'<section style="flex: 1; background: {TINT_CARD}; border-radius: {RADIUS_CARD}; '
                f'padding: 14px 10px; text-align: center;">'
                f'<p style="margin: 0; font-size: 26px; font-weight: bold; color: {BRAND_PRIMARY}; '
                f'line-height: 1.2;">{num}{unit_html}</p>{cap_html}</section>'
            )
        return (f'<section style="display: flex; gap: 8px; margin: 0 8px 0.9em;">'
                f'{"".join(cards)}</section>')

    html, n = re.subn(r"<!--\s*stat:\s*(.+?)\s*-->", render, html, flags=re.DOTALL)
    log(f"✅ 数字强调卡 ×{n}" if n else "⏭️ 未发现 <!-- stat: --> 指令")
    return html


def process_steps(html):
    """流程步骤条：`<!-- steps: 注册登录 || 创建 API key || 复制到配置 || 调用接口 -->`
    → 竖排编号步骤（绿色圆号徽章 + 步骤文字）。步骤以 `||` 分隔。
    """
    def render(m):
        steps = [s.strip() for s in m.group(1).split("||") if s.strip()]
        if not steps:
            return m.group(0)
        rows = []
        for i, s in enumerate(steps, 1):
            rows.append(
                f'<section style="display: flex; align-items: flex-start; margin-bottom: 10px;">'
                f'<section style="flex: 0 0 auto; width: 22px; height: 22px; '
                f'border-radius: {RADIUS_PILL}; background: {BRAND_PRIMARY}; color: #fff; '
                f'font-size: 13px; font-weight: bold; text-align: center; line-height: 22px; '
                f'margin-right: 10px;">{i}</section>'
                f'<section style="flex: 1; font-size: 15px; line-height: 1.7; color: {TEXT_BODY}; '
                f'padding-top: 1px;">{s}</section></section>'
            )
        return (f'<section style="margin: 0 8px 0.9em; padding: 4px 0;">'
                f'{"".join(rows)}</section>')

    html, n = re.subn(r"<!--\s*steps:\s*(.+?)\s*-->", render, html, flags=re.DOTALL)
    log(f"✅ 步骤条 ×{n}" if n else "⏭️ 未发现 <!-- steps: --> 指令")
    return html


def process_compare(html):
    """新旧/双栏对比块：`<!-- compare: 旧做法|手动逐个复制,10分钟 || 新做法|一键批量,10秒 -->`
    → 并排两卡（左灰系「旧」/ 右绿系「新」），每侧 `标题|内容`，两侧以 `||` 分隔。
    不用红色（品牌只有一种主色），旧侧用中性灰、新侧用主题色区分。
    """
    def render(m):
        sides = m.group(1).split("||")
        if len(sides) != 2:
            return m.group(0)
        parsed = []
        for side in sides:
            fields = [x.strip() for x in side.split("|")]
            parsed.append((fields[0] if fields else "",
                           fields[1] if len(fields) > 1 else ""))
        (lt, lb), (rt, rb) = parsed
        left = (
            f'<section style="flex: 1; background: {TINT_SOFT}; border: 1px solid {BORDER_HAIR}; '
            f'border-radius: {RADIUS_CARD}; padding: 12px;">'
            f'<p style="margin: 0 0 6px; font-size: 13px; font-weight: bold; color: {TEXT_MUTED};">{lt}</p>'
            f'<p style="margin: 0; font-size: 14px; line-height: 1.65; color: {TEXT_BODY};">{lb}</p></section>'
        )
        right = (
            f'<section style="flex: 1; background: {TINT_CARD}; border: 1px solid {BORDER_CARD}; '
            f'border-radius: {RADIUS_CARD}; padding: 12px;">'
            f'<p style="margin: 0 0 6px; font-size: 13px; font-weight: bold; color: {BRAND_PRIMARY};">{rt}</p>'
            f'<p style="margin: 0; font-size: 14px; line-height: 1.65; color: {TEXT_BODY};">{rb}</p></section>'
        )
        return (f'<section style="display: flex; gap: 8px; margin: 0 8px 0.9em; '
                f'align-items: stretch;">{left}{right}</section>')

    html, n = re.subn(r"<!--\s*compare:\s*(.+?)\s*-->", render, html, flags=re.DOTALL)
    log(f"✅ 对比块 ×{n}" if n else "⏭️ 未发现 <!-- compare: --> 指令")
    return html


# ========================================
# ===== 【第 15 节】模块9 导读引用块样式 =====
#  模块 9: 导读引用块样式转换
# ========================================
def process_lead_quote(html):
    """将 Markdown 中开头带 `> **导读**` 的引用块转换为较小字号的导读区域。
    """
    pattern = re.compile(
        r'(<blockquote[^>]*>)\s*(<p[^>]*>\s*<strong[^>]*>\s*<span[^>]*>\s*导读\s*</span>\s*</strong>\s*</p>)\s*(<p[^>]*>[\s\S]*?</p>)\s*</blockquote>',
        re.IGNORECASE
    )
    def replacer(m):
        bq_start = m.group(1)
        title_p = m.group(2)
        content_p = m.group(3)
        # 加上内联样式让字体缩小 2 号
        styled_content = content_p.replace('<p', '<p style="font-size: 14px; color: #666666;"', 1)
        return f'{bq_start}\n{title_p}\n{styled_content}\n</blockquote>'

    new_html, count = pattern.subn(replacer, html)
    
    # 也兼容没有 span 的情况
    pattern2 = re.compile(
        r'(<blockquote[^>]*>)\s*(<p[^>]*>\s*<strong[^>]*>\s*导读\s*</strong>\s*</p>)\s*(<p[^>]*>[\s\S]*?</p>)\s*</blockquote>',
        re.IGNORECASE
    )
    def replacer2(m):
        bq_start = m.group(1)
        title_p = m.group(2)
        content_p = m.group(3)
        styled_content = content_p.replace('<p', '<p style="font-size: 14px; color: #666666;"', 1)
        return f'{bq_start}\n{title_p}\n{styled_content}\n</blockquote>'
        
    new_html, c2 = pattern2.subn(replacer2, new_html)
    count += c2

    if count > 0:
        log(f"✅成功将 {count} 处「导读」引用块字号调整为 14px")
    else:
        log("⏭️ 未发现导读引用块")
    return new_html


# ========================================
# ===== 【第 16 节】模块11 微信兼容微调 =====
#  模块 11: 微信兼容性微调（图片圆角 + <p> 强制 color）
# ========================================
def process_wechat_compat(html):
    """微信客户端兼容性微调。

    1. 图片圆角 border-radius: 8px —— 让配图从"方正嵌入"变为"柔和融入"，
       跳过导读栏 hero、bgm 封面等组件小图。
    2. <p> 强制 color —— 微信暗黑模式会对无显式 color 的 <p> 做智能反色，
       经常把黑字变成刺眼的白色。显式声明 color 后微信不再猜测。

    借鉴来源：WeWrite converter.py _apply_wechat_fixes()
    """
    changes = 0

    # --- 图片圆角 ---
    # 跳过已有 border-radius 的图片、导读栏内的 hero 图、推荐卡片封面图
    def add_img_radius(m):
        nonlocal changes
        tag = m.group(0)
        # 跳过已有圆角 / hero / bgm_cover / music_cover / logo
        if 'border-radius' in tag:
            return tag
        skip_keywords = ['hero', 'bgm_cover', 'music_cover', 'logo-white', 'logo-black']
        if any(kw in tag for kw in skip_keywords):
            return tag
        changes += 1
        if 'style="' in tag:
            return tag.replace('style="', f'style="border-radius: {RADIUS_MEDIA}; ')
        else:
            return tag.replace('<img', f'<img style="border-radius: {RADIUS_MEDIA};"', 1)

    html = re.sub(r'<img[^>]*>', add_img_radius, html)

    # --- <p> 强制 color ---
    text_color = TEXT_BODY
    p_fixed = 0
    def force_p_color(m):
        nonlocal p_fixed
        tag = m.group(0)
        # 跳过已有 color 的
        if 'color' in tag.split('>')[0]:
            return tag
        p_fixed += 1
        if 'style="' in tag:
            return tag.replace('style="', f'style="color: {text_color}; ')
        else:
            return tag.replace('<p', f'<p style="color: {text_color};"', 1)

    html = re.sub(r'<p[^>]*>', force_p_color, html)
    changes += p_fixed

    if changes > 0:
        log(f"✅ 微信兼容性微调完成（{changes - p_fixed} 张图片加圆角，{p_fixed} 个 <p> 补 color）")
    else:
        log("⏭️ 无需微信兼容性微调")
    return html


# ========================================
# ===== 【第 17 节】主流程 preflight =====
#  主流程
# ========================================
def preflight_markdown(cwd: str):
    """排版前扫描 定稿.md，捕获会导致排版崩坏的 markdown 异常。
    返回 (errors, warnings)：errors 非空 → 硬阻断排版（真的会崩，如 H3 未闭合 **）；
    warnings 只提示不阻断（如钩子区缺加粗 —— 2026-06-07 起降级，见下）。
    """
    errors = []
    warnings = []
    md_path = Path(cwd) / "定稿.md"
    if not md_path.exists():
        return errors, warnings  # 没有 md 不检查（纯 html 场景）

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        # 1) H3 行内 `**` 未配对 → 会让 baoyu-markdown-to-html 吞掉整段，
        #    后续虚线绘制跳过（复盘问题 #4）
        if line.startswith("### ") and line.count("**") % 2 != 0:
            errors.append(f"定稿.md L{i}: H3 标题存在未闭合 **: {line[:60]}")

        # 2) 数字有序列表 "1. " 在 H3 / H2 之间出现——应写成 ### 1. 形式（时间线要求）
        #    暂不强制，只作信息提示（有些场景不适合改 H3）

    # 🟡 钩子区加粗下限审计；后从硬阻断降为软警告。
    #    背景：曾把「读者第一段不想读第二段」归因为加粗锚点不足，于是上了 sys.exit(2) 硬门。
    #    复盘（写作引擎"顺但没味道"诊断）判定这是因果倒置——决定"想读第二段"的是
    #    首句钩子张力 + 句间承接（见 writing.md §句间引力），不是加粗密度；强制加粗反而把首段
    #    切成均匀要点格，更像 PPT 不像人在说话。故此项降级为 warnings（提示不阻断），加粗"上限"
    #    防刷屏仍由 verify_bold_density 保留。首段质量改由人/agent 判"首句张力+前两句承接"。
    body = re.sub(r'^---.*?---', '', text, count=1, flags=re.DOTALL)

    # 🔴 检查范围从「前 3 段」扩到 **开篇区 = 正文开头 → 第一个 H2**
    # （实证：有的开篇 7+ 段，第 4 段起照样是字墙）。
    # 文案改正向：缺的不是"加粗量"，是「信息锚点四型」——专名首现/关键数字/
    # 时间窗口/对比转折结论（详见 writing.md §信息锚点四型 + playbook
    # opening_highlight_anchors，pinned 硬执行）。仍是 warning 不阻断
    # （因果判定保留：决定读不读下去的是钩子张力，标识管的是"扫得到重点"）。
    h2_split = re.split(r'^## ', body, maxsplit=1, flags=re.MULTILINE)
    opening = h2_split[0]
    op_paragraphs = []
    for p in re.split(r'\n\s*\n', opening):
        first = p.strip()
        if not first or first.startswith('#') or first.startswith('!') \
                or first.startswith('>') or first.startswith('<!--') \
                or first.startswith('---'):
            continue
        # 图注/来源行等纯内联 HTML 块（<section>/<p> 小字行）不是正文段，
        # 不参与开篇锚点统计与字数密度（曾踩坑：新闻配图图注被误判为正文段）
        if re.match(r'<(section|p|div|figure|blockquote)[\s>]', first):
            continue
        text_only = re.sub(r'[*`~_]', '', first)
        if len(text_only) < 30:
            continue
        op_paragraphs.append((first, text_only))

    # 数 markdown `**` / `<mark>` / 主题色 span（font-weight:6X0）/ <strong>，兼容 md 内联 html
    def _n_anchor(raw):
        return (len(re.findall(r'\*\*[^*\n]+?\*\*', raw)) +
                len(re.findall(r'<mark[^>]*>[^<]+?</mark>', raw)) +
                len(re.findall(r'<span[^>]*font-weight:\s*6\d0[^>]*>', raw)) +
                len(re.findall(r'<strong[^>]*>', raw)))
    # 🔴 开篇重点标识：软警告 → **硬下限**（只设下限不设上限）。
    #   要的是 (A) 词组级主题色标识 的下限，不是 (B) 整句口号加粗（B 仍受
    #   verify_bold_density ≤2 上限约束）—— 两者不冲突，所以可同时硬。
    #   读者手机快滑只扫主题色重点词 → 开篇区每个实质段（≥40字）必须 ≥1 处词组级标识，否则 exit 2。
    if op_paragraphs:
        substantive = [(raw, t) for raw, t in op_paragraphs if len(t) >= 40]
        naked = [t[:36] for raw, t in substantive if _n_anchor(raw) == 0]
        if naked:
            errors.append(
                f"🔴 开篇重点标识硬门（只下限不上限）：开篇区（→第一个 H2）有 "
                f"{len(naked)}/{len(substantive)} 个实质段（≥40字）零词组级重点标识 → {naked[:3]}。"
                f"读者手机快滑只扫主题色重点词，开篇每个实质段必须 ≥1 处词组级标识"
                f"（信息锚点六型：①专名首现 ②关键数字 ③时间窗口 ④对比转折结论 ⑤入口/行动锚 ⑥落差/量级对比，"
                f"出现即 **标**，事实型①②⑤⑥优先；≤15 字词组、不是整句口号，整句口号仍受 ≤2 上限约束）。"
            )
        # 🔴 开篇标识 存在性下限 → 追加**比例密度**下限。
        #   存在性门只保证"每实质段至少 1 处"，"每段勉强 1 处 / 短段漏标"仍显稀疏；
        #   补一道 writing.md 早有的"每 ~120 字 1 处"密度门，让开篇标识覆盖真达标（读者一眼扫核心）。
        op_chars = sum(len(t) for _raw, t in op_paragraphs)
        op_anchors = sum(_n_anchor(raw) for raw, _t in op_paragraphs)
        need = -(-op_chars // 120)  # ceil(字数 / 120)
        if op_chars >= 120 and op_anchors < need:
            errors.append(
                f"🔴 开篇标识密度门（比例密度）：开篇区约 {op_chars} 字仅 "
                f"{op_anchors} 处主题色标识，低于下限 {need} 处（每 ~120 字 1 处）。"
                f"读者一眼扫核心靠这些锚点——优先补事实型（①专名 ②数字 ⑤入口 ⑥落差），"
                f"信息锚点六型见 writing.md §信息锚点六型。"
            )

    # 🔴 文字墙警告（实证：~1500 字 0 个 H3 纯段落连排会劝退读者）：
    # H2 区块 ≥800 字且无 H3/图/列表/引用块 → 提示拆 H3（排版才有时间线格式可用）。
    # warning 不阻断——短块/抒情收尾不硬拆（writing.md §H3 子标题与防文字墙）。
    # 颗粒度 = 连续无切分的「run」：块内被 H3/图/列表/引用切开后，任一段连排 ≥800 字
    # 仍算字墙（块里有图，但图与图之间 ~1000 字纯段落连排——整块豁免逮不到）。
    h2_blocks = re.split(r'^(## .+)$', body, flags=re.MULTILINE)
    for bi in range(1, len(h2_blocks) - 1, 2):
        h2_title = h2_blocks[bi][3:].strip()
        block = h2_blocks[bi + 1]
        run_chars, max_run, runs_over = 0, 0, 0
        for ln in block.split('\n'):
            s = ln.strip()
            is_break = bool(
                s.startswith('### ') or s.startswith('![') or s.startswith('> ') or
                re.match(r'^[-*] |^\d+\. ', s))
            if is_break:
                if run_chars >= 800:
                    runs_over += 1
                max_run = max(max_run, run_chars)
                run_chars = 0
            else:
                run_chars += len(re.sub(r'\s', '', s))
        if run_chars >= 800:
            runs_over += 1
        max_run = max(max_run, run_chars)
        if runs_over:
            warnings.append(
                f"H2「{h2_title}」内有 {runs_over} 段 ≥800 字的纯文字连排"
                f"（最长 {max_run} 字，中途无 H3/图/列表/引用）——读者面对字墙。"
                f"找 2-4 个天然推进点（时间推进/环节/要点切换）拆 ### H3，"
                f"排版自动转时间线格式（绿圆角方块+竖线；writing.md §H3 子标题与防文字墙）"
            )

    return errors, warnings


def normalize_img_local_paths(html, base_dir):
    """修复 baoyu-markdown-to-html 写 data-local-path 时的反斜杠转义坑。

    Windows 绝对路径里 `\\n`（如 ...\\nuwa.png）、`\\t`、`\\r`、`\\b` 等会被
    误解析成控制字符（换行/制表/退格），data-local-path 被截断 → wechat-api 上传报
    "Image not found"、配图在草稿里悄悄丢失（曾踩坑：文件名首字母恰构成 \\n 等转义）。
    根治：对本文相对 src（素材/...）的 img，把 data-local-path 重建为**正斜杠**绝对路径
    （Windows + wechat-api 均接受正斜杠，零转义风险）。只动本文素材图，不碰推荐卡里其他
    文章的绝对路径 cover；幂等。"""
    base = os.path.abspath(base_dir).replace("\\", "/")

    def fix(m):
        tag = m.group(0)
        srcm = re.search(r'src="([^"]*)"', tag)
        if not srcm:
            return tag
        s = srcm.group(1)
        if not (s.startswith("素材") or s.startswith("./素材")):
            return tag
        rel = s[2:] if s.startswith("./") else s
        absp = base + "/" + rel
        if "data-local-path=" in tag:
            return re.sub(r'data-local-path="[^"]*"',
                          f'data-local-path="{absp}"', tag, flags=re.S)
        return re.sub(r'(<img\b)', rf'\1 data-local-path="{absp}"', tag, count=1)

    return re.sub(r'<img\b[^>]*?>', fix, html, flags=re.S)


# ========================================
# ===== 【第 18 节】模块8.6 交付附件 _layout-decision =====
#  模块 8.6: 交付附件 _layout-decision.md（2026-07-07 P1-5）
#  给交付一个「确定性排版决策骨架」：扫 定稿.md 的结构信号自动填「机械事实」段；
#  「语义决策」段（文体判定/自拟标题/配图通道仲裁/要点卡落位理由）留 TODO 由编排器/LLM 补。
#  用 AUTO-FACTS 标记包住自动段：文件已存在时只刷新该段、保留 LLM 已填的语义段（--all 多次跑不丢）。
# ========================================
_LD_AUTO_START = "<!-- AUTO-FACTS-START -->"
_LD_AUTO_END = "<!-- AUTO-FACTS-END -->"


def _scan_md_structure(md: str) -> dict:
    """从 定稿.md 源码扫结构信号（markdown 干净、比扫 html 稳）。"""
    f = {}
    f["h2"] = len(re.findall(r"^##\s+\S", md, re.M))
    f["h3"] = len(re.findall(r"^###\s+\S", md, re.M))
    f["stat"] = len(re.findall(r"<!--\s*stat:", md))
    f["steps"] = len(re.findall(r"<!--\s*steps:", md))
    f["compare"] = len(re.findall(r"<!--\s*compare:", md))
    f["chart"] = len(re.findall(r"<!--\s*chart:", md))
    f["takeaway"] = len(re.findall(r">\s*\*\*\s*(?:划重点|核心结论|核心要点|Key Takeaway)", md))
    f["table"] = len(re.findall(r"^\s*\|[\s:\-|]+\|\s*$", md, re.M))  # 表头分隔行 = 表格数
    f["img"] = len(re.findall(r"!\[", md))
    return f


def _render_layout_facts(cwd: str, meta: dict) -> str:
    """渲染 AUTO-FACTS 段正文（不含标记）。"""
    md_path = os.path.join(cwd, "定稿.md")
    md = Path(md_path).read_text(encoding="utf-8") if os.path.exists(md_path) else ""
    s = _scan_md_structure(md)
    meta = meta or {}
    genre = meta.get("genre") or meta.get("文体") or "（未标注 → 见 outline.md 步骤3 文体识别）"
    title = meta.get("title_final") or meta.get("title") or "（见 title.md 锻造结果）"
    rows = [
        f"- **文体**：{genre}",
        f"- **标题**：{title}",
        f"- **结构**：H2 大编号 ×{s['h2']} / H3 子标题 ×{s['h3']}",
        f"- **要点卡（划重点）**：×{s['takeaway']}",
        f"- **结构组件**：数字卡 ×{s['stat']} / 步骤条 ×{s['steps']} / 对比块 ×{s['compare']}",
        f"- **表格**：×{s['table']}（≥3 列自动 11px 横滑；2 列术语｜释义自动转术语卡）",
        f"- **配图**：正文图 ×{s['img']} / 数据图表标记 ×{s['chart']}",
    ]
    return "> 本段由 `format_layout.py --all` 自动扫 `定稿.md` 生成，勿手改（下次 --all 会覆盖本段）。\n\n" + "\n".join(rows)


def write_layout_decision(cwd: str, meta: dict = None) -> None:
    """写/更新 交付附件 _layout-decision.md。已存在则只刷新 AUTO-FACTS 段、保留语义段。
    任何异常静默跳过（交付附件非关键路径，绝不阻断排版主流程）。"""
    try:
        out_path = os.path.join(cwd, "_layout-decision.md")
        facts = _render_layout_facts(cwd, meta)
        auto_block = f"{_LD_AUTO_START}\n{facts}\n{_LD_AUTO_END}"
        if os.path.exists(out_path):
            old = Path(out_path).read_text(encoding="utf-8")
            if _LD_AUTO_START in old and _LD_AUTO_END in old:
                new = re.sub(
                    re.escape(_LD_AUTO_START) + r"[\s\S]*?" + re.escape(_LD_AUTO_END),
                    lambda _m: auto_block, old, count=1)
            else:
                new = old.rstrip() + "\n\n" + auto_block + "\n"
            Path(out_path).write_text(new, encoding="utf-8")
            log("🧾 已刷新 _layout-decision.md 机械事实段（语义段保留）")
            return
        # 首次：写完整骨架（机械事实 + 语义决策 TODO）
        scaffold = (
            "# 排版决策说明（交付附件）\n\n"
            "记录本篇的排版语义决策，随稿交付、便于复盘与学习。\n\n"
            "## 一、机械事实（自动）\n\n"
            f"{auto_block}\n\n"
            "## 二、语义决策（编排器/LLM 填）\n\n"
            "- **文体判定理由**：为什么判为该文体？（题材/信息结构/读者预期，见 outline.md 步骤3）_TODO_\n"
            "- **自拟标题理由**：标题走了哪一招（直球关键词前置/数字反差/…），为何弃其他候选？（见 title.md）_TODO_\n"
            "- **配图通道仲裁**：封面/概念图/数据图各走了哪条通道，为何？（见 image-routing.md）_TODO_\n"
            "- **要点卡落位**：每 800-1200 字一个要点卡，收束了哪些观点？_TODO_\n"
            "- **组件选用**：为何用（或不用）对比块/步骤条/数字卡？（见 layout.md 步骤2.5 配方表）_TODO_\n"
        )
        Path(out_path).write_text(scaffold, encoding="utf-8")
        log("🧾 已生成 _layout-decision.md 交付附件（机械事实已填，语义段待编排器补）")
    except Exception as e:
        log(f"⚠️ _layout-decision.md 生成跳过（不阻断）：{e}")


# ===== 【第 19 节】run() 主编排 · 契约门链 =====
def run(args):
    target = args.file
    if not os.path.exists(target):
        log(f"❌ 文件不存在: {target}")
        sys.exit(1)

    cwd = os.getcwd()

    # 🔴 2026-04 新增：排版前扫描 定稿.md 的致命 markdown 缺陷
    #    触发时机：--all 或 --h2（涉及标题转换时才扫）
    if args.all or getattr(args, "h2", False):
        md_errors, md_warnings = preflight_markdown(cwd)
        for w in md_warnings:
            log(f"⚠️ 排版前提示（不阻断）：{w}")
        if md_errors:
            log("❌ 排版前检查失败，请先修复 定稿.md：")
            for e in md_errors:
                log(f"   • {e}")
            if not getattr(args, "skip_preflight", False):
                log("   （如需强制跳过，加 --skip-preflight；旧 --force 别名仍兼容）")
                sys.exit(2)
            log("   （--skip-preflight 已跳过，但排版结果可能异常）")

        # 🔴 2026-05-21 新增：发布前素材门 + lead 块校验
        #    通过 contracts.verify_publish_assets / verify_article_meta_lead 强制
        try:
            from contracts import verify_publish_assets, verify_article_meta_lead
        except Exception:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from contracts import verify_publish_assets, verify_article_meta_lead
            except Exception as e:
                log(f"⚠️ 无法 import contracts.verify_publish_assets/verify_article_meta_lead：{e}")
                verify_publish_assets = None
                verify_article_meta_lead = None

        if verify_publish_assets:
            assets_result = verify_publish_assets(cwd)
            if assets_result['errors']:
                log(f"❌ 发布前素材门未通过（{assets_result['checks_passed']}/{assets_result['checks_total']}）：")
                for e in assets_result['errors']:
                    log(f"   • {e}")
                if not getattr(args, "skip_preflight", False):
                    log("   （--skip-preflight 强制跳过；建议补齐后再排版）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，发布物可能缺关键素材）")
            for w in assets_result.get('warnings', []):
                log(f"⚠️ 素材门提示：{w}")

        if verify_article_meta_lead:
            lead_result = verify_article_meta_lead(cwd)
            if lead_result['verdict'] == 'warning' and lead_result['missing']:
                log(
                    f"⚠️ article-meta.yaml lead 块缺：{lead_result['missing']}。"
                    f"建议补全后再排版，否则导读栏走默认占位文案"
                )

        # 🔴 2026-05-22 Team refs-activation 落地：A 层前置断言 + B-主门 + B-软门
        try:
            from contracts import (verify_anti_ai_blacklist, audit_style_signals,
                                    verify_cjk_punctuation)
        except Exception:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from contracts import (verify_anti_ai_blacklist, audit_style_signals,
                                        verify_cjk_punctuation)
            except Exception as e:
                log(f"⚠️ 无法 import contracts 验证函数：{e}")
                verify_anti_ai_blacklist = None
                audit_style_signals = None
                verify_cjk_punctuation = None

        md_path = os.path.join(cwd, "定稿.md")

        # A 层：断言 prep_writing.py 跑过（_prep-context.md 存在且非空）
        # 跳过 prep 直接写 = 排版硬门 fail —— A 从「自觉」变「不做走不下去」
        if os.path.exists(md_path):
            prep_path = os.path.join(cwd, "_prep-context.md")
            if not os.path.exists(prep_path) or os.path.getsize(prep_path) == 0:
                log("❌ A 层前置门：_prep-context.md 不存在或为空")
                log("   写作前必须先跑：python $SKILL/scripts/prep_writing.py")
                if not getattr(args, "skip_preflight", False):
                    log("   （补跑 prep_writing.py 后重排；--skip-preflight 可强制跳过）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，本篇未走 prep 喂料）")
            elif os.path.getmtime(prep_path) > os.path.getmtime(md_path):
                log("⚠️ _prep-context.md 的 mtime 晚于 定稿.md —— "
                    "prep 可能在写作后才补跑（重排版场景可忽略）")

        # 冷读外审门（🔴 2026-06-10 P1-7）：断言 _stutter-list.md 存在且非空。
        # 该文件由一个不带写作上下文（无大纲/种子/会话历史）的全新 subagent
        # 以首读读者身份冷读 定稿.md 产出（见 writing.md §磨 第 6 步）。
        # 写作 agent 自审带全上下文会盲目自信（49 号 6 处语法硬伤穿过自审实证），
        # 故收硬门：允许「全文无卡顿」的空结论，但文件必须存在。
        if os.path.exists(md_path):
            stutter_path = os.path.join(cwd, "_stutter-list.md")
            if not os.path.exists(stutter_path) or os.path.getsize(stutter_path) == 0:
                log("❌ 冷读外审门：_stutter-list.md 不存在或为空")
                log("   排版前必须先派冷读 subagent 外审定稿（writing.md §磨·冷读外审）")
                if not getattr(args, "skip_preflight", False):
                    log("   （产出 _stutter-list.md 后重排；--skip-preflight 可强制跳过）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，本篇未走冷读外审）")
            else:
                if os.path.getmtime(stutter_path) < os.path.getmtime(md_path):
                    log("⚠️ _stutter-list.md 早于 定稿.md —— 冷读可能基于旧稿，"
                        "改稿幅度大时建议重派冷读一轮")
                # 诚实边界：本门只验文件存在 + 签名字段在，不验内容质量、不保证真换了模型。
                # 语义层换不换模型靠 agent 自觉（契约见 references/semantic-review.md），过门 ≠ 冷读已把关。
                # 非阻断 WARNING，绝不 exit2（历史 _stutter-list.md 无签名）。
                try:
                    _stutter_txt = Path(stutter_path).read_text(encoding="utf-8")
                except Exception:
                    _stutter_txt = ""
                # 优先认 semantic-review.md 的正式签名块（评审模型/写作模型/段数），兼容旧式自由签名
                _m_review = re.search(r"评审模型[:：]\s*([^\n]+)", _stutter_txt)
                _m_writer = re.search(r"写作模型[:：]\s*([^\n]+)", _stutter_txt)
                _has_model = bool(_m_review) or bool(re.search(
                    r"模型|model|Sonnet|Opus|Haiku|Gemini|GPT", _stutter_txt, re.IGNORECASE))
                _has_segs = bool(re.search(r"段数[:：]\s*\d+|逐段读完|读完.*段|共.*段|\d+\s*段", _stutter_txt))
                if not (_has_model and _has_segs):
                    log("⚠️ 冷读外审建议带结构化签名（见 references/semantic-review.md 的 "
                        "semantic-review-signature 块：评审模型 + 段数）——"
                        "同模型自审照不出语义 AI 味，签名能把『真跑过 / 真换模型』的代理信号抬高一档")
                elif (_m_review and _m_writer
                      and _m_review.group(1).strip().lower() == _m_writer.group(1).strip().lower()):
                    log("⚠️ 冷读签名显示 评审模型 == 写作模型 —— 同模型自审，语义差分信号弱；"
                        "高价值篇建议按 semantic-review.md 换不同模型族（如 Sonnet）重派一轮")
                else:
                    log("ℹ️ 冷读外审签名完整（评审模型 + 段数）；语义内容质量仍靠异模型视野、非脚本可验")

        # 事实复核门（🔴 2026-07-02 C13）：断言 _fact-check.md 存在且非空。
        # 由不带写作上下文的全新 subagent 从定稿提取可核事实（数字/日期/价格/版本号/专名/引语）
        # 逐条对信源或现场搜索核实后产出（见 references/fact-check.md）。与冷读外审门同构：
        # 抓外部真伪，冷读抓内部一致性，两者划界。
        if os.path.exists(md_path):
            factcheck_path = os.path.join(cwd, "_fact-check.md")
            if not os.path.exists(factcheck_path) or os.path.getsize(factcheck_path) == 0:
                log("❌ 事实复核门：_fact-check.md 不存在或为空")
                log("   排版前先派事实复核 subagent 核对定稿的数字/日期/价格/版本号/专名（references/fact-check.md）")
                if not getattr(args, "skip_preflight", False):
                    log("   （产出 _fact-check.md 后重排；--skip-preflight 可强制跳过）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，本篇未走事实复核）")
            else:
                if os.path.getmtime(factcheck_path) < os.path.getmtime(md_path):
                    log("⚠️ _fact-check.md 早于 定稿.md —— 事实复核可能基于旧稿，改稿后建议重核一轮")
                try:
                    _fc_txt = Path(factcheck_path).read_text(encoding="utf-8")
                except Exception:
                    _fc_txt = ""
                _fc_has_model = bool(re.search(
                    r"复核模型[:：]|模型|model|Sonnet|Opus|Haiku|Gemini|GPT", _fc_txt, re.IGNORECASE))
                _fc_has_verdict = bool(re.search(r"PASS|通过|待核实|need_verify|条目数", _fc_txt, re.IGNORECASE))
                if not (_fc_has_model and _fc_has_verdict):
                    log("⚠️ 事实复核建议带签名（复核模型 + 条目数 + 结论 PASS/n条待改，见 references/fact-check.md）")
                elif re.search(r"待核实|need_verify", _fc_txt):
                    log("ℹ️ 事实复核含待核实项 —— 发布前确认这些 claim 已改模糊表述或删除")
                else:
                    log("ℹ️ 事实复核签名完整（复核模型 + 条目）；外部真伪核验靠异视野、非脚本可验")

        # B-主门：AI 腔黑名单硬验证（A 档命中即 exit 2）
        if verify_anti_ai_blacklist and os.path.exists(md_path):
            bl = verify_anti_ai_blacklist(md_path)
            if bl['errors']:
                log(f"❌ B-主门 AI 腔黑名单未通过（A 档硬命中 {bl['hard_hits']} 处）：")
                for e in bl['errors']:
                    log(f"   • {e}")
                if not getattr(args, "skip_preflight", False):
                    log("   （修掉这些显性 AI 套话后重排；--skip-preflight 可强制跳过）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，定稿仍含显性 AI 腔）")
            for w in bl.get('warnings', []):
                log(f"⚠️ B-主门软提示：{w}")
            # 诚实边界提示：B-主门只覆盖反例库约 60% 的显性套话
            log("ℹ️ B-主门只查显性 AI 套话，verdict=ok ≠ AI 味已清；语义类靠磨稿自查")

        # 半角标点硬门：中文间误用半角逗号/冒号（确定性，命中即 exit 2）
        if verify_cjk_punctuation and os.path.exists(md_path):
            cjk = verify_cjk_punctuation(md_path)
            if cjk['errors']:
                log(f"❌ 半角标点门未通过（中文间半角标点 {cjk['hits']} 处）：")
                for e in cjk['errors'][:12]:
                    log(f"   • {e}")
                if not getattr(args, "skip_preflight", False):
                    log('   （一键自动修：python "$SKILL/scripts/normalize_cjk_punctuation.py" 定稿.md')
                    log("     —— 确定性把中文紧邻的半角 ,;:!? 转全角，零误伤代码/URL/时间/.mp4，修完重排）")
                    log("   （或 --skip-preflight 强制跳过）")
                    sys.exit(2)
                log("   （--skip-preflight 已跳过，定稿仍含中文间半角标点）")

        # B-软门：风格信号软审计
        # 命中 ≥1 → verdict=info 只诊断；命中 0 → verdict=blocked 软阻塞 exit 1
        if audit_style_signals and os.path.exists(md_path):
            sig = audit_style_signals(md_path)
            log(f"📊 B-软门：{sig.get('notes', '')}")
            for w in sig.get('warnings', []):
                log(f"⚠️ B-软门提示：{w}")
            if sig.get('verdict') == 'blocked':
                if not getattr(args, "skip_preflight", False):
                    log("❌ B-软门软阻塞：vocab 0 命中 = 写作没用 prep")
                    log("   （回去内化 _prep-context.md 重写；--skip-preflight 可跳过但需说明理由）")
                    sys.exit(1)
                log("   （--skip-preflight 已跳过 B-软门软阻塞）")

        # 量化体检报告（🔴 2026-06-20 P2）：排版时自动打印 audit_quant_signals
        # 的句长方差 / 副词密度 / 段落节奏等数值报告，从「靠人记得敲命令」改成
        # 「排版自动出报告」。永不阻塞 —— 数值是诊断不是目标（避免 Goodhart），
        # 改不改稿靠 agent 判断；门只负责把体检单端上来。
        if os.path.exists(md_path):
            try:
                from contracts import audit_quant_signals as _quant
            except Exception:
                _quant = None
            if _quant:
                try:
                    qs = _quant(md_path)
                    for _n in qs.get('notes', []):
                        log(f"📐 量化体检（仅报告·永不阻塞）：{_n}")
                except Exception as _qe:
                    log(f"⚠️ 量化体检报告生成失败（不阻断）：{_qe}")

        # skill 自省（2026-05-22）：本次 preflight 各门结果追加到 _skill-observations.jsonl
        # locals() 安全取值 —— 某门没跑（import 失败）则变量不存在，跳过
        try:
            from contracts import log_observation as _logobs
            _lv = locals()
            _art = os.path.basename(os.path.normpath(cwd))
            for _var, _ev in [('assets_result', 'verify_publish_assets'),
                              ('lead_result', 'verify_article_meta_lead'),
                              ('bl', 'verify_anti_ai_blacklist'),
                              ('cjk', 'verify_cjk_punctuation'),
                              ('sig', 'audit_style_signals')]:
                _r = _lv.get(_var)
                if isinstance(_r, dict):
                    _d = '; '.join((_r.get('errors') or _r.get('warnings') or [])[:3])
                    _logobs('format_layout', _ev, str(_r.get('verdict', '')), _d, _art)
        except Exception:
            pass

    # 读取 article-meta.yaml（CLI 参数优先于 yaml 值）
    meta = load_article_meta(cwd)
    if meta:
        apply_meta_to_args(args, meta)

    # P2-b 字数对比（2026-05-22 旁观者复核：char_count_target 不再是死字段）
    _md_path = os.path.join(cwd, "定稿.md")
    if meta and meta.get("char_count_target") and os.path.exists(_md_path):
        try:
            _wc = len(Path(_md_path).read_text(encoding="utf-8"))
            log(f"📐 字数：定稿.md 实际 {_wc} 字符 / article-meta 目标 "
                f"{meta.get('char_count_target')}（不硬卡，仅供参考；偏离大则自查内容是否够实）")
        except Exception:
            pass

    html = Path(target).read_text(encoding="utf-8")

    log(f"📄 开始处理: {target}")
    log(f"📏 原始大小: {len(html)} 字符")

    # 判断是否有处理模块需要执行（--check 可单独运行）
    has_processing = any([args.all, args.h2, args.table, args.lead, args.footer,
                          args.colors, args.prompts, args.takeaway,
                          getattr(args, 'lists', False),
                          getattr(args, 'highlights', False),
                          getattr(args, 'lead_quote', False),
                          getattr(args, 'stat', False),
                          getattr(args, 'steps', False),
                          getattr(args, 'compare', False),
                          getattr(args, 'wechat_compat', False)])

    if has_processing:
        # 🔴 先修 baoyu 写 data-local-path 的反斜杠转义坑（\nuwa→换行、\table→\t 等）
        html = normalize_img_local_paths(html, cwd)
        if args.all or args.colors:
            html = process_colors(html)
        if args.all or args.prompts:
            html = process_prompts(html)
        if args.all or getattr(args, 'highlights', False):
            html = process_highlights(html)
        if args.all or args.takeaway:
            html = process_takeaway(html)
        # 结构组件（自包含注释指令，顺序无关；放 takeaway 后、lists 前）
        if args.all or getattr(args, 'stat', False):
            html = process_stat(html)
        if args.all or getattr(args, 'steps', False):
            html = process_steps(html)
        if args.all or getattr(args, 'compare', False):
            html = process_compare(html)
        if args.all or getattr(args, 'lists', False):
            html = process_lists(html)
        if args.all or getattr(args, 'lead_quote', False):
            html = process_lead_quote(html)
        if args.all or args.h2:
            # H2 固定 PART 编号格式
            part_subs = getattr(args, 'part_subtitles', None)
            if isinstance(part_subs, str):
                part_subs = [s.strip() for s in part_subs.split(",") if s.strip()]
            html = process_h2(html, part_subtitles=part_subs)

            # 始终处理 H3 为时间线样式
            html = process_h3(html, style="timeline")
        if args.all or args.table:
            _tw = meta.get("table_widths") if meta else None
            html = process_table(html, table_widths=_tw)
        if args.all or args.lead:
            html = process_lead(html, cwd, args)
        if args.all or args.footer:
            html = process_footer(html)
        if args.all or getattr(args, 'wechat_compat', False):
            html = process_wechat_compat(html)

        # 最终清理：移除连续空行
        html = re.sub(r"\n{3,}", "\n\n", html)

        # 主题换皮（E-1）：把模板写死的默认色换成当前 profile 的主题色。
        # 默认 profile 下逐项自换自、整体 no-op。放在最后一步，确保覆盖所有组件产出。
        html = process_theme(html)

        Path(target).write_text(html, encoding="utf-8")
        log(f"🎉 处理完成，已保存至 {target}")
        try:
            import profile_config as _pc
            if _pc.using_example_profile():
                log("ℹ️  当前使用示例 profile（中性配色 + 占位署名）。"
                    "配置 SANSHENG_WRITE_PROFILE_DIR 换成你自己的品牌。")
        except Exception:
            pass

        # 交付附件：排版决策说明（P1-5，仅 --all 时；非关键路径，异常不阻断）
        if args.all:
            write_layout_decision(cwd, meta)

    # --check 自检（处理后或单独运行）
    if getattr(args, 'check', False):
        # 如果刚写入过，重新读取最新版本
        if has_processing:
            html = Path(target).read_text(encoding="utf-8")
        passed = print_check_results(*check_all(html, cwd, meta=meta))
        if not passed:
            sys.exit(1)


# ===== 【第 20 节】main() CLI 入口 =====
def main():
    parser = argparse.ArgumentParser(
        description="微信公众号排版后处理脚手架 v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python format_layout.py 定稿.html --all                  # 全量处理
  python format_layout.py 定稿.html --all --check           # 处理 + 预发布自检
  python format_layout.py 定稿.html --check                 # 仅自检（不修改文件）
  python format_layout.py 定稿.html --table --colors
  python format_layout.py 定稿.html --lead --lead-line1 "顶级模型点兵" --lead-line2 "视频生成篇"

配置文件:
  在文章目录放置 article-meta.yaml 可持久化导读栏参数、副标题等，
  避免中途插入时遗漏个性化配置。CLI 参数优先于 yaml 值。
        """,
    )

    parser.add_argument("file", help="目标 HTML 文件路径")
    parser.add_argument("--all", action="store_true", help="执行所有处理模块")
    parser.add_argument("--check", action="store_true", help="预发布自检（字符数/品牌色/组件完整性）")
    parser.add_argument("--h2", action="store_true", help="H2 转 PART 编号格式 + H3 转时间线格式")
    parser.add_argument("--part-subtitles", default=None,
                        help="PART 模式下各章节的灰色副标题，逗号分隔（如 \"产品逻辑,行业变局,用户画像\"）。不传则不显示副标题")
    parser.add_argument("--table", action="store_true", help="表格品牌化（绿头/列宽/字号）")
    parser.add_argument("--lead", action="store_true", help="注入导读栏")
    parser.add_argument("--lead-quote", action="store_true", help="导读引用块字号调整（--all 时自动执行）")
    parser.add_argument("--footer", action="store_true", help="注入推荐阅读+关注卡片")
    parser.add_argument("--colors", action="store_true", help="品牌色全局清洗")
    parser.add_argument("--prompts", action="store_true", help="清除 AI 生图提示词残留")
    parser.add_argument("--takeaway", action="store_true", help="将「划重点」引用块转换为品牌卡片组件")
    parser.add_argument("--stat", action="store_true", help="数字强调卡：<!-- stat: 数字|单位|说明 ; ... --> → 一行数字卡（--all 时自动）")
    parser.add_argument("--steps", action="store_true", help="步骤条：<!-- steps: 步骤1 || 步骤2 || ... --> → 竖排编号步骤（--all 时自动）")
    parser.add_argument("--compare", action="store_true", help="对比块：<!-- compare: 左标题|左内容 || 右标题|右内容 --> → 新旧双栏（--all 时自动）")
    parser.add_argument("--lists", action="store_true", help="列表重排版：无序→绿箭头➤、有序→H4圆形编号徽章，均悬挂缩进（--all 时自动执行）")
    parser.add_argument("--highlights", action="store_true", help="将 <mark> 转一级主题色、<mark class=2> 转二级主题色(同色相偏浅分主次)、粗斜体(***text***)走一级")
    parser.add_argument("--wechat-compat", action="store_true", dest="wechat_compat",
                        help="微信兼容性微调：图片圆角 8px + <p> 强制 color（--all 时自动执行）")
    # --skip-preflight 是首选名称（语义清晰）；--force 保留作 deprecated alias 不破坏老命令
    # 注意：dest 统一为 skip_preflight，下游引用 args.skip_preflight；旧调用 --force 仍 work
    parser.add_argument("--skip-preflight", "--force", action="store_true",
                        dest="skip_preflight",
                        help="跳过 preflight 检查（旧文档迁移用）。--force 是已废弃别名")

    # 导读栏自定义参数（也可通过 article-meta.yaml 配置）
    parser.add_argument("--lead-line1", help="导读栏标题第一行", default=None)
    parser.add_argument("--lead-line2", help="导读栏标题第二行", default=None)
    parser.add_argument("--lead-subtitle", help="导读栏副标题", default=None)
    parser.add_argument("--lead-tag1", help="导读栏胶囊标签1", default=None)
    parser.add_argument("--lead-tag2", help="导读栏胶囊标签2", default=None)

    args = parser.parse_args()

    # 无模块指定且无 --check 时默认 --all
    has_module = any([args.all, args.h2, args.table, args.lead, args.footer,
                      args.colors, args.prompts, args.takeaway,
                      getattr(args, 'lists', False),
                      getattr(args, 'highlights', False),
                      getattr(args, 'lead_quote', False),
                      getattr(args, 'wechat_compat', False)])
    if not has_module and not args.check:
        args.all = True

    run(args)


if __name__ == "__main__":
    main()
