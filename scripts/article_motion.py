"""Optional article-motion handoff, adoption and assembly binding; static remains default."""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import shutil
import tempfile

try:
    from .stylebook_workflow import digest, sha, _immutable
    from . import wechat_api
except ImportError:
    from stylebook_workflow import digest, sha, _immutable
    import wechat_api

CONTRACT = 'sansheng.article-motion/1'
SELECTION = '素材/article-motion-selection.json'
ROLES = {'gif', 'poster', 'preview', 'review', 'timeline', 'upstream', 'candidate'}
CHECKS = {'motion_value', 'integrity', 'causality', 'composition', 'legibility', 'loop'}


def palette_identity(value):
    """The image compiler spells an omitted default palette as explicit orig."""
    return {'family': 'orig'} if value is None else value


def local(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('动态媒体须使用包内相对路径')
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file() or (root / relative).is_symlink():
        raise ValueError('动态媒体缺失、越界或使用符号链接')
    return path


def animation(path: Path) -> dict:
    from PIL import Image
    with Image.open(path) as image:
        if image.format != 'GIF' or image.n_frames < 2:
            raise ValueError('文章动态媒体必须是真实多帧 GIF')
        result = {'width': image.width, 'height': image.height, 'frames': image.n_frames,
                  'loop': image.info.get('loop'), 'durations_ms': []}
        for i in range(image.n_frames):
            image.seek(i)
            image.load()
            result['durations_ms'].append(image.info.get('duration', 0))
        if not sum(result['durations_ms']):
            raise ValueError('动态媒体缺少有效播放时长')
        return result


def bundle(path: Path) -> dict:
    path = Path(path).resolve()
    value = json.loads(path.read_text())
    if value.get('contract') != CONTRACT or value.get('state') != 'reviewed_pending_user_adoption':
        raise ValueError('缺少生图 Skill 的当前动态交接合同')
    if set(value.get('files', {})) != ROLES:
        raise ValueError('动态交接缺少完整文件清单')
    for item in value['files'].values():
        file = local(path.parent, item['path'])
        if sha(file) != item['sha256'] or file.stat().st_size != item['bytes'] or not item['bytes']:
            raise ValueError('动态交接文件改变或为空')
    if animation(local(path.parent, value['files']['gif']['path'])) != value['animation']:
        raise ValueError('GIF 与交接时序不一致')
    review = json.loads(local(path.parent, value['files']['review']['path']).read_text())
    candidate_file = local(path.parent, value['files']['candidate']['path'])
    candidate = json.loads(candidate_file.read_text())
    if sha(candidate_file) != value.get('candidate_sha256'):
        raise ValueError('动态交接脱离实际渲染候选')
    for role, name in {'gif': 'motion.gif', 'preview': 'motion.mp4', 'timeline': 'timeline.jpg'}.items():
        if candidate.get('files', {}).get(name) != value['files'][role]['sha256']:
            raise ValueError('动态交接媒体不属于已审片候选')
    if (review.get('state') != 'agent-reviewed-candidate'
            or review.get('candidate_sha256') != value['candidate_sha256']
            or review.get('assessment', {}).get('verdict') != 'accept'
            or review['assessment'].get('playback', {}).get('cycles', 0) < 2
            or not review.get('evidence_sha256')):
        raise ValueError('动态交接缺少当前实际审片通过记录')
    checks = review['assessment'].get('checks', {})
    if set(checks) != CHECKS or any(not isinstance(item, dict)
            or item.get('result') not in ({'pass', 'na'} if key == 'legibility' else {'pass'})
            or not item.get('note', '').strip() for key, item in checks.items()):
        raise ValueError('动态交接缺少动作意义、完整性与循环等审片结论')
    return value


def context(cwd: Path):
    return (json.loads((cwd / '素材/render-batch.json').read_text()),
            json.loads((cwd / 'visual-plan.json').read_text()))


def request(cwd: Path, image_id: str, purpose: str) -> dict:
    try:
        from .stylebook_group import verify_group
        from .stylebook_source import current_source
    except ImportError:
        from stylebook_group import verify_group
        from stylebook_source import current_source
    cwd = Path(cwd).resolve()
    if not purpose.strip():
        raise ValueError('须说明这支动态插图为什么值得动、要帮助读者理解什么')
    group = verify_group(cwd)
    batch, plan = context(cwd)
    items = {item['id']: item for item in plan['article_plan']['items']}
    if image_id not in items or image_id == 'cover':
        raise ValueError('动态需求只能来自本篇已选定的正文插图')
    item, chosen = items[image_id], group['assets'][image_id]
    anchor = re.fullmatch(r'「(.+)」(之后|之前)', item['position'], re.S)
    if not anchor:
        raise ValueError('动态插图须有原文确切引用句')
    article = current_source(cwd, batch, plan)
    image = local(cwd, chosen['image'])
    brief = {'version': 1, 'scene': 'wxillus', 'style': chosen['style'],
             'palette': chosen['palette'], 'source': str(article), 'reason': purpose,
             'format': 'article-illustration', 'use_anchor': False,
             'items': [{'id': image_id, 'position': anchor.group(1), 'message': purpose,
                        'visual': item['subject'], 'text': []}]}
    identity = {'contract': 'sansheng.article-motion-request/1', 'state': 'requested', 'id': image_id,
                'article': str(article), 'article_sha256': sha(article), 'image': str(image),
                'static_sha256': sha(image), 'anchor': anchor.group(1), 'purpose': purpose,
                'selection_id': group['selection_id'], 'brief': brief}
    directory = cwd / '素材/motion-requests' / digest(identity)
    _immutable(directory / 'request.json', identity)
    _immutable(directory / 'brief.json', brief)
    return {**identity, 'request': str(directory / 'request.json'), 'brief_path': str(directory / 'brief.json')}


def prepare(cwd: Path, image_id: str, handoff: Path) -> dict:
    try:
        from .stylebook_group import verify_group
    except ImportError:
        from stylebook_group import verify_group
    cwd = Path(cwd).resolve()
    group = verify_group(cwd)
    batch, plan = context(cwd)
    items = {item['id']: item for item in plan['article_plan']['items']}
    if image_id not in items or image_id == 'cover':
        raise ValueError('动态媒体只能替换本篇已计划的正文插图')
    value = bundle(handoff)
    expected = re.fullmatch(r'「(.+)」(之后|之前)', items[image_id]['position'], re.S)
    source = value['source']
    chosen = group['assets'][image_id]
    if (not expected or source['anchor'] != expected.group(1)
            or source['article_sha256'] != batch['source']['sha256']
            or source['static_sha256'] != chosen['image_sha256']
            or source['style'] != chosen['style']
            or palette_identity(source['palette']) != palette_identity(chosen['palette'])):
        raise ValueError('动态媒体与本篇原文、锚点、静态图或画风色板不一致')
    name, mime, data, note = wechat_api._prepare_body_image(local(handoff.resolve().parent, value['files']['gif']['path']))
    if mime != 'image/gif':
        raise ValueError('上传准备把动画变成了静态图')
    with tempfile.TemporaryDirectory(prefix='article-motion-') as temporary:
        stage = Path(temporary)
        # Copy only declared, verified files; a handoff never grants access to sibling files.
        source_root = stage / 'source'
        source_root.mkdir()
        for item in value['files'].values():
            target_file = source_root / item['path']
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local(handoff.resolve().parent, item['path']), target_file)
        shutil.copyfile(handoff, source_root / handoff.name)
        if bundle(source_root / handoff.name) != value:
            raise ValueError('复制动态交接期间输入改变')
        (stage / 'final.gif').write_bytes(data)
        from PIL import Image
        with Image.open(io.BytesIO(data)) as gif:
            gif.convert('RGBA').save(stage / 'poster.png')
        identity = {'schema_version': 1, 'contract': CONTRACT, 'state': 'prepared_pending_user_adoption',
                    'id': image_id, 'source': source, 'plan_sha256': sha(cwd / 'visual-plan.json'),
                    'input': {'path': 'source/' + handoff.name, 'sha256': sha(handoff)},
                    'files': {role: {'path': file, 'sha256': sha(stage / file)}
                              for role, file in {'gif': 'final.gif', 'poster': 'poster.png',
                                                'preview': 'source/' + value['files']['preview']['path']}.items()},
                    'animation': animation(stage / 'final.gif'), 'preparation_note': note,
                    'preparer_sha256': sha(Path(__file__)), 'upload_preparer_sha256': sha(Path(wechat_api.__file__))}
        key = digest(identity)
        target = cwd / '素材/motion-candidates' / key
        if target.exists():
            if json.loads((target / 'prepared.json').read_text()) != identity:
                raise ValueError('已有动态候选损坏，不覆盖')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            (stage / 'prepared.json').write_text(json.dumps(identity, ensure_ascii=False, indent=2) + '\n')
            shutil.copytree(stage, target)
    return {'state': identity['state'], 'candidate': str(target / 'prepared.json'), 'animation': identity['animation']}


