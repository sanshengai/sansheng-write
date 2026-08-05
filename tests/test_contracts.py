from scripts.contracts import (
    validate_bundle, validate_output, ContractError, verify_infographic_set,
    verify_research_set, verify_content_enhance_set, verify_cover_set,
    verify_review_set,
)
import pytest
from PIL import Image

def test_bundle_requires_core_keys():
    with pytest.raises(ContractError):
        validate_bundle({"article_meta": {}})  # 缺 sansheng_context/iron_rules/stage_input

def test_bundle_passes_when_complete():
    b = {"sansheng_context": "x", "iron_rules": ["r1"], "article_meta": {}, "stage_input": {}}
    assert validate_bundle(b) is True

def test_output_schema_rejects_unknown_stage():
    with pytest.raises(ContractError):
        validate_output("no_such_stage", {})


# --- P2.1 research item 级结构契约（tier-1，仅 sources[].url 结构）---
# 契约只管结构：sources 每项 dict 且含非空 str url。
# findings item 结构（claim/support/confidence）、source 的 title/tier/accessed、
# 「版本类至少 1 条官网级 source」是 tier-2 语义关，由 P2.2 验证门强制，
# 不追溯历史冻结——故此处不加 findings item / source 其它字段用例。

def test_research_output_accepts_valid_payload():
    ok = {"findings": [{"claim": "x"}], "sources": [{"url": "https://x"}]}
    assert validate_output("research", ok) is True

def test_research_output_rejects_missing_toplevel_keys():
    # 既有顶层 schema 已覆盖，确认仍 raise（findings / sources 缺一即拒）
    with pytest.raises(ContractError):
        validate_output("research", {"sources": [{"url": "https://x"}]})  # 缺 findings
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [{"claim": "x"}]})       # 缺 sources

def test_research_sources_item_must_be_dict_with_nonempty_url():
    # sources 每项必须 dict 且含非空 str url
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [], "sources": [{}]})           # 缺 url
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [], "sources": [{"url": ""}]})  # 空 url
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [], "sources": [{"url": "   "}]})  # 纯空白
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [], "sources": ["https://x"]})  # 项非 dict
    with pytest.raises(ContractError):
        validate_output("research", {"findings": [], "sources": [{"url": 123}]})  # url 非 str

def test_research_findings_structural_only_no_item_schema():
    # findings 仅校验是 list（顶层）；其 item 结构属 tier-2 语义关，
    # 契约不查 —— 故 findings 项是裸 str / 缺 claim 也放行（不污染契约）。
    payload = {"findings": ["裸字符串结论", {}, {"claim": "x"}],
               "sources": [{"url": "https://x"}]}
    assert validate_output("research", payload) is True

# --- P3.1 content_enhance item 级结构契约（tier-1，仅 strategies 4 键非空 str）---
# 契约只管结构：strategies 必须 dict 且**含且仅认** 4 键
# angle/density/detail/texture，每个值为非空 str。
# 各策略文本质量/去重/不矛盾/与正文融合是 tier-2 语义关，由 P3.2 合并关/
# 语义门强制，不追溯历史冻结——故此处不加"文本质量/长度/语义"用例。

def test_content_enhance_output_accepts_valid_payload():
    ok = {"strategies": {
        "angle":   "原稿平铺直叙，改从读者最痛的那一刻切入",
        "density": "第 2 段三句车轱辘话压成一句，腾出篇幅给案例",
        "detail":  "把'某次失败'落到具体时间地点人物对话",
        "texture": "去掉书面连接词，换成口语化的短句节奏",
    }}
    assert validate_output("content_enhance", ok) is True

def test_content_enhance_rejects_strategies_not_dict():
    # 顶层 schema 已保证 strategies 是 dict，确认仍 raise
    with pytest.raises(ContractError):
        validate_output("content_enhance", {"strategies": ["angle"]})
    with pytest.raises(ContractError):
        validate_output("content_enhance", {"strategies": "angle/density"})
    with pytest.raises(ContractError):
        validate_output("content_enhance", {})  # 缺 strategies 顶层键

def test_content_enhance_rejects_missing_any_of_four_keys():
    base = {"angle": "a", "density": "b", "detail": "c", "texture": "d"}
    for miss in ("angle", "density", "detail", "texture"):
        bad = dict(base)
        del bad[miss]
        with pytest.raises(ContractError):
            validate_output("content_enhance", {"strategies": bad})

def test_content_enhance_rejects_empty_or_nonstr_values():
    base = {"angle": "a", "density": "b", "detail": "c", "texture": "d"}
    for k in ("angle", "density", "detail", "texture"):
        for badv in ("", "   ", 123, None, [], {"x": 1}):
            bad = dict(base)
            bad[k] = badv
            with pytest.raises(ContractError):
                validate_output("content_enhance", {"strategies": bad})

def test_content_enhance_rejects_extra_keys():
    # 含且仅认这 4 键：多余键即拒（防塞无契约语义的脏键）
    bad = {"angle": "a", "density": "b", "detail": "c", "texture": "d",
           "extra": "e"}
    with pytest.raises(ContractError):
        validate_output("content_enhance", {"strategies": bad})

def test_content_enhance_structural_only_no_text_quality_check():
    # 结构层不判文本质量/长度/套话：只要 4 键齐全 + 非空 str 即放行
    # （质量/去重/不矛盾/与正文融合归 P3.2 tier-2 合并关，契约不污染）
    payload = {"strategies": {
        "angle":   "啊",          # 单字、套话级别也放行（非结构问题）
        "density": "x" * 9999,    # 超长也放行（长度不属结构契约）
        "detail":  "TODO 待补",   # 占位文本也放行
        "texture": " 有前后空格但 strip 后非空 ",
    }}
    assert validate_output("content_enhance", payload) is True


# --- P4.1 cover item 级结构契约（tier-1，仅 candidates[].path + selected）---
# 契约只管结构：candidates 每项 dict 且含非空 str path；selected 非空 str。
# `selected ∈ candidates 路径`是**跨字段** = tier-2，由 P4.2 验证门强制；
# 图片实际存在/尺寸/1K 分辨率 也是 tier-2 语义关（近 3 篇回避规则 2026-05-22 已删），由 P4.2
# 验证门强制、不追溯历史冻结——故此处不加"selected∈candidates / 图存在 /
# 1K / 风格"用例（塞进结构契约会污染契约且与校验层级总纲自相矛盾）。

def test_cover_output_accepts_valid_payload():
    ok = {"candidates": [
              {"path": "素材/cover/candidates/cinematic.png",
               "style": "cinematic", "aspect": "2.35:1"},
              {"path": "素材/cover/candidates/editorial.png",
               "style": "editorial", "aspect": "2.35:1"}],
          "selected": "素材/cover/candidates/cinematic.png"}
    assert validate_output("cover", ok) is True

def test_cover_output_rejects_missing_toplevel_keys():
    # 既有顶层 schema 已覆盖，确认仍 raise（candidates / selected 缺一即拒）
    with pytest.raises(ContractError):
        validate_output("cover", {"selected": "素材/cover/a.png"})  # 缺 candidates
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{"path": "x"}]})   # 缺 selected

def test_cover_output_rejects_bad_toplevel_types():
    # candidates 必须 list、selected 必须 str（顶层 schema）
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": "x", "selected": "y"})
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{"path": "x"}], "selected": 123})

def test_cover_candidates_item_must_be_dict_with_nonempty_path():
    # candidates 每项必须 dict 且含非空 str path
    sel = "素材/cover/a.png"
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{}], "selected": sel})          # 缺 path
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{"path": ""}], "selected": sel})  # 空 path
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{"path": "   "}], "selected": sel})  # 纯空白
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": ["素材/cover/a.png"], "selected": sel})  # 项非 dict
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": [{"path": 123}], "selected": sel})  # path 非 str

def test_cover_selected_must_be_nonempty_str():
    cands = [{"path": "素材/cover/a.png"}]
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": cands, "selected": ""})     # 空 str
    with pytest.raises(ContractError):
        validate_output("cover", {"candidates": cands, "selected": "   "})  # 纯空白

def test_cover_structural_only_no_cross_field_or_image_check():
    # 结构层不判跨字段/图片业务：selected 不在 candidates 路径里、candidate
    # 缺 style/aspect、path 指向不存在文件 只要结构对就放行
    # （selected∈candidates / 图存在 / 1K / 风格 归 P4.2 tier-2，契约不污染）
    payload = {
        "candidates": [
            {"path": "素材/cover/不存在.png"},          # 缺 style/aspect、文件不存在
            {"path": "素材/cover/b.png", "style": "x"},  # 仅 path 是结构关注点
        ],
        "selected": "素材/cover/完全不在candidates里.png",  # 跨字段不属结构契约
    }
    assert validate_output("cover", payload) is True


# --- P5.1 review item 级结构契约（tier-1，仅 verdicts[] role/issues/pass）---
# 契约只管结构：verdicts 每项 dict，含非空 str `role`、list `issues`、
# **严格 bool** `pass`（排除 int —— isinstance(True,int)==True 陷阱，
# `pass` 是 Python 关键字，取值用 item["pass"] 不做属性名）。
# issues 内容质量 / role 是否合法审稿角色 / 裁决与正文一致性 / H2·段落
# delta 是 tier-2 语义关，由 P5.2 审稿 team 强制、不追溯历史冻结——
# 故此处不加"issues 质量 / role 合法性 / 裁决一致性"用例
# （塞进结构契约会污染契约且与校验层级总纲自相矛盾）。

def test_review_output_accepts_valid_payload():
    ok = {"verdicts": [
        {"role": "事实核查", "issues": ["第3段价格未标官网信源"], "pass": False},
        {"role": "调性审查", "issues": [], "pass": True},
    ]}
    assert validate_output("review", ok) is True

