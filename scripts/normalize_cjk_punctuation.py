#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_cjk_punctuation.py — 中文紧邻半角标点确定性转全角

背景（2026-06-04 固化）：正文写作若在中文之间误用半角 , ; : ! ?，会被
contracts.verify_cjk_punctuation 的「半角标点硬门」拦下（format_layout 预检 exit 2）。
该门是确定性谓词「中文字符紧邻半角标点了吗」，对应的修复也是确定性的——本脚本就是它的
逆操作，把命中处的半角标点换成全角，零歧义、零误伤。半角门保留作最终校验。

判定集与 gate 完全对齐：
  - 只转 , ; : ! ? 五种 → ， ； ： ！ ？
  - **不转半角句号 .**（与小数点 / 版本号 v3.5 / 扩展名 .mp4 冲突）
  - 时间 15:38 / 比例 16:9 因两侧是数字、非中文紧邻，天然不命中
保护域镜像 contracts._strip_for_scan（不在这些区域内转换）：
  frontmatter / 围栏代码 ``` / 行内代码 ` / HTML 标签与注释 / 图片 ![alt](url) 整体
  / 普通链接的 (url) 部分（保留可见 [text] 仍参与转换）/ 裸 http(s) URL / 引用行 >

用法：
  python normalize_cjk_punctuation.py 定稿.md           # 原地转换，打印 before/after
  python normalize_cjk_punctuation.py 定稿.md --check    # 只报告命中数，不写盘
"""
import argparse
import re
import sys
from pathlib import Path

# Windows GBK 控制台下 print 含 emoji/全角会 UnicodeEncodeError（成功路径也会崩、退出码非0），
# 强制 stdout/stderr UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

FULL = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？"}
CJK = r"[一-鿿]"
PAIR = re.compile(CJK + r"[,;:!?]|[,;:!?]" + CJK)


def _mask_protected(text: str):
    """把不该转换的区域替换成占位符，返回 (masked_text, masks)。"""
    masks = []

    def stash(s: str) -> str:
        masks.append(s)
        return f"\x00{len(masks) - 1}\x00"

    # 顺序要紧：frontmatter → 代码块 → 注释 → 标签 → 图片整体 → 链接 url → 行内代码 → 裸 url
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", lambda m: stash(m.group(0)), text,
                  count=1, flags=re.DOTALL)
    text = re.sub(r"```[\s\S]*?```", lambda m: stash(m.group(0)), text)
    text = re.sub(r"<!--.*?-->", lambda m: stash(m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", lambda m: stash(m.group(0)), text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", lambda m: stash(m.group(0)), text)  # 图片含 alt 整体保护
    text = re.sub(r"\]\(([^)]*)\)", lambda m: "](" + stash(m.group(1)) + ")", text)  # 普通链接仅遮 url
    text = re.sub(r"`[^`\n]+`", lambda m: stash(m.group(0)), text)
    text = re.sub(r"https?://\S+", lambda m: stash(m.group(0)), text)
    return text, masks


def _convert_segment(seg: str) -> str:
    # 中文,中文 这类标点两侧都命中，需循环到稳定（非重叠匹配一次只吃一边）
    prev = None
    cur = seg
    while prev != cur:
        prev = cur
        cur = PAIR.sub(lambda m: "".join(FULL.get(c, c) for c in m.group(0)), cur)
    return cur


def normalize(text: str) -> str:
    masked, masks = _mask_protected(text)
    out = []
    for ln in masked.split("\n"):
        # 2026-06-25：引用块也转。本 skill 的 `>` 块绝大多是「我方组件」
        # （导读栏 / 划重点 / 选型文本框 / 产物自取），中文标点该全角；中文语境下
        # 外部引用同样应全角。半角门 / _count_hits 仍宽松跳过 `>`（不因引用半角而
        # 阻塞发布），normalize 这里更激进、做完清理——二者刻意非对称（门松、清理全）。
        out.append(_convert_segment(ln))
    res = "\n".join(out)
    for i, s in enumerate(masks):  # 还原保护区
        res = res.replace(f"\x00{i}\x00", s)
    return res


def _count_hits(text: str) -> int:
    """与 gate 等价的命中计数：清洗保护域后数中文紧邻半角对。"""
    masked, _ = _mask_protected(text)
    scan = "\n".join(ln for ln in masked.split("\n") if not ln.lstrip().startswith(">"))
    return len(PAIR.findall(scan))


def main() -> int:
    ap = argparse.ArgumentParser(description="中文紧邻半角标点转全角（半角标点门的确定性逆操作）")
    ap.add_argument("file", help="目标 .md 文件")
    ap.add_argument("--check", action="store_true", help="只报告命中数，不写盘")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ 文件不存在：{p}")
        return 2

    text = p.read_text(encoding="utf-8")
    before = _count_hits(text)
    if args.check:
        print(f"半角标点门命中：{before} 处" + ("" if before else "（已合规）"))
        return 1 if before else 0

    if before == 0:
        print("✅ 中文间无半角标点，无需转换")
        return 0

    fixed = normalize(text)
    after = _count_hits(fixed)
    p.write_text(fixed, encoding="utf-8")
    print(f"✅ 已转换：{before} → {after} 处（{p.name}）")
    if after:
        print(f"⚠️ 仍残留 {after} 处，请人工核查（可能在保护域边界）")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
