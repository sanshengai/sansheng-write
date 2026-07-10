#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""works_registry.py — 统一作品库 works.yaml 的读取/校验/写入。

单一数据源：<数据目录>/works.yaml，顶层结构 {works: [ {...}, ... ]}。
本模块是它的唯一读写入口；下游脚本（推荐卡 / 防重复 / 视频追踪）都经此读取。

数据目录 = 环境变量 SANSHENG_WRITE_DATA_DIR，未配置则 <仓根>/data/（见 profile_config.py）。
"""
import os
import re
import sys
import yaml
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import profile_config as pc

WORKS_FILE = pc.works_file()

# 受控分类码词表（5 主码 + ESS 软内容）；晨报不进库
CATEGORY_CODES = {"AIT", "TUT", "OBS", "ROB", "KID", "ESS"}

# 受控标签词表起步集（新题材受控扩词，统一术语：一律「AI」不写「人工智能」）
TAG_VOCAB = {
    "模型发布", "横评", "模型对比", "Claude", "GPT", "Gemini", "国产模型",
    "MCP", "工作流", "效率工具", "软件安利", "语音输入", "AI Agent", "开源",
    "行业趋势", "厂商战略", "定价", "岗位变迁",
    "机器人", "智能家电", "智能制造", "人形机器人",
    "育儿", "亲子创作", "AI工具", "设计",
    "报税", "跨界", "品牌", "发刊",
    "个人成长", "健康", "认知",
    "投资", "价值投资", "读书蒸馏", "AI蒸馏",
}

# --- 对外分类（reader-facing）：稳定英文 key → 展示中文名（改名不动数据）---
OUTWARD_CATEGORIES = {
    "tutorial": "教程",
    "news": "资讯",
    "picks": "精选",
    "insight": "洞察",
    "essay": "随笔",
    "industry": "行业",
}

# 内部码 → 对外分类默认建议：(建议 key 或 None, 是否需人工确认)
# 内部码语义：AIT=实测 / TUT=教程 / OBS=观察 / ROB=硬件 / KID=育儿 / ESS=随笔
# AIT(实测) 横跨 教程/资讯/精选/洞察，OBS 多数洞察偶有资讯 —— 二者必须人工判。
_OUTWARD_SUGGEST = {
    "TUT": ("tutorial", False),
    "ESS": ("essay", False),
    "KID": ("essay", False),
    "ROB": ("news", False),
    "OBS": ("insight", True),
    "AIT": (None, True),
}


def suggest_outward(category):
    """内部分类码 → (对外分类 key 或 None, 是否需人工确认)。未知/None 码 → (None, True)。"""
    return _OUTWARD_SUGGEST.get(category, (None, True))


VIDEO_STATUS = {"none", "scripted", "published"}
WORK_STATUS = {"draft", "published", "unpublished"}


def load_works(path=None):
    """读 works.yaml，返回 work 记录列表（文件或 works 键缺失则空列表）。"""
    p = Path(path or WORKS_FILE)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("works", []) or []


def save_works(works, path=None):
    """写回 works.yaml，沿用仓库 yaml.dump 约定（中文不转义、不排序、块风格）。"""
    Path(path or WORKS_FILE).write_text(
        yaml.dump({"works": works}, allow_unicode=True, sort_keys=False,
                  default_flow_style=False),
        encoding="utf-8",
    )


_CODE_RE = re.compile(r"^[A-Z]{2,4}-\d{2,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WECHAT_RE = re.compile(r"^https://mp\.weixin\.qq\.com/s/")
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def next_code(category, works):
    """该分类内的下一个 code（分类内独立计数，2 位补零，max+1 不回填空洞=永不复用）。"""
    nums = []
    for w in works:
        c = w.get("code") or ""
        if w.get("category") == category and c.startswith(category + "-"):
            tail = c.split("-", 1)[1]
            if tail.isdigit():
                nums.append(int(tail))
    n = (max(nums) + 1) if nums else 1
    return f"{category}-{n:02d}"


def upsert_work(record, path=None):
    """按 seq 新增或更新一条作品记录。
    - 已存在(同 seq)：合并字段；已冻结的 code 保留不变（发布即冻结铁律）。
    - 新记录：给了 category 且未给 code 时，自动分配分类内下一个 code。
    返回写入后的完整记录。
    """
    works = load_works(path)
    seq = record.get("seq")
    existing = next((w for w in works if w.get("seq") == seq), None)
    if existing is not None:
        if existing.get("code") and not record.get("code"):
            record = {**record, "code": existing["code"]}
        merged = {**existing, **record}
        works[works.index(existing)] = merged
        result = merged
    else:
        if record.get("category") and not record.get("code"):
            record = {**record, "code": next_code(record["category"], works)}
        works.append(record)
        result = record
    works.sort(key=lambda w: (w.get("seq") is None, w.get("seq") or 0))
    save_works(works, path)
    return result


def set_video(seq, video, path=None):
    """视频侧写入：更新指定 seq 作品的 video 块（合并）。返回更新后的记录，找不到返回 None。

    生产调用方：你的视频流程在收尾归档时。
    """
    works = load_works(path)
    rec = next((w for w in works if w.get("seq") == seq), None)
    if rec is None:
        return None
    rec["video"] = {**(rec.get("video") or {}), **(video or {})}
    save_works(works, path)
    return rec


def validate_works(works):
    """对 work 列表做硬规则校验，返回错误信息列表（空=通过）。"""
    errors = []
    seen_seq, seen_code = {}, {}
    all_codes = {w["code"] for w in works if w.get("code")}
    for w in works:
        tag = w.get("code") or f"seq={w.get('seq')}"
        for field in ("seq", "title", "status"):
            if w.get(field) in (None, ""):
                errors.append(f"[{tag}] 缺必填字段 {field}")
        status = w.get("status")
        if status not in WORK_STATUS:
            errors.append(f"[{tag}] status 非法: {status!r}，应为 {sorted(WORK_STATUS)}")
        seq = w.get("seq")
        if seq is not None:
            if seq in seen_seq:
                errors.append(f"[{tag}] seq {seq} 与 [{seen_seq[seq]}] 撞号")
            else:
                seen_seq[seq] = tag
        if status == "published":
            for field in ("date", "category", "code", "wechat_url"):
                if not w.get(field):
                    errors.append(f"[{tag}] 已发布但缺 {field}")
        if w.get("date") and not _DATE_RE.match(str(w["date"])):
            errors.append(f"[{tag}] date 格式应为 YYYY-MM-DD: {w['date']!r}")
        cat = w.get("category")
        if cat and cat not in CATEGORY_CODES:
            errors.append(f"[{tag}] category {cat!r} 不在词表 {sorted(CATEGORY_CODES)}")
        code = w.get("code")
        if code:
            if not _CODE_RE.match(code):
                errors.append(f"[{tag}] code 格式应为 大写字母前缀-数字（如 AIT-13）: {code!r}")
            if code in seen_code:
                errors.append(f"[{tag}] code {code} 与 [{seen_code[code]}] 撞号")
            else:
                seen_code[code] = tag
            prefix = code.split("-")[0]
            if cat and prefix != cat:
                errors.append(f"[{tag}] code 前缀 {prefix} 与 category {cat} 不一致")
        for t in (w.get("tags") or []):
            if t not in TAG_VOCAB:
                errors.append(f"[{tag}] 标签 {t!r} 不在受控词表（如需新增请改 TAG_VOCAB）")
        oc = w.get("outward_category")
        if oc and oc not in OUTWARD_CATEGORIES:
            errors.append(
                f"[{tag}] outward_category {oc!r} 不在词表 {sorted(OUTWARD_CATEGORIES)}"
            )
        url = w.get("wechat_url")
        if url and not _WECHAT_RE.match(url):
            errors.append(f"[{tag}] wechat_url 不是合法公众号链接: {url!r}")
        cover = w.get("cover")
        if cover and _DRIVE_RE.match(str(cover)):
            errors.append(f"[{tag}] cover 必须用相对路径（去掉盘符）: {cover!r}")
        video = w.get("video") or {}
        vstatus = video.get("status", "none")
        if vstatus not in VIDEO_STATUS:
            errors.append(f"[{tag}] video.status 非法: {vstatus!r}")
        if vstatus == "published" and not video.get("url"):
            errors.append(f"[{tag}] video.status=published 但缺 video.url")
        mi = w.get("merged_into")
        if mi and mi not in all_codes:
            errors.append(f"[{tag}] merged_into {mi!r} 指向不存在的 code")
    return errors


def outward_todo(works):
    """返回仍缺 outward_category 的 work 列表（空串也算缺失），供回填追踪。"""
    return [w for w in works if not w.get("outward_category")]


def apply_outward_defaults(works):
    """为缺 outward_category 的 work 就地补默认值（幂等：已有值一律不动、非破坏）。
    仅当 suggest_outward 给出非 None 且无需人工确认时才自动补。
    返回 (auto_filled, needs_review)，元素均为 (seq, code, key_or_None) 三元组：
      auto_filled : 已自动补默认值的
      needs_review: 需人工判的（AIT/OBS/未知码；key 为建议值或 None）
    """
    auto_filled, needs_review = [], []
    for w in works:
        if w.get("outward_category"):
            continue
        key, review = suggest_outward(w.get("category"))
        ident = (w.get("seq"), w.get("code"))
        if key and not review:
            w["outward_category"] = key
            auto_filled.append((ident[0], ident[1], key))
        else:
            needs_review.append((ident[0], ident[1], key))
    return auto_filled, needs_review
