"""生图重渲必须留痕 —— 这是「无法测量就无法改进」的那块补丁。

改造前整条视觉链路对重渲是**完全盲的**：
  · `.gen-log.jsonl` 只追加成功那次
  · `_visual-qa.json` 只保存最终通过那版，失败判定连同原因一起消失
  · `render-receipt.json` 的 attempts 只到整批粒度

于是「某张图渲了几次、每次为什么不合格」一条都查不到。代价是实打实的：
为了搞清 45 次生图里哪些必要，只能靠 60 张手工对照实验反推。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402
import render_visuals as rv  # noqa: E402


def test_log_and_read_roundtrip(tmp_path):
    rv.log_attempt(tmp_path, {"kind": "render", "label": "cover", "outcome": "ok"})
    rv.log_attempt(tmp_path, {"kind": "render", "label": "cover", "outcome": "ok"})
    rows = rv.read_attempts(tmp_path)
    assert len(rows) == 2
    assert rows[0]["label"] == "cover"


def test_log_is_cumulative_across_calls(tmp_path):
    """🔴 重渲的定义本身就跨越多次命令调用 —— 每次调用清一次等于把要测的东西抹掉。"""
    rv.log_attempt(tmp_path, {"kind": "render", "label": "a", "outcome": "ok"})
    rv.log_attempt(tmp_path, {"kind": "render", "label": "a", "outcome": "ok"})
    rv.log_attempt(tmp_path, {"kind": "render", "label": "b", "outcome": "ok"})
    assert len(rv.read_attempts(tmp_path)) == 3


def test_next_seq_counts_per_label(tmp_path):
    rows = [{"label": "a"}, {"label": "a"}, {"label": "b"}]
    assert rv.next_seq(rows, "a") == 3
    assert rv.next_seq(rows, "b") == 2
    assert rv.next_seq(rows, "c") == 1
    assert rv.next_seq([], "a") == 1


def test_read_survives_corrupt_lines(tmp_path):
    """观测数据坏了也不能拖垮渲染链路。"""
    path = rv.attempt_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"label":"a"}\n{ 坏行 \n\n{"label":"b"}\n', encoding="utf-8")
    rows = rv.read_attempts(tmp_path)
    assert [r["label"] for r in rows] == ["a", "b"]


def test_read_returns_empty_when_missing(tmp_path):
    assert rv.read_attempts(tmp_path) == []


def test_log_never_raises_even_if_path_unwritable(tmp_path, monkeypatch):
    """观测失败绝不改变渲染结果 —— 宁可少一条记录，不可多一次失败。"""
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", boom)
    rv.log_attempt(tmp_path, {"kind": "render", "label": "a"})  # 不抛


# ── 汇总 ──────────────────────────────────────────────────────────────────
def _rows():
    return [
        {"kind": "render", "label": "infographic-01", "outcome": "ok",
         "model": "flash", "output_sha256": "aaa"},
        {"kind": "render", "label": "infographic-01", "outcome": "ok",
         "model": "flash", "output_sha256": "bbb"},
        {"kind": "render", "label": "infographic-01", "outcome": "renderer_failed",
         "model": "flash"},
        {"kind": "render", "label": "cover", "outcome": "ok",
         "model": "pro", "output_sha256": "ccc"},
        {"kind": "qa_verdict", "label": "infographic-01", "outcome": "fail",
         "failed_checks": ["text_match"]},
        {"kind": "qa_verdict", "label": "cover", "outcome": "ok",
         "failed_checks": []},
    ]


def test_summary_counts_renders_and_waste():
    s = pipeline.summarize_render_attempts(_rows())
    assert s["total_renders"] == 4
    assert s["assets"] == 2
    assert s["necessary"] == 2
    assert s["wasted"] == 2, "4 次渲染 2 张图 → 浪费 2 次"
    assert 0.49 < s["waste_ratio"] < 0.51


def test_summary_breaks_down_per_label():
    per = pipeline.summarize_render_attempts(_rows())["per_label"]
    assert per["infographic-01"]["renders"] == 3
    assert per["infographic-01"]["ok"] == 2
    assert per["infographic-01"]["failed"] == 1
    assert per["infographic-01"]["qa_fail"] == 1
    assert per["infographic-01"]["distinct_outputs"] == 2, "两次成功产物不同"
    assert per["cover"]["renders"] == 1
    assert per["cover"]["qa_fail"] == 0


def test_summary_ignores_qa_rows_in_render_count():
    """QA 判定不是渲染，不能被算进渲染次数。"""
    only_qa = [{"kind": "qa_verdict", "label": "a", "outcome": "fail"}]
    s = pipeline.summarize_render_attempts(only_qa)
    assert s["total_renders"] == 0
    assert s["assets"] == 0


def test_summary_on_empty_input_does_not_divide_by_zero():
    s = pipeline.summarize_render_attempts([])
    assert s["total_renders"] == 0
    assert s["waste_ratio"] == 0.0


def test_summary_reproduces_the_89th_article_numbers():
    """把第 89 篇的真实形态喂进去：6 张图、45 次渲染 → 浪费 39 次（87%）。

    那次是事后手工数出来的，正是这个函数要替掉的活。
    """
    rows = []
    for i in range(6):
        label = f"asset-{i}"
        for _ in range(7 if i < 3 else 8):
            rows.append({"kind": "render", "label": label, "outcome": "ok",
                         "output_sha256": f"{label}-{len(rows)}"})
    rows = rows[:45]
    s = pipeline.summarize_render_attempts(rows)
    assert s["total_renders"] == 45
    assert s["assets"] == 6
    assert s["wasted"] == 39
    assert round(s["waste_ratio"] * 100) == 87


# ── 命令 ──────────────────────────────────────────────────────────────────
def test_render_stats_command_is_registered():
    parser = pipeline.build_parser() if hasattr(pipeline, "build_parser") else None
    if parser is None:
        src = (Path(__file__).resolve().parents[1] / "scripts" / "pipeline.py"
               ).read_text(encoding="utf-8")
        assert '"render-stats"' in src
        assert 'cmd_render_stats(cwd)' in src
        return
    names = set(parser._subparsers._group_actions[0].choices)  # noqa: SLF001
    assert "render-stats" in names


def test_render_stats_prints_summary(tmp_path, capsys):
    for row in _rows():
        rv.log_attempt(tmp_path, row)
    pipeline.cmd_render_stats(tmp_path)
    out = capsys.readouterr().out
    assert "infographic-01" in out
    assert "浪费" in out
    assert "最费的一张" in out


def test_render_stats_is_explicit_when_there_is_no_history(tmp_path, capsys):
    """没数据时要说清是「还没开始记」，不能让人以为「渲了 0 次」。"""
    pipeline.cmd_render_stats(tmp_path)
    out = capsys.readouterr().out
    assert "暂无渲染尝试记录" in out
    assert "2026-08-16" in out, "要讲明更早的文章查不到历史"


# ── QA 判定留痕 ───────────────────────────────────────────────────────────
def test_qa_verdict_records_failed_checks(tmp_path):
    qa = {
        "reviewer": {"model": "reviewer-x"},
        "assets": [
            {"path": "素材/infographic-01.png",
             "checks": {"text_match": {"pass": False},
                        "crop_safe": {"pass": True}}},
            {"path": "素材/cover.png",
             "checks": {"text_match": {"pass": True}}},
        ],
    }
    pipeline._log_qa_verdict(tmp_path, qa, ["text_match 未通过"])
    rows = [r for r in rv.read_attempts(tmp_path) if r["kind"] == "qa_verdict"]
    by_label = {r["label"]: r for r in rows}
    assert by_label["infographic-01"]["outcome"] == "fail"
    assert by_label["infographic-01"]["failed_checks"] == ["text_match"]
    assert by_label["cover"]["outcome"] == "ok"
    assert by_label["infographic-01"]["reviewer"] == "reviewer-x"


def test_qa_verdict_logging_never_changes_the_verdict(tmp_path):
    """观测失败绝不改变 QA 结果 —— 传进畸形结构也不能抛。"""
    pipeline._log_qa_verdict(tmp_path, None, [])
    pipeline._log_qa_verdict(tmp_path, {"assets": "not-a-list"}, [])
    pipeline._log_qa_verdict(tmp_path, {"assets": [{"checks": 42}]}, [])


def test_batch_level_errors_are_recorded_when_no_assets(tmp_path):
    pipeline._log_qa_verdict(tmp_path, {"assets": []}, ["缺 _visual-qa.json"])
    rows = rv.read_attempts(tmp_path)
    assert rows and rows[0]["label"] == "(batch)"
    assert rows[0]["outcome"] == "fail"
