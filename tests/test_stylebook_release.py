"""Actual article stage routing follows complete opt-in contracts, including zero body images."""
import pytest
from scripts import pipeline
from scripts.stylebook_release import stage_errors
from test_stylebook_evidence import completed


def ready_state():
    return {'stages': {stage: {'status': 'done'} for stage in pipeline.STAGE_ORDER}}


@pytest.mark.parametrize('body', [False, True])
def test_actual_cover_and_body_consumers_accept_reviewed_plan_quantity(tmp_path, monkeypatch, body):
    completed(tmp_path, monkeypatch, body)
    assert not stage_errors(tmp_path)
    for stage in ['cover', 'infographic']:
        ok, errors = pipeline.verify_stage(stage, tmp_path, ready_state())
        assert ok, errors
    assert not pipeline._cover_route_errors(tmp_path)
    assert not pipeline._visual_route_errors(tmp_path)
    errors = pipeline._pre_publish_errors(tmp_path)
    assert not any('需 ≥4' in e or 'claymation' in e or 'cover_route:' in e or 'visual_route:' in e for e in errors), errors
    # Other publishing requirements still apply; the fixture supplies no HTML or hero.
    assert any('定稿.html' in e for e in errors)
    assert any('hero.png' in e for e in errors)


@pytest.mark.parametrize('mutation', ['missing_cover', 'changed_body', 'extra_unreviewed_body', 'missing_review'])
def test_actual_stage_rejects_changed_or_extra_candidates(tmp_path, monkeypatch, mutation):
    _, _, reports, _ = completed(tmp_path, monkeypatch, body=True)
    if mutation == 'missing_cover':
        (tmp_path/'素材/cover.png').unlink()
    elif mutation == 'changed_body':
        (tmp_path/'素材/infographic-01.png').write_bytes(b'new unreviewed content')
    elif mutation == 'extra_unreviewed_body':
        (tmp_path/'素材/infographic-extra.png').write_bytes(b'extra unreviewed image')
    else:
        reports['cover'].unlink()
    ok, errors = pipeline.verify_stage('infographic', tmp_path, ready_state())
    assert not ok and errors
    assert pipeline._visual_route_errors(tmp_path)


def test_uncompiled_plan_cannot_waive_existing_stage_gate(tmp_path, monkeypatch):
    from test_stylebook_workflow import setup_plan
    setup_plan(tmp_path, monkeypatch, body=False)
    ok, errors = pipeline.verify_stage('cover', tmp_path, ready_state())
    assert not ok and errors
