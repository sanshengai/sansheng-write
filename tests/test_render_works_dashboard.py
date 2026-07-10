from scripts.render_works_dashboard import cover_src, build_html


def test_cover_src_strips_root_prefix():
    assert cover_src("<数据目录>/46-x/素材/cover.png") == "46-x/素材/cover.png"


def test_cover_src_empty():
    assert cover_src("") == ""


def _sample():
    return [
        {"seq": 46, "code": "AIT-07", "category": "AIT", "title": "合成横评甲",
         "date": "2026-05-29", "status": "published", "tags": ["横评"],
         "cover": "<数据目录>/46-x/素材/cover.png",
         "wechat_url": "https://mp.weixin.qq.com/s/abc",
         "video": {"status": "published", "url": "https://v.douyin.com/x"}},
        {"seq": 43, "code": "", "category": "AIT", "title": "合成草稿乙",
         "date": "", "status": "draft", "tags": [], "cover": "",
         "wechat_url": "", "video": {"status": "none", "url": ""}},
    ]


def test_build_html_contains_titles_and_stats():
    html = build_html(_sample())
    assert "合成横评甲" in html
    assert "AIT-07" in html
    assert "总数 2" in html and "已发布 1" in html
    # 视频已发布的卡片应有视频标记
    assert "🎬" in html


def test_build_html_has_category_filter_and_data_attrs():
    html = build_html(_sample())
    assert 'data-category="AIT"' in html
    # 草稿卡片有状态标记
    assert "草稿" in html


def test_build_html_shows_seq_prefix():
    html = build_html(_sample())
    assert '<span class="seq">46</span>' in html
    assert '<span class="seq">43</span>' in html
