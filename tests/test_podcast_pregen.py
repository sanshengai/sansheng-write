"""播客预生成（audit-P4）：取件短路、链接补写、漂移防护、pregen 闸门。

背景：NotebookLM 生成实测 ~18 分钟，原本卡在 finalize 串行链中段（89 篇它
一失败官网同步晚了 5 小时）。定稿冻结点预生成 + finalize 取件把它移出关键路径。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import distribute  # noqa: E402
import podcast_episode as pe  # noqa: E402


FINAL = (
    "# 标题\n\n正文。\n\n<!-- SANSHENG-VISUAL-START:01 -->图<!-- SANSHENG-VISUAL-END:01 -->\n"
    "<!-- AUDIO-CARD-START -->音乐卡<!-- AUDIO-CARD-END -->\n"
)


def _pregen_article(tmp_path: Path, *, with_url: bool = False) -> Path:
    art = tmp_path / "article"
    art.mkdir()
    (art / "定稿.md").write_text(FINAL, encoding="utf-8")
    stages = {"writing": {"title_final": "标题"}}
    if with_url:
        stages["publish"] = {"wechat_url": "https://mp.weixin.qq.com/s/abc"}
    (art / ".state.json").write_text(
        json.dumps({"stages": stages}, ensure_ascii=False), encoding="utf-8"
    )
    out = distribute.channel_dir(art, "podcast")
    out.mkdir(parents=True)
    (out / "audio.mp3").write_bytes(b"fake-mp3-bytes")
    (out / "audio.json").write_text(json.dumps({
        "title": "深聊 | 标题", "description": "本期摘要",
        "pub_date": "2026-08-16T00:00:00+08:00", "kind": "article",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "shownotes.md").write_text("# 深聊 | 标题\n\n本期摘要\n", encoding="utf-8")
    distribute.set_status(art, "podcast", "drafted",
                          source_digest=distribute._digest(FINAL))
    return art


def _forbid_nlm(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("取件模式不得触碰 NotebookLM")
    monkeypatch.setattr(pe, "run_nlm", _boom)


def test_generate_short_circuits_on_fresh_pregen(tmp_path, monkeypatch):
    art = _pregen_article(tmp_path)
    monkeypatch.setattr(pe, "cfg", lambda: {"enabled": True, "shownotes_max": 800})
    _forbid_nlm(monkeypatch)
    assert pe.cmd_generate(art) == 0


def test_short_circuit_backfills_wechat_url(tmp_path, monkeypatch):
    art = _pregen_article(tmp_path, with_url=True)
    monkeypatch.setattr(pe, "cfg", lambda: {"enabled": True, "shownotes_max": 800})
    _forbid_nlm(monkeypatch)
    assert pe.cmd_generate(art) == 0
    side = json.loads((distribute.channel_dir(art, "podcast") / "audio.json")
                      .read_text(encoding="utf-8"))
    assert "原文：https://mp.weixin.qq.com/s/abc" in side["description"]
    notes = (distribute.channel_dir(art, "podcast") / "shownotes.md").read_text(encoding="utf-8")
    assert "原文：https://mp.weixin.qq.com/s/abc" in notes


def test_hand_edited_shownotes_survive_url_backfill(tmp_path, monkeypatch):
    art = _pregen_article(tmp_path, with_url=True)
    hand = "# 手写标题\n\n作者自己改过的 shownotes\n"
    (distribute.channel_dir(art, "podcast") / "shownotes.md").write_text(
        hand, encoding="utf-8")
    monkeypatch.setattr(pe, "cfg", lambda: {"enabled": True, "shownotes_max": 800})
    _forbid_nlm(monkeypatch)
    assert pe.cmd_generate(art) == 0
    assert (distribute.channel_dir(art, "podcast") / "shownotes.md").read_text(
        encoding="utf-8") == hand


def test_drifted_final_defeats_short_circuit(tmp_path, monkeypatch):
    """预生成后定稿又改过 → 不许拿旧音频交差，必须走完整生成。"""
    art = _pregen_article(tmp_path)
    (art / "定稿.md").write_text(FINAL + "\n新增段落。\n", encoding="utf-8")
    # focus_prompt 未配置 → 完整生成路径会在短路之后、touching nlm 之前
    # 以 rc=2 停下——恰好证明它没有走短路（短路返回 0）。
    monkeypatch.setattr(pe, "cfg", lambda: {"enabled": True})
    _forbid_nlm(monkeypatch)
    assert pe.cmd_generate(art) == 2


def test_pregen_gate_requires_both_markers(tmp_path, monkeypatch):
    from pipeline import cmd_podcast_pregen

    art = tmp_path / "article"
    art.mkdir()
    (art / "定稿.md").write_text("# 标题\n\n还没走视觉链的裸定稿。\n", encoding="utf-8")
    monkeypatch.setattr(distribute, "enabled_channels", lambda: ["podcast"])
    with pytest.raises(SystemExit) as exc:
        cmd_podcast_pregen(art)
    assert exc.value.code == 2


def test_pregen_runs_generate_when_gates_pass(tmp_path, monkeypatch):
    import pipeline

    art = tmp_path / "article"
    art.mkdir()
    (art / "定稿.md").write_text(FINAL, encoding="utf-8")
    monkeypatch.setattr(distribute, "enabled_channels", lambda: ["podcast"])
    called = []
    monkeypatch.setattr(pe, "cmd_generate", lambda cwd: called.append(cwd) or 0)
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_podcast_pregen(art)
    assert exc.value.code == 0
    assert called == [art]


def test_pregen_noop_when_channel_disabled(tmp_path, monkeypatch):
    from pipeline import cmd_podcast_pregen

    art = tmp_path / "article"
    art.mkdir()
    monkeypatch.setattr(distribute, "enabled_channels", lambda: [])
    assert cmd_podcast_pregen(art) is None
