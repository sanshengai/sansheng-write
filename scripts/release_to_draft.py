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
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .audio_cards import locate_theme_audio_record
    from .evidence import stable_digest
    from .profile_config import brand
except ImportError:  # pragma: no cover - direct script execution
    from audio_cards import locate_theme_audio_record
    from evidence import stable_digest
    from profile_config import brand


ATTEMPT_FILE = "_release-attempt.json"
RECEIPT_FILE = "_publish-receipt.json"
AUDIO_HANDOFF_FILE = "_wechat-audio-handoff.json"
AUDIO_RECEIPT_FILE = "_wechat-audio-receipt.json"
PUBLISHED_AUDIO_RECEIPT_FILE = "_wechat-published-audio-receipt.json"
Publisher = Callable[[dict[str, Any]], dict[str, Any]]
Reader = Callable[[str, dict[str, Any]], dict[str, Any]]
PublishedReader = Callable[[str, dict[str, Any]], dict[str, Any]]
Preflight = Callable[[Path], tuple[dict[str, Any] | None, list[str]]]
AUDIO_TAG = r"(?:mpvoice|mpaudio|mp-common-mpaudio)"


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


class _VisibleTextParser(HTMLParser):
    """Collect text nodes without confusing markup inside quoted attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def _semantic_body_digest(html: str) -> str:
    """Bind visible text while allowing WeChat's documented HTML sanitization."""
    text = _visible_text(html)
    normalized = "".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _visible_text(html: str) -> str:
    """Return human-visible text, including copyable plain-text URLs."""
    parser = _VisibleTextParser()
    parser.feed(str(html or ""))
    parser.close()
    text = "".join(parser.parts)
    return html_lib.unescape(text).replace("\u00a0", " ")


_BROKEN_INLINE_FONT_RE = re.compile(
    r'\bstyle\s*=\s*"[^>]*?\bfont-family\s*:\s*"',
    re.IGNORECASE,
)


