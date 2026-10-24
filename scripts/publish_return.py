"""Consume the external publisher's readback, preserving legacy evidence and IDs."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path

try:
    from .evidence import stable_digest, verify_publish_ready
    from .article_paths import process_file
except ImportError:  # direct CLI invocation
    from evidence import stable_digest, verify_publish_ready
    from article_paths import process_file

EXTERNAL_RECEIPT = '_external-publish-receipt.json'


def atomic_write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent,prefix='.publish-return-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def local_file(root, relative):
    path = (root/relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root) or not path.is_file():
        raise ValueError('回传凭证中的文件必须位于原文章目录内')
    return path


def validate_return(root, receipt):
    root = Path(root).resolve()
    if (receipt.get('schema_version') != 2 or receipt.get('scope') != 'wechat-draft'
            or receipt.get('formal_publish') is not False or receipt.get('remote_verified') is not True
            or not receipt.get('draft_media_id')):
        raise ValueError('不是已核验的公众号草稿回执')
    info = receipt.get('external_publisher',{})
    if info.get('schema_version') != 1 or info.get('platform') != 'wechat' or not info.get('job_key'):
        raise ValueError('缺外部发布任务身份')
    checks = receipt.get('remote_readback',{}).get('checks',{})
    if not checks or not all(v is True for v in checks.values()) or not checks.get('native_media') or not checks.get('layout'):
        raise ValueError('内容、媒体或排版尚未全部核验')
    files = info.get('source_files',[])
    if not isinstance(files,list) or not any(r.get('path')=='定稿.html' for r in files):
        raise ValueError('回传凭证缺原稿文件绑定')
    for row in files:
        p = local_file(root,row['path'])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=row.get('sha256'):
            raise ValueError('回传后源文件已变化：'+row['path'])
    proof = info.get('readback_evidence',{})
    p = local_file(root,proof.get('path',''))
    if hashlib.sha256(p.read_bytes()).hexdigest()!=proof.get('sha256'):
        raise ValueError('官方读回证据丢失或已变化')
    observed = json.loads(p.read_text(encoding='utf-8'))
    if (observed.get('manifest_digest')!=info.get('manifest_digest')
            or observed.get('remote_id')!=receipt['draft_media_id'] or not observed.get('verification_nonce')):
        raise ValueError('官方读回证据与发布任务不符')
    actual = observed.get('article',{})
    if (hashlib.sha256(actual.get('content','').encode()).hexdigest()!=info.get('content_sha256')
            or stable_digest(actual)!=receipt['remote_readback'].get('remote_digest')
            or actual.get('thumb_media_id')!=receipt.get('cover_media_id')):
        raise ValueError('回传内容或封面与官方读回不符')
    native = receipt.get('native_media',{})
    if native.get('manifest_digest')!=info.get('manifest_digest') or native.get('remote_id')!=receipt['draft_media_id']:
        raise ValueError('媒体观察与任务不符')
    review = native.get('layout_review',{})
    if review.get('reviewed') is not True or review.get('content_sha256')!=info['content_sha256'] or not review.get('evidence'):
        raise ValueError('缺当前正文的视觉观察')
    for row in review['evidence']:
        p = Path(row.get('path',''))
        if not p.is_absolute() or not p.is_file() or not p.stat().st_size or hashlib.sha256(p.read_bytes()).hexdigest()!=row.get('sha256'):
            raise ValueError('视觉观察证据丢失或已变化')
    for row in native.get('components',[]):
        if any(row.get(k) is not True for k in ('saved','reopened','loaded','played')):
            raise ValueError('媒体观察尚未完成')
    return receipt


def import_return(root, receipt_path):
    root = Path(root).resolve()
    receipt = validate_return(root,json.loads(Path(receipt_path).read_text(encoding='utf-8')))
    ready, errors = verify_publish_ready(root)
    if errors or not ready or ready['manifest_digest']!=receipt.get('publish_ready_digest'):
        raise ValueError('当前 Write 封存与回传版本不符：'+'; '.join(errors))
    if (receipt.get('manifest') != ready.get('manifest')
            or receipt.get('manifest_digest') != stable_digest(ready['manifest'])):
        raise ValueError('回传的生产端证据与当前 Write 封存不符')
    if __package__:
        from .release_to_draft import build_expected_draft
    else:
        from release_to_draft import build_expected_draft
    expected, errors = build_expected_draft(root)
    if errors or not expected or stable_digest(expected)!=receipt.get('expected_draft_digest'):
        raise ValueError('当前正文或元数据与回传版本不符')
    for prefix in ('', '过程记录'):
        for name in ('_publish-receipt.json','_release-attempt.json',EXTERNAL_RECEIPT):
            old = root/prefix/name
            if old.exists() and json.loads(old.read_text()).get('draft_media_id')!=receipt['draft_media_id']:
                raise ValueError('文章已绑定另一草稿，拒绝覆盖')
    # The old adoption inputs are sealed by hash; preserve them byte for byte.
    destination = process_file(root,EXTERNAL_RECEIPT,for_write=True)
    atomic_write_json(destination,receipt)
    original = process_file(root,'_publish-receipt.json')
    if not original.exists():
        atomic_write_json(process_file(root,'_publish-receipt.json',for_write=True),receipt)
    attempt = process_file(root,'_release-attempt.json')
    if not attempt.exists():
        payload = {k:receipt[k] for k in ('scope','formal_publish','publish_ready_digest','expected_draft_digest','draft_media_id','cover_media_id')}
        payload.update(schema_version=1,created_at=receipt['sealed_at'],method='external-publisher-readback')
        atomic_write_json(process_file(root,'_release-attempt.json',for_write=True),payload)
    return receipt