def prepared(cwd: Path, path: Path, batch: dict, plan: dict) -> dict:
    path = path.resolve()
    if not path.is_relative_to(cwd / '素材/motion-candidates'):
        raise ValueError('动态候选不属于本篇素材目录')
    value = json.loads(path.read_text())
    if (value.get('contract') != CONTRACT or value.get('state') != 'prepared_pending_user_adoption'
            or path.parent.name != digest(value) or value['source']['article_sha256'] != batch['source']['sha256']
            or value['plan_sha256'] != sha(cwd / 'visual-plan.json')
            or value['preparer_sha256'] != sha(Path(__file__))
            or value['upload_preparer_sha256'] != sha(Path(wechat_api.__file__))):
        raise ValueError('动态候选的原文、计划或准备方法改变，须重新交接')
    bundle_path = local(path.parent, value['input']['path'])
    if sha(bundle_path) != value['input']['sha256']:
        raise ValueError('原始动态交接改变')
    origin = bundle(bundle_path)
    if origin['source'] != value['source']:
        raise ValueError('动态候选脱离原始交接')
    for item in value['files'].values():
        if sha(local(path.parent, item['path'])) != item['sha256']:
            raise ValueError('已准备的动态媒体改变')
    if animation(local(path.parent, value['files']['gif']['path'])) != value['animation']:
        raise ValueError('已准备的动画时序改变')
    items = {item['id']: item for item in plan['article_plan']['items']}
    item = items.get(value['id'])
    if not item or item['position'] not in (f"「{value['source']['anchor']}」之后", f"「{value['source']['anchor']}」之前"):
        raise ValueError('动态媒体插入位置改变')
    return value


