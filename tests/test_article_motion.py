"""Synthetic media fixtures exercise the real article assembly/seal consumers."""
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts import article_motion as M
from scripts.stylebook_workflow import sha
from scripts.stylebook_assembly import assemble, verify_assembly
from scripts.stylebook_evidence import aggregate, seal, verify_seal
from scripts.stylebook_release import stage_errors
from scripts.stylebook_reading import context as reading_context, CHECKS, accept_reading, verify_reading
from scripts.assemble_release import author_content_sha256
from test_stylebook_assembly import accepted_group


def handoff(tmp_path, monkeypatch):
    _, _, group = accepted_group(tmp_path, monkeypatch, body=True)
    batch, plan = M.context(tmp_path)
    root = tmp_path / 'synthetic-handoff'
    root.mkdir()
    frames = [Image.new('RGB', (64, 36), color) for color in ['red', 'green', 'blue']]
    frames[0].save(root / 'motion.gif', save_all=True, append_images=frames[1:],
                   duration=[120, 240, 360], loop=0)
    frames[0].save(root / 'poster.png')
    for name in ['motion.mp4', 'timeline.jpg', 'UPSTREAM.md']:
        (root / name).write_text('Synthetic test evidence: ' + name)
    candidate = {'files': {name: sha(root / name) for name in ['motion.gif', 'motion.mp4', 'timeline.jpg']}}
    (root / 'candidate.json').write_text(json.dumps(candidate))
    review = {'state': 'agent-reviewed-candidate', 'candidate_sha256': sha(root / 'candidate.json'),
              'assessment': {'verdict': 'accept', 'playback': {'cycles': 2},
                             'checks': {key: {'result': 'pass', 'note': 'Synthetic check'} for key in M.CHECKS}},
              'evidence_sha256': {'timeline.jpg': sha(root / 'timeline.jpg')}}
    (root / 'review.json').write_text(json.dumps(review))
    files = {role: {'path': name, 'sha256': sha(root / name), 'bytes': (root / name).stat().st_size}
             for role, name in {'gif': 'motion.gif', 'poster': 'poster.png', 'preview': 'motion.mp4',
                                'timeline': 'timeline.jpg', 'review': 'review.json',
                                'candidate': 'candidate.json', 'upstream': 'UPSTREAM.md'}.items()}
    chosen = group['assets']['01']
    value = {'contract': M.CONTRACT, 'state': 'reviewed_pending_user_adoption', 'files': files,
             'source': {'article_sha256': batch['source']['sha256'], 'static_sha256': chosen['image_sha256'],
                        'anchor': plan['article_plan']['items'][0]['position'][1:-3],
                        'style': chosen['style'], 'palette': chosen['palette']},
             'animation': M.animation(root / 'motion.gif'), 'candidate_sha256': sha(root / 'candidate.json')}
    path = root / 'article-media.json'
    path.write_text(json.dumps(value))
    return path, value


def prepared(tmp_path, monkeypatch):
    path, _ = handoff(tmp_path, monkeypatch)
    result = M.prepare(tmp_path, '01', path)
    return Path(result['candidate'])


def adopted(tmp_path, monkeypatch):
    candidate = prepared(tmp_path, monkeypatch)
    M.adopt(tmp_path, candidate, 'Synthetic author: adopt this candidate', 'Test author')
    result, errors = assemble(tmp_path)
    assert not errors, errors
    return candidate, result


def test_prepare_does_not_adopt_or_copy_undeclared_files(tmp_path, monkeypatch):
    path, _ = handoff(tmp_path, monkeypatch)
    (path.parent / 'unrelated-secret.txt').write_text('Must stay outside the handoff')
    result = M.prepare(tmp_path, '01', path)
    assert not (tmp_path / M.SELECTION).exists()
    assert not list(Path(result['candidate']).parent.rglob('unrelated-secret.txt'))
    assembled, errors = assemble(tmp_path)
    assert not errors, errors
    assert assembled['assets']['01']['output'].endswith('.png')
    assert '.gif' not in (tmp_path / '定稿.md').read_text()


