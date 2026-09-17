"""主仓镜像（2026-09-18）：worktree 里生产的 mp3/mp4/作者供图被 .gitignore 挡住，
合回主线带不到主仓 文稿成品/；handoff-assets 必须自动镜像过去，且不覆盖不同内容。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from handoff_assets import mirror_deliverables_to_archive_root  # noqa: E402


def _article(root: Path) -> Path:
    art = root / "wt" / "文稿成品" / "12-篇名"
    (art / "素材" / "视频").mkdir(parents=True)
    (art / "素材" / "作者素材").mkdir(parents=True)
    (art / "dist" / "podcast").mkdir(parents=True)
    (art / "歌.mp3").write_bytes(b"song")
    (art / "cover.png").write_bytes(b"png")
    (art / "定稿.md").write_text("# 不镜像 md\n", encoding="utf-8")
    (art / "素材" / "视频" / "a.mp4").write_bytes(b"video")
    (art / "素材" / "作者素材" / "实景-1.jpg").write_bytes(b"jpg")
    (art / "dist" / "podcast" / "audio.mp3").write_bytes(b"podcast")
    return art


def test_mirror_copies_ignored_deliverables_and_is_idempotent(tmp_path):
    art = _article(tmp_path)
    root = tmp_path / "主仓" / "文稿成品"
    target, copied, errors = mirror_deliverables_to_archive_root(art, root)
    assert errors == []
    assert target == root / "12-篇名"
    assert sorted(copied) == sorted([
        "cover.png", "歌.mp3", "素材/视频/a.mp4", "素材/作者素材/实景-1.jpg", "dist/podcast/audio.mp3",
    ])
    assert (target / "素材" / "视频" / "a.mp4").read_bytes() == b"video"
    assert not (target / "定稿.md").exists()  # tracked 文件走合回，不在镜像范围
    # 再跑一次：同哈希全部跳过
    _, copied2, errors2 = mirror_deliverables_to_archive_root(art, root)
    assert copied2 == [] and errors2 == []


def test_mirror_refuses_to_overwrite_different_content(tmp_path):
    art = _article(tmp_path)
    root = tmp_path / "主仓" / "文稿成品"
    (root / "12-篇名").mkdir(parents=True)
    (root / "12-篇名" / "歌.mp3").write_bytes(b"older-different-song")
    _, copied, errors = mirror_deliverables_to_archive_root(art, root)
    assert any("歌.mp3" in e and "未覆盖" in e for e in errors)
    assert (root / "12-篇名" / "歌.mp3").read_bytes() == b"older-different-song"
    assert "cover.png" in copied  # 其余文件照常镜像


def test_mirror_noop_when_article_already_under_root_or_root_unset(tmp_path):
    root = tmp_path / "主仓" / "文稿成品"
    art = root / "12-篇名"
    art.mkdir(parents=True)
    (art / "歌.mp3").write_bytes(b"song")
    assert mirror_deliverables_to_archive_root(art, root) == (None, [], [])
    assert mirror_deliverables_to_archive_root(art, None) == (None, [], [])
