import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from scripts import profile_config
from scripts.stylebook_branding import produce_branded, branded_manifest
from scripts.stylebook_review import production_inputs, review_candidate, verify_candidate_review
from scripts.stylebook_workflow import digest
from test_stylebook_review import candidate, mocked_reviewer


def branded(tmp_path, monkeypatch):
    base = candidate(tmp_path, monkeypatch)
    profile = tmp_path / 'profile'
    (profile / 'brand').mkdir(parents=True)
    for name, color in [('logo.png', 'white'), ('logo-black.png', 'black')]:
        Image.new('RGBA', (80, 30), color).save(profile / 'brand' / name)
    monkeypatch.setattr(profile_config, 'bind_workspace', lambda cwd: None)
    monkeypatch.setattr(profile_config, 'profile_dir', lambda: profile)
    monkeypatch.setattr(profile_config, 'identity', lambda: {'logo_text_allowlist': ['Example'], 'logo_text_exact': ['Example']})
    base_path = Path(base['receipt_path'])
    base_bytes = base_path.read_bytes()
    record = produce_branded(tmp_path, base_path)
    assert base_path.read_bytes() == base_bytes
    path = tmp_path / record['production_path']
    assert production_inputs(tmp_path, path)[0]['production_method'] == 'brand_postprocess'
    return path, record


def test_real_brand_postprocess_preserves_base_and_reaches_review_consumer(tmp_path, monkeypatch):
    path, record = branded(tmp_path, monkeypatch)
    with Image.open(path.parent / 'main.png') as im:
        assert im.convert('RGBA').getchannel('A').getextrema() == (255, 255)
    assert all(row['watermarked'] for row in record['branding']['ledger'].values())
    with pytest.raises(ValueError, match='重复'):
        produce_branded(tmp_path, path)
    mocked_reviewer(monkeypatch)
    report, errors = review_candidate(tmp_path, path)
    assert not errors and report['passed']
    verify_candidate_review(tmp_path, Path(report['report_path']))
    (tmp_path / 'profile/brand/logo.png').write_bytes(b'changed logo')
    with pytest.raises(ValueError, match='改变'):
        verify_candidate_review(tmp_path, Path(report['report_path']))


def test_real_consumer_rejects_false_brand_ledger_even_with_rehashed_candidate(tmp_path, monkeypatch):
    path, record = branded(tmp_path, monkeypatch)
    original_files = dict(record['files'])
    record.pop('production_path')
    record['branding']['ledger']['main']['watermarked'] = False
    identity = {k: v for k, v in record.items() if k not in ('production_id', 'files')}
    new_id = digest(identity)
    dest = path.parent.parent / new_id
    dest.mkdir()
    record['production_id'] = new_id
    for key, rel in original_files.items():
        target = dest / Path(rel).name
        shutil.copyfile(tmp_path / rel, target)
        record['files'][key] = str(target.relative_to(tmp_path))
    changed = dest / 'production.json'
    changed.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='没有实际水印'):
        production_inputs(tmp_path, changed)


def test_branding_rejects_empty_request():
    with pytest.raises(ValueError, match='缺真实'):
        branded_manifest({}, {})


@pytest.mark.parametrize('width', [0, float('nan'), 0.3, True])
def test_invalid_brand_scale_cannot_produce_candidate(tmp_path, monkeypatch, width):
    path, record = branded(tmp_path, monkeypatch)
    base = tmp_path / record['branding']['base_production']
    with pytest.raises(ValueError, match='水印宽度'):
        produce_branded(tmp_path, base, width_fraction=width)


def test_explicit_brand_scale_changes_actual_output_and_is_bound(tmp_path, monkeypatch):
    path, record = branded(tmp_path, monkeypatch)
    base = tmp_path / record['branding']['base_production']
    larger = produce_branded(tmp_path, base, width_fraction=0.2)
    assert larger['branding']['width_fraction'] == 0.2
    assert larger['outputs']['main']['sha256'] != record['outputs']['main']['sha256']
    large_path = tmp_path / larger['production_path']
    production_inputs(tmp_path, large_path)
    with Image.open(path.parent / 'main.png') as a, Image.open(large_path.parent / 'main.png') as b:
        from PIL import ImageChops
        assert ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is not None
        assert a.size == b.size
