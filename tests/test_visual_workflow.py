import json
import subprocess
import sys
from pathlib import Path

from scripts import pipeline


PIPELINE = Path(pipeline.__file__).resolve()
PRODUCER = "sansheng-write.visual-planner"


def _plan() -> dict:
    return {
        "schema_version": 1,
        "cover": {
            "title": "教程 | 视觉合同",
            "subtitle": "弱模型也不能漏规则",
            "visual_facts": ["一份任务单", "一条发布入口"],
        },
        "hero": {
            "title": "视觉合同",
            "visual_facts": ["规则内建", "渲染外置"],
        },
        "infographics": [
            {
                "id": "01",
                "position": "opening",
                "aspect_ratio": "9:16",
                "title": "先锁定输入",
                "layout": "structured-card",
                "expected_text": ["作者定稿", "任务单"],
                "facts": ["定稿哈希绑定任务单"],
            },
            {
                "id": "02",
                "position": "middle",
                "aspect_ratio": "16:9",
                "title": "再编译规则",
                "layout": "comparison",
                "expected_text": ["业务规则", "像素渲染"],
                "facts": ["业务规则归 write", "渲染器可替换"],
            },
            {
                "id": "03",
                "position": "middle",
                "aspect_ratio": "16:9",
                "title": "发布硬门",
                "layout": "flow",
                "expected_text": ["预检", "发布", "读回"],
                "facts": ["三步必须由一个命令完成"],
            },
            {
                "id": "04",
                "position": "closing",
                "aspect_ratio": "9:16",
                "title": "草稿箱交付",
                "layout": "checklist",
                "expected_text": ["草稿已读回", "正式发布人工完成"],
                "facts": ["自动链终点是微信草稿箱"],
            },
        ],
    }


def _article(tmp_path: Path) -> Path:
    article = tmp_path / "article"
    article.mkdir()
    (article / "定稿.md").write_text(
        "---\n"
        'title: "教程 | 视觉合同"\n'
        'description: "一份稳定的视觉发布合同。"\n'
        "---\n\n# 教程 | 视觉合同\n\n" + "正文段落。\n" * 80,
        encoding="utf-8",
    )
    (article / "article-meta.yaml").write_text(
        'title: "教程 | 视觉合同"\n'
        'digest: "一份稳定的视觉发布合同。"\n'
        'cover_style: "montage-evidence"\n'
        'infographic_subject: "ai-product"\n'
        'infographic_style: "claymation"\n'
        'visual_profile: "warm-light-clay"\n',
        encoding="utf-8",
    )
    (article / "visual-plan.json").write_text(
        json.dumps(_plan(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return article


def test_visual_plan_rejects_wrong_cover_edges_and_middle_ratios():
    from scripts.visual_workflow import validate_visual_plan

    plan = _plan()
    plan["cover"]["aspect_ratio"] = "1:1"
    plan["infographics"][0]["aspect_ratio"] = "16:9"
    plan["infographics"][1]["aspect_ratio"] = "9:16"

    errors = validate_visual_plan(plan)

    assert any("cover aspect_ratio=2.35:1" in error for error in errors)
    assert any("首张信息图必须" in error for error in errors)
    assert any("中间信息图" in error for error in errors)


def test_visual_plan_requires_four_images_and_unique_ids():
    from scripts.visual_workflow import validate_visual_plan

    plan = _plan()
    plan["infographics"] = plan["infographics"][:3]
    plan["infographics"][1]["id"] = "01"

    errors = validate_visual_plan(plan)

    assert any("至少 4 张" in error for error in errors)
    assert any("id 必须唯一" in error for error in errors)


def test_compiler_injects_contract_and_builds_baoyu_batch(tmp_path):
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    result, errors = compile_visual_plan(article)

    assert errors == []
    assert result["producer"] == PRODUCER
    cover = (article / "素材/prompts/final/cover.md").read_text(encoding="utf-8")
    info = (article / "素材/prompts/final/infographic-01.md").read_text(
        encoding="utf-8"
    )
    assert f'producer: "{PRODUCER}"' in cover
    assert 'aspect_ratio: "2.35:1"' in cover
    assert 'title_block_height: "20%"' in cover
    assert 'visual_profile: "warm-light-clay"' in info
    assert "visual_profile_sha256:" in info
    assert "palette_background:" in info
    assert "作者定稿" in info and "任务单" in info
    batch = json.loads(
        (article / "素材/render-batch.json").read_text(encoding="utf-8")
    )
    assert [task["ar"] for task in batch["tasks"]] == [
        "2.35:1",
        "1:1",
        "9:16",
        "16:9",
        "16:9",
        "9:16",
    ]
    assert all(task["promptFiles"][0].startswith("prompts/final/") for task in batch["tasks"])
    assert batch["producer"] == PRODUCER


def test_compiler_writes_analysis_and_structured_content_from_same_plan(tmp_path):
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    _, errors = compile_visual_plan(article)

    assert errors == []
    analysis = (article / "素材/infographic/analysis.md").read_text(encoding="utf-8")
    structured = (article / "素材/infographic/structured-content.md").read_text(
        encoding="utf-8"
    )
    assert "claymation" in analysis
    assert "01 · opening · 9:16" in analysis
    assert "定稿哈希绑定任务单" in structured
    assert "自动链终点是微信草稿箱" in structured


def test_pipeline_compile_visuals_command(tmp_path):
    article = _article(tmp_path)

    result = subprocess.run(
        [sys.executable, str(PIPELINE), "compile-visuals"],
        cwd=article,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "6" in result.stdout
    assert (article / "素材/render-batch.json").exists()