def _promotion_contract(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Compile URL repetition promised by weave.link/base placement wording."""
    merged: dict[str, int] = {}
    weave = meta.get("weave") if isinstance(meta.get("weave"), dict) else {}
    for key in ("link", "base"):
        value = str(weave.get(key) or "").strip()
        if not value or value.startswith("不织"):
            continue
        opening = bool(re.search(r"开篇|开头|首屏", value))
        ending = bool(re.search(r"文末|结尾|末尾", value))
        required = int(opening) + int(ending)
        required = required or 1
        for url in re.findall(r'https?://[^\s<>"）)，。；：、】》”’]+', value):
            clean = url.rstrip("，。；：、】》”’")
            merged[clean] = max(merged.get(clean, 0), required)
    return [
        {"url": url, "required_visible_count": count}
        for url, count in merged.items()
    ]


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


def _image_sources(html: str) -> list[str]:
    """Return ordered image identities from a draft readback."""
    return [
        html_lib.unescape(match.group(2).strip())
        for match in re.finditer(
            r"<img\b[^>]*\bsrc\s*=\s*([\"'])(.*?)\1",
            str(html or ""),
            flags=re.I | re.S,
        )
    ]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_audio_handoff(cwd: Path, media_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    """写出微信编辑器人工接管清单；只含相对路径与哈希，不泄露本机目录。"""
    md = cwd / "定稿.md"
    text = md.read_text(encoding="utf-8") if md.is_file() else ""
    roles: list[dict[str, Any]] = []
    errors: list[str] = []
    if "<!-- AUDIO-CARD-START -->" in text:
        theme, theme_errors = locate_theme_audio_record(cwd)
        errors.extend(theme_errors)
        if theme is None:
            if not theme_errors:
                errors.append("无法从 _music-manifest.json 定位主题曲")
        else:
            roles.append({
                "role": "theme",
                "label": "🎵 阅读配乐｜本文主题曲",
                "title": theme.title,
                "source": theme.relative_path,
                "sha256": theme.sha256,
                "bytes": theme.bytes,
                "duration_seconds": theme.duration_seconds,
                "origin": theme.origin,
                "registry": theme.registry,
                "music_manifest_digest": theme.manifest_digest,
                "placeholder": "（👉 删除本段文字，并插入主题曲音频）",
            })
    if "<!-- PODCAST-CARD-START -->" in text:
        podcast = cwd / "dist" / "podcast" / "audio.mp3"
        if not podcast.is_file():
            errors.append("缺 dist/podcast/audio.mp3")
        else:
            roles.append({
                "role": "podcast",
                "label": "🎧 音频版本｜本期播客",
                "source": _relative(podcast, cwd),
                "sha256": hashlib.sha256(podcast.read_bytes()).hexdigest(),
                "placeholder": "（👉 删除本段文字，并插入播客音频）",
            })
    if errors:
        return None, errors
    payload = {
        "schema_version": 3,
        "created_at": _now(),
        "draft_media_id": media_id,
        "status": "manual_insert_required",
        "roles": roles,
        "audition_required": {
            "surface": "wechat_preview",
            "segments": ["first_10_seconds", "last_10_seconds"],
            "reason": "draft/get exposes component metadata, not the uploaded audio bytes",
        },
        "next_command": "pipeline.py wechat-audio-check --confirm-audition",
    }
    (cwd / AUDIO_HANDOFF_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload, []


def _without_audio_slots(html: str) -> str:
    """Remove only the two intentional manual-insert deltas before readback diff."""
    value = str(html or "")
    value = value.replace("（👉 删除本段文字，并插入主题曲音频）", "")
    value = value.replace("（👉 删除本段文字，并插入播客音频）", "")
    return re.sub(
        rf"(?is)<{AUDIO_TAG}\b[^>]*(?:>.*?</{AUDIO_TAG}\s*>|/>)",
        "",
        value,
    )


def _section_spans(html: str) -> list[tuple[int, int, str]]:
    """Return balanced section spans, including each opening tag for card identity."""
    stack: list[tuple[int, str]] = []
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(r"(?is)<section\b[^>]*>|</section\s*>", str(html or "")):
        token = match.group(0)
        if token.lower().startswith("</"):
            if stack:
                start, opening = stack.pop()
                spans.append((start, match.end(), opening))
        else:
            stack.append((match.start(), token))
    return spans


def _card_bounds(
    content: str,
    *,
    role: str,
    label_pos: int,
) -> tuple[int, int] | None:
    """Return the smallest trustworthy container for one labelled audio card."""
    marker_start = "<!-- AUDIO-CARD-START -->" if role == "theme" else "<!-- PODCAST-CARD-START -->"
    marker_end = "<!-- AUDIO-CARD-END -->" if role == "theme" else "<!-- PODCAST-CARD-END -->"
    start = content.rfind(marker_start, 0, label_pos + 1)
    end = content.find(marker_end, label_pos)
    if start >= 0 and end >= 0:
        return start, end

    # 微信可能剥掉 HTML 注释，但会保留卡片的块级 section 与内联样式。
    # 不退回“标题到文章末尾”这种宽泛区间，否则正文里的游离播放器会假通过。
    candidates: list[tuple[int, int]] = []
    for section_start, section_end, opening in _section_spans(content):
        if not (section_start <= label_pos < section_end):
            continue
        normalized = opening.lower().replace(" ", "")
        identified = (
            f'data-audio-role="{role}"' in normalized
            or f"data-audio-role='{role}'" in normalized
            or ("#d7e3ea" in normalized and "#f2f7f9" in normalized)
        )
        if identified:
            candidates.append((section_start, section_end))
    if not candidates:
        return None
    return min(candidates, key=lambda span: span[1] - span[0])


def _audio_inside_card(
    content: str,
    *,
    role: str,
    label_pos: int,
    audio_positions: list[int],
) -> bool:
    """Fail closed unless a player sits inside the role's actual card container."""
    bounds = _card_bounds(content, role=role, label_pos=label_pos)
    if bounds is None:
        return False
    _, card_end = bounds
    return any(label_pos < audio_pos < card_end for audio_pos in audio_positions)


_REMOTE_AUDIO_ID_ATTRS = {
    "audio_id",
    "media_id",
    "src",
    "voice_encode_fileid",
    "voice_id",
}


def _audio_components(content: str) -> list[dict[str, Any]]:
    """Extract stable remote component evidence without pretending it is a byte hash."""
    components: list[dict[str, Any]] = []
    pattern = re.compile(
        rf"<(?P<tag>{AUDIO_TAG})\b(?P<attrs>[^>]*)>",
        re.I | re.S,
    )
    for match in pattern.finditer(str(content or "")):
        attrs = {
            name.lower(): html_lib.unescape(value.strip())
            for name, _, value in re.findall(
                r"([:\w-]+)\s*=\s*([\"'])(.*?)\2",
                match.group("attrs"),
                flags=re.S,
            )
            if value.strip()
        }
        strong_identity = {
            key: value for key, value in attrs.items() if key in _REMOTE_AUDIO_ID_ATTRS
        }
        fallback_identity = {
            key: value
            for key, value in attrs.items()
            if key not in {"class", "style"} and not key.startswith("data-")
        }
        identity = strong_identity or fallback_identity
        components.append({
            "position": match.start(),
            "tag": match.group("tag").lower(),
            "identity_strength": "remote_id" if strong_identity else "tag_attributes",
            "identity": identity,
            "component_digest": stable_digest({
                "tag": match.group("tag").lower(),
                "identity": identity,
            }),
        })
    return components


def verify_wechat_audio(
    cwd: Path,
    *,
    reader: Reader | None = None,
    persist: bool = True,
    audition_confirmed: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    """官方 draft/get 复核双音频，同时确认其余草稿内容没有被人工误改。"""
    handoff_path = cwd / AUDIO_HANDOFF_FILE
    if not handoff_path.is_file():
        return None, [f"缺 {AUDIO_HANDOFF_FILE}；先运行 release-to-draft"]
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"{AUDIO_HANDOFF_FILE} 解析失败：{exc}"]
    media_id = str(handoff.get("draft_media_id") or "").strip()
    roles = handoff.get("roles") or []
    if not media_id or not roles:
        return None, [f"{AUDIO_HANDOFF_FILE} 缺 draft_media_id 或 roles"]

    errors: list[str] = []
    local_audio_sha256: dict[str, str] = {}
    root = cwd.resolve()
    for role in roles:
        source = str(role.get("source") or "").strip()
        local = (root / source).resolve() if source else Path()
        expected_sha = str(role.get("sha256") or "").strip()
        try:
            local.relative_to(root)
        except (ValueError, OSError):
            errors.append(f"{role.get('label') or role.get('role')} 音频路径越出文章目录：{source}")
            continue
        if not source or not local.is_file():
            errors.append(f"{role.get('label') or role.get('role')} 本地音频不存在：{source}")
            continue
        actual_sha = hashlib.sha256(local.read_bytes()).hexdigest()
        local_audio_sha256[str(role.get("role") or "")] = actual_sha
        if not expected_sha or actual_sha != expected_sha:
            errors.append(
                f"{role.get('label') or role.get('role')} 已在草稿交接后变化；"
                "请重新运行 release-to-draft 生成交接单"
            )
        expected_bytes = role.get("bytes")
        if expected_bytes is not None:
            try:
                bytes_match = int(expected_bytes) == local.stat().st_size
            except (TypeError, ValueError):
                bytes_match = False
            if not bytes_match:
                errors.append(
                    f"{role.get('label') or role.get('role')} 文件大小已在草稿交接后变化；"
                    "请重新运行 release-to-draft 生成交接单"
                )
        if role.get("role") == "theme":
            current_theme, manifest_errors = locate_theme_audio_record(cwd)
            errors.extend(manifest_errors)
            if current_theme is not None:
                if current_theme.relative_path != source:
                    errors.append("主题曲 manifest 的 playback.path 已在草稿交接后变化")
                if current_theme.manifest_digest != str(
                    role.get("music_manifest_digest") or ""
                ):
                    errors.append("主题曲来源 manifest 已在草稿交接后变化")
    expected, expected_errors = build_expected_draft(cwd)
    errors.extend(expected_errors)
    attempt_path = cwd / ATTEMPT_FILE
    try:
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"缺 {ATTEMPT_FILE}；无法核对封面与草稿身份")
        attempt = {}
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"{ATTEMPT_FILE} 损坏：{exc}")
        attempt = {}
    if attempt and str(attempt.get("draft_media_id") or "") != media_id:
        errors.append(f"{AUDIO_HANDOFF_FILE} 与 {ATTEMPT_FILE} 的 draft_media_id 不一致")

    initial_receipt_path = cwd / RECEIPT_FILE
    try:
        initial_receipt = json.loads(initial_receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"缺 {RECEIPT_FILE}；无法确认人工插音频前的配图身份")
        initial_receipt = {}
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"{RECEIPT_FILE} 损坏：{exc}")
        initial_receipt = {}
    if initial_receipt and str(initial_receipt.get("draft_media_id") or "") != media_id:
        errors.append(f"{AUDIO_HANDOFF_FILE} 与 {RECEIPT_FILE} 的 draft_media_id 不一致")
    baseline_image_sources = (
        (initial_receipt.get("remote_readback") or {}).get("image_sources")
        if initial_receipt
        else None
    )
    if not isinstance(baseline_image_sources, list):
        errors.append(f"{RECEIPT_FILE} 缺 remote_readback.image_sources；请重跑 release-to-draft")
    if errors or expected is None:
        return None, errors

    try:
        actual = (reader or _default_reader(cwd))(media_id, expected)
    except Exception as exc:
        return None, [str(exc)]
    content = str(actual.get("content") or "")
    components = _audio_components(content)
    audio_positions = [int(component["position"]) for component in components]
    labels = [str(role.get("label") or "").lstrip("🎵🎧 ") for role in roles]
    label_positions = [content.find(label) for label in labels]
    if any(pos < 0 for pos in label_positions) or label_positions != sorted(label_positions):
        errors.append("草稿双音频卡顺序错误；必须是主题曲卡 → 播客卡 → 正文")
    remote_audio_components: dict[str, dict[str, Any]] = {}
    for role, label, pos in zip(roles, labels, label_positions):
        if pos < 0:
            errors.append(f"草稿读回缺卡片标题：{label}")
            continue
        if not _audio_inside_card(
            content,
            role=str(role.get("role") or ""),
            label_pos=pos,
            audio_positions=audio_positions,
        ):
            errors.append(f"{role.get('label')} 卡片内未读回微信原生音频组件")
        else:
            bounds = _card_bounds(
                content,
                role=str(role.get("role") or ""),
                label_pos=pos,
            )
            inside = [
                component
                for component in components
                if bounds is not None and pos < int(component["position"]) < bounds[1]
            ]
            if len(inside) == 1:
                evidence = dict(inside[0])
                evidence.pop("position", None)
                remote_audio_components[str(role.get("role") or "")] = evidence
            else:
                errors.append(
                    f"{role.get('label')} 卡片内音频组件身份不唯一：{len(inside)} 个"
                )
        placeholder = str(role.get("placeholder") or "")
        if placeholder and placeholder in content:
            errors.append(f"{role.get('label')} 仍保留插入占位文字")
    if len(audio_positions) != len(roles):
        errors.append(f"草稿读回原生音频共 {len(audio_positions)} 个，应为 {len(roles)} 个")
    component_digests = [
        str(item.get("component_digest") or "")
        for item in remote_audio_components.values()
    ]
    if len(component_digests) == len(roles) and len(set(component_digests)) != len(roles):
        errors.append("主题曲与播客卡读回了相同的远端音频组件身份")

    full_checks, full_errors = _compare_readback(
        expected,
        actual,
        str(attempt.get("cover_media_id") or ""),
        content_normalizer=_without_audio_slots,
    )
    full_checks["image_identity"] = _image_sources(content) == baseline_image_sources
    if not full_checks["image_identity"]:
        full_errors.append("draft/get 回读字段不一致：image_identity")
    errors.extend(full_errors)
    if persist and not audition_confirmed:
        errors.append(
            "微信 API 不能证明播放器内字节等于本地 MP3；请在微信预览分别试听主题曲和播客"
            "的开头 10 秒、结尾 10 秒，再用 --confirm-audition 重新核验"
        )
    if errors:
        return None, errors
    receipt = {
        "schema_version": 3,
        "verified_at": _now(),
        "draft_media_id": media_id,
        "roles": [role.get("role") for role in roles],
        "audio_count": len(audio_positions),
        "handoff_digest": stable_digest(handoff),
        "local_audio_sha256": local_audio_sha256,
        "remote_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "remote_audio_components": remote_audio_components,
        "remote_readback": {"checks": full_checks},
        "remote_verified": True,
    }
    if audition_confirmed:
        receipt["audition"] = {
            "confirmed": True,
            "confirmed_at": _now(),
            "surface": "wechat_preview",
            "roles": [role.get("role") for role in roles],
            "segments": ["first_10_seconds", "last_10_seconds"],
            "attestation": "the two remote players match their labelled local audio roles",
        }
    if persist:
        (cwd / AUDIO_RECEIPT_FILE).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return receipt, []


