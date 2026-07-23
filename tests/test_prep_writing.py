"""render_fact_sheet 事实数据清单注入的单元测试（C9 · 2026-07-02）。

覆盖：research fan-out 产物正常渲染 / need_verify 标记 / 信源附注 /
缺产物时优雅降级不抛异常（历史文章无 素材/research/*.json 属正常）。
"""
import json
from pathlib import Path

from scripts.prep_writing import render_fact_sheet


def _write_research(cwd: Path, payload: dict, name: str = "r1.json"):
    rd = cwd / "素材" / "research"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_fact_sheet_renders_findings(tmp_path):
    _write_research(tmp_path, {
        "findings": [
            {"claim": "Opus 4.8 距 4.7 隔 42 天", "support": "官网发布日期", "confidence": "high"},
            {"claim": "某榜单省 61%", "support": "Databricks 实测", "confidence": "need_verify"},
        ],
        "sources": [
            {"title": "Anthropic 官网", "url": "https://anthropic.com", "tier": "官网"},
        ],
    })
    lines, missing = render_fact_sheet(tmp_path)
    text = "\n".join(lines)
    assert missing is None
    assert "Opus 4.8 距 4.7 隔 42 天" in text
    assert "⚠️ 待核实" in text          # need_verify 项被标记
    assert "Anthropic 官网" in text      # 信源附注
    assert "一·据" in text               # 节标题


def test_fact_sheet_graceful_when_absent(tmp_path):
    # 无 素材/research 目录 → 优雅降级, 不抛异常, 返回缺料提示
    lines, missing = render_fact_sheet(tmp_path)
    assert lines == []
    assert missing is not None
    assert "补搜" in missing or "research" in missing


def test_fact_sheet_empty_findings(tmp_path):
    # 有文件但无有效 findings → 不渲染空清单, 给缺料提示
    _write_research(tmp_path, {"findings": [], "sources": []})
    lines, missing = render_fact_sheet(tmp_path)
    assert lines == []
    assert missing is not None


def test_fact_sheet_skips_malformed_json(tmp_path):
    # 坏 json 不应让整个函数崩溃
    rd = tmp_path / "素材" / "research"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "bad.json").write_text("{not valid json", encoding="utf-8")
    _write_research(tmp_path, {
        "findings": [{"claim": "有效条目", "support": "x", "confidence": "high"}],
        "sources": [],
    }, name="good.json")
    lines, missing = render_fact_sheet(tmp_path)
    text = "\n".join(lines)
    assert "有效条目" in text


def test_fact_sheet_skips_valid_non_contract_json(tmp_path):
    """RRF 检索结果是合法 JSON 列表，但不是 research findings 契约，不能让 prep 崩溃。"""
    rd = tmp_path / "素材" / "research"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "检索结果-merged.json").write_text(
        json.dumps([{"url": "https://example.com", "title": "检索结果"}], ensure_ascii=False),
        encoding="utf-8",
    )
    _write_research(tmp_path, {
        "findings": [{"claim": "有效事实", "support": "官方来源", "confidence": "high"}],
        "sources": [],
    }, name="fact-sheet.json")

    lines, missing = render_fact_sheet(tmp_path)
    text = "\n".join(lines)

    assert missing is None
    assert "有效事实" in text
    assert "跳过 检索结果-merged.json" in text
