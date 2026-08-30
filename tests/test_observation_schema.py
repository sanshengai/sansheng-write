import json

from scripts import profile_config
from scripts.contracts import log_observation


def test_observation_v2_has_ids_attempt_and_machine_fields(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "brand.yaml").write_text("brand: fixture\n", encoding="utf-8")
    monkeypatch.setenv("SANSHENG_WRITE_PROFILE_DIR", str(profile))
    monkeypatch.setenv("SANSHENG_WRITE_RUN_ID", "run-test")
    profile_config._reset_cache_for_tests()
    try:
        kwargs = {
            "issue_codes": ["visual.style_drift"],
            "metrics": {"hits": 1},
            "artifact_digest": "abc123",
        }
        log_observation("verify_publish", "visual_route", "fail", "errors=1", "文章甲", **kwargs)
        log_observation("verify_publish", "visual_route", "ok", "errors=0", "文章甲")
        rows = [json.loads(line) for line in profile_config.observations_file().read_text(encoding="utf-8").splitlines()]
        rows = [row for row in rows if row.get("run_id") == "run-test"]
        assert [row["attempt"] for row in rows] == [1, 2]
        assert rows[0]["schema_version"] == 2
        assert rows[0]["record_id"]
        assert rows[0]["run_id"] == "run-test"
        assert rows[0]["passed"] is False
        assert rows[0]["severity"] == "error"
        assert rows[0]["issue_codes"] == ["visual.style_drift"]
        assert rows[0]["metrics"] == {"hits": 1}
        assert rows[0]["artifact_digest"] == "abc123"
        assert rows[0]["article_uid"].startswith("a-")
        assert "文章甲" not in profile_config.observations_file().read_text(encoding="utf-8")
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_PROFILE_DIR", raising=False)
        monkeypatch.delenv("SANSHENG_WRITE_RUN_ID", raising=False)
        profile_config._reset_cache_for_tests()


def test_observation_attempt_key_includes_stage(tmp_path, monkeypatch):
    flywheel = tmp_path / "flywheel"
    monkeypatch.setenv("SANSHENG_WRITE_FLYWHEEL_DIR", str(flywheel))
    profile_config._reset_cache_for_tests()
    try:
        log_observation("verify_writing", "verify_stage_elapsed", "ok", article="文章甲")
        log_observation("verify_layout", "verify_stage_elapsed", "ok", article="文章甲")
        log_observation("verify_writing", "verify_stage_elapsed", "ok", article="文章甲")

        rows = [
            json.loads(line)
            for line in profile_config.observations_file().read_text(encoding="utf-8").splitlines()
        ]
        assert [row["stage"] for row in rows] == [
            "verify_writing",
            "verify_layout",
            "verify_writing",
        ]
        assert [row["attempt"] for row in rows] == [1, 1, 2]
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_FLYWHEEL_DIR", raising=False)
        profile_config._reset_cache_for_tests()


def test_observation_records_bound_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "worktree"
    article = workspace / "data" / "01-fixture"
    article.mkdir(parents=True)
    (workspace / ".git").mkdir()
    flywheel = tmp_path / "flywheel"
    monkeypatch.setenv("SANSHENG_WRITE_FLYWHEEL_DIR", str(flywheel))
    profile_config._reset_cache_for_tests()
    try:
        assert profile_config.bind_workspace(article) == workspace.resolve()
        log_observation("verify_writing", "verify_stage_elapsed", "ok", article="文章甲")

        row = json.loads(
            profile_config.observations_file().read_text(encoding="utf-8").splitlines()[-1]
        )
        assert row["workspace_root"] == str(workspace.resolve())
        assert row["workspace_uid"].startswith("w-")
        assert len(row["workspace_uid"]) == 12
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_FLYWHEEL_DIR", raising=False)
        profile_config._reset_cache_for_tests()
