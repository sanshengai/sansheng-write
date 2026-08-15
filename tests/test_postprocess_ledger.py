"""后处理台账（.postprocess-ledger.json）：幂等护栏 + 空转消除。

背景（2026-08-16 审计）：add_logo.js 就地覆写且无已处理检测，整目录重跑
后处理会在已打过水印的图上再叠一层 35% logo；compress_images 对已达标图
无条件重编码（实测 6 秒 0% saved 纯空转）。台账让两者在「字节未变」时跳过。
"""
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import compress_images as ci  # noqa: E402


def _png(directory: Path, name: str = "infographic-01.png") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    Image.new("RGB", (300, 200), (200, 180, 160)).save(path)
    return path


def test_second_run_skips_via_ledger_and_bytes_stay_identical(tmp_path):
    path = _png(tmp_path / "素材")
    _, _, first = ci.compress_one(path, 2.0, verbose=False)
    assert first in ("OPT", "RESIZE")
    sha_after_first = ci._sha256(path)

    _, _, second = ci.compress_one(path, 2.0, verbose=False)
    assert second == "SKIP_UNCHANGED"
    assert ci._sha256(path) == sha_after_first


def test_rerendered_image_is_processed_again(tmp_path):
    path = _png(tmp_path / "素材")
    ci.compress_one(path, 2.0, verbose=False)
    # 模拟重渲：字节变化
    Image.new("RGB", (300, 200), (10, 90, 60)).save(path)
    _, _, status = ci.compress_one(path, 2.0, verbose=False)
    assert status in ("OPT", "RESIZE"), "重渲后的图必须重新处理，台账不得挡道"


def test_ledger_records_final_sha_and_stage(tmp_path):
    path = _png(tmp_path / "素材")
    ci.compress_one(path, 2.0, verbose=False)
    ledger = json.loads((tmp_path / "素材" / ci.LEDGER_NAME).read_text(encoding="utf-8"))
    entry = ledger[path.name]
    assert entry["sha256"] == ci._sha256(path)
    assert entry["stage"] == "compressed"


def test_component_skip_list_untouched_by_ledger(tmp_path):
    path = _png(tmp_path / "素材", "hero.png")
    _, _, status = ci.compress_one(path, 2.0, verbose=False)
    assert status == "SKIP_COMPONENT"
    assert not (tmp_path / "素材" / ci.LEDGER_NAME).exists()


def test_logo_stage_entry_does_not_block_compress(tmp_path):
    """add_logo 记的 stage="logo" 只说明水印在了，压缩仍必须跑。

    否则 >max-mb 的图永远得不到缩尺寸（首版实现的真实回归，活体链路抓到）。
    """
    path = _png(tmp_path / "素材")
    ci.record_ledger(path, "logo")
    _, _, status = ci.compress_one(path, 2.0, verbose=False)
    assert status in ("OPT", "RESIZE")
    ledger = json.loads((tmp_path / "素材" / ci.LEDGER_NAME).read_text(encoding="utf-8"))
    assert ledger[path.name]["stage"] == "compressed"


def test_corrupt_ledger_degrades_to_reprocess_not_crash(tmp_path):
    path = _png(tmp_path / "素材")
    (tmp_path / "素材" / ci.LEDGER_NAME).write_text("{oops", encoding="utf-8")
    _, _, status = ci.compress_one(path, 2.0, verbose=False)
    assert status in ("OPT", "RESIZE")
