"""Final visual evidence from current independent reviews and exact assembly."""
from __future__ import annotations

import json
from pathlib import Path

try:
    from .stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable
    from .stylebook_assembly import verify_assembly
    from .stylebook_group import verify_group
    from .article_paths import process_file, process_rel
except ImportError:
    from stylebook_workflow import WORKFLOW, PRODUCER, digest, sha, _immutable
    from stylebook_assembly import verify_assembly
    from stylebook_group import verify_group
    from article_paths import process_file, process_rel


def manifest(cwd: Path) -> dict:
    cwd = Path(cwd).resolve()
    assembly = verify_assembly(cwd)
    group = verify_group(cwd)
    assets = []
    for image_id, item in sorted(assembly['assets'].items()):
        chosen = group['assets'][image_id]
        production = json.loads((cwd / chosen['production']).read_text())
        raw = json.loads((cwd / production['raw_receipt']).read_text())
        review = json.loads((cwd / chosen['qa_report']).read_text())
        target = cwd / item['output']
        generation = {'producer': PRODUCER, 'backend': raw['backend'],
                      'model': raw.get('actual_model'), 'source_strength': raw['source_strength'],
                      'independent_invocation_verified': raw['independent_invocation_verified']}
        if 'reuse' in raw:
            generation['reuse'] = raw['reuse']
        assets.append({'id': image_id, 'path': item['output'], 'sha256': sha(target),
                       'bytes': target.stat().st_size, 'style': chosen['style'],
                       'palette': chosen['palette'], 'production': chosen['production'],
                       'production_sha256': chosen['production_sha256'],
                       'qa_report': chosen['qa_report'], 'qa_sha256': chosen['qa_report_sha256'],
                       'actual_reviewer': review['actual_reviewer'],
                       'generation': generation})
    result = {'schema_version': 2, 'workflow': WORKFLOW, 'producer': PRODUCER,
              'assembly_id': assembly['assembly_id'],
              'assembly_sha256': sha(cwd / '素材/stylebook-assembly.json'),
              'assembled_sha256': assembly['assembled_sha256'],
              'source_sha256': assembly['source_sha256'],
              'author_content_sha256': assembly['author_content_sha256'],
              'selection_id': group['selection_id'], 'group': group['group'],
              'plan_review': group['plan_review'], 'plan_review_sha256': group['plan_review_sha256'],
              'actual_plan_reviewer': group['actual_plan_reviewer'], 'assets': assets,
              'evidence_adapter_sha256': sha(Path(__file__))}
    # Reject inputs changing between verification and reading their summaries.
    if verify_assembly(cwd) != assembly or verify_group(cwd) != group:
        raise ValueError('汇总视觉证据期间输入改变')
    return result


def build_manifest(cwd: Path) -> tuple[dict, list[str]]:
    try:
        return manifest(cwd), []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {}, [f'画风手册最终视觉证据失败：{exc}']


def request(cwd: Path) -> dict:
    return {'schema_version': 2, 'workflow': WORKFLOW, 'producer': PRODUCER,
            'assessment_scope': 'aggregate_existing_independent_reviews_and_exact_assembly',
            'additional_independent_review': False, 'manifest': manifest(cwd)}


def aggregate(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        wanted = request(cwd)
        request_path = process_file(cwd, '_visual-qa-request.json', for_write=True)
        request_path.write_text(json.dumps(wanted, ensure_ascii=False, indent=2) + '\n')
        result = {**wanted, 'status': 'pass', 'request_sha256': sha(request_path),
                  'assets': wanted['manifest']['assets'], 'findings': [],
                  'reading_preview_verified': False}
        if request(cwd) != wanted:
            raise ValueError('生成汇总期间视觉证据改变')
        _immutable(cwd / '素材/stylebook-qa-aggregates' / f'{digest(result)}.json', result)
        process_file(cwd, '_visual-qa.json', for_write=True).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        validate_qa(cwd, result)
        return result, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f'画风手册视觉验收汇总失败：{exc}']


def validate_qa(cwd: Path, qa: dict) -> dict:
    cwd = Path(cwd).resolve()
    wanted = request(cwd)
    req = process_file(cwd, '_visual-qa-request.json')
    expected = {**wanted, 'status': 'pass', 'request_sha256': sha(req),
                'assets': wanted['manifest']['assets'], 'findings': [],
                'reading_preview_verified': False}
    snapshot = cwd / '素材/stylebook-qa-aggregates' / f'{digest(expected)}.json'
    if json.loads(req.read_text()) != wanted or qa != expected or json.loads(snapshot.read_text()) != expected:
        raise ValueError('视觉汇总或当前独立验收/装配改变，须重新汇总')
    return qa


def qa_errors(cwd: Path, qa: dict) -> list[str]:
    try:
        validate_qa(cwd, qa)
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f'画风手册视觉汇总失效：{exc}']


def seal(cwd: Path) -> tuple[dict | None, list[str]]:
    cwd = Path(cwd).resolve()
    try:
        qa_path = process_file(cwd, '_visual-qa.json')
        qa = validate_qa(cwd, json.loads(qa_path.read_text()))
        identity = {'schema_version': 2, 'workflow': WORKFLOW, 'producer': PRODUCER,
                    'status': 'visual_sealed_pending_reading_review', 'manifest': qa['manifest'],
                    'manifest_digest': digest(qa['manifest']), 'qa_path': process_rel(cwd, '_visual-qa.json'),
                    'qa_sha256': sha(qa_path), 'qa_status': 'pass', 'qa_findings': []}
        seal_id = digest(identity)
        _immutable(cwd / '素材/stylebook-visual-seals' / f'{seal_id}.json', identity)
        record = {**identity, 'seal_id': seal_id}
        process_file(cwd, '_visual-receipt.json', for_write=True).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        verify_seal(cwd)
        return record, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f'画风手册视觉封存失败：{exc}']


def verify_seal(cwd: Path) -> dict:
    cwd = Path(cwd).resolve()
    record = json.loads(process_file(cwd, '_visual-receipt.json').read_text())
    identity = {k: v for k, v in record.items() if k != 'seal_id'}
    if record.get('seal_id') != digest(identity):
        raise ValueError('视觉封存凭证改变')
    snapshot = cwd / '素材/stylebook-visual-seals' / f'{record["seal_id"]}.json'
    if json.loads(snapshot.read_text()) != identity:
        raise ValueError('视觉封存快照改变')
    qa_path = process_file(cwd, '_visual-qa.json')
    qa = validate_qa(cwd, json.loads(qa_path.read_text()))
    expected = {'schema_version': 2, 'workflow': WORKFLOW, 'producer': PRODUCER,
                'status': 'visual_sealed_pending_reading_review', 'manifest': qa['manifest'],
                'manifest_digest': digest(qa['manifest']), 'qa_path': process_rel(cwd, '_visual-qa.json'),
                'qa_sha256': sha(qa_path), 'qa_status': 'pass', 'qa_findings': []}
    if identity != expected:
        raise ValueError('视觉封存对应的当前成品、全文计划或验收改变')
    return record


def verify_receipt(cwd: Path) -> tuple[dict | None, list[str]]:
    try:
        return verify_seal(cwd), []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, [f'画风手册视觉封存失效：{exc}']
