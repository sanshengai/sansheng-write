# tests/golden/_synthetic_infographic/make_fixtures.py
"""确定性合成信息图 PNG fixture 生成器（P1.2 tier-2 验证门测试用）。

**不在仓里存二进制 PNG**：每次由 Pillow 按固定 (w,h)+纯色确定性现造到
传入的临时目录，跑完即弃。这样 regression_baseline.py P1 门 与
pytest 共用同一套「合规组 / 各违规组」生成逻辑，单一事实源、零仓库膨胀、
hermetic（不依赖外部素材、不烧 baoyu-image-gen 配额）。

每组返回 images list（[{path,aspect,bytes}]，与 _OUTPUT_SCHEMA infographic
同形），交给 contracts.verify_infographic_set 校验：
  - compliant            合规：4 张 = 开篇9:16 + 中间16:9×2 + 结尾9:16，1K，<2MB
  - bad_count            违规①：仅 3 张（< img_count_min）
  - bad_composition      违规②：开篇是 16:9（应 9:16）
  - bad_aspect_enum      违规③：含一张 3:4（非三枚举）
  - bad_oversize         违规④：一张 bytes 伪报 > 2_000_000
  - bad_not_1k           违规⑤：一张长边 800（< 1K 下界 900）

1K 长边统一用 1024（落在 contracts 的 [900,1200] 达标带内）。
"""
from PIL import Image

_LONGEDGE = 1024
_BRAND = (47, 111, 143)  # 中性填充纯色（primary slate），纯色即可（本门只读尺寸/字节，不读内容）


def _dims(aspect, longedge=_LONGEDGE):
    if aspect == "9:16":
        return (round(longedge * 9 / 16), longedge)   # 竖：长边=高
    if aspect == "16:9":
        return (longedge, round(longedge * 9 / 16))   # 横：长边=宽
    if aspect == "1:1":
        return (longedge, longedge)
    raise ValueError(aspect)


def _png(dirpath, name, w, h):
    p = dirpath / name
    Image.new("RGB", (w, h), _BRAND).save(str(p), "PNG", optimize=True)
    return {"path": str(p), "aspect": None, "bytes": p.stat().st_size}


def _mk(dirpath, specs):
    out = []
    for name, spec in specs:
        w, h = spec if isinstance(spec, tuple) else _dims(spec)
        out.append(_png(dirpath, name, w, h))
    return out


def build_groups(dirpath):
    """dirpath: pathlib.Path（已存在的临时目录）。返回 dict[str,list]。"""
    groups = {}
    groups["compliant"] = _mk(dirpath, [
        ("c01_open.png", "9:16"), ("c02_mid.png", "16:9"),
        ("c03_mid.png", "16:9"), ("c04_close.png", "9:16"),
    ])
    groups["bad_count"] = _mk(dirpath, [
        ("n01.png", "9:16"), ("n02.png", "16:9"), ("n03.png", "9:16"),
    ])  # 仅 3 张
    groups["bad_composition"] = _mk(dirpath, [
        ("p01_open.png", "16:9"),  # 开篇错：应 9:16
        ("p02_mid.png", "16:9"), ("p03_mid.png", "16:9"),
        ("p04_close.png", "9:16"),
    ])
    groups["bad_aspect_enum"] = _mk(dirpath, [
        ("e01_open.png", "9:16"), ("e02_mid.png", "16:9"),
        ("e03_bad.png", (768, 1024)),  # 3:4，非三枚举
        ("e04_close.png", "9:16"),
    ])
    over = _mk(dirpath, [
        ("o01_open.png", "9:16"), ("o02_mid.png", "16:9"),
        ("o03_mid.png", "16:9"), ("o04_close.png", "9:16"),
    ])
    over[1] = dict(over[1], bytes=2_000_001)  # 伪报超 2MB（不造真大文件）
    groups["bad_oversize"] = over
    groups["bad_not_1k"] = _mk(dirpath, [
        ("k01_open.png", (450, 800)),  # 9:16 比例但长边 800 < 900
        ("k02_mid.png", "16:9"), ("k03_mid.png", "16:9"),
        ("k04_close.png", "9:16"),
    ])
    return groups