def compare_wechat_audio_receipts(
    stored: dict[str, Any],
    fresh: dict[str, Any],
    *,
    expected_media_id: str = "",
) -> list[str]:
    """Validate the persisted human+API proof against a new draft/get readback."""
    errors: list[str] = []
    if not stored.get("remote_verified"):
        errors.append("双音频草稿凭证未标 remote_verified=true")
    if expected_media_id and stored.get("draft_media_id") != expected_media_id:
        errors.append("双音频草稿凭证与本篇 draft_media_id 不一致")
    if set(stored.get("roles") or []) != {"theme", "podcast"}:
        errors.append("双音频草稿凭证未同时覆盖 theme 与 podcast")
    audition = stored.get("audition") or {}
    if (
        not audition.get("confirmed")
        or audition.get("surface") != "wechat_preview"
        or set(audition.get("roles") or []) != {"theme", "podcast"}
        or set(audition.get("segments") or [])
        != {"first_10_seconds", "last_10_seconds"}
    ):
        errors.append(
            "双音频草稿凭证缺人工试听证明；需在微信预览分别试听两条音频的"
            "开头/结尾 10 秒后重跑 wechat-audio-check --confirm-audition"
        )
    if stored.get("handoff_digest") != fresh.get("handoff_digest"):
        errors.append("双音频草稿凭证已过期：交接单在上次核验后变化")
    if stored.get("local_audio_sha256") != fresh.get("local_audio_sha256"):
        errors.append("双音频草稿凭证已过期：本地音频在上次核验后变化")
    if stored.get("remote_audio_components") != fresh.get("remote_audio_components"):
        errors.append("双音频草稿凭证已过期：远端播放器身份在上次核验后变化")
    return errors


