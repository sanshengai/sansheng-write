import json
import re
from pathlib import Path

import pytest


def _article(root: Path) -> Path:
    (root / "素材").mkdir()
    (root / "article-meta.yaml").write_text(
        'title: "教程 | 一键草稿"\n'
        'digest: "把发布前检查、推送和读回锁进同一条命令。"\n'
        'author: "测试作者"\n'
        'source_url: "https://example.com/article"\n',
        encoding="utf-8",
    )
    (root / "定稿.html").write_text(
        '<html><body><section><p>正文</p>'
        '<img src="素材/hero.png"><img src="素材/infographic-01.png">'
        "</section></body></html>",
        encoding="utf-8",
    )
    (root / "素材/cover.png").write_bytes(b"cover")
    (root / "_release-job.json").write_text(
        json.dumps({"scope": "wechat-draft", "formal_publish": False}),
        encoding="utf-8",
    )
    return root


def _preflight(root: Path):
    from scripts.evidence import stable_digest

    manifest = {
        "schema_version": 1,
        "visual_manifest_digest": "visual-digest",
        "files": [{"path": "定稿.html", "sha256": "html-sha", "bytes": 99}],
    }
    ready = {
        "schema_version": 1,
        "manifest": manifest,
        "manifest_digest": stable_digest(manifest),
    }
    (root / "_publish-ready.json").write_text(
        json.dumps(ready, ensure_ascii=False), encoding="utf-8"
    )
    return ready, []


def _publisher(counter: list[str]):
    def publish(expected):
        counter.append("publish")
        return {
            "media_id": "draft-media-001",
            "cover_media_id": "cover-media-001",
            "method": "api",
            "title": expected["title"],
        }

    return publish


def _reader(*, mutate: str = "", keep_local_src: bool = False):
    """模拟 draft/get 回读。

    🔴 真实微信**一定会把本地 src 换成 mmbiz 远端地址**——上传成功的图才留得下来。
    这个 stub 原本原样回显 expected["content"]（带 `src="素材/hero.png"`），
    与现实不符，正因如此「六张 webp 被微信 40005 拒收、img 保留本地路径」
    连推三版都没被任何测试拦住。stub 不忠实于现实，等于给假通过背书。

    keep_local_src=True 用于反向断言：故意还原成不上传的样子，验证新闸拦得住。
    """

    def read(media_id, expected):
        content = str(expected["content"])
        if not keep_local_src:
            def uploaded(match):
                name = match.group(2).replace("\\", "/").rsplit("/", 1)[-1]
                return f'{match.group(1)}https://wechat-image.invalid/{name}{match.group(3)}'

            content = re.sub(
                r'(<img[^>]*\ssrc=")(?!https?://)([^"]+)(")',
                uploaded,
                content,
                flags=re.I,
            )
        article = {
            "title": expected["title"],
            "author": expected["author"],
            "digest": expected["digest"],
            "content": content,
            "content_source_url": expected["source_url"],
            "thumb_media_id": "cover-media-001",
            "need_open_comment": expected["need_open_comment"],
            "only_fans_can_comment": expected["only_fans_can_comment"],
        }
        if mutate:
            article[mutate] = "远端被改坏"
        return article

    return read


def test_release_to_draft_is_one_transaction_with_remote_readback(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    calls = []
    receipt, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(),
    )

    assert errors == []
    assert calls == ["publish"]
    assert receipt["draft_media_id"] == "draft-media-001"
    assert receipt["remote_verified"] is True
    assert receipt["formal_publish"] is False
    assert receipt["scope"] == "wechat-draft"
    checks = receipt["remote_readback"]["checks"]
    assert all(checks.values())
    assert checks["body_digest"] is True
    assert checks["image_count"] is True
    assert checks["cover_media_id"] is True
    assert receipt["remote_readback"]["image_sources"] == [
        "https://wechat-image.invalid/hero.png",
        "https://wechat-image.invalid/infographic-01.png",
    ]


