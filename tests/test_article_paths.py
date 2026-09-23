from pathlib import Path

from scripts.article_paths import podcast_filename
import pytest

from scripts.podcast_episode import remote_episode_stem, scp_remote


def test_podcast_filename_keeps_the_author_separator():
    assert podcast_filename("资讯 | Grok 4.7发布：对标 Opus 5.0") == (
        "播客 | 资讯 | Grok 4.7发布：对标 Opus 5.0.mp3"
    )


def test_podcast_filename_strips_path_separators_and_ascii_colon():
    assert podcast_filename("a/b:c") == "播客 | abc.mp3"
    assert podcast_filename("   ") == "播客 | 未命名.mp3"


def test_scp_remote_is_unquoted_for_sftp_scp():
    assert scp_remote("root@example", "/var/www/podcast/episodes", "2026-09-23-标题.mp3") == (
        "root@example:/var/www/podcast/episodes/2026-09-23-标题.mp3"
    )


def test_scp_remote_rejects_names_that_need_shell_quoting():
    for bad in ("播客 | 标题.mp3", "a b.mp3", "it's.mp3"):
        with pytest.raises(ValueError):
            scp_remote("root@example", "/var/www/podcast/episodes", bad)


def test_remote_episode_stem_is_safe_for_the_108_title():
    stem = remote_episode_stem("资讯 | Opus 5.5 与 GPT-6 Sol 同夜发布：一个追 Fable，一个砍半价", "2026-09-23")
    assert stem.startswith("2026-09-23-Opus-5.5"), stem  # 分类前缀「资讯 | 」不进远端名
    scp_remote("root@example", "/var/www/podcast/episodes", f"{stem}.mp3")


def test_scp_retries_once_then_succeeds(monkeypatch):
    import scripts.podcast_episode as pe

    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    results = iter([R(1), R(0)])
    monkeypatch.setattr(pe.subprocess, "run", lambda argv: calls.append(argv) or next(results))
    monkeypatch.setattr(pe.time, "sleep", lambda _s: None)
    assert pe._scp_with_retry("scp", Path("a.mp3"), "host:/x/a.mp3") is True
    assert len(calls) == 2


def test_scp_gives_up_after_attempts(monkeypatch):
    import scripts.podcast_episode as pe

    monkeypatch.setattr(pe.subprocess, "run", lambda argv: type("R", (), {"returncode": 1})())
    monkeypatch.setattr(pe.time, "sleep", lambda _s: None)
    assert pe._scp_with_retry("scp", Path("a.mp3"), "host:/x/a.mp3") is False
