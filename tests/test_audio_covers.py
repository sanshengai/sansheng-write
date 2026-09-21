import json

import pytest

from scripts import audio_covers as covers


def article(tmp_path):
    root = tmp_path / "article"
    root.mkdir()
    (root / "定稿.md").write_text(
        "# Jev 处理小判断\n\n邮件先进入工具，模型分类以后由程序接着处理。\n",
        encoding="utf-8",
    )
    (root / "_music-manifest.json").write_text(
        json.dumps({"theme": {"title": "Jev 的选择题"}}), encoding="utf-8"
    )
    return root


def plan(root, **changes):
    data = {
        "schema_version": 1,
        "theme_cover": {
            "article_anchor": "邮件先进入工具，模型分类以后由程序接着处理。",
            "scene": "一封来信前摆着几个待选的分类托盘",
        },
        "podcast_cover": {
            "article_anchor": "模型分类以后由程序接着处理。",
            "scene": "邮件经过分类模块，再连接到核对关口的完整流程",
            "display_title": "Jev 如何接入流程",
        },
    }
    data.update(changes)
    (root / covers.COVER_PLAN).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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


def test_plain_h1_article_reaches_both_actual_render_jobs(tmp_path, monkeypatch):
    root = article(tmp_path)
    plan(root)
    podcast = root / covers.PODCAST_MANIFEST
    podcast.parent.mkdir(parents=True)
    podcast.write_text("{}")
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert not errors and len(ready) == 2
    assert len(prompts) == 2
    assert all("Jev 处理小判断" in prompt for prompt in prompts)
    assert "Jev 的选择题" in prompts[0] and "分类托盘" in prompts[0]
    assert "Jev 如何接入流程" in prompts[1] and "核对关口" in prompts[1]
    assert prompts[0] != prompts[1]
    assert all("a quiet desk at dawn" not in p and "like two people talking" not in p for p in prompts)


def test_meta_and_multiline_frontmatter_are_loaded(tmp_path):
    root = article(tmp_path)
    (root / "定稿.md").write_text("---\ntitle: 前置标题\ndescription: >-\n  分类以后\n  再执行\n---\n# 正文标题\n\n正文内容", encoding="utf-8")
    title, digest, body = covers._article_context(root)
    assert title == "前置标题" and digest == "分类以后 再执行"
    assert not body.startswith("---")
    (root / "article-meta.yaml").write_text("title: 已确认标题\ndigest: 已确认摘要\n", encoding="utf-8")
    assert covers._article_context(root)[:2] == ("已确认标题", "已确认摘要")


@pytest.mark.parametrize("failure", ["missing_plan", "empty_plan", "empty_body", "wrong_anchor", "short_anchor", "empty_scene", "same_scene"])
def test_invalid_material_never_calls_renderer(tmp_path, monkeypatch, failure):
    root = article(tmp_path)
    plan(root)
    path = root / covers.COVER_PLAN
    data = json.loads(path.read_text())
    if failure == "missing_plan":
        path.unlink()
    elif failure == "empty_plan":
        path.write_text("{}")
    elif failure == "empty_body":
        (root / "定稿.md").write_text("")
    else:
        if failure == "wrong_anchor":
            data["theme_cover"]["article_anchor"] = "这是一句在实际正文里面从来没有出现过的话。"
        elif failure == "short_anchor":
            data["theme_cover"]["article_anchor"] = "Jev"
        elif failure == "empty_scene":
            data["theme_cover"]["scene"] = "  "
        else:
            data["podcast_cover"]["scene"] = data["theme_cover"]["scene"]
        path.write_text(json.dumps(data))
    prompts = renderer(monkeypatch)
    ready, errors = covers.ensure_audio_covers(root)
    assert errors and not ready and not prompts
    assert not (root / covers.THEME_COVER).exists()


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
