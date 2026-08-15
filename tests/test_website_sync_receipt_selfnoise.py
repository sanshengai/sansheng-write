"""官网同步前置检查不得把「自己写的回执」当成未提交的归档产物。

2026-08-16 第 90 篇实跑：`_append_website_sync_attempt` 每次失败都更新
`_website-sync-receipt.json`，而它就在被扫描的文章目录内 —— 于是
「提交回执 → 重跑 finalize → 回执又被更新 → 又判未提交」死循环，卡了三轮。
回执是本次运行的产物，官网构建只读作品库与派生视图，扫它没有意义。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


class _Probe:
    """把 git status 的输出替换成受控样本。"""

    def __init__(self, lines):
        self.returncode = 0
        self.stdout = "\n".join(lines) + ("\n" if lines else "")
        self.stderr = ""


def _run(monkeypatch, lines):
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **k: _Probe(lines))
    return pipeline._uncommitted_archive_outputs(Path("."), Path("."))


def test_receipt_alone_is_not_blocking(monkeypatch):
    out = _run(monkeypatch, [' M "文稿成品/90-x/_website-sync-receipt.json"'])
    assert out == []


def test_finalize_state_alone_is_not_blocking(monkeypatch):
    out = _run(monkeypatch, ['?? "文稿成品/90-x/_finalize-state.json"'])
    assert out == []


def test_real_archive_output_still_blocks(monkeypatch):
    """作品库没提交必须照拦——这是本检查存在的理由，不能被削弱。"""
    out = _run(monkeypatch, [' M "文稿成品/作品库.yaml"'])
    assert len(out) == 1 and "作品库" in out[0]


def test_mixed_keeps_only_real_outputs(monkeypatch):
    out = _run(monkeypatch, [
        ' M "文稿成品/90-x/_website-sync-receipt.json"',
        ' M "文稿成品/articles.md"',
        '?? "文稿成品/90-x/_finalize-state.json"',
    ])
    assert len(out) == 1 and "articles.md" in out[0]


def test_clean_tree_returns_empty(monkeypatch):
    assert _run(monkeypatch, []) == []