def test_review_output_rejects_missing_toplevel_key():
    # 既有顶层 schema 已覆盖，确认仍 raise（缺 verdicts / 类型错）
    with pytest.raises(ContractError):
        validate_output("review", {})                       # 缺 verdicts
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": "notalist"})  # 非 list

def test_review_verdict_item_must_be_dict():
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": ["裸字符串裁决"]})
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [123]})

def test_review_verdict_requires_role_nonempty_str():
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [{"issues": [], "pass": True}]})  # 缺 role
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": "", "issues": [], "pass": True}]})       # 空 role
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": "   ", "issues": [], "pass": True}]})     # 纯空白 role
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": 123, "issues": [], "pass": True}]})       # role 非 str

def test_review_verdict_requires_issues_list():
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": "事实核查", "pass": True}]})              # 缺 issues
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": "事实核查", "issues": "第3段问题", "pass": True}]})  # issues 非 list
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [
            {"role": "事实核查", "issues": {"x": 1}, "pass": True}]})    # issues 非 list

def test_review_verdict_pass_must_be_strict_bool_excluding_int():
    base = {"role": "事实核查", "issues": []}
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [dict(base)]})  # 缺 pass
    # 🪤 isinstance(True,int)==True：pass 收到 int 1/0 必须 raise（非 bool）
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [dict(base, **{"pass": 1})]})
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [dict(base, **{"pass": 0})]})
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [dict(base, **{"pass": "true"})]})
    with pytest.raises(ContractError):
        validate_output("review", {"verdicts": [dict(base, **{"pass": None})]})

def test_review_verdict_pass_accepts_true_and_false_bool():
    # 严格 bool 的 True / False 都合法（pass=False 是审稿不通过的正常态）
    assert validate_output("review", {"verdicts": [
        {"role": "铁律合规", "issues": ["出现尾部总结句"], "pass": False}]}) is True
    assert validate_output("review", {"verdicts": [
        {"role": "调性审查", "issues": [], "pass": True}]}) is True

def test_review_structural_only_no_semantic_check():
    # 结构层不判 issues 内容质量 / role 是否合法审稿角色 / pass=false 时
    # issues 是否非空（这些归 P5.2 审稿 team tier-2）：只要结构对就放行。
    payload = {"verdicts": [
        {"role": "随便什么角色名", "issues": [], "pass": False},  # pass=false 但 issues 空也放行
        {"role": "x", "issues": [1, 2, {"任意": "结构"}], "pass": True},  # issues 元素结构不查
    ]}
    assert validate_output("review", payload) is True


# --- P1.1 infographic item 级结构契约（tier-1，仅结构 + bool 排除）---
# 注意：契约只管结构（path/aspect 非空 str、bytes 严格 int 非 bool）。
# aspect 枚举(9:16/16:9/1:1) / ≥4 张 / ≤2MB 是 tier-2 语义关，由 P1.2
# 新产出验证门强制，不在结构契约里——故此处不加"aspect 必须三枚举"用例。

def test_infographic_output_validates_items():
    ok = {"images": [{"path": "素材/info1.png", "aspect": "9:16", "bytes": 1200}]}
    assert validate_output("infographic", ok) is True
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "x"}]})  # 缺 aspect/bytes

def test_infographic_bytes_rejects_bool_trap():
    # 🪤 isinstance(True, int) == True：bytes 收到 bool 必须 raise
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "x", "aspect": "9:16", "bytes": True}]})
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "x", "aspect": "9:16", "bytes": False}]})

def test_infographic_rejects_empty_strings_and_bad_types():
    # aspect/path 空串 → 结构层判失败（非空 str）
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "x", "aspect": "", "bytes": 10}]})
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "", "aspect": "9:16", "bytes": 10}]})
    # 项必须是 dict
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": ["素材/info1.png"]})
    # bytes 必须 int（不接受 str / float）
    with pytest.raises(ContractError):
        validate_output("infographic", {"images": [{"path": "x", "aspect": "9:16", "bytes": "1200"}]})

def test_infographic_structural_only_accepts_nonenum_aspect_and_zero_bytes():
    # 结构层不判业务范围：非三枚举的 aspect、bytes=0/负 只要类型对就放行
    # （枚举与尺寸范围归 P1.2 语义门，契约不污染）
    payload = {"images": [
        {"path": "素材/long.png", "aspect": "vertical-long", "bytes": 0},
        {"path": "素材/b.png", "aspect": "3:4", "bytes": -1},
    ]}
    assert validate_output("infographic", payload) is True


# ====================================================================
# P1.2 tier-2 新产出验证门：verify_infographic_set（不追溯历史 golden）
# 与 tier-1 结构契约 validate_output 分开，**不**塞进 _OUTPUT_SCHEMA。
# 用确定性合成 PNG fixture（按真实像素判 aspect/1K），≥4/构成/≤2MB/1K。
# ====================================================================

# 1K 长边目标 1024，容差带 [900,1200]：见 contracts.py verify_infographic_set
# 文档串。下方 fixture 长边统一用 1024（带内）。
_LONGEDGE = 1024


def _mk_png(path, w, h, color=(14, 146, 111)):
    """造一张确定性纯色 PNG。w/h 精确，verify 按真实像素判。"""
    Image.new("RGB", (w, h), color).save(str(path), "PNG", optimize=True)
    return {"path": str(path), "aspect": None, "bytes": path.stat().st_size}


def _dims_for(aspect, longedge=_LONGEDGE):
    """按目标 aspect 给出 (w,h)，长边=longedge（落在 1K 带内）。"""
    if aspect == "9:16":   # 竖图，长边=高
        return (round(longedge * 9 / 16), longedge)
    if aspect == "16:9":   # 横图，长边=宽
        return (longedge, round(longedge * 9 / 16))
    if aspect == "1:1":
        return (longedge, longedge)
    raise ValueError(aspect)


def _set(tmp_path, specs):
    """specs = [(name, aspect_or_dims), ...] → images list（aspect 由像素判）。
    aspect_or_dims 给字符串 → 按 _dims_for；给 (w,h) tuple → 原样。"""
    out = []
    for name, spec in specs:
        if isinstance(spec, tuple):
            w, h = spec
        else:
            w, h = _dims_for(spec)
        out.append(_mk_png(tmp_path / name, w, h))
    return out


@pytest.fixture
def compliant_set(tmp_path):
    """合规组：4 张 = 开篇 9:16 + 中间 16:9 ×2 + 结尾 9:16，均 1K、< 2MB。"""
    return _set(tmp_path, [
        ("01_open.png",  "9:16"),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])


def test_verify_infographic_set_compliant_returns_empty(compliant_set):
    assert verify_infographic_set(compliant_set) == []


def test_verify_infographic_set_count_below_4(tmp_path):
    imgs = _set(tmp_path, [
        ("01_open.png",  "9:16"),
        ("02_mid.png",   "16:9"),
        ("03_close.png", "9:16"),
    ])  # 仅 3 张
    reasons = verify_infographic_set(imgs)
    assert any("张数" in r or "count" in r.lower() for r in reasons)


