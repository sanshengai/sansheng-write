"""Exercise the actual upload preparation and outgoing multipart animation bytes."""
import io
from pathlib import Path

import pytest
from PIL import Image

from scripts import wechat_api as W


def animation(path: Path):
    frames = []
    for color in ('#124d35', '#e6c668', '#496bb0', '#ac5981'):
        frame = Image.new('RGB', (240, 144), color)
        frames.append(frame)
    frames[0].save(path, 'GIF', save_all=True, append_images=frames[1:],
                   duration=[120, 240, 360, 480], loop=2, disposal=2)
    return path.read_bytes()


def metadata(data):
    with Image.open(io.BytesIO(data)) as img:
        durations = []
        colors = []
        for i in range(img.n_frames):
            img.seek(i)
            durations.append(img.info.get('duration', 0))
            colors.append(img.convert('RGB').getpixel((40, 40)))
        return img.format, img.n_frames, durations, img.info.get('loop'), colors


def test_small_gif_is_sent_unchanged_with_gif_mime(tmp_path, monkeypatch):
    path = tmp_path/'motion.gif'
    original = animation(path)
    sent = {}
    def post(url, field, name, ctype, data, step):
        sent.update(name=name, ctype=ctype, data=data, url=url, step=step)
        return {'url': 'https://media.example.test/synthetic', 'media_id': 'synthetic-gif'}
    monkeypatch.setattr(W, 'post_file', post)
    W.upload_body_image(path, 'synthetic-token')
    assert sent['ctype'] == 'image/gif'
    assert 'material/add_material' in sent['url'] and '&type=image' in sent['url']
    assert sent['data'] == original
    assert metadata(sent['data'])[:4] == ('GIF', 4, [120, 240, 360, 480], 2)


def test_over_budget_gif_compresses_without_changing_sequence_timing_or_loop(tmp_path, monkeypatch):
    path = tmp_path/'motion.gif'
    original = animation(path)
    # Legal trailing padding forces the real oversize branch without a large test fixture.
    path.write_bytes(original + b'\0' * 10000)
    monkeypatch.setattr(W, 'BODY_GIF_MAX_BYTES', 9000)
    sent = {}
    def post(url, field, name, ctype, data, step):
        sent.update(name=name, ctype=ctype, data=data)
        return {'url': 'https://media.example.test/synthetic', 'media_id': 'synthetic-gif'}
    monkeypatch.setattr(W, 'post_file', post)
    out = W.upload_body_image(path, 'synthetic-token')
    assert sent['ctype'] == 'image/gif' and sent['name'].endswith('.gif')
    assert len(sent['data']) <= W.BODY_GIF_MAX_BYTES
    assert metadata(sent['data']) == metadata(original)
    assert '保留 4 帧' in out['note']


def test_uncompressible_animation_is_rejected_before_upload(tmp_path, monkeypatch):
    path = tmp_path/'motion.gif'
    animation(path)
    monkeypatch.setattr(W, 'BODY_GIF_MAX_BYTES', 1)
    monkeypatch.setattr(W, 'post_file', lambda *args: pytest.fail('must not upload a static fallback'))
    with pytest.raises(W.WechatError, match='不能转为静态首帧'):
        W.upload_body_image(path, 'synthetic-token')


def test_animated_webp_is_not_silently_flattened(tmp_path):
    path = tmp_path/'motion.webp'
    Image.new('RGB', (24, 24), 'red').save(path, 'WEBP', save_all=True,
        append_images=[Image.new('RGB', (24, 24), 'blue')], duration=120, loop=0)
    with pytest.raises(W.WechatError, match='请先导出 GIF'):
        W._prepare_body_image(path)


def test_static_png_still_uses_original_bytes(tmp_path):
    path = tmp_path/'still.png'
    Image.new('RGB', (32, 20), 'white').save(path)
    assert W._prepare_body_image(path) == ('still.png', 'image/png', path.read_bytes(), '')


def test_small_static_files_do_not_add_a_pillow_dependency(tmp_path, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def no_pillow(name, *args, **kwargs):
        if name == 'PIL' or name.startswith('PIL.'):
            raise ImportError('Synthetic missing optional dependency')
        return original_import(name, *args, **kwargs)
    paths = []
    for suffix in ['png', 'jpg']:
        path = tmp_path / f'still.{suffix}'
        Image.new('RGB', (32, 20), 'white').save(path)
        paths.append(path)
    monkeypatch.setattr(builtins, '__import__', no_pillow)
    for path in paths:
        assert W._prepare_body_image(path)[2] == path.read_bytes()