def resolve(cwd: Path, batch: dict, plan: dict, *, replacing: frozenset[str] = frozenset()) -> dict:
    cwd = Path(cwd).resolve()
    active = cwd / SELECTION
    if not active.exists():
        return {}
    record = json.loads(active.read_text())
    identity = {k: v for k, v in record.items() if k != 'selection_id'}
    snapshot = cwd / '素材/motion-selections' / f"{digest(identity)}.json"
    if (record.get('selection_id') != digest(identity) or json.loads(snapshot.read_text()) != identity
            or identity.get('contract') != CONTRACT or not identity.get('items')):
        raise ValueError('动态采用记录为空、改变或缺不可变快照')
    selected = {}
    for image_id, item in identity['items'].items():
        approval = item['user_adoption']
        if approval.get('state') != 'adopted' or not approval.get('words', '').strip() or not approval.get('by', '').strip():
            raise ValueError('动态候选尚无作者明确采用记录')
        path = local(cwd, item['candidate'])
        if sha(path) != item['candidate_sha256']:
            raise ValueError('作者采用之后动态候选改变')
        if image_id in replacing:
            # The immutable old adoption remains authenticated; only its obsolete
            # production binding is superseded by an explicitly validated new candidate.
            continue
        value = prepared(cwd, path, batch, plan)
        if value['id'] != image_id:
            raise ValueError('动态采用的插图 ID 不符')
        selected[image_id] = {**value, 'candidate': item['candidate'], 'candidate_sha256': sha(path),
                              'user_adoption': approval,
                              'gif_source': str(local(path.parent, value['files']['gif']['path']).relative_to(cwd)),
                              'poster_source': str(local(path.parent, value['files']['poster']['path']).relative_to(cwd))}
    return selected


def adopt(cwd: Path, candidate: Path, words: str, by: str) -> dict:
    return adopt_many(cwd, [candidate], words, by)


def adopt_many(cwd: Path, candidates: list[Path], words: str, by: str) -> dict:
    cwd = Path(cwd).resolve()
    if not words.strip() or not by.strip() or not candidates:
        raise ValueError('必须提供候选与明确采用的实际授权；Agent 审片不代表采用')
    batch, plan = context(cwd)
    validated = [(path, prepared(cwd, path, batch, plan)) for path in candidates]
    replacing = frozenset(value['id'] for _, value in validated)
    if len(replacing) != len(validated):
        raise ValueError('同一插图 ID 不能重复采用')
    # Validate the old immutable selection and every unaffected item before writing.
    resolve(cwd, batch, plan, replacing=replacing)
    active = cwd / SELECTION
    items = json.loads(active.read_text())['items'] if active.exists() else {}
    for candidate, value in validated:
        items[value['id']] = {'candidate': str(candidate.resolve().relative_to(cwd)), 'candidate_sha256': sha(candidate),
                              'user_adoption': {'state': 'adopted', 'by': by, 'words': words}}
    identity = {'schema_version': 1, 'contract': CONTRACT, 'items': items}
    selection_id = digest(identity)
    _immutable(cwd / '素材/motion-selections' / f'{selection_id}.json', identity)
    record = {**identity, 'selection_id': selection_id}
    active.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    resolve(cwd, batch, plan)
    return record
