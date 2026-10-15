#!/usr/bin/env python3
"""Validate browser handoff observations, including manual/CUA paths. No browser access.

This checks completeness and local asset hashes; observations must come from actual
UI readback. It cannot independently prove that an agent's observations are true.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def validate(data: dict, root: Path, requested: list[str]) -> list[str]:
    errors = []
    channels = data.get("channels", {})
    if not isinstance(channels, dict):
        return ["channels 必须为对象"]
    if not requested or any(c not in ("weibo", "x") for c in requested):
        return ["必须明确指定 weibo / x 渠道"]
    for name in requested:
        ch = channels.get(name)
        if not isinstance(ch, dict):
            errors.append(f"{name}: 缺浏览器回读")
            continue
        def need(ok, message):
            if not ok:
                errors.append(f"{name}: {message}")
        need(bool(data.get("observed_at")) and bool(data.get("method")), "缺观察时间或方法")
        need(ch.get("send_clicked") is False, "必须明确未点击最终发送")
        need(ch.get("text_readback_verified") is True, "文字尚未回读核对")
        assets = ch.get("assets", [])
        need(isinstance(assets, list) and bool(assets), "缺本地素材清单")
        for item in assets if isinstance(assets, list) else []:
            if not isinstance(item, dict):
                need(False, "素材条目必须为对象")
                continue
            path = root / item.get("path", "")
            need(path.is_file(), f"文件不存在: {item.get('path')}")
            if path.is_file():
                need(hashlib.sha256(path.read_bytes()).hexdigest() == item.get("sha256"),
                     f"素材已漂移: {item.get('path')}")
        roles = [a.get("role") for a in assets if isinstance(a, dict)] if isinstance(assets, list) else []
        need("copy" in roles, "缺正文/文案文件")
        need(ch.get("media_order_verified") is True, "图片顺序/位置尚未回读核对")
        need(ch.get("send_button_enabled") is True, "发送入口未就绪")
        if name == "weibo":
            need(ch.get("product") == "image_text", "微博必须为图文")
            count = ch.get("images_uploaded", 0)
            need(isinstance(count, int) and 4 <= count <= 9, "微博实际上传图片须为 4–9 张")
            need(count == ch.get("images_expected"), "微博实际上传数与计划不一致")
            need(roles.count("image") == count, "本地图片清单与实际上传数不一致")
            need(str(ch.get("url", "")).startswith("https://weibo.com/"), "微博页面地址错误")
        else:
            need(ch.get("product") == "article", "X 必须为 Articles 长文章")
            need(bool(re.fullmatch(r"https://x\.com/compose/articles/edit/\d+(?:/focus)?", ch.get("url", ""))),
                 "X 必须是长文章草稿地址，普通短帖不算完成")
            need(roles.count("cover") == 1, "缺唯一封面文件")
            need(roles.count("body_image") == ch.get("body_images_uploaded"), "正文图文件清单与实际上传数不一致")
            need(roles.count("caption") == 1, "缺推荐说明文件")
            for item in assets if isinstance(assets, list) else []:
                if isinstance(item, dict) and item.get("role") == "caption":
                    caption_path = root / item.get("path", "")
                    need(caption_path.is_file() and bool(caption_path.read_text(encoding="utf-8").strip()), "推荐说明文件为空")
            need(ch.get("cover_verified") is True, "封面尚未核对")
            need(ch.get("body_images_uploaded") == ch.get("body_images_expected")
                 and isinstance(ch.get("body_images_expected"), int), "正文图片数量不一致或未登记")
            need(ch.get("body_structure_verified") is True, "正文层级尚未核对")
            need(ch.get("placeholders_remaining") == 0, "正文仍有占位符或未检查")
            need(ch.get("preview_verified") is True, "尚未完成预览核对")
            need(ch.get("caption_prefilled") is True, "推荐短说明尚未预填")
            need(ch.get("caption_readback_verified") is True, "推荐短说明尚未回读")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article_dir", type=Path)
    parser.add_argument("--only", required=True, help="明确列出本次渠道，如 weibo,x")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    path = args.receipt or args.article_dir / "过程记录/_social-browser-handoff.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("回执必须是对象")
        errors = validate(data, args.article_dir, args.only.split(","))
    except (OSError, ValueError, TypeError) as exc:
        errors = [str(exc)]
    print(json.dumps({"ready": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
