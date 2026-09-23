"""pipeline.py new：按文体从模板与 profile 生成新篇骨架（2026-09-23 审计 E2）。

「照抄上一篇」曾是事实上的模板机制，article-meta 连同上一篇的旧值一起被继承。
new 只读模板与 profile；这里用一篇带旧值的「上一篇」做反例。
"""
import pytest
import yaml

import scripts.pipeline as pipeline
import profile_config as pc
import works_registry as wr


@pytest.fixture
def roots(tmp_path, monkeypatch):
    data = tmp_path / "data"
    archive = tmp_path / "archive"
    data.mkdir()
    archive.mkdir()
    works = data / "works.yaml"
    monkeypatch.setattr(pc, "data_dir", lambda: data)
    monkeypatch.setattr(pc, "physical_archive_dir", lambda: archive)
    monkeypatch.setattr(pc, "works_file", lambda: works)
    monkeypatch.setattr(pc, "brand", lambda: {"writing": {"default_style": "示例作者"}})
    previous = data / "12-上一篇"
    previous.mkdir()
    (previous / "article-meta.yaml").write_text(
        'title: "资讯 | 旧标题：上一篇的话"\ndigest: "上一篇的摘要"\n', encoding="utf-8")
    return data, archive, works


def test_new_news_article_from_template_not_previous(roots):
    data, _, _ = roots
    article = pipeline.cmd_new("新模型发布", "news")
    assert article == data / "13-新模型发布"
    text = (article / "article-meta.yaml").read_text(encoding="utf-8")
    assert "旧标题" not in text and "上一篇的摘要" not in text
    meta = yaml.safe_load(text)
    assert meta["title"] == "" and meta["digest"] == ""
    assert meta["outward_category"] == "news" and meta["category"] == "OBS"
    assert meta["logic_bone"] == "ASC" and meta["opening_strategy"] == "直入"   # outline.md 步骤 3.5
    assert meta["style"] == "示例作者"
    assert meta["infographic_mode"] == "author-shots"
    assert (article / "素材").is_dir()


def test_number_accounts_for_archive_and_works(roots):
    data, archive, works = roots
    (archive / "40-已归档").mkdir()
    wr.save_works([{"seq": 57, "title": "作品库里的最后一篇"}], works)
    assert pipeline.cmd_new("教一个工具", "tutorial").name == "58-教一个工具"


def test_tutorial_keeps_generated_infographics(roots):
    meta = yaml.safe_load((pipeline.cmd_new("教一个工具", "tutorial") / "article-meta.yaml")
                          .read_text(encoding="utf-8"))
    assert meta["genre"] == "教程文" and meta["outward_category"] == "tutorial"
    assert "infographic_mode" not in meta


def test_dry_run_creates_nothing(roots):
    data, _, _ = roots
    article = pipeline.cmd_new("只看看", "deep", dry_run=True)
    assert not article.exists()


@pytest.mark.parametrize("topic", ["", "12-带编号", "含/斜杠"])
def test_bad_topic_rejected(roots, topic):
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_new(topic, "news")
    assert exc.value.code == 2


def test_fill_meta_field_keeps_comment():
    text = 'genre: ""                    # 文体：深度文 / 教程文\n'
    assert pipeline._fill_meta_field(text, "genre", "教程文") == \
        'genre: "教程文"                    # 文体：深度文 / 教程文\n'
