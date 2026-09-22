"""定位本机 Baoyu 插件某个 skill 的真实目录。

为什么单独一个模块：插件缓存 `~/.claude/plugins/cache/baoyu-skills/baoyu-skills/<hash>/`
会随升级留下多个版本目录，目录名是 commit hash，没有任何顺序含义。09-22 实证：
在缓存里 `rglob` 后按字典序取最后一个，稳定选中了旧版（`8ae8…` > `1567…`），
旧版没打本机补丁，拉起的 Chrome 就少参数。正确的权威来源是 Claude Code 自己的
`installed_plugins.json`（`installPath` 指向现役版本），四端共享入口的软链也都指向它。

优先级：
1. 显式环境变量（调用方指定）
2. `installed_plugins.json` 里 baoyu-skills 的 `installPath/skills/<name>`
3. 四端共享入口 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`、
   `~/.gemini/config/skills`、`~/Cowork/skills`
4. 缓存目录兜底——只在以上全部缺失时用，且按目录 mtime 取最新，绝不按名字排序
"""

from __future__ import annotations

import json
import os
from pathlib import Path

INSTALLED_PLUGINS = ".claude/plugins/installed_plugins.json"
CACHE_GLOBS = (
    ".claude/plugins/cache/baoyu-skills/**/skills/{name}",
    ".codex/plugins/cache/baoyu-skills/**/skills/{name}",
)
SHARED_ENTRY_DIRS = (
    ".agents/skills",
    ".claude/skills",
    ".codex/skills",
    ".gemini/config/skills",
    "Cowork/skills",
)


def installed_plugin_roots(home: Path | None = None) -> list[Path]:
    """读 installed_plugins.json，返回所有 baoyu-skills 条目的 installPath（存在的）。"""
    home = home or Path.home()
    manifest = home / INSTALLED_PLUGINS
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("plugins", data) if isinstance(data, dict) else {}
    roots: list[Path] = []
    for key, value in entries.items():
        if not isinstance(key, str) or not key.startswith("baoyu-skills"):
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("installPath") or "").strip()
            if path and Path(path).is_dir():
                roots.append(Path(path))
    return roots


def candidate_skill_dirs(name: str, explicit_env: str | None = None) -> list[Path]:
    """按优先级列出可能的 skill 目录（已去重、已 resolve，只含含 SKILL.md 的）。"""
    ordered: list[Path] = []
    if explicit_env:
        explicit = os.getenv(explicit_env, "").strip()
        if explicit:
            ordered.append(Path(explicit).expanduser())
    home = Path.home()
    for root in installed_plugin_roots(home):
        ordered.append(root / "skills" / name)
    for entry in SHARED_ENTRY_DIRS:
        ordered.append(home / entry / name)
    cached: list[Path] = []
    for pattern in CACHE_GLOBS:
        cached.extend(home.glob(pattern.format(name=name)))
    cached = [p for p in cached if p.is_dir()]
    # 缓存目录名是 hash，无顺序含义；只能按修改时间取最新
    cached.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    ordered.extend(cached)

    seen: set[Path] = set()
    result: list[Path] = []
    for path in ordered:
        if not (path / "SKILL.md").is_file():
            continue
        real = path.resolve()
        if real in seen:
            continue
        seen.add(real)
        result.append(real)
    return result


def find_skill_dir(name: str, explicit_env: str | None = None) -> Path | None:
    dirs = candidate_skill_dirs(name, explicit_env)
    return dirs[0] if dirs else None


def find_skill_script(name: str, script_rel: str, explicit_env: str | None = None) -> Path | None:
    """找某个 skill 的脚本文件；skill 目录找到但脚本缺失时继续看下一候选。"""
    for skill_dir in candidate_skill_dirs(name, explicit_env):
        script = skill_dir / script_rel
        if script.is_file():
            return script
    return None
