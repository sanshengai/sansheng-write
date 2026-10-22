"""Article stage checks for explicitly selected, fully reviewed Stylebook groups."""
from pathlib import Path

try:
    from .stylebook_evidence import build_manifest
except ImportError:
    from stylebook_evidence import build_manifest


def stage_errors(cwd: Path) -> list[str]:
    cwd = Path(cwd).resolve()
    manifest, errors = build_manifest(cwd)
    if errors:
        return errors
    expected = {asset['path'] for asset in manifest['assets'] if asset['id'] != 'cover'}
    expected.update(asset['poster']['path'] for asset in manifest['assets'] if 'poster' in asset)
    actual = {str(path.relative_to(cwd)) for path in (cwd / '素材').glob('infographic*')
              if path.is_file() and path.suffix.lower() in {'.png', '.gif'}}
    if actual != expected:
        errors.append(f'正文图须恰好对应当前完整计划；缺少={sorted(expected-actual)}，额外={sorted(actual-expected)}')
    return errors


def reading_errors(cwd: Path) -> list[str]:
    try:
        try:
            from .stylebook_reading import verify_reading
        except ImportError:
            from stylebook_reading import verify_reading
        verify_reading(cwd)
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f'画风库整篇阅读凭证缺失或失效：{exc}']
