import hashlib
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from website_evidence import media_errors

PROSE = '这是一段必须完整出现在正式网站入口上的真实文章正文。'


def check(tmp_path, source, body):
    (tmp_path / '定稿.md').write_text(source)
    return media_errors(tmp_path, 'AIT-1', 'https://site.example', body,
                        lambda url, method: (200, '', 'image/png'))


def test_empty_html_attributes(tmp_path):
    assert check(tmp_path, PROSE, f'<article class style>{PROSE}</article>') == []


@pytest.mark.parametrize('role', ['AUDIO', 'PODCAST'])
def test_editor_cards_are_not_expected_prose_but_real_body_is(tmp_path, role):
    card = f'<!-- {role}-CARD-START -->删除本段文字，并插入播客音频<!-- {role}-CARD-END -->'
    assert check(tmp_path, PROSE + '\n' + card, f'<article>{PROSE}</article>') == []
    assert check(tmp_path, PROSE + '\n' + card, '<article>旧正文</article>')
    assert check(tmp_path, PROSE + '\n' + card, f'<article>{PROSE}{card}</article>')


@pytest.mark.parametrize('variant,ok', [('original', True), ('current', True), ('stale', False), ('missing', False)])
def test_only_current_content_hash_alias_is_accepted(tmp_path, variant, ok):
    data = b'current-image-content'
    (tmp_path / 'figure.png').write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()[:8]
    name = {'original': 'figure.png', 'current': f'figure.h{digest}.png',
            'stale': 'figure.h00000000.png', 'missing': 'other.png'}[variant]
    errors = check(tmp_path, PROSE + '\n![图](figure.png)',
                   f'<article>{PROSE}<img src="/images/{name}"></article>')
    assert (errors == []) is ok


def test_missing_source_remains_failure(tmp_path):
    assert media_errors(tmp_path, 'AIT-1', 'https://site.example', '<article/>', lambda *a: (200, ''))


def test_visible_song_player_uses_initially_hidden_shared_native_engine(tmp_path):
    from article_paths import process_file
    (tmp_path / '定稿.md').write_text(PROSE)
    process_file(tmp_path, '_music-manifest.json', for_write=True).write_text('{}')
    player = '<div class="song-player" data-src="/song-assets/AIT-1/song.mp3"></div>'
    engine = '<div id="mini-player" hidden><audio preload="none"></audio></div>'
    fetch = lambda *args: (200, '', 'audio/mpeg')
    assert media_errors(tmp_path, 'AIT-1', 'https://site.example', f'<article>{PROSE}{player}</article>{engine}', fetch) == []
    assert media_errors(tmp_path, 'AIT-1', 'https://site.example', f'<article>{PROSE}{player}</article>', fetch)
    assert media_errors(tmp_path, 'AIT-1', 'https://site.example', f'<article>{PROSE}</article><div hidden>{player}</div>{engine}', fetch)
