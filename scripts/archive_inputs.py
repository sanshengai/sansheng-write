"""Explicit website input closure; never stage an entire article directory."""
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .article_paths import process_file
except ImportError:
    from article_paths import process_file


def article_inputs(article: Path) -> list[Path]:
    root = article.resolve()
    selected: set[Path] = set()

    def add(value, *, required=False):
        if not isinstance(value, str) or not value.strip():
            return
        value = value.strip().strip('<>')
        if urlsplit(value).scheme or value.startswith('//'):
            return
        raw = root / unquote(value.split('#', 1)[0].split('?', 1)[0])
        resolved = raw.resolve()
        if not resolved.is_relative_to(root) or any(p.is_symlink() for p in [raw, *raw.parents] if p != root and p.is_relative_to(root)):
            raise ValueError(f'归档输入越界或为符号链接：{value}')
        if resolved.is_dir():
            raise ValueError(f'归档输入必须是文件，不能收集目录：{value}')
        if required and not resolved.is_file():
            raise ValueError(f'归档引用文件缺失或已删除：{value}')
        if resolved != root:
            selected.add(raw)

    for name in ('定稿.md', '定稿.html', 'article-meta.yaml', '.state.json',
                 'visual-plan.json', '_website-media.json', 'dist/podcast/audio.mp3',
                 'dist/podcast/audio.manifest.json', 'dist/podcast/audio.json',
                 '素材/cover.webp', '素材/cover.png', '素材/lead-hero.webp',
                 '素材/lead-hero.png', '素材/hero.webp', '素材/hero.png',
                 '音乐封面.png', '播客封面.png'):
        add(name)
    md = root / '定稿.md'
    text = md.read_text(encoding='utf-8') if md.is_file() else ''
    for ref in re.findall(r'!\[[^\]]*\]\(\s*(<[^>]+>|[^)]+?)\s*(?:"[^"]*")?\s*\)', text):
        add(ref, required=True)
    for ref in re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)', text, re.I):
        add(ref, required=True)
    for name in ('_music-manifest.json', '_publish-receipt.json', '_visual-receipt.json',
                 '_wechat-published-audio-receipt.json', '_wechat-audio-receipt.json'):
        p = process_file(root, name)
        add(str(p.relative_to(root)))
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding='utf-8'))
        if name == '_music-manifest.json':
            add(((data.get('theme') or {}).get('playback') or {}).get('path'), required=True)
        if name == '_publish-receipt.json':
            for entry in (data.get('manifest') or {}).get('files', []):
                add(entry.get('path'), required=True)
    media = root / '_website-media.json'
    if media.is_file():
        for entry in json.loads(media.read_text(encoding='utf-8')).get('entries', []):
            for field in ('poster', 'path', 'license_file'):
                add(entry.get(field), required=True)
            if entry.get('anchor_kind') == 'markdown-video':
                match = re.fullmatch(r'\[!\[[^\]\r\n]*\]\(([^()\r\n]+)\)\]\(([^()\r\n]+)\)', entry.get('anchor', ''))
                if not match or entry['anchor'] not in text:
                    raise ValueError('归档视频缺当前正文中的明确封面链接')
                add(match[1], required=True)
                add(match[2], required=True)
    return sorted(selected)