@pytest.mark.parametrize('palette,accepted', [
    ({'family': 'orig'}, True),
    ({'family': 'peach'}, False),
    ({}, False),
    ('orig', False),
])
def test_prepare_matches_compiler_default_without_accepting_other_palettes(tmp_path, monkeypatch, palette, accepted):
    path, value = handoff(tmp_path, monkeypatch)
    assert value['source']['palette'] is None
    value['source']['palette'] = palette
    path.write_text(json.dumps(value))
    if accepted:
        candidate = Path(M.prepare(tmp_path, '01', path)['candidate'])
        assert candidate.is_file()
        M.adopt(tmp_path, candidate, 'Synthetic adoption', 'Test author')
        result, errors = assemble(tmp_path)
        assert not errors, errors
        assert result['assets']['01']['output'].endswith('.gif')
        verify_assembly(tmp_path)
    else:
        with pytest.raises(ValueError, match='画风色板不一致'):
            M.prepare(tmp_path, '01', path)


def test_request_exports_exact_selected_source_and_a_real_image_brief(tmp_path, monkeypatch):
    from scripts.stylebook_group import verify_group
    import importlib
    accepted_group(tmp_path, monkeypatch, body=True)
    group = verify_group(tmp_path)
    result = M.request(tmp_path, '01', 'Show why verification follows download')
    assert result['static_sha256'] == group['assets']['01']['image_sha256']
    assert sha(Path(result['article'])) == result['article_sha256']
    brief_path = Path(result['brief_path'])
    # The real peer compiler must consume this brief; it is not a handwritten prepared receipt.
    root = Path(__file__).resolve().parents[2] / 'sansheng-image'
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    make = importlib.import_module('stylebook.make')
    compiled = make.prepare(json.loads(brief_path.read_text()), base_path=brief_path.parent)
    assert compiled['source']['sha256'] == result['article_sha256']
    assert compiled['tasks'][0]['manifest']['style'] == group['assets']['01']['style']
    assert not (tmp_path / M.SELECTION).exists()
    with pytest.raises(ValueError):
        M.request(tmp_path, 'cover', 'No animated cover')
    with pytest.raises(ValueError):
        M.request(tmp_path, '01', '')


def test_adopted_gif_reaches_assembly_seal_and_reading_unchanged(tmp_path, monkeypatch):
    candidate, result = adopted(tmp_path, monkeypatch)
    draft = (tmp_path / '定稿.md').read_text()
    batch, _ = M.context(tmp_path)
    original = (tmp_path / batch['source_snapshot']).read_text()
    assert author_content_sha256(draft) == author_content_sha256(original)
    assert '素材/infographic-01.gif' in draft
    media = tmp_path / '素材/infographic-01.gif'
    assert M.animation(media)['durations_ms'] == [120, 240, 360]
    assert sha(media) == json.loads(candidate.read_text())['files']['gif']['sha256']
    assert not stage_errors(tmp_path)
    verify_assembly(tmp_path)
    qa, errors = aggregate(tmp_path)
    assert not errors, errors
    _, errors = seal(tmp_path)
    assert not errors, errors
    verify_seal(tmp_path)
    from scripts.md_render import render_file
    render_file(tmp_path / '定稿.md')
    assert 'infographic-01.gif' in (tmp_path / '定稿.html').read_text()
    actual = reading_context(tmp_path)
    assert any(item['path'].endswith('.gif') and item['sha256'] == sha(media) for item in actual['images'])
    assert next(a for a in qa['assets'] if a['id'] == '01')['motion']['platform_playback'] == 'unverified'
    observation = {'schema_version': 1, 'html_sha256': actual['html_sha256'],
                   'source_strength': 'host_attested_browser_and_native_reading',
                   'additional_independent_review': False, 'native_checks': dict.fromkeys(CHECKS, True), 'views': []}
    for width in [390, 430, 900]:
        image = tmp_path / f'synthetic-reading-{width}.png'
        Image.new('RGB', (width, 844), 'ivory').save(image)
        observation['views'].append({'width': width, 'document_width': width, 'document_height': 844,
            'viewport_height': 844, 'images': [{**item, 'loaded': True, 'natural_width': 64, 'display_width': width - 64}
                                             for item in actual['images']],
            'screenshot': {'path': image.name, 'sha256': sha(image)}})
    record_path = tmp_path / 'synthetic-reading.json'
    record_path.write_text(json.dumps(observation))
    rejected, errors = accept_reading(tmp_path, record_path)
    assert rejected is None and errors  # A loaded first frame cannot pass dynamic reading.
    screens = []
    for i, color in enumerate(['red', 'blue']):
        image = tmp_path / f'synthetic-motion-state-{i}.png'
        Image.new('RGB', (390, 844), color).save(image)
        screens.append({'path': image.name, 'sha256': sha(image), 'at_ms': i * 200})
    playback = {**actual['motions'][0], 'width': 390, 'cycles': 2,
                'method': 'Synthetic browser playback fixture', 'evidence': screens,
                'checks': {'all_states_readable': True, 'meaning_matches_context': True, 'loop_continuous': True}}
    observation['motion_playback'] = [playback]
    record_path.write_text(json.dumps(observation))
    _, errors = accept_reading(tmp_path, record_path)
    assert not errors, errors
    verify_reading(tmp_path)
    for key, mutated in [('cycles', 0), ('sha256', '0' * 64), ('evidence', [screens[0], screens[0]])]:
        old = playback[key]
        playback[key] = mutated
        record_path.write_text(json.dumps(observation))
        rejected, errors = accept_reading(tmp_path, record_path)
        assert rejected is None and errors
        playback[key] = old


