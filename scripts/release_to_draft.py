#!/usr/bin/env python3
"""Single-entry WeChat draft release transaction with official readback."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import shlex
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .evidence import stable_digest
    from .profile_config import brand
except ImportError:  # pragma: no cover - direct script execution
    from evidence import stable_digest
    from profile_config import brand


ATTEMPT_FILE = "_release-attempt.json"
RECEIPT_FILE = "_publish-receipt.json"
Publisher = Callable[[dict[str, Any]], dict[str, Any]]
Reader = Callable[[str, dict[str, Any]], dict[str, Any]]
Preflight = Callable[[Path], tuple[dict[str, Any] | None, list[str]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_content(html: str) -> str:
    match = re.search(r'<div\s+id=["\']output["\'][^>]*>([\s\S]*?)</div>\s*</body>', html, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html, re.I)
    return match.group(1).strip() if match else html.strip()


def normalize_wechat_html(html: str) -> str:
    """Normalize only transformations expected from image uploading/transport."""
    content = _extract_content(str(html or ""))
    content = re.sub(
        r'(\bsrc\s*=\s*)(["\']).*?\2',
        lambda match: f'{match.group(1)}"<wechat-image>"',
        content,
        flags=re.I,
    )
    content = re.sub(r">\s+<", "><", content)
    content = re.sub(r"[\t\r\n ]+", " ", content)
    return content.strip()


def _body_digest(html: str) -> str:
    return hashlib.sha256(normalize_wechat_html(html).encode("utf-8")).hexdigest()


def _semantic_body_digest(html: str) -> str:
    """Bind visible text while allowing WeChat's documented HTML sanitization."""
    text = re.sub(r"<!--.*?-->", "", str(html or ""), flags=re.S)
    text = re.sub(
        r"<(?:br|/p|/section|/div|/h[1-6]|/li|/tr|/td|/th)\b[^>]*>",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\u00a0", " ")
    normalized = "".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _published_digest(digest: str) -> str:
    """Mirror baoyu-post-to-wechat's stable summary-length rule."""
    value = str(digest or "")
    if len(value) <= 120:
        return value
    truncated = value[:117]
    last_punct = max(
        truncated.rfind(mark) for mark in ("。", "，", "；", "、")
    )
    return (
        truncated[: last_punct + 1]
        if last_punct > 80
        else truncated + "..."
    )


def _image_count(html: str) -> int:
    return len(re.findall(r"<img\b", str(html or ""), flags=re.I))


# 微信 media/uploadimg 只认 jpg / png，其余一律 40005 invalid file type。
_WECHAT_UNSUPPORTED_SUFFIX = (".webp", ".avif", ".heic", ".heif", ".bmp", ".tiff", ".tif")


def _unsupported_local_images(html: str) -> list[str]:
    """正文里引用了微信不收的图片格式——发出去必然是坏图，发布前就拦。

    与 `_unuploaded_images` 的分工：这条在**推送前**看本地 HTML（能防患于未然、
    报错时还能指出该转哪几张），那条在**回读后**看远端（兜住其它原因的上传失败）。
    """
    bad: list[str] = []
    for match in re.finditer(
        r'<img[^>]*\s(?:data-local-path|src)=["\']([^"\']+)["\']',
        str(html or ""),
        flags=re.I,
    ):
        value = match.group(1).strip()
        if value.lower().endswith(_WECHAT_UNSUPPORTED_SUFFIX):
            name = value.replace("\\", "/").rsplit("/", 1)[-1]
            if name not in bad:
                bad.append(name)
    return bad


def _unuploaded_images(html: str) -> list[str]:
    """回读正文里仍指向本地路径的图片 src。

    🔴 2026-07-28 补。此前只有 `_image_count`（数 <img> 个数），而
    baoyu-post-to-wechat 的上传循环把失败 **catch 掉只打一行 stderr**，
    img 标签原样保留本地 src。于是「六张 .webp 全被微信以 40005
    invalid file type 拒收」这件事，连推三版都显示校验通过——数量对得上，
    可读者看到的是六个坏图。数量相等 ≠ 图传上去了，必须验 src 真的换成了远端地址。
    """
    bad: list[str] = []
    for match in re.finditer(
        r"<img[^>]*\ssrc=[\"']([^\"']+)[\"']", str(html or ""), flags=re.I
    ):
        src = match.group(1).strip()
        if not re.match(r"https?://", src, flags=re.I):
            bad.append(src[:80])
    return bad


def _load_meta(cwd: Path) -> tuple[dict[str, Any], list[str]]:
    path = cwd / "article-meta.yaml"
    try:
        meta = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}, ["缺 article-meta.yaml"]
    except Exception as exc:
        return {}, [f"article-meta.yaml 解析失败：{exc}"]
    if not isinstance(meta, dict):
        return {}, ["article-meta.yaml 顶层必须为对象"]
    return meta, []


