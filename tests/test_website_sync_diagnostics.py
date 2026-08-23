"""官网同步失败时必须看得见真正的报错。

第 89 篇实跑：`_run_website_sync` 用 capture_output 跑发布脚本，失败时打印
`(stderr or stdout)[:500]` —— 从**开头**截。而 `git worktree add` 会先刷几百行
`Updating files: NN%`，于是屏幕上永远只有进度条；receipt 里又只存 sha256，
不存输出本身。结果是唯一一份诊断信息被丢掉，为了看到真正那行
（世界史 canonical 门禁失败）多跑了两轮、二十多分钟。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


NOISY = (
    "Preparing worktree (detached HEAD abc1234)\n"
    + "".join(f"Updating files:  {i}% (1{i}00/34933)\n" for i in range(1, 100))
    + "Canonical verified 门禁失败: contract_version_invalid\n"
    "npm 失败，退出码 1\n"
)


def test_tail_keeps_the_real_error_not_the_progress_bar():
    out = pipeline._diagnostic_tail(NOISY)
    assert "Canonical verified 门禁失败" in out
    assert "npm 失败" in out
    assert "Updating files" not in out


def test_tail_prefers_stderr_but_falls_back_to_stdout():
    assert "真错" in pipeline._diagnostic_tail("真错在这", "无关")
    assert "只有它" in pipeline._diagnostic_tail("   ", "只有它")
    assert "没有任何输出" in pipeline._diagnostic_tail("", "  ")


def test_tail_keeps_the_end_when_noise_filter_cannot_help():
    """噪声过滤和「取尾」是两条独立机制，必须分开测。

    上面那条用的是进度行，被过滤器全滤光后只剩 3 行 —— 取头取尾结果相同，
    于是「取尾」根本没被测到（实测：把 kept[-lines:] 改成 kept[:lines]，
    那条测试照样全绿）。这里用**过滤器认不出的**普通构建日志，让方向可观测。
    """
    body = "".join(f"[build] compiling module_{i}.ts\n" for i in range(400))
    body += "ERROR: contract_version_invalid\n"
    out = pipeline._diagnostic_tail(body)
    assert "ERROR: contract_version_invalid" in out
    assert "module_0.ts" not in out


def test_tail_keeps_the_end_of_a_single_huge_line():
    """单行超长时也要留末尾 —— 报错常被追加在一长串上下文之后。"""
    body = "x" * 8000 + " FATAL_MARKER"
    out = pipeline._diagnostic_tail(body)
    assert "FATAL_MARKER" in out


def test_tail_survives_all_noise():
    """全是进度行时不能返回空 —— 空诊断比噪声还糟。"""
    only_noise = "".join(f"Updating files:  {i}%\n" for i in range(1, 50))
    out = pipeline._diagnostic_tail(only_noise)
    assert out.strip()


def _run(tmp_path, monkeypatch, stdout, returncode):
    class R:
        pass

    r = R()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = ""

    monkeypatch.setattr(
        pipeline, "brand",
        lambda: {"publish": {"website_command": "echo {code}",
                             "website_cwd": str(tmp_path)}})
    monkeypatch.setattr(pipeline, "_archived_code", lambda c: "OBS-27")
    monkeypatch.setattr(pipeline, "_resolve_website_command", lambda c: (c, ""))
    monkeypatch.setattr(pipeline, "_uncommitted_archive_outputs", lambda c, w: [])
    return pipeline._run_website_sync(
        tmp_path, "https://mp.weixin.qq.com/s/X",
        runner=lambda *a, **k: r)


def test_failure_prints_the_real_error(tmp_path, monkeypatch, capsys):
    assert _run(tmp_path, monkeypatch, NOISY, 1) is False
    out = capsys.readouterr().out
    assert "Canonical verified 门禁失败" in out, "真报错必须打在屏幕上"
    assert "Updating files" not in out


def test_failure_persists_readable_tail_in_receipt(tmp_path, monkeypatch, capsys):
    _run(tmp_path, monkeypatch, NOISY, 1)
    receipt = json.loads(
        (tmp_path / "_website-sync-receipt.json").read_text(encoding="utf-8"))
    latest = receipt["latest"]
    assert latest["status"] == "failed"
    assert "Canonical verified 门禁失败" in latest.get("tail", ""), (
        "只存 sha256 等于把唯一一份诊断信息扔了 —— 命令是 capture 跑的，"
        "输出不在任何终端里"
    )


def test_success_does_not_bloat_the_receipt(tmp_path, monkeypatch, capsys):
    assert _run(tmp_path, monkeypatch, NOISY, 0) is True
    receipt = json.loads(
        (tmp_path / "_website-sync-receipt.json").read_text(encoding="utf-8"))
    assert receipt["latest"]["status"] == "done"
    assert "tail" not in receipt["latest"]

def _run_capture_kwargs(tmp_path, monkeypatch):
    captured = {}

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(command, **kwargs):
        captured.update(kwargs)
        return R()

    monkeypatch.setattr(
        pipeline, "brand",
        lambda: {"publish": {"website_command": "echo {code}",
                             "website_cwd": str(tmp_path)}})
    monkeypatch.setattr(pipeline, "_archived_code", lambda c: "OBS-27")
    monkeypatch.setattr(pipeline, "_resolve_website_command", lambda c: (c, ""))
    monkeypatch.setattr(pipeline, "_uncommitted_archive_outputs", lambda c, w: [])
    pipeline._run_website_sync(tmp_path, "https://mp.weixin.qq.com/s/X", runner=runner)
    return captured


def test_website_sync_timeout_covers_a_real_release(tmp_path, monkeypatch):
    """一次真实授权发布（全站构建+素材上传+激活+验证）实测约 20 分钟。
    900s 会把发布进程在中途杀掉（2026-08-15 OBS-27 finalize 实证），
    超时必须给足余量。"""
    monkeypatch.delenv("SANSHENG_WRITE_WEBSITE_TIMEOUT", raising=False)
    kwargs = _run_capture_kwargs(tmp_path, monkeypatch)
    assert kwargs["timeout"] >= 2400


def test_website_sync_timeout_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_WRITE_WEBSITE_TIMEOUT", "120")
    kwargs = _run_capture_kwargs(tmp_path, monkeypatch)
    assert kwargs["timeout"] == 120


def test_archived_code_reads_this_worktree_works_file(tmp_path):
    article = tmp_path / "94-psychology"
    article.mkdir()
    (tmp_path / "作品库.yaml").write_text(
        "works:\n- seq: 94\n  code: OBS-30\n", encoding="utf-8")
    assert pipeline._archived_code(article) == "OBS-30"


def test_archived_code_missing_code_raises(tmp_path):
    article = tmp_path / "94-psychology"
    article.mkdir()
    (tmp_path / "作品库.yaml").write_text(
        "works:\n- seq: 94\n  title: x\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="没有 CODE"):
        pipeline._archived_code(article)


def test_empty_code_does_not_run_website_command(tmp_path, monkeypatch):
    called = {"n": 0}

    def runner(*_a, **_k):
        called["n"] += 1
        raise AssertionError("empty CODE must not invoke website_command")

    monkeypatch.setattr(
        pipeline, "brand",
        lambda: {"publish": {"website_command": "run-site {code}",
                             "website_cwd": str(tmp_path)}})
    monkeypatch.setattr(pipeline, "_archived_code", lambda _c: "")
    monkeypatch.setattr(pipeline, "_resolve_website_command", lambda c: (c, ""))
    monkeypatch.setattr(pipeline, "_uncommitted_archive_outputs", lambda c, w: [])
    assert pipeline._run_website_sync(
        tmp_path, "https://mp.weixin.qq.com/s/X", runner=runner) is False
    assert called["n"] == 0
    receipt = json.loads(
        (tmp_path / "_website-sync-receipt.json").read_text(encoding="utf-8"))
    assert receipt["latest"]["status"] == "failed"
    assert receipt["latest"]["reason"] == "article_code_missing"
