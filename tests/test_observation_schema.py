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
