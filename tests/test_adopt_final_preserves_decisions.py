"""adopt-final 覆写 _draft-approval.md 前必须留档。

2026-08-14 第 89 篇实跑：走完整流程的文章，作者审读记录本来就写在
`_draft-approval.md` 里（那是 draft 闸门的锚点文件）；到 `adopt-final` 这一步
被整份覆写成机器接管块，四轮返工的原因、作者原话、当时定下的取舍全没了 ——
当次是人工发现后手抄回来的。

文档里虽然提醒过「要写在另一个文件里」，但提醒挡不住既成事实：作者根本没有
机会「提前写到别处」。所以改成代码保证，本文件钉住这个保证。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _make_article(tmp_path: Path, approval_text: str | None) -> Path:
    art = tmp_path / "89-x"
    art.mkdir()
    # 正文需 ≥1500 字才过 adopt_final 前置校验
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
    """调用 adopt_final 并断言前置校验通过（否则测试等于空跑）。"""
    from release_job import adopt_final

    job, errors = adopt_final(art, art / "定稿.md", art / "article-meta.yaml")
    assert not errors, f"夹具未过前置校验，测试会空转：{errors}"
    return job


def test_author_decisions_are_archived_before_overwrite(tmp_path):
    """真实场景：走完整流程，审批文件里有作者拍板记录。"""
    original = (
        "# 定稿闸门 · 作者审读记录\n\n"
        "作者原话：删掉「只高 1 分」那个判断，会误导读者。\n"
        "第三轮返工：改倒叙、删「三个坑」整节。\n\n"
        "审批结论：通过\n"
    )
    art = _make_article(tmp_path, original)

    _adopt(art)

    archived = (art / "_draft-decisions.md")
    assert archived.exists(), "覆写前必须留档"
    text = archived.read_text(encoding="utf-8")
    assert "删掉「只高 1 分」那个判断" in text, "作者原话不得丢失"
    assert "第三轮返工" in text, "返工记录不得丢失"
    assert "adopt-final 覆写前" in text, "存档需注明来由"

    # 审批文件本身仍被正常改写成机器接管块
    approval = (art / "_draft-approval.md").read_text(encoding="utf-8")
    assert "# 作者定稿接管" in approval
    assert "审批结论：通过" in approval


def test_machine_block_is_not_re_archived(tmp_path):
    """重复跑 adopt-final 时，机器块自身不该被反复存档。"""
    art = _make_article(tmp_path, None)
    _adopt(art)
    first = (art / "_draft-decisions.md").exists()

    _adopt(art)
    second_text = ""
    if (art / "_draft-decisions.md").exists():
        second_text = (art / "_draft-decisions.md").read_text(encoding="utf-8")

    assert not first, "无作者内容时不该产生存档"
    assert "# 作者定稿接管" not in second_text, "机器块不得被当作作者记录存档"


def test_existing_decisions_file_is_appended_not_clobbered(tmp_path):
    """已有 _draft-decisions.md 时必须追加，不能覆盖掉先前的记录。"""
    art = _make_article(tmp_path, "# 作者审读\n\n作者说：保留那句原话。\n")
    (art / "_draft-decisions.md").write_text(
        "# 作者拍板与取舍记录\n\n蓝图闸：标题选方案 2。\n", encoding="utf-8"
    )

    _adopt(art)

    text = (art / "_draft-decisions.md").read_text(encoding="utf-8")
    assert "蓝图闸：标题选方案 2" in text, "先前记录不得被覆盖"
    assert "保留那句原话" in text, "新存档内容也要在"
