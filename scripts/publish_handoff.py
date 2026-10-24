#!/usr/bin/env python3
"""Export a neutral, versioned publishing package. No network or publishing here."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from audio_cards import CARD_COPY, locate_theme_audio_record


class HandoffError(ValueError):
    pass


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def local(root, path):
    p = (root / path).resolve()
    if not p.is_relative_to(root) or not p.is_file() or not p.stat().st_size:
        raise HandoffError(f'文件缺失、为空或越界：{path}')
    return p


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible(text):
    p = Visible(); p.feed(text)
    return re.sub(r'\s+', ' ', ''.join(p.parts)).strip()


def export_handoff(article_dir, targets, *, media=None, job_id='article-publish', existing_draft=None):
    """Media declarations name exact anchors; do not infer a location from filenames."""
    root = Path(article_dir).resolve()
    original = local(root, '定稿.html')
    markup = original.read_text(encoding='utf-8')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', job_id):
        raise HandoffError('job_id 必须为稳定英文/数字标识')
    if not isinstance(targets, list) or not targets:
        raise HandoffError('targets 不能为空')
    adoption = None
    if existing_draft:
        if sum(t.get('platform') == 'wechat' for t in targets) != 1:
            raise HandoffError('认领必须指定唯一公众号目标')
        from legacy_draft_handoff import load_existing
        adoption = load_existing(root, existing_draft, local=local, sha=sha, error=HandoffError)
    if not adoption and any(t.get('platform') == 'wechat' for t in targets):
        # Existing submissions belong to the old transaction until explicitly adopted.
        # Empty/corrupt receipts are uncertainty, not permission to create another draft.
        legacy = [root / prefix / name for prefix in ('', '过程记录')
                  for name in ('_release-attempt.json', '_publish-receipt.json')]
        if any(path.exists() or path.is_symlink() for path in legacy):
            raise HandoffError('已有内置公众号提交记录；先沿原入口只读恢复。旧草稿认领尚未验收，禁止导出为新建稿以免重复发送')
    if media is not None and not isinstance(media, list):
        raise HandoffError('media 必须为数组')
    declarations = [dict(x) for x in (media or [])]
    md_path = root/'定稿.md'
    md_text = md_path.read_text(encoding='utf-8') if md_path.is_file() else ''
    for item in declarations:
        if 'markdown_anchor' in item and (not item['markdown_anchor'] or md_text.count(item['markdown_anchor']) != 1):
            raise HandoffError('显式 Markdown 媒体锚点必须唯一匹配原稿')
    if md_path.is_file():
        for anchor in re.findall(r'<!--\s*VIDEO\s*:.*?-->', md_text, re.S):
            if not any(item.get('markdown_anchor', item.get('anchor')) == anchor for item in declarations):
                raise HandoffError('Markdown 视频锚点未交接本地媒体和 HTML 插入位置')
    explicit_roles = {x.get('role') for x in declarations}
    # Existing validated producer manifests remain the source of truth.
    for role in ('theme', 'podcast'):
        anchor = CARD_COPY[role]['placeholder']
        if anchor not in markup or role in explicit_roles:
            continue
        if role == 'theme':
            record, errors = locate_theme_audio_record(root)
            if errors or record is None:
                raise HandoffError('主题曲正式素材未验真：' + '; '.join(errors))
            path = str(record.path)
        else:
            path = 'dist/podcast/audio.mp3'
        declarations.append(dict(id=role, role=role, kind='audio', path=path, anchor=anchor))

    assets, slots = [], []
    ids = set()

    def add_asset(ident, path, kind):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', ident) or ident in ids:
            raise HandoffError(f'素材 ID 非法或重复：{ident}')
        p = local(root, path)
        ids.add(ident)
        assets.append(dict(id=ident, path=p.relative_to(root).as_posix(), kind=kind, sha256=sha(p)))
        return ident

    for item in declarations:
        ident, anchor = item.get('id', ''), item.get('anchor', '')
        if item.get('kind') not in {'audio', 'video'}:
            raise HandoffError('正文插槽只接受音频/视频')
        if not anchor or markup.count(anchor) != 1:
            raise HandoffError(f'插入位置必须唯一匹配：{ident}')
        add_asset(ident, item.get('path', ''), item['kind'])
        token = f'【发布媒体:{ident}】'
        # Comment anchors become visible text, so the editor need not preserve DOM IDs.
        markup = markup.replace(anchor, token)
        slots.append(dict(id=ident, asset_id=ident, document_id='article', role=item.get('role', ident)))
        if adoption:
            # A comment is not an observable editor location. Do not guess its position.
            if visible(anchor) != anchor or any(c in anchor for c in '<>&') or adoption['article']['content'].count(anchor) != 1:
                raise HandoffError('旧草稿媒体锚点必须是唯一可见纯文字；注释锚点需先人工核对迁移')
            slots[-1]['legacy_anchor'] = anchor
            adoption['article']['content'] = adoption['article']['content'].replace(anchor, token)
    if re.search(r'<!--\s*VIDEO\s*:|删除本段文字[^<]*插入|【发布媒体:', markup):
        expected = {f'【发布媒体:{s["id"]}】' for s in slots}
        remainder = markup
        for token in expected:
            remainder = remainder.replace(token, '')
        if re.search(r'<!--\s*VIDEO\s*:|删除本段文字[^<]*插入|【发布媒体:', remainder):
            raise HandoffError('仍有未声明的媒体占位，不能交给发布端猜测')

    # Collect and bind every local HTML image. Rewrite only its path in the derived copy.
    image_refs = []
    pattern = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*)([\"\'])(.*?)(\2)', re.I | re.S)
    for match in pattern.finditer(markup):
        raw = html.unescape(match.group(3))
        parsed = urlsplit(raw)
        if parsed.scheme in {'https', 'http'}:
            continue
        if parsed.scheme or parsed.netloc or parsed.query:
            raise HandoffError(f'不支持的图片引用：{raw}')
        p = local(root, unquote(parsed.path))
        ident = 'image-' + hashlib.sha256(p.relative_to(root).as_posix().encode()).hexdigest()[:12]
        if ident not in ids:
            add_asset(ident, p, 'image')
        image_refs.append((match.group(0), match.group(1), match.group(2), p))
    if (root/'素材/cover.png').is_file():
        add_asset('cover', '素材/cover.png', 'image')

    targets = json.loads(json.dumps(targets))
    for target in targets:
        if not all(target.get(k) for k in ('id', 'platform', 'account', 'content_type', 'endpoint')):
            raise HandoffError('目标必须显式声明平台、账号、内容类型和终点')
        if target['content_type'] != 'article':
            raise HandoffError('此入口导出文章；图文/短帖请先完成对应内容改编')
        target.setdefault('document_id', 'article')
        if target['document_id'] != 'article':
            raise HandoffError('目标文稿必须为本次 article')
        target['asset_ids'] = sorted(ids)
        if 'cover' in ids:
            target.setdefault('cover_asset_id', 'cover')
        if adoption and target['platform'] == 'wechat':
            if target['endpoint'] != 'draft':
                raise HandoffError('旧草稿认领不能升级为发表或群发')
            article = adoption['article']
            for key, source_key in (('title','title'),('author','author'),('digest','digest'),('source_url','content_source_url'),
                                    ('open_comment','need_open_comment'),('fans_only_comment','only_fans_can_comment')):
                if key in target and target[key] != article[source_key]:
                    raise HandoffError('认领目标元数据与旧草稿不符：' + key)
                target[key] = article[source_key]
            target['existing_draft'] = dict(remote_id=existing_draft, expected_document_id='legacy-expected')

    seed = json.dumps(dict(html=markup, assets=assets, targets=targets, adoption=adoption,
                           source_html=sha(original), source_md=sha(md_path) if md_path.is_file() else None),
                      sort_keys=True, ensure_ascii=False)
    revision = hashlib.sha256(seed.encode()).hexdigest()[:16]
    output_dir = root/'过程记录'/'publish'/revision
    for whole, prefix, quote, p in image_refs:
        relative = os.path.relpath(p, output_dir)
        markup = markup.replace(whole, prefix+quote+html.escape(relative, quote=True)+quote)
    text = visible(markup)
    for slot in slots:
        token = f'【发布媒体:{slot["id"]}】'
        if text.count(token) != 1:
            raise HandoffError(f'插入位置不可见或不唯一：{slot["id"]}')
        i = text.index(token)
        slot['context'] = dict(before=text[max(0, i-48):i], after=text[i+len(token):i+len(token)+48])

    documents = [dict(id='source-html', path='定稿.html', format='html', sha256=sha(original))]
    if (root/'定稿.md').is_file():
        documents.append(dict(id='source-md', path='定稿.md', format='markdown', sha256=sha(root/'定稿.md')))
    sources = [d['id'] for d in documents]
    if adoption:
        documents.extend(adoption['records'])
        adoption_json = json.dumps(adoption['article'], ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        documents.append(dict(id='legacy-expected', path=(output_dir/'legacy-expected.json').relative_to(root).as_posix(),
                              format='text', sha256=hashlib.sha256(adoption_json.encode()).hexdigest(),
                              source_document_ids=[d['id'] for d in adoption['records']]))
        sources.append('legacy-expected')
    documents.append(dict(id='article', path=(output_dir/'article.html').relative_to(root).as_posix(),
                          format='html', sha256=hashlib.sha256(markup.encode()).hexdigest(),
                          asset_ids=sorted(ids), source_document_ids=sources))
    manifest = dict(schema_version=1, job_id=job_id, producer='sansheng-write', content_status='final',
                    source_root=str(root), documents=documents, assets=assets, media_slots=slots, targets=targets)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {'article.html': markup, 'publish-manifest.json': json.dumps(manifest, ensure_ascii=False, indent=2)+'\n'}
    if adoption:
        outputs['legacy-expected.json'] = adoption_json
    for name, value in outputs.items():
        out = output_dir/name
        if out.exists() and out.read_text(encoding='utf-8') != value:
            raise HandoffError(f'候选目录中已有不同内容，拒绝覆盖：{out}')
    for name, value in outputs.items():
        (output_dir/name).write_text(value, encoding='utf-8')
    return output_dir/'publish-manifest.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description='导出文章、正式素材和媒体位置，交给独立发布器')
    parser.add_argument('--dir', required=True)
    parser.add_argument('--targets', required=True, help='含 targets 数组的 JSON')
    parser.add_argument('--media', help='含 media 数组的 JSON；视频须明确 anchor 与本地文件')
    parser.add_argument('--job-id', default='article-publish')
    parser.add_argument('--existing-draft', help='显式认领已核验旧草稿的 ID；只导出，不新建')
    args = parser.parse_args(argv)
    try:
        targets = json.loads(Path(args.targets).read_text(encoding='utf-8'))['targets']
        media = json.loads(Path(args.media).read_text(encoding='utf-8'))['media'] if args.media else None
        path = export_handoff(args.dir, targets, media=media, job_id=args.job_id, existing_draft=args.existing_draft)
        print(json.dumps(dict(ok=True, manifest=str(path)), ensure_ascii=False))
        return 0
    except (HandoffError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
