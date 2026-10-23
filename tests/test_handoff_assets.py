import json
from pathlib import Path

from scripts.evidence import sha256_file, stable_digest
from scripts.handoff_assets import export_handoff_assets
from scripts.music_manifest import write_music_manifest


def _article(tmp_path: Path, *, podcast: bool = False):
    article = tmp_path / "97-example"
    article.mkdir()
    materials = article / "素材"
    materials.mkdir()
    cover = materials / "cover.png"
    cover.write_bytes(b"sealed-cover")
    # 主题曲封面必交付；播客封面只在有播客时交付（audio_covers.py 负责生成）。
    (materials / "bgm_cover.png").write_bytes(b"theme-cover")
    if podcast:
        (materials / "podcast_cover.png").write_bytes(b"podcast-cover")
    visual_receipt = {
        "schema_version": 1,
        "manifest": {
            "schema_version": 1,
            "assets": [
                {
                    "stage": "cover",
                    "path": "素材/cover.png",
                    "sha256": sha256_file(cover),
                    "bytes": cover.stat().st_size,
                }
            ],
        },
        "manifest_digest": "",
    }
    visual_receipt["manifest_digest"] = stable_digest(visual_receipt["manifest"])
    theme = article / "边界之歌.mp3"
    theme.write_bytes(b"theme-audio")
    (article / "article-meta.yaml").write_text("title: 边界之歌\n", encoding="utf-8")
    write_music_manifest(
        article,
        theme,
        title="边界之歌",
        duration_seconds=206.2,
        provider="example-provider",
        model="music-model-v3",
        mode="web_manual",
        registry_reference="catalog/theme-songs.json",
        registry_entry="biography-example",
    )
    if podcast:
        podcast_dir = article / "dist/podcast"
        podcast_dir.mkdir(parents=True)
        podcast_audio = podcast_dir / "audio.mp3"
        podcast_audio.write_bytes(b"podcast-audio")
        podcast_manifest = {
            "schema_version": 1,
            "audio_sha256": sha256_file(podcast_audio),
            "bytes": podcast_audio.stat().st_size,
            "duration_seconds": 600.0,
        }
        (podcast_dir / "audio.manifest.json").write_text(
            json.dumps(podcast_manifest, ensure_ascii=False), encoding="utf-8"
        )

    def verify_visual(_article_dir: Path):
        return visual_receipt, []

    def probe(path: Path):
        return (600.0, "") if path.name == "audio.mp3" else (206.2, "")

    return article, verify_visual, probe