def test_readback_accepts_publisher_digest_truncation_and_wechat_html_cleanup(
    tmp_path,
):
    from scripts.release_to_draft import (
        _compare_readback,
        _published_digest,
    )

    article = _article(tmp_path)
    from scripts.release_to_draft import build_expected_draft

    expected, errors = build_expected_draft(article)
    assert errors == []
    expected["digest"] = (
        "第一层信息足够完整。" + "第二层信息需要继续保留，" * 12 + "最后一句。"
    )
    expected["content"] = (
        "<!-- 本地排版注释 --><section><p>正文</p>"
        '<img src="素材/hero.png"><img src="素材/infographic-01.png">'
        "</section>"
    )
    actual = {
        "title": expected["title"],
        "author": expected["author"],
        "digest": _published_digest(expected["digest"]),
        "content": (
            "<section><p>正文</p>"
            '<img src="https://wechat-image.invalid/one">'
            '<img src="https://wechat-image.invalid/two">'
            "</section>"
        ),
        "content_source_url": expected["source_url"],
        "thumb_media_id": "cover-media-001",
        "need_open_comment": expected["need_open_comment"],
        "only_fans_can_comment": expected["only_fans_can_comment"],
    }

    checks, compare_errors = _compare_readback(
        expected, actual, "cover-media-001"
    )

    assert compare_errors == []
    assert checks["digest"] is True
    assert checks["body_digest"] is True


def test_semantic_body_digest_ignores_markup_inside_sanitized_title_attribute():
    from scripts.release_to_draft import _semantic_body_digest

    local = (
        '<p><a href="https://example.com" '
        'title="<strong>打开企业沉浮</strong>">'
        '<strong>打开企业沉浮</strong></a></p>'
    )
    wechat = (
        '<p><a href="https://example.com" title="打开企业沉浮">'
        '<strong>打开企业沉浮</strong></a></p>'
    )
    changed_visible_text = (
        '<p><a href="https://example.com" title="打开企业沉浮">'
        '<strong>打开另一个栏目</strong></a></p>'
    )

    assert _semantic_body_digest(local) == _semantic_body_digest(wechat)
    assert _semantic_body_digest(local) != _semantic_body_digest(changed_visible_text)


def _dual_audio_article(root: Path) -> Path:
    from scripts.audio_cards import render_card
    from scripts.release_to_draft import release_to_draft, write_audio_handoff

    article = _article(root)
    theme_card = render_card("theme", "原创 · 3 分 20 秒")
    podcast_card = render_card("podcast", "AI 生成 · 双主持")
    (article / "定稿.md").write_text(
        f"# 标题\n\n正文。\n\n{theme_card}\n\n{podcast_card}\n",
        encoding="utf-8",
    )
    (article / "定稿.html").write_text(
        "<html><body><section><p>正文</p>"
        '<img src="素材/hero.png"><img src="素材/infographic-01.png">'
        f"{theme_card}{podcast_card}</section></body></html>",
        encoding="utf-8",
    )
    (article / "主题曲.mp3").write_bytes(b"theme-audio")
    (article / "dist/podcast").mkdir(parents=True)
    (article / "dist/podcast/audio.mp3").write_bytes(b"podcast-audio")
    receipt, release_errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher([]),
        reader=_reader(),
    )
    assert release_errors == [] and receipt is not None
    handoff, errors = write_audio_handoff(article, "draft-media-001")
    assert errors == [] and handoff is not None
    return article


