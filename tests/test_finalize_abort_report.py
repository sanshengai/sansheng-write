"""finalize 中断时必须点名「后面还有哪几步没跑」。

第 89 篇的实跑事故：finalize 在 distribution（播客）上 SystemExit(3)，屏幕上
只有一行播客报错。人据此判断「补跑一次播客就行」，补完收工 —— 而排在它后面的
website_sync 从头到尾没执行。文章正文被别人一次不相干的部署顺带带上了线，配图
和音频却从没上传，线上整页破图，零报警。

失败允许发生；失败时不说清「这条链还剩什么」不允许。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


def test_abort_lists_every_unrun_downstream_step(capsys):
    state = {"steps": {
        "publish_link": {"status": "done"},
        "archive": {"status": "done"},
        "archive_verify": {"status": "done"},
        "moments_copy": {"status": "done"},
    }}
    pipeline._report_finalize_abort(state, "distribution")
    out = capsys.readouterr().out

    assert "没有走完" in out
    assert "website_sync" in out, "官网同步没跑就必须点名，这正是第 89 篇踩的坑"
    assert "重跑 finalize" in out


def test_abort_does_not_relist_completed_steps(capsys):
    """续跑场景：官网早已同步过，就别再报它没跑。"""
    state = {"steps": {
        "publish_link": {"status": "done"},
        "website_sync": {"status": "done"},
    }}
    pipeline._report_finalize_abort(state, "distribution")
    out = capsys.readouterr().out

    assert "website_sync" not in out
    assert "此前已完成" in out


def test_abort_on_last_step_has_nothing_downstream(capsys):
    state = {"steps": {}}
    pipeline._report_finalize_abort(state, "website_sync")
    out = capsys.readouterr().out

    assert "没有走完" in out
    assert "· website_sync" not in out


def test_step_order_matches_the_real_finalize_chain():
    """顺序是语义的一部分：播客必须排在官网之前，否则首发页面只剩主题曲。"""
    names = [key for key, _ in pipeline.FINALIZE_STEPS]
    assert names.index("distribution") < names.index("website_sync")
    assert names.index("archive") < names.index("archive_verify")
    assert names[0] == "publish_link"


def test_unknown_step_is_silent(capsys):
    pipeline._report_finalize_abort({"steps": {}}, "not_a_step")
    assert capsys.readouterr().out == ""


def test_finalize_actually_calls_the_report_on_distribution_failure(
    tmp_path, monkeypatch, capsys
):
    """钉住调用点，不只钉函数。

    只测 _report_finalize_abort 本身是不够的：把 cmd_finalize 里那行调用删掉，
    单元测试照样全绿 —— 函数写对了却没接上，正是第 89 篇那类「零报警」缺陷的
    温床。这条测试走真实的 cmd_finalize 控制流。
    """
    url = "https://mp.weixin.qq.com/s/TESTONLY"
    art = tmp_path / "90-x"
    art.mkdir()

    monkeypatch.setattr(pipeline, "_finalize_preflight_errors", lambda c, u: [])
    monkeypatch.setattr(
        pipeline, "_load_or_reset_finalize_state",
        lambda c, u: {"steps": {
            "publish_link": {"status": "done"},
            "archive": {"status": "done"},
            "archive_verify": {"status": "done"},
            "moments_copy": {"status": "done"},
        }})
    # 播客失败 —— 就是实跑那次的形态
    monkeypatch.setattr(pipeline, "_handoff_to_distribute", lambda c: False)
    monkeypatch.setattr(
        pipeline, "_run_website_sync",
        lambda c, u: pytest.fail("播客失败后不该继续同步官网"))

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_finalize(url, art)

    assert exc.value.code == 3
    out = capsys.readouterr().out
    assert "website_sync" in out, "中断时必须告诉作者官网同步还没跑"
