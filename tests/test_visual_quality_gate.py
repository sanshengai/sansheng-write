import json
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from scripts import pipeline


def _png(path: Path, w: int, h: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (245, 240, 230)).save(path)


def _minimal_visual_article(tmp_path: Path, *, subject="ai-product", style="claymation") -> Path:
    (tmp_path / "素材" / "infographic").mkdir(parents=True)
    (tmp_path / "素材" / "prompts" / "final").mkdir(parents=True)
    visual_profile = 'visual_profile: "warm-light-clay"\n' if style == "claymation" else ""
    (tmp_path / "article-meta.yaml").write_text(
        f'infographic_subject: "{subject}"\ninfographic_style: "{style}"\n{visual_profile}',
        encoding="utf-8",
    )
    (tmp_path / "素材" / "infographic" / "analysis.md").write_text(
        f"route: {subject}\nstyle: {style}\n", encoding="utf-8"
    )
    (tmp_path / "素材" / "infographic" / "structured-content.md").write_text(
        f"style: {style}\n", encoding="utf-8"
    )
    specs = [
        ("infographic-01.png", 576, 1024, "01.md"),
        ("infographic-02.png", 1024, 576, "02.md"),
        ("infographic-03.png", 1024, 576, "03.md"),
        ("infographic-04.png", 576, 1024, "04.md"),
    ]
    images = []
    logs = []
    recipe_name = {
        "claymation": "warm-light-clay",
        "morandi-journal": "morandi-journal",
    }.get(style, "")
    recipe = pipeline._visual_recipe(recipe_name) if recipe_name else {}
    for name, w, h, prompt_name in specs:
        rel = f"素材/{name}"
        _png(tmp_path / rel, w, h)
        prompt_path = tmp_path / "素材" / "prompts" / "final" / prompt_name
        if style == "claymation":
            prompt_text = (
                f"---\n"
                f"style: {style}\n"
                f"visual_profile: {recipe['name']}\n"
                f"visual_profile_sha256: {recipe['sha256']}\n"
                f"palette_background: \"{recipe['background']}\"\n"
                f"palette_accent: \"{recipe['accent']}\"\n"
                f"---\n"
                "Warm beige background, light palette, matte clay, diffuse light.\n"
            )
        elif style == "morandi-journal":
            prompt_text = (
                f"---\n"
                f"style: {style}\n"
                f"visual_profile: {recipe['name']}\n"
                f"visual_profile_sha256: {recipe['sha256']}\n"
                f"palette_background: \"{recipe['background']}\"\n"
                f"palette_accent: \"{recipe['accent']}\"\n"
                f"---\n"
                "Warm Morandi hand-drawn doodle, restrained washi tape, "
                "clean-sketch bullet journal.\n"
            )
        else:
            prompt_text = f"---\nstyle: {style}\n---\n"
        prompt_path.write_text(prompt_text, encoding="utf-8")
        images.append({"path": rel, "aspect": "9:16" if h > w else "16:9", "bytes": (tmp_path / rel).stat().st_size, "style": style})
        logs.append({
            "schema_version": 2,
            "record_id": f"rec-{prompt_name}",
            "stage": "infographic",
            "producer": "sansheng-write.visual-planner",
            "tool": "sansheng-write.visual-planner",
            "output": rel,
            "output_sha256": hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest(),
            "prompt": f"素材/prompts/final/{prompt_name}",
            "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
            "renderer": "imagegen",
            "model": "test-model",
            "visual_profile": recipe.get("name", ""),
            "visual_profile_sha256": recipe.get("sha256", ""),
            "cmd": f"sansheng-write.visual-planner --style {style} 素材/prompts/final/{prompt_name}",
        })
    (tmp_path / "素材" / "infographic" / "final-set.json").write_text(
        json.dumps({"images": images}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def _enable_warm_light_profile(article: Path) -> None:
    meta = article / "article-meta.yaml"
    text = meta.read_text(encoding="utf-8")
    if "visual_profile:" not in text:
        meta.write_text(
            text + 'visual_profile: "warm-light-clay"\n',
            encoding="utf-8",
        )


def test_ai_product_subject_requires_claymation(tmp_path):
    article = _minimal_visual_article(tmp_path, subject="ai-product", style="morandi-journal")
    errors = pipeline._visual_route_errors(article)
    assert any("ai-product" in e and "claymation" in e for e in errors), errors


def test_final_assets_must_match_meta_latest_log_and_prompt(tmp_path):
    article = _minimal_visual_article(tmp_path)
    log_path = article / ".gen-log.jsonl"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "schema_version": 2,
            "record_id": "rec-bad",
            "stage": "infographic",
            "producer": "sansheng-write.visual-planner",
            "tool": "sansheng-write.visual-planner",
            "output": "素材/infographic-03.png",
            "output_sha256": hashlib.sha256((article / "素材/infographic-03.png").read_bytes()).hexdigest(),
            "prompt": "素材/prompts/final/03.md",
            "prompt_sha256": hashlib.sha256((article / "素材/prompts/final/03.md").read_bytes()).hexdigest(),
            "renderer": "imagegen",
            "model": "test-model",
            "cmd": "sansheng-write.visual-planner --style morandi-journal 素材/prompts/final/03.md",
        }, ensure_ascii=False) + "\n")
    errors = pipeline._visual_route_errors(article)
    assert any("infographic-03.png" in e and "claymation" in e for e in errors), errors