def test_handoff_exports_only_receipt_bound_assets_and_is_idempotent(tmp_path: Path):
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    target_root = tmp_path / "handoff"

    target, status, errors = export_handoff_assets(
        article,
        target_root=target_root,
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert errors == [] and target is not None and status == "created"
    assert sorted(path.name for path in target.iterdir()) == [
        "_handoff-receipt.json",
        "cover.png",
        "播客 | 边界之歌.mp3",
        "播客封面.png",
        "边界之歌.mp3",
        "音乐封面.png",
    ]
    receipt = json.loads((target / "_handoff-receipt.json").read_text(encoding="utf-8"))
    assert [asset["role"] for asset in receipt["assets"]] == [
        "cover",
        "theme",
        "podcast",
        "theme_cover",
        "podcast_cover",
    ]
    theme = receipt["assets"][1]
    assert theme["origin"]["provider"] == "example-provider"
    assert theme["registry"]["entry"] == "biography-example"
    assert "created_at" not in receipt

    second, second_status, second_errors = export_handoff_assets(
        article,
        target_root=target_root,
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert second_errors == [] and second == target and second_status == "unchanged"


def test_handoff_refuses_different_snapshot_unless_revision(tmp_path: Path):
    article, verify_visual, probe = _article(tmp_path)
    target_root = tmp_path / "handoff"
    first, status, errors = export_handoff_assets(
        article,
        target_root=target_root,
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert first is not None and status == "created" and errors == []

    theme = article / "边界之歌.mp3"
    theme.write_bytes(b"new-theme-audio")
    write_music_manifest(
        article,
        theme,
        title="边界之歌",
        duration_seconds=206.2,
        provider="example-provider",
        model="music-model-v3",
        mode="web_manual",
        registry_reference="catalog/theme-songs.json",
        registry_entry="biography-example",
    )
    refused, _, refused_errors = export_handoff_assets(
        article,
        target_root=target_root,
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert refused is None
    assert any("--revision" in error for error in refused_errors)

    revised, revised_status, revised_errors = export_handoff_assets(
        article,
        target_root=target_root,
        revision="r2",
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert revised_errors == [] and revised is not None
    assert revised_status == "created" and revised.name.endswith("--r2")


def test_handoff_rejects_unmanifested_podcast(tmp_path: Path):
    article, verify_visual, probe = _article(tmp_path)
    podcast_dir = article / "dist/podcast"
    podcast_dir.mkdir(parents=True)
    (podcast_dir / "audio.mp3").write_bytes(b"unmanifested")

    target, _, errors = export_handoff_assets(
        article,
        target_root=tmp_path / "handoff",
        duration_probe=probe,
        visual_verifier=verify_visual,
    )
    assert target is None
    assert any("必须同时存在" in error for error in errors)


def test_default_handoff_stays_in_article_and_ignores_legacy_env(tmp_path, monkeypatch):
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    legacy = tmp_path / "legacy-handoff"
    monkeypatch.setenv("SANSHENG_WRITE_HANDOFF_DIR", str(legacy))
    manuscript = article / "定稿.md"
    manuscript.write_text("作者原稿", encoding="utf-8")
    before = {p: p.read_bytes() for p in article.rglob("*") if p.is_file()}
    kwargs = dict(duration_probe=probe, visual_verifier=verify_visual)
    target, status, errors = export_handoff_assets(article, **kwargs)
    assert (target, status, errors) == (article, "created", [])
    assert not legacy.exists()
    assert (article / "播客 | 边界之歌.mp3").read_bytes() == (article / "dist/podcast/audio.mp3").read_bytes()
    assert (article / "cover.png").read_bytes() == (article / "素材/cover.png").read_bytes()
    assert (article / "音乐封面.png").read_bytes() == b"theme-cover"
    assert (article / "播客封面.png").read_bytes() == b"podcast-cover"
    assert not (article / "theme-边界之歌.mp3").exists()
    assert not (article / "podcast.mp3").exists()
    assert all(p.read_bytes() == data for p, data in before.items())
    assert export_handoff_assets(article, **kwargs) == (article, "unchanged", [])


def test_default_handoff_rejects_collision_before_any_write(tmp_path):
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    (article / "播客 | 边界之歌.mp3").write_bytes(b"authors-unrelated-recording")
    before = {p: p.read_bytes() for p in article.rglob("*") if p.is_file()}
    target, _, errors = export_handoff_assets(article, duration_probe=probe, visual_verifier=verify_visual)
    assert target is None and any("未覆盖" in error for error in errors)
    assert {p: p.read_bytes() for p in article.rglob("*") if p.is_file()} == before


def test_default_handoff_rejects_empty_article(tmp_path):
    target, _, errors = export_handoff_assets(tmp_path)
    assert target is None and errors
    assert list(tmp_path.iterdir()) == []


def test_default_handoff_does_not_accept_corrupted_copy(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    monkeypatch.setattr(handoff.shutil, "copyfile", lambda source, dest: Path(dest).write_bytes(b"corrupted"))
    target, _, errors = export_handoff_assets(article, duration_probe=probe, visual_verifier=verify_visual)
    assert target is None and any("复制后校验失败" in error for error in errors)
    assert not (article / "cover.png").exists()
    assert not (article / "_handoff-receipt.json").exists()
    assert not list(article.glob(".handoff-tmp-*"))


def test_default_handoff_preserves_concurrent_writer_and_rolls_back_own_files(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    link = handoff.os.link
    def racing_link(source, destination):
        if destination.name == "播客 | 边界之歌.mp3":
            destination.write_bytes(b"concurrent-writer")
        return link(source, destination)
    monkeypatch.setattr(handoff.os, "link", racing_link)
    target, _, errors = export_handoff_assets(article, duration_probe=probe, visual_verifier=verify_visual)
    assert target is None and errors
    assert (article / "播客 | 边界之歌.mp3").read_bytes() == b"concurrent-writer"
    assert not (article / "cover.png").exists()
    assert not (article / "_handoff-receipt.json").exists()


def test_handoff_requires_theme_cover_and_podcast_cover(tmp_path):
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    kwargs = dict(duration_probe=probe, visual_verifier=verify_visual)
    (article / "素材/podcast_cover.png").unlink()
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("缺播客封面" in error for error in errors)
    assert not (article / "cover.png").exists()

    (article / "素材/podcast_cover.png").write_bytes(b"podcast-cover")
    (article / "素材/bgm_cover.png").write_bytes(b"")
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("缺音乐封面" in error for error in errors)

    # 没有播客的文章不要求播客封面
    (tmp_path / "plain").mkdir()
    plain, verify_plain, probe_plain = _article(tmp_path / "plain")
    target, status, errors = export_handoff_assets(
        plain, duration_probe=probe_plain, visual_verifier=verify_plain
    )
    assert errors == [] and status == "created"
    assert (plain / "音乐封面.png").exists() and not (plain / "播客封面.png").exists()



def _ready_upgrade(tmp_path):
    article, visual, probe = _article(tmp_path, podcast=True)
    kwargs = dict(duration_probe=probe, visual_verifier=visual)
    assert export_handoff_assets(article, **kwargs) == (article, "created", [])
    audio = article / "dist/podcast/audio.mp3"
    audio.write_bytes(b"verified-new-podcast")
    manifest_path = article / "dist/podcast/audio.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(audio_sha256=sha256_file(audio), bytes=audio.stat().st_size)
    manifest_path.write_text(json.dumps(manifest))
    return article, kwargs, article / "播客 | 边界之歌.mp3", article / "过程记录/_handoff-receipt.json"


def test_root_upgrade_preserves_old_receipt_and_bytes_then_is_idempotent(tmp_path):
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    old_receipt = receipt.read_bytes()
    (article / "定稿.md").write_text("作者稿")
    assert export_handoff_assets(article, **kwargs) == (article, "updated", [])
    assert upload.read_bytes() == b"verified-new-podcast"
    backups = list((article / "过程记录/handoff-history").glob("revision-*"))
    assert len(backups) == 1
    assert (backups[0] / upload.name).read_bytes() == b"podcast-audio"
    assert (backups[0] / "previous-receipt.json").read_bytes() == old_receipt
    assert (backups[0] / "next-receipt.json").read_bytes() == receipt.read_bytes()
    assert (article / "定稿.md").read_text() == "作者稿"
    assert export_handoff_assets(article, **kwargs) == (article, "unchanged", [])


def test_root_upgrade_rejects_manually_edited_upload_before_writes(tmp_path):
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    upload.write_bytes(b"author-changed-this")
    before = {p: p.read_bytes() for p in article.rglob("*") if p.is_file()}
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("不匹配旧" in e for e in errors)
    assert {p: p.read_bytes() for p in article.rglob("*") if p.is_file()} == before


def test_root_upgrade_refuses_missing_or_malformed_prior_ownership(tmp_path):
    mutations = [
        lambda r: r.update(schema_version=99),
        lambda r: r["article"].update(directory="another-article"),
        lambda r: r["assets"][2]["handoff"].update(sha256="broken"),
        lambda r: r["assets"][2]["handoff"].update(bytes=True),
        lambda r: r["assets"][2]["source"].update(sha256="0" * 64),
        lambda r: r["assets"][2]["source"].update(path="../../outside.mp3"),
        lambda r: r["assets"][2]["source"].pop("receipt_digest"),
        lambda r: r["assets"][2]["source"].update(receipt_digest="bad-digest"),
        lambda r: r["assets"].pop(2),  # Known filename alone is not ownership.
        lambda r: r.update(assets=[]),
    ]
    for index, mutation in enumerate([None, "json", *mutations]):
        root = tmp_path / str(index)
        root.mkdir()
        article, kwargs, upload, receipt = _ready_upgrade(root)
        if mutation is None:
            receipt.unlink()
        elif mutation == "json":
            receipt.write_text("not json")
        else:
            old = json.loads(receipt.read_text())
            mutation(old)
            receipt.write_text(json.dumps(old))
        before = {p: p.read_bytes() for p in article.rglob("*") if p.is_file()}
        target, _, errors = export_handoff_assets(article, **kwargs)
        assert target is None and errors, index
        assert {p: p.read_bytes() for p in article.rglob("*") if p.is_file()} == before


def test_root_upgrade_requires_valid_new_manifest(tmp_path):
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    (article / "dist/podcast/audio.mp3").write_bytes(b"unverified-new-audio")
    old_receipt = receipt.read_bytes()
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and errors
    assert upload.read_bytes() == b"podcast-audio"
    assert receipt.read_bytes() == old_receipt
    assert not (article / "过程记录/handoff-history").exists()


def test_root_upgrade_rejects_corrupt_staging_without_retiring_old_files(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    monkeypatch.setattr(handoff.shutil, "copyfile", lambda src, dst: Path(dst).write_bytes(b"bad"))
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("复制后校验失败" in e for e in errors)
    assert upload.read_bytes() == b"podcast-audio"
    assert not (article / "过程记录/handoff-history").exists()


def test_root_upgrade_detects_edit_during_retirement_and_restores_it(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    old_receipt = receipt.read_bytes()
    rename = handoff.os.rename
    def race(source, destination):
        if source == upload:
            source.write_bytes(b"concurrent-edit-before-move")
        return rename(source, destination)
    monkeypatch.setattr(handoff.os, "rename", race)
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("并发修改" in e for e in errors)
    assert upload.read_bytes() == b"concurrent-edit-before-move"
    assert receipt.read_bytes() == old_receipt


def test_root_upgrade_preserves_concurrent_install_and_old_backup(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    old_receipt = receipt.read_bytes()
    link = handoff.os.link
    def race(source, destination):
        if destination == upload:
            destination.write_bytes(b"concurrent-new-file")
        return link(source, destination)
    monkeypatch.setattr(handoff.os, "link", race)
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and any("并发文件保留" in e for e in errors)
    assert upload.read_bytes() == b"concurrent-new-file"
    assert receipt.read_bytes() == old_receipt
    backup = next((article / "过程记录/handoff-history").glob("revision-*"))
    assert (backup / upload.name).read_bytes() == b"podcast-audio"


def test_root_upgrade_rolls_back_when_receipt_install_fails(tmp_path, monkeypatch):
    import scripts.handoff_assets as handoff
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    old_receipt = receipt.read_bytes()
    link = handoff.os.link
    def fail_once(source, destination):
        if destination == receipt and source.name == "_handoff-receipt.json":
            raise OSError("simulated receipt install failure")
        return link(source, destination)
    monkeypatch.setattr(handoff.os, "link", fail_once)
    target, _, errors = export_handoff_assets(article, **kwargs)
    assert target is None and errors
    assert upload.read_bytes() == b"podcast-audio"
    assert receipt.read_bytes() == old_receipt
    monkeypatch.setattr(handoff.os, "link", link)
    assert export_handoff_assets(article, **kwargs) == (article, "updated", [])


def test_old_byte_gate_mutation_would_overwrite_manual_edit(tmp_path, monkeypatch):
    """Actual exporter rejects a manual edit; disable old-byte guard to prove coverage."""
    import scripts.handoff_assets as handoff
    article, kwargs, upload, receipt = _ready_upgrade(tmp_path)
    upload.write_bytes(b"author-manual-edit")
    assert export_handoff_assets(article, **kwargs)[0] is None
    matches = handoff._matches_file
    old_digest = next(a["handoff"]["sha256"] for a in json.loads(receipt.read_text())["assets"] if a["role"] == "podcast")
    # Mutate only verification of old bytes; new source/staging checks remain real.
    monkeypatch.setattr(handoff, "_matches_file", lambda path, expected: True if expected[1] == old_digest else matches(path, expected))
    assert export_handoff_assets(article, **kwargs) == (article, "updated", [])
    assert upload.read_bytes() == b"verified-new-podcast"
