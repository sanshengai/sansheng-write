# -*- coding: utf-8 -*-
"""tweet_evidence.py 离线测试：URL/ID 解析、时区转换、JSON 解析、视频选码率、
文件名生成、合并去重、CLI 退出码。全程不联网、不起真浏览器——网络与 Playwright
调用统一通过 monkeypatch 换成假实现（fetch_tweet_json / capture_screenshot /
download_video 三个函数）。
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from scripts import tweet_evidence as te


# ===== extract_tweet_id =====

@pytest.mark.parametrize("ref, expected", [
    ("2102435511222890900", "2102435511222890900"),
    ("  123  ", "123"),
    ("https://x.com/claudeai/status/2102435511222890900", "2102435511222890900"),
    ("https://twitter.com/claudeai/status/2102435511222890900", "2102435511222890900"),
    ("http://www.x.com/claudeai/status/123", "123"),
    ("https://mobile.twitter.com/claudeai/status/123/", "123"),
    ("https://x.com/claudeai/status/123?s=20&t=abc", "123"),
    ("https://x.com/claudeai/status/123/photo/1", "123"),
    ("https://x.com/i/web/status/123", "123"),
    ("x.com/claudeai/status/123", "123"),
])
def test_extract_tweet_id_accepts_known_forms(ref, expected):
    assert te.extract_tweet_id(ref) == expected


@pytest.mark.parametrize("bad", [
    "",
    "   ",
    "not-a-tweet",
    "https://example.com/claudeai/status/123",
    "https://x.com/claudeai/no-status-here/123",
])
def test_extract_tweet_id_rejects_unknown_forms(bad):
    with pytest.raises(ValueError):
        te.extract_tweet_id(bad)


# ===== 时间转换（含北京时间跨日用例） =====

def test_utc_to_beijing_crosses_midnight():
    # 真实取证：2026-09-22 深夜（UTC）发布 == 北京时间 09-23 零点后
    assert te.to_beijing_str("2026-09-22T16:31:01.000Z") == "2026-09-23 00:31"


def test_utc_to_beijing_same_day_no_rollover():
    assert te.to_beijing_str("2026-09-22T01:00:00.000Z") == "2026-09-22 09:00"


def test_to_utc_str_normalizes_milliseconds_and_z_suffix():
    assert te.to_utc_str("2026-09-22T16:31:01.000Z") == "2026-09-22T16:31:01Z"


def test_parse_created_at_rejects_empty():
    with pytest.raises(ValueError):
        te.parse_created_at("")


# ===== pick_video_variants =====

def test_pick_video_variants_picks_highest_bitrate_mp4_and_skips_m3u8():
    media = [{
        "type": "video",
        "video_info": {
            "variants": [
                {"content_type": "application/x-mpegURL", "url": "https://v/playlist.m3u8"},
                {"bitrate": 256000, "content_type": "video/mp4", "url": "https://v/lo.mp4"},
                {"bitrate": 2176000, "content_type": "video/mp4", "url": "https://v/hi.mp4"},
                {"bitrate": 832000, "content_type": "video/mp4", "url": "https://v/mid.mp4"},
            ]
        },
    }]
    assert te.pick_video_variants(media) == ["https://v/hi.mp4"]


def test_pick_video_variants_skips_photo_only_media():
    media = [{"type": "photo", "media_url_https": "https://p/1.jpg"}]
    assert te.pick_video_variants(media) == []


def test_pick_video_variants_handles_variant_without_bitrate_field():
    # 动图转码后的 mp4 常常不带 bitrate 字段，仍应被当成候选（唯一的 mp4）
    media = [{
        "type": "animated_gif",
        "video_info": {"variants": [{"content_type": "video/mp4", "url": "https://v/gif.mp4"}]},
    }]
    assert te.pick_video_variants(media) == ["https://v/gif.mp4"]


def test_pick_video_variants_each_media_item_contributes_independently():
    media = [
        {"video_info": {"variants": [{"bitrate": 100, "content_type": "video/mp4", "url": "a"}]}},
        {"video_info": {"variants": [{"bitrate": 200, "content_type": "video/mp4", "url": "b"}]}},
    ]
    assert te.pick_video_variants(media) == ["a", "b"]


def test_pick_video_variants_tolerates_malformed_input():
    assert te.pick_video_variants(None) == []
    assert te.pick_video_variants([None, {}, {"video_info": None},
                                    {"video_info": {"variants": None}}]) == []


# ===== syndication JSON -> 记录（parse_tweet_payload） =====

def _sample_payload(with_quote=False, with_video=False):
    payload = {
        "id_str": "1000000000000000006",
        "created_at": "2026-09-22T16:31:01.000Z",
        "text": "示例正文第一行\n示例正文第二行",
        "user": {"screen_name": "sample_user", "name": "示例作者"},
        "mediaDetails": [],
    }
    if with_video:
        payload["mediaDetails"] = [{
            "type": "video",
            "video_info": {"variants": [
                {"bitrate": 832000, "content_type": "video/mp4", "url": "https://v/mid.mp4"},
                {"bitrate": 2176000, "content_type": "video/mp4", "url": "https://v/hi.mp4"},
            ]},
        }]
    if with_quote:
        payload["quoted_tweet"] = {
            "id_str": "999",
            "created_at": "2026-09-21T00:00:00.000Z",
            "text": "被引用的原文",
            "user": {"screen_name": "other_user", "name": "另一个人"},
            "mediaDetails": [],
        }
    return payload


def test_parse_tweet_payload_basic_fields():
    record = te.parse_tweet_payload(_sample_payload())
    assert record["id"] == "1000000000000000006"
    assert record["handle"] == "sample_user"
    assert record["name"] == "示例作者"
    assert record["created_at_utc"] == "2026-09-22T16:31:01Z"
    assert record["created_at_bjt"] == "2026-09-23 00:31"
    assert record["text"] == "示例正文第一行\n示例正文第二行"
    assert record["url"] == "https://x.com/sample_user/status/1000000000000000006"
    assert record["quoted"] is None
    assert record["videos"] == []
    assert record["screenshot"] is None
    assert record["employee"] is None


def test_parse_tweet_payload_quote_is_recursive_and_same_shape():
    record = te.parse_tweet_payload(_sample_payload(with_quote=True))
    quoted = record["quoted"]
    assert quoted is not None
    assert quoted["id"] == "999"
    assert quoted["handle"] == "other_user"
    assert quoted["text"] == "被引用的原文"
    assert quoted["url"] == "https://x.com/other_user/status/999"
    assert set(quoted.keys()) == set(record.keys())  # 同结构


def test_parse_tweet_payload_picks_best_video_variant():
    record = te.parse_tweet_payload(_sample_payload(with_video=True))
    assert record["videos"] == ["https://v/hi.mp4"]


def test_parse_tweet_payload_missing_handle_falls_back_to_generic_url():
    payload = _sample_payload()
    payload["user"] = {}
    record = te.parse_tweet_payload(payload)
    assert record["handle"] == ""
    assert record["url"] == "https://x.com/i/status/1000000000000000006"


def test_parse_tweet_payload_empty_quoted_tweet_dict_is_none():
    payload = _sample_payload()
    payload["quoted_tweet"] = {}
    record = te.parse_tweet_payload(payload)
    assert record["quoted"] is None


# ===== 文件名生成 =====

def test_screenshot_filename_default_prefix_uses_last_six_digits():
    assert te.screenshot_filename("shot-tw-", "ClaudeAI", "2102435511222890900") == \
        "shot-tw-ClaudeAI-890900.png"


def test_screenshot_filename_sanitizes_handle_and_strips_leading_at():
    assert te.screenshot_filename("shot-tw-", "@weird/name!", "123") == "shot-tw-weirdname-123.png"


def test_screenshot_filename_short_id_not_padded_or_truncated():
    assert te.screenshot_filename("shot-tw-", "user", "42") == "shot-tw-user-42.png"


def test_screenshot_filename_custom_prefix():
    assert te.screenshot_filename("shot-", "user", "123456") == "shot-user-123456.png"


def test_video_filename_single_item_has_no_index_suffix():
    assert te.video_filename("user", "123456", 0, 1) == "user-123456.mp4"


def test_video_filename_multiple_items_get_1_based_index():
    assert te.video_filename("user", "123456", 0, 2) == "user-123456-1.mp4"
    assert te.video_filename("user", "123456", 1, 2) == "user-123456-2.mp4"


# ===== JSON 合并去重（merge_records） =====

def test_merge_records_appends_new_ids_after_existing_ones():
    existing = [{"id": "1", "text": "a"}]
    updates = [{"id": "2", "text": "b"}]
    merged = te.merge_records(existing, updates)
    assert [r["id"] for r in merged] == ["1", "2"]


def test_merge_records_updates_same_id_in_place_without_duplicating():
    existing = [{"id": "1", "text": "old", "employee": None}]
    updates = [{"id": "1", "text": "new", "employee": None}]
    merged = te.merge_records(existing, updates)
    assert len(merged) == 1
    assert merged[0]["text"] == "new"


def test_merge_records_preserves_manual_employee_annotation_on_rerun():
    existing = [{"id": "1", "text": "old", "employee": "人工标注：Anthropic 员工"}]
    updates = [{"id": "1", "text": "refreshed", "employee": None}]
    merged = te.merge_records(existing, updates)
    assert merged[0]["employee"] == "人工标注：Anthropic 员工"
    assert merged[0]["text"] == "refreshed"


def test_merge_records_explicit_non_null_employee_in_update_overrides():
    existing = [{"id": "1", "employee": "旧标注"}]
    updates = [{"id": "1", "employee": "新标注"}]
    merged = te.merge_records(existing, updates)
    assert merged[0]["employee"] == "新标注"


def test_merge_records_dedupes_error_entries_without_id_by_url():
    existing = [{"id": None, "url": "bad-ref", "error": "解析失败"}]
    updates = [{"id": None, "url": "bad-ref", "error": "解析失败（重试仍失败）"}]
    merged = te.merge_records(existing, updates)
    assert len(merged) == 1
    assert merged[0]["error"] == "解析失败（重试仍失败）"


def test_merge_records_ignores_malformed_rows():
    assert te.merge_records([None, "x"], [{"id": "1"}]) == [{"id": "1"}]


# ===== render_markdown =====

def test_render_markdown_includes_manual_employee_reminder_and_screenshot_path():
    md = te.render_markdown([{
        "id": "1", "handle": "u", "name": "N",
        "created_at_bjt": "2026-09-23 00:31", "created_at_utc": "2026-09-22T16:31:01Z",
        "url": "https://x.com/u/status/1", "text": "正文",
        "quoted": None, "videos": [], "screenshot": "shot-tw-u-000001.png", "employee": None,
    }])
    assert "员工身份需人工标注" in md
    assert "shot-tw-u-000001.png" in md
    assert "2026-09-23 00:31" in md


def test_render_markdown_error_entry_is_rendered_distinctly():
    md = te.render_markdown([{"id": None, "url": "bad-ref", "error": "无法解析出推文 ID"}])
    assert "抓取失败：无法解析出推文 ID" in md


# ===== fetch_tweet_json：monkeypatch urllib，覆盖两种真实观察到的失败形态 =====

def test_fetch_tweet_json_reports_400_bad_request_detail(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", None, io.BytesIO(b'{"error":"Bad request."}')
        )

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="Bad request"):
        te.fetch_tweet_json("notanumber")


def test_fetch_tweet_json_reports_404_as_deleted_or_missing(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", None, io.BytesIO(b"<html>not found</html>")
        )

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="不存在或已删除"):
        te.fetch_tweet_json("1")


def test_fetch_tweet_json_rejects_tombstone_shaped_response(monkeypatch):
    class _FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        return _FakeResp(b'{"__typename":"TweetTombstone"}')

    monkeypatch.setattr(te.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="TweetTombstone"):
        te.fetch_tweet_json("123")


# ===== CLI main()：退出码、合并落盘、截图/视频子步骤的软失败 =====

def _fake_payload(tweet_id, text="正文", handle=None):
    return {
        "id_str": tweet_id,
        "created_at": "2026-09-22T16:31:01.000Z",
        "text": text,
        "user": {"screen_name": handle or f"user{tweet_id}", "name": f"作者{tweet_id}"},
        "mediaDetails": [],
    }


def test_main_all_success_returns_0_and_writes_both_files(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "fetch_tweet_json", lambda tid, **kw: _fake_payload(tid))

    rc = te.main(["--out", str(tmp_path), "--no-screenshot", "111", "222"])
    assert rc == 0
    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    assert [r["id"] for r in data] == ["111", "222"]
    assert (tmp_path / te.EVIDENCE_MD_NAME).is_file()


def test_main_partial_failure_returns_1_and_records_error_field(tmp_path, monkeypatch):
    def fake_fetch(tid, **kw):
        if tid == "222":
            raise RuntimeError("推文不存在或已删除（HTTP 404）")
        return _fake_payload(tid)

    monkeypatch.setattr(te, "fetch_tweet_json", fake_fetch)
    rc = te.main(["--out", str(tmp_path), "--no-screenshot", "111", "222"])
    assert rc == 1

    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in data}
    assert not by_id["111"].get("error")
    assert by_id["222"]["error"] == "推文不存在或已删除（HTTP 404）"


def test_main_all_failure_returns_2(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "fetch_tweet_json",
                         lambda tid, **kw: (_ for _ in ()).throw(RuntimeError("网络请求失败：timeout")))
    rc = te.main(["--out", str(tmp_path), "--no-screenshot", "111"])
    assert rc == 2


def test_main_bad_ref_produces_error_entry_without_crashing(tmp_path):
    rc = te.main(["--out", str(tmp_path), "--no-screenshot", "not-a-valid-ref"])
    assert rc == 2
    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    assert data[0]["id"] is None
    assert "无法从" in data[0]["error"]


def test_main_rerun_merges_by_id_and_preserves_employee_annotation(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "fetch_tweet_json", lambda tid, **kw: _fake_payload(tid, text="第一版正文"))
    assert te.main(["--out", str(tmp_path), "--no-screenshot", "111"]) == 0

    json_path = tmp_path / te.EVIDENCE_JSON_NAME
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data[0]["employee"] = "人工标注：非官方账号"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(te, "fetch_tweet_json",
                         lambda tid, **kw: _fake_payload(tid, text="第二版正文（重新抓取）"))
    assert te.main(["--out", str(tmp_path), "--no-screenshot", "111"]) == 0

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 1  # 不重复追加
    assert data[0]["text"] == "第二版正文（重新抓取）"
    assert data[0]["employee"] == "人工标注：非官方账号"  # 人工标注未被冲掉


def test_main_screenshot_and_video_steps_invoked_when_requested(tmp_path, monkeypatch):
    """不起真浏览器：monkeypatch capture_screenshot / download_video 本体。"""
    payload = _fake_payload("333", handle="user333")
    payload["mediaDetails"] = [{
        "video_info": {"variants": [{"bitrate": 100, "content_type": "video/mp4", "url": "https://v/a.mp4"}]},
    }]
    monkeypatch.setattr(te, "fetch_tweet_json", lambda tid, **kw: payload)

    shots = []

    def fake_capture(tweet_id, out_path, **kw):
        shots.append((tweet_id, out_path))
        out_path.write_bytes(b"fake-png")

    monkeypatch.setattr(te, "capture_screenshot", fake_capture)

    downloads = []

    def fake_download(url, out_path, **kw):
        downloads.append((url, out_path))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-mp4")

    monkeypatch.setattr(te, "download_video", fake_download)

    rc = te.main(["--out", str(tmp_path), "--video", "333"])
    assert rc == 0
    assert len(shots) == 1
    assert len(downloads) == 1

    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    assert data[0]["screenshot"] == "shot-tw-user333-333.png"
    assert (tmp_path / "shot-tw-user333-333.png").is_file()
    assert (tmp_path / "video" / "user333-333.mp4").is_file()


def test_main_screenshot_failure_is_soft_and_still_counts_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "fetch_tweet_json", lambda tid, **kw: _fake_payload(tid))
    monkeypatch.setattr(te, "capture_screenshot",
                         lambda tid, out_path, **kw: (_ for _ in ()).throw(RuntimeError("playwright 未装")))

    rc = te.main(["--out", str(tmp_path), "111"])
    assert rc == 0  # 文字证据仍完整，截图子步骤失败不拖累整条记录
    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    assert data[0]["screenshot"] is None
    assert data[0]["text"]


def test_main_video_download_failure_is_soft_and_does_not_block(tmp_path, monkeypatch):
    payload = _fake_payload("444", handle="user444")
    payload["mediaDetails"] = [{
        "video_info": {"variants": [{"bitrate": 100, "content_type": "video/mp4", "url": "https://v/a.mp4"}]},
    }]
    monkeypatch.setattr(te, "fetch_tweet_json", lambda tid, **kw: payload)
    monkeypatch.setattr(te, "download_video",
                         lambda url, out_path, **kw: (_ for _ in ()).throw(RuntimeError("网络超时")))

    rc = te.main(["--out", str(tmp_path), "--no-screenshot", "--video", "444"])
    assert rc == 0
    data = json.loads((tmp_path / te.EVIDENCE_JSON_NAME).read_text(encoding="utf-8"))
    assert data[0]["videos"] == ["https://v/a.mp4"]  # 直链仍记录在 JSON 里
