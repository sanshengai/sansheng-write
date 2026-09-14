import json
from pathlib import Path

from scripts.evidence import sha256_file
from scripts.handoff_assets import export_handoff_assets
from scripts.music_manifest import write_music_manifest


def _article(tmp_path: Path, *, podcast: bool = False):
    article = tmp_path / "97-example"
    article.mkdir()
    materials = article / "素材"
    materials.mkdir()
    cover = materials / "cover.png"
    cover.write_bytes(b"sealed-cover")
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
        "manifest_digest": "visual-manifest",
    }
    theme = article / "边界之歌.mp3"
    theme.write_bytes(b"theme-audio")
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
        "podcast.mp3",
        "theme-边界之歌.mp3",
    ]
    receipt = json.loads((target / "_handoff-receipt.json").read_text(encoding="utf-8"))
    assert [asset["role"] for asset in receipt["assets"]] == [
        "cover",
        "theme",
        "podcast",
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
    assert (article / "podcast.mp3").read_bytes() == (article / "dist/podcast/audio.mp3").read_bytes()
    assert (article / "cover.png").read_bytes() == (article / "素材/cover.png").read_bytes()
    assert not (article / "theme-边界之歌.mp3").exists()
    assert all(p.read_bytes() == data for p, data in before.items())
    assert export_handoff_assets(article, **kwargs) == (article, "unchanged", [])


def test_default_handoff_rejects_collision_before_any_write(tmp_path):
    article, verify_visual, probe = _article(tmp_path, podcast=True)
    (article / "podcast.mp3").write_bytes(b"authors-unrelated-recording")
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
        if destination.name == "podcast.mp3":
            destination.write_bytes(b"concurrent-writer")
        return link(source, destination)
    monkeypatch.setattr(handoff.os, "link", racing_link)
    target, _, errors = export_handoff_assets(article, duration_probe=probe, visual_verifier=verify_visual)
    assert target is None and errors
    assert (article / "podcast.mp3").read_bytes() == b"concurrent-writer"
    assert not (article / "cover.png").exists()
    assert not (article / "_handoff-receipt.json").exists()
