# tests/golden/_synthetic_cover/make_fixtures.py
"""确定性合成封面 PNG fixture 生成器（P4.2 tier-2 验证门测试用）。

**不在仓里存二进制 PNG**：每次由 Pillow 按固定 (w,h)+纯色确定性现造到
传入的临时目录，跑完即弃（与 _synthetic_infographic/make_fixtures.py
同构 —— verify_cover_set 要做磁盘 IO 读真实像素判 2.35:1 / 1K，故必须
真造文件，不能像 research/content_enhance 纯 dict）。这样
regression_baseline.py P4 门 与 pytest 共用同一套「合规组 / 各违规组」
生成逻辑，单一事实源、零仓库膨胀、hermetic（不依赖外部素材、不烧
baoyu-cover-image 生图配额）。

每组返回 (candidates, selected, recent_covers) 三元组（candidates 与
_OUTPUT_SCHEMA cover 的 candidates 同形，每项带 path/style），交给
contracts.verify_cover_set 校验：
  - compliant            合规：≥2 候选、selected∈candidates、2.35:1、1K、
                          风格不撞近 3 篇
  - bad_selected_not_in  违规①：selected 不在 candidates 路径集合
  - bad_too_few           违规②：仅 1 个候选（< 多风格打样下限 2）
  - bad_missing_file      违规③：某候选 path 指向不存在文件
  - bad_not_1k            违规④：某候选长边 800（< 1K 下界 900）
  - bad_ratio             违规⑤：某候选 16:9（非 cinematic 2.35:1）
  - bad_recent_repeat     违规⑥：selected 风格命中近 3 篇

设计要点（与 _synthetic_content_enhance「单一违因」精神一致）：每个
bad_* 组**只**从合规基线变异**一个**维度，其余保持合规基线原样，确保
该组只精确触发目标规则、不夹带无关噪声（便于 pytest/P4 门按规则名
精确断言）。风格字符串取自 cover-styles.md 5 风格池（briefing /
noir / montage-evidence / montage-pipeline / montage-starry），但内容是
确定性手构桩，不代表任何真实封面产出。
"""
from PIL import Image

# 2.35:1 cinematic 标称：长边（宽）1024 时高 ≈ 1024*100/235 ≈ 436。
# 复用 contracts._K1_* 既定 1K 带（[900,1200]）：1024 落带内。
_LONG = 1024
_BRAND = (47, 111, 143)  # 中性填充纯色（primary slate），纯色即可（本门只读尺寸，不读内容）


def _ratio_dims(longedge=_LONG):
    """2.35:1：宽=longedge（横图长边），高=round(宽*100/235)。"""
    return (longedge, round(longedge * 100 / 235))


def _png(dirpath, name, w, h):
    p = dirpath / name
    Image.new("RGB", (w, h), _BRAND).save(str(p), "PNG", optimize=True)
    return str(p)


def build_groups(dirpath):
    """dirpath: pathlib.Path（已存在的临时目录）。返回
    dict[str, (candidates, selected, recent_covers)]。全确定性手构。"""
    w, h = _ratio_dims()

    # 合规基线：2 个 2.35:1 / 1K 候选，风格不撞近 3 篇（近 3 篇用 noir
    # / briefing / montage-pipeline，selected=montage-evidence 不撞且
    # 注意：montage 同源家族回避——故 recent 不放任何 montage，避免合规
    # 基线被规则⑥ montage 同源关误报）。
    recent_ok = ["noir", "briefing", "noir"]  # 近 3 篇，无 montage 家族

    def _base_cands(prefix):
        return [
            {"path": _png(dirpath, f"{prefix}_evi.png", w, h),
             "style": "montage-evidence", "aspect": "2.35:1"},
            {"path": _png(dirpath, f"{prefix}_brief.png", w, h),
             "style": "briefing", "aspect": "2.35:1"},
        ]

    groups = {}

    base = _base_cands("c")
    groups["compliant"] = (base, base[0]["path"], recent_ok)

    # 违规①：selected 指向一个根本不在 candidates 里的 path（不可追溯）
    s1 = _base_cands("s1")
    groups["bad_selected_not_in"] = (
        s1, "素材/cover/candidates/完全不在里面.png", recent_ok)

    # 违规②：仅 1 个候选（< 多风格打样下限 2）—— 单张=没并行打样
    one = [{"path": _png(dirpath, "few_only.png", w, h),
            "style": "montage-evidence", "aspect": "2.35:1"}]
    groups["bad_too_few"] = (one, one[0]["path"], recent_ok)

    # 违规③：某候选 path 指向不存在文件（不真造该 png）
    mf = [
        {"path": _png(dirpath, "mf_ok.png", w, h),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": str(dirpath / "mf_缺失.png"),  # 故意不造
         "style": "briefing", "aspect": "2.35:1"},
    ]
    groups["bad_missing_file"] = (mf, mf[0]["path"], recent_ok)

    # 违规④：某候选长边 800（< 1K 下界 900），仍保持 2.35:1 比例
    nk_w = 800
    nk_h = round(nk_w * 100 / 235)
    nk = [
        {"path": _png(dirpath, "nk_ok.png", w, h),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _png(dirpath, "nk_small.png", nk_w, nk_h),  # 长边 800
         "style": "briefing", "aspect": "2.35:1"},
    ]
    groups["bad_not_1k"] = (nk, nk[0]["path"], recent_ok)

    # 违规⑤：某候选 16:9（非 cinematic 2.35:1），长边仍 1K
    r16_w, r16_h = 1024, 576  # 16:9
    rr = [
        {"path": _png(dirpath, "rr_ok.png", w, h),
         "style": "montage-evidence", "aspect": "2.35:1"},
        {"path": _png(dirpath, "rr_169.png", r16_w, r16_h),  # 16:9 非 cinematic
         "style": "briefing", "aspect": "2.35:1"},
    ]
    groups["bad_ratio"] = (rr, rr[0]["path"], recent_ok)

    # 违规⑥：selected 风格命中近 3 篇（近 3 篇含 noir，selected=noir 撞车）。
    # 候选/比例/1K 全合规，只违风格回避（单一违因）。
    rp = [
        {"path": _png(dirpath, "rp_noir.png", w, h),
         "style": "noir", "aspect": "2.35:1"},
        {"path": _png(dirpath, "rp_brief.png", w, h),
         "style": "briefing", "aspect": "2.35:1"},
    ]
    groups["bad_recent_repeat"] = (rp, rp[0]["path"], ["noir", "briefing", "noir"])

    return groups
