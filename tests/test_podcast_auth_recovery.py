"""登录态失效 → 自动登录成功后必须继续跑，而不是掉进失败分支。

第 89 篇实跑踩到的假失败：自动登录拿到了 38 个 cookie、独立跑 `nlm notebook
list` 也通，流程却打印「连接预检失败」并 return 1，还反过来叫作者去手跑
`nlm login`。根因是登录成功分支写了个裸 `pass`，没有 return/continue，于是
顺着控制流掉进了 else 的失败处理。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class _AuthExpired(Exception):
    def __str__(self) -> str:
        return "Authentication expired; run `nlm login`"


def _article(tmp_path: Path) -> Path:
    art = tmp_path / "90-p"
    (art / "dist" / "podcast").mkdir(parents=True)
    (art / "定稿.md").write_text("# 标题\n\n正文", encoding="utf-8")
    return art


def _stub_common(monkeypatch, art: Path, podcast, prompt: Path):
    """把预检之后的所有外部依赖都掐掉，只留控制流本身可观测。"""
    monkeypatch.setattr(
        podcast, "cfg",
        lambda: {"enabled": True, "focus_prompt": str(prompt)}, raising=False)
    monkeypatch.setattr(
        podcast.distribute, "read_final_title", lambda d: "测试标题", raising=False)
    monkeypatch.setattr(
        podcast.distribute, "channel_dir",
        lambda d, name: d / "dist" / name, raising=False)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    import podcast_episode as podcast

    art = _article(tmp_path)
    prompt = art / "_podcast-prompt.md"
    prompt.write_text("聚焦：测试", encoding="utf-8")

    calls = []

    def fake_run_nlm(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("notebook", "list"):
            raise _AuthExpired()
        # 预检之后立刻中止，避免真的去建 notebook
        raise RuntimeError("__STOPPED_AFTER_PREFLIGHT__")

    monkeypatch.setattr(podcast, "run_nlm", fake_run_nlm)
    # _retry 的退避是 (20, 45) 秒真睡；不掐掉这条测试要跑 65 秒。
    monkeypatch.setattr(podcast.time, "sleep", lambda *_: None, raising=False)
    _stub_common(monkeypatch, art, podcast, prompt)
    return podcast, art, calls


def test_successful_relogin_continues_past_preflight(harness, monkeypatch):
    podcast, art, calls = harness
    monkeypatch.setattr(podcast, "_try_auto_login", lambda: True)

    try:
        code = podcast.cmd_generate(art)
    except RuntimeError as exc:
        assert "__STOPPED_AFTER_PREFLIGHT__" in str(exc)
    else:
        assert code not in (1, 3), (
            f"自动登录成功后不该走失败分支，实际返回 {code}；调用序列 {calls}"
        )

    assert any(a[:2] == ("notebook", "create") for a in calls) or len(calls) > 1, (
        f"登录成功后应继续往下走，实际只调了 {calls}"
    )


def test_failed_relogin_still_returns_manual_login_code(harness, monkeypatch):
    """登录真的失败时，仍要停在人工边界并返回 3。"""
    podcast, art, calls = harness
    monkeypatch.setattr(podcast, "_try_auto_login", lambda: False)

    assert podcast.cmd_generate(art) == 3


def test_non_auth_error_is_not_swallowed_by_login_path(harness, monkeypatch):
    """非认证类的预检失败要走 return 1，不能被登录分支吃掉。"""
    podcast, art, calls = harness

    def boom(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("connection refused")

    monkeypatch.setattr(podcast, "run_nlm", boom)
    monkeypatch.setattr(
        podcast, "_try_auto_login",
        lambda: pytest.fail("非认证错误不该触发自动登录"))

    assert podcast.cmd_generate(art) == 1