def _canonical_published_url(value: str) -> str:
    """Return a stable identity for a public WeChat article URL."""
    raw = html_lib.unescape(str(value or "")).strip()
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if (parsed.hostname or "").lower() != "mp.weixin.qq.com":
        return ""
    path = re.sub(r"/+", "/", parsed.path or "").rstrip("/")
    if path.startswith("/s/") and len(path) > 3:
        return f"https://mp.weixin.qq.com{path}"
    if path == "/s":
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        identity = [
            (key, query.get(key, [""])[0])
            for key in ("__biz", "mid", "idx", "sn")
            if query.get(key, [""])[0]
        ]
        if identity:
            return "https://mp.weixin.qq.com/s?" + urllib.parse.urlencode(identity)
    return ""


def _published_urls_match(left: str, right: str) -> bool:
    left_id = _canonical_published_url(left)
    right_id = _canonical_published_url(right)
    return bool(left_id and right_id and left_id == right_id)


def _element_inner_by_id(document: str, element_id: str) -> str:
    """Extract one balanced HTML element without depending on optional parsers."""
    start_tags = re.compile(
        r"<(?P<tag>[A-Za-z][\w:-]*)\b(?P<attrs>[^>]*)>",
        re.I | re.S,
    )
    opening = None
    tag_name = ""
    for match in start_tags.finditer(str(document or "")):
        attrs = {
            name.lower(): html_lib.unescape(value)
            for name, _, value in re.findall(
                r"([:\w-]+)\s*=\s*([\"'])(.*?)\2",
                match.group("attrs"),
                flags=re.S,
            )
        }
        if attrs.get("id") == element_id:
            opening = match
            tag_name = match.group("tag")
            break
    if opening is None:
        return ""

    depth = 1
    tokens = re.compile(
        rf"<{re.escape(tag_name)}\b[^>]*>|</{re.escape(tag_name)}\s*>",
        re.I | re.S,
    )
    for token in tokens.finditer(document, opening.end()):
        value = token.group(0)
        if value.lower().startswith("</"):
            depth -= 1
            if depth == 0:
                return document[opening.end() : token.start()]
        elif not value.rstrip().endswith("/>"):
            depth += 1
    return ""


