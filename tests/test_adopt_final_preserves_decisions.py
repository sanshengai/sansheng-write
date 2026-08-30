"""adopt-final 必须把真实审批当证据读取，不能再改写或制造它。

2026-08-14 第 89 篇实跑曾把 `_draft-approval.md` 覆写成机器接管块，
导致作者原话、返工原因与取舍记录丢失。现在的边界更直接：审批文件由作者
产生，adopt-final 只读并绑定其字节摘要；没有真实通过记录就拒绝接管。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _make_article(tmp_path: Path, approval_text: str | None) -> Path:
    art = tmp_path / "89-x"
    art.mkdir(parents=True)
    (art / "定稿.md").write_text(
        "# 精选 | 标题\n\n" + "正文内容" * 500, encoding="utf-8"
    )
    (art / "article-meta.yaml").write_text(
        'title: "精选 | 标题"\n'
        'category: "OBS"\n'
        'outward_category: "picks"\n'
        'digest: "一句话摘要"\n'
        "cover_style: montage-evidence\n"
        "infographic_style: claymation\n"
        "visual_profile: warm-light-clay\n"
        "lead:\n"
        '  line1: "四个字"\n'
        '  line2: "副标题在这"\n'
        '  accent: "在这"\n'
        '  tag1: "标签"\n'
        '  tag2: "分类"\n',
        encoding="utf-8",
    )
    if approval_text is not None:
        (art / "_draft-approval.md").write_text(approval_text, encoding="utf-8")
    return art


def _adopt(art: Path):
    from release_job import adopt_final

    job, errors = adopt_final(art, art / "定稿.md", art / "article-meta.yaml")
    assert not errors, f"夹具未过前置校验，测试会空转：{errors}"
    return job


def test_author_decisions_remain_in_original_approval_bytes(tmp_path):
    original = (
        "# 定稿闸门 · 作者审读记录\r\n\r\n"
        "作者原话：删掉「只高 1 分」那个判断，会误导读者。\r\n"
        "第三轮返工：改倒叙、删「三个坑」整节。\r\n\r\n"
        "审批结论：通过\r\n"
    )
    art = _make_article(tmp_path, original)
    approval = art / "_draft-approval.md"
    before = approval.read_bytes()

    job = _adopt(art)

    assert approval.read_bytes() == before
    assert not (art / "_draft-decisions.md").exists(), "不再需要覆写前备份"
    assert job["approval_evidence"]["sha256"]
    assert job["approval_evidence"]["subject"]["title"] == "精选 | 标题"


def test_missing_approval_is_not_replaced_with_machine_block(tmp_path):
    art = _make_article(tmp_path, None)
    from release_job import adopt_final

    job, errors = adopt_final(art, art / "定稿.md", art / "article-meta.yaml")

    assert job is None
    assert any("不得替作者自签" in error for error in errors)
    assert not (art / "_draft-approval.md").exists()
    assert not (art / ".state.json").exists()
    assert not (art / "_release-job.json").exists()
    assert not (art / "_checkpoint-receipts.json").exists()


def test_existing_decisions_file_is_untouched(tmp_path):
    approval_text = "# 作者审读\n\n作者说：保留那句原话。\n\n审批结论：通过\n"
    art = _make_article(tmp_path, approval_text)
    decisions = art / "_draft-decisions.md"
    decisions.write_text(
        "# 作者拍板与取舍记录\n\n蓝图闸：标题选方案 2。\n", encoding="utf-8"
    )
    before = decisions.read_bytes()

    _adopt(art)

    assert decisions.read_bytes() == before
    assert (art / "_draft-approval.md").read_text(encoding="utf-8") == approval_text
