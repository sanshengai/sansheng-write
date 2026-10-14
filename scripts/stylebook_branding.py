"""Derive a branded final candidate without changing the reviewed base bytes."""
from __future__ import annotations

import copy
import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

try:
    from .stylebook_workflow import digest, sha, _immutable
except ImportError:
    from stylebook_workflow import digest, sha, _immutable


def branded_manifest(manifest: dict, branding: dict) -> dict:
    if not isinstance(branding, dict) or branding.get('version') != 1:
        raise ValueError('缺真实品牌后处理凭证')
    allowed = branding.get('logo_text')
    if not isinstance(allowed, list) or not allowed or any(not isinstance(t, str) or not t.strip() for t in allowed):
        raise ValueError('品牌后处理缺真实 Logo 文字白名单')
    width = branding.get('width_fraction')
    if type(width) not in (int, float) or not math.isfinite(width) or not 0.05 <= width <= 0.25:
        raise ValueError('品牌水印宽度须在 0.05 到 0.25 之间')
    result = copy.deepcopy(manifest)
    note = f'\nFinal production exception to the unbranded raw brief: explicitly requested official publisher watermark ({', '.join(allowed)}) at 35% opacity and {width:.0%} image width in the bottom-right corner. Software logos remain forbidden.'
    for key in ('subject', 'final_subject'):
        if key in result['content']:
            result['content'][key] += note
    if result.setdefault('text', {}).get('mode') == 'none':
        result['text']['mode'] = 'native'
    result['text'].setdefault('items', []).extend([{'role': 'brand', 'text': text} for text in allowed])
    return result


def verify_branding(cwd: Path, record: dict, task: dict) -> dict:
    try:
        from .stylebook_review import production_inputs
    except ImportError:
        from stylebook_review import production_inputs
    branding = record['branding']
    base_path = (cwd / branding['base_production']).resolve()
    if (record.get('production_method') != 'brand_postprocess' or sha(base_path) != branding['base_sha256']
            or str(Path(__file__).resolve()) not in record['dependencies_sha256']):
        raise ValueError('品牌后处理缺基础制作与实际方法绑定')
    base = json.loads(base_path.read_text())
    if 'branding' in base:
        raise ValueError('禁止重复叠加品牌水印')
    checked, _, _ = production_inputs(cwd, base_path)
    if (checked['request_id'] != record['request_id'] or checked['id'] != record['id']
            or set(record['outputs']) != set(checked['outputs'])):
        raise ValueError('品牌后处理与基础制作不一致')
    script = Path(__file__).with_name('add_logo.js').resolve()
    if str(script) not in record['dependencies_sha256']:
        raise ValueError('品牌后处理缺真实 add_logo 方法')
    for key, output in record['outputs'].items():
        row = branding['ledger'].get(key)
        if not isinstance(row, dict) or row.get('sha256') != output['sha256'] or row.get('watermarked') is not True:
            raise ValueError('品牌后处理台账未绑定最终图片或没有实际水印')
    return branded_manifest(checked['manifest'], branding)