@pytest.mark.parametrize('mutation', ['gif', 'poster', 'adoption', 'candidate', 'anchor', 'static', 'extra_gif'])
def test_actual_consumer_rejects_changed_dynamic_inputs(tmp_path, monkeypatch, mutation):
    candidate, _ = adopted(tmp_path, monkeypatch)
    if mutation in {'gif', 'poster'}:
        suffix = 'gif' if mutation == 'gif' else 'png'
        (tmp_path / f'素材/infographic-01.{suffix}').write_bytes(b'changed')
    elif mutation == 'adoption':
        (tmp_path / M.SELECTION).write_text('{}')
    elif mutation == 'candidate':
        candidate.write_text('{}')
    elif mutation == 'anchor':
        plan = tmp_path / 'visual-plan.json'
        value = json.loads(plan.read_text())
        value['article_plan']['items'][0]['position'] = '「Wrong anchor。」之后'
        plan.write_text(json.dumps(value))
    elif mutation == 'static':
        from scripts.stylebook_group import verify_group
        batch, plan = M.context(tmp_path)
        selected = verify_group(tmp_path)
        (tmp_path / selected['assets']['01']['image']).write_bytes(b'changed')
    else:
        (tmp_path / '素材/infographic-unregistered.gif').write_bytes(b'GIF89a')
        assert stage_errors(tmp_path)
        return
    with pytest.raises((ValueError, OSError, KeyError)):
        verify_assembly(tmp_path)


@pytest.mark.parametrize('mutation', ['empty', 'wrong_article', 'wrong_static', 'no_review', 'no_cycles', 'changed_gif'])
def test_prepare_rejects_empty_or_unrelated_handoffs(tmp_path, monkeypatch, mutation):
    path, value = handoff(tmp_path, monkeypatch)
    if mutation == 'empty':
        value = {}
    elif mutation == 'wrong_article':
        value['source']['article_sha256'] = '0' * 64
    elif mutation == 'wrong_static':
        value['source']['static_sha256'] = '0' * 64
    elif mutation in {'no_review', 'no_cycles'}:
        review_path = path.parent / 'review.json'
        review = json.loads(review_path.read_text())
        if mutation == 'no_review':
            review['assessment']['checks'] = {}
        else:
            review['assessment']['playback']['cycles'] = 0
        review_path.write_text(json.dumps(review))
        value['files']['review'].update(sha256=sha(review_path), bytes=review_path.stat().st_size)
    else:
        (path.parent / 'motion.gif').write_bytes(b'changed')
    path.write_text(json.dumps(value))
    with pytest.raises((ValueError, OSError, KeyError)):
        M.prepare(tmp_path, '01', path)
    assert not (tmp_path / M.SELECTION).exists()


