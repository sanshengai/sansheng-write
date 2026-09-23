"""命令级失败留痕（2026-09-23 审计 G6）。

曾有一天 8 类失败都在写观察日志之前就退出了，日志里一条没有。
入口统一包一层 run_observed：非零退出、返回非零、抛异常都要留下 command_exit。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import command_telemetry as ct  # noqa: E402
import contracts  # noqa: E402


@pytest.fixture
def captured(monkeypatch):
    rows = []
    monkeypatch.setattr(contracts, "log_observation",
                        lambda *a, **k: rows.append((a, k)))
    return rows


def test_system_exit_nonzero_is_recorded_with_failure_lines(captured):
    def cmd():
        print("  ❌ 发布前素材门未通过（8/9）：")
        print("普通输出不该被记")
        raise SystemExit(2)

    with pytest.raises(SystemExit):
        ct.run_observed("pipeline.release-check", cmd, article="108-测试")
    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == "pipeline.release-check" and args[1] == "command_exit" and args[2] == "fail"
    assert "exit=2" in args[3] and "素材门" in args[3] and "普通输出" not in args[3]
    assert kwargs["article"] == "108-测试"


def test_nonzero_return_code_is_recorded(captured):
    assert ct.run_observed("distribute", lambda: 2) == 2
    assert captured and "exit=2" in captured[0][0][3]


def test_exception_is_recorded_and_reraised(captured):
    def boom():
        raise RuntimeError("scp 失败")

    with pytest.raises(RuntimeError):
        ct.run_observed("podcast_episode", boom)
    assert "exception:RuntimeError" in captured[0][0][3]


def test_success_writes_nothing(captured):
    assert ct.run_observed("format_layout", lambda: 0) == 0
    with pytest.raises(SystemExit):
        ct.run_observed("format_layout", lambda: (_ for _ in ()).throw(SystemExit(0)))
    assert captured == []


def test_lazy_stage_and_article_are_resolved_at_failure_time(captured):
    state = {"stage": "pipeline", "article": ""}

    def cmd():
        state.update(stage="pipeline.finalize", article="108")
        raise SystemExit(3)

    with pytest.raises(SystemExit):
        ct.run_observed(lambda: state["stage"], cmd, article=lambda: state["article"])
    args, kwargs = captured[0]
    assert args[0] == "pipeline.finalize" and kwargs["article"] == "108"


def test_stdout_is_restored(captured):
    before = sys.stdout
    ct.run_observed("x", lambda: 0)
    assert sys.stdout is before


def test_entry_points_are_wired():
    scripts = ROOT / "scripts"
    for name in ("pipeline.py", "format_layout.py", "podcast_episode.py", "distribute.py"):
        assert "run_observed(" in (scripts / name).read_text(encoding="utf-8"), name
