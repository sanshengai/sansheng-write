# -*- coding: utf-8 -*-
"""独立视觉复核适配器 + 后处理留痕 + 列表 URL 排版的回归测试。

用例全部来自接上视觉闸那天踩到的坑，每条对应一次真实的静默失败：

1. **提示词根本没送到复核模型**：Windows 上 codex 入口是 codex.cmd，批处理 shim
   转发 %* 时吃掉了多行参数。模型只收到图片，于是自说自话地全判通过 ——
   闸门被架空却不报错。改走 stdin 后修复。
2. **看图模型把糊字脑补成通顺句子**：hero 图实际渲成「重置不是祸利，是昀家公司
   付溻针」，复核仍判 text_match 通过。靠「逐字辨认 + 认不出写 □ + 禁止补全」修复。
3. **转写被打碎导致好图被误杀**：两行标签被拆成 ['Codex', '主动补发 20 次']，
   下游按拼接串做子串匹配就找不到「Codex 主动补发 20 次」。
4. **负面清单压不住第二色相**：只写 Avoid brick red 时，凡「两组对照」题材模型
   必然自造一个对比色。改成正面清单 + 明确给出替代区分手段。
5. **后处理改了字节却没留痕**：add_logo/compress 之后，render-visuals --only
   再也无法沿用未重渲的图，等于把补渲单张的能力废掉。
6. **➤ 列表缺 word-break**：要点卡早就加了，列表漏了，「信息来源」里的网址把
   整行拉散且读者选不中。
"""
import hashlib
import json
from pathlib import Path

from scripts import compress_images, format_layout, visual_qa_codex, visual_workflow


# ---------- ① 复核模型的输出契约 ----------

def test_schema_requires_evidence_and_exact_checks():
    checks = ["text_match", "crop_safe"]
    schema = visual_qa_codex._build_schema(checks)
    evidence = schema["properties"]["visual_evidence"]
    # 空数组曾被判合法 —— 模型交一份「格式对但什么都没看」的结论就能过。
    assert evidence["minItems"] == 1
    assert schema["properties"]["checks"]["required"] == checks
    assert schema["properties"]["checks"]["additionalProperties"] is False
    for key in ("observed_text", "observed_layout", "visual_evidence", "checks", "notes"):
        assert key in schema["required"]


def test_default_reviewer_is_not_an_image_model():
    """复核模型撞上生图模型，视觉闸就等于自己给自己发合格证。"""
    assert "gemini" not in visual_qa_codex.DEFAULT_MODEL
    assert "image" not in visual_qa_codex.DEFAULT_MODEL


# ---------- ② 转写纪律（防脑补 / 防打碎） ----------

def _prompt() -> str:
    return visual_qa_codex._build_prompt(
        {
            "path": "素材/x.png",
            "stage": "infographic",
            "target_style": "claymation",
            "expected_text": ["它能回答什么"],
            "required_checks": list(visual_qa_codex.CHECK_DEFINITIONS),
            "pixel_metrics": {"width": 1024, "height": 1024},
            "style_contract": {
                "layout": "grid",
                "palette": {"background": "#F5F0E6", "accent": "#0E926F", "neutrals": []},
                "required_visual_traits": ["one dominant object"],
                "forbidden_visual_traits": ["neon"],
            },
        }
    )


def test_prompt_forbids_charitable_completion():
    text = _prompt()
    assert "逐字辨认" in text
    assert "不许补全" in text
    assert "□" in text
    # 顺序很关键：先转写再对白名单，反了就会被白名单牵着走。
    assert "先转写、再回头对白名单" in text


def test_prompt_requires_block_level_transcription():
    text = _prompt()
    assert "按「块」转写" in text
    # 反例必须写进提示词 —— 只讲规则时模型照样按「先写完所有第一行」的方式拆。
    assert "'Codex', 'Claude'" in text or "Codex', 'Claude" in text


def test_whitelist_is_declared_as_upper_and_lower_bound():
    text = _prompt()
    assert "文字白名单" in text
    # 产品名 / 署名出现在白名单里时不算违禁，否则封面永远过不了。
    assert "不是违规" in text


def test_watermark_excluded_from_crop_safe():
    """署名由脚本按固定 2% 内边距叠加，位置既定；算进裁切风险会让闸门永远无法通过。"""
    assert "2%" in visual_qa_codex.CHECK_DEFINITIONS["crop_safe"]


def test_palette_check_separates_design_elements_from_materials():
    text = visual_qa_codex.CHECK_DEFINITIONS["brand_palette_match"]
    assert "设计元素" in text
    assert "肤色" in text  # 黏土人偶的肉色是配方允许的，不该被判违规


# ---------- ③ 生图侧：正面色板 + 字形准确 ----------

def test_clay_palette_keeps_recipe_keywords_verbatim():
    """visual_route 门是逐字子串比对，写同义表述过不了，而改 prompt 要整批重渲。"""
    palette = visual_workflow._clay_palette(
        {"background": "#F5F0E6", "accent": "#0E926F", "neutrals": ["#FBF8F2"]}
    )
    # 与 pipeline.py::_visual_route_errors 同口径：它比对的是 body.lower()。
    body = palette.lower()
    for phrase in ("warm ivory", "high-key pastel palette", "pale pastel jade", "soft clay", "diffuse light"):
        assert phrase in body, phrase


