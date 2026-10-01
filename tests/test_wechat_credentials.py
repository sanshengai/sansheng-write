"""微信凭证位置：写作 Skill 自己的 wechat.env 优先，旧的宝玉 .env 只作兼容回退。"""
from pathlib import Path

import scripts.release_to_draft as r


def _env(path: Path, app: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"WECHAT_APP_ID={app}\nWECHAT_APP_SECRET=s-{app}\n", encoding="utf-8")


def test_own_file_wins_over_legacy(tmp_path, monkeypatch):
    monkeypatch.delenv("WECHAT_APP_ID", raising=False)
    monkeypatch.delenv("WECHAT_APP_SECRET", raising=False)
    _env(tmp_path / "own.env", "own")
    _env(tmp_path / "art/.baoyu-skills/.env", "legacy")
    monkeypatch.setenv("SANSHENG_WRITE_WECHAT_ENV", str(tmp_path / "own.env"))
    assert r._wechat_credentials(tmp_path / "art") == ("own", "s-own")


def test_legacy_still_works_when_own_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("WECHAT_APP_ID", raising=False)
    monkeypatch.delenv("WECHAT_APP_SECRET", raising=False)
    monkeypatch.setenv("SANSHENG_WRITE_WECHAT_ENV", str(tmp_path / "missing.env"))
    monkeypatch.setattr(r.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
    _env(tmp_path / "art/.baoyu-skills/.env", "legacy")
    assert r._wechat_credentials(tmp_path / "art") == ("legacy", "s-legacy")
