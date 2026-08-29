from scripts.generate_article_bgm import (
    STYLE_POOL,
    build_music_prompt,
    read_article_meta_music,
    resolve_vocal_gender,
)


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


def test_shanghai_jazz_soul_uses_its_vintage_room_prompt():
    prompt = build_music_prompt(
        "旧弄堂里的灯光慢慢亮起",
        ["雨巷", "黄铜灯", "夜色"],
        "shanghai_jazz_soul",
        "female",
    )

    assert STYLE_POOL["shanghai_jazz_soul"]["bpm"] == "68"
    assert "classic Shanghai jazz and gentle soul" in prompt
    assert "intimate female voice" in prompt
    assert "softly radiant chorus" in prompt
    assert "feather-light brushed drums" in prompt
    assert "vintage room ambience" in prompt
    assert "beatless" not in prompt
    assert "Avoid: energetic" in prompt


def test_shanghai_jazz_soul_defaults_to_female_but_respects_explicit_gender(tmp_path):
    article_dir = tmp_path / "2-even-article"
    article_dir.mkdir()

    assert resolve_vocal_gender(None, None, article_dir, "shanghai_jazz_soul") == (
        "female",
        "风格默认",
    )
    assert resolve_vocal_gender("male", None, article_dir, "shanghai_jazz_soul") == (
        "male",
        "显式指定",
    )


def test_existing_ambient_styles_remain_beatless_and_drum_free():
    prompt = build_music_prompt("一束微光", ["薄雾"], "ambient_piano", "female")

    assert "beatless and free-flowing" in prompt
    assert "Avoid: energetic" in prompt
    assert "drums" in prompt


# ── 历史引擎遗留 model 值必须被挡掉（32 篇存量 article-meta.yaml 里是 MiniMax 时代的值）──
from scripts.generate_article_bgm import resolve_model, DEFAULT_LYRIA_MODEL


def test_atomic_audio_write_preserves_old_file_on_invalid_payload(tmp_path):
    from scripts.generate_article_bgm import _write_audio_atomically

    output = tmp_path / "theme.mp3"
    output.write_bytes(b"last-good-audio")

    try:
        _write_audio_atomically("not-valid-base64", output)
    except Exception:
        pass
    else:
        raise AssertionError("invalid payload should fail")

    assert output.read_bytes() == b"last-good-audio"
    assert not (tmp_path / "theme.mp3.next").exists()


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
