from scripts import pipeline


def test_visual_route_hints_keep_schema2_out_of_legacy_mutations(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, '_stylebook_selected', lambda cwd: True)
    assert '固定张数' in pipeline._stage_description(tmp_path, 'infographic', hint=True)
    assert '不得' in pipeline._stage_description(tmp_path, 'logo', hint=True)
    assert 'add_logo.js' not in pipeline._stage_description(tmp_path, 'logo', hint=True)
    monkeypatch.setattr(pipeline, '_stylebook_selected', lambda cwd: False)
    assert pipeline._stage_description(tmp_path, 'logo', hint=True) == pipeline.STAGE_HINTS['logo']