def _source_url(meta: dict[str, Any], profile: dict[str, Any]) -> str:
    value = str(meta.get("source_url") or "").strip()
    publish = profile.get("publish") or {}
    if value == "treasure":
        return str(publish.get("source_url_treasure") or "").strip()
    if value == "default" or not value:
        return str(publish.get("source_url_default") or "").strip()
    return value


def build_expected_draft(cwd: Path) -> tuple[dict[str, Any] | None, list[str]]:
    meta, errors = _load_meta(cwd)
    html_path = cwd / "定稿.html"
    cover_path = cwd / "素材/cover.png"
    if not html_path.is_file():
        errors.append("缺 定稿.html")
    if not cover_path.is_file():
        errors.append("缺 素材/cover.png")
    title = str(meta.get("title") or "").strip()
    digest = str(meta.get("digest") or meta.get("description") or "").strip()
    if not title:
        errors.append("article-meta.yaml 缺 title")
    if not digest:
        errors.append("article-meta.yaml 缺 digest")
    if errors:
        return None, errors
    profile = brand()
    html = html_path.read_text(encoding="utf-8")
    content = _extract_content(html)
    unsupported = _unsupported_local_images(content)
    if unsupported:
        return None, [
            f"正文引用了 {len(unsupported)} 张微信不收的图片格式"
            f"（media/uploadimg 只认 jpg/png，其余返回 40005 invalid file type，"
            f"而上传器会吞掉这个失败、把本地路径原样留在正文里）：{unsupported}"
            "；跑一次 `compress_images.py <素材目录>` 会就地转 PNG 并改好引用",
        ]
    return {
        "title": title,
        "digest": digest,
        "author": str(meta.get("author") or profile.get("author") or "").strip(),
        "source_url": _source_url(meta, profile),
        "need_open_comment": int(meta.get("need_open_comment", 1)),
        "only_fans_can_comment": int(meta.get("only_fans_can_comment", 0)),
        "content": content,
        "body_digest": _body_digest(content),
        "image_count": _image_count(content),
        "cover_path": str(cover_path),
        "cover_sha256": hashlib.sha256(cover_path.read_bytes()).hexdigest(),
    }, []


