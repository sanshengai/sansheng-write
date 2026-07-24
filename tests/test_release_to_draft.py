import json
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


def _reader(*, mutate: str = ""):
    def read(media_id, expected):
        article = {
            "title": expected["title"],
            "author": expected["author"],
            "digest": expected["digest"],
            "content": expected["content"],
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
