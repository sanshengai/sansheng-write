"""Seal actual browser observations and a host's explicit native reading review."""
from __future__ import annotations

import json
import math
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from .stylebook_evidence import verify_seal
    from .stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable
except ImportError:
    from stylebook_evidence import verify_seal
    from stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable

CHECKS = {'whole_article_read', 'required_text_readable', 'no_clipping', 'consistent_style', 'cover_crops_checked'}
WIDTHS = {390, 430, 900}


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            value = dict(attrs)
            self.paths.append(value.get('data-local-path') or value.get('src') or '')


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('head', 'script', 'style'):
            self.hidden += 1
        if tag in ('p', 'li', 'pre', 'h1', 'h2', 'h3', 'h4', 'td', 'th', 'blockquote'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('head', 'script', 'style'):
            self.hidden = max(0, self.hidden-1)
        if tag in ('p', 'li', 'pre', 'h1', 'h2', 'h3', 'h4', 'td', 'th', 'blockquote'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def check_author_text(cwd: Path, html: str) -> str:
    try:
        import markdown
    except ImportError as exc:
        raise ValueError('阅读文字核对需要 Python Markdown：python3 -m pip install Markdown') from exc
    original = (cwd / '定稿.md').read_text()
    source = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', original, count=1, flags=re.S)
    # baoyu-md recognizes a quoted list directly after its introductory line;
    # Python Markdown needs a quoted blank line. Preserve every source character
    # and only supply that parser separator outside fenced code.
    lines, fence, previous = [], None, ''
    for line in source.splitlines():
        content = re.sub(r'^\s*(?:>\s*)+', '', line)
        marker = re.match(r'^\s*(`{3,}|~{3,})', content)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        quoted_list = re.match(r'^(\s*>\s*)[-+*]\s+', line)
        if (fence is None and quoted_list and re.match(r'^\s*>\s*\S', previous)
                and not re.match(r'^\s*>\s*[-+*]\s+', previous)):
            lines.append('>')
        lines.append(line)
        previous = line
    source = '\n'.join(lines)
    expected, actual = Text(), Text()
    expected.feed(markdown.markdown(source, extensions=['tables', 'fenced_code']))
    actual.feed(html)
    rendered = re.sub(r'\s+', '', ''.join(actual.parts))
    cursor = 0
    chunks = [re.sub(r'\s+', '', p) for p in ''.join(expected.parts).split('\n')]
    for chunk in (p for p in chunks if p):
        index = rendered.find(chunk, cursor)
        if index < 0:
            raise ValueError(f'整篇 HTML 缺失、改写或重排作者文字：{chunk[:48]}')
        cursor = index + len(chunk)
    if not any(chunks):
        raise ValueError('整篇阅读缺作者文字')
    return markdown.__version__


def context(cwd: Path) -> dict:
    sealed = verify_seal(cwd)
    html = cwd / '定稿.html'
    if not html.read_bytes():
        raise ValueError('缺非空整篇 HTML')
    parser = Images()
    html_text = html.read_text()
    parser.feed(html_text)
    markdown_version = check_author_text(cwd, html_text)
    images = []
    for value in parser.paths:
        parsed = urlparse(value)
        if parsed.scheme not in ('', 'file') or not parsed.path:
            raise ValueError('阅读验收要求 HTML 图片具有可核对的本地来源')
        path = (cwd / unquote(parsed.path)).resolve()
        images.append({'path': str(path), 'sha256': sha(path)})
    body = {str((cwd / a['path']).resolve()) for a in sealed['manifest']['assets'] if a['id'] != 'cover'}
    if not body <= {item['path'] for item in images}:
        raise ValueError('整篇 HTML 缺当前计划的正文图')
    return {'visual_seal_id': sealed['seal_id'], 'html_sha256': sha(html), 'images': images,
            'method_sha256': sha(Path(__file__)), 'markdown_parser_version': markdown_version}


def validate_observation(cwd: Path, observation: dict, current: dict) -> dict:
    if (not isinstance(observation, dict) or type(observation.get('schema_version')) is not int
            or observation['schema_version'] != 1 or observation.get('html_sha256') != current['html_sha256']
            or observation.get('source_strength') != 'host_attested_browser_and_native_reading'
            or observation.get('additional_independent_review') is not False):
        raise ValueError('缺当前 HTML 的真实浏览器及宿主阅读记录')
    checks = observation.get('native_checks')
    if not isinstance(checks, dict) or set(checks) != CHECKS or any(v is not True for v in checks.values()):
        raise ValueError('整篇阅读、必要文字、裁切或画风仍有未通过项')
    views = observation.get('views')
    if not isinstance(views, list) or len(views) != len(WIDTHS):
        raise ValueError('须核对 390、430 手机和 900 桌面三个真实视口')
    widths = [v.get('width') for v in views if isinstance(v, dict)]
    if len(widths) != len(views) or any(type(v) is not int for v in widths) or set(widths) != WIDTHS:
        raise ValueError('阅读视口重复、缺失或非法')
    bound = {}
    for view in views:
        if type(view.get('document_width')) is not int or not 0 < view['document_width'] <= view['width']:
            raise ValueError('整篇阅读存在横向溢出')
        images = view.get('images')
        if not isinstance(images, list) or len(images) != len(current['images']):
            raise ValueError('浏览器图片数量与实际 HTML 不同')
        for actual, expected in zip(images, current['images']):
            if (not isinstance(actual, dict) or actual.get('path') != expected['path']
                    or actual.get('sha256') != expected['sha256'] or actual.get('loaded') is not True
                    or type(actual.get('natural_width')) not in (int, float)
                    or not math.isfinite(actual['natural_width']) or actual['natural_width'] <= 0
                    or type(actual.get('display_width')) not in (int, float)
                    or not math.isfinite(actual['display_width'])
                    or not 0 < actual['display_width'] <= view['width']):
                raise ValueError('浏览器有坏图、错图或不可见图片')
        screen = view.get('screenshot')
        if not isinstance(screen, dict):
            raise ValueError('缺实际视口截图')
        path = (cwd / screen['path']).resolve()
        if not path.is_relative_to(cwd) or sha(path) != screen.get('sha256'):
            raise ValueError('实际视口截图路径或字节已改变')
        from PIL import Image
        with Image.open(path) as picture:
            if (type(view.get('viewport_height')) is not int or view['viewport_height'] < 640
                    or type(view.get('document_height')) is not int or view['document_height'] <= 0
                    or picture.format != 'PNG' or picture.width != view['width']
                    or picture.height < max(view['viewport_height'], view['document_height'])):
                raise ValueError('实际视口截图格式或尺寸不同')
            picture.verify()
        bound[str(path)] = sha(path)
    return bound


def accept_reading(cwd: Path, observation_path: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        observation_path = Path(observation_path).resolve()
        before = sha(observation_path)
        current = context(cwd)
        observation = json.loads(observation_path.read_text())
        screenshots = validate_observation(cwd, observation, current)
        record = {'schema_version': 2, 'workflow': WORKFLOW, 'producer': PRODUCER,
                  'status': 'reading_review_passed', 'context': current,
                  'observation_path': str(observation_path), 'observation_sha256': before,
                  'source_strength': observation['source_strength'], 'additional_independent_review': False,
                  'screenshots_sha256': screenshots}
        if sha(observation_path) != before or context(cwd) != current:
            raise ValueError('封存阅读期间输入改变')
        path = cwd / '素材/stylebook-reading-reviews' / f'{digest(record)}.json'
        _immutable(path, record)
        pointer = {'path': str(path.relative_to(cwd)), 'sha256': sha(path)}
        (cwd / '素材/stylebook-reading-review.json').write_text(json.dumps(pointer, ensure_ascii=False, indent=2)+'\n')
        verify_reading(cwd)
        return {**record, 'report_path': str(path)}, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f'画风库整篇阅读验收失败：{exc}']


def verify_reading(cwd: Path) -> dict:
    cwd = Path(cwd).resolve()
    pointer = json.loads((cwd / '素材/stylebook-reading-review.json').read_text())
    path = (cwd / pointer['path']).resolve()
    record = json.loads(path.read_text())
    if (path.parent != cwd / '素材/stylebook-reading-reviews' or path.stem != digest(record)
            or sha(path) != pointer['sha256'] or record.get('status') != 'reading_review_passed'
            or record.get('workflow') != WORKFLOW or record.get('producer') != PRODUCER):
        raise ValueError('整篇阅读凭证已改变或不是正式记录')
    current = context(cwd)
    observation_path = Path(record['observation_path'])
    if current != record['context'] or sha(observation_path) != record['observation_sha256']:
        raise ValueError('整篇 HTML、视觉封存、方法或阅读记录已改变')
    observation = json.loads(observation_path.read_text())
    if (validate_observation(cwd, observation, current) != record['screenshots_sha256']
            or record.get('source_strength') != observation['source_strength']
            or record.get('additional_independent_review') is not False):
        raise ValueError('整篇阅读来源或截图不同')
    return record
