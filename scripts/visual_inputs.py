"""One source for scene options and read-only identity references."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse


def layout_options(item: dict, stage: str) -> dict:
    defaults = {'tag_separator': 'slash'} if stage == 'cover' else {'frame': 'dotted'}
    return {**defaults, **(item.get('layout_options') or {})}


def validate_scene_inputs(plan: dict) -> list[str]:
    errors = []
    for stage, choices in [('cover', {'tag_separator': {'slash', 'space'}}),
                           ('hero', {'frame': {'dotted', 'none'}})]:
        item = plan.get(stage) or {}
        if not isinstance(item, dict):
            continue
        supplied = item.get('layout_options', {})
        if not isinstance(supplied, dict):
            errors.append(f'{stage}.layout_options 必须是对象')
            continue
        for k, v in supplied.items():
            if k not in choices or not isinstance(v, str) or v not in choices[k]:
                errors.append(f'{stage}.layout_options.{k} 无效：{v!r}')
        facts = '\n'.join(str(x) for x in item.get('visual_facts') or [])
        options = {**({'tag_separator': 'slash'} if stage == 'cover' else {'frame': 'dotted'}), **supplied}
        if stage == 'cover' and options['tag_separator'] == 'slash' and re.search(r'(?:禁止|严禁|不用|no |without ).{0,18}(?:斜线|slash)', facts, re.I):
            errors.append('cover 场景禁止斜线但标签合同要求斜线；在 layout_options.tag_separator 明确选择 space，或修正场景要求')
        if stage == 'hero' and options['frame'] == 'dotted' and re.search(r'(?:禁止|严禁|不用|no |without ).{0,35}(?:边框|虚线框|frame|border)', facts, re.I):
            errors.append('hero 场景禁止边框但模板要求圆点框；在 layout_options.frame 明确选择 none，或修正场景要求')
    return errors


def bind_references(cwd: Path, item: dict) -> list[dict]:
    if not isinstance(item, dict):
        raise ValueError("图片规划项必须是对象")
    refs = item.get('reference_images') or []
    if not isinstance(refs, list) or len(refs) > 3:
        raise ValueError('reference_images 必须是最多3项的列表')
    bound = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('参考图声明必须是对象')
        rel = str(ref.get('file') or '')
        path = (cwd / rel).resolve()
        if not rel or not path.is_relative_to(cwd.resolve()) or not path.is_file():
            raise ValueError('参考图缺失或越过文章目录')
        source = str(ref.get('source_url') or '')
        if urlparse(source).scheme != 'https' or not urlparse(source).netloc:
            raise ValueError('参考图必须有真实 HTTPS source_url')
        purpose = str(ref.get('purpose') or '').strip()
        if not purpose:
            raise ValueError('参考图必须声明比较用途 purpose')
        from PIL import Image
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError) as exc:
            raise ValueError('参考图不是可读取的图片') from exc
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        declared = ref.get('sha256')
        if declared and declared != digest:
            raise ValueError('参考图 SHA256 已变化，须核对后更新计划')
        bound.append({'file': path.relative_to(cwd.resolve()).as_posix(), 'sha256': digest,
                      'source_url': source, 'purpose': purpose})
    return bound


def reference_paths(article_dir: Path, asset: dict) -> list[Path]:
    """Adapters also verify bytes immediately before reading references."""
    refs = asset.get('reference_images') or []
    bound = bind_references(article_dir, {'reference_images': refs})
    if any(not r.get('sha256') for r in refs):
        raise ValueError('QA 参考图必须绑定 SHA256')
    return [(article_dir / r['file']).resolve() for r in bound]
