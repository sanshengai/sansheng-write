"""出图默认模型的唯一真源是 profile 的 image.renderers（2026-09-23 审计 V1）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import render_visuals as rv  # noqa: E402


def test_profile_renderers_used_when_article_has_no_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "_profile_renderers", lambda: [
        {"id": "profile-default", "provider": "openai", "model": "gpt-image-2"}])
    renderers, errors = rv._load_policy(tmp_path)
    assert not errors
    assert renderers[0]["id"] == "profile-default" and renderers[0]["model"] == "gpt-image-2"


def test_baoyu_default_when_profile_has_no_image_section(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "_profile_renderers", lambda: [])
    renderers, errors = rv._load_policy(tmp_path)
    assert not errors and renderers[0]["id"] == "baoyu-default"


def test_article_policy_still_overrides_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "_profile_renderers", lambda: [{"id": "profile-default", "provider": "openai"}])
    (tmp_path / "renderer-policy.json").write_text(json.dumps(
        {"schema_version": 1, "renderers": [{"id": "temp-google", "provider": "google"}]}), encoding="utf-8")
    renderers, errors = rv._load_policy(tmp_path)
    assert not errors and renderers[0]["id"] == "temp-google"


def test_copied_policy_from_previous_article_is_flagged(tmp_path):
    payload = json.dumps({"schema_version": 1, "renderers": [{"id": "x", "provider": "openai"}]})
    for name in ("107-上一篇", "108-这一篇"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "renderer-policy.json").write_text(payload, encoding="utf-8")
    warning = rv.policy_copy_warning(tmp_path / "108-这一篇")
    assert "107-上一篇" in warning and "照抄" in warning


def test_distinct_policy_is_not_flagged(tmp_path):
    (tmp_path / "107-上一篇").mkdir()
    (tmp_path / "107-上一篇" / "renderer-policy.json").write_text('{"renderers": [{"id": "a"}]}', encoding="utf-8")
    (tmp_path / "108-这一篇").mkdir()
    (tmp_path / "108-这一篇" / "renderer-policy.json").write_text('{"renderers": [{"id": "b"}]}', encoding="utf-8")
    assert rv.policy_copy_warning(tmp_path / "108-这一篇") == ""
