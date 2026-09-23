#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tweet_evidence.py -- 抓取推特(X)证据：原文、时间、作者、引用、视频直链与截图。

写「模型发布当夜快讯」一类文章时，常要把 X 上官方/网友的帖子固化成可复核证据：
原文全文、准确发布时间（UTC + 北京时间）、作者、引用帖、视频直链，以及一张能
直接放进公众号正文的截图。第 108 篇是手搓验证过一遍的做法，这里收成脚本。

数据源两处，都不需要登录：
  1. 全文/时间/作者/引用/媒体 —— `cdn.syndication.twimg.com/tweet-result` 匿名端点，
     是 X 官方 embed（Tweet.html / oembed）背后实际调用的接口。字段形状见
     `_parse_node`；已用真实推文验证过（created_at 形如
     `2026-09-22T16:31:01.000Z`，video_info.variants 按 bitrate 区分清晰度）。
  2. 截图 —— Playwright 打开 X 官方 embed 页 `platform.twitter.com/embed/Tweet.html`，
     等 `article` 元素出现再等约 2.5 秒（图片/头像异步加载），对该元素截图。

用法：
    python tweet_evidence.py --out <文章目录>/素材 <推文URL或ID> [<推文URL或ID> ...]
    python tweet_evidence.py --out 素材 2102435511222890900 --video
    python tweet_evidence.py --out 素材 https://x.com/user/status/123 --no-screenshot

参数：
    --out PATH          输出目录（必填），通常是 `<文章目录>/素材`
    --no-screenshot      跳过截图（只要文字证据、省浏览器开销时用）
    --video               额外下载每条推文最高码率 mp4 到 `<out>/video/`
                          （JSON 里的 videos 字段始终记直链，与是否下载无关）
    --prefix PREFIX      截图文件名前缀，默认 shot-tw-（与 image-routing.md
                          「作者供图」`shot-` 前缀约定同源，不会被误判成生成图）

单条推文抓取失败不影响其余；失败条目仍写入 JSON（带 error 字段）与终端汇总。
重复运行按推文 id 合并更新已有的 tweet-evidence.json，不重复追加；已被人工
标注过的 employee 字段（脚本自己永远只写 null）在合并时予以保留。

退出码：0 全部成功 / 1 部分失败 / 2 全部失败。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    _BJT = ZoneInfo("Asia/Shanghai")
except Exception:                                     # pragma: no cover - 极端环境缺 tzdata
    _BJT = timezone(timedelta(hours=8))

# Windows GBK 控制台吃不下 ✓/✗/⚠ 等符号，统一把标准输出重配为 UTF-8 容错模式
# （与 podcast_episode.py / compress_images.py 同源防护）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SYNDICATION_URL_TMPL = "https://cdn.syndication.twimg.com/tweet-result?id={id}&token=4&lang=en"
EMBED_URL_TMPL = (
    "https://platform.twitter.com/embed/Tweet.html?id={id}&theme=light&lang=zh-cn&dnt=true"
)
_USER_AGENT = "Mozilla/5.0 (compatible; sansheng-write-tweet-evidence/1.0)"

DEFAULT_SCREENSHOT_PREFIX = "shot-tw-"
EVIDENCE_JSON_NAME = "tweet-evidence.json"
EVIDENCE_MD_NAME = "推文证据.md"
VIDEO_SUBDIR = "video"

SCREENSHOT_VIEWPORT_WIDTH = 560
SCREENSHOT_DEVICE_SCALE = 2
SCREENSHOT_EXTRA_WAIT_MS = 2500
SCREENSHOT_NAV_TIMEOUT_MS = 30_000

FETCH_TIMEOUT_SECONDS = 20
VIDEO_DOWNLOAD_TIMEOUT_SECONDS = 180

_ID_RE = re.compile(r"^\d+$")
_URL_ID_RE = re.compile(
    r"^(?:https?://)?(?:www\.|mobile\.|m\.)?(?:x\.com|twitter\.com)/(?:[^/?#]+/)+status/(\d+)",
    re.I,
)
_HANDLE_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")


