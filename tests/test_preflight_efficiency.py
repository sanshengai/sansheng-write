"""Deduplicate aliases, never memoize acceptance or relax mutation checks."""
import json
import os
from pathlib import Path

import pytest
from PIL import Image
from scripts import pipeline
from scripts.article_paths import process_file
from scripts.stylebook_acceptance import reject_candidate
from test_stylebook_evidence import completed


def visual_fixture(tmp_path, monkeypatch):
    result = completed(tmp_path, monkeypatch, body=True)
    (tmp_path / '素材/hero.png').write_bytes((tmp_path / '素材/cover.png').read_bytes())
    (tmp_path / '定稿.html').write_text('<!-- AUDIO-CARD-START --><!-- PODCAST-CARD-START -->')
    import contracts
    monkeypatch.setattr(contracts, 'verify_publish_assets', lambda _: {'errors': []})
    # This test isolates visual acceptance; reading validation has its own suite.
    import stylebook_release
    monkeypatch.setattr(stylebook_release, 'reading_errors', lambda _: [])
    return result


def test_schema2_calls_group_gate_once_without_legacy_aliases(tmp_path, monkeypatch):
    visual_fixture(tmp_path, monkeypatch)
    original = pipeline._stylebook_release_errors
    calls = []
    monkeypatch.setattr(pipeline, '_stylebook_release_errors', lambda root: (calls.append(root), original(root))[1])
    def duplicate(*args, **kwargs):
        raise AssertionError('schema2 must not repeat this alias')
    for name in ('_cover_route_errors', '_visual_route_errors', '_visual_qa_errors', 'verify_visual_receipt'):
        monkeypatch.setattr(pipeline, name, duplicate)
    assert pipeline._pre_publish_errors(tmp_path) == []
    assert len(calls) == 1


@pytest.mark.parametrize('mutation', ['pixel_same_mtime', 'objection', 'extra_image', 'qa_empty', 'seal', 'author', 'missing_image', 'review'])
def test_preflight_still_rejects_mutations_after_prior_success(tmp_path, monkeypatch, mutation):
    _, _, reports, selected = visual_fixture(tmp_path, monkeypatch)
    assert pipeline._pre_publish_errors(tmp_path) == []
    target = tmp_path / '素材/cover.png'
    if mutation == 'pixel_same_mtime':
        stat = target.stat()
        with Image.open(target) as im:
            image = im.convert('RGB')
        image.putpixel((0, 0), (1, 2, 3))
        image.save(target)
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    elif mutation == 'objection':
        reject_candidate(tmp_path, tmp_path / selected['assets']['cover']['production'], 'wrong design')
    elif mutation == 'extra_image':
        (tmp_path / '素材/infographic-extra.png').write_bytes(target.read_bytes())
    elif mutation == 'qa_empty':
        process_file(tmp_path, '_visual-qa.json').write_text('{}')
    elif mutation == 'seal':
        process_file(tmp_path, '_visual-receipt.json').write_text('{}')
    elif mutation == 'author':
        path = tmp_path / '定稿.md'
        path.write_text(path.read_text() + '\nUnapproved new claim\n')
    elif mutation == 'missing_image':
        target.unlink()
    else:
        reports['cover'].write_text('{}')
    assert pipeline._pre_publish_errors(tmp_path)


def test_empty_input_fails_before_expensive_visual_work(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('cheap failure should not run deep visual validation')
    monkeypatch.setattr(pipeline, '_stylebook_release_errors', unexpected)
    monkeypatch.setattr(pipeline, '_cover_route_errors', unexpected)
    errors = pipeline._pre_publish_errors(tmp_path)
    assert any('cover.png' in e for e in errors)
    assert any('定稿.html' in e for e in errors)


@pytest.mark.parametrize('drift', [False, True])
def test_draft_entry_rebinds_only_machine_blocks_before_preflight(tmp_path, monkeypatch, drift):
    from test_release_job import _article, _run
    from scripts.evidence import sha256_file
    import release_to_draft as transaction
    article = _article(tmp_path)
    assert _run(article, 'adopt-final').returncode == 0
    path = article / '定稿.md'
    path.write_text(path.read_text() + ('\nNew author claim\n' if drift else
        '\n<!-- SANSHENG-VISUAL-START:01 -->\n![图](素材/infographic-01.png)\n<!-- SANSHENG-VISUAL-END:01 -->\n'))
    calls = []
    monkeypatch.setattr(pipeline, '_pre_publish_errors', lambda _: calls.append('preflight') or [])
    monkeypatch.setattr(pipeline, 'write_publish_ready', lambda _: ({'manifest_digest': 'test-only'}, []))
    def capture(root, *, preflight):
        ready, errors = preflight(root)
        if drift:
            assert errors and ready is None
            assert calls == []
        else:
            assert not errors and ready
            job = json.loads(process_file(root, '_release-job.json').read_text())
            assert job['final_sha256'] == sha256_file(path)
            assert calls == ['preflight']
        # No network/publication: stop after inspecting the actual callback.
        return None, ['test stopped before upload']
    monkeypatch.setattr(transaction, 'release_to_draft', capture)
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_release_to_draft(article)
    assert exc.value.code == 2


def test_asset_contract_failure_is_timed_as_failure(tmp_path, monkeypatch):
    import contracts
    events = []
    monkeypatch.setattr(contracts, 'verify_publish_assets', lambda _: {'errors': ['missing input']})
    monkeypatch.setattr(contracts, 'log_observation', lambda *args, **kwargs: events.append((args, kwargs)))
    errors = pipeline._pre_publish_errors(tmp_path)
    assert any('missing input' in e for e in errors)
    matches = [args for args, _ in events if args[:2] == ('publish_preflight', 'asset_contract')]
    assert matches and matches[0][2] == 'fail'
