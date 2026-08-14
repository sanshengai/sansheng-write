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
                "layout_type": "linear-progression",
                "layout": "structured-card",
                "anchor": "# 教程 | 视觉合同",
                "expected_text": ["作者定稿", "任务单"],
                "facts": ["定稿哈希绑定任务单"],
            },
            {
                "id": "02",
                "position": "middle",
                "aspect_ratio": "16:9",
                "title": "再编译规则",
                "layout_type": "binary-comparison",
                "layout": "comparison",
                "anchor": "中段锚点一",
                "expected_text": ["业务规则", "像素渲染"],
                "facts": ["业务规则归 write", "渲染器可替换"],
            },
            {
                "id": "03",
                "position": "middle",
                "aspect_ratio": "16:9",
                "title": "三道关卡",
                "layout_type": "hub-spoke",
                "layout": "flow",
                "anchor": "中段锚点二",
                "expected_text": ["预检", "推送", "读回"],
                "facts": ["三步必须由一个命令完成"],
            },
            {
                "id": "04",
                "position": "closing",
                "aspect_ratio": "9:16",
                "title": "草稿箱交付",
                "layout_type": "winding-roadmap",
                "layout": "checklist",
                "anchor": "结尾锚点",
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
        "---\n\n# 教程 | 视觉合同\n\n"
        + "正文段落。\n" * 20
        + "中段锚点一\n\n"
        + "正文段落。\n" * 20
        + "中段锚点二\n\n"
        + "正文段落。\n" * 20
        + "结尾锚点\n",
        encoding="utf-8",
    )
    (article / "article-meta.yaml").write_text(
        'title: "教程 | 视觉合同"\n'
        'digest: "一份稳定的视觉发布合同。"\n'
        'cover_style: "montage-evidence"\n'
        "lead:\n"
        '  line1: "规则不能丢"\n'
        '  line2: "弱模型也能稳"\n'
        '  accent: "也能稳"\n'
        '  subtitle: "确定性视觉合同"\n'
        '  tag1: "规则内建"\n'
        '  tag2: "独立验收"\n'
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


def test_cover_prompt_ban_allows_only_the_exact_legacy_negative_clause():
    from scripts.evidence import cover_prompt_banned_terms

    legacy = (
        "No extra words, logos, watermarks, fake UI, dark technology background, "
        "neon, extra-black or ultra-black type."
    )

    assert cover_prompt_banned_terms(legacy) == []
    assert cover_prompt_banned_terms("Use extra-black type.") == ["extra-black"]


def test_visual_plan_requires_four_images_and_unique_ids():
    from scripts.visual_workflow import validate_visual_plan

    plan = _plan()
    plan["infographics"] = plan["infographics"][:3]
    plan["infographics"][1]["id"] = "01"

    errors = validate_visual_plan(plan)

    assert any("至少 4 张" in error for error in errors)
    assert any("id 必须唯一" in error for error in errors)


def test_visual_plan_requires_a_unique_author_text_anchor_for_each_slot():
    from scripts.visual_workflow import validate_visual_plan

    plan = _plan()
    plan["infographics"][0].pop("anchor")

    errors = validate_visual_plan(plan)

    assert any("anchor" in error for error in errors)


def test_visual_plan_rejects_suspicious_double_character_typo_clusters():
    from scripts.visual_workflow import validate_visual_plan

    plan = _plan()
    plan["infographics"][2]["expected_text"][0] = (
        "重履约网络轻轻装装修，先找重复订单"
    )

    errors = validate_visual_plan(plan)

    assert any("疑似重复字" in error for error in errors)


def test_shipped_visual_plan_template_satisfies_current_contract():
    from scripts.visual_workflow import validate_visual_plan

    root = Path(__file__).resolve().parents[1]
    plan = json.loads(
        (root / "templates" / "visual-plan.template.json").read_text(
            encoding="utf-8"
        )
    )

    assert validate_visual_plan(plan) == []


def test_cover_text_contract_uses_exact_five_fields_and_rejects_drift():
    from scripts.visual_contracts import cover_text_contract

    meta = {
        "lead": {
            "line1": "规则不能丢",
            "line2": "弱模型也能稳",
            "accent": "也能稳",
            "subtitle": "文章导读不进封面",
            "tag1": "硬门",
            "tag2": "证据链",
        }
    }
    contract, errors = cover_text_contract(meta)
    assert errors == []
    assert contract["tags"] == ["硬门", "证据链"]
    assert "文章导读不进封面" not in contract["tags"]

    meta["lead"]["accent"] = "弱模型"
    meta["lead"].pop("tag2")
    _, errors = cover_text_contract(meta)
    assert any("line2 的结尾子串" in error for error in errors)
    assert any("lead.tag2 不能为空" in error for error in errors)


def test_compiler_injects_contract_and_builds_baoyu_batch(tmp_path):
    from scripts.profile_config import visual_profile
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    result, errors = compile_visual_plan(article)

    assert errors == []
    assert result["producer"] == PRODUCER
    cover = (article / "素材/prompts/final/cover.md").read_text(encoding="utf-8")
    hero = (article / "素材/prompts/final/hero.md").read_text(encoding="utf-8")
    info = (article / "素材/prompts/final/infographic-01.md").read_text(
        encoding="utf-8"
    )
    assert f'producer: "{PRODUCER}"' in cover
    # 🔴 封面走自建 montage-evidence 签名视觉，刻意不接 baoyu-cover-image
    # （2026-08-02 复核定案）：声明一个明确不使用的依赖，只会让
    # producer_chain 退化成不可验证的空标签。
    assert 'producer_chain: ["sansheng-write.visual-planner"]' in cover
    assert "baoyu-cover-image" not in cover
    assert 'aspect_ratio: "2.35:1"' in cover
    assert "Canvas base MUST be the exact deep-charcoal color #0E0E10" in cover
    assert "only visible accent hue is exactly #2F6F8F" in cover
    assert "slightly larger left zone" in cover
    assert "slightly smaller right zone" in cover
    assert "narrow quiet gutter" in cover
    assert "Do not render ghost words" in cover
    assert "CONDITION × SIGNAL × LEVER" not in cover
    assert any(
        "purely pictorial low-contrast background" in trait
        for trait in visual_profile("montage-evidence")["required_visual_traits"]
    )
    assert "ONLY VISIBLE TEXT ALLOWLIST" in cover
    assert "Never render layout guides, measurements or percentages" in cover
    assert "Main Chinese headline: 规则不能丢" in cover
    assert "Supporting Chinese subtitle: 弱模型也能稳" in cover
    # 🔴 钉的是「字号必须锚在画布上」这条契约本身，不是措辞。
    # 旧版只说 L1 是 100% scale，没有画布锚点，模型可自由决定 L1 多大 ——
    # 实测同一份提示词跑出过 L1 占画布高 8% 和 12% 两种结果（前者主标题比
    # 整张封面失去视觉主体）。这条断言防止锚点被改回相对值。
    assert "cap height MUST be 12%-14% of the canvas height" in cover
    assert "supporting subtitle is 58%-64% of the headline cap height" in cover
    # 主题色只染 L2，L1 靠字号称王 —— 防止「两行都染 / 主标题染色」回潮。
    assert "Never colour any part of the main headline" in cover
    # 🔴 品牌胶囊：主题色 78%-85% + 哑光磨砂。满色 100% 会跟 L1 争焦点。
    assert "78%-85% opacity" in cover
    assert "FLAT MATTE frosted body" in cover
    # 「磨砂」与「毛玻璃」必须泾渭分明——合并掉就会渲成廉价玻璃按钮
    assert "NOT glassmorphism" in cover
    assert "glassmorphism" in cover.split("STRICT FORBIDDEN")[1]
    assert "no specular highlight" in cover
    assert "Render exactly the two allowlisted tags" in cover
    assert "Descriptor tags: 规则内建 / 独立验收" in cover
    assert "确定性视觉合同" not in cover
    assert "一份任务单" in cover
    assert "一条发布入口" in cover
    assert "TEXTLESS visual evidence only" in cover
    for prompt in (cover, hero, info):
        assert "ONE-PASS NATIVE RASTER CONTRACT" in prompt
        assert "Never output, request or rely on SVG, HTML, Canvas" in prompt
        assert "do not separate the words from the picture" in prompt
    assert "same dimensional matte-clay material" in hero
    assert "same dimensional matte-clay material" in info
    assert "bright editorial evidence montage" not in cover
    assert "extra-black" not in cover.casefold()
    assert "ultra-black" not in cover.casefold()
    assert 'visual_profile: "warm-light-clay"' in info
    assert 'producer_chain: ["sansheng-write.visual-planner"]' in info
    assert 'method_sources: ["baoyu-infographic"]' in info
    assert "visual_profile_sha256:" in info
    assert "palette_background:" in info
    assert "作者定稿" in info and "任务单" in info
    assert "extruded clay letters" in info
    assert "embedded in the clay scene" in info
    assert "handwritten editorial marker" not in info
    assert "brush-pen character" not in info
    assert 'template_id:' not in info
    assert "reviewed editorial composition contract" in info
    assert "定稿哈希绑定任务单" not in info
    batch = json.loads(
        (article / "素材/render-batch.json").read_text(encoding="utf-8")
    )
    assert batch["jobs"] == 1
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


def test_svg_converter_rejects_formal_generated_visual_slots(tmp_path, monkeypatch):
    from scripts import svg_to_png

    source = tmp_path / "diagram.svg"
    source.write_text(
        '<svg viewBox="0 0 10 10"><text x="1" y="5">补字</text></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["svg_to_png.py", str(source), "--output", str(tmp_path / "infographic-01.png")],
    )

    assert svg_to_png.main() == 2
    assert not (tmp_path / "infographic-01.png").exists()


def test_visual_prompt_rejects_clay_style_conflict_phrase(tmp_path):
    from scripts.profile_config import visual_profile
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    _, compile_errors = compile_visual_plan(article)
    assert compile_errors == []
    prompt = (article / "素材/prompts/final/hero.md").read_text(encoding="utf-8")
    prompt += "\nThis is not cartoonish.\n"
    recipe = visual_profile("warm-light-clay")
    recipe["sha256"] = pipeline._visual_recipe("warm-light-clay")["sha256"]

    errors = pipeline._visual_prompt_errors(prompt, recipe, "hero")

    assert any("视觉风格冲突短语" in error for error in errors)


def test_morandi_route_is_retired(tmp_path):
    """morandi-journal 不再可路由：全站统一粘土风。

    配方本身仍封存在 profile 的 visual.profiles 里（想切回来只需改回这里的映射），
    但 meta 写 morandi-journal 必须被编译器直接拒绝，不能再产出 prompt。
    """
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    meta = article / "article-meta.yaml"
    text = meta.read_text(encoding="utf-8")
    text = text.replace('infographic_style: "claymation"', 'infographic_style: "morandi-journal"')
    text = text.replace('visual_profile: "warm-light-clay"', 'visual_profile: ""')
    meta.write_text(text, encoding="utf-8")

    _, errors = compile_visual_plan(article)

    assert any("claymation" in e for e in errors), errors


def test_clay_compiler_embeds_full_style_contract(tmp_path):
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    _, errors = compile_visual_plan(article)

    assert errors == []
    prompt = (article / "素材/prompts/final/infographic-01.md").read_text(
        encoding="utf-8"
    )
    assert 'visual_profile: "warm-light-clay"' in prompt
    assert "visual_profile_sha256:" in prompt
    assert "#F7F2E9" in prompt
    assert 'visual_contract_owner: "sansheng-write"' in prompt
    assert 'visual_contract_revision: "warm-light-clay/2"' in prompt
    assert "Baoyu may choose content structure and layout" in prompt
    assert "never for large headings" in prompt
    assert "claymation" in prompt
    assert "VISIBLE TEXT ALLOWLIST" in prompt
    assert "SOURCE FACTS ARE NOT PROVIDED TO THE RENDERER" in prompt


def test_long_chinese_layout_is_rejected(tmp_path):
    """layout 里的中文散文会被模型照着画进图里，必须在编译前拦掉。

    实测（82-格拉德威尔五本书，同流水线同配方同模型）：layout 中文 0 字的两张一次
    成功；108 字那张连废 4 版，其中一版直接把 layout 里的「训练和比赛」画成了图上
    标签「训练与比赛」；158 字那张出乱码；181 字那张多画「污染」。
    """
    from scripts.visual_workflow import validate_visual_plan

    plan = json.loads((_article(tmp_path) / "visual-plan.json").read_text(encoding="utf-8"))
    plan["infographics"][0]["layout"] = (
        "从左上方的一条无日期、无刻度分组线起步，经由少年选拔、训练和比赛时间，"
        "向右下方的能力放大形成一条连续因果链；让冰球和训练场景承担叙事，"
        "不要画日历、钟表、计分牌、队服标识或通用卡片拼贴"
    )
    errors = validate_visual_plan(plan)
    assert any("layout" in e and "中文" in e for e in errors), errors

    # 历史上稳定跑完 100+ 篇的短中文标签照常放行
    plan["infographics"][0]["layout"] = "三段式因果对比"
    assert not [e for e in validate_visual_plan(plan) if "layout 含" in e]

    # 英文长描述无害：实测 538 字英文一次成功
    plan["infographics"][0]["layout"] = (
        "Use one clean S-shaped roadmap with exactly five text slots: the title once "
        "at the top and the four allowlisted labels once along the road. Every text "
        "slot holds exactly one allowlisted string, rendered as plain raised letters "
        "resting directly on the road surface."
    )
    assert not [e for e in validate_visual_plan(plan) if "layout 含" in e]


def test_hero_prompt_keeps_text_guards(tmp_path):
    from scripts.visual_workflow import compile_visual_plan

    article = _article(tmp_path)
    _, errors = compile_visual_plan(article)
    assert errors == []
    hero = (article / "素材/prompts/final/hero.md").read_text(encoding="utf-8")

    assert "VISIBLE TEXT ALLOWLIST" in hero
    assert 'producer_chain: ["sansheng-write.visual-planner"]' in hero
    assert 'method_sources: ["baoyu-article-illustrator"]' in hero
    assert "Use facts only as textless objects" in hero
    assert "Render this title EXACTLY ONCE" in hero
    assert "独立复核" not in hero


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
    assert "anchor=中段锚点一" in analysis


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


def test_release_markdown_assembly_is_idempotent_and_references_every_infographic(
    tmp_path,
):
    from scripts.assemble_release import assemble_release_markdown

    article = _article(tmp_path)
    draft = article / "定稿.md"
    draft.write_text(
        draft.read_text(encoding="utf-8")
        + "\n## 第一部分\n\n第一部分正文。\n"
        + "\n## 第二部分\n\n第二部分正文。\n"
        + "\n## 第三部分\n\n第三部分正文。\n",
        encoding="utf-8",
    )

    first, errors = assemble_release_markdown(article)
    second, second_errors = assemble_release_markdown(article)

    assert errors == []
    assert second_errors == []
    assert first["changed"] is True
    assert second["changed"] is False
    text = draft.read_text(encoding="utf-8")
    for item in _plan()["infographics"]:
        image = f"素材/infographic-{item['id']}.png"
        assert text.count(image) == 1
        assert text.count(f"SANSHENG-VISUAL-START:{item['id']}") == 1
        assert text.count(f"SANSHENG-VISUAL-END:{item['id']}") == 1
    assert text.index("infographic-01.png") > text.index("# 教程 | 视觉合同")
    assert text.index("infographic-04.png") > text.index("结尾锚点")


def test_release_markdown_assembly_removes_legacy_unsealed_infographic_refs(
    tmp_path,
):
    from scripts.assemble_release import assemble_release_markdown

    article = _article(tmp_path)
    draft = article / "定稿.md"
    draft.write_text(
        draft.read_text(encoding="utf-8")
        + "\n![旧图一](素材/infographic1.png)\n"
        + "\n![旧图二](素材/infographic-2.png)\n",
        encoding="utf-8",
    )

    _, errors = assemble_release_markdown(article)

    assert errors == []
    text = draft.read_text(encoding="utf-8")
    assert "素材/infographic1.png" not in text
    assert "素材/infographic-2.png" not in text
    assert text.count("素材/infographic-01.png") == 1
