"""Catch publication format failures before generating paid assets."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pipeline


def result(root, body):
    (root / '定稿.md').write_text(body)
    (root / 'article-meta.yaml').write_text('title: 示例\n')
    return [r for r in pipeline._preflight_checks(root) if r[1] == '微信图片格式']


@pytest.mark.parametrize('body', [
    '![截图](素材/screenshot.webp)',
    '[![视频封面](素材/poster.avif)](素材/video.mp4)',
    '<img src="素材/picture.heic">',
])
def test_unsupported_format_fails_in_actual_preflight(tmp_path, body):
    rows = result(tmp_path, body)
    assert rows and rows[0][0] == 'fail'
    assert not (tmp_path / '定稿.html').exists()
    assert (tmp_path / '定稿.md').read_text() == body


@pytest.mark.parametrize('body', ['![图片](素材/p.png)', '![动画](素材/p.gif)', '普通正文。', ''])
def test_allowed_or_no_image_keeps_format_check_clear(tmp_path, body):
    assert all(row[0] == 'ok' for row in result(tmp_path, body))


def test_format_check_uses_same_consumer_and_fails_closed(tmp_path, monkeypatch):
    import release_to_draft
    monkeypatch.setattr(release_to_draft, '_unsupported_local_images', lambda _: ['fixture.format'])
    assert result(tmp_path, '![图](素材/p.png)')[0][0] == 'fail'
    def broken(_):
        raise ValueError('bad consumer')
    monkeypatch.setattr(release_to_draft, '_unsupported_local_images', broken)
    assert '未完成' in result(tmp_path, '正文')[0][2]
