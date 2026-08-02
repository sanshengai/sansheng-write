# -*- coding: utf-8 -*-
"""播客生成的人工边界：只允许认证需要人，音频本身仍由脚本生成。"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import podcast_episode as podcast  # noqa: E402


def test_auth_expired_fails_fast_before_creating_notebook(tmp_path, monkeypatch):
    # Unit tests must never launch the real browser-based NotebookLM login flow.
    # This case verifies the explicit unattended/fail-fast branch only.
    monkeypatch.setenv("SANSHENG_NLM_NO_AUTOLOGIN", "1")
    article = tmp_path / "1-test"
    article.mkdir()
    (article / "定稿.md").write_text("# 标题\n\n正文", encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("两位主持人深入讨论。", encoding="utf-8")

    monkeypatch.setattr(
        podcast, "cfg",
        lambda: {"enabled": True, "focus_prompt": str(prompt)},
    )
    monkeypatch.setattr(podcast.distribute, "read_final_title", lambda d: "测试标题")
    calls = []

    def fake_nlm(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("Authentication expired. Run 'nlm login'")

    monkeypatch.setattr(podcast, "run_nlm", fake_nlm)

    assert podcast.cmd_generate(article) == 3
    assert calls == [("notebook", "list", "--json")]
