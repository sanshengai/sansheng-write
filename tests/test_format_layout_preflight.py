"""format_layout preflight 开篇标识门测试（D2 · 2026-07-02）。

覆盖：① 二级绿 <mark class="2"> 被 _n_anchor 计入(修复漏计 bug)；
② 开篇标识过稀触发比例密度门(每 ~120 字 1 处)；③ 标识充足则放行。
"""
from pathlib import Path

from scripts.format_layout import preflight_markdown


def _write(tmp_path: Path, body: str) -> str:
    (tmp_path / "定稿.md").write_text("---\ntitle: t\n---\n\n" + body, encoding="utf-8")
    return str(tmp_path)


def test_secondary_green_counts_as_anchor(tmp_path):
    # <mark class="2"> 二级绿应被计入开篇标识, 不再误判为"零标识裸段"
    seg = "测" * 60 + "，这里有个<mark class=\"2\">次级锚点</mark>收尾。"
    errors, _ = preflight_markdown(_write(tmp_path, seg + "\n"))
    assert not any("零词组级重点标识" in e for e in errors)


def test_density_gate_fires_when_sparse(tmp_path):
    # 一段 ~300 字仅 1 处标识 → 低于每 120 字 1 处 → 触发密度门
    seg = "测" * 300 + "，只有一个**关键锚点**。"
    errors, _ = preflight_markdown(_write(tmp_path, seg + "\n"))
    assert any("密度门" in e for e in errors)


def test_dense_opening_passes(tmp_path):
    # 两段各 ~110 字各 2 处标识 → 每段 ≥1 且总量达标 → 无开篇门 error
    seg = "测" * 108 + "**锚一**又**锚二**。"
    errors, _ = preflight_markdown(_write(tmp_path, seg + "\n\n" + seg + "\n"))
    assert not any("开篇" in e for e in errors)


# ── A4（2026-09-22）：B-主门 Jev 影子软提示行，只报不拦 ─────────────────────
from scripts.format_layout import jev_shadow_lines


def test_jev_shadow_lines_only_in_shadow_with_scores():
    summary = {"mode": "shadow", "scored": 12, "agree": 10, "baseline_hits": 1, "jev_hits": 3,
               "new_hits": [{"line": 8, "noul": 0.81, "excerpt": "在这个快速发展的时代"},
                            {"line": 20, "noul": 0.7, "excerpt": "值得注意的是"},
                            {"line": 31, "noul": 0.66, "excerpt": "总而言之"},
                            {"line": 40, "noul": 0.6, "excerpt": "第四条不该出现"}]}
    lines = jev_shadow_lines(summary)
    assert lines[0].startswith("ℹ️ B-主门影子：Jev 第二意见 4 段（只报）") and "正则 1 vs Jev 3" in lines[0]
    assert len(lines) == 4 and all("Jev 影子：clean vs hit" in l for l in lines[1:])   # 最多 3 条样本
    assert "第四条不该出现" not in "".join(lines)
    # 反例：enforce / off / error / 没打分 / 非 dict → 不出行
    for bad in ({**summary, "mode": "enforce"}, {**summary, "mode": "off"}, {"mode": "error", "error": "x"},
                {**summary, "scored": 0}, None, "shadow"):
        assert jev_shadow_lines(bad) == []
