import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_RELEASE_DOCS = [
    ROOT / "SKILL.md",
    ROOT / "references/release-runtime.md",
    ROOT / "references/autopilot.md",
    ROOT / "references/orchestration.md",
    ROOT / "references/image-routing.md",
    ROOT / "references/cover-styles.md",
    ROOT / "references/layout.md",
    ROOT / "references/publish.md",
    ROOT / "references/iron-rules.md",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_runtime_is_short_single_source_with_all_hard_commands():
    path = ROOT / "references/release-runtime.md"
    text = _text(path)
    assert len(text.splitlines()) <= 190
    for command in (
        "adopt-final",
        "compile-visuals",
        "render-visuals",
        "visual-qa",
        "seal visual",
        "release-to-draft",
        "finalize",
    ):
        assert command in text


def test_active_release_docs_bind_internal_planner_to_baoyu_semantic_producers():
    combined = "\n".join(_text(path) for path in ACTIVE_RELEASE_DOCS)
    assert "baoyu-cover-image" in combined
    assert "baoyu-infographic" in combined
    routing = _text(ROOT / "references/image-routing.md")
    assert "sansheng-write.visual-planner" in routing
    assert "baoyu-image-gen" in routing
    assert "renderer" in routing


def test_docs_have_one_bgm_truth_and_one_draft_entry():
    combined = "\n".join(_text(path) for path in ACTIVE_RELEASE_DOCS)
    assert not re.search(r"BGM[^\n]{0,30}(?:可选|不配也行|跳过)", combined, re.I)
    assert "BGM 是发布硬门" in combined

    runtime = _text(ROOT / "references/release-runtime.md")
    publish = _text(ROOT / "references/publish.md")
    assert "done publish draft_media_id" not in runtime + publish
    assert "wechat-api.ts" not in runtime + publish
    assert "release-to-draft" in runtime and "release-to-draft" in publish


def test_orchestration_is_agent_neutral_and_public_docs_hide_private_adapter():
    neutral = _text(ROOT / "references/orchestration.md") + _text(
        ROOT / "references/autopilot.md"
    )
    assert "主 Claude" not in neutral
    assert "Claude 将" not in neutral
    combined = "\n".join(_text(path) for path in ACTIVE_RELEASE_DOCS)
    assert "Antigravity" not in combined
    assert "ORCA" not in combined
