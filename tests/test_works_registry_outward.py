# -*- coding: utf-8 -*-
"""works_registry.py 对外分类(outward_category)单元测试。运行：
   PYTHONUTF8=1 python -m pytest tests/test_works_registry_outward.py -v

与 tests/test_works_registry.py 互补：本文件测六类词表 / suggest_outward 裁决 /
outward 校验与回填；那边测 load/save/validate/next_code/upsert/set_video。
两文件 basename 必须唯一——pytest 默认 prepend 模式用裸 basename 当模块名。
"""
from scripts import works_registry as wr


def test_outward_categories_has_six_stable_keys():
    assert set(wr.OUTWARD_CATEGORIES) == {
        "tutorial", "news", "picks", "insight", "essay", "industry"
    }


def test_outward_categories_display_names_are_two_chars():
    for name in wr.OUTWARD_CATEGORIES.values():
        assert len(name) == 2, f"展示名应为 2 字: {name!r}"


def test_suggest_outward_clean_codes_no_review():
    assert wr.suggest_outward("TUT") == ("tutorial", False)
    assert wr.suggest_outward("ESS") == ("essay", False)
    assert wr.suggest_outward("KID") == ("essay", False)
    assert wr.suggest_outward("ROB") == ("news", False)


def test_suggest_outward_ambiguous_needs_review():
    assert wr.suggest_outward("OBS") == ("insight", True)
    assert wr.suggest_outward("AIT") == (None, True)


def test_suggest_outward_unknown_needs_review():
    assert wr.suggest_outward("ZZZ") == (None, True)
    assert wr.suggest_outward(None) == (None, True)


def test_validate_rejects_bad_outward_category():
    works = [{"seq": 1, "title": "t", "status": "draft",
              "outward_category": "bogus"}]
    errs = wr.validate_works(works)
    assert any("outward_category" in e for e in errs)


def test_validate_accepts_valid_outward_category():
    works = [{"seq": 1, "title": "t", "status": "draft",
              "outward_category": "tutorial"}]
    errs = wr.validate_works(works)
    assert not any("outward_category" in e for e in errs)


def test_validate_allows_missing_outward_category():
    works = [{"seq": 1, "title": "t", "status": "draft"}]
    errs = wr.validate_works(works)
    assert not any("outward_category" in e for e in errs)


def test_outward_todo_lists_only_missing():
    works = [
        {"seq": 1, "outward_category": "tutorial"},
        {"seq": 2},
        {"seq": 3, "outward_category": ""},   # 空串视为缺失
    ]
    todo = wr.outward_todo(works)
    assert sorted(w["seq"] for w in todo) == [2, 3]


def test_apply_outward_defaults_fills_clean_flags_review_idempotent():
    works = [
        {"seq": 1, "code": "TUT-01", "category": "TUT", "title": "a", "status": "published"},
        {"seq": 2, "code": "AIT-01", "category": "AIT", "title": "b", "status": "published"},
        {"seq": 3, "code": "OBS-01", "category": "OBS", "title": "c", "status": "published"},
        {"seq": 4, "code": "TUT-02", "category": "TUT", "title": "d", "status": "published",
         "outward_category": "picks"},
    ]
    auto, review = wr.apply_outward_defaults(works)
    # TUT 自动补 tutorial
    assert works[0]["outward_category"] == "tutorial"
    assert (1, "TUT-01", "tutorial") in auto
    # AIT 不自动补，进 review（建议 None）
    assert works[1].get("outward_category") is None
    assert (2, "AIT-01", None) in review
    # OBS 需人工确认，不自动补，但建议 insight 进 review
    assert works[2].get("outward_category") is None
    assert (3, "OBS-01", "insight") in review
    # 已有值幂等不动
    assert works[3]["outward_category"] == "picks"
    # 再跑一次不产生新的 auto（幂等）
    auto2, _ = wr.apply_outward_defaults(works)
    assert auto2 == []