def produce_branded(cwd: Path, base_path: Path, *, logo_text: list[str] | None = None, width_fraction: float = 0.12) -> dict:
    try:
        from .stylebook_review import production_inputs
        from .profile_config import profile_dir, bind_workspace, identity
    except ImportError:
        from stylebook_review import production_inputs
        from profile_config import profile_dir, bind_workspace, identity
    cwd, base_path = Path(cwd).resolve(), Path(base_path).resolve()
    bind_workspace(cwd)
    base, task, _ = production_inputs(cwd, base_path)
    if 'branding' in base:
        raise ValueError('候选已带品牌水印，不得重复后处理')
    script = Path(__file__).with_name('add_logo.js').resolve()
    logo_dir = profile_dir() / 'brand'
    logos = [logo_dir / 'logo.png', logo_dir / 'logo-black.png']
    if not all(p.is_file() for p in logos):
        raise ValueError('品牌后处理须提供明暗两版真实 Logo')
    if type(width_fraction) not in (int, float) or not math.isfinite(width_fraction) or not 0.05 <= width_fraction <= 0.25:
        raise ValueError('品牌水印宽度须在 0.05 到 0.25 之间')
    config = identity()
    allowed = logo_text if logo_text is not None else config.get('logo_text_exact')
    if not isinstance(allowed, list) or not allowed or any(not isinstance(t, str) or not t.strip() for t in allowed):
        raise ValueError('须明确实际 Logo 的逐字文本：--logo-text，或 identity.logo_text_exact')
    allowlist = config.get('logo_text_allowlist', [])
    if any(text not in allowlist for text in allowed):
        raise ValueError('实际 Logo 文字须属于品牌配置白名单')
    dependencies = dict(base['dependencies_sha256'])
    for p in [base_path, Path(__file__).resolve(), script, *logos]:
        dependencies[str(p)] = sha(p)
    with tempfile.TemporaryDirectory(prefix='stylebook-brand-', dir=cwd / '素材') as temp:
        folder = Path(temp)
        paths = {}
        for key, rel in base['files'].items():
            p = folder / (key + '.png')
            p.write_bytes((cwd / rel).read_bytes())
            paths[key] = p
        run = subprocess.run(['node', str(script), *map(str, paths.values()), '--logo', str(logo_dir), '--width-fraction', str(width_fraction)], cwd=cwd,
                             capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise ValueError('品牌后处理失败：' + (run.stdout + run.stderr)[-800:])
        ledger = json.loads((folder / '.postprocess-ledger.json').read_text())
        # Composite any alpha introduced by the watermark onto the actual base.
        # Never infer a background color or change the already opaque pixels.
        for key, p in paths.items():
            with Image.open(cwd / base['files'][key]) as src, Image.open(p) as marked:
                if src.convert('RGBA').getchannel('A').getextrema() != (255, 255):
                    raise ValueError('品牌后处理基础图必须不透明')
                Image.alpha_composite(src.convert('RGBA'), marked.convert('RGBA')).convert('RGB').save(p)
            ledger[p.name]['sha256'] = sha(p)
        branding = {'version': 1, 'base_production': str(base_path.relative_to(cwd)),
                    'base_sha256': sha(base_path), 'logo_text': allowed, 'width_fraction': width_fraction, 'ledger': {k: ledger[p.name] for k, p in paths.items()}}
        if any(sha(Path(p)) != value for p, value in dependencies.items()):
            raise ValueError('品牌后处理期间输入或方法改变')
        identity = {k: v for k, v in base.items() if k not in ('production_id', 'files', 'text_layout')}
        # A geometry-refitted base remains independently bound through base_production.
        identity.update(production_method='brand_postprocess', branding=branding,
                        dependencies_sha256=dependencies,
                        manifest=branded_manifest(task['manifest'], branding),
                        outputs={k: {'sha256': sha(p)} for k, p in paths.items()})
        production_id = digest(identity)
        dest = base_path.parent.parent / production_id
        record = {**identity, 'production_id': production_id,
                  'files': {k: str((dest / p.name).relative_to(cwd)) for k, p in paths.items()}}
        for key, p in paths.items():
            target = cwd / record['files'][key]
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and sha(target) != sha(p):
                raise ValueError('已保存品牌候选字节改变，拒绝覆盖')
            if not target.exists():
                target.write_bytes(p.read_bytes())
        _immutable(dest / 'production.json', record)
        production_inputs(cwd, dest / 'production.json')
        return {**record, 'production_path': str((dest / 'production.json').relative_to(cwd))}


def install_ledger(cwd: Path) -> None:
    """Copy genuine postprocess records only after accepted bytes were assembled."""
    try:
        from .stylebook_group import verify_group
        from .stylebook_assembly import verify_assembly
    except ImportError:
        from stylebook_group import verify_group
        from stylebook_assembly import verify_assembly
    cwd = Path(cwd).resolve()
    verify_assembly(cwd)
    group = verify_group(cwd)
    path = cwd / '素材/.postprocess-ledger.json'
    ledger = json.loads(path.read_text()) if path.exists() else {}
    for image_id, selected in group['assets'].items():
        record = json.loads((cwd / selected['production']).read_text())
        row = record.get('branding', {}).get('ledger', {}).get('main')
        target = cwd / ('素材/cover.png' if image_id == 'cover' else f'素材/infographic-{image_id}.png')
        if not row or row.get('watermarked') is not True or row['sha256'] != sha(target):
            raise ValueError('当前整组未完成真实品牌后处理')
        ledger[target.name] = row
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
