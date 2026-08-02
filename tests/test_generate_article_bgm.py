from scripts.generate_article_bgm import read_article_meta_music


def test_music_meta_ignores_inline_comments(tmp_path):
    (tmp_path / "article-meta.yaml").write_text(
        "music:\n"
        "  style: cinematic_vocal # 风格说明\n"
        '  model: "music-2.6-free" # MiniMax 模型\n'
        "  gender: female\n"
        "  song_name: '杯中沉浮' # 歌名\n",
        encoding="utf-8",
    )

    assert read_article_meta_music(tmp_path) == {
        "style": "cinematic_vocal",
        "gender": "female",
        "model": "music-2.6-free",
        "song_name": "杯中沉浮",
    }
