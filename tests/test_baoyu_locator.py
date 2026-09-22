"""baoyu_locator：插件目录定位必须以 installed_plugins.json 为准。

背景（2026-09-22）：插件缓存同时留着 `8ae8…`（旧、未打本机补丁）与 `1567…`（现役）两个
版本目录；旧逻辑 `sorted(rglob(...))[-1]` 按字典序选中旧版，拉起的 Chrome 少了参数。
这里的反例专门构造「字典序更大 + mtime 更新」的过期目录，确保它输给 installPath。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import baoyu_locator  # noqa: E402
import distribute  # noqa: E402
import release_to_draft  # noqa: E402


def _mk_skill(root: Path, name: str, script: str = "scripts/weibo-post.ts") -> Path:
    d = root / "skills" / name
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    (d / script).write_text("// script\n", encoding="utf-8")
    return d


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("BAOYU_POST_TO_WECHAT_DIR", raising=False)
    cache = tmp_path / ".claude/plugins/cache/baoyu-skills/baoyu-skills"
    active = cache / "1567581c26ec"
    stale = cache / "8ae8c33a8d7c"          # 字典序更大
    for name in ("baoyu-post-to-weibo", "baoyu-post-to-wechat"):
        _mk_skill(active, name)
        _mk_skill(stale, name)
    # 让过期目录的 mtime 也更新，双重诱饵
    later = time.time() + 3600
    for p in stale.rglob("*"):
        os.utime(p, (later, later))
    os.utime(stale / "skills/baoyu-post-to-weibo", (later, later))
    manifest = tmp_path / ".claude/plugins/installed_plugins.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "version": 2,
        "plugins": {"baoyu-skills@baoyu-skills": [{
            "scope": "user", "installPath": str(active), "version": "1567581c26ec",
        }]},
    }), encoding="utf-8")
    return {"home": tmp_path, "active": active, "stale": stale, "manifest": manifest}


def test_installPath_胜过字典序和mtime都更大的旧缓存(fake_home):
    got = baoyu_locator.find_skill_dir("baoyu-post-to-weibo")
    assert got == (fake_home["active"] / "skills/baoyu-post-to-weibo").resolve()
    # 反例：把 manifest 改指旧目录，结果必须跟着变——证明真的在读 manifest 而不是碰巧
    fake_home["manifest"].write_text(json.dumps({"plugins": {"baoyu-skills@baoyu-skills": [
        {"scope": "user", "installPath": str(fake_home["stale"])}]}}), encoding="utf-8")
    assert baoyu_locator.find_skill_dir("baoyu-post-to-weibo") == (
        fake_home["stale"] / "skills/baoyu-post-to-weibo"
    ).resolve()


def test_没有manifest时按mtime取新而不按名字(fake_home):
    fake_home["manifest"].unlink()
    got = baoyu_locator.find_skill_dir("baoyu-post-to-weibo")
    assert got == (fake_home["stale"] / "skills/baoyu-post-to-weibo").resolve()


def test_共享入口软链优先于缓存兜底(fake_home):
    fake_home["manifest"].unlink()
    entry = fake_home["home"] / ".agents/skills"
    entry.mkdir(parents=True)
    (entry / "baoyu-post-to-weibo").symlink_to(fake_home["active"] / "skills/baoyu-post-to-weibo")
    got = baoyu_locator.find_skill_dir("baoyu-post-to-weibo")
    assert got == (fake_home["active"] / "skills/baoyu-post-to-weibo").resolve()


def test_显式环境变量最优先(fake_home, monkeypatch):
    custom = _mk_skill(fake_home["home"] / "custom", "baoyu-post-to-wechat")
    monkeypatch.setenv("BAOYU_POST_TO_WECHAT_DIR", str(custom))
    assert baoyu_locator.find_skill_dir("baoyu-post-to-wechat", "BAOYU_POST_TO_WECHAT_DIR") == custom.resolve()


def test_脚本缺失时跳到下一候选(fake_home):
    (fake_home["active"] / "skills/baoyu-post-to-weibo/scripts/weibo-post.ts").unlink()
    got = baoyu_locator.find_skill_script("baoyu-post-to-weibo", "scripts/weibo-post.ts")
    assert got == (fake_home["stale"] / "skills/baoyu-post-to-weibo/scripts/weibo-post.ts").resolve()
    assert baoyu_locator.find_skill_script("baoyu-post-to-weibo", "scripts/不存在.ts") is None


def test_distribute微博脚本走现役版本(fake_home):
    got = distribute.resolve_post_script("weibo", {})
    assert got == (fake_home["active"] / "skills/baoyu-post-to-weibo/scripts/weibo-post.ts").resolve()


def test_distribute显式post_script仍优先(fake_home, tmp_path):
    script = tmp_path / "mine.ts"
    script.write_text("//", encoding="utf-8")
    assert distribute.resolve_post_script("weibo", {"post_script": str(script)}) == script
    assert distribute.resolve_post_script("weibo", {"post_script": str(tmp_path / "missing.ts")}) is None


def test_release_to_draft公众号目录走现役版本(fake_home):
    got = release_to_draft._find_skill_dir("baoyu-post-to-wechat", "BAOYU_POST_TO_WECHAT_DIR")
    assert got == (fake_home["active"] / "skills/baoyu-post-to-wechat").resolve()


def test_全部缺失返回None(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert baoyu_locator.find_skill_dir("baoyu-post-to-weibo") is None
    assert distribute.resolve_post_script("weibo", {}) is None
