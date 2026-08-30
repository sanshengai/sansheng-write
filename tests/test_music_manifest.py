import json
from pathlib import Path

from scripts.audio_cards import locate_theme_audio, locate_theme_audio_record
from scripts.music_manifest import (
    MUSIC_MANIFEST_FILE,
    validate_music_manifest,
    write_music_manifest,
)


def _write_manifest(article: Path, audio: Path):
    return write_music_manifest(
        article,
        audio,
        title="边界之歌",
        duration_seconds=206.2,
        provider="example-provider",
        model="music-model-v3",
        mode="web_manual",
        registry_reference="catalog/theme-songs.json",
        registry_entry="biography-example",
    )


def test_manifest_is_the_only_theme_audio_authority(tmp_path: Path):
    article = tmp_path / "1-article"
    article.mkdir()
    audio = article / "theme.mp3"
    audio.write_bytes(b"theme-bytes")
    (article / "newer.mp3").write_bytes(b"newer-but-unregistered")
    (article / "newer.json").write_text(
        '{"prompt_version":"v2","song_name":"错误候选","generated_at":"9999"}',
        encoding="utf-8",
    )

    assert locate_theme_audio(article) is None
    _, errors = locate_theme_audio_record(article)
    assert any(MUSIC_MANIFEST_FILE in error for error in errors)

    _write_manifest(article, audio)
    asset, errors = validate_music_manifest(article)
    assert errors == [] and asset is not None
    assert locate_theme_audio(article) == audio
    assert asset.title == "边界之歌"
    assert asset.origin == {
        "provider": "example-provider",
        "model": "music-model-v3",
        "mode": "web_manual",
    }
    assert asset.registry["reference"] == "catalog/theme-songs.json"


def test_manifest_rejects_file_drift_without_falling_back(tmp_path: Path):
    article = tmp_path / "1-article"
    article.mkdir()
    audio = article / "theme.mp3"
    audio.write_bytes(b"original")
    _write_manifest(article, audio)

    audio.write_bytes(b"changed")
    (article / "fallback.mp3").write_bytes(b"plausible")

    asset, errors = validate_music_manifest(article)
    assert asset is None
    assert any("sha256" in error.lower() or "bytes" in error for error in errors)
    assert locate_theme_audio(article) is None


def test_manifest_requires_channel_neutral_label(tmp_path: Path):
    article = tmp_path / "1-article"
    article.mkdir()
    audio = article / "theme.mp3"
    audio.write_bytes(b"audio")
    path = _write_manifest(article, audio)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["theme"]["label"] = "某供应商临时通道"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    asset, errors = validate_music_manifest(article)
    assert asset is None
    assert any("通道中性标签" in error for error in errors)


def test_manifest_writer_refuses_audio_outside_article(tmp_path: Path):
    article = tmp_path / "article"
    article.mkdir()
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")

    try:
        _write_manifest(article, outside)
    except ValueError as exc:
        assert "越出文章目录" in str(exc)
    else:
        raise AssertionError("outside audio must be rejected")