def _dual_audio_reader(
    *,
    mutate_body: bool = False,
    stray_podcast: bool = False,
    duplicate_image: bool = False,
    duplicate_audio_identity: bool = False,
    reverse_cards: bool = False,
):
    base = _reader()

    def read(media_id, expected):
        actual = base(media_id, expected)
        content = actual["content"].replace(
            "（👉 删除本段文字，并插入主题曲音频）",
            '<mp-common-mpaudio name="主题曲"></mp-common-mpaudio>',
        )
        podcast_name = "主题曲" if duplicate_audio_identity else "播客"
        podcast_player = f'<mp-common-mpaudio name="{podcast_name}"></mp-common-mpaudio>'
        content = content.replace(
            "（👉 删除本段文字，并插入播客音频）",
            "" if stray_podcast else podcast_player,
        )
        if stray_podcast:
            content += podcast_player
        if mutate_body:
            content = content.replace("正文", "正文被人工误改", 1)
        if duplicate_image:
            content = content.replace(
                "https://wechat-image.invalid/infographic-01.png",
                "https://wechat-image.invalid/hero.png",
                1,
            )
        if reverse_cards:
            blocks = re.findall(
                r"<!-- (?:AUDIO|PODCAST)-CARD-START -->.*?"
                r"<!-- (?:AUDIO|PODCAST)-CARD-END -->",
                content,
                flags=re.S,
            )
            assert len(blocks) == 2
            content = content.replace(blocks[0], "__FIRST_AUDIO_CARD__", 1)
            content = content.replace(blocks[1], blocks[0], 1)
            content = content.replace("__FIRST_AUDIO_CARD__", blocks[1], 1)
        actual["content"] = content
        return actual

    return read


def _published_audio_reader(
    *,
    remote_url: str = "https://mp.weixin.qq.com/s/x",
    article_id: str = "published-article-001",
):
    base = _dual_audio_reader()

    def read(wechat_url, expected):
        actual = base("draft-media-001", expected)
        actual["url"] = remote_url
        return {
            "article_id": article_id,
            "listed_url": remote_url,
            "article": actual,
            "readback_mode": "freepublish_api",
            "published_identity": article_id,
            "published_surface_sha256": "published-surface-001",
            "evidence_coverage": {
                "published_api": ["freepublish/getarticle"],
                "chained_draft_receipt": [],
            },
        }

    return read


def test_dual_audio_readback_checks_players_and_full_article(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article,
        reader=_dual_audio_reader(),
        audition_confirmed=True,
    )

    assert errors == []
    assert receipt is not None
    assert receipt["roles"] == ["theme", "podcast"]
    assert receipt["audio_count"] == 2
    assert all(receipt["remote_readback"]["checks"].values())
    assert set(receipt["local_audio_sha256"]) == {"theme", "podcast"}
    assert set(receipt["remote_audio_components"]) == {"theme", "podcast"}
    assert receipt["audition"]["confirmed"] is True


def test_published_audio_recovery_writes_distinct_official_receipt(tmp_path):
    from scripts.release_to_draft import (
        PUBLISHED_AUDIO_RECEIPT_FILE,
        verify_wechat_published_audio,
    )

    article = _dual_audio_article(tmp_path)
    url = "https://mp.weixin.qq.com/s/x"
    receipt, errors = verify_wechat_published_audio(
        article,
        url,
        reader=_published_audio_reader(),
        audition_confirmed=True,
    )

    assert errors == []
    assert receipt is not None
    assert receipt["proof_kind"] == "wechat_published_article_audio"
    assert receipt["readback_mode"] == "freepublish_api"
    assert receipt["published_identity"] == "published-article-001"
    assert receipt["published_article_id"] == "published-article-001"
    assert receipt["wechat_url"] == url
    assert receipt["audition"]["surface"] == "wechat_published_article"
    assert (article / PUBLISHED_AUDIO_RECEIPT_FILE).is_file()
    assert not (article / "_wechat-audio-receipt.json").exists()


def test_published_audio_recovery_requires_explicit_audition(tmp_path):
    from scripts.release_to_draft import verify_wechat_published_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_published_audio(
        article,
        "https://mp.weixin.qq.com/s/x",
        reader=_published_audio_reader(),
    )

    assert receipt is None
    assert any("正式文章" in error and "开头 10 秒" in error for error in errors)


def test_published_audio_recovery_rejects_wrong_permanent_url(tmp_path):
    from scripts.release_to_draft import verify_wechat_published_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_published_audio(
        article,
        "https://mp.weixin.qq.com/s/x",
        reader=_published_audio_reader(
            remote_url="https://mp.weixin.qq.com/s/y"
        ),
        audition_confirmed=True,
    )

    assert receipt is None
    assert any("URL 与指定永久链接不一致" in error for error in errors)


