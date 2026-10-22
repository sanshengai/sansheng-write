"""Prove title-only changes against real frozen article bytes, retaining original media provenance."""
from pathlib import Path
import hashlib
import re
import yaml


def title_and_body(text):
    try:
        from .assemble_release import strip_machine_assembly
    except ImportError:
        from assemble_release import strip_machine_assembly
    text = strip_machine_assembly(text)
    match = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    if not match:
        heading = re.match(r'\A# ([^\n]+)\n', text)
        if not heading or not text[heading.end():].strip():
            raise ValueError('复用须有非空标题与正文')
        return heading.group(1), ({}, text[heading.end():].strip())
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict) or not isinstance(meta.get('title'), str) or not meta['title'].strip():
        raise ValueError('复用原文缺标题')
    title = meta.pop('title')
    body = text[match.end():]
    body = re.sub(r'\A\s*# ' + re.escape(title) + r'\n', '', body, count=1).strip()
    if not body:
        raise ValueError('不能复用空正文')
    return title, (meta, body)


def verify_title_only(cwd: Path, old_sha: str, new_sha: str):
    if not all(re.fullmatch(r'[a-f0-9]{64}', v or '') for v in (old_sha, new_sha)):
        raise ValueError('原文摘要无效')
    texts = []
    for value in (old_sha, new_sha):
        p = cwd / '素材/stylebook-sources' / f'{value}.md'
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != value:
            raise ValueError('缺少未改变的真实冻结原文')
        texts.append(title_and_body(p.read_text()))
    if texts[0][1] != texts[1][1]:
        raise ValueError('正文或非标题元数据改变，不能沿用仅改标题的媒体证据')
    return {'kind':'verified_title_only', 'original_source_sha256':old_sha,
            'current_source_sha256':new_sha, 'original_title':texts[0][0], 'current_title':texts[1][0],
            'method_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