def _decode_js_string(value: str) -> str:
    """Decode the small JavaScript string-escape subset used by article pages."""
    def replace_escape(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("x") and len(token) == 3:
            return chr(int(token[1:], 16))
        if token.startswith("u") and len(token) == 5:
            return chr(int(token[1:], 16))
        return {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "/": "/",
            "\\": "\\",
            "\"": "\"",
            "'": "'",
        }.get(token, token)

    decoded = re.sub(r"\\(x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|.)", replace_escape, value)
    return html_lib.unescape(decoded)


def _js_string_value(document: str, name: str) -> str:
    """Read a quoted JS assignment/object field while respecting escaped quotes."""
    match = re.search(
        rf"\b{re.escape(name)}\b\s*(?:=|:)\s*(?:htmlDecode\s*\(\s*)?",
        str(document or ""),
        flags=re.I,
    )
    if not match:
        return ""
    cursor = match.end()
    while cursor < len(document) and document[cursor].isspace():
        cursor += 1
    if cursor >= len(document) or document[cursor] not in "\"'":
        return ""
    quote = document[cursor]
    cursor += 1
    start = cursor
    escaped = False
    while cursor < len(document):
        char = document[cursor]
        if char == quote and not escaped:
            return _decode_js_string(document[start:cursor])
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
        cursor += 1
    return ""


def _normalize_public_page_content(content: str) -> str:
    """Make WeChat lazy-loaded images comparable with the earlier draft receipt."""
    def normalize_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        data_src = re.search(
            r"\sdata-src\s*=\s*([\"'])(.*?)\1",
            tag,
            flags=re.I | re.S,
        )
        if not data_src:
            return tag
        source = html_lib.unescape(data_src.group(2).strip())
        cleaned = re.sub(
            r"\s+(?:data-src|src)\s*=\s*([\"']).*?\1",
            "",
            tag,
            flags=re.I | re.S,
        )
        suffix = "/>" if cleaned.rstrip().endswith("/>") else ">"
        cleaned = cleaned.rstrip()
        cleaned = cleaned[:-2] if suffix == "/>" else cleaned[:-1]
        escaped_source = html_lib.escape(source, quote=True)
        return f'{cleaned} src="{escaped_source}"{suffix}'

    return re.sub(r"<img\b[^>]*>", normalize_img, str(content or ""), flags=re.I | re.S)


def _published_page_payload(
    cwd: Path,
    canonical_url: str,
    expected: dict[str, Any],
    document: str,
    *,
    final_url: str,
) -> dict[str, Any]:
    """Build an auditable payload from the exact official WeChat public page."""
    if not _published_urls_match(final_url, canonical_url):
        raise RuntimeError("公众号公开页最终 URL 与指定永久链接不一致")
    content = _normalize_public_page_content(
        _element_inner_by_id(document, "js_content")
    )
    title = _visible_text(_element_inner_by_id(document, "activity-name")).strip()
    account_author = _visible_text(
        _element_inner_by_id(document, "js_author_name")
    ).strip()
    digest = _js_string_value(document, "msg_desc")
    source_url = (
        _js_string_value(document, "msg_source_url")
        or _js_string_value(document, "source_url")
    )
    cover_url = _js_string_value(document, "msg_cdn_url")
    missing = [
        name
        for name, value in {
            "js_content": content,
            "title": title,
            "account_author": account_author,
            "msg_desc": digest,
            "msg_source_url": source_url,
            "msg_cdn_url": cover_url,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"公众号公开页缺可核验字段：{missing}")

    receipt_path = cwd / RECEIPT_FILE
    try:
        baseline = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"缺 {RECEIPT_FILE}；无法建立正式页与原官方草稿证据链") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{RECEIPT_FILE} 损坏：{exc}") from exc
    baseline_readback = baseline.get("remote_readback") or {}
    baseline_checks = baseline_readback.get("checks") or {}
    if not baseline.get("remote_verified") or not baseline_checks or not all(
        baseline_checks.values()
    ):
        raise RuntimeError(f"{RECEIPT_FILE} 不是完整通过的官方草稿回读凭证")
    cover_media_id = str(
        baseline_readback.get("thumb_media_id")
        or baseline.get("cover_media_id")
        or ""
    ).strip()
    if not cover_media_id:
        raise RuntimeError(f"{RECEIPT_FILE} 缺封面 media_id")

    article = {
        "title": title,
        "digest": digest,
        "author": expected["author"],
        "content": content,
        "content_source_url": source_url,
        "thumb_media_id": cover_media_id,
        "need_open_comment": expected["need_open_comment"],
        "only_fans_can_comment": expected["only_fans_can_comment"],
        "url": canonical_url,
    }
    page_facts = {
        "wechat_url": canonical_url,
        "title": title,
        "digest": digest,
        "account_author": account_author,
        "source_url": source_url,
        "cover_url": cover_url,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    return {
        "article_id": "",
        "listed_url": canonical_url,
        "article": article,
        "readback_mode": "public_article_page",
        "published_identity": canonical_url,
        "published_surface_sha256": stable_digest(page_facts),
        "evidence_coverage": {
            "published_page": [
                "permanent_url",
                "title",
                "digest",
                "account_identity",
                "content_source_url",
                "cover_url",
                "body_and_image_identity",
                "audio_components",
            ],
            "chained_draft_receipt": [
                "thumb_media_id",
                "article_author",
                "need_open_comment",
                "only_fans_can_comment",
            ],
            "baseline_receipt": RECEIPT_FILE,
            "baseline_remote_digest": baseline_readback.get("remote_digest"),
        },
    }


def _read_published_page(
    cwd: Path,
    canonical_url: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Read the exact official public page when freepublish is unauthorized."""
    request = urllib.request.Request(
        canonical_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = str(response.geturl() or canonical_url)
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RuntimeError("公众号公开页超过 8 MiB 安全上限")
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"公众号公开页请求失败：{exc}") from exc
    document = raw.decode(charset, errors="replace")
    return _published_page_payload(
        cwd,
        canonical_url,
        expected,
        document,
        final_url=final_url,
    )


def compare_wechat_published_audio_receipts(
    stored: dict[str, Any],
    fresh: dict[str, Any],
    *,
    expected_wechat_url: str,
) -> list[str]:
    """Bind a human audition to a fresh official published-article readback."""
    errors: list[str] = []
    if stored.get("proof_kind") != "wechat_published_article_audio":
        errors.append("正式文章双音频凭证 proof_kind 不正确")
    if not stored.get("remote_verified"):
        errors.append("正式文章双音频凭证未标 remote_verified=true")
    if not _published_urls_match(
        str(stored.get("wechat_url") or ""), expected_wechat_url
    ):
        errors.append("正式文章双音频凭证与本次永久链接不一致")
    if set(stored.get("roles") or []) != {"theme", "podcast"}:
        errors.append("正式文章双音频凭证未同时覆盖 theme 与 podcast")
    audition = stored.get("audition") or {}
    if (
        not audition.get("confirmed")
        or audition.get("surface") != "wechat_published_article"
        or set(audition.get("roles") or []) != {"theme", "podcast"}
        or set(audition.get("segments") or [])
        != {"first_10_seconds", "last_10_seconds"}
    ):
        errors.append(
            "正式文章双音频凭证缺人工试听证明；需在正式文章分别试听两条音频的"
            "开头/结尾 10 秒后重跑 wechat-published-audio-check --confirm-audition"
        )
    if stored.get("readback_mode") != fresh.get("readback_mode"):
        errors.append("正式文章双音频凭证已过期：官方回读模式发生变化")
    if not stored.get("published_identity") or (
        stored.get("published_identity") != fresh.get("published_identity")
    ):
        errors.append("正式文章双音频凭证已过期：正式文章身份发生变化")
    if (
        stored.get("readback_mode") == "freepublish_api"
        and stored.get("published_article_id") != fresh.get("published_article_id")
    ):
        errors.append("正式文章双音频凭证已过期：article_id 发生变化")
    if stored.get("published_surface_sha256") != fresh.get("published_surface_sha256"):
        errors.append("正式文章双音频凭证已过期：正式文章公开面字段发生变化")
    if (
        (stored.get("remote_readback") or {}).get("evidence_coverage")
        != (fresh.get("remote_readback") or {}).get("evidence_coverage")
    ):
        errors.append("正式文章双音频凭证已过期：证据覆盖链发生变化")
    if stored.get("handoff_digest") != fresh.get("handoff_digest"):
        errors.append("正式文章双音频凭证已过期：交接单在上次核验后变化")
    if stored.get("local_audio_sha256") != fresh.get("local_audio_sha256"):
        errors.append("正式文章双音频凭证已过期：本地音频在上次核验后变化")
    if stored.get("remote_audio_components") != fresh.get("remote_audio_components"):
        errors.append("正式文章双音频凭证已过期：远端播放器身份在上次核验后变化")
    if stored.get("remote_content_sha256") != fresh.get("remote_content_sha256"):
        errors.append("正式文章双音频凭证已过期：已发布正文在上次核验后变化")
    return errors


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
    if _BROKEN_INLINE_FONT_RE.search(html):
        return None, [
            '定稿.html 含 style="...font-family: "..." 非法嵌套引号；'
            '微信清洗会丢组件，先重跑 format_layout.py --all --check'
        ]
    content = _extract_content(html)
    unsupported = _unsupported_local_images(content)
    if unsupported:
        return None, [
            f"正文引用了 {len(unsupported)} 张微信不收的图片格式"
            f"（media/uploadimg 只认 jpg/png，其余返回 40005 invalid file type，"
            f"而上传器会吞掉这个失败、把本地路径原样留在正文里）：{unsupported}"
            "；跑一次 `compress_images.py <素材目录>` 会就地转 PNG 并改好引用",
        ]
    promotion_contract = _promotion_contract(meta)
    visible = _visible_text(content)
    promotion_errors = []
    for item in promotion_contract:
        actual_count = visible.count(item["url"])
        required_count = int(item["required_visible_count"])
        if actual_count < required_count:
            promotion_errors.append(
                f'推广地址可见次数不足：{item["url"]} '
                f'需要 {required_count} 次，实际 {actual_count} 次'
            )
    if promotion_errors:
        return None, promotion_errors
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
        "promotion_contract": promotion_contract,
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
        "微信官方 API 缺 WECHAT_APP_ID / WECHAT_APP_SECRET；"
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


def _wechat_access_token(cwd: Path) -> str:
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
    return str(token)


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
        token = _wechat_access_token(cwd)
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


def _default_published_reader(cwd: Path) -> PublishedReader:
    """Use freepublish APIs, or the exact official page only on API 48001."""

    def read_published(
        wechat_url: str, expected: dict[str, Any]
    ) -> dict[str, Any]:
        canonical = _canonical_published_url(wechat_url)
        if not canonical:
            raise RuntimeError(f"不是合法公众号永久链接：{wechat_url!r}")
        token = _wechat_access_token(cwd)
        token_query = urllib.parse.urlencode({"access_token": token})
        article_id = ""
        listed_url = ""
        offset = 0
        total_count: int | None = None
        while total_count is None or offset < total_count:
            try:
                response = _http_json(
                    "https://api.weixin.qq.com/cgi-bin/freepublish/batchget?"
                    + token_query,
                    payload={"offset": offset, "count": 20, "no_content": 0},
                )
            except RuntimeError as exc:
                if not re.search(r"WeChat API 错误\s+48001\b", str(exc)):
                    raise
                return _read_published_page(cwd, canonical, expected)
            items = response.get("item")
            if not isinstance(items, list):
                raise RuntimeError("freepublish/batchget 返回的 item 不是列表")
            try:
                total_count = int(response.get("total_count") or len(items))
            except (TypeError, ValueError):
                total_count = len(items)
            for record in items:
                record_id = str((record or {}).get("article_id") or "").strip()
                news_items = ((record or {}).get("content") or {}).get("news_item") or []
                if not record_id or not isinstance(news_items, list):
                    continue
                for article in news_items:
                    candidate_url = str((article or {}).get("url") or "").strip()
                    if _published_urls_match(candidate_url, canonical):
                        article_id = record_id
                        listed_url = candidate_url
                        break
                if article_id:
                    break
            if article_id:
                break
            if not items:
                break
            offset += len(items)
        if not article_id:
            raise RuntimeError(
                "freepublish/batchget 未找到该永久链接；请确认链接属于当前公众号，"
                "且账号具备已发布内容接口权限"
            )

        try:
            response = _http_json(
                "https://api.weixin.qq.com/cgi-bin/freepublish/getarticle?"
                + token_query,
                payload={"article_id": article_id},
            )
        except RuntimeError as exc:
            if not re.search(r"WeChat API 错误\s+48001\b", str(exc)):
                raise
            return _read_published_page(cwd, canonical, expected)
        news_items = response.get("news_item")
        if not isinstance(news_items, list) or not news_items:
            raise RuntimeError("freepublish/getarticle 未返回 news_item")
        matches = [
            article
            for article in news_items
            if _published_urls_match(str((article or {}).get("url") or ""), canonical)
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"freepublish/getarticle 对该永久链接命中 {len(matches)} 篇，应恰好为 1 篇"
            )
        article = matches[0]
        if article.get("is_deleted"):
            raise RuntimeError("freepublish/getarticle 显示该文章已删除")
        return {
            "article_id": article_id,
            "listed_url": listed_url,
            "article": article,
            "readback_mode": "freepublish_api",
            "published_identity": article_id,
            "published_surface_sha256": stable_digest({
                "wechat_url": canonical,
                "article_id": article_id,
                "title": article.get("title"),
                "digest": article.get("digest"),
                "author": article.get("author"),
                "source_url": article.get("content_source_url"),
                "content_sha256": hashlib.sha256(
                    str(article.get("content") or "").encode("utf-8")
                ).hexdigest(),
            }),
            "evidence_coverage": {
                "published_api": [
                    "freepublish/batchget",
                    "freepublish/getarticle",
                ],
                "chained_draft_receipt": [],
            },
        }

    return read_published


def verify_wechat_published_audio(
    cwd: Path,
    wechat_url: str,
    *,
    reader: PublishedReader | None = None,
    persist: bool = True,
    audition_confirmed: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Recover proof from an official API or its strict 48001 public-page fallback."""
    canonical = _canonical_published_url(wechat_url)
    if not canonical:
        return None, [f"不是合法公众号永久链接：{wechat_url!r}"]
    if persist and not audition_confirmed:
        return None, [
            "请先在正式文章分别试听主题曲和播客的开头 10 秒、结尾 10 秒，"
            "再用 --confirm-audition 重新核验"
        ]

    published: dict[str, Any] = {}

    def published_as_draft(
        media_id: str, expected: dict[str, Any]
    ) -> dict[str, Any]:
        del media_id
        payload = (reader or _default_published_reader(cwd))(wechat_url, expected)
        article = payload.get("article") if isinstance(payload, dict) else None
        if not isinstance(article, dict):
            raise RuntimeError("已发布内容读取器未返回 article 对象")
        published.update(payload)
        return article

    draft_receipt, errors = verify_wechat_audio(
        cwd,
        reader=published_as_draft,
        persist=False,
        audition_confirmed=audition_confirmed,
    )
    surface_name = (
        "公众号正式文章公开页"
        if published.get("readback_mode") == "public_article_page"
        else "freepublish/getarticle"
    )
    errors = [str(error).replace("draft/get", surface_name) for error in errors]
    if errors or draft_receipt is None:
        return None, errors

    article = published.get("article") or {}
    remote_url = str(article.get("url") or published.get("listed_url") or "")
    if not _published_urls_match(remote_url, canonical):
        return None, [f"{surface_name} 返回的文章 URL 与指定永久链接不一致"]
    readback_mode = str(published.get("readback_mode") or "freepublish_api")
    article_id = str(published.get("article_id") or "").strip()
    published_identity = str(published.get("published_identity") or article_id).strip()
    published_surface_sha256 = str(
        published.get("published_surface_sha256") or ""
    ).strip()
    if readback_mode == "freepublish_api" and not article_id:
        return None, ["freepublish/getarticle 补验缺 article_id"]
    if not published_identity:
        return None, ["正式文章补验缺 published_identity"]
    if not published_surface_sha256:
        return None, ["正式文章补验缺 published_surface_sha256"]

    receipt = {
        "schema_version": 2,
        "proof_kind": "wechat_published_article_audio",
        "verified_at": _now(),
        "wechat_url": canonical,
        "readback_mode": readback_mode,
        "published_identity": published_identity,
        "published_article_id": article_id or None,
        "published_surface_sha256": published_surface_sha256,
        "source_draft_media_id": draft_receipt.get("draft_media_id"),
        "roles": draft_receipt.get("roles"),
        "audio_count": draft_receipt.get("audio_count"),
        "handoff_digest": draft_receipt.get("handoff_digest"),
        "local_audio_sha256": draft_receipt.get("local_audio_sha256"),
        "remote_content_sha256": draft_receipt.get("remote_content_sha256"),
        "remote_audio_components": draft_receipt.get("remote_audio_components"),
        "remote_readback": {
            "apis": (
                ["freepublish/batchget", "freepublish/getarticle"]
                if readback_mode == "freepublish_api"
                else []
            ),
            "surface": (
                "https://mp.weixin.qq.com/s/..."
                if readback_mode == "public_article_page"
                else "freepublish/getarticle"
            ),
            "evidence_coverage": published.get("evidence_coverage") or {},
            "checks": (draft_receipt.get("remote_readback") or {}).get("checks"),
        },
        "remote_verified": True,
    }
    if audition_confirmed:
        receipt["audition"] = {
            "confirmed": True,
            "confirmed_at": _now(),
            "surface": "wechat_published_article",
            "roles": draft_receipt.get("roles"),
            "segments": ["first_10_seconds", "last_10_seconds"],
            "attestation": "the two published players match their labelled local audio roles",
        }
    if persist:
        (cwd / PUBLISHED_AUDIO_RECEIPT_FILE).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return receipt, []


def _compare_readback(
    expected: dict[str, Any],
    actual: dict[str, Any],
    cover_media_id: str,
    *,
    content_normalizer: Callable[[str], str] | None = None,
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
    expected_content = str(expected["content"])
    compared_content = content_normalizer(content) if content_normalizer else content
    compared_expected = (
        content_normalizer(expected_content) if content_normalizer else expected_content
    )
    checks["body_digest"] = _semantic_body_digest(
        compared_expected
    ) == _semantic_body_digest(compared_content)
    checks["image_count"] = expected["image_count"] == _image_count(content)
    unuploaded = _unuploaded_images(content)
    checks["image_src_uploaded"] = not unuploaded
    checks["cover_media_id"] = (
        bool(cover_media_id)
        and cover_media_id == str(actual.get("thumb_media_id") or "")
    )
    promotion_counts: dict[str, int] = {}
    visible = _visible_text(content)
    for item in expected.get("promotion_contract") or []:
        url = str(item.get("url") or "")
        promotion_counts[url] = visible.count(url)
    checks["promotion_urls"] = all(
        promotion_counts.get(str(item.get("url") or ""), 0)
        >= int(item.get("required_visible_count") or 1)
        for item in expected.get("promotion_contract") or []
    )
    errors = [f"draft/get 回读字段不一致：{name}" for name, ok in checks.items() if not ok]
    if unuploaded:
        # 单独给一条能直接照着修的报错：只说「image_src_uploaded 不一致」
        # 等于把人推回去逐张翻 HTML，而失败原因（微信拒收某种格式）就藏在文件名里。
        errors.append(
            f"以下 {len(unuploaded)} 张图未上传成功、仍指向本地路径"
            f"（微信只收 jpg/png，webp 会被 40005 拒收）：{unuploaded}"
        )
    if not checks["promotion_urls"]:
        errors.append(f"draft/get 回读推广地址次数不足：{promotion_counts}")
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
        "image_sources": _image_sources(str(actual.get("content") or "")),
        "thumb_media_id": str(actual.get("thumb_media_id") or ""),
        "promotion_url_counts": {
            str(item.get("url") or ""): _visible_text(
                str(actual.get("content") or "")
            ).count(str(item.get("url") or ""))
            for item in expected.get("promotion_contract") or []
        },
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
