"""preflight 前移三检（2026-08-16 第 90 篇耗时归因后固化）。

第 90 篇实测：排版阶段耗时 24.9 分钟，全花在三轮重排上——
裸 URL、DEEP READ 缺入口两条要等 `format_layout --all` 才报，每报一条就得
重转一次 HTML；锚点劈段要等 `assemble-release` 才报，那时配图与 BGM 都已跑完。
这三条**全是纯静态检查**，前移到 preflight（写完正文即可跑）零质量代价。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


def _article(tmp_path: Path, body: str, plan: dict | None = None) -> Path:
    d = tmp_path / "90-测试"
    (d / "素材").mkdir(parents=True)
    (d / "定稿.md").write_text(body, encoding="utf-8")
    (d / "article-meta.yaml").write_text('title: "测试"\n', encoding="utf-8")
    if plan is not None:
        (d / "visual-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return d


def _fails(results, keyword):
    return [m for lvl, name, m in results if lvl == "fail" and keyword in name]


# ── 裸 URL ────────────────────────────────────────────────────────────────

def test_bare_url_in_markdown_is_caught_before_layout(tmp_path):
    d = _article(tmp_path, "正文一段。\n\nGitHub：github.com/sanshengai/sansheng-write\n")
    assert _fails(pipeline._preflight_checks(d), "裸 URL")


def test_url_inside_link_card_passes(tmp_path):
    body = ('正文一段。\n\n<section style="padding:8px;">'
            '<section>https://github.com/sanshengai/sansheng-write</section></section>\n')
    assert not _fails(pipeline._preflight_checks(_article(tmp_path, body)), "裸 URL")


def test_markdown_link_syntax_is_not_bare(tmp_path):
    body = "正文一段，详见[上一篇](https://example.com/s/EXAMPLE-ARTICLE-ID)。\n"
    assert not _fails(pipeline._preflight_checks(_article(tmp_path, body)), "裸 URL")


# ── DEEP READ 入口 ────────────────────────────────────────────────────────

def test_deep_read_without_site_entry_is_caught(tmp_path):
    body = ("正文。\n\n<!-- SANSHENG-DEEP-READ -->\n<section>"
            "<section>https://mp.weixin.qq.com/s/abc</section></section>\n")
    assert _fails(pipeline._preflight_checks(_article(tmp_path, body)), "DEEP READ")


def test_deep_read_with_site_entry_passes(tmp_path):
    """站点入口取自**生效 profile**：测试环境下 profile 可能是示例仓（example.com），
    硬编码自家域名会必然失败 —— 首版就这么挂了一条，属测试自身的环境依赖 bug。"""
    from profile_config import identity

    site = str((identity() or {}).get("site") or "https://example.com")
    body = ("正文。\n\n<!-- SANSHENG-DEEP-READ -->\n<section>"
            f"<section>{site}</section></section>\n")
    assert not _fails(pipeline._preflight_checks(_article(tmp_path, body)), "DEEP READ")


def test_no_deep_read_block_means_no_check(tmp_path):
    assert not _fails(pipeline._preflight_checks(_article(tmp_path, "只有正文。\n")), "DEEP READ")


# ── 信息图锚点 ────────────────────────────────────────────────────────────

def _plan(anchor):
    return {"schema_version": 1, "infographics": [{"id": "01", "anchor": anchor}]}


def test_anchor_mid_paragraph_is_caught(tmp_path):
    """第 90 篇真实翻车：锚点是段落中间那句，装配会把整段劈成两半。"""
    body = "开头。\n\n它治这个不靠多加规则，靠换供给。写之前，它先把你的原话存起来。\n"
    d = _article(tmp_path, body, _plan("它治这个不靠多加规则，靠换供给。"))
    assert _fails(pipeline._preflight_checks(d), "锚点")


def test_anchor_at_paragraph_end_passes(tmp_path):
    body = "开头。\n\n读者读到的是你，不是模型。\n\n下一段。\n"
    d = _article(tmp_path, body, _plan("读者读到的是你，不是模型。"))
    assert not _fails(pipeline._preflight_checks(d), "锚点")


def test_anchor_not_unique_is_caught(tmp_path):
    body = "同一句话。\n\n中间段。\n\n同一句话。\n"
    d = _article(tmp_path, body, _plan("同一句话。"))
    assert _fails(pipeline._preflight_checks(d), "锚点")
