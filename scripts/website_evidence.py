"""Verify media in their real player elements and current article text."""
import html
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, unquote, urlparse
try:
    from .delivery_snapshot import build_snapshot
except ImportError:
    from delivery_snapshot import build_snapshot


class EntryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.hidden = []
        self.article_text = []
        self.has_article = False
        self.images, self.video, self.audio, self.dynamic_audio, self.text = [], [], [], [], []
        self.has_audio = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (self.hidden[-1] if self.hidden else False) or 'hidden' in attrs or attrs.get('aria-hidden') == 'true' or tag == 'template' or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style',''), re.I))
        if tag == 'article':
            self.has_article = True
        if hidden:
            if tag not in {'img','source','br','hr','meta','link','input','area','base','embed','param','track','wbr'}:
                self.stack.append(tag)
                self.hidden.append(True)
            return
        if tag == 'img' and attrs.get('src'):
            self.images.append(attrs['src'])
        owner = tag if tag in {'video','audio'} else next((t for t in reversed(self.stack) if t in {'video','audio'}), '')
        if tag in {'video','audio','source'} and attrs.get('src') and owner:
            (self.video if owner == 'video' else self.audio).append(attrs['src'])
        if tag == 'audio':
            self.has_audio = True
        if 'song-player' in attrs.get('class','').split() and attrs.get('data-src'):
            self.dynamic_audio.append(attrs['data-src'])
        if tag not in {'img','source','br','hr','meta','link','input','area','base','embed','param','track','wbr'}:
            self.stack.append(tag)
            self.hidden.append(bool(hidden))
    def handle_endtag(self, tag):
        if tag in self.stack:
            end = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:end]
            self.hidden = self.hidden[:end]
    def handle_data(self, data):
        if not (self.hidden[-1] if self.hidden else False) and not any(t in self.stack for t in {'script','style','template'}):
            self.text.append(data)
            if 'article' in self.stack:
                self.article_text.append(data)


def _normalize(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value)).casefold()


def current_text_errors(cwd: Path, parsed: EntryParser) -> list[str]:
    path = cwd / '定稿.md'
    if not path.is_file():
        return ['缺本篇定稿，无法证明正文已同步']
    source = path.read_text(encoding='utf-8')
    source = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', source, flags=re.S)
    source = re.sub(r'<!--.*?-->', '', source, flags=re.S)
    source = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', source)
    source = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', source)
    source = re.sub(r'<[^>]*>', '', source)
    actual = _normalize(''.join(parsed.article_text if parsed.has_article else parsed.text))
    for line in source.splitlines():
        line = re.sub(r'^\s*[-+*]\s+\[[ xX]\]\s*', '', line)
        line = re.sub(r'^\s*(?:\d+[.)]|[-+*])\s+', '', line)
        expected = _normalize(line)
        # Long lines of visible prose/headers/data must be in the actual entry.
        if len(expected) >= 12 and re.search(r'[\u4e00-\u9fff]', expected) and expected not in actual:
            return ['正式入口缺少或仍是旧版正文；须先完成当前内容同步']
    return []


def media_errors(cwd: Path, code: str, site: str, body: str, fetch) -> list[str]:
    snapshot = build_snapshot(cwd)
    parsed = EntryParser()
    parsed.feed(body)
    errors = current_text_errors(cwd, parsed)
    def reachable(url, kind):
        response = fetch(url, 'HEAD')
        if response[0] != 200:
            return False
        # Production fetch includes Content-Type. Injectable readers may omit headers.
        return len(response) < 3 or str(response[2]).lower().startswith(kind + '/')
    names = {Path(unquote(urlparse(u).path)).name: urljoin(site + '/', u) for u in parsed.images}
    for asset in snapshot['assets']:
        if asset['role'] != 'body_image':
            continue
        name = Path(asset['file']).name
        if asset['status'] == 'missing' or name not in names or not reachable(names.get(name, ''), 'image'):
            errors.append(f'正文图片未在正式入口完整呈现：{asset["file"]}')
    if snapshot['video_declaration_missing']:
        errors.append('正文视频缺 _website-media.json')
    for entry in snapshot['videos']:
        src = entry.get('src') or ''
        if not src or src not in parsed.video or not reachable(src, 'video'):
            errors.append(f'视频未在原生播放器入口呈现或不可访问：{src}')
    audio_urls = [urljoin(site + '/', u) for u in parsed.audio + (parsed.dynamic_audio if parsed.has_audio else [])]
    if '_music-manifest.json' in snapshot['receipts']:
        manifest = snapshot['receipts']['_music-manifest.json'].get('value') or {}
        suffix = Path(((manifest.get('theme') or {}).get('playback') or {}).get('path') or 'song.mp3').suffix
        expected = f'{site}/song-assets/{code}/song{suffix}'
        if expected not in audio_urls or not reachable(expected, 'audio'):
            errors.append('主题曲未在本篇正式播放器呈现或不可播放')
    if (cwd / 'dist/podcast/audio.mp3').is_file():
        expected = f'{site}/song-assets/{code}/podcast.mp3'
        if expected not in audio_urls or not reachable(expected, 'audio'):
            errors.append('播客未在本篇正式播放器呈现或不可播放')
    return errors


def deployment_state(stdout: str) -> str:
    match = re.search(r'JOB_STATE\s*=\s*(queued|running|succeeded|failed)', stdout or '', re.I)
    return match[1].lower() if match else ''