def test_published_audio_receipt_comparison_rejects_changed_article(tmp_path):
    from scripts.release_to_draft import (
        compare_wechat_published_audio_receipts,
        verify_wechat_published_audio,
    )

    article = _dual_audio_article(tmp_path)
    url = "https://mp.weixin.qq.com/s/x"
    stored, errors = verify_wechat_published_audio(
        article,
        url,
        reader=_published_audio_reader(),
        audition_confirmed=True,
    )
    assert errors == [] and stored is not None
    fresh = json.loads(json.dumps(stored, ensure_ascii=False))
    fresh.pop("audition")
    fresh["published_article_id"] = "published-article-002"
    fresh["remote_content_sha256"] = "changed"
    fresh["remote_readback"]["evidence_coverage"] = {"changed": True}

    compare_errors = compare_wechat_published_audio_receipts(
        stored,
        fresh,
        expected_wechat_url=url,
    )

    assert any("article_id" in error for error in compare_errors)
    assert any("证据覆盖链" in error for error in compare_errors)
    assert any("已发布正文" in error for error in compare_errors)


def test_default_published_reader_pages_then_rechecks_exact_article(
    tmp_path, monkeypatch
):
    from scripts import release_to_draft

    url = "https://mp.weixin.qq.com/s/x"
    calls = []
    monkeypatch.setattr(release_to_draft, "_wechat_access_token", lambda cwd: "token")

    def fake_http(endpoint, *, payload=None):
        calls.append((endpoint, payload))
        if "freepublish/batchget" in endpoint:
            offset = payload["offset"]
            candidate = (
                "https://mp.weixin.qq.com/s/OTHER"
                if offset == 0
                else url
            )
            return {
                "total_count": 2,
                "item_count": 1,
                "item": [{
                    "article_id": f"article-{offset}",
                    "content": {"news_item": [{"url": candidate}]},
                }],
            }
        assert "freepublish/getarticle" in endpoint
        assert payload == {"article_id": "article-1"}
        return {"news_item": [{"url": url, "title": "测试文章"}]}

    monkeypatch.setattr(release_to_draft, "_http_json", fake_http)
    payload = release_to_draft._default_published_reader(tmp_path)(url, {})

    assert payload["article_id"] == "article-1"
    assert payload["article"]["url"] == url
    assert sum("freepublish/batchget" in endpoint for endpoint, _ in calls) == 2
    assert sum("freepublish/getarticle" in endpoint for endpoint, _ in calls) == 1


def test_published_page_payload_chains_only_unobservable_draft_fields(tmp_path):
    from scripts import release_to_draft

    article = _dual_audio_article(tmp_path)
    expected, expected_errors = release_to_draft.build_expected_draft(article)
    assert expected_errors == [] and expected is not None
    actual = _dual_audio_reader()("draft-media-001", expected)
    public_content = re.sub(
        r'\ssrc="([^"]+)"',
        r' data-src="\1" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yw="',
        actual["content"],
    )
    url = "https://mp.weixin.qq.com/s/x"
    document = (
        '<html><head><script>var msg_desc = htmlDecode('
        + json.dumps(expected["digest"], ensure_ascii=False)
        + "); var msg_source_url = "
        + json.dumps(expected["source_url"], ensure_ascii=False)
        + '; var msg_cdn_url = "https://example.com/cover.jpg";'
        + "</script></head><body>"
        + f'<h1 id="activity-name"><span>{expected["title"]}</span></h1>'
        + f'<span id="js_author_name">{expected["author"]}</span>'
        + f'<div id="js_content">{public_content}</div>'
        + "</body></html>"
    )

    payload = release_to_draft._published_page_payload(
        article,
        url,
        expected,
        document,
        final_url=url + "?scene=1",
    )

    assert payload["readback_mode"] == "public_article_page"
    assert payload["published_identity"] == url
    assert payload["article_id"] == ""
    assert payload["article"]["content"].count("data:image/gif") == 0
    assert release_to_draft._image_sources(payload["article"]["content"]) == (
        json.loads((article / "_publish-receipt.json").read_text(encoding="utf-8"))
        ["remote_readback"]["image_sources"]
    )
    coverage = payload["evidence_coverage"]
    assert "audio_components" in coverage["published_page"]
    assert set(coverage["chained_draft_receipt"]) == {
        "thumb_media_id",
        "article_author",
        "need_open_comment",
        "only_fans_can_comment",
    }


