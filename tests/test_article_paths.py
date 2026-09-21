from scripts.article_paths import podcast_filename
from scripts.podcast_episode import scp_remote


def test_podcast_filename_keeps_the_author_separator():
    assert podcast_filename("资讯 | Grok 4.7发布：对标 Opus 5.0") == (
        "播客 | 资讯 | Grok 4.7发布：对标 Opus 5.0.mp3"
    )


def test_podcast_filename_strips_path_separators_and_ascii_colon():
    assert podcast_filename("a/b:c") == "播客 | abc.mp3"
    assert podcast_filename("   ") == "播客 | 未命名.mp3"


def test_scp_remote_quotes_pipe_and_spaces():
    assert scp_remote("root@example", "/var/www/podcast/episodes", "播客 | 标题.mp3") == (
        "root@example:'/var/www/podcast/episodes/播客 | 标题.mp3'"
    )