def test_clay_palette_offers_an_alternative_to_a_second_hue():
    palette = visual_workflow._clay_palette({})
    # 钉行为不钉措辞：必须**给出替代手段**，而不是必须出现某句禁令。
    # 2026-08-15 起禁令式表述已改成正面描述（扩散模型对否定式基本不敏感），
    # 原来断言字面串 "SECOND HUE" 的写法会把「改进措辞」误判成「破坏契约」，
    # 正是 prompt 只增不减、一路膨胀到 5000 字符的机制之一。
    assert "same jade" in palette, "必须约束在单一色相内"
    for alternative in ("tints", "shape", "size", "texture", "position"):
        assert alternative in palette, f"缺少区分两组的替代手段：{alternative}"


def test_infographic_prompt_demands_character_accuracy():
    prompt = visual_workflow._infographic_prompt(
        {"title": "标题", "labels": ["甲", "乙"], "template_id": "t", "aspect_ratio": "16:9"},
        "claymation",
        {"name": "warm-light-clay", "sha256": "x", "background": "#F5F0E6", "accent": "#0E926F"},
    )
    assert "CHARACTER ACCURACY IS CRITICAL" in prompt


def test_clay_typography_is_dimensional_and_scene_integrated():
    contract = visual_workflow._clay_typography()
    assert "extruded clay letters" in contract
    assert "dimensional rounded clay text" in contract
    assert "embedded in the clay scene" in contract
    # 钉正面契约：字必须是「立体黏土实体」。原来钉的是禁令串
    # "flat printed business typography"，2026-08-15 起改成正面表述
    # （模型对否定式不敏感）—— 钉措辞会把改进误判成破坏。
    assert "sculpted as extruded clay letters" in contract
    # 语义不变（大部分标签不要底板），措辞由 "at least half of all labels …
    # with NO backing plate, box, ribbon, banner or card" 改成正面的
    # "stand free … with open background around them"。
    assert "most labels stand free" in contract


def test_visual_reviewer_has_a_separate_typography_gate():
    text = visual_qa_codex.CHECK_DEFINITIONS["typography_contract_match"]
    assert "立体" in text
    assert "平面印刷黑体" in text
    assert "大多数文字都有底板" in text


def test_palette_gate_rejects_dark_green_even_when_hue_is_allowed():
    text = visual_qa_codex.CHECK_DEFINITIONS["brand_palette_match"]
    assert "大标题" in text
    assert "深绿" in text
    assert "最深色只允许" in text


def test_visual_evidence_must_copy_every_trait_verbatim():
    text = _prompt()
    assert "逐条覆盖 required_visual_traits" in text
    assert "trait 字段原样复制" in text


# ---------- ④ 后处理留痕 ----------

def _write_log(article: Path, output: str, sha: str) -> None:
    (article / ".gen-log.jsonl").write_text(
        json.dumps({"output": output, "output_sha256": sha, "renderer": "gen_img"}) + "\n",
        encoding="utf-8",
    )


def test_stamp_records_drift_and_keeps_provenance(tmp_path):
    article = tmp_path / "art"
    (article / "素材").mkdir(parents=True)
    img = article / "素材" / "a.png"
    img.write_bytes(b"generated")
    _write_log(article, "素材/a.png", hashlib.sha256(b"generated").hexdigest())

    img.write_bytes(b"watermarked-and-compressed")  # 模拟 add_logo + compress
    assert compress_images.stamp_gen_log([img], verbose=False) == 1

    last = json.loads((article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert last["output_sha256"] == hashlib.sha256(b"watermarked-and-compressed").hexdigest()
    assert last["renderer"] == "gen_img"  # 出身信息必须带过来，否则收据会缺字段
    assert last["post_process"]["source_sha256"] == hashlib.sha256(b"generated").hexdigest()


def test_stamp_is_idempotent_when_bytes_unchanged(tmp_path):
    article = tmp_path / "art"
    (article / "素材").mkdir(parents=True)
    img = article / "素材" / "a.png"
    img.write_bytes(b"same")
    _write_log(article, "素材/a.png", hashlib.sha256(b"same").hexdigest())
    assert compress_images.stamp_gen_log([img], verbose=False) == 0


def test_stamp_refuses_images_without_provenance(tmp_path):
    """没有原始生成记录的图本来就来历不明 —— 补记等于替它伪造出身。"""
    article = tmp_path / "art"
    (article / "素材").mkdir(parents=True)
    img = article / "素材" / "orphan.png"
    img.write_bytes(b"who-made-you")
    _write_log(article, "素材/other.png", "deadbeef")
    assert compress_images.stamp_gen_log([img], verbose=False) == 0


# ---------- ⑤ 列表里的长 URL ----------

def test_list_rows_carry_word_break():
    html = format_layout.process_lists(
        '<ul class="ul"><li>某某公开档案 · example.com/tools/some-long-path</li></ul>'
        '<ol class="ol"><li>第一步</li></ol>'
    )
    body = html[0] if isinstance(html, tuple) else html
    # 两种列表都要有：微信会对含超长 token 的行做两端对齐，把中文撑成大字间距。
    assert body.count("word-break:break-all") >= 2
