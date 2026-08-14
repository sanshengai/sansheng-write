"""transcribe_audio 纯函数契约（不联网、不起 ffmpeg）。

钉住三件事：
  ① 输出路径推导 -- 默认 `<同名>.转写.md` 落在音频旁（素材/ 里的音频转写稿
     留在 素材/，才能被「素材自动读取」一并读到）；
  ② 端点分流 -- 与 gen_img.py 同一约定：AIza→AI Studio、AQ.→Vertex 项目级；
     断言用字面 URL 而非模块常量，防「拿被测变量当尺子」空转；
  ③ 引擎选择 -- 显式指定时原样透传，不被 auto 探测覆盖。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import transcribe_audio as ta  # noqa: E402


# ---------------------------------------------------------------- 输出路径

def test_output_path_default_stays_next_to_audio(tmp_path):
    audio = tmp_path / "素材" / "录音.m4a"
    out = ta.output_path_for(audio, None)
    assert out == tmp_path / "素材" / "录音.转写.md"


def test_output_path_explicit_out_wins(tmp_path):
    audio = tmp_path / "录音.mp3"
    out = ta.output_path_for(audio, str(tmp_path / "思考.md"))
    assert out == tmp_path / "思考.md"


# ---------------------------------------------------------------- 端点分流

def test_endpoint_aistudio_for_aiza_key():
    url = ta._gemini_endpoint("gemini-test", "AIzaFAKEKEY")
    assert url == ("https://generativelanguage.googleapis.com/v1beta/"
                   "models/gemini-test:generateContent")


def test_endpoint_vertex_project_for_aq_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_VERTEX_PROJECT", "proj-unit-test")
    url = ta._gemini_endpoint("gemini-test", "AQ.FAKEKEY")
    assert url == ("https://aiplatform.googleapis.com/v1/projects/proj-unit-test/"
                   "locations/global/publishers/google/models/gemini-test:generateContent")


def test_endpoint_aq_key_without_project_exits(monkeypatch):
    # env 与 .env 都拿不到项目 ID 时必须报错指路，不许悄悄退回错误端点
    monkeypatch.delenv("GOOGLE_VERTEX_PROJECT", raising=False)
    monkeypatch.setattr(ta.pc, "_load_dotenv", lambda: {})
    ta.pc._cache.pop("dotenv", None)
    with pytest.raises(SystemExit):
        ta._gemini_endpoint("gemini-test", "AQ.FAKEKEY")
    ta.pc._cache.pop("dotenv", None)


# ---------------------------------------------------------------- 引擎与格式

def test_pick_engine_explicit_passthrough():
    assert ta.pick_engine("gemini") == "gemini"
    assert ta.pick_engine("whisper") == "whisper"


def test_audio_exts_cover_phone_recordings():
    # 手机语音备忘录常见格式必须在支持清单里（iOS m4a / 微信 amr）
    assert {".m4a", ".amr", ".mp3", ".wav"} <= ta.AUDIO_EXTS


def test_redact_strips_key_from_url_errors():
    leaked = "https://example.com/x?key=AQ.SECRET123&alt=json"
    assert "SECRET123" not in ta._redact(leaked)
    assert "key=***" in ta._redact(leaked)
