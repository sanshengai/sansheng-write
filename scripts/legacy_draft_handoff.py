"""Read-only export of a verified legacy draft; never calls the uploader."""
import html
import json
import re
from pathlib import Path

from evidence import stable_digest
from release_to_draft import build_expected_draft


def load_existing(root, remote_id, *, local, sha, error):
    """Require a successful legacy receipt and the exact still-present source files."""
    records = []
    values_seen = []
    receipt = None
    for name in ('_publish-receipt.json', '_release-attempt.json'):
        copies = []
        for prefix in ('', '过程记录'):
            path = root / prefix / name
            if path.exists() or path.is_symlink():
                path = local(root, path)
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                except (ValueError, OSError) as exc:
                    raise error('旧公众号记录无法解析；先沿原入口只读恢复') from exc
                if not isinstance(value, dict):
                    raise error('旧公众号记录格式错误')
                copies.append(value)
                values_seen.append(value)
                records.append(dict(id='legacy-' + str(len(records)), path=path.relative_to(root).as_posix(),
                                    format='text', sha256=sha(path)))
        if copies and any(value != copies[0] for value in copies):
            raise error('文章根与过程记录存在冲突的旧公众号记录')
        if name == '_publish-receipt.json' and copies:
            receipt = copies[0]
        for value in copies:
            if value.get('draft_media_id') != remote_id:
                raise error('指定草稿 ID 与旧记录不符')
    if not receipt or receipt.get('schema_version') != 2 or receipt.get('remote_verified') is not True:
        raise error('认领需要已核验的旧公众号回执；仅尝试记录不能认领')
    if receipt.get('scope') != 'wechat-draft' or receipt.get('formal_publish') is not False:
        raise error('旧记录不是公众号草稿')
    for value in values_seen:
        for field in ('cover_media_id', 'publish_ready_digest', 'expected_draft_digest'):
            if not value.get(field) or value[field] != receipt.get(field):
                raise error('旧提交尝试与成功回执的版本或封面身份不符')
    old_manifest = receipt.get('manifest')
    if not isinstance(old_manifest, dict) or not old_manifest.get('files'):
        raise error('旧回执缺源文件封存')
    fingerprint = stable_digest(old_manifest)
    if receipt.get('manifest_digest') != fingerprint or receipt.get('publish_ready_digest') != fingerprint:
        raise error('旧回执封存指纹不符')
    paths = set()
    for row in old_manifest['files']:
        path = local(root, row.get('path', ''))
        if sha(path) != row.get('sha256'):
            raise error('旧草稿对应的源文件已变化；不得按旧版本认领')
        paths.add(path)
    if root / '定稿.html' not in paths:
        raise error('旧回执未绑定定稿 HTML')
    expected, errors = build_expected_draft(root)
    if errors or not expected:
        raise error('原草稿预期内容无效：' + '; '.join(errors))
    if stable_digest(expected) != receipt.get('expected_draft_digest'):
        raise error('当前正文、封面或元数据与旧草稿不符')
    for path in (local(root, 'article-meta.yaml'),):
        records.append(dict(id='legacy-source-' + str(len(records)), path=path.relative_to(root).as_posix(),
                            format='text', sha256=sha(path)))
    images = (receipt.get('remote_readback') or {}).get('image_sources')
    cover = receipt.get('cover_media_id')
    if not isinstance(images, list) or not cover or any(not isinstance(x, str) or not x.startswith('https://') for x in images):
        raise error('旧回执缺已读回的图片或封面身份')
    pattern = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*)(["\'])(.*?)(\2)', re.I | re.S)
    if len(list(pattern.finditer(expected['content']))) != len(images):
        raise error('旧回执图片数量与定稿不符')
    iterator = iter(images)
    body = pattern.sub(lambda m: m[1] + m[2] + html.escape(next(iterator), quote=True) + m[2], expected['content'])
    article = {k: expected[k] for k in ('title', 'author', 'digest', 'need_open_comment', 'only_fans_can_comment')}
    article.update(content=body, thumb_media_id=cover, content_source_url=expected['source_url'])
    return dict(remote_id=remote_id, article=article, records=records)