def test_visual_route_compliant_bundle_passes(tmp_path):
    article = _minimal_visual_article(tmp_path)
    assert pipeline._visual_route_errors(article) == []


def test_morandi_route_rejects_prompt_that_only_names_style(tmp_path):
    article = _minimal_visual_article(
        tmp_path,
        subject="phenomenon",
        style="morandi-journal",
    )
    prompt = article / "素材" / "prompts" / "final" / "01.md"
    prompt.write_text(
        "---\nstyle: morandi-journal\n---\n"
        "Muted pastel tactile editorial paper collage.\n",
        encoding="utf-8",
    )
    logs = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    logs[0]["prompt_sha256"] = hashlib.sha256(prompt.read_bytes()).hexdigest()
    (article / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in logs) + "\n",
        encoding="utf-8",
    )

    errors = pipeline._visual_route_errors(article)

    assert any("视觉配方" in error or "关键词组" in error for error in errors), errors


def test_structured_renderer_style_does_not_require_legacy_cli_flag():
    record = {
        "tool": pipeline.VISUAL_PRODUCER,
        "style": "morandi-journal",
        "cmd": "baoyu-image-gen --batchfile <sealed-attempt> --json",
    }

    assert pipeline._infographic_style_error(record) == ""


def test_renderer_style_still_blocks_unapproved_value():
    record = {
        "tool": pipeline.VISUAL_PRODUCER,
        "style": "cyberpunk",
        "cmd": "baoyu-image-gen --batchfile <sealed-attempt> --json",
    }

    assert "cyberpunk" in pipeline._infographic_style_error(record)


def test_publish_preflight_requires_visual_qa_record(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _png(article / "素材" / "cover.png", 1024, 436)
    _png(article / "素材" / "hero.png", 1024, 1024)
    (article / "定稿.md").write_text("正文", encoding="utf-8")
    (article / "定稿.html").write_text("<html><body>正文</body></html>", encoding="utf-8")
    errors = pipeline._pre_publish_errors(article)
    assert any("_visual-qa.json" in e for e in errors), errors


def test_visual_qa_markdown_cannot_authorize_release(tmp_path):
    article = _minimal_visual_article(tmp_path)
    (article / "_visual-qa.md").write_text("# 视觉验收记录\n通过\n", encoding="utf-8")
    errors = pipeline._visual_qa_errors(article)
    assert any("_visual-qa.json" in e for e in errors), errors


def test_warm_light_profile_rejects_article_79_style_dark_prompt(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _enable_warm_light_profile(article)
    prompt = article / "素材" / "prompts" / "final" / "01.md"
    prompt.write_text(
        """---
style: claymation
---
Deep charcoal studio background, muted steel blue panels, brick red and
mustard yellow accents, metallic clay figures, cinematic high contrast.
""",
        encoding="utf-8",
    )
    logs = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    logs[0]["prompt_sha256"] = hashlib.sha256(prompt.read_bytes()).hexdigest()
    (article / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )

    errors = pipeline._visual_route_errors(article)

    assert any("视觉配方" in error or "禁用色" in error for error in errors), errors


def test_claymation_requires_explicit_visual_profile_in_article_meta(tmp_path):
    article = _minimal_visual_article(tmp_path)
    meta = article / "article-meta.yaml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            'visual_profile: "warm-light-clay"\n',
            "",
        ),
        encoding="utf-8",
    )

    errors = pipeline._visual_route_errors(article)

    assert any("article-meta.yaml" in error and "visual_profile" in error for error in errors), errors


def test_cmd_log_blocks_dark_prompt_before_it_enters_evidence_chain(tmp_path):
    article = _minimal_visual_article(tmp_path)
    prompt = article / "素材" / "prompts" / "final" / "01.md"
    prompt.write_text(
        "---\nstyle: claymation\n---\n"
        "Deep charcoal background, steel blue, brick red, metallic, high contrast.\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_log(
            "infographic",
            "sansheng-write.visual-planner",
            article,
            output="素材/infographic-01.png",
            prompt="素材/prompts/final/01.md",
            renderer="imagegen",
            model="test-model",
        )

    assert exc.value.code == 2