def test_default_published_reader_falls_back_to_official_page_only_on_48001(
    tmp_path, monkeypatch
):
    from scripts import release_to_draft

    url = "https://mp.weixin.qq.com/s/x"
    fallback = {"readback_mode": "public_article_page"}
    calls = []
    monkeypatch.setattr(release_to_draft, "_wechat_access_token", lambda cwd: "token")
    monkeypatch.setattr(
        release_to_draft,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("WeChat API 错误 48001：api unauthorized")
        ),
    )
    monkeypatch.setattr(
        release_to_draft,
        "_read_published_page",
        lambda cwd, canonical, expected: calls.append((cwd, canonical, expected))
        or fallback,
    )

    payload = release_to_draft._default_published_reader(tmp_path)(url, {"x": 1})

    assert payload is fallback
    assert calls == [(tmp_path, url, {"x": 1})]


def test_default_published_reader_does_not_hide_other_api_failures(
    tmp_path, monkeypatch
):
    from scripts import release_to_draft

    monkeypatch.setattr(release_to_draft, "_wechat_access_token", lambda cwd: "token")
    monkeypatch.setattr(
        release_to_draft,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("WeChat API 错误 40013：invalid appid")
        ),
    )
    monkeypatch.setattr(
        release_to_draft,
        "_read_published_page",
        lambda *args, **kwargs: pytest.fail("非 48001 不得降级公开页"),
    )

    with pytest.raises(RuntimeError, match="40013"):
        release_to_draft._default_published_reader(tmp_path)(
            "https://mp.weixin.qq.com/s/x",
            {},
        )


