"""发给图像模型的那份 prompt 必须只有正文，不带 YAML frontmatter。

🔴 2026-08-16 实测修复，是这一轮改造里最后一块、也是单项收益最大的一块。

canonical prompt 是带 frontmatter 的 .md，头部约 340 字符：producer、
schema_version、method_sources、**两个 64 位 sha256**、**两个 hex 色号**。
而 baoyu-image-gen 的 readPromptFromFiles() 是 `readFile(f, "utf8")` 整个文件
塞进去 —— 那段纯元数据原样发给了图像模型。

12 张对照（同内容、同 allowlist、同 SCENE、同模型，唯一变量是带不带 frontmatter）：

    带 frontmatter    8/12 = 67%
    剥掉 frontmatter 11/12 = 92%

典型翻车形态就是模型把哈希串、色号那类字符串当成「要写的字」，在画面上补出
乱码汉字或整条色卡（早前实测抓到过一张底部渲出 #F7F2E9 / #79AA95 的色卡带）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

FRONTMATTER = """---
schema_version: 1
producer: "sansheng-write.visual-planner"
method_sources: ["baoyu-infographic"]
stage: "infographic"
expected_text_sha256: "4f21ba4d9803ab3298e6fa40d5cc7af3b342be9b0f1d976e5baf32e4598e6313"
visual_profile_sha256: "709edd9694ad930db9a56cc2d27843b3af56ff94d772882edc9bc832d6fe393f"
palette_background: "#F7F2E9"
palette_accent: "#79AA95"
---

A high-information Chinese infographic in claymation style.

SCENE — build this arrangement out of clay: five small clay robots.

## VISIBLE TEXT ALLOWLIST — EXHAUSTIVE
- 一个月，八次更新
- 中国五个
"""

NOISE = [
    "schema_version", "producer", "method_sources",
    "4f21ba4d9803ab3298e6fa40d5cc7af3b342be9b0f1d976e5baf32e4598e6313",
    "709edd9694ad930db9a56cc2d27843b3af56ff94d772882edc9bc832d6fe393f",
    "#F7F2E9", "#79AA95",
]


import render_visuals as rv  # noqa: E402

_split_body = rv.prompt_body


def test_body_split_drops_all_metadata_noise():
    body = _split_body(FRONTMATTER)
    for token in NOISE:
        assert token not in body, f"元数据泄漏进发给模型的正文：{token}"


def test_body_split_keeps_everything_the_model_needs():
    body = _split_body(FRONTMATTER)
    assert "claymation" in body
    assert "SCENE" in body
    assert "five small clay robots" in body
    assert "一个月，八次更新" in body
    assert "中国五个" in body


def test_body_split_is_idempotent_for_files_without_frontmatter():
    plain = "A plain prompt with no front matter.\n"
    assert _split_body(plain) == plain


def test_body_split_survives_horizontal_rules_in_the_body():
    """正文里出现 --- 分隔线时，不能把正文也切掉。"""
    text = FRONTMATTER + "\n---\n\nextra tail paragraph\n"
    body = _split_body(text)
    assert "extra tail paragraph" in body
    assert "schema_version" not in body


@pytest.mark.parametrize("token", NOISE)
def test_each_noise_token_is_individually_removed(token):
    assert token not in _split_body(FRONTMATTER)


def test_attempt_task_points_the_renderer_at_the_stripped_body(tmp_path):
    """🔴 钉调用点：batch 里给渲染器的 promptFiles 必须是剥好的正文。

    只测 prompt_body() 是不够的 —— 把 build_attempt_task 里那行替换删掉，
    单元测试照样全绿（实测过）。这条走真实的 batch 构造。
    """
    material = tmp_path / "素材"
    (material / "prompts" / "final").mkdir(parents=True)
    canonical = material / "prompts" / "final" / "infographic-01.md"
    canonical.write_text(FRONTMATTER, encoding="utf-8")

    task = {"id": "infographic-01", "image": "infographic-01.png",
            "ar": "9:16", "promptFiles": ["prompts/final/infographic-01.md"]}
    out = rv.build_attempt_task(
        task, {"provider": "google", "model": "gemini-3.1-flash-image"},
        "infographic-01", material)

    assert out["promptFiles"] != task["promptFiles"], "promptFiles 没被换成正文版"
    sent = (material / out["promptFiles"][0]).read_text(encoding="utf-8")
    for token in NOISE:
        assert token not in sent, f"元数据仍会发给模型：{token}"
    assert "中国五个" in sent and "SCENE" in sent


def test_canonical_prompt_file_is_never_touched(tmp_path):
    """canonical .md 一个字节都不许动 —— prompt_sha256 与溯源都钉在它上面。"""
    material = tmp_path / "素材"
    (material / "prompts" / "final").mkdir(parents=True)
    canonical = material / "prompts" / "final" / "infographic-01.md"
    canonical.write_text(FRONTMATTER, encoding="utf-8")
    before = canonical.read_bytes()

    rv.build_attempt_task(
        {"id": "x", "image": "x.png", "ar": "9:16",
         "promptFiles": ["prompts/final/infographic-01.md"]},
        {"provider": "google", "model": "m"}, "x", material)

    assert canonical.read_bytes() == before, "canonical prompt 被改写了"


def test_renderer_settings_still_applied(tmp_path):
    """剥离不能顺手把 provider/model 的套用弄丢。"""
    material = tmp_path / "素材"
    (material / "p").mkdir(parents=True)
    (material / "p" / "a.md").write_text(FRONTMATTER, encoding="utf-8")
    out = rv.build_attempt_task(
        {"id": "a", "image": "a.png", "ar": "1:1", "promptFiles": ["p/a.md"]},
        {"provider": "google", "model": "gemini-3-pro-image", "quality": None,
         "imageSize": "1K"},
        "a", material)
    assert out["provider"] == "google"
    assert out["model"] == "gemini-3-pro-image"
    assert out["imageSize"] == "1K"
    assert "quality" not in out, "None 的字段不该写进 batch"
