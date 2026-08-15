"""log_observation 的 elapsed_ms（2026-08-16 审计：日志从不记耗时，
阶段耗时画像只能靠 mtime 考古——这是后续一切量化改进的数据前提）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _fresh_flywheel(tmp_path, monkeypatch):
    # 仓根 conftest.py 把 SANSHENG_WRITE_FLYWHEEL_DIR 钉到共享测试数据目录，
    # 这里显式覆盖成本测试自己的 tmp，避免读到别的测试写的记录。
    fw = tmp_path / "flywheel"
    fw.mkdir(parents=True)
    monkeypatch.setenv("SANSHENG_WRITE_FLYWHEEL_DIR", str(fw))
    monkeypatch.delenv("SANSHENG_WRITE_TELEMETRY", raising=False)
    import profile_config

    profile_config._cache.clear()
    return fw


def _last_record(fw: Path) -> dict:
    log = fw / "_skill-observations.jsonl"
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1])


def test_elapsed_ms_lands_in_metrics(tmp_path, monkeypatch):
    fw = _fresh_flywheel(tmp_path, monkeypatch)
    from contracts import log_observation

    log_observation("verify_writing", "verify_stage_elapsed", "ok",
                    "errors=0", "测试文章", elapsed_ms=1234.56)
    rec = _last_record(fw)
    assert rec["metrics"]["elapsed_ms"] == 1234.6


def test_omitting_elapsed_keeps_old_shape(tmp_path, monkeypatch):
    fw = _fresh_flywheel(tmp_path, monkeypatch)
    from contracts import log_observation

    log_observation("verify_writing", "verify_pos_ratio", "ok", "ratio=0.1", "测试文章")
    rec = _last_record(fw)
    assert "elapsed_ms" not in rec["metrics"]
