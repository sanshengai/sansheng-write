"""验收：推荐卡片从「读 articles.md」切到「读 works.yaml」后，两个数据源产出必须逐字一致。

夹具是**合成**的（公开仓不含真实文章）。两份等价数据源现造，跑同一套挑选与渲染逻辑。
"""
import pytest

from scripts import generate_recommend_html as G
from scripts.generate_recommend_html import (
    generate_recommend_html,
    parse_articles_from_markdown,
    parse_articles_from_works,
)

# 六篇合成文章：全有封面，供「一三五」规则取第 1/3/5 篇
_ARTICLES = [
    {"seq": i, "title": f"合成文章 {i}", "date": f"2026-05-{20 - i:02d}",
     "cover": f"http://example.com/cover-{i}.png",
     "wechat_url": f"https://example.com/a/{i}", "status": "published",
     "code": f"TUT-{i:02d}", "category": "TUT", "outward_category": "tutorial"}
    for i in range(1, 7)
]

# articles.md 是表格式渲染视图（由 archive 自动生成），照其真实格式合成
_ARTICLES_MD = "\n".join(
    f"### {a['seq']}. {a['title']}\n\n"
    f"| 字段 | 值 |\n|---|---|\n"
    f"| **发布日期** | {a['date']} |\n"
    f"| **封面** | ![cover]({a['cover']}) |\n"
    f"| **摘要** | 合成摘要 |\n"
    f"| **微信链接** | [阅读原文]({a['wechat_url']}) |\n"
    for a in _ARTICLES
)


@pytest.fixture()
def synthetic_sources(tmp_path, monkeypatch):
    """现造一份 articles.md 与一份等价的 works.yaml，并把两个解析器指向它们。"""
    import yaml

    md = tmp_path / "articles.md"
    md.write_text(_ARTICLES_MD, encoding="utf-8")
    monkeypatch.setattr(G, "ARTICLES_DB_PATH", md)

    works = tmp_path / "works.yaml"
    works.write_text(yaml.safe_dump({"works": _ARTICLES}, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(G, "load_works", lambda *a, **k: list(_ARTICLES))
    return tmp_path


def test_recommend_html_identical_old_vs_new(synthetic_sources):
    old = generate_recommend_html(parse_articles_from_markdown())
    new = generate_recommend_html(parse_articles_from_works())
    assert old is not None, "旧源(articles.md)生成失败"
    assert new is not None, "新源(works.yaml)生成失败"
    # 选出的 3 篇标题/链接一致
    assert [a["title"] for a in old[1]] == [a["title"] for a in new[1]]
    assert [a["link"] for a in old[1]] == [a["link"] for a in new[1]]
    # 完整 HTML 逐字一致
    assert old[0] == new[0]


def test_works_source_picks_three(synthetic_sources):
    new = generate_recommend_html(parse_articles_from_works())
    assert new is not None
    assert len(new[1]) == 3


def test_card_is_cover_only():
    from scripts.generate_recommend_html import generate_single_card_html
    card = generate_single_card_html(
        {"title": "T", "link": "https://x", "cover": "http://img/c.png", "digest": "D"}, 0)
    assert "width:100%" in card           # 全宽封面
    assert "http://img/c.png" in card
    assert "阅读全文" not in card          # 已取消右侧文字
    assert "{digest}" not in card and "D" not in card.replace("https://x", "")


def test_only_cover_articles_selected():
    from scripts.generate_recommend_html import generate_recommend_html as gen
    arts = [
        {"title": "有封面1", "date": "2026-05-09", "cover": "http://i/1.png", "link": "https://mp.weixin.qq.com/s/1"},
        {"title": "无封面", "date": "2026-05-08", "cover": "", "link": "https://mp.weixin.qq.com/s/2"},
        {"title": "有封面2", "date": "2026-05-07", "cover": "http://i/3.png", "link": "https://mp.weixin.qq.com/s/3"},
        {"title": "有封面3", "date": "2026-05-06", "cover": "http://i/4.png", "link": "https://mp.weixin.qq.com/s/4"},
        {"title": "有封面4", "date": "2026-05-05", "cover": "http://i/5.png", "link": "https://mp.weixin.qq.com/s/5"},
        {"title": "有封面5", "date": "2026-05-04", "cover": "http://i/6.png", "link": "https://mp.weixin.qq.com/s/6"},
    ]
    res = gen(arts)
    assert res is not None
    titles = [a["title"] for a in res[1]]
    assert "无封面" not in titles          # 无封面被跳过
    assert len(titles) == 3 and len(set(titles)) == 3   # 3 篇不重复
