"""封面真实肖像合成（scripts/cover_portrait.py）。

钉三件 2026-08-28 实拍定案里换来的判据：
  ① 照片区宽度按肖像自身比例反推 —— 铺满整高时不裁发顶；
  ② 暖调 LUT 是三段连续通道表（交错会把灰阶变蓝调）；
  ③ 声明缺来源或许可就拒绝 —— 真人肖像必须可追溯。
"""

import pathlib
import sys

import pytest
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import cover_portrait as cp  # noqa: E402

CANVAS = (3168, 1344)


def test_region_width_follows_portrait_ratio_so_head_is_not_cropped():
    # 竖构图肖像 800x1059（比例 0.755）
    x0, w, h = cp.photo_region(CANVAS, (800, 1059))
    assert h == CANVAS[1], "必须铺满整高"
    assert x0 + w == CANVAS[0], "必须顶到右边缘"
    # 照片区比例应贴住原图比例，这样才不需要垂直裁切
    assert abs(w / h - 800 / 1059) < 0.03


def test_region_width_is_clamped_for_extreme_portraits():
    _, wide, _ = cp.photo_region(CANVAS, (2000, 1000))     # 很宽的横图
    _, narrow, _ = cp.photo_region(CANVAS, (400, 1600))    # 很窄的竖图
    assert wide <= CANVAS[0] * cp.WIDTH_MAX, "过宽会吃掉文字区"
    assert narrow >= CANVAS[0] * cp.WIDTH_MIN, "过窄压不住画面"


def test_crop_keeps_top_of_head():
    src = Image.new("RGB", (800, 1059), (200, 200, 200))
    crop = cp.crop_for_region(src, (1015, 1344), (0.45, 0.34))
    # 比例贴合时不该从顶部让出任何像素（发顶完整）
    assert crop.size[1] == 1059


def test_warm_tone_stays_neutral_not_blue():
    src = Image.new("RGB", (10, 10), (128, 128, 128))
    out = cp.warm_tone(src)
    r, g, b = out.getpixel((5, 5))
    # 暖调：R ≥ G ≥ B。交错 LUT 的老 bug 会让 B 明显最大
    assert r >= g >= b, (r, g, b)
    assert b < r, "蓝通道不该压过红通道（LUT 通道错位的症状）"


def test_validate_requires_source_and_license(tmp_path):
    (tmp_path / "p.jpg").write_bytes(b"x")
    errs = cp.validate({"file": "p.jpg"}, tmp_path)
    assert any("source" in e for e in errs)
    assert any("license" in e for e in errs)


def test_validate_passes_with_full_declaration(tmp_path):
    (tmp_path / "p.jpg").write_bytes(b"x")
    spec = {"file": "p.jpg", "source": "馆藏页 URL", "license": "公有领域（作者卒年 + 70）"}
    assert cp.validate(spec, tmp_path) == []


def test_validate_rejects_bad_anchor(tmp_path):
    (tmp_path / "p.jpg").write_bytes(b"x")
    spec = {"file": "p.jpg", "source": "s", "license": "l", "anchor": [1.4, 0.3]}
    assert any("anchor" in e for e in cp.validate(spec, tmp_path))


def test_clean_right_erases_leftover_panel():
    # 造一张底板：右区中间画一块比背景亮的"面板"，抹完应当消失
    base = Image.new("RGB", (400, 200), (16, 16, 18))
    for x in range(240, 330):
        for y in range(40, 160):
            base.putpixel((x, y), (60, 60, 66))
    out = cp.clean_right(base, from_ratio=0.55)
    assert out.getpixel((300, 100))[0] < 30, "面板残留没被抹掉"


def test_compose_writes_bleeding_photo(tmp_path):
    cover = tmp_path / "cover.png"
    Image.new("RGB", (1584, 672), (16, 16, 18)).save(cover)
    portrait = tmp_path / "p.png"
    Image.new("RGB", (800, 1059), (210, 205, 195)).save(portrait)
    info = cp.compose(cover, portrait)
    assert info["photo_region"]["x"] + info["photo_region"]["width"] == 1584
    assert info["vertical_crop_free"] is True
    out = Image.open(cover)
    # 右边缘中部应当是照片（亮），左边仍是深炭底
    assert out.getpixel((1580, 336))[0] > 90
    assert out.getpixel((40, 336))[0] < 40


def test_portrait_spec_rejects_non_mapping():
    with pytest.raises(SystemExit):
        cp.portrait_spec({"cover_portrait": ["x"]})
