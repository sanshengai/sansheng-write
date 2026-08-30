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