def test_empty_adoption_cannot_select_a_candidate(tmp_path, monkeypatch):
    candidate = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='明确采用'):
        M.adopt(tmp_path, candidate, '', 'Test observer')
    assert not (tmp_path / M.SELECTION).exists()


def test_publish_assets_exempts_only_verified_motion_fallback(tmp_path, monkeypatch):
    from scripts.contracts import verify_publish_assets
    adopted(tmp_path, monkeypatch)
    assert not any('infographic-01.png' in e for e in verify_publish_assets(str(tmp_path))['errors'])
    Image.new('RGB', (64, 36), 'red').save(tmp_path / '素材/unregistered.png')
    assert any('unregistered.png' in e for e in verify_publish_assets(str(tmp_path))['errors'])
    (tmp_path / '素材/infographic-01.png').write_bytes(b'changed poster')
    assert any('动态备用图来源无效' in e for e in verify_publish_assets(str(tmp_path))['errors'])


def test_prepare_rejects_a_mutated_upload_path_that_flattens_animation(tmp_path, monkeypatch):
    path, _ = handoff(tmp_path, monkeypatch)
    monkeypatch.setattr(M.wechat_api, '_prepare_body_image',
                        lambda path: ('flattened.jpg', 'image/jpeg', b'flattened frame', 'mutant'))
    with pytest.raises(ValueError, match='变成了静态图'):
        M.prepare(tmp_path, '01', path)


def test_replace_stale_motion_preserves_history_and_validates_new(tmp_path, monkeypatch):
    candidate = prepared(tmp_path, monkeypatch)
    old = M.adopt(tmp_path, candidate, 'old delegated adoption', 'Test agent')
    # Make a second valid candidate with a distinct preparation identity.
    source = candidate.parent / 'source/article-media.json'
    base_sha = M.sha
    monkeypatch.setattr(M, 'sha', lambda p: 'new-method' if Path(p) == Path(M.__file__) else base_sha(p))
    replacement = Path(M.prepare(tmp_path, '01', source)['candidate'])
    assert replacement != candidate
    with pytest.raises(ValueError):
        M.resolve(tmp_path, *M.context(tmp_path))
    before = (tmp_path / M.SELECTION).read_bytes()
    with pytest.raises(ValueError):
        M.adopt_many(tmp_path, [replacement, candidate], 'replace', 'Test agent')
    assert (tmp_path / M.SELECTION).read_bytes() == before
    new = M.adopt_many(tmp_path, [replacement], 'replace under delegation', 'Test agent')
    assert new['items']['01']['candidate'] != old['items']['01']['candidate']
    assert (tmp_path / '素材/motion-selections' / (old['selection_id'] + '.json')).is_file()
    assert M.resolve(tmp_path, *M.context(tmp_path))['01']['candidate'] == new['items']['01']['candidate']


def test_replacement_cannot_hide_corrupt_selection_or_empty_input(tmp_path, monkeypatch):
    candidate = prepared(tmp_path, monkeypatch)
    M.adopt(tmp_path, candidate, 'adopt', 'Test agent')
    before = (tmp_path / M.SELECTION).read_bytes()
    with pytest.raises(ValueError):
        M.adopt_many(tmp_path, [], 'replace', 'Test agent')
    assert (tmp_path / M.SELECTION).read_bytes() == before
    record = json.loads(before);record['items']['01']['user_adoption']['words'] = 'tampered'
    (tmp_path / M.SELECTION).write_text(json.dumps(record))
    with pytest.raises(ValueError, match='不可变'):
        M.adopt(tmp_path, candidate, 'replace', 'Test agent')
