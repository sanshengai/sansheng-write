"""Current media handoff; statuses come from files and receipts, never prose."""
import hashlib
import json
import re
from pathlib import Path
try:
    from .article_paths import process_file, resolve_cover
except ImportError:
    from article_paths import process_file, resolve_cover


def file_link(path: Path, label=None) -> str:
    target = str(path.resolve())
    return f"[{label or path.name}](<{target}>)" if ' ' in target else f"[{label or path.name}]({target})"


def build_snapshot(cwd: Path) -> dict:
    cwd = cwd.resolve()
    text = (cwd / '定稿.md').read_text(encoding='utf-8') if (cwd / '定稿.md').is_file() else ''
    assets = []
    def add(role, rel, source='', position=''):
        path = (cwd / rel).resolve()
        valid = path.is_relative_to(cwd) and path.is_file()
        assets.append({'role': role, 'file': rel, 'source': source, 'position': position,
                       'status': 'present_unverified' if valid else 'missing',
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if valid else ''})
    for index, rel in enumerate(re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text)):
        if not rel.startswith(('https://', 'http://')):
            add('body_image', rel.strip('<>'), position=f'正文图片 {index + 1}')
    for role, rel in [('article_cover', '素材/cover.png'), ('hero', '素材/hero.png'),
                      ('theme_cover', str((resolve_cover(cwd, kind='theme') or (cwd / '音乐封面.png')).relative_to(cwd))), ('podcast_cover', str((resolve_cover(cwd, kind='podcast') or (cwd / '播客封面.png')).relative_to(cwd))),
                      ('music_brief', 'MiniMax-主题曲生成单.md')]:
        add(role, rel)
    receipts = {}
    for name in ['_music-manifest.json', '_podcast-manifest.json', '_website-sync-receipt.json', '_handoff-receipt.json']:
        p = process_file(cwd, name)
        if p.is_file():
            try:
                receipts[name] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'value': json.loads(p.read_text())}
            except ValueError:
                receipts[name] = {'status': 'invalid_json'}
    theme = ((receipts.get('_music-manifest.json') or {}).get('value') or {}).get('theme') or {}
    if (theme.get('playback') or {}).get('path'):
        add('theme_audio', theme['playback']['path'], source=theme.get('origin') or {})
    if (cwd / 'dist/podcast/audio.manifest.json').is_file():
        add('podcast_audio', 'dist/podcast/audio.mp3', source='dist/podcast/audio.manifest.json')
    p = cwd / '_website-media.json'
    videos = json.loads(p.read_text()).get('entries', []) if p.is_file() else []
    return {'schema_version': 1, 'assets': assets, 'videos': videos, 'receipts': receipts,
            'body_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'plan': {'assets': [{**a, 'channels': ['wechat', 'website']} for a in assets], 'body': 'news_images' if 'shot-' in text or '作者素材/' in text else 'generated_or_mixed', 'article_cover': 'generate', 'hero': 'generate', 'theme_cover': 'generate', 'podcast_cover': 'generate_if_podcast', 'videos': 'website_media_manifest_required_if_declared'},
            'video_declaration_missing': bool('<!-- VIDEO:' in text and not videos),
            'note': 'present_unverified 只表示存在；发布和视觉验收仍以对应回执为准。'}


def write_snapshot(cwd: Path) -> dict:
    snapshot = build_snapshot(cwd)
    plan_path = process_file(cwd, '_asset-plan.json', for_write=True)
    if not plan_path.is_file():
        plan_path.write_text(json.dumps(snapshot['plan'], ensure_ascii=False, indent=2) + '\n')
    snapshot['plan'] = json.loads(plan_path.read_text())
    for asset in snapshot['assets']:
        editorial = next((a for a in snapshot['plan'].get('assets', []) if a.get('role') == asset['role'] and a.get('file') == asset['file']), {})
        for key in ['source', 'position', 'channels']:
            if editorial.get(key):
                asset[key] = editorial[key]
    process_file(cwd, '_delivery-snapshot.json', for_write=True).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 当前交付状态', '', '文件存在不等于已验收；以下状态来自当前文件和回执。', '']
    website = (snapshot['receipts'].get('_website-sync-receipt.json') or {}).get('value') or {}
    if website:
        lines += [f"官网同步：{website.get('status', 'unknown')}；详情以官网回执为准。", '']
    lines += ['人工项：按公众号 API 支持范围完成原创、赞赏及正式发布；尚未提供的音频/封面见下方缺项。', '']
    for asset in snapshot['assets']:
        path = cwd / asset['file']
        lines.append(f"- {asset['role']}：{file_link(path) if asset['status'] != 'missing' else asset['file']}（{asset['status']}）")
    for entry in snapshot['videos']:
        lines.append(f"- 视频：[{entry.get('credit') or '视频'}]({entry.get('src')})；网站入口验收见官网回执。")
    if snapshot['video_declaration_missing']:
        lines.append('- 待办：正文声明视频，但尚未交付网站媒体清单。')
    (cwd / '交付状态.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return snapshot


def website_input_digest(cwd: Path) -> str:
    """Only source media, never self-generated website receipts or handoff prose."""
    snapshot = build_snapshot(cwd)
    payload = {key: snapshot[key] for key in ['assets', 'videos', 'body_sha256']}
    payload['references'] = []
    plan_path = cwd / 'visual-plan.json'
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        if isinstance(plan, dict):
            for stage in ['cover', 'hero']:
                item = plan.get(stage) or {}
                if isinstance(item, dict):
                    for ref in item.get('reference_images') or []:
                        if isinstance(ref, dict):
                            path = (cwd / str(ref.get('file') or '')).resolve()
                            payload['references'].append({**ref, 'current_sha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.is_relative_to(cwd.resolve()) and path.is_file() else ''})
    payload['audio_provenance'] = {key: value.get('sha256') for key,value in snapshot['receipts'].items() if key in {'_music-manifest.json','_podcast-manifest.json'}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
