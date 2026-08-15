"""visual-qa 超时预算与失败韧性（2026-08-16 审计修复的安全网）。

旧配置的洞：6 张 ÷ DEFAULT_JOBS=3 = 2 波 × 600s = 1200s，而上游
run_visual_qa 对整个复核器进程只给 900s——最坏情形外层先杀、死状是
裸 traceback；且单张 codex 非零退出（一次 429）会让整轮 QA 判失败。
"""
import json
import math
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts import visual_qa, visual_qa_codex  # noqa: E402


STANDARD_ASSETS = 6  # 封面 + Hero + 4 张信息图


def test_timeout_budget_inequality_holds():
    """波数 × 单张预算 + 重试余量 必须小于外层进程预算。

    这组不等式是 DEFAULT_JOBS=6 的存在理由；谁改回 3（或把单张预算加大）
    这里当场红，逼着同步想清楚外层墙。
    """
    waves = math.ceil(STANDARD_ASSETS / visual_qa_codex.DEFAULT_JOBS)
    worst = (
        waves * visual_qa_codex.PER_ASSET_TIMEOUT
        + visual_qa_codex.RETRY_PAUSE
        + visual_qa_codex.RETRY_TIMEOUT
    )
    assert worst < visual_qa.QA_PROCESS_TIMEOUT, (
        f"最坏耗时 {worst}s ≥ 外层预算 {visual_qa.QA_PROCESS_TIMEOUT}s："
        f"jobs={visual_qa_codex.DEFAULT_JOBS} 会让复核器被外层砍掉"
    )


def test_run_visual_qa_reports_timeout_as_structured_error(tmp_path, monkeypatch):
    """外层撞墙必须给结构化报错，不许裸 traceback 抛穿。"""
    import test_visual_qa_contract as tvc

    article = tvc._article(tmp_path)

    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=visual_qa.QA_PROCESS_TIMEOUT)

    monkeypatch.setattr(visual_qa.subprocess, "run", _boom)
    qa, errors = visual_qa.run_visual_qa(
        article, reviewer_command=[sys.executable, "-c", "pass"]
    )
    assert qa is None
    assert errors and "超时" in errors[0]
    assert str(visual_qa.QA_PROCESS_TIMEOUT) in errors[0]


def _asset(tmp_path: Path) -> dict:
    from PIL import Image

    img = tmp_path / "素材" / "cover.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 32), (20, 20, 22)).save(img)
    return {"path": "素材/cover.png", "required_checks": ["text_match"]}


def _fake_answer(cmd: list) -> None:
    answer = Path(cmd[cmd.index("--output-last-message") + 1])
    answer.write_text(
        json.dumps(
            {
                "checks": {"text_match": True},
                "visual_evidence": [{"trait": "看到了", "detail": "ok"}],
                "observed_text": ["标题"],
                "observed_layout": "left",
                "notes": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_review_one_retries_once_on_nonzero_exit(tmp_path, monkeypatch):
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(kwargs.get("timeout"))
        if len(calls) == 1:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="429 rate limit")
        _fake_answer(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(visual_qa_codex.subprocess, "run", _fake_run)
    monkeypatch.setattr(visual_qa_codex.time, "sleep", lambda *_: None)
    result = visual_qa_codex._review_one(
        _asset(tmp_path), article_dir=tmp_path, codex_bin="codex", model="m"
    )
    assert "_error" not in result, result
    # 重试确实发生了，且第二发用的是收紧后的预算
    assert calls == [visual_qa_codex.PER_ASSET_TIMEOUT, visual_qa_codex.RETRY_TIMEOUT]


def test_review_one_fails_after_two_nonzero_exits(tmp_path, monkeypatch):
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(1)
        return types.SimpleNamespace(returncode=7, stdout="", stderr="boom")

    monkeypatch.setattr(visual_qa_codex.subprocess, "run", _fake_run)
    monkeypatch.setattr(visual_qa_codex.time, "sleep", lambda *_: None)
    result = visual_qa_codex._review_one(
        _asset(tmp_path), article_dir=tmp_path, codex_bin="codex", model="m"
    )
    assert len(calls) == 2
    assert "_error" in result and "exit=7" in result["_error"]


def test_review_one_does_not_retry_on_timeout(tmp_path, monkeypatch):
    """超时不重试：预算不够，重试只会把外层墙也撞穿。"""
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired(cmd="codex", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(visual_qa_codex.subprocess, "run", _fake_run)
    monkeypatch.setattr(visual_qa_codex.time, "sleep", lambda *_: None)
    result = visual_qa_codex._review_one(
        _asset(tmp_path), article_dir=tmp_path, codex_bin="codex", model="m"
    )
    assert len(calls) == 1
    assert "_error" in result and "超时" in result["_error"]
