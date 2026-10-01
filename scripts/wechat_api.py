"""微信公众号官方 API 发草稿：内置实现，只用标准库（图片压缩用 Pillow，按需导入）。

取代此前经 bun 调用 baoyu-post-to-wechat 的 ``wechat-api.ts``。只用四个官方接口：
``cgi-bin/token`` → ``media/uploadimg``（正文图）→ ``material/add_material``（封面）→ ``draft/add``。
终点仍是草稿箱，不发布；未认证账号本来也没有发布接口。

与旧实现的关键区别：
- 任何一张图上传失败都是硬错误（旧实现把失败吞掉，草稿里留着本地路径）。
- 返回结构化结果（封面 media_id 与每张图的上传结果），不再匹配 stderr 文本。
- access_token 在磁盘上缓存到过期前，避免触碰每日取 token 次数限制。

IP 白名单：所有接口都要求调用机器的公网 IP 在公众平台后台白名单内（40164 / 40165 会给出提示）。
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

API_BASE = os.environ.get("SANSHENG_WRITE_WECHAT_API_BASE", "https://api.weixin.qq.com").rstrip("/")
BODY_IMAGE_MAX_BYTES = 1024 * 1024  # 正文图接口上限 1MB
BODY_EXTS = {".jpg", ".jpeg", ".png", ".gif"}
TOKEN_SAFETY_SECONDS = 300

ERRCODE_HINTS = {
    40001: "access_token 无效或已过期",
    40013: "AppID 不正确",
    40125: "AppSecret 不正确",
    40164: "调用机器的公网 IP 不在公众平台后台的 IP 白名单里（开发 → 基本配置 → IP 白名单）",
    40165: "调用机器的公网 IP 不在白名单里",
    40005: "文件类型不受支持（正文图只收 jpg / png / gif）",
    40009: "图片尺寸或大小超限",
    45009: "接口调用次数达到上限",
    48001: "该账号没有此接口权限（未认证账号无发布接口）",
    42001: "access_token 已过期",
}


class WechatError(RuntimeError):
    def __init__(self, message: str, *, errcode: int | None = None, step: str = ""):
        self.errcode, self.step = errcode, step
        super().__init__(message)


Http = Callable[[str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


def _bypass_proxy() -> None:
    """微信接口按白名单认 IP：不走代理，否则会以海外出口 IP 调用而被拒（40164）。"""
    for key in ("NO_PROXY", "no_proxy"):
        entries = [e.strip() for e in os.environ.get(key, "").split(",") if e.strip()]
        if "weixin.qq.com" not in entries:
            entries.append("weixin.qq.com")
        os.environ[key] = ",".join(entries)


def _check(result: dict[str, Any], step: str) -> dict[str, Any]:
    code = result.get("errcode")
    if code not in (None, 0):
        hint = ERRCODE_HINTS.get(int(code), "")
        raise WechatError(f"微信接口 {step} 失败：errcode={code} {result.get('errmsg', '')}" + (f"（{hint}）" if hint else ""),
                          errcode=int(code), step=step)
    return result


_OPENER: urllib.request.OpenerDirector | None = None  # 隧道开着时换成走 SOCKS5 的 opener


def _request(req: urllib.request.Request, step: str, timeout: float = 60) -> dict[str, Any]:
    _bypass_proxy()
    try:
        with (_OPENER.open(req, timeout=timeout) if _OPENER else urllib.request.urlopen(req, timeout=timeout)) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise WechatError(f"微信接口 {step} HTTP {exc.code}", step=step) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise WechatError(f"微信接口 {step} 连不上：{exc}", step=step) from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise WechatError(f"微信接口 {step} 返回的不是 JSON", step=step) from exc
    return _check(data, step)


def post_json(url: str, payload: dict[str, Any], step: str) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 中文不转义，微信按 UTF-8 存
    return _request(urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"}), step)


def post_file(url: str, field: str, filename: str, content_type: str, data: bytes, step: str) -> dict[str, Any]:
    boundary = "----sansheng" + uuid.uuid4().hex
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n").encode("utf-8")
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    return _request(urllib.request.Request(url, data=body, method="POST",
                                           headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}), step, timeout=120)


# ---------------- token ----------------
def _token_cache_path(app_id: str) -> Path:
    base = Path(os.environ.get("SANSHENG_WRITE_CACHE_DIR") or Path.home() / ".cache" / "sansheng-write")
    return base / f"wechat-token-{hashlib.sha256(app_id.encode()).hexdigest()[:12]}.json"


def access_token(app_id: str, secret: str, *, force: bool = False) -> str:
    cache = _token_cache_path(app_id)
    if not force and cache.is_file():
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if saved.get("expires_at", 0) - TOKEN_SAFETY_SECONDS > time.time() and saved.get("token"):
                return saved["token"]
        except (OSError, ValueError):
            pass
    query = urllib.parse.urlencode({"grant_type": "client_credential", "appid": app_id, "secret": secret})
    data = _request(urllib.request.Request(f"{API_BASE}/cgi-bin/token?{query}"), "token")
    token = data.get("access_token")
    if not token:
        raise WechatError("微信 token 响应缺 access_token", step="token")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"token": token, "expires_at": time.time() + int(data.get("expires_in", 7200))}), encoding="utf-8")
        os.chmod(cache, 0o600)
    except OSError:
        pass  # 缓存写不进去不影响本次调用
    return str(token)


# ---------------- 图片 ----------------
def _prepare_body_image(path: Path) -> tuple[str, str, bytes, str]:
    """返回（文件名, 类型, 字节, 处理说明）。超过 1MB 或格式不收的图，缩到 1MB 以内。"""
    data = path.read_bytes()
    ext = path.suffix.lower()
    if ext in BODY_EXTS and len(data) <= BODY_IMAGE_MAX_BYTES:
        return path.name, mimetypes.guess_type(path.name)[0] or "image/png", data, ""
    try:
        from PIL import Image
    except ImportError as exc:
        raise WechatError(f"{path.name} 需要压缩或转格式，但没有安装 Pillow（python3 -m pip install Pillow）", step="uploadimg") from exc
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
        base = img.convert("RGBA" if has_alpha else "RGB")
        for width in (2560, 2048, 1600, 1280, 1024, 800, 640):
            frame = base.copy()
            if frame.width > width:
                frame = frame.resize((width, max(1, round(frame.height * width / frame.width))))
            if has_alpha:
                buf = io.BytesIO()
                frame.save(buf, "PNG", optimize=True)
                if buf.tell() <= BODY_IMAGE_MAX_BYTES:
                    return path.stem + ".png", "image/png", buf.getvalue(), f"压缩为 PNG {frame.width}px"
                frame = _flatten(frame)
            for quality in (88, 80, 72, 64):
                buf = io.BytesIO()
                frame.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
                if buf.tell() <= BODY_IMAGE_MAX_BYTES:
                    return path.stem + ".jpg", "image/jpeg", buf.getvalue(), f"压缩为 JPEG q{quality} {frame.width}px"
    raise WechatError(f"{path.name} 无法压缩到 1MB 以内", step="uploadimg")


def _flatten(image):
    from PIL import Image
    bg = Image.new("RGB", image.size, (255, 255, 255))
    bg.paste(image, mask=image.getchannel("A"))
    return bg


def upload_body_image(path: Path, token: str) -> dict[str, Any]:
    name, ctype, data, note = _prepare_body_image(path)
    url = f"{API_BASE}/cgi-bin/media/uploadimg?access_token={urllib.parse.quote(token)}"
    result = post_file(url, "media", name, ctype, data, "uploadimg")
    if not result.get("url"):
        raise WechatError(f"{path.name} 上传后没有返回图片地址", step="uploadimg")
    return {"path": str(path), "url": re.sub(r"^http://", "https://", str(result["url"])), "note": note}


def upload_cover(path: Path, token: str) -> dict[str, Any]:
    data = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "image/png"
    url = f"{API_BASE}/cgi-bin/material/add_material?access_token={urllib.parse.quote(token)}&type=image"
    result = post_file(url, "media", path.name, ctype, data, "add_material")
    if not result.get("media_id"):
        raise WechatError("封面上传后没有返回 media_id", step="add_material")
    return {"path": str(path), "media_id": str(result["media_id"])}


_IMG = re.compile(r"<img\b[^>]*?\bsrc=([\"'])(.*?)\1[^>]*>", re.I | re.S)
_LOCAL = re.compile(r"\sdata-local-path=([\"'])(.*?)\1", re.I)


def upload_html_images(html: str, base_dir: Path, token: str) -> tuple[str, list[dict[str, Any]]]:
    """把正文里的本地图片传到微信并换成远端地址。任何一张失败都抛错，不留本地路径。"""
    uploaded: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        tag, src = match.group(0), match.group(2).strip()
        if src.startswith("https://mmbiz.qpic.cn") or src.startswith("data:"):
            return tag
        local = _LOCAL.search(tag)
        ref = local.group(2) if local else src
        if re.match(r"https?://", ref, re.I) and not local:
            raise WechatError(f"正文图 {ref[:80]} 是外链，微信不收；请先下载到本地", step="uploadimg")
        path = Path(ref) if Path(ref).is_absolute() else (base_dir / urllib.parse.unquote(ref))
        if not path.is_file():
            raise WechatError(f"正文图不存在：{path}", step="uploadimg")
        key = str(path.resolve())
        if key not in uploaded:
            uploaded[key] = upload_body_image(path, token)
            results.append(uploaded[key])
        new = re.sub(r"(\bsrc=)([\"']).*?\2", lambda m: f'{m.group(1)}"{uploaded[key]["url"]}"', tag, count=1, flags=re.I | re.S)
        return _LOCAL.sub("", new)

    return _IMG.sub(replace, html), results


# ---------------- 草稿 ----------------
def add_draft(token: str, article: dict[str, Any]) -> str:
    url = f"{API_BASE}/cgi-bin/draft/add?access_token={urllib.parse.quote(token)}"
    result = post_json(url, {"articles": [article]}, "draft/add")
    if not result.get("media_id"):
        raise WechatError("draft/add 没有返回 media_id", step="draft/add")
    return str(result["media_id"])


@contextlib.contextmanager
def _tunnel():
    """开一条 SSH 隧道，让请求从白名单里的服务器出去。没配置时抛 WechatError。"""
    global _OPENER
    try:
        from . import wechat_tunnel as T
    except ImportError:  # pragma: no cover - direct script execution
        import wechat_tunnel as T
    cfg = T.tunnel_config()
    if not cfg:
        raise WechatError("本机出口不在公众号 IP 白名单，且没有配置 SSH 隧道（见 wechat_tunnel.py 顶部说明）", step="tunnel")
    try:
        with T.ssh_tunnel(cfg) as port:
            _OPENER = T.make_opener(port)
            try:
                yield
            finally:
                _OPENER = None
    except RuntimeError as exc:
        raise WechatError(f"SSH 隧道不可用：{exc}", step="tunnel") from exc


WHITELIST_ERRCODES = (40164, 40165)


def publish_draft(*, html: str, base_dir: Path, cover: Path, title: str, digest: str, app_id: str, secret: str,
                  author: str = "", source_url: str = "", open_comment: int = 1, fans_only_comment: int = 0) -> dict[str, Any]:
    """完整流程：token → 传正文图 → 传封面 → 建草稿。token 过期时自动换一次重试。"""
    def run(token: str) -> dict[str, Any]:
        content, images = upload_html_images(html, base_dir, token)
        cover_result = upload_cover(cover, token)
        article = {"article_type": "news", "title": title, "content": content, "thumb_media_id": cover_result["media_id"],
                   "need_open_comment": open_comment, "only_fans_can_comment": fans_only_comment}
        if author:
            article["author"] = author
        if digest:
            article["digest"] = digest
        if source_url:
            article["content_source_url"] = source_url
        media_id = add_draft(token, article)
        return {"media_id": media_id, "cover_media_id": cover_result["media_id"], "method": "api", "title": title,
                "images": images, "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}

    def attempt() -> dict[str, Any]:
        try:
            return run(access_token(app_id, secret))
        except WechatError as exc:
            if exc.errcode in (40001, 42001):
                return run(access_token(app_id, secret, force=True))
            raise

    mode = os.environ.get("SANSHENG_WRITE_WECHAT_TUNNEL", "").strip().lower()
    if mode == "always" and _OPENER is None:
        with _tunnel():
            return attempt()
    try:
        return attempt()  # 默认先从本机直连：本机出口在白名单里就不绕路
    except WechatError as exc:
        # 只有「出口不在白名单」才退到隧道（固定 IP 的服务器）；其他错误原样抛出，不掩盖。
        if mode == "off" or _OPENER is not None or exc.errcode not in WHITELIST_ERRCODES:
            raise
        with _tunnel():
            return attempt()