def test_dual_audio_readback_requires_explicit_remote_audition(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(article, reader=_dual_audio_reader())

    assert receipt is None
    assert any("开头 10 秒、结尾 10 秒" in error for error in errors)


def test_dual_audio_readback_rejects_duplicate_remote_component_identity(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article,
        reader=_dual_audio_reader(duplicate_audio_identity=True),
        audition_confirmed=True,
    )

    assert receipt is None
    assert any("相同的远端音频组件身份" in error for error in errors)


def test_dual_audio_readback_rejects_reversed_card_order(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article,
        reader=_dual_audio_reader(reverse_cards=True),
        audition_confirmed=True,
    )

    assert receipt is None
    assert any("主题曲卡 → 播客卡 → 正文" in error for error in errors)


def test_finalize_receipt_comparison_rejects_stale_remote_player(tmp_path):
    from scripts.release_to_draft import (
        compare_wechat_audio_receipts,
        verify_wechat_audio,
    )

    article = _dual_audio_article(tmp_path)
    stored, errors = verify_wechat_audio(
        article,
        reader=_dual_audio_reader(),
        audition_confirmed=True,
    )
    assert errors == [] and stored is not None
    fresh = json.loads(json.dumps(stored, ensure_ascii=False))
    fresh.pop("audition")
    fresh["remote_audio_components"]["podcast"]["component_digest"] = "replaced"

    compare_errors = compare_wechat_audio_receipts(
        stored,
        fresh,
        expected_media_id="draft-media-001",
    )

    assert any("远端播放器身份" in error for error in compare_errors)


def test_finalize_receipt_comparison_rejects_legacy_receipt_without_audition(tmp_path):
    from scripts.release_to_draft import (
        compare_wechat_audio_receipts,
        verify_wechat_audio,
    )

    article = _dual_audio_article(tmp_path)
    current, errors = verify_wechat_audio(
        article,
        reader=_dual_audio_reader(),
        audition_confirmed=True,
    )
    assert errors == [] and current is not None
    legacy = json.loads(json.dumps(current, ensure_ascii=False))
    legacy["schema_version"] = 2
    legacy.pop("audition")
    legacy.pop("remote_audio_components")

    compare_errors = compare_wechat_audio_receipts(legacy, current)

    assert any("缺人工试听证明" in error for error in compare_errors)
    assert any("远端播放器身份" in error for error in compare_errors)


def test_dual_audio_readback_rejects_unrelated_manual_body_edit(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article, reader=_dual_audio_reader(mutate_body=True)
    )

    assert receipt is None
    assert any("body_digest" in error for error in errors)


def test_dual_audio_handoff_expires_when_local_audio_changes(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    (article / "dist/podcast/audio.mp3").write_bytes(b"a-new-podcast")
    receipt, errors = verify_wechat_audio(article, reader=_dual_audio_reader())

    assert receipt is None
    assert any("草稿交接后变化" in error for error in errors)


def test_dual_audio_readback_rejects_player_outside_podcast_card(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article, reader=_dual_audio_reader(stray_podcast=True)
    )

    assert receipt is None
    assert any("播客" in error and "卡片内" in error for error in errors)


def test_dual_audio_readback_rejects_equal_count_image_replacement(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(
        article, reader=_dual_audio_reader(duplicate_image=True)
    )

    assert receipt is None
    assert any("image_identity" in error for error in errors)


def test_remote_mismatch_blocks_publish_receipt_but_preserves_attempt(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    receipt, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher([]),
        reader=_reader(mutate="title"),
    )

    assert receipt is None
    assert any("title" in error for error in errors)
    assert (article / "_release-attempt.json").is_file()
    assert not (article / "_publish-receipt.json").exists()


def test_retry_reads_existing_draft_instead_of_creating_duplicate(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    calls = []
    first, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(mutate="title"),
    )
    assert first is None and errors

    second, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(),
    )

    assert errors == []
    assert second["draft_media_id"] == "draft-media-001"
    assert calls == ["publish"]
    assert second["resumed_attempt"] is True


def test_changed_ready_digest_requires_a_new_draft_attempt(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    calls = []
    assert release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(mutate="title"),
    )[0] is None

    def changed_preflight(root):
        ready, errors = _preflight(root)
        ready["manifest_digest"] = "changed-ready"
        (root / "_publish-ready.json").write_text(json.dumps(ready), encoding="utf-8")
        return ready, errors

    receipt, errors = release_to_draft(
        article,
        preflight=changed_preflight,
        publisher=_publisher(calls),
        reader=_reader(),
    )

    assert errors == []
    assert calls == ["publish", "publish"]
    assert receipt["resumed_attempt"] is False


def test_changed_remote_metadata_never_reuses_old_attempt(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    calls = []
    assert release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(mutate="title"),
    )[0] is None
    meta = article / "article-meta.yaml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            "把发布前检查、推送和读回锁进同一条命令。",
            "摘要已经改变，必须新建草稿。",
        ),
        encoding="utf-8",
    )

    receipt, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher(calls),
        reader=_reader(),
    )

    assert errors == []
    assert calls == ["publish", "publish"]
    assert receipt["resumed_attempt"] is False


def test_release_job_scope_cannot_expand_to_formal_publish(tmp_path):
    from scripts.release_to_draft import release_to_draft

    article = _article(tmp_path)
    job = json.loads((article / "_release-job.json").read_text(encoding="utf-8"))
    job["scope"] = "formal-publish"
    job["formal_publish"] = True
    (article / "_release-job.json").write_text(json.dumps(job), encoding="utf-8")

    receipt, errors = release_to_draft(
        article,
        preflight=_preflight,
        publisher=_publisher([]),
        reader=_reader(),
    )

    assert receipt is None
    assert any("wechat-draft" in error for error in errors)


