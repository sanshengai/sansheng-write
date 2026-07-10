from scripts.render_articles_md import render_md


def _sample():
    return [
        {"seq": 46, "code": "AIT-07", "category": "AIT", "title": "合成文章甲",
         "date": "2026-05-29", "status": "published", "digest": "摘要甲",
         "cover": "<数据目录>/46-x/素材/cover.png",
         "wechat_url": "https://mp.weixin.qq.com/s/aaa",
         "video": {"status": "none", "url": ""}},
        {"seq": 44, "code": "TUT-13", "category": "TUT", "title": "合成文章乙",
         "date": "2026-05-26", "status": "published", "digest": "",
         "cover": "", "wechat_url": "https://mp.weixin.qq.com/s/bbb",
         "video": {"status": "published", "url": "https://v.douyin.com/x"}},
        {"seq": 99, "code": "", "category": "AIT", "title": "未发草稿",
         "date": "", "status": "draft", "wechat_url": "", "video": {"status": "none"}},
    ]


def test_render_md_lists_published_by_date_desc():
    md = render_md(_sample())
    assert "### 1. 合成文章甲" in md
    assert "### 2. 合成文章乙" in md
    # 草稿不进 articles.md
    assert "未发草稿" not in md


def test_render_md_has_code_link_and_digest_fallback():
    md = render_md(_sample())
    assert "AIT-07" in md
    assert "https://mp.weixin.qq.com/s/aaa" in md
    assert "暂无摘要" in md          # 无摘要兜底
    assert "总作品数** -- 2 篇" in md


def test_render_md_shows_video_when_present():
    md = render_md(_sample())
    assert "https://v.douyin.com/x" in md