def log(msg: str) -> None:
    print(f"[tweet-evidence {datetime.now():%H:%M:%S}] {msg}", flush=True)


# ===== 纯函数：URL / ID 解析 =====

def extract_tweet_id(ref: str) -> str:
    """从推文 URL 或纯数字 ID 里解析出推文 id_str。

    接受：纯数字 ID；`x.com`/`twitter.com` 的 `/status/<id>` 链接（可选
    scheme、可选 www./mobile./m. 子域、`/i/web/status/<id>` 这类多段路径、
    以及链接后面挂的查询串或 `/photo/1` 等尾段都会被忽略）。解析不出来
    就报中文错误，不静默返回空串——空 id 会让后续请求打到无意义的 URL 上。
    """
    text = str(ref or "").strip()
    if not text:
        raise ValueError("推文引用不能为空")
    if _ID_RE.match(text):
        return text
    m = _URL_ID_RE.match(text)
    if m:
        return m.group(1)
    raise ValueError(f"无法从「{text}」解析出推文 ID：需要 x.com/twitter.com 链接或纯数字 ID")


# ===== 纯函数：时间转换 =====

def parse_created_at(value: str) -> datetime:
    """解析 syndication 接口的 created_at：UTC ISO，形如 `2026-09-22T16:31:01.000Z`。"""
    text = str(value or "").strip()
    if not text:
        raise ValueError("created_at 为空")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_utc_str(value: str) -> str:
    return parse_created_at(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_beijing_str(value: str) -> str:
    """UTC ISO → 北京时间 `YYYY-MM-DD HH:MM`（固定 UTC+8，不依赖本机时区）。"""
    return parse_created_at(value).astimezone(_BJT).strftime("%Y-%m-%d %H:%M")


# ===== 纯函数：最高码率视频挑选 =====

def pick_video_variants(media_details: list) -> list[str]:
    """每个媒体项里挑最高码率的 mp4 直链；纯图片 / 只有 m3u8 的项跳过。"""
    urls: list[str] = []
    for media in media_details or []:
        if not isinstance(media, dict):
            continue
        variants = ((media.get("video_info") or {}).get("variants")) or []
        best_url, best_bitrate = "", -1
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            if variant.get("content_type") != "video/mp4":
                continue
            bitrate = variant.get("bitrate")
            bitrate = int(bitrate) if isinstance(bitrate, (int, float)) else 0
            if bitrate > best_bitrate:
                best_bitrate = bitrate
                best_url = str(variant.get("url") or "")
        if best_url:
            urls.append(best_url)
    return urls


# ===== 纯函数：syndication JSON → 记录 =====

def _parse_node(node: dict) -> dict:
    """把 syndication 接口的一层推文节点（顶层推文或 quoted_tweet）转成统一记录。

    quoted 字段与本函数返回值同结构（递归），因为「同一条 X 帖子」这个概念
    在顶层推文和它引用的推文上完全对称；screenshot 只有顶层会被真正填值——
    引用贴的画面已经包含在顶层截图里，这里留 null 只是保持结构一致，方便
    JSON 消费方不必区分「顶层 record」和「quoted record」两套 schema。
    """
    tweet_id = str(node.get("id_str") or node.get("id") or "").strip()
    user = node.get("user") or {}
    handle = str(user.get("screen_name") or "").strip()
    name = str(user.get("name") or "").strip()
    created_raw = str(node.get("created_at") or "").strip()
    created_utc = to_utc_str(created_raw) if created_raw else ""
    created_bjt = to_beijing_str(created_raw) if created_raw else ""
    text = str(node.get("text") or "").strip()

    if handle and tweet_id:
        url = f"https://x.com/{handle}/status/{tweet_id}"
    elif tweet_id:
        url = f"https://x.com/i/status/{tweet_id}"
    else:
        url = ""

    quoted_raw = node.get("quoted_tweet")
    quoted = _parse_node(quoted_raw) if isinstance(quoted_raw, dict) and quoted_raw else None

    return {
        "id": tweet_id,
        "url": url,
        "handle": handle,
        "name": name,
        "created_at_utc": created_utc,
        "created_at_bjt": created_bjt,
        "text": text,
        "quoted": quoted,
        "videos": pick_video_variants(node.get("mediaDetails") or []),
        "screenshot": None,
        "employee": None,
    }


def parse_tweet_payload(payload: dict) -> dict:
    """syndication 接口返回的整条 JSON → 标准记录（供 CLI 与测试共用的唯一入口）。"""
    return _parse_node(payload or {})


# ===== 纯函数：文件名生成 =====

def _sanitize_handle(handle: str) -> str:
    cleaned = _HANDLE_SAFE_RE.sub("", str(handle or "").lstrip("@"))
    return cleaned or "unknown"


def _id_tail(tweet_id: str, length: int = 6) -> str:
    tweet_id = str(tweet_id or "")
    return tweet_id[-length:] if len(tweet_id) > length else tweet_id or "0"


def screenshot_filename(prefix: str, handle: str, tweet_id: str) -> str:
    return f"{prefix}{_sanitize_handle(handle)}-{_id_tail(tweet_id)}.png"


def video_filename(handle: str, tweet_id: str, index: int, total: int) -> str:
    stem = f"{_sanitize_handle(handle)}-{_id_tail(tweet_id)}"
    return f"{stem}.mp4" if total <= 1 else f"{stem}-{index + 1}.mp4"


# ===== 纯函数：JSON 合并去重 =====

def _merge_key(record: dict) -> str:
    rid = str(record.get("id") or "").strip()
    return rid if rid else f"ref:{record.get('url') or ''}"


def merge_records(existing: list, updates: list) -> list[dict]:
    """按推文 id 合并更新，保持原有顺序、新记录追加在末尾，不重复追加同一 id。

    人工标注的 employee 字段是这份证据存在的意义之一（脚本自己永远只写
    null，员工身份要靠人核实）；重跑脚本补抓另一条推文时，如果旧记录已被
    标注过而这次的新记录没给值（脚本产的必然如此），保留旧值——否则每次
    重跑都会把人工标注悄悄冲掉，而这个错误在 diff 里几乎看不出来。
    """
    order: list[str] = []
    by_key: dict[str, dict] = {}
    for rec in existing or []:
        if not isinstance(rec, dict):
            continue
        key = _merge_key(rec)
        if key not in by_key:
            order.append(key)
        by_key[key] = rec
    for rec in updates or []:
        if not isinstance(rec, dict):
            continue
        key = _merge_key(rec)
        merged = dict(rec)
        prior = by_key.get(key)
        if prior is not None and merged.get("employee") is None and prior.get("employee") is not None:
            merged["employee"] = prior["employee"]
        if key not in by_key:
            order.append(key)
        by_key[key] = merged
    return [by_key[k] for k in order]


# ===== 纯函数：Markdown 渲染 =====

def render_markdown(records: list) -> str:
    lines = ["# 推文证据", ""]
    for rec in records or []:
        if rec.get("error"):
            lines.append(f"## {rec.get('url') or rec.get('id') or '未知推文'}")
            lines.append(f"- 抓取失败：{rec['error']}")
            lines.append("")
            continue
        name = str(rec.get("name") or "").strip()
        handle = str(rec.get("handle") or "").strip()
        header = f"{name} @{handle}".strip() if handle else (name or str(rec.get("id") or "未知作者"))
        lines.append(f"## {header}")
        lines.append(f"- 北京时间：{rec.get('created_at_bjt', '')}（UTC {rec.get('created_at_utc', '')}）")
        lines.append(f"- 链接：{rec.get('url', '')}")
        text = str(rec.get("text") or "").strip()
        if text:
            lines.append("")
            lines.extend(f"> {line}" for line in text.splitlines())
        quoted = rec.get("quoted")
        if quoted:
            q_header = f"{quoted.get('name', '')} @{quoted.get('handle', '')}".strip()
            lines.append(f"- 引用：{q_header}：{str(quoted.get('text') or '').strip()}")
        for i, video_url in enumerate(rec.get("videos") or [], 1):
            lines.append(f"- 视频直链 {i}：{video_url}")
        shot = rec.get("screenshot")
        lines.append(f"- 截图：{shot if shot else '（未截图）'}")
        lines.append("")
    lines.append("> ⚠ 员工身份需人工标注：以上 employee 字段均为占位 null，"
                 "请在核实后回填到 tweet-evidence.json。")
    return "\n".join(lines).rstrip() + "\n"


# ===== IO：读写证据文件 =====

def load_existing_records(json_path: Path) -> list[dict]:
    if not json_path.is_file():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def write_evidence_json(json_path: Path, records: list[dict]) -> None:
    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ===== 网络 / 浏览器调用（全部集中在这三个函数，测试用 monkeypatch 整体替换）=====

def fetch_tweet_json(tweet_id: str, *, timeout: float = FETCH_TIMEOUT_SECONDS) -> dict:
    """调用 syndication 匿名端点拿整条推文的结构化数据。不需要登录/Cookie。"""
    url = SYNDICATION_URL_TMPL.format(id=urllib.parse.quote(str(tweet_id), safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:                              # noqa: BLE001 - 读 body 失败不影响报错
            pass
        detail = ""
        try:
            detail = str(json.loads(body).get("error") or "").strip()
        except (json.JSONDecodeError, AttributeError, TypeError):
            detail = ""
        if e.code == 404:
            raise RuntimeError("推文不存在或已删除（HTTP 404）") from e
        raise RuntimeError(f"接口返回 HTTP {e.code}" + (f"：{detail}" if detail else "")) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络请求失败：{str(getattr(e, 'reason', e))[:200]}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"响应不是合法 JSON：{str(e)[:120]}") from e
    if not isinstance(data, dict) or "text" not in data or "user" not in data:
        typename = str(data.get("__typename") or "") if isinstance(data, dict) else ""
        hint = f"（{typename}）" if typename else ""
        raise RuntimeError(f"接口未返回可用推文数据{hint}，可能已被删除/设为保护账号/需要登录查看")
    return data


def capture_screenshot(tweet_id: str, out_path: Path,
                        *, nav_timeout_ms: int = SCREENSHOT_NAV_TIMEOUT_MS) -> None:
    """用 Playwright 打开 X 官方 embed 页，对渲染完成的 <article> 截图。

    只在函数内部 import playwright：模块本身要能在没装 playwright 的机器上
    被正常 import 并跑纯函数测试，只有真正需要截图这一步才要求装它。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "未安装 playwright，请先执行：pip install playwright && playwright install chromium"
        ) from exc

    url = EMBED_URL_TMPL.format(id=urllib.parse.quote(str(tweet_id), safe=""))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": SCREENSHOT_VIEWPORT_WIDTH, "height": 900},
                device_scale_factor=SCREENSHOT_DEVICE_SCALE,
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=nav_timeout_ms, wait_until="domcontentloaded")
                page.wait_for_selector("article", timeout=nav_timeout_ms)
                page.wait_for_timeout(SCREENSHOT_EXTRA_WAIT_MS)
                page.locator("article").first.screenshot(path=str(out_path))
            finally:
                context.close()
        finally:
            browser.close()


def download_video(url: str, out_path: Path, *, timeout: float = VIDEO_DOWNLOAD_TIMEOUT_SECONDS) -> None:
    """下载单个 mp4 直链，先写临时文件再原子替换，避免半截文件被当成有效产物。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, tmp_path.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except (urllib.error.URLError, OSError) as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"视频下载失败：{str(getattr(e, 'reason', e))[:200]}") from e
    tmp_path.replace(out_path)


# ===== 单条推文的编排（网络 + 纯函数 + 落盘）=====

def process_ref(
    ref: str,
    *,
    out_dir: Path,
    want_screenshot: bool,
    want_video: bool,
    prefix: str,
) -> dict:
    """处理一条推文引用；任何一步失败都返回带 error 字段的记录，不抛出。"""
    try:
        tweet_id = extract_tweet_id(ref)
    except ValueError as e:
        return {"id": None, "url": ref, "error": str(e)}

    try:
        payload = fetch_tweet_json(tweet_id)
    except RuntimeError as e:
        return {"id": tweet_id, "url": ref, "error": str(e)}

    record = parse_tweet_payload(payload)

    if want_screenshot:
        shot_name = screenshot_filename(prefix, record["handle"], record["id"])
        shot_path = out_dir / shot_name
        try:
            capture_screenshot(record["id"], shot_path)
            record["screenshot"] = shot_name
        except Exception as e:                        # noqa: BLE001 - 截图失败不能丢掉已拿到的文字证据
            log(f"  ⚠ 截图失败（{ref}）：{str(e)[:200]}")

    if want_video and record["videos"]:
        video_dir = out_dir / VIDEO_SUBDIR
        total = len(record["videos"])
        for i, video_url in enumerate(record["videos"]):
            dest = video_dir / video_filename(record["handle"], record["id"], i, total)
            try:
                download_video(video_url, dest)
            except Exception as e:                    # noqa: BLE001 - 视频下载失败不影响文字/截图证据
                log(f"  ⚠ 视频下载失败（{ref} 第 {i + 1} 个）：{str(e)[:200]}")

    return record


# ===== CLI =====

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tweet_evidence.py",
        description="抓取推特(X)证据：原文/时间/作者/引用/视频直链/截图",
    )
    ap.add_argument("refs", nargs="+", metavar="URL_OR_ID",
                     help="推文 URL（x.com/twitter.com）或纯数字 ID，可给多个")
    ap.add_argument("--out", required=True, help="输出目录，通常是 <文章目录>/素材")
    ap.add_argument("--no-screenshot", action="store_true", help="跳过截图")
    ap.add_argument("--video", action="store_true",
                     help="额外下载每条推文最高码率 mp4 到 <out>/video/")
    ap.add_argument("--prefix", default=DEFAULT_SCREENSHOT_PREFIX,
                     help=f"截图文件名前缀，默认 {DEFAULT_SCREENSHOT_PREFIX}")
    args = ap.parse_args(argv)

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / EVIDENCE_JSON_NAME
    md_path = out_dir / EVIDENCE_MD_NAME

    results: list[dict] = []
    ok = 0
    for ref in args.refs:
        log(f"处理 {ref} …")
        record = process_ref(
            ref,
            out_dir=out_dir,
            want_screenshot=not args.no_screenshot,
            want_video=args.video,
            prefix=args.prefix,
        )
        results.append(record)
        if record.get("error"):
            log(f"  ✗ 失败：{record['error']}")
        else:
            ok += 1
            log(f"  ✓ {record.get('handle', '?')} / {record.get('created_at_bjt', '?')}")

    merged = merge_records(load_existing_records(json_path), results)
    write_evidence_json(json_path, merged)
    md_path.write_text(render_markdown(merged), encoding="utf-8")
    log(f"✓ 已写入 {json_path.name}（共 {len(merged)} 条）与 {md_path.name}")

    total = len(results)
    if ok == 0:
        log(f"✗ 全部 {total} 条失败")
        return 2
    if ok < total:
        failed = ", ".join(r.get("url") or r.get("id") or "?" for r in results if r.get("error"))
        log(f"⚠ {total - ok}/{total} 条失败：{failed}")
        return 1
    log(f"✓ 全部 {total} 条成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
