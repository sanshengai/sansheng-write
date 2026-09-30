"""Stop unchanged repeated QA failures before another paid generation call."""
import hashlib
import json
from pathlib import Path
try:
    from .article_paths import process_file
except ImportError:
    from article_paths import process_file


def input_digest(cwd: Path, label: str = '') -> str:
    h = hashlib.sha256()
    plan_path = cwd / 'visual-plan.json'
    if plan_path.is_file():
        if label:
            plan = json.loads(plan_path.read_text())
            item = plan.get(label)
            if label.startswith('infographic-'):
                item = next((x for x in plan.get('infographics') or [] if f"infographic-{x.get('id')}" == label), None)
            h.update(json.dumps(item, ensure_ascii=False, sort_keys=True).encode())
        else:
            h.update(plan_path.read_bytes())
    for p in sorted((cwd / '素材/prompts').rglob('*.md')):
        if not label or p.stem == label or p.stem.startswith(label + '.') or p.stem.startswith(label + '-'):
            h.update(p.relative_to(cwd).as_posix().encode())
            h.update(p.read_bytes())
    meta = cwd / 'article-meta.yaml'
    if meta.is_file():
        h.update(meta.read_bytes())
    return h.hexdigest()


def retry_errors(cwd: Path, rows: list, only=None, *, consume=False) -> list[str]:
    groups = {}
    for row in rows:
        if row.get('kind') == 'qa_verdict' and row.get('label') != '(batch)':
            groups.setdefault(row.get('label'), []).append(row)
    failures = []
    for label, history in groups.items():
        if only and label not in only:
            continue
        seen = set()
        last = []
        for row in reversed(history):
            identity = row.get('output_sha256') or row.get('render_seq')
            if not identity or identity in seen:
                continue
            seen.add(identity)
            last.append(row)
            if len(last) == 2:
                break
        digest = input_digest(cwd, label)
        if len(last) == 2 and all(r.get('outcome') == 'fail' and r.get('input_digest') == digest for r in last):
            checks = last[0].get('failed_checks') or []
            if checks and checks == last[1].get('failed_checks'):
                failures.append({'label':label, 'checks':checks, 'input_digest':digest,
                                 'latest_verdict_count':len(history), 'attempts':[r.get('output_sha256') or r.get('render_seq') for r in last]})
    if not failures:
        return []
    binding = hashlib.sha256(json.dumps(failures, sort_keys=True).encode()).hexdigest()
    diagnostic = {'binding':binding, 'failures':failures,
                  'required_analysis':['输入条件及模板冲突', '图片可见缺陷', '参考图及附件是否齐全', 'QA 是否添加合同外标准'],
                  'note':'诊断后选择修输入、局部编辑、补参考复核或有理由重生成；不会豁免视觉验收。'}
    process_file(cwd, '_visual-retry-diagnostic.json', for_write=True).write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    decision_path = process_file(cwd, '_visual-retry-decision.json', for_write=True)
    try:
        decision = json.loads(decision_path.read_text())
    except (OSError, ValueError):
        decision = {}
    if decision.get('binding') == binding and not decision.get('used') and decision.get('action') in {'regenerate','edit'} and str(decision.get('reason') or '').strip():
        if consume:
            decision['used'] = True
            decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2))
        return []
    return ['相同单图输入连续两轮被同项打回：先完成 _visual-retry-diagnostic.json 的根因分析；修正输入，或写入绑定本次诊断且说明理由的 _visual-retry-decision.json，再重生成。']
