#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_articles_md.py — 把 works.yaml 渲染成 <数据目录>/articles.md（自动生成的视图）。

articles.md 不再手维护：发布时由 pipeline 自动重生成（二期C 的刷新 hook）。
只收已发布作品（晨报等非作品不进；它们在 每日晨报/ 单独管理）。
"""
import os
import sys
import argparse
from pathlib import Path

try:  # Windows GBK 控制台兜底，避免 print emoji 抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(__file__))
from works_registry import load_works, works_path
import profile_config as pc


def articles_md_path():
    """当前 workspace 的 articles.md 派生视图。"""
    return works_path().parent / "articles.md"


# pipeline 仍可沿用 RAM.ARTICLES_MD；代理不会在 import 时锁死主仓。
ARTICLES_MD = pc.dynamic_path(articles_md_path)


def _brand_name():
    try:
        return pc.brand().get("name") or "作品库"
    except Exception:
        return "作品库"


def _esc(s):
    """转义表格单元里的 | ，避免破坏 markdown 列结构。"""
    return str(s).replace("|", "\\|")


def render_md(works):
    pub = [w for w in works if w.get("status") == "published" and w.get("wechat_url")]
    pub.sort(key=lambda w: w.get("date", ""), reverse=True)
    lines = [
        f"# {_brand_name()} · 已发布作品库",
        "",
        "> 本文件由 `works.yaml` 自动生成，**请勿手改**。改数据请改 works.yaml 后重跑 render_articles_md.py。",
        "",
        "---",
        "",
        "## 作品列表（按发布时间倒序）",
        "",
    ]
    for i, w in enumerate(pub, 1):
        lines += [
            f"### {i}. {w['title']}",
            "",
            "| 字段 | 内容 |",
            "|------|------|",
            f"| **编码** | {w.get('code', '')} |",
            f"| **标题** | {_esc(w['title'])} |",
            f"| **发布日期** | {w.get('date', '')} |",
        ]
        if w.get("cover"):
            lines.append(f"| **封面** | ![cover]({w['cover']}) |")
        lines.append(f"| **摘要** | {_esc(w.get('digest') or '暂无摘要')} |")
        lines.append(f"| **微信链接** | [查看文章]({w['wechat_url']}) |")
        video = w.get("video") or {}
        if video.get("status") in ("scripted", "published"):
            vurl = video.get("url", "")
            cell = video["status"] + (f" {vurl}" if vurl else "")
            lines.append(f"| **视频** | {cell} |")
        lines += ["", "---", ""]
    lines += [
        "## 文件信息",
        "",
        f"- **总作品数** -- {len(pub)} 篇",
        "- **更新方式** -- 由 works.yaml 自动生成（发布时刷新）",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="由作品库重建 articles.md")
    parser.add_argument("--dir", default=".", help="文章目录，用于绑定当前 worktree")
    args = parser.parse_args(argv)
    article_dir = Path(args.dir).expanduser().resolve()
    if not article_dir.is_dir():
        parser.error(f"文章目录不存在：{article_dir}")
    try:
        pc.bind_workspace(article_dir)
    except pc.WorkspaceBindingError as exc:
        parser.error(str(exc))
    output = Path(ARTICLES_MD)
    output.write_text(render_md(load_works()), encoding="utf-8")
    print(f"✅ articles.md 已由 works.yaml 重新生成 → {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
