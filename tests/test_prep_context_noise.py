"""_prep-context.md 的噪声治理（2026-08-16 审计修复的安全网）。

三件事：① 声纹样本取最近（尾部）而不是最旧（头部）——learn_edits 往尾部追加，
头部截断让新样本永不可见；② 缺料的可选段整节不输出——旧行为对着不存在的
范文打印「写前通读一遍」；③ 反 AI 工具箱只注入 A/B/C 规则本体，元说明与
沿革（~3.4KB 维护者向内容）剥掉。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prep_writing import _toolbox_body, _voice_excerpt, build_prep_context  # noqa: E402


# ── ① 声纹取样 ──────────────────────────────────────────────────────────────

def test_voice_excerpt_prefers_tail_over_head():
    old = "## 2026-07-11 · 旧文\n\n" + ("旧段落。" * 40 + "\n\n") * 40
    new = "## 2026-08-15 · 新文\n\n最新追加的样本段落，必须可见。\n"
    text = old + new
    excerpt = _voice_excerpt(text, budget=2000)
    assert "最新追加的样本段落" in excerpt, "尾部新样本必须进窗口"
    assert len(excerpt) <= 2000


def test_voice_excerpt_strips_html_and_duplicate_headers():
    text = (
        "## 2026-07-11 · 同一篇\n段落一。\n"
        '<section style="margin:0">微信残渣</section>\n'
        "## 2026-07-11 · 同一篇\n段落二。\n"
        "## 2026-07-11 · 同一篇\n段落三。\n"
    )
    excerpt = _voice_excerpt(text, budget=6000)
    assert "微信残渣" not in excerpt
    assert excerpt.count("## 2026-07-11 · 同一篇") == 1
    for p in ("段落一", "段落二", "段落三"):
        assert p in excerpt


def test_voice_excerpt_keeps_short_text_whole():
    text = "## 标题\n很短的语料。"
    assert _voice_excerpt(text, budget=6000) == text


# ── ③ 工具箱剥元说明 ────────────────────────────────────────────────────────

def test_toolbox_body_cuts_meta_sections_keeps_rules():
    text = (
        "# 反 AI 写作工具箱\n\n## A 层 · 无条件铁律（每段必扫）\n规则……\n\n"
        "## 与你的手册 compact 的关系\n元说明……\n\n"
        "## 与 iron-rules.md 的关系\n元说明……\n\n## 历史背景（为什么有这份文件）\n沿革……\n"
    )
    body = _toolbox_body(text)
    assert "A 层" in body
    assert "与你的手册 compact 的关系" not in body
    assert "历史背景" not in body


def test_toolbox_body_passthrough_without_marker():
    text = "# 某文件\n没有元说明标题。"
    assert _toolbox_body(text) == text


def test_real_toolbox_file_gets_stripped():
    tf = Path(__file__).resolve().parents[1] / "references" / "反 AI 写作工具箱.md"
    raw = tf.read_text(encoding="utf-8").strip()
    body = _toolbox_body(raw)
    assert "## A 层" in body and "## B 层" in body and "## C 层" in body
    assert "与 iron-rules.md 的关系" not in body
    a_idx, b_idx, c_idx = raw.find("## A 层"), raw.find("## B 层"), raw.find("## C 层")
    assert a_idx >= 0 and b_idx > a_idx and c_idx > b_idx
    assert "### B2" in raw[b_idx:c_idx]
    assert "自嘲" in raw[b_idx:c_idx]
    assert "### A2" not in raw[a_idx:b_idx]


# ── ② 缺料段整节不输出（集成：走真实 build_prep_context） ────────────────────

def test_optional_sections_vanish_when_material_missing(tmp_path, monkeypatch):
    # 最小 profile：只有一个 author compact，无 samples/、无 style-examples.md
    profile = tmp_path / "profile"
    (profile / "corpus" / "authors").mkdir(parents=True)
    (profile / "corpus" / "authors" / "测试作者.compact.md").write_text(
        "# 测试作者\n写短句。", encoding="utf-8"
    )
    monkeypatch.setenv("SANSHENG_WRITE_PROFILE_DIR", str(profile))
    import profile_config

    profile_config._cache.clear()

    article = tmp_path / "article"
    article.mkdir()
    (article / "article-meta.yaml").write_text(
        'title: "测试"\nstyle: "测试作者"\n', encoding="utf-8"
    )
    text, missing = build_prep_context(article)

    # 缺料段不许留下空壳标题与「写前通读」指令
    assert "整篇金标范文" not in text
    assert "风格 few-shot 示例" not in text
    # 工具箱元说明不进写作上下文
    assert "与 iron-rules.md 的关系" not in text
    # 缺料事实仍进 missing 清单，不是静默丢失
    assert any("金标范文" in m for m in missing)

    profile_config._cache.clear()
