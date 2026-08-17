"""二期C-3 验收：pipeline.py archive 写作品库(自动编码) + 刷新 articles.md/看板。

全程 monkeypatch 重定向到临时文件，不触碰真实 works.yaml。
注意：cmd_archive 用裸名 import 兄弟模块，故测试也用裸名导入同一实例。
"""
import json
import sys
import types
import pytest
import scripts.pipeline as pipeline   # 触发 pipeline 顶部 bootstrap，把 scripts/ 加进 sys.path
import works_registry as wr
import render_articles_md as ram
import render_works_dashboard as rwd
import generate_recommend_html as grh
import profile_config as pc
import distribute


def _allow_golden(monkeypatch, tmp_path, article_name):
    golden = tmp_path / f"golden-{article_name}.md"
    golden.write_text(f"- 一句。 *({article_name})*\n", encoding="utf-8")
    monkeypatch.setattr(pc, "golden_lines_file", lambda: golden)
    return golden


def test_cmd_archive_writes_works_and_refreshes(tmp_path, monkeypatch):
    works_file = tmp_path / "works.yaml"
    wr.save_works([{
        "seq": 8, "code": "AIT-01", "category": "AIT", "title": "甲",
        "date": "2026-01-01", "status": "published",
        "wechat_url": "https://mp.weixin.qq.com/s/a", "tags": [],
    }], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    monkeypatch.setattr(ram, "ARTICLES_MD", tmp_path / "articles.md")
    monkeypatch.setattr(rwd, "DASHBOARD_FILE", tmp_path / "看板.html")
    monkeypatch.setattr(grh, "generate_recommend_html", lambda articles=None: None)
    _allow_golden(monkeypatch, tmp_path, "47-测试选题")

    folder = tmp_path / "47-测试选题"
    folder.mkdir()
    (folder / "定稿.md").write_text("正文内容若干字", encoding="utf-8")
    (folder / "素材").mkdir()
    (folder / "素材" / "cover.png").write_bytes(b"x")
    (folder / "article-meta.yaml").write_text(
        "title: 精选 | 测试标题\ncategory: AIT\ntags: [横评]\ndigest: 测试摘要\nstyle: example-author\nlogic_bone: CSA\n"
        "outward_category: picks\n",
        encoding="utf-8")
    (folder / ".state.json").write_text(json.dumps({
        "style": "example-author",
        "stages": {"writing": {"title_final": "精选 | 测试标题"},
                   "publish": {"wechat_url": "https://mp.weixin.qq.com/s/test"}},
    }, ensure_ascii=False), encoding="utf-8")

    pipeline.cmd_archive(folder, [])

    works = wr.load_works(works_file)
    rec = next(w for w in works if w["seq"] == 47)
    assert rec["code"] == "AIT-02"          # 分类内自动编号(AIT-01 之后)
    assert rec["status"] == "published"
    assert rec["title"] == "精选 | 测试标题"
    assert rec["category"] == "AIT"
    assert rec["digest"] == "测试摘要"
    assert rec["tags"] == ["横评"]
    assert rec["cover"] == "<数据目录>/47-测试选题/素材/cover.png"
    # 视图已自动刷新
    assert (tmp_path / "articles.md").exists()
    assert "测试标题" in (tmp_path / "articles.md").read_text(encoding="utf-8")
    assert (tmp_path / "看板.html").exists()


def test_cmd_archive_guards_missing_category(tmp_path, monkeypatch, capsys):
    works_file = tmp_path / "works.yaml"
    wr.save_works([], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    folder = tmp_path / "48-无分类"
    folder.mkdir()
    (folder / "article-meta.yaml").write_text("style: example-author\n", encoding="utf-8")
    (folder / ".state.json").write_text(json.dumps({
        "stages": {"writing": {"title_final": "x"},
                   "publish": {"wechat_url": "https://mp.weixin.qq.com/s/x"}}}), encoding="utf-8")
    pipeline.cmd_archive(folder, [])
    out = capsys.readouterr().out
    assert "category" in out          # 提示缺 category
    assert wr.load_works(works_file) == []   # 未写入任何记录


def _mk_folder(tmp_path, name, meta="title: 精选 | 测试\ncategory: AIT\ntags: []\noutward_category: picks\ndigest: 测试摘要\n",
               url="https://mp.weixin.qq.com/s/x"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "定稿.md").write_text("正文", encoding="utf-8")
    (folder / "article-meta.yaml").write_text(meta, encoding="utf-8")
    (folder / ".state.json").write_text(json.dumps({
        "stages": {"writing": {"title_final": "精选 | 测试"}, "publish": {"wechat_url": url}}}), encoding="utf-8")
    return folder


def test_cmd_archive_no_url_aborts(tmp_path, monkeypatch, capsys):
    works_file = tmp_path / "works.yaml"
    wr.save_works([], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    folder = _mk_folder(tmp_path, "50-无链接", url="")
    pipeline.cmd_archive(folder, [])
    out = capsys.readouterr().out
    assert ("wechat_url" in out) or ("未发布" in out)
    assert wr.load_works(works_file) == []


def test_cmd_archive_non_numeric_seq_aborts(tmp_path, monkeypatch, capsys):
    works_file = tmp_path / "works.yaml"
    wr.save_works([], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    folder = _mk_folder(tmp_path, "选题孵化")  # 无数字前缀
    pipeline.cmd_archive(folder, [])
    out = capsys.readouterr().out
    assert "seq" in out
    assert wr.load_works(works_file) == []


def test_cmd_archive_second_run_keeps_frozen_code(tmp_path, monkeypatch):
    works_file = tmp_path / "works.yaml"
    wr.save_works([{"seq": 8, "code": "AIT-01", "category": "AIT", "title": "甲",
                    "date": "2026-01-01", "status": "published",
                    "wechat_url": "https://mp.weixin.qq.com/s/a", "tags": []}], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    monkeypatch.setattr(ram, "ARTICLES_MD", tmp_path / "a.md")
    monkeypatch.setattr(rwd, "DASHBOARD_FILE", tmp_path / "d.html")
    monkeypatch.setattr(grh, "generate_recommend_html", lambda articles=None: None)
    _allow_golden(monkeypatch, tmp_path, "47-X")
    folder = _mk_folder(tmp_path, "47-X")
    pipeline.cmd_archive(folder, [])
    code1 = next(w for w in wr.load_works(works_file) if w["seq"] == 47)["code"]
    assert code1 == "AIT-02"             # 分类内自动编号
    pipeline.cmd_archive(folder, [])     # 二次归档
    code2 = next(w for w in wr.load_works(works_file) if w["seq"] == 47)["code"]
    assert code2 == "AIT-02"             # 冻结 code 保留不变


def test_cmd_archive_rejects_bad_tags_before_writing(tmp_path, monkeypatch, capsys):
    works_file = tmp_path / "works.yaml"
    original = [{"seq": 8, "code": "AIT-01", "category": "AIT", "title": "甲",
                 "date": "2026-01-01", "status": "published",
                 "wechat_url": "https://mp.weixin.qq.com/s/a", "tags": []}]
    wr.save_works(original, works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    folder = _mk_folder(
        tmp_path, "47-坏标签",
        meta="category: AIT\noutward_category: picks\ntags: [NotInVocab]\ndigest: 摘要\n",
    )

    assert pipeline.cmd_archive(folder, []) is False
    assert wr.load_works(works_file) == original
    assert "作品库未写入" in capsys.readouterr().out


def test_cmd_archive_requires_article_meta_title(tmp_path, monkeypatch, capsys):
    """state 里即使有 title_final，也不能代替正式标题 SSOT。"""
    works_file = tmp_path / "works.yaml"
    wr.save_works([], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    folder = _mk_folder(
        tmp_path, "47-缺正式标题",
        meta="category: AIT\noutward_category: picks\ntags: [横评]\ndigest: 摘要\n",
    )

    assert pipeline.cmd_archive(folder, []) is False
    assert wr.load_works(works_file) == []
    assert "article-meta.yaml title 缺失" in capsys.readouterr().out


def test_cmd_archive_rerun_preserves_operational_fields(tmp_path, monkeypatch):
    works_file = tmp_path / "works.yaml"
    existing = {
        "seq": 47, "code": "AIT-02", "category": "AIT", "outward_category": "picks",
        "title": "旧标题", "digest": "旧摘要", "date": "2026-01-02", "status": "published",
        "wechat_url": "https://mp.weixin.qq.com/s/old", "tags": ["横评"],
        "merged_into": "AIT-01",
        "video": {"status": "published", "url": "https://example.com/video", "platform": "x"},
    }
    wr.save_works([{"seq": 8, "code": "AIT-01", "category": "AIT", "title": "甲",
                    "date": "2026-01-01", "status": "published",
                    "wechat_url": "https://mp.weixin.qq.com/s/a", "tags": []}, existing], works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    monkeypatch.setattr(ram, "ARTICLES_MD", tmp_path / "a.md")
    monkeypatch.setattr(rwd, "DASHBOARD_FILE", tmp_path / "d.html")
    monkeypatch.setattr(grh, "generate_recommend_html", lambda articles=None: None)
    _allow_golden(monkeypatch, tmp_path, "47-X")
    folder = _mk_folder(tmp_path, "47-X", url="https://mp.weixin.qq.com/s/new")

    assert pipeline.cmd_archive(folder, []) is True
    rec = next(w for w in wr.load_works(works_file) if w["seq"] == 47)
    assert rec["date"] == "2026-01-02"
    assert rec["merged_into"] == "AIT-01"
    assert rec["video"]["status"] == "published"
    assert rec["video"]["url"] == "https://example.com/video"


def test_verify_archive_rejects_invalid_registry_even_when_record_exists(tmp_path, monkeypatch):
    works_file = tmp_path / "works.yaml"
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    monkeypatch.setattr(ram, "ARTICLES_MD", tmp_path / "articles.md")
    monkeypatch.setattr(rwd, "DASHBOARD_FILE", tmp_path / "dashboard.html")
    golden = tmp_path / "golden-lines.md"
    golden.write_text("- 一句。 *(47-X)*\n", encoding="utf-8")
    monkeypatch.setattr(pc, "golden_lines_file", lambda: golden)

    folder = _mk_folder(
        tmp_path, "47-X",
        meta="category: AIT\noutward_category: picks\ntags: [NotInVocab]\ndigest: 测试摘要\n",
    )
    state = json.loads((folder / ".state.json").read_text(encoding="utf-8"))
    works = [{
        "seq": 47, "code": "AIT-02", "category": "AIT", "outward_category": "picks",
        "title": "精选 | 测试", "digest": "测试摘要", "date": "2026-01-02", "status": "published",
        "wechat_url": "https://mp.weixin.qq.com/s/x", "tags": ["NotInVocab"],
    }]
    wr.save_works(works, works_file)
    ram.ARTICLES_MD.write_text(ram.render_md(works), encoding="utf-8")
    rwd.DASHBOARD_FILE.write_text(rwd.build_html(works), encoding="utf-8")

    passed, errors = pipeline.verify_stage("archive", folder, state)
    assert passed is False
    assert any("受控词表" in error for error in errors)


def test_finalize_runs_publish_archive_verify_in_order(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_finalize_preflight_errors", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "cmd_done", lambda *a, **k: calls.append("publish"))
    monkeypatch.setattr(pipeline, "cmd_archive", lambda *a, **k: calls.append("archive") or True)
    monkeypatch.setattr(pipeline, "cmd_verify", lambda *a, **k: calls.append("verify"))
    monkeypatch.setattr(
        pipeline, "_run_website_sync", lambda *a, **k: calls.append("website") or True
    )
    monkeypatch.setattr(
        pipeline, "_write_moments_copy", lambda *a, **k: calls.append("moments")
    )
    monkeypatch.setattr(
        pipeline, "_handoff_to_distribute", lambda *a, **k: calls.append("distribute") or True
    )

    pipeline.cmd_finalize("https://mp.weixin.qq.com/s/abc", tmp_path)
    # 朋友圈文案排在归档验证之后、播客与官网同步之前：它只需要标题、摘要和
    # 永久链接，那三样在 verify 之后就已就位，不该排在 10-30 分钟的播客音频后面。
    assert calls == ["publish", "archive", "verify", "moments", "distribute", "website"]


def test_moments_copy_is_deterministic_and_uses_profile_cta(tmp_path, monkeypatch):
    (tmp_path / "article-meta.yaml").write_text(
        'title: "教程 | 自动收尾"\n'
        'digest: "正式发布后自动归档、同步官网并生成朋友圈文案。"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pipeline,
        "brand",
        lambda: {
            "writing": {"moments_cta": "去官网看完整方法"},
            "identity": {"site": "https://example.com"},
        },
    )

    first = pipeline._write_moments_copy(
        tmp_path, "https://mp.weixin.qq.com/s/abc"
    )
    second = pipeline._write_moments_copy(
        tmp_path, "https://mp.weixin.qq.com/s/abc"
    )

    assert first == second
    assert first == (
        "🔥 教程 | 自动收尾\n\n"
        "🧭 正式发布后自动归档、同步官网并生成朋友圈文案。\n\n"
        "👉 去官网看完整方法 · https://example.com\n"
    )
    assert "mp.weixin.qq.com" not in first
    assert len([line for line in first.splitlines() if line]) == 3
    assert first.startswith("🔥")
    assert "# 朋友圈文案" not in first
    assert not any(char in first for char in "\u200b\u200c\u200d\ufeff\u00a0")
    assert all(line == line.strip() for line in first.splitlines())
    assert (tmp_path / "_moments-copy.md").read_text(encoding="utf-8") == first


def test_moments_copy_fast_path_has_no_finalize_side_effects(tmp_path, monkeypatch):
    (tmp_path / "article-meta.yaml").write_text(
        'title: "一篇现成文章"\ndigest: "只生成文案，不启动发布链。"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pipeline,
        "brand",
        lambda: {"writing": {"moments_cta": "打开上方文章卡片"}},
    )
    monkeypatch.setattr(
        pipeline,
        "cmd_finalize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不得进入 finalize")),
    )

    pipeline.cmd_moments_copy(tmp_path)

    text = (tmp_path / "_moments-copy.md").read_text(encoding="utf-8")
    assert text.count("\n\n") == 2
    assert "一篇现成文章" in text
    assert not (tmp_path / pipeline.FINALIZE_STATE_FILE).exists()


def test_moments_cta_does_not_repeat_site_when_bare_host_is_present(tmp_path, monkeypatch):
    (tmp_path / "article-meta.yaml").write_text(
        'title: "一篇现成文章"\ndigest: "直接生成朋友圈文案。"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pipeline,
        "brand",
        lambda: {
            "writing": {
                "moments_cta": "查看完整内容 → 示例品牌 · example.com"
            },
            "identity": {"site": "https://example.com"},
        },
    )

    text = pipeline._write_moments_copy(tmp_path, "")

    assert text.endswith("👉 查看完整内容 → 示例品牌 · example.com\n")
    assert "https://example.com" not in text


def test_handoff_auto_podcast_runs_generate_then_publish(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(distribute, "enabled_channels", lambda: ["podcast"])
    monkeypatch.setattr(
        distribute,
        "cmd_plan",
        lambda cwd, only="": calls.append(("plan", only)) or 0,
    )
    monkeypatch.setattr(
        distribute, "channel_config",
        lambda ch: {"enabled": True, "auto_after_finalize": True},
    )
    monkeypatch.setattr(distribute, "get_status", lambda *a: "planned")
    monkeypatch.setattr(distribute, "_is_drifted", lambda *a: False)
    fake = types.SimpleNamespace(
        cmd_generate=lambda cwd: calls.append("generate") or 0,
        cmd_publish=lambda cwd, confirm=False: calls.append(("publish", confirm)) or 0,
    )
    monkeypatch.setitem(sys.modules, "podcast_episode", fake)

    assert pipeline._handoff_to_distribute(tmp_path) is True
    assert calls == [("plan", "podcast"), "generate", ("publish", True)]


def test_handoff_auto_podcast_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(distribute, "enabled_channels", lambda: ["podcast"])
    monkeypatch.setattr(distribute, "cmd_plan", lambda cwd, only="": 0)
    monkeypatch.setattr(
        distribute, "channel_config",
        lambda ch: {"enabled": True, "auto_after_finalize": True},
    )
    monkeypatch.setattr(distribute, "get_status", lambda *a: "planned")
    monkeypatch.setattr(distribute, "_is_drifted", lambda *a: False)
    fake = types.SimpleNamespace(
        cmd_generate=lambda cwd: 3,
        cmd_publish=lambda *a, **k: pytest.fail("认证失败后不得继续 publish"),
    )
    monkeypatch.setitem(sys.modules, "podcast_episode", fake)

    assert pipeline._handoff_to_distribute(tmp_path) is False


def test_handoff_does_not_auto_plan_assisted_social_channels(tmp_path, monkeypatch):
    """小红书 / 微博必须按篇显式触发，profile 已启用也不等于授权。"""
    monkeypatch.setattr(distribute, "enabled_channels", lambda: ["xhs", "weibo"])
    monkeypatch.setattr(
        distribute,
        "cmd_plan",
        lambda *a, **k: pytest.fail("finalize 不得自动规划社媒"),
    )

    assert pipeline._handoff_to_distribute(tmp_path) is True


def test_website_failure_does_not_roll_back_moments(tmp_path, monkeypatch):
    """官网同步失败仍以 2 退出，但朋友圈文案已在它之前产出，不得回滚。

    2026-08-04 起朋友圈文案前移到归档验证之后。旧契约是「官网失败阻断文案生成」，
    那会让作者在首发最需要文案的几小时里，因为一个与文案无关的部署失败而拿不到它。
    """
    calls = []
    monkeypatch.setattr(pipeline, "_finalize_preflight_errors", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "cmd_done", lambda *a, **k: calls.append("publish"))
    monkeypatch.setattr(pipeline, "cmd_archive", lambda *a, **k: calls.append("archive") or True)
    monkeypatch.setattr(pipeline, "cmd_verify", lambda *a, **k: calls.append("verify"))
    monkeypatch.setattr(
        pipeline, "_handoff_to_distribute", lambda *a, **k: calls.append("distribute") or True
    )
    monkeypatch.setattr(pipeline, "_run_website_sync", lambda *a, **k: False)
    monkeypatch.setattr(
        pipeline, "_write_moments_copy", lambda *a, **k: calls.append("moments")
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_finalize("https://mp.weixin.qq.com/s/abc", tmp_path)

    assert exc.value.code == 2
    assert calls == ["publish", "archive", "verify", "moments", "distribute"]


def test_finalize_resumes_after_website_failure_without_repeating_archive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_finalize_preflight_errors", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "cmd_done", lambda *a, **k: calls.append("publish"))
    monkeypatch.setattr(
        pipeline, "cmd_archive", lambda *a, **k: calls.append("archive") or True
    )
    monkeypatch.setattr(pipeline, "cmd_verify", lambda *a, **k: calls.append("verify"))
    website_results = iter([False, True])
    monkeypatch.setattr(
        pipeline,
        "_run_website_sync",
        lambda *a, **k: calls.append("website") or next(website_results),
    )
    monkeypatch.setattr(
        pipeline, "_write_moments_copy", lambda *a, **k: calls.append("moments")
    )
    monkeypatch.setattr(
        pipeline, "_handoff_to_distribute", lambda *a, **k: calls.append("distribute") or True
    )

    url = "https://mp.weixin.qq.com/s/abc"
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_finalize(url, tmp_path)
    assert exc.value.code == 2

    pipeline.cmd_finalize(url, tmp_path)
    # 续跑只重试失败的官网同步：朋友圈文案与播客都已标记完成，不重复执行。
    assert calls == [
        "publish", "archive", "verify", "moments", "distribute", "website",
        "website",
    ]


def test_distribution_failure_blocks_website_but_keeps_moments(tmp_path, monkeypatch):
    """播客失败仍以 3 退出并阻断官网，但不影响已经产出的朋友圈文案。"""
    calls = []
    monkeypatch.setattr(pipeline, "_finalize_preflight_errors", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "cmd_done", lambda *a, **k: calls.append("publish"))
    monkeypatch.setattr(
        pipeline, "cmd_archive", lambda *a, **k: calls.append("archive") or True
    )
    monkeypatch.setattr(pipeline, "cmd_verify", lambda *a, **k: calls.append("verify"))
    monkeypatch.setattr(
        pipeline, "_handoff_to_distribute", lambda *a, **k: calls.append("distribute") or False
    )
    monkeypatch.setattr(
        pipeline, "_run_website_sync", lambda *a, **k: calls.append("website") or True
    )
    monkeypatch.setattr(
        pipeline, "_write_moments_copy", lambda *a, **k: calls.append("moments")
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_finalize("https://mp.weixin.qq.com/s/abc", tmp_path)

    assert exc.value.code == 3
    assert calls == ["publish", "archive", "verify", "moments", "distribute"]


def test_website_receipt_preserves_failed_and_successful_attempts(tmp_path, monkeypatch):
    website = tmp_path / "website"
    website.mkdir()
    monkeypatch.setattr(
        pipeline,
        "brand",
        lambda: {
            "publish": {
                "website_command": "run-site {code}",
                "website_cwd": str(website),
            }
        },
    )
    monkeypatch.setattr(pipeline, "_archived_code", lambda cwd: "AIT-01")

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode
            self.stdout = "ok" if returncode == 0 else ""
            self.stderr = "bad" if returncode else ""

    results = iter([Result(1), Result(0)])
    runner = lambda *a, **k: next(results)
    assert pipeline._run_website_sync(tmp_path, "https://mp.weixin.qq.com/s/x", runner=runner) is False
    assert pipeline._run_website_sync(tmp_path, "https://mp.weixin.qq.com/s/x", runner=runner) is True

    receipt = json.loads((tmp_path / "_website-sync-receipt.json").read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert [attempt["status"] for attempt in receipt["attempts"]] == ["failed", "done"]


def test_cmd_archive_rejects_missing_golden_marker_before_writing(tmp_path, monkeypatch):
    works_file = tmp_path / "works.yaml"
    original = [{"seq": 8, "code": "AIT-01", "category": "AIT", "title": "甲",
                 "date": "2026-01-01", "status": "published",
                 "wechat_url": "https://mp.weixin.qq.com/s/a", "tags": []}]
    wr.save_works(original, works_file)
    monkeypatch.setattr(wr, "WORKS_FILE", works_file)
    golden = tmp_path / "golden.md"
    golden.write_text("- 只有别篇。 *(46-Y)*\n", encoding="utf-8")
    monkeypatch.setattr(pc, "golden_lines_file", lambda: golden)
    folder = _mk_folder(tmp_path, "47-X")

    assert pipeline.cmd_archive(folder, []) is False
    assert wr.load_works(works_file) == original