def _find_skill_dir(name: str, explicit_env: str) -> Path | None:
    explicit = os.getenv(explicit_env, "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    home = Path.home()
    patterns = [
        f".codex/plugins/cache/baoyu-skills/**/skills/{name}",
        f".claude/plugins/cache/baoyu-skills/**/skills/{name}",
        f".agents/skills/{name}",
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(home.glob(pattern))
    valid = [path.resolve() for path in candidates if path.is_dir()]
    return max(valid, key=lambda path: path.stat().st_mtime) if valid else None


def _bun_command(entrypoint: Path) -> tuple[list[str] | None, list[str]]:
    bun = shutil.which("bun")
    if bun:
        return [bun, str(entrypoint)], []
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "bun", str(entrypoint)], []
    return None, ["未找到 bun 或 npx"]


def _parse_json_stdout(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    for index in [0, *reversed([i for i, char in enumerate(text) if char == "{"])]:
        try:
            payload = json.loads(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _default_publisher(cwd: Path) -> Publisher:
    skill_dir = _find_skill_dir("baoyu-post-to-wechat", "BAOYU_POST_TO_WECHAT_DIR")
    if not skill_dir:
        raise RuntimeError(
            "未找到 baoyu-post-to-wechat；请安装插件或设置 BAOYU_POST_TO_WECHAT_DIR"
        )
    command, errors = _bun_command(skill_dir / "scripts/wechat-api.ts")
    if errors or command is None:
        raise RuntimeError("; ".join(errors))

    def publish(expected: dict[str, Any]) -> dict[str, Any]:
        profile = brand()
        args = [
            *command,
            str(cwd / "定稿.html"),
            "--theme",
            "default",
            "--title",
            expected["title"],
            "--summary",
            expected["digest"],
            "--cover",
            str(cwd / "素材/cover.png"),
        ]
        author = expected.get("author")
        if author:
            args.extend(["--author", str(author)])
        source_url = expected.get("source_url")
        if source_url:
            args.extend(["--source-url", str(source_url)])
        color = str((profile.get("colors") or {}).get("primary") or "").strip()
        if color:
            args.extend(["--color", color])
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        payload = _parse_json_stdout(completed.stdout)
        if completed.returncode != 0 or not payload or not payload.get("media_id"):
            raise RuntimeError(
                f"baoyu-post-to-wechat 失败（exit={completed.returncode}）："
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        cover_match = re.search(
            r"Cover uploaded successfully,\s*media_id:\s*(\S+)",
            completed.stderr,
            flags=re.I,
        )
        if not cover_match:
            raise RuntimeError("publisher 未返回可核验的 cover media_id")
        return {
            "media_id": str(payload["media_id"]),
            "cover_media_id": cover_match.group(1),
            "method": str(payload.get("method") or "api"),
            "title": str(payload.get("title") or ""),
        }

    return publish


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _wechat_credentials(cwd: Path) -> tuple[str, str]:
    sources = [
        dict(os.environ),
        _parse_dotenv(cwd / ".baoyu-skills/.env"),
        _parse_dotenv(Path.home() / ".baoyu-skills/.env"),
    ]
    for source in sources:
        app_id = str(source.get("WECHAT_APP_ID") or "").strip()
        secret = str(source.get("WECHAT_APP_SECRET") or "").strip()
        if app_id and secret:
            return app_id, secret
    raise RuntimeError(
        "draft/get 缺 WECHAT_APP_ID / WECHAT_APP_SECRET；"
        "请配置环境变量、文章目录 .baoyu-skills/.env 或 ~/.baoyu-skills/.env"
    )


def _http_json(
    url: str, *, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"WeChat API 请求失败：{exc}") from exc
    if result.get("errcode") not in (None, 0):
        raise RuntimeError(
            f"WeChat API 错误 {result.get('errcode')}：{result.get('errmsg')}"
        )
    return result


def _external_reader_command() -> list[str] | None:
    raw = os.getenv("SANSHENG_WRITE_WECHAT_GET_COMMAND", "").strip()
    if not raw:
        return None
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise RuntimeError("SANSHENG_WRITE_WECHAT_GET_COMMAND 必须是字符串数组")
        return parsed
    return shlex.split(raw, posix=os.name != "nt")


def _default_reader(cwd: Path) -> Reader:
    external = _external_reader_command()
    if external:
        def read_external(media_id: str, expected: dict[str, Any]) -> dict[str, Any]:
            completed = subprocess.run(
                [*external, "--media-id", media_id],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            payload = _parse_json_stdout(completed.stdout)
            if completed.returncode != 0 or not payload:
                raise RuntimeError(
                    f"外部 draft/get 失败（exit={completed.returncode}）："
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                )
            return payload

        return read_external

    def read_official(media_id: str, expected: dict[str, Any]) -> dict[str, Any]:
        app_id, secret = _wechat_credentials(cwd)
        query = urllib.parse.urlencode(
            {
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": secret,
            }
        )
        token = _http_json(
            f"https://api.weixin.qq.com/cgi-bin/token?{query}"
        ).get("access_token")
        if not token:
            raise RuntimeError("WeChat token 响应缺 access_token")
        response = _http_json(
            "https://api.weixin.qq.com/cgi-bin/draft/get?"
            + urllib.parse.urlencode({"access_token": token}),
            payload={"media_id": media_id},
        )
        articles = response.get("news_item")
        if not isinstance(articles, list) or len(articles) != 1:
            raise RuntimeError(
                f"draft/get news_item 数量异常：{len(articles) if isinstance(articles, list) else '非列表'}"
            )
        return articles[0]

    return read_official


def _compare_readback(
    expected: dict[str, Any],
    actual: dict[str, Any],
    cover_media_id: str,
) -> tuple[dict[str, bool], list[str]]:
    pairs = {
        "title": (expected["title"], actual.get("title")),
        "digest": (_published_digest(expected["digest"]), actual.get("digest")),
        "author": (expected["author"], actual.get("author") or ""),
        "source_url": (
            expected["source_url"],
            actual.get("content_source_url") or "",
        ),
        "need_open_comment": (
            expected["need_open_comment"],
            actual.get("need_open_comment"),
        ),
        "only_fans_can_comment": (
            expected["only_fans_can_comment"],
            actual.get("only_fans_can_comment"),
        ),
    }
    checks = {
        name: str(wanted).strip() == str(got).strip()
        for name, (wanted, got) in pairs.items()
    }
    content = str(actual.get("content") or "")
    checks["body_digest"] = _semantic_body_digest(
        expected["content"]
    ) == _semantic_body_digest(content)
    checks["image_count"] = expected["image_count"] == _image_count(content)
    unuploaded = _unuploaded_images(content)
    checks["image_src_uploaded"] = not unuploaded
    checks["cover_media_id"] = (
        bool(cover_media_id)
        and cover_media_id == str(actual.get("thumb_media_id") or "")
    )
    errors = [f"draft/get 回读字段不一致：{name}" for name, ok in checks.items() if not ok]
    if unuploaded:
        # 单独给一条能直接照着修的报错：只说「image_src_uploaded 不一致」
        # 等于把人推回去逐张翻 HTML，而失败原因（微信拒收某种格式）就藏在文件名里。
        errors.append(
            f"以下 {len(unuploaded)} 张图未上传成功、仍指向本地路径"
            f"（微信只收 jpg/png，webp 会被 40005 拒收）：{unuploaded}"
        )
    return checks, errors


def release_to_draft(
    cwd: Path,
    *,
    preflight: Preflight,
    publisher: Publisher | None = None,
    reader: Reader | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Execute preflight → draft/add → draft/get as one resumable transaction."""
    cwd = cwd.resolve()
    try:
        job = json.loads((cwd / "_release-job.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["缺 _release-job.json；先运行 adopt-final"]
    except json.JSONDecodeError as exc:
        return None, [f"_release-job.json 解析失败：{exc}"]
    if job.get("scope") != "wechat-draft" or job.get("formal_publish") is not False:
        return None, ["release job 只允许 scope=wechat-draft 且 formal_publish=false"]

    ready, errors = preflight(cwd)
    if errors or ready is None:
        return None, errors
    ready_digest = str(ready.get("manifest_digest") or "")
    if not ready_digest:
        return None, ["preflight 未返回 publish-ready digest"]
    expected, expected_errors = build_expected_draft(cwd)
    if expected_errors or expected is None:
        return None, expected_errors
    expected_digest = stable_digest(expected)

    attempt_path = cwd / ATTEMPT_FILE
    attempt: dict[str, Any] = {}
    if attempt_path.is_file():
        try:
            old = json.loads(attempt_path.read_text(encoding="utf-8"))
            if (
                isinstance(old, dict)
                and old.get("publish_ready_digest") == ready_digest
                and old.get("expected_draft_digest") == expected_digest
                and old.get("draft_media_id")
            ):
                attempt = old
        except json.JSONDecodeError:
            pass
    resumed = bool(attempt)
    try:
        if not attempt:
            publish = publisher or _default_publisher(cwd)
            result = publish(expected)
            media_id = str(result.get("media_id") or "").strip()
            cover_media_id = str(result.get("cover_media_id") or "").strip()
            if not media_id or not cover_media_id:
                return None, ["publisher 响应缺 media_id 或 cover_media_id"]
            attempt = {
                "schema_version": 1,
                "created_at": _now(),
                "scope": "wechat-draft",
                "formal_publish": False,
                "publish_ready_digest": ready_digest,
                "expected_draft_digest": expected_digest,
                "draft_media_id": media_id,
                "cover_media_id": cover_media_id,
                "method": str(result.get("method") or ""),
            }
            # Critical crash boundary: persist the remote ID before any readback.
            attempt_path.write_text(
                json.dumps(attempt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        read = reader or _default_reader(cwd)
        actual = read(str(attempt["draft_media_id"]), expected)
    except Exception as exc:
        return None, [str(exc)]

    checks, compare_errors = _compare_readback(
        expected, actual, str(attempt.get("cover_media_id") or "")
    )
    if compare_errors:
        return None, compare_errors
    readback = {
        "checks": checks,
        "title": str(actual.get("title") or ""),
        "digest": str(actual.get("digest") or ""),
        "source_url": str(actual.get("content_source_url") or ""),
        "body_digest": _semantic_body_digest(str(actual.get("content") or "")),
        "image_count": _image_count(str(actual.get("content") or "")),
        "thumb_media_id": str(actual.get("thumb_media_id") or ""),
        "remote_digest": stable_digest(actual),
    }
    receipt = {
        "schema_version": 2,
        "sealed_at": _now(),
        "scope": "wechat-draft",
        "formal_publish": False,
        "draft_media_id": attempt["draft_media_id"],
        "cover_media_id": attempt["cover_media_id"],
        "publish_ready_digest": ready_digest,
        "expected_draft_digest": expected_digest,
        "manifest": ready.get("manifest") or {},
        "manifest_digest": stable_digest(ready.get("manifest") or {}),
        "remote_verified": True,
        "remote_readback": readback,
        "resumed_attempt": resumed,
    }
    (cwd / RECEIPT_FILE).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt, []
