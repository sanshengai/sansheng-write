from PIL import Image


def test_text_safe_visual_renders_exact_contract_dimensions(tmp_path):
    from scripts.render_text_safe_visual import render_hero, render_infographic

    hero_path = tmp_path / "hero.png"
    info_path = tmp_path / "info.png"
    render_hero({"title": "只允许这一行标题"}, hero_path)
    render_infographic(
        {
            "aspect_ratio": "9:16",
            "title": "确定性信息图",
            "expected_text": ["标签一", "标签二", "标签三", "标签四"],
        },
        info_path,
    )

    with Image.open(hero_path) as hero:
        assert hero.size == (1024, 1024)
    with Image.open(info_path) as info:
        assert info.size == (576, 1024)
    assert hero_path.stat().st_size > 10_000
    assert info_path.stat().st_size > 10_000
