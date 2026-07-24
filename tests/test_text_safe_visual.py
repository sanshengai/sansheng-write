import json

from PIL import Image


def test_text_safe_visual_renders_reviewed_templates_and_design_manifests(tmp_path):
    from scripts.render_text_safe_visual import (
        render_cover,
        render_hero,
        render_infographic,
    )

    cover_path = tmp_path / "cover.png"
    hero_path = tmp_path / "hero.png"
    render_cover(
        {
            "line1": "三条曲线",
            "line2": "同时拐弯",
            "descriptor": "中国老龄化的机会重排",
            "ghost": "BIRTH × CARE × CITY",
        },
        cover_path,
    )
    render_hero({"title": "只允许这一行标题"}, hero_path)
    specs = [
        ("curve-convergence", "9:16"),
        ("service-map", "16:9"),
        ("tiered-network", "16:9"),
        ("experience-loop", "9:16"),
    ]
    outputs = []
    for index, (template_id, aspect_ratio) in enumerate(specs, start=1):
        output = tmp_path / f"info-{index}.png"
        render_infographic(
            {
                "aspect_ratio": aspect_ratio,
                "template_id": template_id,
                "title": "存量空间改造与三级养老服务节点",
                "expected_text": [
                    "标签一需要准确清晰地显示",
                    "标签二需要准确清晰地显示",
                    "标签三需要准确清晰地显示",
                    "标签四需要准确清晰地显示",
                ],
            },
            output,
        )
        outputs.append(output)

    with Image.open(cover_path) as cover:
        assert cover.size == (1024, 436)
    with Image.open(hero_path) as hero:
        assert hero.size == (1024, 1024)
    assert [Image.open(path).size for path in outputs] == [
        (576, 1024),
        (1024, 576),
        (1024, 576),
        (576, 1024),
    ]
    for path, (template_id, _) in zip(outputs, specs):
        manifest_path = path.with_suffix(".design.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["template_id"] == template_id
        assert manifest["image_sha256"]
        assert manifest["visual_elements"]
        assert len(manifest["text_boxes"]) == 5
        safe = manifest["safe_bounds"]
        for box in manifest["text_boxes"]:
            x1, y1, x2, y2 = box["box"]
            assert safe[0] <= x1 < x2 <= safe[2]
            assert safe[1] <= y1 < y2 <= safe[3]
    cover_manifest = json.loads(
        cover_path.with_suffix(".design.json").read_text(encoding="utf-8")
    )
    assert cover_manifest["template_id"] == "montage-evidence-v2"
    assert cover_manifest["text_roles"]["line1"] == "primary"
    assert cover_manifest["text_roles"]["line2"] == "secondary"
    assert cover_manifest["font_scale_ratio"]["line2_to_line1"] <= 0.65
