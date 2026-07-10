"""二期C-3 验收：pipeline.py archive 写作品库(自动编码) + 刷新 articles.md/看板。

全程 monkeypatch 重定向到临时文件，不触碰真实 works.yaml。
注意：cmd_archive 用裸名 import 兄弟模块，故测试也用裸名导入同一实例。
"""
import json
import scripts.pipeline as pipeline   # 触发 pipeline 顶部 bootstrap，把 scripts/ 加进 sys.path
import works_registry as wr
import render_articles_md as ram
import render_works_dashboard as rwd


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

    folder = tmp_path / "47-测试选题"
    folder.mkdir()
    (folder / "定稿.md").write_text("正文内容若干字", encoding="utf-8")
    (folder / "素材").mkdir()
    (folder / "素材" / "cover.png").write_bytes(b"x")
    (folder / "article-meta.yaml").write_text(
        "category: AIT\ntags: [横评]\ndigest: 测试摘要\nstyle: example-author\nlogic_bone: CSA\n"
        "outward_category: picks\n",
        encoding="utf-8")
    (folder / ".state.json").write_text(json.dumps({
        "style": "example-author",
        "stages": {"writing": {"title_final": "测试标题"},
                   "publish": {"wechat_url": "https://mp.weixin.qq.com/s/test"}},
    }, ensure_ascii=False), encoding="utf-8")

    pipeline.cmd_archive(folder, [])

    works = wr.load_works(works_file)
    rec = next(w for w in works if w["seq"] == 47)
    assert rec["code"] == "AIT-02"          # 分类内自动编号(AIT-01 之后)
    assert rec["status"] == "published"
    assert rec["title"] == "测试标题"
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


def _mk_folder(tmp_path, name, meta="category: AIT\ntags: []\noutward_category: picks\n",
               url="https://mp.weixin.qq.com/s/x"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "定稿.md").write_text("正文", encoding="utf-8")
    (folder / "article-meta.yaml").write_text(meta, encoding="utf-8")
    (folder / ".state.json").write_text(json.dumps({
        "stages": {"writing": {"title_final": "测试"}, "publish": {"wechat_url": url}}}), encoding="utf-8")
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
    folder = _mk_folder(tmp_path, "47-X")
    pipeline.cmd_archive(folder, [])
    code1 = next(w for w in wr.load_works(works_file) if w["seq"] == 47)["code"]
    assert code1 == "AIT-02"             # 分类内自动编号
    pipeline.cmd_archive(folder, [])     # 二次归档
    code2 = next(w for w in wr.load_works(works_file) if w["seq"] == 47)["code"]
    assert code2 == "AIT-02"             # 冻结 code 保留不变
