"""Already-published registration consumes real files without sending another post."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlunsplit

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import distribute

WORDS = '请把这篇文章发布到微博。'
URL = 'https://weibo.com/1234567890/Ab123cd'
# Synthetic URL: no actual account or published article is embedded in fixtures.
ORIGINAL = urlunsplit(('https', 'mp.weixin.qq.com', '/s/' + 'ExampleArticle', '', ''))
COPY = f'中年人的经验，可以和 AI 一起发挥作用。\n全文：{ORIGINAL}\n#人工智能# #中年人#'


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def published(tmp_path, monkeypatch):
    root = tmp_path / 'article'
    cdir = root / 'dist/weibo'
    (cdir / 'images').mkdir(parents=True)
    (root / '定稿.md').write_text('# AI 与经验\n\n真实文章。', encoding='utf-8')
    (cdir / 'copy.txt').write_text(COPY, encoding='utf-8')
    (root / 'dist/社媒文案.txt').write_text(f'════════════ 微博 ════════════\n\n# 正文\n\n{COPY}\n', encoding='utf-8')
    for i in range(4):
        Image.new('RGB', (100, 100), (i*40, 30, 20)).save(cdir / 'images' / f'{i+1:02d}.png')
    write_json(root/'.state.json', {'stages': {'writing': {'title_final': 'AI 与经验'}, 'publish': {'wechat_url': ORIGINAL}}})
    monkeypatch.setattr(distribute, 'distribute_channel', lambda _: {'enabled': True})
    assert distribute.cmd_plan(root, only='weibo') == 0
    assert distribute.cmd_verify(root, 'weibo') == 0
    assets = [{'path': str(p.relative_to(root)), 'role': role,
               'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
              for p, role in [(cdir/'copy.txt', 'copy'), *[(p, 'image') for p in sorted((cdir/'images').glob('*.png'))]]]
    prefill = {'observed_at': '2026-10-23T11:40:00Z', 'method': 'Actual DOM and visual review',
               'channels': {'weibo': {'product': 'image_text', 'url': 'https://weibo.com/',
               'account_url': 'https://weibo.com/u/1234567890', 'assets': assets,
               'send_clicked': False, 'text_readback_verified': True, 'media_order_verified': True,
               'send_button_enabled': True, 'images_expected': 4, 'images_uploaded': 4,
               'uploaded_urls': [f'https://wx1.sinaimg.cn/bmiddle/p{i}.jpg' for i in range(4)]}}}
    publication = {'published_at': '2026-10-23T11:41:00Z', 'platform': 'weibo', 'account_id': '1234567890',
                   'url': URL, 'status': 'published', 'send_clicked': True,
                   'permalink_readback_verified': True, 'image_order_verified': True,
                   'images_expected': 4, 'images_published': 4,
                   'images': [f'https://wx1.sinaimg.cn/orj360/p{i}.jpg' for i in range(4)],
                   'text_readback': '账号导航\n' + COPY.replace(ORIGINAL, '网页链接') + '\n评论区域',
                   'links': [{'text': '网页链接', 'href': 'https://weibo.cn/sinaurl?u='+quote(ORIGINAL, safe='')}],
                   'local_prefill_receipt': 'prefill-verified.json', 'screenshot': 'published.png'}
    write_json(cdir/'prefill-verified.json', prefill)
    write_json(cdir/'publish-receipt.json', publication)
    (cdir/'authorization.md').write_text('用户原话：'+WORDS, encoding='utf-8')
    Image.new('RGB', (100, 100), 'white').save(cdir/'published.png')
    monkeypatch.setattr(distribute, 'cmd_dispatch', lambda *a, **k: pytest.fail('registration must not send'))
    return root, cdir, prefill, publication


def record(data, words=WORDS):
    root, cdir, _, _ = data
    return distribute.cmd_record_published(root, 'weibo', str(cdir/'publish-receipt.json'), words, str(cdir/'authorization.md'))


def test_record_verified_as_agent_authorized_without_sending(published):
    root, cdir, _, _ = published
    assert distribute.cmd_confirm(root, 'weibo', URL) == 2  # old author-only path remains closed
    assert record(published) == 0
    assert distribute.get_status(root, 'weibo') == 'sent'
    receipt = json.loads((cdir/distribute.RECEIPT_FILE).read_text())
    assert receipt['confirmed_by'] == 'agent_authorized_readback'
    assert receipt['authorization_words'] == WORDS
    assert receipt['registration_only'] is True
    assert receipt['post_url'] == URL
    for item in receipt['evidence'].values():
        assert item['sha256'] == hashlib.sha256((root/item['path']).read_bytes()).hexdigest()
    assert record(published) == 0  # repeat registration does not send


@pytest.mark.parametrize('case', [
    'bad_url', 'wrong_account', 'missing_image', 'changed_hash', 'missing_remote', 'remote_order',
    'unsent', 'unread', 'empty_readback', 'different_body', 'wrong_link', 'no_authorization',
    'source_drift', 'missing_hash', 'prefill_missing_image', 'prefill_order', 'outside', 'symlink',
    'empty_evidence', 'malformed_prefill', 'earlier_publication', 'missing_screenshot',
    'wrong_copy', 'different_existing_url', 'not_verified',
])
def test_bad_evidence_rejected_without_state_or_receipt_write(published, case, tmp_path):
    root, cdir, pref, pub = published
    ch = pref['channels']['weibo']
    if case == 'bad_url': pub['url'] = 'https://weibo.com/u/1234567890'
    elif case == 'wrong_account': pub['account_id'] = '111'
    elif case == 'missing_image': (cdir/'images/01.png').unlink()
    elif case == 'changed_hash': Image.new('RGB', (100, 100), 'blue').save(cdir/'images/01.png')
    elif case == 'missing_remote': pub['images'].pop()
    elif case == 'remote_order': pub['images'].reverse()
    elif case == 'unsent': pub['send_clicked'] = False
    elif case == 'unread': pub['permalink_readback_verified'] = False
    elif case == 'empty_readback': pub['text_readback'] = ''
    elif case == 'different_body': pub['text_readback'] = '不相关的一条微博'
    elif case == 'wrong_link': pub['links'][0]['href'] = 'https://example.invalid/wrong'
    elif case == 'no_authorization': (cdir/'authorization.md').write_text('仅准备草稿')
    elif case == 'source_drift': (root/'定稿.md').write_text('变动了定稿')
    elif case == 'missing_hash': ch['assets'][1].pop('sha256')
    elif case == 'prefill_missing_image': ch['assets'].pop()
    elif case == 'prefill_order': ch['assets'][1:] = reversed(ch['assets'][1:])
    elif case == 'outside':
        outside = tmp_path/'outside.json'; write_json(outside, pref)
        pub['local_prefill_receipt'] = str(outside)
    elif case == 'symlink':
        (cdir/'alias.json').symlink_to(cdir/'prefill-verified.json')
        pub['local_prefill_receipt'] = 'alias.json'
    elif case == 'malformed_prefill': pref['channels'] = ['weibo']
    elif case == 'earlier_publication': pub['published_at'] = '2026-10-23T11:39:00Z'
    elif case == 'missing_screenshot': pub['screenshot'] = 'not-found.png'
    elif case == 'wrong_copy': (root/'dist/社媒文案.txt').write_text('════════════ 微博 ════════════\n# 正文\n其他内容')
    elif case == 'different_existing_url':
        distribute.set_status(root, 'weibo', 'sent')
        write_json(cdir/distribute.RECEIPT_FILE, {'post_url': 'https://weibo.com/1234567890/Other'})
    elif case == 'not_verified': distribute.set_status(root, 'weibo', 'planned')
    write_json(cdir/'prefill-verified.json', pref)
    write_json(cdir/'publish-receipt.json', pub)
    if case == 'empty_evidence': (cdir/'publish-receipt.json').write_text('')
    before = distribute.read_state(root)
    receipt_path = cdir/distribute.RECEIPT_FILE
    before_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
    assert record(published) == 2
    assert distribute.read_state(root) == before
    assert (receipt_path.read_bytes() if receipt_path.exists() else None) == before_receipt
