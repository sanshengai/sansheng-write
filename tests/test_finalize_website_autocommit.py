"""finalize 官网同步：归档产物自动文件级提交 + 已上线识别（2026-09-23 审计 F5）。

连续三篇首跑都失败于「归档产物未提交」——finalize 自己刚写的作品库，
紧接着又因为没提交而拒绝同步官网。其中一篇的页面其实早被别的会话的发布带上线，
回执却一直是 failed。
"""
from scripts.article_paths import process_file
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(repo), *args],
                         capture_output=True, text=True, check=True)
    return out.stdout


def _registry(records: list[dict]) -> str:
    import yaml
    return yaml.safe_dump({"works": records}, allow_unicode=True, sort_keys=False)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "Cowork"
    data = repo / "成品"
    data.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (data / "作品库.yaml").write_text(_registry([{"seq": 1, "title": "旧文"}]), encoding="utf-8")
    (data / "articles.md").write_text("# 列表\n- 旧文\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    monkeypatch.setattr("profile_config.works_file", lambda: data / "作品库.yaml")
    article = data / "2-新文章"
    (article / "素材").mkdir(parents=True)
    (article / "定稿.md").write_text("# 新文章\n", encoding="utf-8")
    (article / "素材" / "cover.png").write_bytes(b"png")
    (data / "作品库.yaml").write_text(
        _registry([{"seq": 1, "title": "旧文"}, {"seq": 2, "title": "新文章", "code": "OBS-99"}]),
        encoding="utf-8")
    (data / "articles.md").write_text("# 列表\n- 旧文\n- 新文章\n", encoding="utf-8")
    return repo, article


def test_autocommit_takes_only_this_article_files(repo):
    repo_dir, article = repo
    (repo_dir / "别人的草稿.md").write_text("别人的未提交改动\n", encoding="utf-8")
    sha, errors = pipeline._commit_archive_outputs(article, repo_dir, "OBS-99")
    assert not errors and sha
    committed = set(_git(repo_dir, "show", "--name-only", "--pretty=format:", "HEAD").split())
    assert "成品/作品库.yaml" in committed
    assert "成品/articles.md" in committed
    assert "成品/2-新文章/定稿.md" in committed
    assert "成品/2-新文章/素材/cover.png" in committed
    assert "别人的草稿.md" not in committed
    assert "别人的草稿.md" in _git(repo_dir, "status", "--porcelain")


def test_autocommit_refuses_when_registry_has_other_changes(repo):
    repo_dir, article = repo
    registry = repo_dir / "成品" / "作品库.yaml"
    registry.write_text(
        _registry([{"seq": 1, "title": "旧文-被别的会话改了"},
                   {"seq": 2, "title": "新文章", "code": "OBS-99"}]),
        encoding="utf-8")
    head_before = _git(repo_dir, "rev-parse", "HEAD")
    sha, errors = pipeline._commit_archive_outputs(article, repo_dir, "OBS-99")
    assert sha is None and errors and "seq=1" in errors[0]
    assert _git(repo_dir, "rev-parse", "HEAD") == head_before


def test_website_sync_autocommits_then_runs_command(repo, monkeypatch):
    repo_dir, article = repo
    monkeypatch.setattr(pipeline, "brand", lambda: {"publish": {"website_command": "echo {code}",
                                                                 "website_cwd": str(repo_dir)}})
    monkeypatch.setattr(pipeline, "_archived_code", lambda c: "OBS-99")
    monkeypatch.setattr(pipeline, "_resolve_website_command", lambda c: (c, ""))
    ran = []

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    ok = pipeline._run_website_sync(article, "https://mp.weixin.qq.com/s/X",
                                    runner=lambda *a, **k: ran.append(a) or R(),
                                    live_checker=lambda c, code: False)
    assert ok and ran
    receipt = json.loads(process_file(article, "_website-sync-receipt.json").read_text(encoding="utf-8"))
    assert receipt["latest"]["status"] == "done" and receipt["latest"]["auto_commit"]


def test_already_live_skips_publish_command(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "brand", lambda: {"publish": {"website_command": "echo {code}",
                                                                 "website_cwd": str(tmp_path)}})
    monkeypatch.setattr(pipeline, "_archived_code", lambda c: "OBS-37")
    monkeypatch.setattr(pipeline, "_resolve_website_command", lambda c: (c, ""))
    monkeypatch.setattr(pipeline, "_uncommitted_archive_outputs", lambda c, w: [])
    ran = []
    ok = pipeline._run_website_sync(tmp_path, "https://mp.weixin.qq.com/s/X",
                                    runner=lambda *a, **k: ran.append(a),
                                    live_checker=lambda c, code: True)
    assert ok and not ran
    receipt = json.loads(process_file(tmp_path, "_website-sync-receipt.json").read_text(encoding="utf-8"))
    assert receipt["latest"]["reason"] == "already_live"


def test_live_check_is_off_without_site(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "brand", lambda: {"publish": {}})
    assert pipeline._article_already_live(tmp_path, "OBS-37") is False