def test_unuploaded_local_images_block_the_draft(tmp_path):
    """图上传失败时必须拦住——数量对得上不等于图传上去了。

    真实事故（2026-07-28）：六张 .webp 被微信以 40005 invalid file type 拒收，
    baoyu-post-to-wechat 把上传异常 catch 掉只打一行 stderr，img 标签保留本地
    src。`image_count` 数出 15 == 15 照样放行，连推三版都显示校验通过，
    而读者看到的是六个坏图。
    """
    from scripts.release_to_draft import release_to_draft

    root = _article(tmp_path)
    receipt, errors = release_to_draft(
        root,
        preflight=_preflight,
        publisher=_publisher([]),
        reader=_reader(keep_local_src=True),   # 还原「上传失败、src 没被换掉」
    )

    assert receipt is None, "带本地 src 的回读绝不能被判为发布成功"
    assert any("image_src_uploaded" in e for e in errors)
    # 报错必须点名是哪几张、并说清原因，否则等于把人推回去逐张翻 HTML
    detail = "\n".join(errors)
    assert "素材/hero.png" in detail
    assert "webp" in detail


def test_wechat_unsupported_image_format_is_blocked_before_push(tmp_path):
    """正文引用 .webp 时必须在推送前拦下——微信 40005 拒收，且失败会被吞掉。"""
    from scripts.release_to_draft import build_expected_draft

    root = _article(tmp_path)
    (root / "定稿.html").write_text(
        "<html><body><section><p>正文</p>"
        '<img src="素材/01-截图.webp" data-local-path="C:/x/素材/01-截图.webp">'
        "</section></body></html>",
        encoding="utf-8",
    )

    expected, errors = build_expected_draft(root)

    assert expected is None
    detail = "\n".join(errors)
    assert "01-截图.webp" in detail
    assert "40005" in detail          # 说清微信为什么拒
    assert "compress_images.py" in detail   # 给出照着做就能修的下一步


def test_malformed_inline_font_style_is_blocked_before_push(tmp_path):
    from scripts.release_to_draft import build_expected_draft

    root = _article(tmp_path)
    (root / "定稿.html").write_text(
        '<html><body><section style="font-family: "Source Han Serif SC", serif;">'
        '<p>主题曲卡片</p></section></body></html>',
        encoding="utf-8",
    )

    expected, errors = build_expected_draft(root)
    assert expected is None
    assert any("非法嵌套引号" in error for error in errors)


def test_promotion_url_promised_twice_must_survive_remote_readback(tmp_path):
    from scripts.release_to_draft import _compare_readback, build_expected_draft

    root = _article(tmp_path)
    url = "https://example.com/tools/booknotes-author/"
    with (root / "article-meta.yaml").open("a", encoding="utf-8") as stream:
        stream.write(
            'weave:\n  base: "德鲁克作品集 '
            + url
            + '，放在开篇第一屏与文末。"\n'
        )
    (root / "定稿.html").write_text(
        f"<html><body><section><p>{url}</p><p>正文</p><p>{url}</p></section></body></html>",
        encoding="utf-8",
    )
    expected, errors = build_expected_draft(root)
    assert errors == []
    actual = {
        "title": expected["title"],
        "author": expected["author"],
        "digest": expected["digest"],
        "content": f"<section><p>{url}</p><p>正文</p></section>",
        "content_source_url": expected["source_url"],
        "thumb_media_id": "cover-media-001",
        "need_open_comment": expected["need_open_comment"],
        "only_fans_can_comment": expected["only_fans_can_comment"],
    }
    checks, errors = _compare_readback(expected, actual, "cover-media-001")
    assert checks["promotion_urls"] is False
    assert any("推广地址次数不足" in error for error in errors)


def test_compress_images_converts_unsupported_and_rewrites_references(tmp_path):
    """转换必须连引用一起改，且删掉原文件——留着下次还会被引用回去。"""
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from PIL import Image

    from compress_images import convert_unsupported

    art = tmp_path / "art"
    (art / "素材").mkdir(parents=True)
    Image.new("RGB", (8, 6), (1, 2, 3)).save(art / "素材/01-截图.webp", "WEBP")
    (art / "定稿.md").write_text("![图](素材/01-截图.webp)", encoding="utf-8")

    done = convert_unsupported(art / "素材", verbose=False)

    assert len(done) == 1
    assert (art / "素材/01-截图.png").is_file()
    assert not (art / "素材/01-截图.webp").exists(), "原文件必须删掉"
    assert (art / "定稿.md").read_text(encoding="utf-8") == "![图](素材/01-截图.png)"
