"""An exact author title is permitted only with current, local source evidence."""
import copy
import hashlib
import sys
import subprocess

import pytest
import yaml

from scripts import contracts, pipeline, release_job
from scripts.title_policy import title_prefix_errors

TITLE = 'AI，让经验变成新的作品！'
WORDS = '标题就用：' + TITLE


def _case(tmp_path):
    article = tmp_path / 'article'
    article.mkdir()
    evidence = article / 'title-instruction.md'
    evidence.write_text('作者原话：' + WORDS + '\n', encoding='utf-8')
    policy = {
        'mode': 'author-exact', 'exact_title': TITLE, 'author_words': WORDS,
        'evidence_file': evidence.name,
        'evidence_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    meta = {
        'title': TITLE, 'title_policy': policy, 'category': 'OBS',
        'outward_category': 'insight', 'tags': ['个人成长'], 'digest': '真实经验与新的学习机会',
        'infographic_style': 'claymation', 'visual_profile': 'warm-light-clay',
        'cover_style': 'montage-evidence',
        'lead': {'line1': '经验的力量', 'line2': '让想法做出来', 'accent': '做出来',
                 'subtitle': '一个普通人的真实尝试', 'tag1': '经验', 'tag2': '行动',
                 'ghost': 'IDEA × ACTION'},
    }
    (article / '定稿.md').write_text('# ' + TITLE + '\n\n' + '真实经验和实际尝试。' * 220, encoding='utf-8')
    _write_meta(article, meta)
    return article, meta


def _write_meta(article, meta):
    (article / 'article-meta.yaml').write_text(yaml.safe_dump(meta, allow_unicode=True), encoding='utf-8')


def _all_errors(article):
    _, adopt = release_job._validate_final_and_meta(article / '定稿.md', article / 'article-meta.yaml')
    _, _, archive = pipeline._archive_metadata(article, {})
    title = contracts.verify_title_contract(str(article))['violations']
    return [adopt, archive, title]


def _assert_rejected_everywhere(article):
    for errors in _all_errors(article):
        assert any('title_policy' in error or '分类标签前缀' in error for error in errors), errors


def test_author_exact_evidence_accepted_by_all_three_consumers(tmp_path):
    article, _ = _case(tmp_path)
    assert _all_errors(article) == [[], [], []]


@pytest.mark.parametrize('mutation', [
    'absent_policy', 'empty_policy', 'unknown_mode', 'old_title', 'empty_words',
    'words_without_title', 'missing_file', 'empty_file', 'changed_file',
    'wrong_quote', 'absolute_path', 'outside_path', 'symlink_escape',
])
def test_invalid_or_stale_evidence_rejected_by_all_consumers(tmp_path, mutation):
    article, meta = _case(tmp_path)
    policy = meta['title_policy']
    evidence = article / policy['evidence_file']
    if mutation == 'absent_policy': del meta['title_policy']
    elif mutation == 'empty_policy': meta['title_policy'] = {}
    elif mutation == 'unknown_mode': policy['mode'] = 'skip'
    elif mutation == 'old_title': policy['exact_title'] = '上一个标题'
    elif mutation == 'empty_words': policy['author_words'] = ''
    elif mutation == 'words_without_title': policy['author_words'] = '按这个做吧'
    elif mutation == 'missing_file': evidence.unlink()
    elif mutation == 'empty_file': evidence.write_text('')
    elif mutation == 'changed_file': evidence.write_text('作者原话：另一个标题\n')
    elif mutation == 'wrong_quote':
        evidence.write_text('转述：' + WORDS + '\n')
        policy['evidence_sha256'] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    elif mutation == 'absolute_path': policy['evidence_file'] = str(evidence)
    elif mutation == 'outside_path': policy['evidence_file'] = '../elsewhere.md'
    elif mutation == 'symlink_escape':
        outside = tmp_path / 'outside.md'
        outside.write_bytes(evidence.read_bytes())
        evidence.unlink()
        evidence.symlink_to(outside)
    _write_meta(article, meta)
    _assert_rejected_everywhere(article)


def test_changed_current_title_cannot_reuse_old_evidence(tmp_path):
    article, meta = _case(tmp_path)
    meta['title'] = '今天换了一个新标题'
    draft = article / '定稿.md'
    draft.write_text(draft.read_text().replace(TITLE, meta['title']))
    _write_meta(article, meta)
    _assert_rejected_everywhere(article)


def test_empty_input_is_not_an_author_exception(tmp_path):
    article, meta = _case(tmp_path)
    assert title_prefix_errors('', 'insight', title_policy=meta['title_policy'], article_dir=article)
    assert title_prefix_errors('', 'insight', article_dir=article)


def test_default_prefixed_title_still_works_without_exception():
    assert title_prefix_errors('洞察 | 经验与AI的配合', 'insight') == []
    assert title_prefix_errors('分享 | 经验与AI的配合', 'insight')


def test_exception_does_not_disable_other_title_rules(tmp_path):
    article, meta = _case(tmp_path)
    title = 'AI 的背后真相'
    policy = copy.deepcopy(meta['title_policy'])
    policy['exact_title'] = title
    policy['author_words'] = '标题：' + title
    evidence = article / policy['evidence_file']
    evidence.write_text('作者原话：' + policy['author_words'] + '\n')
    policy['evidence_sha256'] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    result = contracts.audit_title_contract(title, title_policy=policy, article_dir=article)
    assert result['verdict'] == 'fail'
    assert any('悬念' in error for error in result['violations'])


def test_mutation_removing_shared_guard_is_caught_at_actual_consumers(tmp_path, monkeypatch):
    article, meta = _case(tmp_path)
    del meta['title_policy']
    _write_meta(article, meta)
    _assert_rejected_everywhere(article)  # prove baseline negative before mutation
    for name in ('scripts.title_policy', 'title_policy'):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, 'title_prefix_errors', lambda *args, **kwargs: [])
    # The same negative oracle must fail if the shared guard is removed.
    with pytest.raises(AssertionError):
        _assert_rejected_everywhere(article)


def test_exact_title_evidence_never_substitutes_for_draft_approval(tmp_path):
    article, _ = _case(tmp_path)
    result = subprocess.run(
        [sys.executable, pipeline.__file__, 'adopt-final'], cwd=article,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'approval' in result.stdout or '审批' in result.stdout
    assert not (article / '.state.json').exists()
