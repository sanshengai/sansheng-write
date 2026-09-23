#!/usr/bin/env python3
"""封面视觉 QA 的像素级确定性测量（G4 体检补丁）。

背景：`visual_qa_codex.py::CHECK_DEFINITIONS` 里 `ghost_layer_subdued` /
`composition_contract_match` 全靠看图模型主观转述判断，历史上 103 次独立复核只打回
过 2 次。本模块给其中**可以被量化**的两项补一条确定性测量：

1. `measure_ghost_layer`：封面左侧文字区，标题后方那行半隐英文 ghost 层相对局部
   背景的有效不透明度估算（契约 `profile.example/brand.yaml` 写的是 8%-14%）。
2. `measure_watermark_presence`：封面右下角是否存在 `add_logo.js` 风格的品牌水印
   （12% 宽、2% 内边距、35% 不透明度）的辅助像素判定。

🔴 两者都只是**辅助测量，不是新的硬门**（2026-09-23 作者拍板）：

- **基线数据**（2026-09-23 量的，`/Users/sandy/Cowork/文稿成品/*/素材/cover.png`，
  含要求的 100-108 号全部现存封面，外加 77-99 号扩大样本，共 99 张只读实测，
  不进本仓）：
  - ghost 层：99 张里 81 张（82%）测到候选像素簇；测到的里只有 27 张（33%）
    落在契约写的 8%-14% 范围内，其余明显偏淡或偏浓（例如第 90 篇约 5.7%、
    第 20 篇约 16.0%）；100-108 号这个必测区间里 9 张全部测到候选像素簇，
    但只有 2 张（105、107）落在 8%-14%，其余 7 张在 4.8%-7.5% 之间
    （包括肉眼确认过、观感正常的第 108 篇实测 7.5%）。
  - 结论：契约数字是**设计目标**，不是当前生产分布的真实约束；拿
    `in_contract_range` 当硬门会把大量已发布、作者认可的封面判 fail，
    所以只接成 warn。
  - 水印：99 张里 96 张（97%）测到符合 35% 不透明度特征的像素簇；
    100-108 号必测区间 9 张全部命中（100%）。另外 3 张未命中的
    （`2-我用小龙虾给酒吧招了个CFO`、`15-openclaw-vs-claude-code`、
    `18-安利「读书软件」`）经目视核实是**引入 `add_logo.js` 水印惯例之前的
    老封面**，本来就没有水印 —— 是真阴性，不是漏检。这项即使已经很准，
    仍然只做辅助信号：它检测的是「像素特征像不像水印」，不是水印台账
    要核对的「这个字节是否真的跑过 add_logo.js 且之后没被别的工序动过」，
    两者不能互相替代。
- 因此 `visual_qa.py::run_visual_qa` 只把这两个函数的输出当成**只报告不拦截**的
  `pixel_checks` 字段合并进 `_visual-qa.json` / `_visual-qa.md`，从不写入
  `validation_findings`/`errors`，不影响 `status`。
- 何时可以切成硬门：积累至少一个真实发布周期（建议 ≥20 篇新增封面）的
  `pixel_checks.ghost_layer` 记录后，如果 `contract_verdict` 落在
  `in_range`/`below_range`/`above_range` 的分布里，`below_range`/`above_range`
  与人工目测「ghost 层过淡看不见」或「比标题还抢眼」高度重合（而不是把正常
  作品也判出界），再考虑把 `in_contract_range is False` 接成 fail，并同时把
  这份基线数据贴进 PR/评审记录。

两个测量函数都是纯函数（只读 PIL Image，不碰磁盘/网络），可独立单测；
`compute_cover_pixel_checks` 是唯一的磁盘 IO 入口，供 `visual_qa.py` 调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# ghost layer（封面左侧文字区，标题后方的半隐英文）
# ---------------------------------------------------------------------------

# 版式合同（left-50-gap-6-right-44）里左栏约占 44%-52%；取上限再放宽一点，
# 保证 ghost 行即使贴着标题右边缘也落在采样区内。
GHOST_LEFT_FRACTION = 0.55
# 上下各切掉一点边缘，避开画布最边缘的渐晕/光线笔触造成的极端值。
GHOST_VERTICAL_MARGIN = 0.05
# 主标题按配方是纯白色实心笔画，用它定位「标题第一行在哪一行」：
# 一行里近白像素占比超过该阈值，才算落在标题笔画上（用来把 ghost 的搜索范围
# 收窄到标题正上方一条窄带，而不是整个左栏 —— 早期版本扫全栏，
# 结果把光束/渐变等大面积中间调背景全部计成候选像素，占比虚高到 20%-45%，
# 与「一行字」的真实占比数量级完全不符，见模块顶部基线数据）。
GHOST_TITLE_LUMA_FLOOR = 235.0
GHOST_ROW_COVERAGE_MIN = 0.02
# 标题笔画行判定允许的行间断（像素）：字形笔画之间偶尔有 1-2 行空隙，
# 不应被当成「标题第一行已经结束」。
GHOST_ROW_GAP_TOLERANCE = 2
# ghost 搜索带高度：用检测到的标题第一行高度做基准（ghost 字号不大于标题），
# 但夹在 [min, max] 之间，防止标题行检测异常时搜索带塌缩为 0 或撑爆整个区域。
GHOST_BAND_HEIGHT_MIN_FRACTION = 0.03
GHOST_BAND_HEIGHT_MAX_FRACTION = 0.22
# 候选像素的亮度带按「相对不透明度」而不是绝对亮度定义，边界比契约的 8%-14%
# 更宽松，好让「明显偏淡」「明显过重」也能落进候选簇、被判成 below/above_range，
# 而不是直接漏检；真正的契约判定仍以 GHOST_CONTRACT_LOW/HIGH 为准。
GHOST_BAND_OPACITY_LOW = 0.02
# 上界必须明显高于 GHOST_CONTRACT_HIGH，否则「明显画得比标题还抢眼」的 ghost
# 反而会因为超出扫描带上界被直接漏检（候选像素归零→判「未检测到」），
# 而不是被扣上应得的 above_range —— 等于放过了本方法最该抓的那种反例。
GHOST_BAND_OPACITY_HIGH = 0.6
# 候选像素占搜索带的比例：太低=没画东西；太高=更像一整块渐变/光束而不是
# 一行字的笔画覆盖率，这种情况宁可标「不可信」也不要报一个假不透明度数字。
# 🔴 背景亮度取的是搜索带自身的中位数，数学上「比背景亮」的像素永远不可能
# 超过该带一半（中位数定义使然）；上限必须 < 0.5 才有意义，定成 ≥0.5 等于
# 永远不会触发。99 张真实基线里最高的是 0.486（第 54 篇），故取 0.49，
# 刚好卡在理论上限内侧、又不影响当前基线里任何一张的判定。
GHOST_SHAPE_MIN_RATIO = 0.02
GHOST_SHAPE_MAX_RATIO = 0.49
# 品牌契约写的范围（profile.example/brand.yaml 的 required_visual_traits）。
GHOST_CONTRACT_LOW = 0.08
GHOST_CONTRACT_HIGH = 0.14


def measure_ghost_layer(
    image: Image.Image,
    *,
    left_fraction: float = GHOST_LEFT_FRACTION,
    vertical_margin: float = GHOST_VERTICAL_MARGIN,
    title_luma_floor: float = GHOST_TITLE_LUMA_FLOOR,
    row_coverage_min: float = GHOST_ROW_COVERAGE_MIN,
    row_gap_tolerance: int = GHOST_ROW_GAP_TOLERANCE,
    band_height_min_fraction: float = GHOST_BAND_HEIGHT_MIN_FRACTION,
    band_height_max_fraction: float = GHOST_BAND_HEIGHT_MAX_FRACTION,
    band_opacity_low: float = GHOST_BAND_OPACITY_LOW,
    band_opacity_high: float = GHOST_BAND_OPACITY_HIGH,
    shape_min_ratio: float = GHOST_SHAPE_MIN_RATIO,
    shape_max_ratio: float = GHOST_SHAPE_MAX_RATIO,
) -> dict[str, Any]:
    """估算封面左侧文字区 ghost 层相对局部背景的有效不透明度。

    两步法（v2，见上面常量注释里 v1 的失败教训）：

    1. **定位标题第一行**：在左侧文字区内按行统计「近白像素占比」，找到第一段
       连续的高占比行 —— 那是主标题笔画（配方规定纯白实色），不是 ghost。
    2. **只在标题正上方一条窄带里量 ghost**：带高按标题行自身高度估计（ghost
       字号不大于标题），带内用中位数亮度当局部背景，取「比背景亮但没到纯白
       那一档」的像素簇按 `(簇均值 − 背景) / (255 − 背景)` 反解不透明度。

    仍是近似：光束/渐变类背景装饰如果恰好压在标题正上方，会被一起计入候选簇；
    `shape_plausible=False`（候选像素占比过高，不像一行字的笔画覆盖率）就是
    专门标记这种情况的信号 —— 调用方看到它应把 `estimated_opacity` 当不可信、
    只参考 `detected`/`shape_plausible` 本身。
    """
    import numpy as np

    rgb = image.convert("RGB") if image.mode != "RGB" else image
    width, height = rgb.size
    left_width = max(1, min(width, int(round(width * left_fraction))))
    top = max(0, int(round(height * vertical_margin)))
    bottom = max(top + 1, height - top)
    bottom = min(bottom, height)
    region = rgb.crop((0, top, left_width, bottom)).convert("L")
    arr = np.asarray(region, dtype=np.float64)
    region_h, region_w = arr.shape

    result: dict[str, Any] = {
        "method": "title-band-projection-v2",
        "region_box": [0, top, left_width, bottom],
        "title_band": None,
        "search_band": None,
        "background_luma": None,
        "candidate_pixel_ratio": None,
        "ghost_luma_mean": None,
        "estimated_opacity": None,
        "shape_plausible": None,
        "detected": False,
    }
    if arr.size == 0 or region_h < 4 or region_w < 4:
        return result

    row_coverage = (arr >= title_luma_floor).mean(axis=1)
    title_rows = np.flatnonzero(row_coverage >= row_coverage_min)
    if title_rows.size == 0:
        return result

    title_top = int(title_rows[0])
    run_end = title_top
    for row_index in title_rows:
        if row_index <= run_end + row_gap_tolerance:
            run_end = int(row_index)
        else:
            break
    result["title_band"] = [title_top + top, run_end + top]

    band_h = run_end - title_top + 1
    band_h = max(int(round(region_h * band_height_min_fraction)), band_h)
    band_h = min(band_h, int(round(region_h * band_height_max_fraction)))
    search_top = max(0, title_top - band_h)
    search_bottom = title_top
    if search_bottom - search_top < 2:
        return result
    result["search_band"] = [search_top + top, search_bottom + top]

    band = arr[search_top:search_bottom, :]
    background_luma = float(np.median(band))
    result["background_luma"] = round(background_luma, 2)

    denom = 255.0 - background_luma
    if denom <= 1e-6:
        return result
    lower = background_luma + band_opacity_low * denom
    upper = background_luma + band_opacity_high * denom
    if upper <= lower:
        return result

    mask = (band >= lower) & (band < upper)
    total = int(band.size)
    candidate_count = int(mask.sum())
    candidate_ratio = candidate_count / total if total else 0.0
    result["candidate_pixel_ratio"] = round(candidate_ratio, 6)
    if candidate_count == 0 or candidate_ratio < shape_min_ratio:
        return result

    result["shape_plausible"] = bool(candidate_ratio <= shape_max_ratio)
    if not result["shape_plausible"]:
        # 候选像素铺满了大半条搜索带：更像一整块渐变/光束，不是一行字的
        # 笔画覆盖率。仍然只是把话说清楚、不硬凑一个不透明度，不代表判定失败。
        return result

    ghost_luma_mean = float(band[mask].mean())
    result["ghost_luma_mean"] = round(ghost_luma_mean, 2)
    result["detected"] = True
    opacity = (ghost_luma_mean - background_luma) / denom
    result["estimated_opacity"] = round(max(0.0, min(1.0, opacity)), 4)
    return result


def evaluate_ghost_layer(
    measurement: dict[str, Any],
    *,
    low: float = GHOST_CONTRACT_LOW,
    high: float = GHOST_CONTRACT_HIGH,
) -> dict[str, Any]:
    """把 `measure_ghost_layer` 的原始测量换算成人可读的判定文案（仅供参考）。"""
    if measurement.get("shape_plausible") is False:
        return {
            "contract_verdict": "ambiguous_background",
            "in_contract_range": None,
            "note": (
                "自动测量：标题正上方候选像素铺满了大半条搜索带，更像大片渐变/光束"
                "而非一行字的笔画覆盖率，本方法拒绝给出不透明度数字（宁可不测也不误报）"
            ),
        }
    if not measurement.get("detected"):
        return {
            "contract_verdict": "not_detected",
            "in_contract_range": None,
            "note": (
                "自动测量：标题正上方未找到明显的 ghost 候选像素簇"
                "（可能没画 ghost 层，也可能不透明度低于本方法的测量灵敏度，"
                "也可能没能定位到标题行）"
            ),
        }
    opacity = measurement.get("estimated_opacity")
    if opacity is None:
        return {
            "contract_verdict": "unmeasurable",
            "in_contract_range": None,
            "note": "自动测量：检测到候选像素簇，但背景亮度过高导致无法换算不透明度",
        }
    if opacity < low:
        verdict, in_range = "below_range", False
    elif opacity > high:
        verdict, in_range = "above_range", False
    else:
        verdict, in_range = "in_range", True
    note = (
        f"自动测量：ghost 层有效不透明度约 {opacity:.1%}"
        f"（契约参考范围 {low:.0%}-{high:.0%}），判定 {verdict}"
        "（仅报告，不参与发布拦截，见模块顶部说明）"
    )
    return {"contract_verdict": verdict, "in_contract_range": in_range, "note": note}


# ---------------------------------------------------------------------------
# 品牌水印（封面右下角，add_logo.js 的固定版式）
# ---------------------------------------------------------------------------

# 与 add_logo.js 完全一致的版式常量：12% 宽、2% 内边距、右下角。
WATERMARK_PADDING_FRACTION = 0.02
WATERMARK_WIDTH_FRACTION = 0.12
# add_logo.js 只按宽度缩放 logo，真实高度取决于每个账号自己的 logo 文件宽高比
# （品牌素材是私有配置，公开 skill 不能假设固定比例）。这里放宽搜索框，
# 用「一个明显比 12% 宽还大」的区域兜住各种宽高比的真实 logo。
WATERMARK_SEARCH_MARGIN = 1.6
WATERMARK_SEARCH_HEIGHT_FRACTION = 0.24
# add_logo.js 写死 35% 不透明度、且按右下角取样亮度自适应选白/黑字 logo
# （同一分界 128）。这两个数字是本方法唯一能确定的先验，直接拿来比「与相邻
# 对照区比纹理」更准 —— 基线曾用后一种方法测 99 张真实封面，
# 命中率只有 54%（第 108 篇肉眼可见水印，仍判「未检测到」，因为水印正左侧
# 恰好是场景里立体挂件的阴影，比 logo 本身纹理还重，对照区选址不可靠）。
WATERMARK_OPACITY_ESTIMATE = 0.35
# 容忍窗口要覆盖「实际不透明度较真实合成有偏差」与「取样框里背景本身有渐变」，
# 基线里把窗口收紧到 ±0.12 以内会漏掉一部分已知带水印的老封面。
WATERMARK_OPACITY_TOLERANCE = 0.20
# logo 只占搜索框一小部分面积（周围大量透明留白），候选像素占比门槛不能定太高。
WATERMARK_MIN_CANDIDATE_RATIO = 0.01
# 与 add_logo.js 的 LIGHT_BG_THRESHOLD 同一分界，用来决定該找变亮还是变暗的簇。
WATERMARK_LIGHT_BG_THRESHOLD = 128.0


def measure_watermark_presence(
    image: Image.Image,
    *,
    padding_fraction: float = WATERMARK_PADDING_FRACTION,
    width_fraction: float = WATERMARK_WIDTH_FRACTION,
    search_margin: float = WATERMARK_SEARCH_MARGIN,
    search_height_fraction: float = WATERMARK_SEARCH_HEIGHT_FRACTION,
    opacity_estimate: float = WATERMARK_OPACITY_ESTIMATE,
    opacity_tolerance: float = WATERMARK_OPACITY_TOLERANCE,
    min_candidate_ratio: float = WATERMARK_MIN_CANDIDATE_RATIO,
    light_bg_threshold: float = WATERMARK_LIGHT_BG_THRESHOLD,
) -> dict[str, Any]:
    """右下角「是否存在 logo 特征」的辅助像素判定（不是台账核对的替代品）。

    方法：在 `add_logo.js` 实际贴图的右下角位置取一个放宽过的搜索框，用框内
    中位数亮度当「没有 logo 时大概长什么样」的局部背景估计，再按
    `add_logo.js` 写死的 35% 不透明度与黑白字判定分界，反推「如果这里真贴了
    logo，像素会漂移到哪个亮度」，检查搜索框里有没有一簇像素落在那个范围。

    这是启发式辅助信号，不做「水印是否合规」的最终裁决 —— 真正的水印合规
    台账核对在 pipeline 侧另有实现（`.postprocess-ledger.json` +
    `.gen-log.jsonl` sha 对账）。以不误伤为优先：判「未检测到」不代表水印
    不存在，只代表本方法在这张图的右下角没有量到符合该不透明度特征的像素簇。
    """
    import numpy as np

    rgb = image.convert("RGB") if image.mode != "RGB" else image
    width, height = rgb.size
    gray = np.asarray(rgb.convert("L"), dtype=np.float64)

    pad_x = int(round(width * padding_fraction))
    pad_y = int(round(height * padding_fraction))
    box_w = max(4, int(round(width * width_fraction * search_margin)))
    box_h = max(4, int(round(height * search_height_fraction)))

    x2 = max(1, width - pad_x)
    y2 = max(1, height - pad_y)
    x1 = max(0, x2 - box_w)
    y1 = max(0, y2 - box_h)
    corner = gray[y1:y2, x1:x2]

    result: dict[str, Any] = {
        "method": "corner-opacity-band-v2",
        "logo_search_box": [x1, y1, x2, y2],
        "background_luma": None,
        "expected_variant": None,
        "candidate_pixel_ratio": 0.0,
        "likely_present": False,
        "note": "",
    }
    if corner.size == 0:
        result["note"] = "自动测量：图片过小，搜索框为空，无法判定"
        return result

    background_luma = float(np.median(corner))
    result["background_luma"] = round(background_luma, 2)
    is_light_bg = background_luma > light_bg_threshold
    lo_alpha = max(0.0, opacity_estimate - opacity_tolerance)
    hi_alpha = min(1.0, opacity_estimate + opacity_tolerance)

    if is_light_bg:
        # 浅底配深字 logo：像素应比背景更暗（黑色以 alpha 混合进浅底）。
        result["expected_variant"] = "dark-logo-on-light-bg"
        hi = background_luma - lo_alpha * background_luma
        lo = background_luma - hi_alpha * background_luma
    else:
        # 深底配白字 logo：像素应比背景更亮（白色以 alpha 混合进深底）。
        result["expected_variant"] = "light-logo-on-dark-bg"
        denom = 255.0 - background_luma
        lo = background_luma + lo_alpha * denom
        hi = background_luma + hi_alpha * denom
    lo, hi = min(lo, hi), max(lo, hi)

    mask = (corner >= lo) & (corner <= hi)
    candidate_ratio = float(mask.mean())
    result["candidate_pixel_ratio"] = round(candidate_ratio, 6)
    likely_present = bool(candidate_ratio >= min_candidate_ratio)
    result["likely_present"] = likely_present
    result["note"] = (
        "自动测量：右下角量到一簇符合 35% 不透明度特征的像素，与品牌水印特征相符"
        "（辅助信号，非台账核验）"
        if likely_present
        else "自动测量：右下角未量到符合水印不透明度特征的像素簇"
        "（不代表水印一定缺失，台账核对以 pipeline 侧记录为准）"
    )
    return result


# ---------------------------------------------------------------------------
# 汇总入口
# ---------------------------------------------------------------------------


def compute_cover_pixel_checks(image_path: Path) -> dict[str, Any]:
    """唯一的磁盘 IO 入口：打开一次图片，跑两项测量，供 `visual_qa.py` 调用。

    任何异常都吞掉并落进 `error` 字段而不是向上抛 —— 这两项测量是辅助信号，
    不应该因为一张图片解码失败就把整条视觉 QA 流程带崩。
    """
    try:
        with Image.open(image_path) as raw:
            rgb = raw.convert("RGB")
            ghost = measure_ghost_layer(rgb)
            ghost_verdict = evaluate_ghost_layer(ghost)
            watermark = measure_watermark_presence(rgb)
    except Exception as exc:  # noqa: BLE001 - 辅助测量必须降级，不拖垮 QA 流程
        return {"schema_version": SCHEMA_VERSION, "error": f"像素检查失败：{exc}"}

    return {
        "schema_version": SCHEMA_VERSION,
        "ghost_layer": {**ghost, **ghost_verdict},
        "watermark": watermark,
    }
