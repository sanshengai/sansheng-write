"""approve --words：按作者原话生成审批文件再封存（2026-09-23 审计 F1/F6）。

审批文件此前由 Agent 按作者原话手写，格式各篇不一（有的只有一行「审批结论：通过」）。
approve 命令现在把作者原话逐字放进引用块、写北京时间与审批来源，蓝图与定稿同一结构；
封存失败时文件回滚，不留半截状态。
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts import pipeline
from scripts.evidence import CHECKPOINT_RECEIPT_FILE, _approval_anchor, render_approval_anchor

PIPELINE = Path(pipeline.__file__).resolve()


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PIPELINE), *args],
        cwd=cwd, text=True, encoding="utf-8", capture_output=True, check=False,
    )


def _article(tmp_path: Path) -> Path:
    article = tmp_path / "88-approve-fixture"
    article.mkdir()
    (article / "定稿.md").write_text(
        "---\n"
        'title: "教程 | 一篇已经确认的文章"\n'
        'description: "这是给发布链使用的摘要。"\n'
        "---\n\n"
        "# 教程 | 一篇已经确认的文章\n\n"
        + "这是作者已经审定的正文内容。它只需要进入发布后端，不应重新经历大纲和写作流程。\n" * 80,
        encoding="utf-8",
    )
    (article / "article-meta.yaml").write_text(
        'title: "教程 | 一篇已经确认的文章"\n'
        'category: "TUT"\n'
        'outward_category: "tutorial"\n'
        'tags: ["AI工具"]\n'
        'digest: "这是给发布链使用的摘要。"\n'
        'lead:\n'
        '  line1: "规则不能丢"\n'
        '  line2: "发布链也要稳"\n'
        '  accent: "也要稳"\n'
        '  subtitle: "文章导读"\n'
        '  tag1: "硬门"\n'
        '  tag2: "证据"\n'
        '  ghost: "RULE × GATE × PROOF"\n'
        'cover_style: "montage-evidence"\n'
        'infographic_subject: "ai-product"\n'
        'infographic_style: "claymation"\n'
        'visual_profile: "warm-light-clay"\n',
        encoding="utf-8",
    )
    return article


WORDS = "标题用方案2，开头A，\n直接按完整流程走完。"


def test_draft_words_are_quoted_verbatim_and_sealed(tmp_path):
    article = _article(tmp_path)
    result = _run(article, "approve", "draft", "--source-mode", "author-provided-final", "--words", WORDS)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (article / "_draft-approval.md").read_text(encoding="utf-8")
    assert "> 标题用方案2，开头A，\n> 直接按完整流程走完。" in text
    assert "作者原话（" in text and "北京时间" in text
    assert "审批结论：通过" in text
    receipts = json.loads((article / CHECKPOINT_RECEIPT_FILE).read_text(encoding="utf-8"))
    assert receipts["checkpoints"]["draft"]["decision"] == "approved"


def test_adopt_final_accepts_generated_approval(tmp_path):
    article = _article(tmp_path)
    assert _run(article, "approve", "draft", "--source-mode", "author-provided-final",
                "--words", WORDS).returncode == 0
    result = _run(article, "adopt-final")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "没有「作者原话」记录" not in result.stdout


def test_adopt_final_warns_on_hand_written_approval(tmp_path):
    article = _article(tmp_path)
    (article / "_draft-approval.md").write_text("# 定稿审批\n\n审批结论：通过\n", encoding="utf-8")
    result = _run(article, "adopt-final")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "没有「作者原话」记录" in result.stdout
    assert "MiniMax-主题曲生成单" in result.stdout   # 审计 F3：接管后先交付生成单


def test_negative_words_inside_quote_do_not_reject(tmp_path):
    """作者原话里的「不同意」是原话的一部分，不是审批结论。"""
    article = _article(tmp_path)
    result = _run(article, "approve", "draft", "--source-mode", "author-provided-final",
                  "--words", "不同意改标题，其余通过，按这版走。")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "否定词" in result.stdout
    anchor, _ = _approval_anchor(article, "draft")
    assert anchor["decision"] == "approved"


def test_existing_record_is_kept_as_quote_and_no_longer_governs(tmp_path):
    article = _article(tmp_path)
    old = "# 定稿审批\n\n审批结论：待确认\n作者还没看完。\n"
    (article / "_draft-approval.md").write_text(old, encoding="utf-8")
    assert _run(article, "approve", "draft", "--source-mode", "author-provided-final",
                "--words", "看完了，过。").returncode == 0
    text = (article / "_draft-approval.md").read_text(encoding="utf-8")
    assert "> 审批结论：待确认" in text and "> 作者还没看完。" in text
    assert _approval_anchor(article, "draft")[0]["decision"] == "approved"


def test_blueprint_requires_structured_fields(tmp_path):
    article = _article(tmp_path)
    (article / "大纲.md").write_text("大纲\n" * 100, encoding="utf-8")
    result = _run(article, "approve", "blueprint", "--source-mode", "new-draft", "--words", "方案2，开头A")
    assert result.returncode == 2
    assert "--opening" in result.stdout and "--cover-style" in result.stdout
    assert not (article / "_blueprint-approval.md").exists()

    result = _run(article, "approve", "blueprint", "--source-mode", "new-draft", "--words", "方案2，开头A",
                  "--title", "教程 | 一篇已经确认的文章", "--opening", "A",
                  "--outline", "三段：问题、做法、边界", "--cover-style", "montage-evidence")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (article / "_blueprint-approval.md").read_text(encoding="utf-8")
    for needle in ("作者指定标题", "开头", "大纲", "封面风格"):
        assert needle in text   # 与 verify outline 的蓝图结构检查同一口径


def test_seal_failure_rolls_back_anchor(tmp_path):
    """new-draft 缺质检文件时封存失败：新建的审批文件删掉，旧文件恢复原样。"""
    article = _article(tmp_path)
    result = _run(article, "approve", "draft", "--source-mode", "new-draft", "--words", "过")
    assert result.returncode == 2 and "已回滚" in result.stdout
    assert not (article / "_draft-approval.md").exists()

    old = "# 定稿审批\n\n审批结论：待确认\n"
    (article / "_draft-approval.md").write_text(old, encoding="utf-8")
    assert _run(article, "approve", "draft", "--source-mode", "new-draft", "--words", "过").returncode == 2
    assert (article / "_draft-approval.md").read_text(encoding="utf-8") == old


def test_waiver_writes_waived_conclusion():
    text, errors = render_approval_anchor("blueprint", "这篇不用给我看大纲", source_mode="checkpoint-waived")
    assert not errors
    assert "作者免检授权：免检" in text and "审批结论：通过" not in text


def test_empty_words_are_rejected():
    _, errors = render_approval_anchor("draft", "   ", source_mode="author-provided-final")
    assert errors and "作者原话" in errors[0]