def test_warm_light_profile_rejects_stale_gen_log_profile_hash(tmp_path):
    article = _minimal_visual_article(tmp_path)
    logs = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    logs[0]["visual_profile_sha256"] = "stale"
    (article / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )

    errors = pipeline._visual_route_errors(article)

    assert any("gen-log 视觉配方" in error and "infographic-01.png" in error for error in errors), errors


def test_warm_light_profile_rejects_dark_infographic_pixels(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _enable_warm_light_profile(article)
    output = article / "素材" / "infographic-01.png"
    Image.new("RGB", (576, 1024), (32, 36, 40)).save(output)
    logs = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    logs[0]["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (article / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )

    errors = pipeline._visual_route_errors(article)

    assert any("infographic-01.png" in error and "暗部" in error for error in errors), errors


def test_warm_light_profile_applies_same_tone_gate_to_hero(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _enable_warm_light_profile(article)
    Image.new("RGB", (1024, 1024), (20, 24, 28)).save(article / "素材" / "hero.png")

    errors = pipeline._visual_route_errors(article)

    assert any("hero.png" in error and "暗部" in error for error in errors), errors


def test_visual_qa_markdown_checkboxes_are_not_structured_evidence(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _enable_warm_light_profile(article)
    (article / "_visual-qa.md").write_text(
        """# 视觉验收记录
- [x] 封面主标题
- [x] 封面杂字
- [x] 封面裁切
- [x] 信息图统一
- [x] 图 1
- [x] 图 2
- [x] 图 3
- [x] 图 4 逐字核对
结论：通过
""",
        encoding="utf-8",
    )

    errors = pipeline._visual_qa_errors(article)

    assert any("_visual-qa.json" in error for error in errors), errors


def test_visual_contract_command_prints_canonical_prompt_block(tmp_path, capsys):
    article = _minimal_visual_article(tmp_path)

    pipeline.cmd_visual_contract(article)

    output = capsys.readouterr().out
    recipe = pipeline._visual_recipe("warm-light-clay")
    assert "visual_profile: warm-light-clay" in output
    assert f"visual_profile_sha256: {recipe['sha256']}" in output
    assert 'palette_background: "#F5F0E6"' in output
    assert 'palette_accent: "#2F6F8F"' in output


def test_visual_contract_command_rejects_unknown_explicit_profile(tmp_path):
    article = _minimal_visual_article(tmp_path)
    meta = article / "article-meta.yaml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            "warm-light-clay",
            "unknown-clay",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_visual_contract(article)

    assert "无法解析" in str(exc.value)


def test_gen_log_records_host_skill_extend_and_visual_profile(tmp_path):
    article = _minimal_visual_article(tmp_path)
    recipe = pipeline._visual_recipe("warm-light-clay")
    hero = article / "素材" / "hero.png"
    _png(hero, 1024, 1024)
    prompt = article / "素材" / "prompts" / "final" / "hero.md"
    prompt.write_text(
        (
            "---\n"
            "style: claymation\n"
            "visual_profile: warm-light-clay\n"
            f"visual_profile_sha256: {recipe['sha256']}\n"
            'palette_background: "#F5F0E6"\n'
            'palette_accent: "#2F6F8F"\n'
            "---\n"
            "Warm beige background, light palette, matte clay, diffuse light.\n"
        ),
        encoding="utf-8",
    )

    pipeline.cmd_log(
        "hero",
        "gen_img",
        article,
        output="素材/hero.png",
        prompt="素材/prompts/final/hero.md",
        renderer="gen_img",
        model="test-model",
        host_agent="codex",
        extend_sha256="abc123",
    )

    record = json.loads((article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["host_agent"] == "codex"
    assert record["orchestrator_skill"] == "sansheng-write"
    assert record["extend_sha256"] == "abc123"
    assert record["visual_profile"] == "warm-light-clay"
    assert record["visual_profile_sha256"] == recipe["sha256"]


def test_reference_declares_product_axis_precedence_and_refined_cover_cap():
    root = Path(__file__).resolve().parents[1]
    routing = (root / "references" / "image-routing.md").read_text(encoding="utf-8")
    cover = (root / "references" / "cover-styles.md").read_text(encoding="utf-8")
    assert "产品/模型轴优先于趋势结论" in routing
    assert "标题块总高度上限" in cover
    assert "禁止把 `largest` / `extra-black`" in cover


def test_reviewed_template_compositor_is_an_allowed_pixel_renderer():
    assert (
        "deterministic-template-compositor"
        in pipeline.IMAGE_RENDERER_WHITELIST
    )
