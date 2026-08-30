from pathlib import Path
import os
import subprocess
import sys

import pytest

from scripts import profile_config as pc
from scripts import works_registry as package_wr

# pipeline 的历史调用方式会把 scripts/ 放进 sys.path 后按裸模块名导入；同时验证
# 两套 import 入口共享的公开行为，不依赖某个特定进程启动顺序。
import generate_recommend_html as recommend
import learn_edits
import render_articles_md as articles
import render_works_dashboard as dashboard
import works_registry as wr
import format_layout as layout


PATH_ENV = (
    "SANSHENG_WRITE_PROFILE_DIR",
    "SANSHENG_WRITE_DATA_DIR",
    "SANSHENG_WRITE_WORKS_FILE",
    "SANSHENG_WRITE_FLYWHEEL_DIR",
    "SANSHENG_WRITE_GOLDEN_LINES_FILE",
    "SANSHENG_WRITE_WORKSPACE_DIR",
    "SANSHENG_WRITE_ACTIVE_WORKSPACE",
)


@pytest.fixture(autouse=True)
def _clean_binding(monkeypatch):
    for name in PATH_ENV:
        monkeypatch.delenv(name, raising=False)
    pc._reset_cache_for_tests()
    # 裸模块与 package 模块在测试进程中可能是两个实例；两边都清掉。
    import profile_config as bare_pc
    bare_pc._reset_cache_for_tests()
    yield
    pc._reset_cache_for_tests()
    bare_pc._reset_cache_for_tests()


def _workspace(tmp_path: Path, name: str, brand_name: str) -> tuple[Path, Path]:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    article = root / "文稿成品" / "97-测试"
    article.mkdir(parents=True)
    profile = root / "profile"
    profile.mkdir()
    (profile / "brand.yaml").write_text(
        f"name: {brand_name}\ncolors:\n  primary: '#123456'\n",
        encoding="utf-8",
    )
    return root, article


def _configure_tokens(monkeypatch):
    values = {
        "SANSHENG_WRITE_PROFILE_DIR": "@workspace/profile",
        "SANSHENG_WRITE_DATA_DIR": "@workspace/文稿成品",
        "SANSHENG_WRITE_WORKS_FILE": "@workspace/文稿成品/作品库.yaml",
        "SANSHENG_WRITE_FLYWHEEL_DIR": "@workspace/private/flywheel",
        "SANSHENG_WRITE_GOLDEN_LINES_FILE": "@workspace/prompts/金句库.md",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _bind_both(article_dir: Path):
    """两种历史 import 名必须桥接到同一实例，只绑定一次。"""
    import profile_config as bare_pc
    assert pc is bare_pc
    return pc.bind_workspace(article_dir)


def test_package_and_bare_import_share_one_module_instance():
    import profile_config as bare_pc

    assert pc is bare_pc


def test_workspace_tokens_fail_closed_until_article_is_bound(tmp_path, monkeypatch):
    _configure_tokens(monkeypatch)
    with pytest.raises(pc.WorkspaceBindingError, match="bind_workspace"):
        pc.data_dir()

    root, article = _workspace(tmp_path, "tree-a", "甲品牌")
    assert pc.bind_workspace(article) == root
    assert pc.profile_dir() == root / "profile"
    assert pc.data_dir() == root / "文稿成品"
    assert pc.works_file() == root / "文稿成品" / "作品库.yaml"
    assert pc.flywheel_dir() == root / "private" / "flywheel"
    assert pc.golden_lines_file() == root / "prompts" / "金句库.md"


def test_dynamic_paths_and_render_brand_follow_rebinding(tmp_path, monkeypatch):
    _configure_tokens(monkeypatch)
    root_a, article_a = _workspace(tmp_path, "tree-a", "甲品牌")
    root_b, article_b = _workspace(tmp_path, "tree-b", "乙品牌")

    _bind_both(article_a)
    assert Path(wr.WORKS_FILE) == root_a / "文稿成品" / "作品库.yaml"
    assert Path(package_wr.WORKS_FILE) == root_a / "文稿成品" / "作品库.yaml"
    assert Path(articles.ARTICLES_MD) == root_a / "文稿成品" / "articles.md"
    assert Path(dashboard.DASHBOARD_FILE) == root_a / "文稿成品" / "works-dashboard.html"
    assert Path(recommend.ARTICLES_DB_PATH) == root_a / "文稿成品" / "articles.md"
    assert Path(learn_edits.LESSONS_FILE) == root_a / "private" / "flywheel" / "lessons.yaml"
    assert "甲品牌" in articles.render_md([])
    assert "甲品牌作品库" in dashboard.build_html([])

    _bind_both(article_b)
    assert Path(wr.WORKS_FILE) == root_b / "文稿成品" / "作品库.yaml"
    assert Path(articles.ARTICLES_MD) == root_b / "文稿成品" / "articles.md"
    assert Path(dashboard.DASHBOARD_FILE) == root_b / "文稿成品" / "works-dashboard.html"
    assert Path(recommend.ARTICLES_DB_PATH) == root_b / "文稿成品" / "articles.md"
    assert Path(learn_edits.VOICE_CORPUS_FILE) == root_b / "profile" / "corpus" / "voice-samples.md"
    assert "乙品牌" in articles.render_md([])
    assert "乙品牌作品库" in dashboard.build_html([])


def test_workspace_token_cannot_escape_root(tmp_path, monkeypatch):
    root, article = _workspace(tmp_path, "tree", "品牌")
    assert pc.bind_workspace(article) == root
    with pytest.raises(pc.WorkspaceBindingError, match="不能逃出"):
        pc.resolve_config_path("@workspace/../outside", setting="TEST_PATH")


@pytest.mark.parametrize(
    "value",
    (
        "@workspaceevil/path",
        "@Workspace/path",
        "@workspace:C:/outside",
        "@workspace/C:/outside",
        "@workspace//server/share",
        "@workspace/\\\\server\\share",
    ),
)
def test_workspace_token_rejects_malformed_or_anchored_suffix(tmp_path, value):
    root, article = _workspace(tmp_path, "tree", "品牌")
    pc.bind_workspace(article)
    with pytest.raises(pc.WorkspaceBindingError, match="非法|相对路径"):
        pc.resolve_config_path(value, setting="TEST_PATH")


def test_non_git_absolute_paths_keep_working_without_binding(tmp_path, monkeypatch):
    data = tmp_path / "articles"
    monkeypatch.setenv("SANSHENG_WRITE_DATA_DIR", str(data))
    assert pc.bind_workspace(tmp_path) is None
    assert pc.data_dir() == data


def test_explicit_workspace_supports_non_git_article_dir(tmp_path, monkeypatch):
    root = tmp_path / "plain-workspace"
    article = root / "文稿成品" / "1-test"
    article.mkdir(parents=True)
    monkeypatch.setenv("SANSHENG_WRITE_WORKSPACE_DIR", str(root))
    monkeypatch.setenv("SANSHENG_WRITE_DATA_DIR", "@workspace/文稿成品")
    assert pc.bind_workspace(article) == root
    assert pc.data_dir() == root / "文稿成品"


def test_explicit_workspace_must_be_absolute(tmp_path, monkeypatch):
    article = tmp_path / "article"
    article.mkdir()
    monkeypatch.setenv("SANSHENG_WRITE_WORKSPACE_DIR", "relative-workspace")
    with pytest.raises(pc.WorkspaceBindingError, match="绝对路径"):
        pc.bind_workspace(article)


def test_explicit_workspace_must_contain_article(tmp_path, monkeypatch):
    configured = tmp_path / "main"
    configured.mkdir()
    article = tmp_path / "worktree" / "article"
    article.mkdir(parents=True)
    monkeypatch.setenv("SANSHENG_WRITE_WORKSPACE_DIR", str(configured))
    with pytest.raises(pc.WorkspaceBindingError, match="包含当前文章目录"):
        pc.bind_workspace(article)


def test_active_workspace_propagates_to_real_child_process(tmp_path, monkeypatch):
    root, article = _workspace(tmp_path, "tree", "品牌")
    _configure_tokens(monkeypatch)
    pc.bind_workspace(article)

    env = os.environ.copy()
    env.pop("SANSHENG_WRITE_WORKSPACE_DIR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import profile_config as pc; "
                "print(pc.workspace_root()); print(pc.data_dir())"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1] / "scripts",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(root), str(root / "文稿成品")]


