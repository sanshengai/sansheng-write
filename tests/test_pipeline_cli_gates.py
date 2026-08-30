import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_handoff_assets_is_a_pipeline_command_and_fails_closed(tmp_path):
    result = _run(
        tmp_path,
        "handoff-assets",
        "--target-root",
        str(tmp_path / "handoff"),
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "手工上传包导出失败" in result.stdout
    assert not (tmp_path / "handoff").exists()


def test_status_reports_manifest_music_origin_instead_of_hardcoded_provider(tmp_path):
    pipeline.save_state(tmp_path, _state(status="pending"))
    (tmp_path / "_music-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "theme": {
                    "title": "胜利的边界",
                    "origin": {
                        "provider": "MiniMax",
                        "model": "Music 3.0",
                        "mode": "web-ui",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = _run(tmp_path, "status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "《胜利的边界》 · MiniMax / Music 3.0" in result.stdout
    assert "Lyria 3 Pro" not in result.stdout


def test_published_audio_cli_requires_explicit_audition(tmp_path):
    result = _run(
        tmp_path,
        "wechat-published-audio-check",
        "https://mp.weixin.qq.com/s/x",
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "--confirm-audition" in result.stdout


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


def test_checkpoint_only_verify_waits_for_author_without_failure_count(
    tmp_path, monkeypatch, capsys
):
    import contracts

    state = _state(status="pending")
    state["stages"]["outline"]["status"] = "done"
    state["stages"]["writing"].update(
        {"status": "failed", "fail_count": 2, "last_failed_at": "old"}
    )
    pipeline.save_state(tmp_path, state)
    monkeypatch.setattr(
        pipeline,
        "verify_stage",
        lambda *args, **kwargs: (
            False,
            ["checkpoint:draft 未过 -- 等作者回复并写 _draft-approval.md"],
        ),
    )
    observations = []
    monkeypatch.setattr(
        contracts,
        "log_observation",
        lambda *args, **kwargs: observations.append((args, kwargs)),
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_verify("writing", tmp_path)

    assert exc.value.code == 2
    saved = pipeline.load_state(tmp_path)
    writing = saved["stages"]["writing"]
    assert writing["status"] == "waiting_author"
    assert writing["fail_count"] == 0
    assert "last_failed_at" not in writing
    assert writing["waiting_checkpoint"] == ["draft"]
    assert "作者" in writing["required_author_action"]
    assert any(
        args[1] == "verify_stage_elapsed"
        and args[2] == "waiting_author"
        and kwargs["metrics"] == {
            "errors": 1,
            "stage_status": "waiting_author",
        }
        for args, kwargs in observations
    )
    assert any(
        args[1] == "stage_state_transition"
        and args[2] == "waiting_author"
        and kwargs["metrics"]["waiting_author"] == 1
        for args, kwargs in observations
    )

    capsys.readouterr()
    pipeline.cmd_status(tmp_path)
    status_output = capsys.readouterr().out
    assert "等待作者拍板" in status_output
    pipeline.cmd_next(tmp_path)
    next_output = capsys.readouterr().out
    assert "等待作者拍板" in next_output


def test_checkpoint_wait_clears_waiting_fields_after_success(tmp_path, monkeypatch):
    import contracts

    state = _state(status="pending")
    state["stages"]["outline"].update(
        {
            "status": "waiting_author",
            "waiting_since": "old",
            "last_waiting_at": "old",
            "waiting_checkpoint": ["blueprint"],
            "waiting_reason": "old",
            "required_author_action": "old",
        }
    )
    pipeline.save_state(tmp_path, state)
    monkeypatch.setattr(
        pipeline, "verify_stage", lambda *args, **kwargs: (True, [])
    )
    observations = []
    monkeypatch.setattr(
        contracts,
        "log_observation",
        lambda *args, **kwargs: observations.append((args, kwargs)),
    )

    pipeline.cmd_verify("outline", tmp_path)

    outline = pipeline.load_state(tmp_path)["stages"]["outline"]
    assert outline["status"] == "done"
    assert not any(key.startswith("waiting_") for key in outline)
    assert "required_author_action" not in outline
    assert any(
        args[1] == "stage_state_transition"
        and "from=waiting_author to=done" in args[3]
        for args, _ in observations
    )


def test_checkpoint_only_done_uses_same_waiting_state(tmp_path, monkeypatch):
    pipeline.save_state(tmp_path, _state(status="pending"))
    monkeypatch.setattr(
        pipeline,
        "verify_stage",
        lambda *args, **kwargs: (False, ["checkpoint:blueprint 未过 -- 等作者拍板"]),
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_done("outline", tmp_path, [])

    assert exc.value.code == 2
    assert pipeline.load_state(tmp_path)["stages"]["outline"]["status"] == "waiting_author"
