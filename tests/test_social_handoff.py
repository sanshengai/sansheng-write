import copy
import hashlib

import pytest

from scripts.social_handoff import validate
from scripts.x_article import check_caption


@pytest.fixture
def good(tmp_path):
    path = tmp_path / "copy.txt"
    path.write_text("文章素材", encoding="utf-8")
    common = dict(assets=[dict(path="copy.txt", role="copy", sha256=hashlib.sha256(path.read_bytes()).hexdigest())],
                  text_readback_verified=True, media_order_verified=True,
                  send_button_enabled=True, send_clicked=False)
    weibo = dict(common, product="image_text", url="https://weibo.com/",
                 images_expected=9, images_uploaded=9)
    x = dict(common, product="article", url="https://x.com/compose/articles/edit/123/focus",
             cover_verified=True, body_images_expected=6, body_images_uploaded=6,
             body_structure_verified=True, placeholders_remaining=0, preview_verified=True,
             caption_prefilled=True, caption_readback_verified=True)
    def more(roles):
        return [dict(path="copy.txt", role=role, sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for role in roles]
    weibo["assets"] = weibo["assets"] + more(["image"] * 9)
    x["assets"] = x["assets"] + more(["cover", "caption"] + ["body_image"] * 6)
    return dict(observed_at="2026-10-15T00:00:00Z", method="actual_ui_readback",
                channels=dict(weibo=weibo, x=x))


def test_complete_handoff(good, tmp_path):
    assert validate(good, tmp_path, ["weibo", "x"]) == []


@pytest.mark.parametrize("channel,key,value", [
    ("weibo", "images_uploaded", 0), ("weibo", "images_uploaded", 8),
    ("x", "url", "https://x.com/compose/post"), ("x", "cover_verified", False),
    ("x", "body_images_uploaded", 5), ("x", "placeholders_remaining", 1),
    ("x", "caption_prefilled", False), ("x", "caption_readback_verified", False),
    ("x", "body_structure_verified", False), ("x", "preview_verified", False),
    ("weibo", "media_order_verified", False), ("x", "send_clicked", True),
])
def test_mutating_observed_handoff_rejects(good, tmp_path, channel, key, value):
    candidate = copy.deepcopy(good)
    candidate["channels"][channel][key] = value
    assert validate(candidate, tmp_path, [channel])


def test_empty_and_unrequested_channel(good, tmp_path):
    assert validate({}, tmp_path, ["weibo", "x"])
    assert validate(good, tmp_path, [])
    del good["channels"]["x"]
    assert validate(good, tmp_path, ["weibo"]) == []
    assert validate(good, tmp_path, ["weibo", "x"])


def test_asset_drift(good, tmp_path):
    (tmp_path / "copy.txt").write_text("changed", encoding="utf-8")
    assert any("漂移" in e for e in validate(good, tmp_path, ["weibo"]))


@pytest.mark.parametrize("text", ["", "  \n "])
def test_empty_caption_rejected(text):
    assert any("缺推荐说明" in e for e in check_caption(text))


@pytest.mark.parametrize("caption", [None, "", "  \n "])
def test_publish_main_rejects_missing_caption_before_browser(tmp_path, monkeypatch, capsys, caption):
    from scripts import x_article as xa
    import sys
    monkeypatch.setattr(xa, "x_config", lambda _: dict(cdp="", chrome_profile="", article_url_template="", tail_line=""))
    monkeypatch.setattr(xa, "parse_article", lambda _: dict(blocks=[], sources=[], title="标题"))
    monkeypatch.setattr(xa, "site_url", lambda *_: "https://example.test/article")
    monkeypatch.setattr(xa, "find_cover", lambda _: tmp_path / "cover.png")
    monkeypatch.setattr(xa, "tail_links", lambda *_: "")
    argv = ["x_article.py", str(tmp_path), "--publish", "--dry-run"]
    if caption is not None:
        f = tmp_path / "caption.txt"
        f.write_text(caption, encoding="utf-8")
        argv += ["--caption-file", str(f)]
    monkeypatch.setattr(sys, "argv", argv)
    assert xa.main() == 2
    assert "缺推荐说明" in capsys.readouterr().out


def test_missing_asset_roles_rejected(good, tmp_path):
    good["channels"]["x"]["assets"] = good["channels"]["x"]["assets"][:1]
    assert validate(good, tmp_path, ["x"])
