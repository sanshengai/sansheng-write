from scripts.generate_article_bgm import read_article_meta_music


def test_music_meta_ignores_inline_comments(tmp_path):
    (tmp_path / "article-meta.yaml").write_text(
        "music:\n"
        "  style: cinematic_vocal # 风格说明\n"
        '  model: "lyria-3-pro-preview" # Lyria 模型\n'
        "  gender: female\n"
        "  song_name: '杯中沉浮' # 歌名\n",
        encoding="utf-8",
    )

    assert read_article_meta_music(tmp_path) == {
        "style": "cinematic_vocal",
        "gender": "female",
        "model": "lyria-3-pro-preview",
        "song_name": "杯中沉浮",
    }


# ── 历史引擎遗留 model 值必须被挡掉（32 篇存量 article-meta.yaml 里是 MiniMax 时代的值）──
from scripts.generate_article_bgm import resolve_model, DEFAULT_LYRIA_MODEL


def test_legacy_minimax_model_in_meta_is_ignored():
    """存量 meta 里的 music-2.6-free 不得盖过当前引擎，否则会被原样发给 Vertex 报错。"""
    assert resolve_model(None, "music-2.6-free") == DEFAULT_LYRIA_MODEL
    assert resolve_model(None, "music-2.6") == DEFAULT_LYRIA_MODEL
    assert resolve_model(None, "music-1.5") == DEFAULT_LYRIA_MODEL


def test_meta_lyria_model_is_respected():
    """meta 里已是 lyria-* 的则照用（不能一刀切成默认值，否则等于忽略配置）。"""
    assert resolve_model(None, "lyria-3-pro-preview") == "lyria-3-pro-preview"


def test_cli_model_wins_over_meta():
    """--model 显式传入优先级最高，即便 meta 里有合法值。"""
    assert resolve_model("lyria-3-pro-preview", "music-2.6-free") == "lyria-3-pro-preview"


def test_empty_meta_falls_back_to_default():
    assert resolve_model(None, None) == DEFAULT_LYRIA_MODEL
    assert resolve_model("", "") == DEFAULT_LYRIA_MODEL
