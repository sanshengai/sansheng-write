"""Real-Git regression for explicit article archive inputs (no directory staging).

All examples are synthetic and temporary. A rejected input must leave both HEAD
and the existing index alone; unknown files in the same article are not ours.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive_inputs
import pipeline


def git(repo, *args):
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    article = repo / "成品" / "2-示例文章"
    article.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "user.email", "test@example.invalid")
    works = write(repo / "成品/作品库.yaml", json.dumps({"works": [{"seq": 2, "title": "示例文章", "code": "OBS-2"}]}))
    write(article / "定稿.md", "# 示例文章\n\n已经完成的正文。\n")
    write(article / "同目录他人草稿.md", "tracked baseline\n")
    write(article / "素材/旧图.png", "old-image")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    monkeypatch.setattr("profile_config.works_file", lambda: works)
    return repo, article


def commit(case):
    repo, article = case
    return pipeline._commit_archive_outputs(article, repo, "OBS-2")


def committed_paths(repo):
    return set(git(repo, "show", "--name-only", "--pretty=format:", "HEAD").splitlines())


def assert_rejected_unchanged(case):
    repo, _ = case
    head = git(repo, "rev-parse", "HEAD")
    index = git(repo, "diff", "--cached", "--binary")
    sha, errors = commit(case)
    assert sha is None and errors
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "diff", "--cached", "--binary") == index
    return errors


def test_real_git_does_not_collect_same_article_unknown_or_social_files(case):
    repo, article = case
    write(article / "定稿.md", "# 示例文章\n\n本次修改。\n")
    others = ["同目录他人草稿.md", "陌生文件.txt", "dist/x/article.md", "dist/weibo/images/01.png"]
    for name in others:
        write(article / name, "belongs to another task\n")
    git(repo, "add", "--", str(article / "同目录他人草稿.md"))
    staged_before = git(repo, "diff", "--cached", "--binary")
    sha, errors = commit(case)
    assert sha and not errors
    changed = committed_paths(repo)
    assert "成品/2-示例文章/定稿.md" in changed
    assert not any(str((article / name).relative_to(repo)) in changed for name in others)
    assert git(repo, "diff", "--cached", "--binary") == staged_before
    status = git(repo, "status", "--porcelain", "--untracked-files=all")
    assert all(name in status for name in others)


def test_real_git_collects_markdown_html_music_and_website_inputs(case):
    repo, article = case
    write(article / "定稿.md", '# 示例文章\n![图](<素材/带 空格.png>)\n<img src="素材/html.png">\n![远程](https://example.invalid/a.png)\n')
    refs = ["素材/带 空格.png", "素材/html.png", "music/song.mp3", "video/demo.mp4", "video/poster.png", "video/license.txt", "素材/published.png"]
    for name in refs:
        write(article / name, "fixture bytes")
    write(article / "过程记录/_music-manifest.json", json.dumps({"theme": {"playback": {"path": "music/song.mp3"}}}))
    write(article / "过程记录/_publish-receipt.json", json.dumps({"manifest": {"files": [{"path": "素材/published.png"}]}}))
    write(article / "_website-media.json", json.dumps({"entries": [{"path": "video/demo.mp4", "poster": "video/poster.png", "license_file": "video/license.txt"}]}))
    sha, errors = commit(case)
    assert sha and not errors
    changed = committed_paths(repo)
    expected = [*refs, "过程记录/_music-manifest.json", "过程记录/_publish-receipt.json", "_website-media.json"]
    assert all(str((article / name).relative_to(repo)) in changed for name in expected)


@pytest.mark.parametrize("ref", ["../other.png", "%2e%2e/other.png", "/tmp/outside.png"])
def test_escape_reference_rejected_before_real_git_mutation(case, ref):
    _, article = case
    write(article / "定稿.md", f"# 示例文章\n![图]({ref})\n")
    errors = assert_rejected_unchanged(case)
    assert "归档输入" in errors[0]


@pytest.mark.parametrize("target_outside", [False, True])
def test_symlink_reference_rejected_even_when_target_is_inside(case, target_outside):
    repo, article = case
    target = write((repo if target_outside else article) / "target.png", "fixture")
    (article / "素材/link.png").symlink_to(target)
    write(article / "定稿.md", "# 示例文章\n![图](素材/link.png)\n")
    assert_rejected_unchanged(case)


def test_symlink_directory_reference_rejected(case):
    _, article = case
    write(article / "actual/pic.png", "fixture")
    (article / "linked").symlink_to(article / "actual", target_is_directory=True)
    write(article / "定稿.md", "# 示例文章\n![图](linked/pic.png)\n")
    assert_rejected_unchanged(case)


def test_deleted_tracked_input_rejected_without_committing_other_changes(case):
    _, article = case
    write(article / "定稿.md", "# 示例文章\n![图](素材/旧图.png)\n")
    (article / "素材/旧图.png").unlink()
    errors = assert_rejected_unchanged(case)
    assert "删除" in errors[0]


def test_empty_optional_references_do_not_expand_to_article_directory(case):
    repo, article = case
    write(article / "定稿.md", "# 示例文章\n![空]()\n")
    write(article / "_website-media.json", json.dumps({"entries": [{"path": "", "poster": "  ", "license_file": None}]}))
    write(article / "unknown/secret.txt", "never collect")
    selected = archive_inputs.article_inputs(article)
    assert article not in selected
    sha, errors = commit(case)
    assert sha and not errors
    assert "成品/2-示例文章/unknown/secret.txt" not in committed_paths(repo)


def test_empty_manifest_rejected_before_git_mutation(case):
    _, article = case
    write(article / "过程记录/_music-manifest.json", "")
    assert_rejected_unchanged(case)


def test_unchanged_valid_inputs_create_no_empty_commit(case):
    repo, _ = case
    head = git(repo, "rev-parse", "HEAD")
    assert commit(case) == (None, [])
    assert git(repo, "rev-parse", "HEAD") == head


def test_directory_reference_cannot_collect_its_unrelated_descendants(case):
    """A file-looking reference to a directory must never become broad pathspec."""
    _, article = case
    write(article / "定稿.md", "# 示例文章\n![图](素材)\n")
    write(article / "素材/other-session-secret.txt", "not article input")
    assert_rejected_unchanged(case)


def test_nonexistent_glob_reference_cannot_select_unreferenced_files(case):
    _, article = case
    write(article / "定稿.md", "# 示例文章\n![图](素材/*.png)\n")
    write(article / "素材/another-task.png", "not requested")
    assert_rejected_unchanged(case)


def test_existing_reference_with_brackets_is_a_literal_git_path(case):
    repo, article = case
    write(article / "定稿.md", "# 示例文章\n![图](素材/[ab].png)\n")
    write(article / "素材/[ab].png", "literal requested image")
    write(article / "素材/a.png", "other task must remain untracked")
    sha, errors = commit(case)
    assert sha and not errors
    changed = committed_paths(repo)
    assert "成品/2-示例文章/素材/[ab].png" in changed
    assert "成品/2-示例文章/素材/a.png" not in changed


def test_declared_markdown_video_includes_exact_local_bytes(case):
    repo, article = case
    anchor = '[![视频](素材/poster.png)](素材/demo.mp4)'
    write(article / '定稿.md', '# 示例文章\n' + anchor)
    for name in ('poster.png', 'demo.mp4', 'other.mp4'):
        write(article / '素材' / name, 'fixture bytes')
    write(article / '_website-media.json', json.dumps({'entries': [{
        'anchor_kind': 'markdown-video', 'anchor': anchor, 'poster': '素材/poster.png',
        'src': 'https://example.invalid/demo.mp4'}]}))
    sha, errors = commit(case)
    assert sha and not errors
    paths = committed_paths(repo)
    assert '成品/2-示例文章/素材/demo.mp4' in paths
    assert '成品/2-示例文章/素材/other.mp4' not in paths


def test_video_anchor_not_in_manuscript_rejected(case):
    _, article = case
    write(article / '_website-media.json', json.dumps({'entries': [{
        'anchor_kind': 'markdown-video', 'anchor': '[![视频](p.png)](v.mp4)'}]}))
    assert_rejected_unchanged(case)
