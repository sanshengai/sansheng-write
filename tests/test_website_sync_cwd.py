"""官网同步 cwd 必须跟着文章所在的 git 检出走（2026-09-18 假绿实证）。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pipeline  # noqa: E402


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_article_in_other_checkout_wins_over_configured_main(tmp_path, capsys):
    main = _init_repo(tmp_path / "main")
    wt = _init_repo(tmp_path / "wt")
    article = wt / "成品" / "1-篇"
    article.mkdir(parents=True)
    assert pipeline._website_cwd_for_article(article, str(main)) == wt.resolve()
    assert "官网同步改在文章所在检出执行" in capsys.readouterr().out


def test_same_checkout_keeps_configured_cwd(tmp_path):
    main = _init_repo(tmp_path / "main")
    article = main / "成品" / "1-篇"
    article.mkdir(parents=True)
    assert pipeline._website_cwd_for_article(article, str(main)) == main


def test_article_outside_git_falls_back_to_configured(tmp_path):
    main = _init_repo(tmp_path / "main")
    article = tmp_path / "loose" / "1-篇"
    article.mkdir(parents=True)
    assert pipeline._website_cwd_for_article(article, str(main)) == main
