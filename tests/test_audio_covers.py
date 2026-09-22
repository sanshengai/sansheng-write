import json

import pytest

from scripts import audio_covers as covers


def article(tmp_path, name="106-Jev入门与应用"):
    root = tmp_path / name
    root.mkdir()
    (root / "定稿.md").write_text(
        "# Jev 处理小判断\n\n邮件先进入工具，模型分类以后由程序接着处理。\n",
        encoding="utf-8",
    )
    (root / "_music-manifest.json").write_text(
        json.dumps({"theme": {"title": "Jev 的选择题"}}), encoding="utf-8"
    )
    (root / covers.MUSIC_BRIEF).write_text(
        "## 歌名\n\n```text\nJev 的选择题\n```\n\n## 歌词\n\n```text\n三个托盘摆在面前\n只挑一个，别的留给人\n```\n",
        encoding="utf-8",
    )
    return root


def plan(root, **changes):
    data = {
        "schema_version": 2,
        "theme_cover": {
            "subject": "一封信悬在三个空托盘上方，正落向中间那个",
            "lyric_anchor": "三个托盘摆在面前",
            "article_anchor": "邮件先进入工具，模型分类以后由程序接着处理。",
            "palette": "ocean",
        },
        "podcast_cover": {
            "subject": "一枚齿轮咬着一枚更小的齿轮，小的那枚是信封形状",
            "article_anchor": "模型分类以后由程序接着处理。",
            "palette": "ember",
            "render": "flat",
        },
    }
    data.update(changes)
    (root / covers.COVER_PLAN).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def renderer(monkeypatch):
    prompts = []
    monkeypatch.setattr(covers, "resolve_renderer_command", lambda: (["fake-renderer"], "test", []))
    monkeypatch.setattr(covers, "_load_policy", lambda _root: ([{}], []))

    def render(_root, **kw):
        prompts.append(kw["prompt_file"].read_text(encoding="utf-8"))
        kw["output"].write_bytes(b"test-render-output")
        return []

    monkeypatch.setattr(covers, "_render_one", render)
    return prompts


def test_icon_prompts_have_one_subject_palette_and_no_text(tmp_path, monkeypatch):
    root = article(tmp_path)
    plan(root)
    podcast = root / covers.PODCAST_MANIFEST
    podcast.parent.mkdir(parents=True)
    podcast.write_text("{}")
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert not errors and len(ready) == 2
    assert len(prompts) == 2
    theme, podcast_prompt = prompts
    assert "Jev 的选择题" in theme and "三个托盘摆在面前" in theme and "正落向中间那个" in theme
    assert "deep navy" in theme and "aqua cyan" in theme and covers.RENDERS["sculpted"] in theme
    assert "信封形状" in podcast_prompt and "warm amber" in podcast_prompt and covers.RENDERS["flat"] in podcast_prompt
    assert theme != podcast_prompt
    for prompt in prompts:
        assert "ONE subject only" in prompt and "Strictly no text" in prompt and "64 pixels" in prompt
        assert "Display title" not in prompt and "Render the supplied display title" not in prompt
        assert "a quiet desk at dawn" not in prompt


def test_meta_and_multiline_frontmatter_are_loaded(tmp_path):
    root = article(tmp_path)
    (root / "定稿.md").write_text("---\ntitle: 前置标题\ndescription: >-\n  分类以后\n  再执行\n---\n# 正文标题\n\n正文内容", encoding="utf-8")
    title, digest, body = covers._article_context(root)
    assert title == "前置标题" and digest == "分类以后 再执行"
    assert not body.startswith("---")
    (root / "article-meta.yaml").write_text("title: 已确认标题\ndigest: 已确认摘要\n", encoding="utf-8")
    assert covers._article_context(root)[:2] == ("已确认标题", "已确认摘要")


