from scripts.works_registry import load_works, save_works, validate_works, next_code, upsert_work, set_video, WORKS_FILE
import pytest


def test_save_then_load_roundtrip(tmp_path):
    works = [
        {"seq": 1, "code": "AIT-01", "category": "AIT", "title": "甲", "date": "2026-01-01", "status": "published"},
        {"seq": 2, "code": "TUT-01", "category": "TUT", "title": "乙", "date": "2026-01-02", "status": "published"},
    ]
    f = tmp_path / "works.yaml"
    save_works(works, f)
    assert load_works(f) == works


def test_load_missing_file_returns_empty(tmp_path):
    assert load_works(tmp_path / "nope.yaml") == []


def _ok():
    return {"seq": 1, "code": "AIT-01", "category": "AIT", "title": "甲",
            "date": "2026-01-01", "status": "published",
            "wechat_url": "https://mp.weixin.qq.com/s/abc", "tags": ["横评"]}


def test_valid_work_has_no_errors():
    assert validate_works([_ok()]) == []


def test_missing_required_field():
    w = _ok(); del w["title"]
    assert any("缺必填字段 title" in e for e in validate_works([w]))


def test_bad_status():
    w = _ok(); w["status"] = "done"
    assert any("status 非法" in e for e in validate_works([w]))


def test_duplicate_seq():
    a, b = _ok(), _ok(); b["code"] = "TUT-01"; b["category"] = "TUT"
    assert any("撞号" in e and "seq" in e for e in validate_works([a, b]))


def test_published_requires_code_and_url():
    w = _ok(); w["code"] = ""; w["wechat_url"] = ""
    errs = validate_works([w])
    assert any("已发布但缺 code" in e for e in errs)
    assert any("已发布但缺 wechat_url" in e for e in errs)


def test_bad_date_format():
    w = _ok(); w["date"] = "2026/01/01"
    assert any("date 格式" in e for e in validate_works([w]))


def test_category_not_in_vocab():
    w = _ok(); w["category"] = "XXX"; w["code"] = "XXX-01"
    assert any("不在词表" in e for e in validate_works([w]))


def test_bad_code_format():
    w = _ok(); w["code"] = "ait1"
    assert any("code 格式" in e for e in validate_works([w]))


def test_duplicate_code():
    a = _ok(); b = _ok(); b["seq"] = 2
    assert any("撞号" in e and "code" in e for e in validate_works([a, b]))


def test_code_prefix_mismatch_category():
    w = _ok(); w["code"] = "TUT-01"  # category 仍 AIT
    assert any("不一致" in e for e in validate_works([w]))


def test_tag_not_in_vocab():
    w = _ok(); w["tags"] = ["乱编标签"]
    assert any("不在受控词表" in e for e in validate_works([w]))


def test_bad_wechat_url():
    w = _ok(); w["wechat_url"] = "https://example.com/x"
    assert any("公众号链接" in e for e in validate_works([w]))


def test_cover_must_be_relative():
    w = _ok(); w["cover"] = "D:" + chr(92) + "some" + chr(92) + "abs" + chr(92) + "x.png"
    assert any("相对路径" in e for e in validate_works([w]))


def test_video_published_needs_url():
    w = _ok(); w["video"] = {"status": "published", "url": ""}
    assert any("缺 video.url" in e for e in validate_works([w]))


def test_merged_into_must_exist():
    w = _ok(); w["merged_into"] = "AIT-99"
    assert any("merged_into" in e for e in validate_works([w]))


@pytest.mark.skipif(not WORKS_FILE.exists(), reason="works.yaml 尚未生成")
def test_real_works_yaml_is_valid():
    errors = validate_works(load_works())
    assert errors == [], "works.yaml 校验未通过:\n" + "\n".join(errors)


# ── 二期C: upsert_work / next_code ──

def test_next_code_empty_starts_at_01():
    assert next_code("AIT", []) == "AIT-01"


def test_next_code_is_max_plus_one_per_category():
    works = [{"category": "AIT", "code": "AIT-01"}, {"category": "AIT", "code": "AIT-03"},
             {"category": "TUT", "code": "TUT-09"}]
    assert next_code("AIT", works) == "AIT-04"   # max+1，空洞不回填（永不复用）
    assert next_code("TUT", works) == "TUT-10"


def test_upsert_new_assigns_code(tmp_path):
    f = tmp_path / "w.yaml"
    save_works([{"seq": 1, "code": "AIT-01", "category": "AIT", "title": "甲",
                 "date": "2026-01-01", "status": "published"}], f)
    r = upsert_work({"seq": 2, "category": "AIT", "title": "乙", "status": "published",
                     "date": "2026-01-02", "wechat_url": "https://mp.weixin.qq.com/s/x"}, f)
    assert r["code"] == "AIT-02"
    assert len(load_works(f)) == 2


def test_set_video_updates_block(tmp_path):
    f = tmp_path / "w.yaml"
    save_works([{"seq": 45, "code": "KID-03", "category": "KID", "title": "丁",
                 "status": "published", "date": "2026-01-01",
                 "video": {"status": "none", "url": ""}}], f)
    r = set_video(45, {"status": "published", "url": "https://v.douyin.com/x",
                       "platform": "douyin"}, f)
    assert r["video"]["status"] == "published"
    assert r["video"]["url"] == "https://v.douyin.com/x"
    assert set_video(999, {"status": "published"}, f) is None   # 找不到 seq


def test_upsert_existing_merges_and_keeps_frozen_code(tmp_path):
    f = tmp_path / "w.yaml"
    save_works([{"seq": 5, "code": "TUT-03", "category": "TUT", "title": "丙",
                 "status": "published", "date": "2026-01-01"}], f)
    # 再次写入同 seq、不带 code → 保留已冻结 TUT-03，并更新标题
    r = upsert_work({"seq": 5, "category": "TUT", "title": "丙改", "status": "published"}, f)
    assert r["code"] == "TUT-03"
    assert r["title"] == "丙改"
    assert len(load_works(f)) == 1
