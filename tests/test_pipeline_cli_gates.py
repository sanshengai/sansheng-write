import json
import subprocess
import sys
from pathlib import Path

from scripts import pipeline


PIPELINE = Path(pipeline.__file__).resolve()


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIPELINE), *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _state(status="pending") -> dict:
    return {
        "schema_version": 2,
        "topic_id": "fixture",
        "run_id": "run-fixture",
        "stages": {stage: {"status": status} for stage in pipeline.STAGE_ORDER},
    }


def test_verify_failure_returns_nonzero_and_invalidates_downstream(tmp_path):
    pipeline.save_state(tmp_path, _state(status="done"))
    result = _run(tmp_path, "verify", "outline")
    assert result.returncode == 2, result.stdout + result.stderr
    saved = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert saved["stages"]["outline"]["status"] == "failed"
    assert saved["stages"]["writing"]["status"] == "dirty"
    assert saved["stages"]["publish"]["status"] == "dirty"


def test_done_failure_returns_nonzero_and_invalidates_downstream(tmp_path):
    pipeline.save_state(tmp_path, _state(status="done"))
    result = _run(tmp_path, "done", "outline")
    assert result.returncode == 2, result.stdout + result.stderr
    saved = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert saved["stages"]["outline"]["status"] == "failed"
    assert saved["stages"]["writing"]["status"] == "dirty"


def test_wechat_url_cannot_bypass_receipt_and_legacy_flag_is_rejected(tmp_path):
    pipeline.save_state(tmp_path, _state())
    url = "wechat_url=https://mp.weixin.qq.com/s/fixture"
    result = _run(tmp_path, "done", "publish", url)
    assert result.returncode == 2, result.stdout + result.stderr
    saved = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert "wechat_url" not in saved["stages"]["publish"]
    assert not (tmp_path / "_publish-receipt.json").exists()

    legacy = _run(tmp_path, "done", "publish", url, "--legacy")
    assert legacy.returncode != 0, legacy.stdout + legacy.stderr
    saved = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert "wechat_url" not in saved["stages"]["publish"]


def test_force_flags_are_rejected_instead_of_bypassing_stage_contracts(tmp_path):
    pipeline.save_state(tmp_path, _state())
    assert _run(tmp_path, "done", "cover", "--force").returncode != 0
    assert _run(tmp_path, "skip", "cover", "--force").returncode != 0


def test_publish_preflight_rejects_non_done_upstream(tmp_path):
    pipeline.save_state(tmp_path, _state(status="pending"))
    result = _run(tmp_path, "verify", "publish", "--pre")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "上游阶段 outline=pending" in result.stdout


def test_bgm_is_a_non_skippable_release_stage(tmp_path):
    pipeline.save_state(tmp_path, _state(status="pending"))
    result = _run(tmp_path, "skip", "bgm")
    assert result.returncode == 2, result.stdout + result.stderr
    saved = pipeline.load_state(tmp_path)
    assert saved["stages"]["bgm"]["status"] == "pending"


def test_init_persists_cross_process_run_id(tmp_path):
    result = _run(tmp_path, "init")
    assert result.returncode == 0
    state = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert state["run_id"]


def test_draft_media_id_is_valid_draft_state_without_wechat_url(tmp_path):
    state = _state(status="done")
    state["stages"]["publish"]["draft_media_id"] = "draft-fixture"
    warnings = pipeline._cross_check(tmp_path, state)
    assert not any("wechat_url" in warning for warning in warnings)


def test_invalid_wechat_url_does_not_replace_existing_publish_receipt(tmp_path):
    state = _state(status="done")
    state["stages"]["publish"].update(
        {"draft_media_id": "trusted-id", "wechat_url": ""}
    )
    pipeline.save_state(tmp_path, state)
    receipt = tmp_path / pipeline.PUBLISH_RECEIPT_FILE
    receipt.write_text('{"draft_media_id":"trusted-id"}', encoding="utf-8")
    before = receipt.read_bytes()

    result = _run(tmp_path, "done", "publish", "wechat_url=https://example.com/bad")
    assert result.returncode == 2, result.stdout + result.stderr
    saved = json.loads((tmp_path / ".state.json").read_text(encoding="utf-8"))
    assert saved["stages"]["publish"]["draft_media_id"] == "trusted-id"
    assert saved["stages"]["publish"]["wechat_url"] == ""
    assert receipt.read_bytes() == before