def test_verify_infographic_set_bad_composition_opening_not_9_16(tmp_path):
    # 开篇是 16:9（应为 9:16），张数/枚举都合法 → 只挂构成关
    imgs = _set(tmp_path, [
        ("01_open.png",  "16:9"),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("构成" in r or "开篇" in r for r in reasons)


def test_verify_infographic_set_bad_composition_too_few_middle_16_9(tmp_path):
    # 开篇/结尾 9:16 对，但中间只有 1 张 16:9（需 ≥2）
    imgs = _set(tmp_path, [
        ("01_open.png",  "9:16"),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "9:16"),
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("中间" in r or "16:9" in r for r in reasons)


def test_verify_infographic_set_aspect_not_in_enum(tmp_path):
    # 一张 3:4（≈768×1024）—— 不在 {9:16,16:9,1:1}
    imgs = _set(tmp_path, [
        ("01_open.png",  "9:16"),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   (768, 1024)),  # 3:4，非三枚举
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("枚举" in r or "aspect" in r.lower() for r in reasons)


def test_verify_infographic_set_oversize_bytes(tmp_path, monkeypatch):
    # 字节超 2_000_000：用一张合规尺寸图但伪报巨大 bytes（避免造 2MB 真文件）
    imgs = _set(tmp_path, [
        ("01_open.png",  "9:16"),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    imgs[1] = dict(imgs[1], bytes=2_000_001)
    reasons = verify_infographic_set(imgs)
    assert any("2MB" in r or "2_000_000" in r or "bytes" in r.lower() for r in reasons)


def test_verify_infographic_set_not_1k_too_small(tmp_path):
    # 长边 800 < 900 下界 —— 不达 1K
    imgs = _set(tmp_path, [
        ("01_open.png",  (450, 800)),   # 9:16 比例但长边 800
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("1K" in r or "分辨率" in r or "长边" in r for r in reasons)


def test_verify_infographic_set_not_1k_too_large(tmp_path):
    # 长边 1600 > 1200 上界（模拟历史 2k 长卷）—— 超 1K 带
    imgs = _set(tmp_path, [
        ("01_open.png",  (900, 1600)),  # 9:16 比例但长边 1600
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("1K" in r or "分辨率" in r or "长边" in r for r in reasons)


def test_verify_infographic_set_aspect_tolerance_2px(tmp_path):
    # ±2px 容差：9:16 理想 576×1024，给 578×1024（差 2px）仍判 9:16 合规
    imgs = _set(tmp_path, [
        ("01_open.png",  (578, 1024)),
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    assert verify_infographic_set(imgs) == []


def test_verify_infographic_set_missing_file_reports_not_crash(tmp_path):
    # path 指向不存在文件 → 结构化报原因，不抛异常
    imgs = [
        {"path": str(tmp_path / "nope.png"), "aspect": "9:16", "bytes": 100},
    ] + _set(tmp_path, [
        ("02_mid.png",   "16:9"),
        ("03_mid.png",   "16:9"),
        ("04_close.png", "9:16"),
    ])
    reasons = verify_infographic_set(imgs)
    assert any("不存在" in r or "缺失" in r or "missing" in r.lower() for r in reasons)


def test_verify_infographic_set_returns_list_of_str(compliant_set):
    out = verify_infographic_set(compliant_set)
    assert isinstance(out, list)
    assert all(isinstance(r, str) for r in out)


# ====================================================================
# P2.2 tier-2 新产出验证门：verify_research_set（不追溯历史 golden）
# 与 tier-1 结构契约 validate_output 分开，**不**塞进 _OUTPUT_SCHEMA
# （与 verify_infographic_set 并列同构）。纯函数，只读入参 dict，
# 不读磁盘/网络/状态。规则①findings 实质 support ②去重源 ≥3
# ③版本/价格/日期类至少 1 官网级源 ④sources url 非空 + host 合法。
# ====================================================================

# 官网级源（tier=官网 / 官方 host / 官方路径）+ 权威媒体 + 二手社媒
_RS_OFFICIAL = {"title": "OpenAI 定价", "url": "https://openai.com/pricing",
                "tier": "官网", "accessed": "2026-05-19"}
_RS_DOCS = {"title": "API 更新日志", "url": "https://docs.example.com/changelog",
            "tier": "权威媒体", "accessed": "2026-05-19"}  # 官方 host 前缀命中
_RS_MEDIA = {"title": "The Verge", "url": "https://www.theverge.com/x",
             "tier": "权威媒体", "accessed": "2026-05-19"}
_RS_ZHIHU = {"title": "知乎", "url": "https://zhuanlan.zhihu.com/p/1",
             "tier": "社区", "accessed": "2026-05-19"}
_RS_36KR = {"title": "36氪", "url": "https://36kr.com/p/2", "tier": "权威媒体"}


def test_verify_research_set_compliant_returns_empty():
    findings = [
        {"claim": "新版定价每百万 token 5 美元",
         "support": "官网 pricing 页列出", "confidence": "high"},
        {"claim": "用户更依赖线下", "support": "竞品与社区讨论指向此",
         "confidence": "need_verify"},
    ]
    sources = [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU]  # 去重 3 条，含官网级
    assert verify_research_set(findings, sources) == []


def test_verify_research_set_findings_empty():
    reasons = verify_research_set([], [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU])
    assert any("findings" in r and "空" in r for r in reasons)


def test_verify_research_set_finding_missing_support():
    findings = [
        {"claim": "某趋势成立", "support": "", "confidence": "high"},
        {"claim": "另一观点"},  # 无 support 键
    ]
    reasons = verify_research_set(findings, [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU])
    assert any("support" in r and "findings[0]" in r for r in reasons)
    assert any("support" in r and "findings[1]" in r for r in reasons)


def test_verify_research_set_finding_missing_claim():
    findings = [{"support": "有证据但没主张"}]
    reasons = verify_research_set(findings, [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU])
    assert any("claim" in r and "findings[0]" in r for r in reasons)


def test_verify_research_set_sources_below_min():
    findings = [{"claim": "纯观点", "support": "有讨论佐证",
                 "confidence": "need_verify"}]
    # _RS_MEDIA 重复一份，归一化去重后只剩 2 个不同 url < 3
    sources = [_RS_MEDIA, dict(_RS_MEDIA), _RS_ZHIHU]
    reasons = verify_research_set(findings, sources)
    assert any("信源不足" in r or "sources_min" in r for r in reasons)


def test_verify_research_set_dedup_ignores_protocol_and_trailing_slash():
    # 同一篇换 http/https + 末尾斜杠 + ?query 不应凑成 3 条
    findings = [{"claim": "x", "support": "y", "confidence": "high"}]
    sources = [
        {"url": "https://a.com/post"},
        {"url": "http://a.com/post/"},
        {"url": "https://a.com/post?utm=1"},
    ]
    reasons = verify_research_set(findings, sources)
    assert any("信源不足" in r for r in reasons)  # 归一化后只 1 个


def test_verify_research_set_vpd_finding_without_official_source():
    findings = [
        {"claim": "新模型价格涨到每月 200 美元",
         "support": "多个社区帖子提到", "confidence": "high"},
    ]
    sources = [_RS_ZHIHU, _RS_36KR,
               {"url": "https://weibo.com/x", "tier": "社区"}]  # 全非官网级
    reasons = verify_research_set(findings, sources)
    assert any("官网级" in r and "findings[0]" in r for r in reasons)


def test_verify_research_set_vpd_finding_with_official_source_ok():
    # 同样涉价格，但有官网级源兜底 → 规则③ 不报
    findings = [
        {"claim": "新版价格每月 200 美元", "support": "官网定价页确认",
         "confidence": "high"},
    ]
    sources = [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU]
    reasons = verify_research_set(findings, sources)
    assert not any("官网级" in r for r in reasons)


def test_verify_research_set_official_via_tier_field():
    # tier == "官网" 即判官网级（即便 host 不带官方特征）
    findings = [{"claim": "v4 发布日期为 5 月", "support": "官方公告确认",
                 "confidence": "high"}]
    sources = [
        {"url": "https://some-vendor.io/a", "tier": "官网"},
        _RS_MEDIA, _RS_ZHIHU,
    ]
    assert verify_research_set(findings, sources) == []


def test_verify_research_set_official_via_official_subdomain():
    # 厂商自家文档/blog 子域（docs./blog. 前缀）→ 判官网级（一手声明，
    # 符合铁律）。P2.2 复审：官方子域仍判官网级，保留不动。
    findings = [{"claim": "定价是 5 美元", "support": "定价页列出",
                 "confidence": "high"}]
    sources = [
        {"url": "https://docs.acme-ai.com/pricing"},  # docs. 官方子域
        _RS_MEDIA, _RS_ZHIHU,
    ]
    assert verify_research_set(findings, sources) == []


def test_verify_research_set_bare_root_domain_path_not_official():
    # 🔴 P2.2 复审 Important 1：根域 + /pricing 但无官方子域前缀、无
    #    tier=="官网" → 路径提示**不单独生效**，不再判官网级。原 P2.2
    #    把 acme-ai.com/pricing 当官网级是过松，复审收紧后必须被 rule③ 报。
    findings = [{"claim": "定价是 5 美元", "support": "定价页列出",
                 "confidence": "high"}]
    sources = [
        {"url": "https://acme-ai.com/pricing"},  # 根域，无 docs./blog. 前缀
        _RS_MEDIA, _RS_ZHIHU,
    ]
    reasons = verify_research_set(findings, sources)
    assert any("官网级" in r and "findings[0]" in r for r in reasons)


def test_verify_research_set_pure_media_version_finding_reports_vpd():
    # 🔴 P2.2 复审 Important 1 核心回归：版本/价格 finding 全部源自
    #    The Verge / TechCrunch（含 /news、/release-notes 路径）零厂商
    #    官网 → 必须被 rule③ 报 vpd_needs_official（原实现误放行）。
    findings = [{"claim": "新模型版本 v4 发布，价格每月 200 美元",
                 "support": "The Verge 与 TechCrunch 报道",
                 "confidence": "high"}]
    sources = [
        {"url": "https://www.theverge.com/news/2026/ai-v4",
         "tier": "权威媒体"},
        {"url": "https://techcrunch.com/2026/05/19/release-notes",
         "tier": "权威媒体"},
        {"url": "https://www.wired.com/story/ai-pricing",
         "tier": "权威媒体"},
    ]
    reasons = verify_research_set(findings, sources)
    assert any("官网级" in r and "vpd_needs_official" in r
               for r in reasons), reasons


def test_verify_research_set_media_blog_path_not_official():
    # 第三方媒体即便路径像 /blog 也不提成官网级（Important 1）。
    findings = [{"claim": "价格 5 美元", "support": "媒体博客报道",
                 "confidence": "high"}]
    sources = [
        {"url": "https://www.theverge.com/blog/ai-price", "tier": "权威媒体"},
        _RS_MEDIA, _RS_ZHIHU,
    ]
    reasons = verify_research_set(findings, sources)
    assert any("官网级" in r for r in reasons)


def test_verify_research_set_vendor_blog_subdomain_still_official():
    # 厂商自家 blog. 子域属一手声明，仍判官网级（Important 1 明确保留）。
    findings = [{"claim": "v4 价格每月 200 美元", "support": "厂商博客公布",
                 "confidence": "high"}]
    sources = [
        {"url": "https://blog.openai.com/v4-pricing"},  # 厂商自家 blog.
        _RS_MEDIA, _RS_ZHIHU,
    ]
    assert verify_research_set(findings, sources) == []


def test_verify_research_set_non_official_exact_domain_match():
    # 🔴 P2.2 复审 Important 2：精确/后缀域匹配——合法官方子域
    #    docs.netflix.com / blog.max.com 含 "x.com"/"max.com" 子串，
    #    旧裸子串实现会误降级；新实现不误杀（这些 docs./blog. 前缀
    #    仍判官网级）。真 twitter.com / x.com 仍判非官网级。
    f = [{"claim": "v4 价格 200 美元", "support": "官方文档", "confidence": "high"}]
    # docs.netflix.com：官方子域，含 "x.com" 子串但不应被误降级
    ok1 = [{"url": "https://docs.netflix.com/pricing"},
           _RS_MEDIA, _RS_ZHIHU]
    assert verify_research_set(f, ok1) == []
    # blog.max.com：官方 blog 子域，含 "max.com" 但 max.com 不在黑名单，
    # 且 "x.com" 后缀匹配不命中（host 是 blog.max.com，不 endswith ".x.com"）
    ok2 = [{"url": "https://blog.max.com/release-notes"},
           _RS_MEDIA, _RS_ZHIHU]
    assert verify_research_set(f, ok2) == []
    # 真 x.com / twitter.com：仍判非官网级 → rule③ 报
    bad = [{"url": "https://x.com/someone/status/1", "tier": "社区"},
           {"url": "https://twitter.com/a", "tier": "社区"},
           _RS_ZHIHU]
    rb = verify_research_set(f, bad)
    assert any("官网级" in r for r in rb)


def test_verify_research_set_subdomain_of_non_official_still_blocked():
    # weibo.com 的子域 m.weibo.com 仍属二手（后缀域匹配命中），非官网级。
    f = [{"claim": "价格 5 美元", "support": "微博转述", "confidence": "high"}]
    sources = [{"url": "https://m.weibo.com/status/1", "tier": "社区"},
               _RS_MEDIA, _RS_ZHIHU]
    reasons = verify_research_set(f, sources)
    assert any("官网级" in r for r in reasons)


def test_verify_research_set_36kr_path_not_official():
    # 36氪即便路径像 /news 也属二手转述，不算官网级
    findings = [{"claim": "价格 5 美元", "support": "36氪报道",
                 "confidence": "high"}]
    sources = [
        {"url": "https://36kr.com/news/123", "tier": "权威媒体"},
        _RS_MEDIA, _RS_ZHIHU,
    ]
    reasons = verify_research_set(findings, sources)
    assert any("官网级" in r for r in reasons)


def test_verify_research_set_empty_url_source():
    findings = [{"claim": "结论", "support": "证据", "confidence": "high"}]
    sources = [_RS_OFFICIAL, {"title": "无链接", "url": "", "tier": "社区"},
               _RS_MEDIA, _RS_ZHIHU]
    reasons = verify_research_set(findings, sources)
    assert any("sources[1]" in r and "空" in r for r in reasons)


def test_verify_research_set_illegal_host():
    findings = [{"claim": "结论", "support": "证据", "confidence": "high"}]
    sources = [_RS_OFFICIAL, {"url": "not-a-real-url"},
               _RS_MEDIA, _RS_ZHIHU]
    reasons = verify_research_set(findings, sources)
    assert any("域名非法" in r or "host" in r for r in reasons)


def test_verify_research_set_non_list_inputs_no_crash():
    # 非 list 入参 → 结构化报，不裸崩
    reasons = verify_research_set("notalist", {"url": "x"})
    assert isinstance(reasons, list)
    assert any("findings 必须是 list" in r for r in reasons)
    assert any("sources 必须是 list" in r for r in reasons)


def test_verify_research_set_bare_str_finding_no_crash():
    # findings 项是裸 str（tier-1 放行的形态）→ tier-2 报实质缺失，不崩
    reasons = verify_research_set(
        ["裸字符串结论"], [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU])
    assert any("findings[0]" in r for r in reasons)


def test_verify_research_set_returns_list_of_str():
    out = verify_research_set(
        [{"claim": "x", "support": "y", "confidence": "high"}],
        [_RS_OFFICIAL, _RS_MEDIA, _RS_ZHIHU])
    assert isinstance(out, list)
    assert all(isinstance(r, str) for r in out)


# --- 与合成 fixture 生成器一致性（单一事实源，与 P2 门共用）---

def test_verify_research_set_fixture_groups_behave():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "research_make_fixtures",
        sw / "tests" / "golden" / "_synthetic_research" / "make_fixtures.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    g = mf.build_groups()
    assert verify_research_set(*g["compliant"]) == []
    assert any("support" in r for r in verify_research_set(*g["bad_no_support"]))
    assert any("信源不足" in r for r in verify_research_set(*g["bad_sources_few"]))
    assert any("官网级" in r
               for r in verify_research_set(*g["bad_vpd_no_official"]))
    assert any("空" in r for r in verify_research_set(*g["bad_empty_url"]))


# ====================================================================
# P3.2 tier-2 新产出验证门：verify_content_enhance_set（不追溯历史 golden）
# 与 tier-1 结构契约 validate_output 分开，**不**塞进 _OUTPUT_SCHEMA
# （与 verify_infographic_set / verify_research_set 并列同构）。纯函数，
# 只读入参 strategies(dict) + 可选 article_body(str)，不读磁盘/网络/状态。
# 规则①四策略两两去重 ②无显著自相矛盾 ③每策略实质性 ④与正文非脱节。
# 合并关本身（去重/消矛盾/统一嗓音/与正文融合）由编排器主轴自做、绝不
# 外派 subagent；本门是合并后对**新产出**的把关。
# ====================================================================

_CE_OK = {
    "angle":   "原稿平铺功能，改从「没有全能选手」反共识结论切入，"
               "让读者一开始就有立场。",
    "density": "第二段把「体验不错」压成可操作判据：长文给字数与"
               "卡顿阈值，事实给出错率，排版给格式清单。",
    "detail":  "把「用户踩的坑」落到具体场景：导出公众号丢加粗，"
               "附当时字数与报错画面。",
    "texture": "去掉评测腔书面长句，换口语短句节奏，用「你」直接"
               "对话读者贴近真实选型场景。",
}
# 正文桩须与 _CE_OK 四策略共享真实 token（立场/读者/字数/格式/场景/
# 踩坑/选型/评测），否则脱节关（fail-safe）会对合规策略误报——这是
# fixture 质量要求，非门 bug：正文太窄时增强说明本就难有公共 token。
_CE_BODY = (
    "对比三款 AI 写作工具的真实体验，关注长文生成、事实准确、"
    "排版导出三个场景，以及普通用户上手最容易踩的坑。文章先立场"
    "后展开，给读者明确的选型态度：长文看字数与卡顿，排版看导出"
    "格式清单，评测落到导出公众号丢加粗这类具体场景画面。")


def test_verify_content_enhance_set_compliant_returns_empty():
    assert verify_content_enhance_set(dict(_CE_OK), _CE_BODY) == []


def test_verify_content_enhance_set_compliant_ok_without_body():
    # article_body 缺省 → 脱节关整体跳过，其余关仍跑，合规组仍空
    assert verify_content_enhance_set(dict(_CE_OK)) == []


def test_verify_content_enhance_set_duplicate_strategies():
    # 两策略归一化后完全雷同（复制粘贴凑数）→ 规则① dedup
    bad = dict(_CE_OK)
    bad["detail"] = _CE_OK["density"]
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("dedup" in r and "density" in r and "detail" in r
               for r in reasons), reasons


def test_verify_content_enhance_set_large_overlap_dedup():
    # 非全等但大段连续雷同（占较短文本 ≥65%）也判 dedup
    shared = ("把第二段空泛体验压成可操作判据长文给字数与卡顿阈值"
              "事实给出错率排版给格式清单让读者照着做选型不再含糊")
    bad = dict(_CE_OK)
    bad["density"] = shared
    bad["detail"] = shared + "（仅尾部加一句不同的话）"
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("dedup" in r for r in reasons), reasons


def test_verify_content_enhance_set_self_contradiction():
    # 同一策略文本对冲词同现（更口语 vs 更书面）→ 规则② no_contradiction
    bad = dict(_CE_OK)
    bad["texture"] = ("整体应该更口语、句子更短贴近选型场景；同时"
                      "又要更书面、更严谨像正式评测报告给读者。")
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("no_contradiction" in r and "texture" in r
               for r in reasons), reasons


def test_verify_content_enhance_set_placeholder_too_short():
    # 占位 + 过短 → 规则③ substantive（实质性不足）
    bad = dict(_CE_OK)
    bad["detail"] = "TODO 待补"
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("substantive" in r and "detail" in r
               for r in reasons), reasons


def test_verify_content_enhance_set_short_but_not_placeholder():
    # 过短但非占位 → 仍报实质性不足（substantive_minlen），不误放过
    bad = dict(_CE_OK)
    bad["angle"] = "改切入"  # 3 字符 < 12，无占位词
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("substantive_minlen" in r and "angle" in r
               for r in reasons), reasons


def test_verify_content_enhance_set_disjoint_from_body():
    # 某策略与正文零公共 token（跑错题/套模板）→ 规则④ not_disjoint
    bad = dict(_CE_OK)
    bad["angle"] = ("建议从家常红烧肉火候讲起，先焯水再冰糖炒色，"
                    "铁锅厚底受热均匀风味更佳。")
    reasons = verify_content_enhance_set(bad, _CE_BODY)
    assert any("not_disjoint" in r and "angle" in r
               for r in reasons), reasons


def test_verify_content_enhance_set_disjoint_skipped_without_body():
    # 不给 article_body → 脱节关跳过：即便策略写的是另一选题也不报④
    bad = dict(_CE_OK)
    bad["angle"] = ("建议从家常红烧肉火候讲起，先焯水再冰糖炒色，"
                    "铁锅厚底受热均匀风味更佳。")
    reasons = verify_content_enhance_set(bad)  # 无 body
    assert not any("not_disjoint" in r for r in reasons), reasons


def test_verify_content_enhance_set_disjoint_skipped_empty_body():
    # 空白 article_body 等同未给 → 脱节关跳过（不臆断）
    assert not any(
        "not_disjoint" in r
        for r in verify_content_enhance_set(dict(_CE_OK), "   "))


def test_verify_content_enhance_set_non_dict_no_crash():
    # 非 dict 入参 → 结构化报，不裸崩
    reasons = verify_content_enhance_set("notadict", _CE_BODY)
    assert isinstance(reasons, list)
    assert any("strategies 必须是 dict" in r for r in reasons)


def test_verify_content_enhance_set_missing_key_no_crash():
    # tier-1 通常已先拦，但 tier-2 防御性遇缺键/非 str 不崩、结构化报
    reasons = verify_content_enhance_set(
        {"angle": "x" * 30, "density": "y" * 30, "detail": "z" * 30},
        _CE_BODY)  # 缺 texture
    assert isinstance(reasons, list)
    assert any("texture" in r and "prereq" in r for r in reasons)


def test_verify_content_enhance_set_returns_list_of_str():
    out = verify_content_enhance_set(dict(_CE_OK), _CE_BODY)
    assert isinstance(out, list)
    assert all(isinstance(r, str) for r in out)


def test_verify_content_enhance_set_uses_canonical_key_constant():
    # 单一事实源：verify 内部按模块级 _CE_STRATEGY_KEYS 取值，
    # 不重抄 4 键硬编码。改常量即改判定面（防双写漂移）。
    import scripts.contracts as cmod
    assert cmod._CE_STRATEGY_KEYS == ("angle", "density", "detail", "texture")


# --- 与合成 fixture 生成器一致性（单一事实源，与 P3 门共用）---

def test_verify_content_enhance_set_fixture_groups_behave():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "ce_make_fixtures",
        sw / "tests" / "golden" / "_synthetic_content_enhance"
        / "make_fixtures.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    g = mf.build_groups()
    assert verify_content_enhance_set(*g["compliant"]) == []
    assert any("dedup" in r
               for r in verify_content_enhance_set(*g["bad_duplicate"]))
    assert any("no_contradiction" in r
               for r in verify_content_enhance_set(*g["bad_contradiction"]))
    assert any("substantive" in r
               for r in verify_content_enhance_set(*g["bad_placeholder"]))
    assert any("not_disjoint" in r
               for r in verify_content_enhance_set(*g["bad_disjoint"]))


# --- P3.1 复审保护：_run_p3 误配 strategies_present<1 不得裸 IndexError ---
# 复审 Important：p3_fixture_invalid 自检命中后必须立即 return，否则
# legal_keys=() → neg_cases 的 legal_keys[0] 抛裸 IndexError 逃出 _run_p3
# 成 traceback（违反「任何异常转结构化 harness_error、禁裸 traceback」铁律）。
# 本用例临时把 THRESHOLDS["P3"]["strategies_present"] 误配为 0，断言：
#   ① _run_p3 不抛任何异常（尤其不抛 IndexError）；
#   ② failures 含结构化 p3_fixture_invalid；
#   ③ 还原阈值后正常 n_strat=4 路径仍 failures 空（return 未破坏正常路径）。

def test_run_p3_misconfigured_strategies_present_is_structured_not_traceback():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "regression_baseline", sw / "scripts" / "regression_baseline.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)

    orig = rb.THRESHOLDS["P3"]["strategies_present"]
    try:
        rb.THRESHOLDS["P3"]["strategies_present"] = 0  # 误配 <1
        bad_failures = []
        # 不得抛 IndexError / 任何异常逃出（裸 traceback 即测试失败）
        rb._run_p3(bad_failures)
        kinds = [f.get("kind") for f in bad_failures]
        assert "p3_fixture_invalid" in kinds, bad_failures
        # 误配收口后不应继续跑出契约 smoke 失败（已 return）
        assert all(
            k != "contract_smoke_negative_fail" for k in kinds), bad_failures
    finally:
        rb.THRESHOLDS["P3"]["strategies_present"] = orig

    # 还原后正常路径仍干净（return 修复未破坏 n_strat=4 真实消费）
    assert rb.THRESHOLDS["P3"]["strategies_present"] == 4
    good_failures = []
    rb._run_p3(good_failures)
    assert all(
        f.get("kind") != "p3_fixture_invalid" for f in good_failures), \
        good_failures


# ====================================================================
# P4.2 tier-2 新产出验证门：verify_cover_set（不追溯历史 golden）
# 与 tier-1 结构契约 validate_output 分开，**不**塞进 _OUTPUT_SCHEMA
# （与 verify_infographic_set / verify_research_set /
# verify_content_enhance_set 并列同构）。纯函数，读入参 + 磁盘 PNG
# 像素（IO），不碰网络/状态。规则① selected∈candidates ②候选≥2
# ③图实际存在 ④1K（复用信息图既定带）⑤2.35:1 cinematic
# （⑥近 3 篇回避 2026-05-22 封面锁定后已删除，recent_covers 为废弃 no-op）。
# 默认锁定单风格路径不调本门；cover 要做磁盘 IO 读真实像素判 2.35:1/1K，故
# fixture 必须真造 PNG（与 verify_infographic_set 同，用 tmp_path）。
# ====================================================================

# 2.35:1 cinematic：长边（宽）1024 → 高 = round(1024*100/235) = 436。
# 1024 落 contracts._K1_*（[900,1200]）既定 1K 带内（复用信息图口径）。
_CV_W = 1024
_CV_H = round(_CV_W * 100 / 235)
_BRAND = (47, 111, 143)  # 中性填充纯色（primary slate）；本门只读尺寸，不读内容


def _cv_png(dirpath, name, w, h):
    """造一张纯色 PNG，返回绝对 path str。"""
    p = dirpath / name
    Image.new("RGB", (w, h), _BRAND).save(str(p), "PNG", optimize=True)
    return str(p)


def _cv_ok_cands(tmp_path, prefix="ok"):
    """合规候选基线：2 个 2.35:1 / 1K 候选，风格 montage-evidence + briefing。"""
    return [
        {"path": _cv_png(tmp_path, f"{prefix}_evi.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, f"{prefix}_brief.png", _CV_W, _CV_H),
         "style": "briefing", "aspect": "2.35:1"},
    ]

# 近 3 篇刻意不含 montage 家族，避免合规组被规则⑥ montage 同源关误报。
_CV_RECENT_OK = ["noir", "briefing", "noir"]


def test_verify_cover_set_compliant_returns_empty(tmp_path):
    cands = _cv_ok_cands(tmp_path)
    assert verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK) == []


def test_verify_cover_set_compliant_ok_without_recent(tmp_path):
    # recent_covers 缺省 → 风格回避关整体跳过，其余关仍跑，合规组仍空
    cands = _cv_ok_cands(tmp_path)
    assert verify_cover_set(cands, cands[0]["path"]) == []


def test_verify_cover_set_selected_not_in_candidates(tmp_path):
    # selected 不在 candidates 路径集合 → 规则① selected_in_candidates
    cands = _cv_ok_cands(tmp_path)
    reasons = verify_cover_set(
        cands, "素材/cover/完全不在里面.png", _CV_RECENT_OK)
    assert any("selected_in_candidates" in r for r in reasons), reasons


def test_verify_cover_set_too_few_candidates(tmp_path):
    # 仅 1 个候选（< 多风格打样下限 2）→ 规则② candidates_min
    one = [{"path": _cv_png(tmp_path, "one.png", _CV_W, _CV_H),
            "style": "noir", "aspect": "2.35:1"}]
    reasons = verify_cover_set(one, one[0]["path"], _CV_RECENT_OK)
    assert any("candidates_min" in r for r in reasons), reasons


def test_verify_cover_set_missing_file_reports_not_crash(tmp_path):
    # 某候选 path 指向不存在文件 → 规则③ candidate_exists（不裸崩）
    cands = [
        {"path": _cv_png(tmp_path, "ex_ok.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": str(tmp_path / "缺失.png"),  # 不造
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert any("candidate_exists" in r for r in reasons), reasons


def test_verify_cover_set_not_1k_too_small(tmp_path):
    # 某候选长边 800（< 1K 下界 900）但仍 2.35:1 → 规则④ resolution_1k
    sw = 800
    sh = round(sw * 100 / 235)
    cands = [
        {"path": _cv_png(tmp_path, "k_ok.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "k_small.png", sw, sh),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert any("resolution_1k" in r for r in reasons), reasons


def test_verify_cover_set_not_1k_too_large(tmp_path):
    # 长边 1500（> 1K 上界 1200）2.35:1 长卷 → 规则④ resolution_1k
    bw = 1500
    bh = round(bw * 100 / 235)
    cands = [
        {"path": _cv_png(tmp_path, "kb_ok.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "kb_big.png", bw, bh),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert any("resolution_1k" in r for r in reasons), reasons


def test_verify_cover_set_wrong_ratio_16_9(tmp_path):
    # 某候选 16:9（非 cinematic 2.35:1），长边仍 1K → 规则⑤ cinematic_ratio
    cands = [
        {"path": _cv_png(tmp_path, "r_ok.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "r_169.png", 1024, 576),  # 16:9
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert any("cinematic_ratio" in r for r in reasons), reasons


def test_verify_cover_set_ratio_tolerance_within_4px(tmp_path):
    # 2.35:1 在 ±4px 容差内（高 436 时理想宽 1024.6，造 1022 偏差 <4）
    # 应判合规、不误报比例。验证 _COVER_RATIO_TOL_PX 容差落实。
    cands = [
        {"path": _cv_png(tmp_path, "t_a.png", 1022, 436),  # 偏差 ~2.6px
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "t_b.png", _CV_W, _CV_H),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert not any("cinematic_ratio" in r for r in reasons), reasons


def test_verify_cover_set_recent_avoidance_removed(tmp_path):
    # 🔴 2026-05-22 封面锁定 montage-evidence，「近 3 篇回避」规则已删除。
    # 回归守护：即便传入会精确撞车 / montage 同源撞车的 recent_covers，
    # verify_cover_set 也**绝不再**产生任何 recent_repeat 违规。
    cands = [
        {"path": _cv_png(tmp_path, "rm_evi.png", _CV_W, _CV_H),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "rm_brief.png", _CV_W, _CV_H),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    # 精确撞车（selected=montage-evidence，近 3 篇也含 montage-evidence）
    # 且 montage 同源撞车——两种旧违规情形都给齐，断言均不再触发。
    reasons = verify_cover_set(
        cands, cands[0]["path"],
        ["montage-evidence", "montage-pipeline", "noir"])
    assert not any("recent_repeat" in r for r in reasons), reasons


def test_verify_cover_set_recent_skipped_without_recent(tmp_path):
    # 不给 recent_covers → 风格回避关跳过：即便风格会撞也不报⑥
    cands = [
        {"path": _cv_png(tmp_path, "sk_noir.png", _CV_W, _CV_H),
         "style": "noir", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "sk_brief.png", _CV_W, _CV_H),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    reasons = verify_cover_set(cands, cands[0]["path"])  # 无 recent
    assert not any("recent_repeat" in r for r in reasons), reasons


def test_verify_cover_set_recent_skipped_empty_list(tmp_path):
    # 空 recent_covers 等同未给 → 回避关跳过（不臆断）
    cands = [
        {"path": _cv_png(tmp_path, "se_noir.png", _CV_W, _CV_H),
         "style": "noir", "aspect": "2.35:1"},
        {"path": _cv_png(tmp_path, "se_brief.png", _CV_W, _CV_H),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    assert not any(
        "recent_repeat" in r
        for r in verify_cover_set(cands, cands[0]["path"], []))


def test_verify_cover_set_recent_skipped_when_selected_no_style(tmp_path):
    # selected 对应 candidate 无 style 字段 → 回避关跳过不臆断（边界）
    cands = [
        {"path": _cv_png(tmp_path, "ns_a.png", _CV_W, _CV_H)},  # 无 style
        {"path": _cv_png(tmp_path, "ns_b.png", _CV_W, _CV_H),
         "style": "briefing"},
    ]
    reasons = verify_cover_set(
        cands, cands[0]["path"], ["noir", "briefing", "noir"])
    # 缺 style 本身不是⑥违规（⑥ 只管与近 3 篇重复），其余关合规故空
    assert not any("recent_repeat" in r for r in reasons), reasons


def test_verify_cover_set_non_list_inputs_no_crash(tmp_path):
    # 非 list candidates / 非 str selected → 结构化报，不裸崩
    reasons = verify_cover_set("notalist", 123, _CV_RECENT_OK)
    assert isinstance(reasons, list)
    assert any("candidates 必须是 list" in r for r in reasons)
    assert any("selected 必须是非空 str" in r for r in reasons)


def test_verify_cover_set_candidate_not_dict_no_crash(tmp_path):
    # candidates 含裸 str 项 → 结构化报 candidate_struct，不裸崩
    ok = _cv_png(tmp_path, "cd_ok.png", _CV_W, _CV_H)
    reasons = verify_cover_set(
        [{"path": ok, "style": "noir"}, "素材/裸串.png"],
        ok, _CV_RECENT_OK)
    assert any("candidate_struct" in r for r in reasons), reasons


def test_verify_cover_set_returns_list_of_str(tmp_path):
    cands = _cv_ok_cands(tmp_path)
    out = verify_cover_set(cands, cands[0]["path"], _CV_RECENT_OK)
    assert isinstance(out, list)
    assert all(isinstance(r, str) for r in out)


def test_verify_cover_set_not_in_output_schema():
    # tier-2 门**不**塞进 _OUTPUT_SCHEMA / validate_output（与总纲一致；
    # 与 verify_infographic_set/research/content_enhance 并列同构）。
    import scripts.contracts as cmod
    assert "verify_cover_set" not in cmod._OUTPUT_SCHEMA
    # 顶层 cover schema 仍 {candidates:list, selected:str} 不变（一致性等价）
    assert cmod._OUTPUT_SCHEMA["cover"] == {"candidates": list, "selected": str}


def test_verify_cover_set_reuses_infographic_1k_band():
    # 1K 复用 verify_infographic_set 既定 [900,1200] 口径（单一事实源，
    # 不双写漂移）：verify_cover_set 直接用模块级 _K1_MIN/_K1_MAX。
    import scripts.contracts as cmod
    assert (cmod._K1_MIN, cmod._K1_MAX) == (900, 1200)
    # cover 多风格打样下限常量（fixture 与门共用单一事实源）
    assert cmod._COVER_MIN_CANDIDATES == 2


# --- 与合成 fixture 生成器一致性（单一事实源，与 P4 门共用）---

def test_verify_cover_set_fixture_groups_behave(tmp_path):
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "cover_make_fixtures",
        sw / "tests" / "golden" / "_synthetic_cover" / "make_fixtures.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    g = mf.build_groups(tmp_path)
    assert verify_cover_set(*g["compliant"]) == []
    assert any("selected_in_candidates" in r
               for r in verify_cover_set(*g["bad_selected_not_in"]))
    assert any("candidates_min" in r
               for r in verify_cover_set(*g["bad_too_few"]))
    assert any("candidate_exists" in r
               for r in verify_cover_set(*g["bad_missing_file"]))
    assert any("resolution_1k" in r
               for r in verify_cover_set(*g["bad_not_1k"]))
    assert any("cinematic_ratio" in r
               for r in verify_cover_set(*g["bad_ratio"]))
    # 🔴「近 3 篇回避」规则已删除（2026-05-22 封面锁定）：旧 bad_recent_repeat
    # 组即便构造撞车也不再产生 recent_repeat 违规。
    assert not any("recent_repeat" in r
                   for r in verify_cover_set(*g["bad_recent_repeat"]))


# --- 锁定回归：P4.2 _run_p4 (c) 段不读历史 golden + 自检 return 防裸崩 ---
# 仿 P3.1 复审保护用例（test_run_p3_misconfigured_...）：从 rb 侧把合规
# fixture 形状常量 _P4_FX_CAND_N 误配成一个让自检失配的值（1，<
# contracts._COVER_MIN_CANDIDATES=2），断言 _run_p4：
#   ① 不抛任何异常逃出（裸 traceback 即测试失败）；
#   ② failures 含结构化 p4_fixture_invalid（自检即收口）；
#   ③ 还原后正常路径仍干净（return 未破坏 _P4_FX_CAND_N=2 真实消费）。
# 用 rb 侧 _P4_FX_CAND_N 而非 contracts._COVER_MIN_CANDIDATES 作杠杆：
# _run_p4 内按文件路径 fresh import contracts（独立模块实例），改
# contracts 常量不影响该实例；rb._P4_FX_CAND_N 是 rb 自身模块级、
# _run_p4 直接读，可稳定 monkeypatch（与 P3.1 用 rb.THRESHOLDS 同理）。

def test_run_p4_misconfigured_fixture_shape_is_structured_not_traceback():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    rb_spec = importlib.util.spec_from_file_location(
        "regression_baseline", sw / "scripts" / "regression_baseline.py")
    rb = importlib.util.module_from_spec(rb_spec)
    rb_spec.loader.exec_module(rb)

    orig = rb._P4_FX_CAND_N
    try:
        rb._P4_FX_CAND_N = 1  # < contracts._COVER_MIN_CANDIDATES(2) → 失配
        bad_failures = []
        rb._run_p4(bad_failures)  # 不得抛任何异常逃出（裸 traceback 即失败）
        kinds = [f.get("kind") for f in bad_failures]
        assert "p4_fixture_invalid" in kinds, bad_failures
        # 自检收口后不应继续跑出 tier-2 误判 failure（已 return）
        assert all(
            k not in ("tier2_gate_false_positive",
                      "tier2_gate_false_negative") for k in kinds), \
            bad_failures
    finally:
        rb._P4_FX_CAND_N = orig

    # 还原后正常路径仍干净（return 修复未破坏 _P4_FX_CAND_N=2 真实消费）
    assert rb._P4_FX_CAND_N == 2
    good_failures = []
    rb._run_p4(good_failures)
    assert all(
        f.get("kind") != "p4_fixture_invalid" for f in good_failures), \
        good_failures


# ====================================================================
# review tier-1 结构契约不污染锁定（P5.1 起；P5.2 接入 verify_review_set
# 后仍须保证顶层 schema 面不变 = team 关闭与 legacy 字节级等价的前提）。
# ====================================================================

def test_review_not_in_output_schema_item_validator():
    # tier-1 结构校验经 _validate_review_items，但顶层 review schema 仍
    # {verdicts:list} 不变（一致性等价：升 tier-1/接入 tier-2 不改顶层
    # schema 面 —— team 关闭时单 agent 磨稿不因 P5.2 多出任何 tier-1 强制）。
    import scripts.contracts as cmod
    assert cmod._OUTPUT_SCHEMA["review"] == {"verdicts": list}
    # P5.2 起 verify_review_set 已实装，但**只能是 tier-2 独立纯函数**，
    # 严禁塞进 _OUTPUT_SCHEMA / validate_output（污染 tier-1 契约且与
    # 校验层级总纲自相矛盾）。锁定：函数存在 + 不在 _OUTPUT_SCHEMA 内。
    assert hasattr(cmod, "verify_review_set")
    assert "verify_review_set" not in cmod._OUTPUT_SCHEMA
    assert "review" in cmod._OUTPUT_SCHEMA  # 顶层 stage 键仍在


def test_review_pass_strict_bool_mirrors_bytes_int_exclusion():
    # pass 严格 bool（排 int 1/0）与 infographic.bytes 严格 int（排 bool）
    # 互为镜像：同一文件两条 isinstance 取向相反，验证未被统一偷懒写法污染。
    # bytes=True/False 必须被拒（int 分支排 bool）
    with pytest.raises(ContractError):
        validate_output("infographic",
                        {"images": [{"path": "x", "aspect": "9:16",
                                     "bytes": True}]})
    # pass=1/0(int) 必须被拒（bool 分支排 int）
    with pytest.raises(ContractError):
        validate_output("review",
                        {"verdicts": [{"role": "x", "issues": [],
                                       "pass": 1}]})
    # 两者各自合法值仍放行（bytes 真 int / pass 真 bool）
    assert validate_output(
        "infographic",
        {"images": [{"path": "x", "aspect": "9:16", "bytes": 10}]}) is True
    assert validate_output(
        "review",
        {"verdicts": [{"role": "x", "issues": [], "pass": True}]}) is True


# --- P3.1 复审保护范式套用：_run_p5 误配 para_delta_pct 不得裸崩 ---
# 仿 test_run_p3_misconfigured_... / test_run_p4_misconfigured_...：
# 临时把 THRESHOLDS["P5"]["para_delta_pct"] 误配成非法值（-1 / 字符串），
# 断言 _run_p5：
#   ① 不抛任何异常逃出（裸 traceback 即测试失败）；
#   ② failures 含结构化 p5_fixture_invalid（自检即收口）；
#   ③ 还原后正常路径仍干净（return 未破坏 h2_delta/para_delta_pct 真实消费）。

def test_run_p5_misconfigured_para_delta_pct_is_structured_not_traceback():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "regression_baseline", sw / "scripts" / "regression_baseline.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)

    orig = rb.THRESHOLDS["P5"]["para_delta_pct"]
    for bad_val in (-1, "15", 0, 200):
        try:
            rb.THRESHOLDS["P5"]["para_delta_pct"] = bad_val  # 误配非法
            bad_failures = []
            # 不得抛任何异常逃出（裸 traceback 即测试失败）
            rb._run_p5(bad_failures)
            kinds = [f.get("kind") for f in bad_failures]
            assert "p5_fixture_invalid" in kinds, (bad_val, bad_failures)
            # 自检收口后不应继续跑出数值门误判 failure（已 return）
            assert all(
                k not in ("p5_numeric_gate_false_positive",
                          "p5_numeric_gate_false_negative") for k in kinds), \
                (bad_val, bad_failures)
        finally:
            rb.THRESHOLDS["P5"]["para_delta_pct"] = orig

    # 误配 h2_delta（非 0）也必须自检收口
    orig_h2 = rb.THRESHOLDS["P5"]["h2_delta"]
    try:
        rb.THRESHOLDS["P5"]["h2_delta"] = 1
        bf = []
        rb._run_p5(bf)
        assert "p5_fixture_invalid" in [f.get("kind") for f in bf], bf
    finally:
        rb.THRESHOLDS["P5"]["h2_delta"] = orig_h2

    # 还原后正常路径仍干净（return 修复未破坏 P5 数值阈真实消费）
    assert rb.THRESHOLDS["P5"]["para_delta_pct"] == 15
    assert rb.THRESHOLDS["P5"]["h2_delta"] == 0
    good_failures = []
    rb._run_p5(good_failures)
    assert all(
        f.get("kind") not in ("p5_fixture_invalid",
                              "p5_numeric_gate_false_positive",
                              "p5_numeric_gate_false_negative",
                              "p5_numeric_gate_wrong_reason")
        for f in good_failures), good_failures


# ====================================================================
# P5.2 tier-2 新产出验证门：verify_review_set（不追溯历史 golden）
# 与 tier-1 结构契约 validate_output 分开，**不**塞进 _OUTPUT_SCHEMA
# （与 verify_infographic_set / verify_research_set /
# verify_content_enhance_set / verify_cover_set 并列同构）。纯函数，
# 只读入参 list[dict]，不读磁盘/网络/状态。规则① 去重后 ≥3 不同 role
# ② pass=false 须带非空 issues ③ pass=true 却带 issues 的弱不一致。
# **汇总裁决是编排器主轴自做、绝不外派 subagent**；本门是汇总裁决
# 前置对新产出的把关，不是汇总裁决本身。审稿 team 是 opt-in/提议制。
# ====================================================================

# 合规基线三角色：覆盖 ≥3 不同 role；pass=false 均带非空 issues；
# pass=true 的 issues 空（无 pass-true-却带 issues 弱不一致）。
def _rv_ok():
    return [
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "铁律审", "issues": ["第3段尾部总结句"], "pass": False},
        {"role": "事实核查", "issues": ["第5段价格未标官网信源"],
         "pass": False},
    ]


def test_verify_review_set_compliant_returns_empty():
    assert verify_review_set(_rv_ok()) == []


def test_verify_review_set_compliant_ok_ignores_second_arg():
    # 第二参 recent_or_ctx 仅同构预留位，规则①②③ 不消费 → 给任意值
    # 不改判定（合规仍空）。锁定门不臆用上下文（review 不追溯历史）。
    assert verify_review_set(_rv_ok(), ["任意历史"]) == []
    assert verify_review_set(_rv_ok(), {"x": 1}) == []
    assert verify_review_set(_rv_ok(), None) == []


def test_verify_review_set_too_few_roles():
    # 只 2 个不同 role（铁律审复制凑数）→ 规则① roles_min
    few = [
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "铁律审", "issues": ["a"], "pass": False},
        {"role": "铁律审", "issues": ["b"], "pass": False},
    ]
    rs = verify_review_set(few)
    assert any("roles_min" in r for r in rs), rs
    # 只精确触发① —— 其余裁决本身合规，不应夹带②③
    assert not any("fail_needs_issues" in r or "verdict_consistency" in r
                   for r in rs), rs


def test_verify_review_set_fail_without_issues():
    # 事实核查 pass=false 但 issues 空 → 规则② fail_needs_issues
    bad = _rv_ok()
    bad[2] = {"role": "事实核查", "issues": [], "pass": False}
    rs = verify_review_set(bad)
    assert any("fail_needs_issues" in r for r in rs), rs
    # 三角色仍齐 + 无 pass-true-带-issues → 不夹带①③
    assert not any("roles_min" in r or "verdict_consistency" in r
                   for r in rs), rs


def test_verify_review_set_fail_with_only_blank_issues_still_reports():
    # issues 全是空白 str → 视为「无具体可定位 issue」，仍报②（fail-safe）
    bad = _rv_ok()
    bad[1] = {"role": "铁律审", "issues": ["", "   "], "pass": False}
    rs = verify_review_set(bad)
    assert any("fail_needs_issues" in r for r in rs), rs


def test_verify_review_set_pass_true_with_issues_inconsistent():
    # 风格审 pass=true 却带非空 issues → 规则③ verdict_consistency（弱提示）
    bad = _rv_ok()
    bad[0] = {"role": "风格审", "issues": ["句长方差不足却判过"],
              "pass": True}
    rs = verify_review_set(bad)
    assert any("verdict_consistency" in r for r in rs), rs
    assert not any("roles_min" in r or "fail_needs_issues" in r
                   for r in rs), rs


def test_verify_review_set_does_not_whitelist_role_names():
    # 门不内置「合法 role 白名单」：3 个非常规但去重不同的 role 名，
    # 裁决本身合规 → 必须放行（不判 role 是否「正统审稿角色」）。
    odd = [
        {"role": "角色A", "issues": [], "pass": True},
        {"role": "角色B", "issues": ["x"], "pass": False},
        {"role": "角色C", "issues": ["y"], "pass": False},
    ]
    assert verify_review_set(odd) == []


def test_verify_review_set_dedup_counts_distinct_roles():
    # 5 条 verdict 但只 2 个不同 role（去重后）→ 仍报① roles_min
    dup = [
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "铁律审", "issues": ["a"], "pass": False},
        {"role": "铁律审", "issues": ["b"], "pass": False},
        {"role": "  风格审  ", "issues": [], "pass": True},  # strip 后同名
    ]
    rs = verify_review_set(dup)
    assert any("roles_min" in r for r in rs), rs


def test_verify_review_set_pass_false_strict_only_bool_false():
    # ② 只对真 False 触发（pass 非 bool 由 tier-1 管，本门不臆判）。
    # pass=0(int) 不是 False（is False 为否）→ 本门不报②（tier-1 已会拦）。
    weird = [
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "铁律审", "issues": ["a"], "pass": False},
        {"role": "事实核查", "issues": [], "pass": 0},  # int，非严格 False
    ]
    rs = verify_review_set(weird)
    # 不应因 pass=0 报②（那是 tier-1 _validate_review_items 的职责）
    assert not any("fail_needs_issues" in r for r in rs), rs


def test_verify_review_set_non_list_input_no_crash():
    rs = verify_review_set("notalist")
    assert isinstance(rs, list) and rs
    assert any("必须是 list" in r for r in rs), rs


def test_verify_review_set_verdict_not_dict_no_crash():
    rs = verify_review_set(["裸字符串", 123,
                            {"role": "风格审", "issues": [], "pass": True}])
    assert isinstance(rs, list)
    # 裸项结构化报 + 角色不足（只 1 个合法 role）—— 不裸崩
    assert any("不是 dict" in r for r in rs), rs


def test_verify_review_set_issues_not_list_structured_not_crash():
    bad = [
        {"role": "风格审", "issues": "应是list", "pass": False},
        {"role": "铁律审", "issues": ["a"], "pass": False},
        {"role": "事实核查", "issues": ["b"], "pass": False},
    ]
    rs = verify_review_set(bad)
    assert any("issues 非 list" in r for r in rs), rs


def test_verify_review_set_returns_list_of_str():
    out = verify_review_set(_rv_ok())
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)


def test_verify_review_set_not_in_output_schema():
    # tier-2 门**不**塞进 _OUTPUT_SCHEMA / validate_output（与总纲一致；
    # team 关闭时单 agent 磨稿不因 P5.2 多出 tier-1 强制 = 字节级等价前提）。
    import scripts.contracts as cmod
    assert "verify_review_set" not in cmod._OUTPUT_SCHEMA
    # 顶层 review schema 仍 {verdicts:list} 不变（一致性等价 exit0）
    assert cmod._OUTPUT_SCHEMA["review"] == {"verdicts": list}
    # validate_output("review",...) 仍只做 tier-1，不调 verify_review_set
    assert validate_output("review", {"verdicts": [
        {"role": "x", "issues": ["有问题但 pass=true"], "pass": True}]}) is True


def test_verify_review_set_fixture_groups_behave():
    # 与 regression_baseline.py P5 门 (d) 段共用同一套合成 fixture
    # （单一事实源，hermetic）：合规组空、各违规组精确报对应规则名。
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    mf_spec = importlib.util.spec_from_file_location(
        "review_make_fixtures",
        sw / "tests" / "golden" / "_synthetic_review" / "make_fixtures.py")
    mf = importlib.util.module_from_spec(mf_spec)
    mf_spec.loader.exec_module(mf)
    g = mf.build_groups()
    assert verify_review_set(g["compliant"]) == []
    assert any("roles_min" in r
               for r in verify_review_set(g["bad_too_few_roles"]))
    assert any("fail_needs_issues" in r
               for r in verify_review_set(g["bad_fail_no_issues"]))
    assert any("verdict_consistency" in r
               for r in verify_review_set(g["bad_inconsistent"]))


def test_verify_review_set_min_roles_constant_is_3():
    # 锁定回归：_REVIEW_MIN_ROLES = 3（三角色风格审/铁律审/事实核查）。
    # 与 _run_p5 (d) 自检的 _RV_FX_ROLES=3 一致性的契约面。
    import scripts.contracts as cmod
    assert cmod._REVIEW_MIN_ROLES == 3


# --- 锁定回归：_run_p5 (d) 段不读历史 golden + 自检 return 防裸崩 ---
# 仿 P4.2 test_run_p4_misconfigured_...：从 rb 侧把合规 review fixture
# 形状常量 _RV_FX_ROLES 误配成让自检失配的值（不可——它是 (d) 内局部
# 量），改走 contracts._REVIEW_MIN_ROLES monkeypatch：把它抬到 99
# （> 合规 fixture 的 3 角色）触发 (d) 自检即收口，断言 _run_p5：
#   ① 不抛任何异常逃出（裸 traceback 即测试失败）；
#   ② failures 含结构化 p5_fixture_invalid（自检即收口）；
#   ③ 还原后正常路径仍干净（return 未破坏 verify_review_set 真实消费）。
# _run_p5 内按文件路径 fresh import contracts（独立模块实例），故须改
# 那个 fresh 实例看到的值 —— 这里直接 monkeypatch 源文件无效；改用
# 在 rb 侧不可行，故验证「合规常量=3 时正常路径 (d) 不误判」+ 单独
# 用 contracts 模块级常量存在性锁定（自检逻辑本身已被 fixture 用例覆盖）。

def test_run_p5_section_d_clean_on_valid_config():
    import importlib.util, pathlib
    sw = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "regression_baseline", sw / "scripts" / "regression_baseline.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    failures = []
    rb._run_p5(failures)
    # (d) 段在合法配置下不得产生 tier-2 误判 / fixture 失配 / 等价破坏
    bad_kinds = {
        "tier2_gate_false_positive", "tier2_gate_false_negative",
        "tier2_gate_wrong_reason", "p5_team_off_equivalence_fail",
    }
    offenders = [f for f in failures
                 if f.get("func") == "verify_review_set"
                 or f.get("kind") in bad_kinds]
    assert not offenders, offenders
    # 合规 review fixture 必须真实被 (d) 消费且全过（无 p5_fixture_invalid）
    assert all(f.get("kind") != "p5_fixture_invalid"
               for f in failures), failures


# --- 2026-06-10 P0-5 导游腔元话语硬门（49 号实证：报幕句 6 处，人类范文 0 处）---

def _write_md(tmp_path, body):
    p = tmp_path / "定稿.md"
    p.write_text("---\ntitle: t\n---\n\n" + body, encoding="utf-8")
    return str(p)

def test_meta_discourse_hits_are_hard_errors(tmp_path):
    from scripts.contracts import verify_anti_ai_blacklist
    body = (
        "听起来有点抽象。我们不妨把它拆成三件已经在发生的小事。\n\n"
        "先说最直观的一个。\n\n这一点我们后面再说。\n\n"
        "聊到这儿，可以往后退一步。\n\n还记得前面埋的那个细节吗。\n\n"
        "所以临了我想留个问题，给你。\n\n这句话翻译过来就是：以后不用自己点了。\n\n"
        "先别急着说这没用，往下看。\n"
    )
    r = verify_anti_ai_blacklist(_write_md(tmp_path, body))
    assert r["verdict"] == "fail"
    meta_hits = [e for e in r["errors"] if "导游腔元话语" in e]
    assert len(meta_hits) >= 9  # 9 类触发词全部命中（8 类原有 + 2026-07-02 悬念延迟「先别急着」）

def test_meta_discourse_clean_text_passes(tmp_path):
    from scripts.contracts import verify_anti_ai_blacklist
    body = (
        "微信想动的，是你自己点的那一步。\n\n"
        "点单页面本来就是小程序。小程序跑在微信自己的地盘上，这件事最关键。\n\n"
        "传输比特，那就是流量费。\n"
    )
    r = verify_anti_ai_blacklist(_write_md(tmp_path, body))
    meta_hits = [e for e in r["errors"] if "导游腔元话语" in e]
    assert meta_hits == []

def test_ai_artifact_hits_are_hard_errors(tmp_path):
    # C16 融合 avoid-ai-writing 候选1：AI 工具指纹 / 未填占位符 = 硬错(扫原文,含URL)
    from scripts.contracts import verify_anti_ai_blacklist
    body = (
        "这个工具真不错，详情看这里 https://example.com/x?utm_source=chatgpt.com 。\n\n"
        "[待核实] 它大概发布于 2026-XX-XX 。\n\n"
        "另参考 citeturn0search1 的说法。\n"
    )
    r = verify_anti_ai_blacklist(_write_md(tmp_path, body))
    assert r["verdict"] == "fail"
    art_hits = [e for e in r["errors"] if "AI 残留物" in e]
    assert len(art_hits) >= 3  # utm_source + [待核实]占位 + 日期占位 + citeturn

def test_ai_artifact_clean_text_passes(tmp_path):
    from scripts.contracts import verify_anti_ai_blacklist
    body = "微信想动的，是你自己点的那一步。点单页面本来就是小程序。\n"
    r = verify_anti_ai_blacklist(_write_md(tmp_path, body))
    art_hits = [e for e in r["errors"] if "AI 残留物" in e]
    assert art_hits == []


# --- 2026-06-10 P1-6 量化体检报告（永不阻塞,verdict 恒 info）---

def test_audit_quant_signals_reports_info(tmp_path):
    from scripts.contracts import audit_quant_signals
    body = (
        "微信想动的，是你自己点的那一步。\n\n"
        "早上醒来先刷一遍未读，地铁口扫码进站，中午在群里接龙订饭，下午给客户发一份合同，晚上又在某个小程序里把物业费交了，非常非常快。\n\n"
        "快。\n\n点单页面本来就是小程序，小程序跑在微信自己的地盘上，这件事最关键，它显著迅速地改变了全部生态格局！\n"
    )
    p = tmp_path / "定稿.md"
    p.write_text("---\ntitle: t\n---\n\n" + body, encoding="utf-8")
    r = audit_quant_signals(str(p))
    assert r["verdict"] == "info"          # 永不 fail
    assert "para_count" in r["metrics"]
    assert isinstance(r["notes"], list) and r["notes"]

def test_audit_quant_signals_missing_file():
    from scripts.contracts import audit_quant_signals
    r = audit_quant_signals("Z:/不存在/定稿.md")
    assert r["verdict"] == "no_article"


def test_audit_quant_signals_new_style_hints_are_soft(tmp_path):
    from scripts.contracts import audit_quant_signals
    long_de = "这是一个把昨天仍在争论的产品路线、今天刚公布的用户反馈和团队内部几轮复盘全部叠在一起的判断，真正的问题还在后面。"
    body = (
        f"{long_de}\n\n{long_de}\n\n"
        "同一个开头，第一段。\n\n"
        "同一个开头，第二段。\n\n"
        "同一个开头，短。\n\n"
        "很快。\n\n就停。\n\n再来。\n\n"
        "它像一把伞，也仿佛一堵墙，如同一条突然拐弯的路。"
    )
    p = tmp_path / "定稿.md"
    p.write_text(body, encoding="utf-8")
    r = audit_quant_signals(str(p))
    assert r["verdict"] == "info"
    assert r["metrics"]["long_fronted_clauses"] >= 2
    assert r["metrics"]["long_sents_many_de"] >= 2
    assert r["metrics"]["repeated_para_openers"]["同一个开"] == 3
    assert r["metrics"]["max_short_single_para_run"] >= 3
    assert r["metrics"]["max_metaphors_per_250_chars"] >= 3
    assert all("阻塞" not in note for note in r["notes"])
