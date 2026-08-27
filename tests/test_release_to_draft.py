import json
import re
from pathlib import Path


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
    *, mutate_body: bool = False, stray_podcast: bool = False, duplicate_image: bool = False
):
    base = _reader()

    def read(media_id, expected):
        actual = base(media_id, expected)
        content = actual["content"].replace(
            "（👉 删除本段文字，并插入主题曲音频）",
            '<mp-common-mpaudio name="主题曲"></mp-common-mpaudio>',
        )
        podcast_player = '<mp-common-mpaudio name="播客"></mp-common-mpaudio>'
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
        actual["content"] = content
        return actual

    return read


def test_dual_audio_readback_checks_players_and_full_article(tmp_path):
    from scripts.release_to_draft import verify_wechat_audio

    article = _dual_audio_article(tmp_path)
    receipt, errors = verify_wechat_audio(article, reader=_dual_audio_reader())

    assert errors == []
    assert receipt is not None
    assert receipt["roles"] == ["theme", "podcast"]
    assert receipt["audio_count"] == 2
    assert all(receipt["remote_readback"]["checks"].values())
    assert set(receipt["local_audio_sha256"]) == {"theme", "podcast"}


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
