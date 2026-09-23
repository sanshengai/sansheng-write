# -*- coding: utf-8 -*-
"""`visual_pixel_checks.py` 的像素级硬校验（2026-09-23 审计 G4 补丁）。

背景：`ghost_layer_subdued`（封面 ghost 层不透明度）与封面右下角品牌水印，
过去 10 项视觉判据里只有这两项**可量化**却完全靠看图模型主观转述判断。
本文件覆盖：

1. 契约内/超标/未画三种 ghost 层场景，且要求反解出来的不透明度数值本身
   要跟合成时用的真实 alpha 接近（不是只判"有没有"的粗粒度断言）。
2. `shape_plausible` 安全阀：候选像素占比过高时必须拒绝报数字，而不是
   硬凑一个误导性的"不透明度"。
3. 水印在深底/浅底两种版式下的有/无四种组合。
4. `compute_cover_pixel_checks` 的磁盘 IO 入口：正常读图、以及读到坏文件时
   优雅降级成 `error` 字段而不是抛异常炸穿调用方。

合成图用真实 alpha 合成（`Image.alpha_composite`），不是凭空断言：ghost/水印
矩形按 `(1-alpha)*背景 + alpha*前景` 真实混合，这样"反解出来的不透明度接近
合成时用的 alpha"才是一句有意义的话，而不是自己骗自己。
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from scripts import visual_pixel_checks as vpc


DARK_BG = (14, 14, 16)
LIGHT_BG = (238, 234, 226)


def _alpha_paste(base: Image.Image, box, rgb, opacity: float) -> Image.Image:
    """把 `rgb` 以 `opacity` 真混合进 `box`（真实 alpha 合成，不是凭空赋值）。"""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle(box, fill=(*rgb, int(round(opacity * 255))))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _make_cover(
    *,
    size: tuple[int, int] = (1584, 672),
    background: tuple[int, int, int] = DARK_BG,
    ghost_opacity: float | None = None,
    watermark: bool = False,
) -> Image.Image:
    """montage-evidence 封面的最小合成替身：深/浅底 + 一排纯白"标题笔画" +
    可选的半透明 ghost 行 + 可选的、按 add_logo.js 同一套版式与黑白判定
    规则贴的品牌水印。

    标题画成 9 段不透明白色矩形（模拟粗体大写字母的整体覆盖形状与间隙），
    落在纵向 34%-50% —— 这正是 `measure_ghost_layer` 靠行投影定位"标题带"
    所需要的信号；ghost 行贴在标题正上方一条窄带，宽高与真实封面同数量级。
    """
    width, height = size
    img = Image.new("RGB", size, background)

    title_top = int(height * 0.34)
    title_bottom = int(height * 0.50)
    x = int(width * 0.06)
    for _ in range(9):
        w = int(width * 0.032)
        img.paste((255, 255, 255), (x, title_top, x + w, title_bottom))
        x += w + int(width * 0.010)

    if ghost_opacity is not None:
        ghost_bottom = title_top - int(height * 0.02)
        ghost_top = ghost_bottom - int(height * 0.05)
        gx = int(width * 0.06)
        for _ in range(9):
            w = int(width * 0.032)
            img = _alpha_paste(
                img, (gx, ghost_top, gx + w, ghost_bottom), (255, 255, 255), ghost_opacity
            )
            gx += w + int(width * 0.010)

    if watermark:
        pad_x = int(width * 0.02)
        pad_y = int(height * 0.02)
        logo_w = int(width * 0.12)
        logo_h = int(logo_w * 0.36)  # 与真实品牌 logo 的宽高比同量级（828x301）
        x2 = width - pad_x
        y2 = height - pad_y
        x1 = x2 - logo_w
        y1 = y2 - logo_h
        # 与 add_logo.js 完全同一条判定：右下角亮度决定贴白字还是黑字 logo。
        sample_luma = 0.299 * background[0] + 0.587 * background[1] + 0.114 * background[2]
        color = (0, 0, 0) if sample_luma > 128 else (255, 255, 255)
        img = _alpha_paste(img, (x1, y1, x2, y2), color, 0.35)

    return img


# ---------------------------------------------------------------------------
# ghost 层
# ---------------------------------------------------------------------------


def test_ghost_layer_in_contract_range_is_detected_and_in_range():
    measurement = vpc.measure_ghost_layer(_make_cover(ghost_opacity=0.11))
    assert measurement["detected"] is True
    verdict = vpc.evaluate_ghost_layer(measurement)
    assert verdict["contract_verdict"] == "in_range"
    assert verdict["in_contract_range"] is True


def test_ghost_layer_far_above_contract_is_rejected():
    """明显比标题还抢眼（45% 不透明度）：这正是 CHECK_DEFINITIONS 里
    ghost_layer_subdued 要拦的反面案例，必须能被机械判 false（above_range）。"""
    measurement = vpc.measure_ghost_layer(_make_cover(ghost_opacity=0.45))
    assert measurement["detected"] is True
    verdict = vpc.evaluate_ghost_layer(measurement)
    assert verdict["contract_verdict"] == "above_range"
    assert verdict["in_contract_range"] is False


def test_ghost_layer_below_contract_is_flagged_not_silently_passed():
    measurement = vpc.measure_ghost_layer(_make_cover(ghost_opacity=0.03))
    assert measurement["detected"] is True
    verdict = vpc.evaluate_ghost_layer(measurement)
    assert verdict["contract_verdict"] == "below_range"
    assert verdict["in_contract_range"] is False


def test_ghost_layer_missing_is_reported_as_not_detected_not_a_fake_zero():
    """没画 ghost 层：必须诚实报「未检测到」，不能编造一个 0% 或任意数字。"""
    measurement = vpc.measure_ghost_layer(_make_cover(ghost_opacity=None))
    assert measurement["detected"] is False
    assert measurement["estimated_opacity"] is None
    verdict = vpc.evaluate_ghost_layer(measurement)
    assert verdict["contract_verdict"] == "not_detected"
    assert verdict["in_contract_range"] is None


def test_ghost_layer_estimate_tracks_the_real_composited_opacity():
    """核心可信度检验：反解出来的数值必须贴近合成用的真实 alpha（<=1 个百分点），
    不能只是方向对、幅度乱猜 —— 否则连"偏淡多少/偏浓多少"都无法向作者交代。
    """
    for true_opacity in (0.05, 0.08, 0.11, 0.14, 0.20, 0.30):
        measurement = vpc.measure_ghost_layer(_make_cover(ghost_opacity=true_opacity))
        estimated = measurement["estimated_opacity"]
        assert estimated is not None, true_opacity
        assert abs(estimated - true_opacity) < 0.01, (true_opacity, measurement)


def test_ghost_layer_rejects_implausible_shape_instead_of_guessing():
    """候选像素占比一旦被判定"太像一整块背景装饰、不像一行字"，必须拒绝给出
    不透明度数字（`shape_plausible=False` → `detected` 仍为 False），而不是
    在光束/渐变上硬算出一个具体百分比误导使用者。

    用一张普通、已确认能测准的 ghost 图（0.11 不透明度，见上一条测试），
    只把 `shape_max_ratio` 收紧到远低于它实际候选像素占比的值 ——
    这是该安全阀在真实候选像素占比超过阈值时的行为，不依赖精心构造的
    极端合成图。
    """
    img = _make_cover(ghost_opacity=0.11)
    baseline = vpc.measure_ghost_layer(img)
    assert baseline["candidate_pixel_ratio"] > 0.05  # 确认默认阈值下能正常测到

    strict = vpc.measure_ghost_layer(img, shape_max_ratio=0.05)
    assert strict["shape_plausible"] is False
    assert strict["detected"] is False
    assert strict["estimated_opacity"] is None

    verdict = vpc.evaluate_ghost_layer(strict)
    assert verdict["contract_verdict"] == "ambiguous_background"
    assert verdict["in_contract_range"] is None


def test_evaluate_ghost_layer_notes_are_advisory_not_accusatory():
    """三条判词都必须自带"仅报告/仅供参考"的免责语，防止未来有人把这份
    note 原样当成拦截理由抄进 failures 列表——见模块顶部 warn-only 说明。
    """
    detected_high = vpc.evaluate_ghost_layer(
        vpc.measure_ghost_layer(_make_cover(ghost_opacity=0.30))
    )
    not_detected = vpc.evaluate_ghost_layer(
        vpc.measure_ghost_layer(_make_cover(ghost_opacity=None))
    )
    assert "仅报告" in detected_high["note"] or "参考" in detected_high["note"]
    assert "自动测量" in not_detected["note"]


# ---------------------------------------------------------------------------
# 水印
# ---------------------------------------------------------------------------


def test_watermark_detected_on_dark_background_with_light_logo():
    result = vpc.measure_watermark_presence(_make_cover(background=DARK_BG, watermark=True))
    assert result["expected_variant"] == "light-logo-on-dark-bg"
    assert result["likely_present"] is True


def test_watermark_detected_on_light_background_with_dark_logo():
    result = vpc.measure_watermark_presence(_make_cover(background=LIGHT_BG, watermark=True))
    assert result["expected_variant"] == "dark-logo-on-light-bg"
    assert result["likely_present"] is True


def test_watermark_absent_is_not_falsely_claimed_present_dark_bg():
    result = vpc.measure_watermark_presence(_make_cover(background=DARK_BG, watermark=False))
    assert result["likely_present"] is False


def test_watermark_absent_is_not_falsely_claimed_present_light_bg():
    result = vpc.measure_watermark_presence(_make_cover(background=LIGHT_BG, watermark=False))
    assert result["likely_present"] is False


# ---------------------------------------------------------------------------
# compute_cover_pixel_checks（唯一磁盘 IO 入口）
# ---------------------------------------------------------------------------


def test_compute_cover_pixel_checks_reads_from_disk(tmp_path):
    path = tmp_path / "cover.png"
    _make_cover(ghost_opacity=0.10, watermark=True).save(path)

    checks = vpc.compute_cover_pixel_checks(path)

    assert checks["schema_version"] == 1
    assert "error" not in checks
    assert checks["ghost_layer"]["detected"] is True
    assert checks["watermark"]["likely_present"] is True


def test_compute_cover_pixel_checks_degrades_gracefully_on_bad_file(tmp_path):
    """辅助测量不能因为一张读不出来的图就把整条视觉 QA 请求构建炸掉。"""
    path = tmp_path / "not-an-image.png"
    path.write_bytes(b"this is not a real png")

    checks = vpc.compute_cover_pixel_checks(path)

    assert checks["schema_version"] == 1
    assert "error" in checks
    assert "ghost_layer" not in checks
    assert "watermark" not in checks
