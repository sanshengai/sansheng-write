import json
import shutil
from pathlib import Path

import pytest

from scripts import physical_archive as pa
from scripts import pipeline
from scripts import profile_config as pc


def _article(root: Path, name: str = "98-测试文章") -> Path:
    article = root / name
    (article / "dist" / "xhs").mkdir(parents=True)
    (article / "空目录").mkdir()
    (article / ".state.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
    (article / "article-meta.yaml").write_text('title: "测试"\n', encoding="utf-8")
    (article / "定稿.md").write_text("# 正文\n", encoding="utf-8")
    (article / "dist" / "xhs" / "01.png").write_bytes(b"fake-png")
    return article


def test_archive_article_verifies_then_deletes_source(tmp_path):
    source = _article(tmp_path / "worktree" / "文稿成品")
    archive_root = tmp_path / "permanent" / "文稿成品"
    archive_root.mkdir(parents=True)

    receipt = pa.archive_article(source, archive_root, delete_source=True)

    target = archive_root / source.name
    assert not source.exists()
    assert (target / "定稿.md").read_text(encoding="utf-8") == "# 正文\n"
    assert (target / "空目录").is_dir()
    assert receipt["source_deleted"] is True
    saved = json.loads((target / pa.RECEIPT_FILE).read_text(encoding="utf-8"))
    assert saved["archived_from"] == str(source.resolve())
    assert saved["target"] == str(target.resolve())
    assert saved["source_file_count"] == 4
    assert saved["source_manifest_sha256"] == receipt["source_manifest_sha256"]


def test_existing_target_conflict_aborts_without_overwrite_or_delete(tmp_path):
    source = _article(tmp_path / "worktree" / "文稿成品")
    archive_root = tmp_path / "permanent" / "文稿成品"
    target = archive_root / source.name
    target.mkdir(parents=True)
    conflict = target / "article-meta.yaml"
    conflict.write_text('title: "另一篇"\n', encoding="utf-8")

    with pytest.raises(pa.PhysicalArchiveError, match="哈希冲突"):
        pa.archive_article(source, archive_root, delete_source=True)

    assert source.is_dir()
    assert conflict.read_text(encoding="utf-8") == 'title: "另一篇"\n'
    assert not (target / pa.RECEIPT_FILE).exists()


def test_existing_identical_target_is_idempotent_and_preserves_target_only_files(tmp_path):
    source = _article(tmp_path / "worktree" / "文稿成品")
    archive_root = tmp_path / "permanent" / "文稿成品"
    archive_root.mkdir(parents=True)
    target = archive_root / source.name
    shutil.copytree(source, target)
    (target / "dist" / "xhs" / "01.png").unlink()
    (target / "仅归档端.txt").write_text("保留\n", encoding="utf-8")

    receipt = pa.archive_article(source, archive_root)

    assert source.is_dir()
    assert receipt["placement"] == "merged"
    assert receipt["source_deleted"] is False
    assert (target / "dist" / "xhs" / "01.png").read_bytes() == b"fake-png"
    assert (target / "仅归档端.txt").read_text(encoding="utf-8") == "保留\n"


def test_source_change_during_copy_aborts_before_target_placement(tmp_path, monkeypatch):
    source = _article(tmp_path / "worktree" / "文稿成品")
    archive_root = tmp_path / "permanent" / "文稿成品"
    archive_root.mkdir(parents=True)
    real_copytree = pa.shutil.copytree

    def mutating_copytree(src, dst, **kwargs):
        # shutil.copytree 递归时会再次按模块名找 copytree；先恢复真实函数，
        # 只在顶层复制完成后模拟另一写者改动源文件。
        monkeypatch.setattr(pa.shutil, "copytree", real_copytree)
        result = real_copytree(src, dst, **kwargs)
        (Path(src) / "定稿.md").write_text("复制中被另一写者修改\n", encoding="utf-8")
        return result

    monkeypatch.setattr(pa.shutil, "copytree", mutating_copytree)

    with pytest.raises(pa.PhysicalArchiveError, match="复制期间源目录发生变化"):
        pa.archive_article(source, archive_root, delete_source=True)

    assert source.is_dir()
    assert not (archive_root / source.name).exists()
    assert not list(archive_root.glob("*.physical-archive.lock"))


def test_archive_root_cannot_contain_source(tmp_path):
    source = _article(tmp_path / "文稿成品")

    with pytest.raises(pa.PhysicalArchiveError, match="不能互相包含"):
        pa.archive_article(source, source.parent)


def test_physical_archive_config_requires_external_absolute_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_WRITE_ARCHIVE_DIR", str(tmp_path / "archive"))
    pc._reset_cache_for_tests()
    assert pc.physical_archive_dir() == (tmp_path / "archive").resolve()

    monkeypatch.setenv("SANSHENG_WRITE_ARCHIVE_DIR", "@workspace/文稿成品")
    pc._reset_cache_for_tests()
    with pytest.raises(pc.WorkspaceBindingError, match="不能使用 @workspace"):
        pc.physical_archive_dir()

    monkeypatch.setenv("SANSHENG_WRITE_ARCHIVE_DIR", "relative/archive")
    pc._reset_cache_for_tests()
    with pytest.raises(pc.WorkspaceBindingError, match="绝对路径"):
        pc.physical_archive_dir()


def test_pipeline_refuses_physical_archive_before_registry_verifies(tmp_path, monkeypatch):
    source = _article(tmp_path / "worktree" / "文稿成品")
    archive_root = tmp_path / "permanent" / "文稿成品"
    archive_root.mkdir(parents=True)
    monkeypatch.setattr(pipeline, "load_state", lambda cwd: {"stages": {}})
    monkeypatch.setattr(
        pipeline,
        "verify_stage",
        lambda stage, cwd, state: (False, ["作品库尚未登记"]),
    )
    monkeypatch.setattr(pipeline, "_log_archive_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pa,
        "archive_article",
        lambda *args, **kwargs: pytest.fail("前置验证失败时不得复制文件"),
    )

    assert pipeline.cmd_physical_archive(
        source, archive_root=str(archive_root), delete_source=True
    ) is False
    assert source.is_dir()
