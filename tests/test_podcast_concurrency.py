"""Offline producer tests: a real control flow, fake network/encoder, no paid jobs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import podcast_episode as pe


@pytest.fixture
def producer(tmp_path, monkeypatch):
    article = tmp_path / 'article'
    article.mkdir()
    draft = article / '定稿.md'
    draft.write_text('# 测试标题\n\n已批准的正文。\n')
    prompt = article / 'focus.txt'
    prompt.write_text('仅讨论原文。')
    config = {'enabled': True, 'focus_prompt': str(prompt), 'language': 'zh'}
    monkeypatch.setattr(pe, 'cfg', lambda: config)
    monkeypatch.setattr(pe.distribute, 'channel_dir', lambda d, name: d / 'dist' / name)
    monkeypatch.setattr(pe.distribute, 'read_final_title', lambda d: ((d / '定稿.md').read_text().splitlines() or [''])[0][2:])
    monkeypatch.setattr(pe.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(pe.shutil, 'which', lambda name: '/fake/' + name)
    monkeypatch.setattr(pe, 'probe_audio', lambda p: ({'codec_name': 'mp3', 'duration_seconds': 80}, ''))
    monkeypatch.setattr(pe, '_record_phase', lambda *args: None)
    out = pe.distribute.channel_dir(article, 'podcast')
    out.mkdir(parents=True)
    (out / 'audio.mp3').write_bytes(b'original-audio')
    (out / 'audio.manifest.json').write_text('{"old": true}')
    calls, sources = [], []
    change = lambda: None

    def network(*args, **kwargs):
        calls.append(args[:2])
        if args[:2] == ('notebook', 'create'):
            return {'id': 'notebook'}
        if args[:2] == ('source', 'add'):
            sources.append(Path(args[args.index('--file') + 1]).read_text())
        if args[:2] == ('audio', 'create'):
            return {'artifact_id': 'artifact'}
        if args[:2] == ('studio', 'status'):
            change()
            return [{'id': 'artifact', 'status': 'completed'}]
        if args[:2] == ('download', 'audio'):
            Path(args[args.index('-o') + 1]).write_bytes(b'x' * (pe.MIN_AUDIO_BYTES + 1))
        return []

    monkeypatch.setattr(pe, 'run_nlm', network)
    monkeypatch.setattr(pe.subprocess, 'run', lambda args, **kwargs: Path(args[-1]).write_bytes(b'new-audio'))

    def run(mutation=lambda: None):
        nonlocal change
        change = mutation
        return pe.cmd_generate(article)
    return article, draft, prompt, config, out, calls, sources, run


@pytest.mark.parametrize('mutation', ['body', 'title', 'prompt', 'parameters'])
def test_changed_inputs_during_generation_never_relabel_old_audio(producer, mutation):
    article, draft, prompt, config, out, calls, sources, run = producer
    frozen = draft.read_text()
    def change():
        if mutation == 'body':
            draft.write_text(frozen + '\n新的结论。')
        elif mutation == 'title':
            draft.write_text(frozen.replace('测试标题', '新的标题'))
        elif mutation == 'prompt':
            prompt.write_text('改为另一种主持风格。')
        else:
            config['language'] = 'en'
    assert run(change) == 2
    assert sources == [frozen]
    assert (out / 'audio.mp3').read_bytes() == b'original-audio'
    assert json.loads((out / 'audio.manifest.json').read_text()) == {'old': True}
    assert len(list(out.glob('audio.input-drift-*.mp3'))) == 1
    assert not pe.generation_is_fresh(article, config)


def test_image_assembly_can_finish_while_podcast_runs(producer):
    article, draft, _, config, out, _, sources, run = producer
    frozen = draft.read_text()
    def add_machine_blocks():
        draft.write_text(frozen + '\n<!-- AUDIO-CARD-START -->音乐就绪<!-- AUDIO-CARD-END -->\n')
    assert run(add_machine_blocks) == 0
    assert sources == [frozen]
    assert (out / 'audio.mp3').read_bytes() == b'new-audio'
    assert pe.generation_is_fresh(article, config)


def test_second_producer_does_not_create_duplicate_remote_job(producer):
    article, _, _, _, _, calls, _, run = producer
    second = []
    assert run(lambda: second.append(pe.cmd_generate(article))) == 0
    assert second == [4]
    assert calls.count(('notebook', 'create')) == 1
    # Lock is released after completion; the fresh audio is reused.
    assert pe.cmd_generate(article) == 0
    assert calls.count(('notebook', 'create')) == 1


def test_empty_source_fails_before_remote_creation(producer):
    _, draft, _, _, _, calls, _, run = producer
    draft.write_text('')
    assert run() == 2
    assert not calls


def test_failed_call_records_time_without_source_or_ids(monkeypatch, tmp_path):
    import contracts
    records = []
    monkeypatch.setattr(contracts, 'log_observation', lambda *a, **k: records.append((a, k)))
    monkeypatch.setattr(pe, '_run_nlm', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    token = pe._ACTIVE_ARTICLE.set(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            pe.run_nlm('source', 'add', 'private-notebook-id', '--file', 'private.md')
    finally:
        pe._ACTIVE_ARTICLE.reset(token)
    assert records[0][0] == ('podcast_generation', 'nlm.source.add', 'fail')
    assert records[0][1]['elapsed_ms'] >= 0
    assert 'private' not in str(records)


def test_generated_audio_still_publishes_with_receipt(producer, monkeypatch):
    from types import SimpleNamespace
    article, _, _, config, out, _, _, run = producer
    assert run() == 0
    config.update(remote_host='test.invalid', remote_episodes_dir='/test', feed_rebuild_command='rebuild')
    monkeypatch.setattr(pe, '_scp_with_retry', lambda *a, **k: True)
    monkeypatch.setattr(pe.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    assert pe.cmd_publish(article, confirm=True) == 0
    receipt = json.loads((out / pe.distribute.RECEIPT_FILE).read_text())
    assert receipt['generation_digest'] == pe.generation_digest(article, config)
    assert receipt['source_digest'] == pe.distribute.source_digest(article, 'podcast')