@pytest.mark.parametrize("failure", [
    "missing_plan", "empty_plan", "old_schema", "empty_body", "wrong_anchor", "short_anchor",
    "empty_subject", "long_subject", "list_subject", "text_subject", "generic_prop",
    "missing_lyric", "lyric_not_in_brief", "bad_palette", "same_palette", "same_subject",
    "bad_render", "legacy_scene_field",
])
def test_invalid_plan_never_calls_renderer(tmp_path, monkeypatch, failure):
    root = article(tmp_path)
    data = plan(root)
    path = root / covers.COVER_PLAN
    theme, podcast = data["theme_cover"], data["podcast_cover"]
    if failure == "missing_plan":
        path.unlink()
    elif failure == "empty_plan":
        path.write_text("{}")
    elif failure == "old_schema":
        data["schema_version"] = 1
    elif failure == "empty_body":
        (root / "定稿.md").write_text("")
    elif failure == "wrong_anchor":
        theme["article_anchor"] = "这是一句在实际正文里面从来没有出现过的话。"
    elif failure == "short_anchor":
        theme["article_anchor"] = "Jev"
    elif failure == "empty_subject":
        theme["subject"] = "  "
    elif failure == "long_subject":
        theme["subject"] = "一间书房里" + "有很多东西" * 20
    elif failure == "list_subject":
        theme["subject"] = "一封信、三个托盘、一只手"
    elif failure == "text_subject":
        theme["subject"] = "三个托盘上方立着歌名的陶土字体"
    elif failure == "generic_prop":
        theme["subject"] = "一盏台灯照着三个托盘"
    elif failure == "missing_lyric":
        del theme["lyric_anchor"]
    elif failure == "lyric_not_in_brief":
        theme["lyric_anchor"] = "这句歌词从来没写进生成单"
    elif failure == "bad_palette":
        theme["palette"] = "sunset"
    elif failure == "same_palette":
        podcast["palette"] = theme["palette"]
    elif failure == "same_subject":
        podcast["subject"] = theme["subject"]
    elif failure == "bad_render":
        theme["render"] = "photoreal"
    elif failure == "legacy_scene_field":
        theme["scene"] = "窗边书桌"
    if failure not in ("missing_plan", "empty_plan"):
        path.write_text(json.dumps(data, ensure_ascii=False))
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert errors and not ready and not prompts
    assert not (root / covers.THEME_COVER).exists()


def test_generic_prop_allowed_when_lyric_or_article_actually_has_it(tmp_path, monkeypatch):
    root = article(tmp_path)
    (root / covers.MUSIC_BRIEF).write_text("```text\n台灯下只剩三个托盘\n```\n", encoding="utf-8")
    plan(root, theme_cover={
        "subject": "一盏台灯的光圈里只有三个托盘",
        "lyric_anchor": "台灯下只剩三个托盘",
        "article_anchor": "邮件先进入工具，模型分类以后由程序接着处理。",
        "palette": "ocean",
    })
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert not errors and len(ready) == 1 and len(prompts) == 1


def test_theme_palette_must_avoid_previous_three_articles(tmp_path, monkeypatch):
    for number, palette in ((103, "moss"), (104, "plum"), (105, "rust"), (102, "ocean")):
        older = tmp_path / f"{number}-旧文"
        older.mkdir()
        (older / covers.COVER_PLAN).write_text(json.dumps({
            "schema_version": 2, "theme_cover": {"palette": palette},
        }), encoding="utf-8")
    # 未升级到 schema 2 的旧规划不参与回避。
    legacy = tmp_path / "101-更旧"
    legacy.mkdir()
    (legacy / covers.COVER_PLAN).write_text(json.dumps({"schema_version": 1, "theme_cover": {"palette": "ink"}}))
    root = article(tmp_path)
    assert covers._recent_theme_palettes(root) == {"105-旧文": "rust", "104-旧文": "plum", "103-旧文": "moss"}

    data = plan(root)
    data["theme_cover"]["palette"] = "plum"
    (root / covers.COVER_PLAN).write_text(json.dumps(data, ensure_ascii=False))
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert errors and not ready and not prompts and "plum" in errors[0] and "104-旧文" in errors[0]

    # 102 用过的 ocean 已滑出三篇窗口，可以再用。
    data["theme_cover"]["palette"] = "ocean"
    (root / covers.COVER_PLAN).write_text(json.dumps(data, ensure_ascii=False))
    ready, errors = covers.ensure_audio_covers(root)
    assert not errors and len(ready) == 1


def test_existing_covers_reused_but_force_requires_current_plan(tmp_path, monkeypatch):
    root = article(tmp_path)
    target = root / covers.THEME_COVER
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"previous-published-image")
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert not errors and ready == [target] and not prompts
    _, errors = covers.ensure_audio_covers(root, force=True)
    assert errors and not prompts
    assert target.read_bytes() == b"previous-published-image"


def test_thumb_sheet_lays_out_site_sizes_and_skips_invalid_images(tmp_path):
    from PIL import Image

    root = article(tmp_path)
    theme = root / covers.THEME_COVER
    Image.new("RGB", (1024, 1024), "#0B1A2E").save(theme)
    broken = root / covers.PODCAST_COVER
    broken.write_bytes(b"not-an-image")
    out = covers.write_thumb_sheet(root, [theme, broken])
    assert out == root / covers.COVER_THUMBS and out.is_file()
    sheet = Image.open(out)
    assert sheet.height == covers.THUMB_SIZES[0] + 18 + 24  # 一行：只有有效的那张
    assert sheet.width > sum(covers.THUMB_SIZES)
    assert covers.write_thumb_sheet(root, [broken]) is None
