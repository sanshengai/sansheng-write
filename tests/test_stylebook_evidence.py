"""Formal consumers bind complete reviews and exact final article/image bytes."""
import json

import pytest

from scripts.article_paths import process_file
from scripts.assemble_release import assemble_release_markdown
from scripts.evidence import build_visual_manifest, seal_visual_receipt, verify_visual_receipt
from scripts.visual_qa import run_visual_qa, validate_qa_result, final_byte_errors
from scripts.stylebook_acceptance import reject_candidate
from test_stylebook_assembly import accepted_group


def completed(tmp_path, monkeypatch, body=True):
    _, reports, selected = accepted_group(tmp_path, monkeypatch, body=body)
    _, errors = assemble_release_markdown(tmp_path)
    assert not errors
    qa, errors = run_visual_qa(tmp_path)
    assert not errors, errors
    receipt, errors = seal_visual_receipt(tmp_path)
    assert not errors, errors
    return qa, receipt, reports, selected


@pytest.mark.parametrize('body', [False, True])
def test_final_consumers_aggregate_actual_reviews_without_inventing_another_review(tmp_path, monkeypatch, body):
    qa, receipt, _, _ = completed(tmp_path, monkeypatch, body)
    assert qa['additional_independent_review'] is False
    assert qa['reading_preview_verified'] is False
    assert receipt['status'] == 'visual_sealed_pending_reading_review'
    manifest, errors = build_visual_manifest(tmp_path)
    assert not errors and len(manifest['assets']) == 1 + int(body)
    assert all(a['generation']['model'] is None for a in manifest['assets'])
    assert all(a['generation']['independent_invocation_verified'] is False for a in manifest['assets'])
    assert not validate_qa_result(tmp_path, qa)
    assert not final_byte_errors(tmp_path, qa)
    actual, errors = verify_visual_receipt(tmp_path)
    assert not errors and actual == receipt


@pytest.mark.parametrize('mutation', ['image', 'author', 'report', 'objection', 'qa', 'request', 'seal', 'empty_assets'])
def test_sealed_consumer_rejects_changed_or_empty_evidence(tmp_path, monkeypatch, mutation):
    qa, receipt, reports, selected = completed(tmp_path, monkeypatch)
    if mutation == 'image':
        (tmp_path / '素材/cover.png').write_bytes(b'changed')
    elif mutation == 'author':
        with (tmp_path / '定稿.md').open('a') as stream:
            stream.write('\nA changed author claim\n')
    elif mutation == 'report':
        reports['cover'].write_text('{}')
    elif mutation == 'objection':
        objection = reject_candidate(tmp_path, tmp_path / selected['assets']['cover']['production'], 'Visible unexpected logo')
        assert objection['reason'] == 'Visible unexpected logo'
    elif mutation == 'qa':
        qa['additional_independent_review'] = True
        process_file(tmp_path, '_visual-qa.json').write_text(json.dumps(qa))
    elif mutation == 'request':
        process_file(tmp_path, '_visual-qa-request.json').write_text('{}')
    elif mutation == 'seal':
        receipt['qa_status'] = 'fail'
        process_file(tmp_path, '_visual-receipt.json').write_text(json.dumps(receipt))
    else:
        qa['assets'] = []
        process_file(tmp_path, '_visual-qa.json').write_text(json.dumps(qa))
    actual, errors = verify_visual_receipt(tmp_path)
    assert actual is None and errors


def test_unassembled_or_missing_reviews_never_become_a_seal(tmp_path, monkeypatch):
    accepted_group(tmp_path, monkeypatch, body=True)
    qa, errors = run_visual_qa(tmp_path)
    assert qa is None and errors
    receipt, errors = seal_visual_receipt(tmp_path)
    assert receipt is None and errors


def test_old_reviewer_command_cannot_be_silently_replaced_by_aggregation(tmp_path, monkeypatch):
    accepted_group(tmp_path, monkeypatch, body=False)
    qa, errors = run_visual_qa(tmp_path, reviewer_command=['old-baoyu-review'])
    assert qa is None and errors
