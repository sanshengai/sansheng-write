#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板令牌一致性 lint —— 守 templates/*.html + bgm 脚本内嵌 HTML 不偏离 design-tokens SSOT。

背景（借鉴 gzh-design 的「源头关」思想，独立自研）：脚本生成的组件天然随 format_layout.py
常量全局变；但 9 个静态 templates/*.html + generate_article_bgm.py 内嵌 HTML 是手写字面
色值/圆角，改令牌要手工三处对齐、无守护。本 lint 把「模板色值/圆角是否偏离令牌」做成确定性关。

设计：调色板直接 import format_layout.py 的 Design Tokens 常量（自动跟随令牌变更，不另立真值）。
  ERROR = 平台硬违规（position/grid/var/@media/style/script/div/class/id）→ exit 1。
         （flex / float 已实测可用，不在禁列，见 wechat-compat §1.5）
  WARN  = 疑似色值漂移（非令牌调色板）/ 圆角脱 4 档 —— 信息性，供人工核，不阻断。

豁免：① HTML 注释（<!-- -->）内提及的样式不算真实代码；② mp-common-profile 关注卡是微信
      原生白名单组件，合法带 class/data-id（wechat-compat §10 第 14 条），整块豁免 class/id 检查。

用法: python lint_templates.py [skill-dir]   # 默认脚本上级目录
退出码: 1 = 有 ERROR; 0 = 通过。
"""
import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import format_layout as F  # 复用 Design Tokens 常量作为调色板 SSOT


def _norm(c):
    return c.strip().lower().replace(" ", "")


# 令牌色（来自 format_layout.py 常量，改令牌自动跟随）
TOKEN_COLORS = {_norm(c) for c in [
    F.BRAND_PRIMARY, F.BRAND_SECONDARY, F.TINT_CARD, F.TINT_SOFT, F.TINT_INSET,
    F.TINT_ROW, F.BORDER_CARD, F.BORDER_HAIR, F.LINE_TIMELINE,
    F.TEXT_BODY, F.TEXT_TITLE, F.TEXT_MUTED, F.TEXT_FAINT,
]}
NEUTRAL_COLORS = {_norm(c) for c in ["#ffffff", "#fefefe", "#fff", "#000000", "#000"]}
# 既有的、经确认的令牌外用色（新增令牌外色值前必须先在此登记并注明用途，否则 lint WARN）
DOCUMENTED_EXTRAS = {
    "#245a75": "quote-card 金句渐变的深绿档（同色相更深，仅用于渐变）",
    "#4a6b7a": "deep-read / link-card 的 URL 文字绿灰",
    "#f0652f": "generate_article_bgm.py 音频卡橙色 accent",
}
ALLOWED_EXACT = TOKEN_COLORS | NEUTRAL_COLORS | {_norm(c) for c in DOCUMENTED_EXTRAS}

def _hex_to_rgb(h: str) -> str:
    """#2F6F8F → '47,111,143'（供 rgba 族匹配用）。非法值返回空串。"""
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return ""
    try:
        return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return ""


# 允许的 rgba 族：主题色 / 纯黑 / 纯白 任意 alpha（半透明是通用手段，不算漂移）
# 主题色的 rgb 三元组由 BRAND_PRIMARY 推导 —— 换主题时自动跟随，不写死。
_RGBA_FAMILY = [re.compile(r"rgba\(0,0,0,[0-9.]+\)"), re.compile(r"rgba\(255,255,255,[0-9.]+\)")]
_primary_rgb = _hex_to_rgb(F.BRAND_PRIMARY)
if _primary_rgb:
    _RGBA_FAMILY.insert(0, re.compile(rf"rgba\({re.escape(_primary_rgb)},[0-9.]+\)"))

COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,6}\b|rgba?\([0-9,.\s]+\)")
RADIUS_RE = re.compile(r"border-radius:\s*([0-9]+)px", re.I)
RADIUS_OK = {0, 2, 6, 8, 10, 12, 999}  # 2 = 装饰短条（3-4px 高绿条）的半高微圆角；其余为 4 档尺度 + 全圆胶囊

# ERROR 级平台硬违规（flex/float 不在此列——已实测可用）
FORBIDDEN = [
    (re.compile(r"position\s*:\s*(fixed|absolute|sticky)", re.I), "position fixed/absolute/sticky 不支持"),
    (re.compile(r"display\s*:\s*grid", re.I), "display:grid 不支持（改 flex）"),
    (re.compile(r"var\s*\(\s*--", re.I), "CSS 变量 var(--x) 不支持，写死令牌值"),
    (re.compile(r"@(media|keyframes|import)", re.I), "@media/@keyframes/@import 不支持"),
    (re.compile(r"<style[\s>]", re.I), "<style> 标签会被过滤"),
    (re.compile(r"<script[\s>]", re.I), "<script> 标签会被过滤"),
    (re.compile(r"</?div[\s>]", re.I), "<div> 应改 <section>"),
    (re.compile(r"\sclass\s*=", re.I), "class 属性会被剥离（关注卡除外）"),
    (re.compile(r"\sid\s*=", re.I), "id 属性会被剥离"),
]
# 关注卡白名单标记：含这些标记的行豁免 class/id 检查
_PROFILE = re.compile(r"mp_profile|mpprofile|mp-common-profile|custom_select_card", re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _color_ok(c):
    n = _norm(c)
    if n in ALLOWED_EXACT:
        return True
    return any(rx.fullmatch(n) for rx in _RGBA_FAMILY)


def lint_text(name, text, css_checks=True):
    """返回 (errors, warns)。css_checks=False 时只查色值/圆角（用于 .py 内嵌 HTML，避免误配 Python 语法）。"""
    errors, warns = [], []
    body = _COMMENT.sub("", text)  # 剥 HTML 注释：注释里提及 div/position/id 不算真实代码

    if css_checks:
        # 关注卡 mp-common-profile 是微信白名单组件，合法带 class/data-id → 去掉标记行再查
        css_scan = "\n".join(ln for ln in body.splitlines() if not _PROFILE.search(ln))
        for rx, msg in FORBIDDEN:
            if rx.search(css_scan):
                errors.append(f"[{name}] ERROR: {msg}")

    seen = set()
    for m in COLOR_RE.finditer(body):
        c = m.group(0)
        if _norm(c) in seen:
            continue
        seen.add(_norm(c))
        if not _color_ok(c):
            warns.append(f"[{name}] WARN: 令牌外色值 {c}（design-tokens 无此值；确需则登记 DOCUMENTED_EXTRAS）")

    for m in RADIUS_RE.finditer(body):
        r = int(m.group(1))
        if r not in RADIUS_OK:
            warns.append(f"[{name}] WARN: border-radius {r}px 脱离 4 档尺度(6/8/10/12/999)")
    return errors, warns


def lint_all(root):
    """扫 templates/*.html（全检查）+ generate_article_bgm.py（仅色值/圆角）。返回 (errors, warns)。"""
    errors, warns = [], []
    for p in sorted(glob.glob(os.path.join(root, "templates", "*.html"))):
        e, w = lint_text(os.path.basename(p),
                         open(p, encoding="utf-8", errors="replace").read())
        errors += e
        warns += w
    bgm = os.path.join(root, "scripts", "generate_article_bgm.py")
    if os.path.exists(bgm):
        e, w = lint_text("generate_article_bgm.py",
                         open(bgm, encoding="utf-8", errors="replace").read(),
                         css_checks=False)
        errors += e
        warns += w
    return errors, warns


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else str(F.SCRIPT_DIR.parent)
    errors, warns = lint_all(root)
    n_tpl = len(glob.glob(os.path.join(root, "templates", "*.html")))
    print(f"📐 模板令牌一致性 lint：{n_tpl} 个模板 + bgm 脚本")
    if errors:
        print(f"\n❌ ERROR ×{len(errors)}（平台硬违规，必修）:")
        for e in errors:
            print(f"   • {e}")
    if warns:
        print(f"\n⚠️  WARN ×{len(warns)}（疑似令牌漂移，人工核）:")
        for w in warns:
            print(f"   • {w}")
    if not errors and not warns:
        print("✅ 全部模板色值/圆角对齐 design-tokens，无平台违规")
    elif not errors:
        print(f"\n✅ 无平台违规（ERROR 0）；{len(warns)} 条 WARN 供人工核")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
