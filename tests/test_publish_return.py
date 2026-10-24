"""External receipt consumption and restart invariants; no network calls."""
import json
from unittest.mock import patch

from scripts import evidence, publish_return, release_to_draft
from scripts.article_paths import process_file


def test_package_consumer_rejects_empty_external_receipt(tmp_path):
    process_file(tmp_path, '_external-publish-receipt.json', for_write=True).write_text('{}')
    with patch.object(evidence, 'build_publish_manifest', return_value=({}, [])):
        _, errors = evidence.verify_publish_receipt(tmp_path, 'existing-draft')
    assert any('外部发布回传已失效' in e for e in errors)


def test_external_import_preserves_legacy_audio_handoff_bytes(tmp_path):
    (tmp_path / '定稿.md').write_text('正文')
    original, errors = release_to_draft.write_audio_handoff(tmp_path, 'existing-draft')
    assert not errors
    path = process_file(tmp_path, '_wechat-audio-handoff.json')
    original['created_at'] = '2000-01-01T00:00:00Z'
    path.write_text(json.dumps(original, ensure_ascii=False, indent=3) + '\n')
    before = path.read_bytes()
    result, errors = release_to_draft.write_audio_handoff(
        tmp_path, 'existing-draft', external_job_key='job')
    assert not errors
    assert result == original
    assert path.read_bytes() == before


def test_external_handoff_rebinds_only_when_source_roles_change(tmp_path):
    (tmp_path / '定稿.md').write_text('<!-- PODCAST-CARD-START -->')
    audio = tmp_path / 'dist/podcast/audio.mp3'
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b'offline-audio-fixture')
    first, errors = release_to_draft.write_audio_handoff(
        tmp_path, 'existing-draft', external_job_key='job')
    assert not errors
    assert first['status'] == 'external_media_verified'
    audio.write_bytes(b'changed-offline-fixture')
    changed, errors = release_to_draft.write_audio_handoff(
        tmp_path, 'existing-draft', external_job_key='job')
    assert not errors
    assert changed['roles'][0]['sha256'] != first['roles'][0]['sha256']


def test_empty_return_refused(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        publish_return.validate_return(tmp_path, {})
