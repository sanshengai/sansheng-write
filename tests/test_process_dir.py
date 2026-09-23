"""机器回执收进 过程记录/（2026-09-23 审计 E4）。

文章目录第一层曾有 48 项，其中 28 个是机器回执，作者要找的上传文件混在里面。新文章的
机器回执写进 过程记录/；旧文章第一层已有的回执照旧在第一层读写，同一份回执不分两处。
"""
import re
import subprocess
import sys
from pathlib import Path

from scripts import pipeline
from scripts.article_paths import PROCESS_DIR, PROCESS_FILES, process_file, process_rel

PIPELINE = Path(pipeline.__file__).resolve()
SCRIPTS = PIPELINE.parent


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PIPELINE), *args], cwd=cwd, text=True,
                          encoding="utf-8", capture_output=True, check=False)


def _article(tmp_path: Path) -> Path:
    article = tmp_path / "88-process-dir"
    article.mkdir()
    (article / "定稿.md").write_text(
        "---\ntitle: \"教程 | 一篇已经确认的文章\"\ndescription: \"摘要。\"\n---\n\n"
        "# 教程 | 一篇已经确认的文章\n\n" + "这是作者已经审定的正文内容，只需要进入发布后端。\n" * 80,
        encoding="utf-8")
    (article / "article-meta.yaml").write_text(
        'title: "教程 | 一篇已经确认的文章"\ncategory: "TUT"\noutward_category: "tutorial"\n'
        'tags: ["AI工具"]\ndigest: "摘要。"\nlead:\n  line1: "规则不能丢"\n  line2: "发布链也要稳"\n'
        '  accent: "也要稳"\n  subtitle: "文章导读"\n  tag1: "硬门"\n  tag2: "证据"\n'
        '  ghost: "RULE × GATE × PROOF"\ncover_style: "montage-evidence"\n'
        'infographic_subject: "ai-product"\ninfographic_style: "claymation"\nvisual_profile: "warm-light-clay"\n',
        encoding="utf-8")
    return article


# ---------- 解析规则 ----------

def test_new_file_goes_to_process_dir_and_legacy_root_wins(tmp_path):
    assert process_rel(tmp_path, "_release-job.json") == f"{PROCESS_DIR}/_release-job.json"
    assert not (tmp_path / PROCESS_DIR).exists()            # 只读解析不建目录
    path = process_file(tmp_path, "_release-job.json", for_write=True)
    assert path.parent.is_dir()
    (tmp_path / "_release-job.json").write_text("{}", encoding="utf-8")
    assert process_file(tmp_path, "_release-job.json") == tmp_path / "_release-job.json"


def test_agent_written_reviews_stay_on_top_level(tmp_path):
    for name in ("_fact-check.md", "_stutter-list.md", "_draft-qc.md", "_opening-choice.md"):
        assert name not in PROCESS_FILES
        assert process_file(tmp_path, name) == tmp_path / name


# ---------- 端到端：新文章第一层不再出现机器回执 ----------

def test_approve_and_adopt_keep_top_level_clean(tmp_path):
    article = _article(tmp_path)
    before = {p.name for p in article.iterdir()}
    assert _run(article, "approve", "draft", "--source-mode", "author-provided-final",
                "--words", "过").returncode == 0
    result = _run(article, "adopt-final")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _run(article, "verify-release-job").returncode == 0
    new_top = {p.name for p in article.iterdir()} - before
    assert not [name for name in new_top if name.startswith("_")], new_top
    for name in ("_draft-approval.md", "_checkpoint-receipts.json", "_release-job.json", "_prep-context.md"):
        assert (article / PROCESS_DIR / name).is_file(), name


def test_legacy_article_keeps_its_top_level_approval(tmp_path):
    article = _article(tmp_path)
    (article / "_draft-approval.md").write_text("# 定稿审批\n\n审批结论：通过\n", encoding="utf-8")
    result = _run(article, "adopt-final")
    assert result.returncode == 0, result.stdout + result.stderr
    import json
    job = json.loads(process_file(article, "_release-job.json").read_text(encoding="utf-8"))
    assert job["approval_evidence"]["path"] == "_draft-approval.md"
    assert not (article / PROCESS_DIR / "_draft-approval.md").exists()
    assert _run(article, "verify-release-job").returncode == 0


# ---------- 静态守护：脚本不得再把回执直接拼到文章第一层 ----------

# 交接的外部导出目录不是文章目录，回执照旧放导出根目录
_ALLOWED = {
    ("handoff_assets.py", "receipt_path = target / HANDOFF_RECEIPT_FILE"),
    ("handoff_assets.py", "(temp / HANDOFF_RECEIPT_FILE).write_bytes(_canonical_json(receipt))"),
}


def _process_constants() -> tuple[set[str], dict[str, set[str]]]:
    """全局无歧义的过程文件常量名，以及只在定义文件内按过程文件处理的歧义名。"""
    defs: dict[str, set[str]] = {}
    local: dict[str, set[str]] = {}
    for f in SCRIPTS.glob("*.py"):
        for name, value in re.findall(r'^([A-Z_]+)\s*=\s*["\']([^"\']+)["\']', f.read_text(encoding="utf-8"), re.M):
            defs.setdefault(name, set()).add(value)
            if value in PROCESS_FILES:
                local.setdefault(f.name, set()).add(name)
    unambiguous = {n for n, values in defs.items() if values <= PROCESS_FILES}
    return unambiguous, local


def test_scripts_resolve_receipts_through_process_file():
    names = "|".join(re.escape(n) for n in PROCESS_FILES)
    literal = re.compile(r'/ ?["\'](' + names + r')["\']|os\.path\.join\([^)]*["\'](' + names + r')["\']')
    unambiguous, local = _process_constants()
    offenders = []
    for f in sorted(SCRIPTS.glob("*.py")):
        if f.name == "article_paths.py":
            continue
        consts = unambiguous | local.get(f.name, set())
        const = re.compile(r'/ ?(?:(\w+)\.)?(' + "|".join(sorted(consts)) + r')\b') if consts else None
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            text = line.strip()
            if text.startswith("#") or "process_file" in text or "process_rel" in text:
                continue
            if (f.name, text) in _ALLOWED:
                continue
            hit = literal.search(text)
            m = const.search(text) if const else None
            if m and m.group(1) in ("distribute",):   # dist/<渠道>/_receipt.json 不是过程文件
                m = None
            if hit or m:
                offenders.append(f"{f.name}:{i}: {text}")
    assert offenders == [], "\n".join(offenders)


# ---------- .bak 清理 ----------

def test_layout_success_cleans_html_backups(tmp_path):
    (tmp_path / "定稿.html").write_text("<p>ok</p>", encoding="utf-8")
    for stamp in ("20260923035137", "20260923035850"):
        (tmp_path / f"定稿.html.bak-{stamp}").write_text("old", encoding="utf-8")
    (tmp_path / "别的.bak-1").write_text("keep", encoding="utf-8")
    assert pipeline._cleanup_html_backups(tmp_path) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["别的.bak-1", "定稿.html"]