def test_format_layout_loads_theme_only_after_target_workspace_binding(tmp_path, monkeypatch):
    for name in (
        "_C", "_R", "BRAND_PRIMARY", "BRAND_SECONDARY", "RADIUS_SM",
        "RADIUS_MEDIA", "RADIUS_CARD", "RADIUS_MODULE", "RADIUS_PILL",
        "TINT_CARD", "TINT_SOFT", "TINT_INSET", "TINT_ROW", "BORDER_CARD",
        "BORDER_HAIR", "TEXT_BODY", "TEXT_TITLE", "TEXT_MUTED", "_THEME_DEFAULTS",
    ):
        monkeypatch.setattr(layout, name, getattr(layout, name))
    _configure_tokens(monkeypatch)
    root_a, article_a = _workspace(tmp_path, "tree-a", "甲品牌")
    root_b, article_b = _workspace(tmp_path, "tree-b", "乙品牌")
    (root_b / "profile" / "brand.yaml").write_text(
        "name: 乙品牌\ncolors:\n  primary: '#654321'\nradius:\n  card: 18px\n",
        encoding="utf-8",
    )
    html_a = article_a / "定稿.html"
    html_b = article_b / "定稿.html"
    html_a.write_text("<p>#2F6F8F</p>", encoding="utf-8")
    html_b.write_text("<p>#2F6F8F</p>", encoding="utf-8")

    layout._bind_layout_workspace(html_a)
    assert layout.BRAND_PRIMARY == "#123456"
    layout._bind_layout_workspace(html_b)
    assert layout.BRAND_PRIMARY == "#654321"
    assert layout.RADIUS_CARD == "18px"
    assert "#654321" in layout.process_theme("<p>#2F6F8F</p>")


def test_pipeline_binds_selected_article_before_dispatch(tmp_path, monkeypatch):
    import pipeline
    import profile_config as bare_pc

    article = tmp_path / "article"
    article.mkdir()
    calls = []
    monkeypatch.setattr(
        bare_pc, "bind_workspace", lambda path: calls.append(("bind", Path(path)))
    )
    monkeypatch.setattr(
        pipeline, "cmd_status", lambda path: calls.append(("status", Path(path)))
    )
    monkeypatch.setattr(
        sys, "argv", ["pipeline.py", "--dir", str(article), "status"]
    )

    pipeline.main()

    assert calls == [("bind", article.resolve()), ("status", article.resolve())]
