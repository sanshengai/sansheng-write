"""测试期的 Baoyu 依赖 fixture。

`scripts/baoyu_contract.py` 把 Baoyu 视觉能力做成了**真实依赖**：编译期要从磁盘上的
`baoyu-infographic/SKILL.md` 解析 Layout Gallery 枚举并记 sha256，发布期重新解析比对。
这在本机成立（四端共享真源里有这些能力），但公开仓 CI 不会安装 Baoyu。

因此测试统一通过 `SANSHENG_WRITE_BAOYU_SKILL_ROOT` 注入一份最小 fixture：
契约逻辑照常被完整验证（枚举解析、数量自校验、sha 比对、篡改检出），
只是不依赖真机上是否装了 Baoyu。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.baoyu_contract import SKILL_ROOT_ENV

# 与 baoyu-infographic SKILL.md 的 Layout Gallery 同构（21 项）。
# 必须覆盖本仓 INFOGRAPHIC_LAYOUTS 的全部 key，否则编译期硬门会拒绝——
# 这正是该门要守的东西：本仓版式语言必须整体取自 Baoyu 枚举。
_LAYOUTS = [
    "linear-progression",
    "binary-comparison",
    "comparison-matrix",
    "hierarchical-layers",
    "tree-branching",
    "hub-spoke",
    "structural-breakdown",
    "bento-grid",
    "iceberg",
    "bridge",
    "funnel",
    "isometric-map",
    "dashboard",
    "periodic-table",
    "comic-strip",
    "story-mountain",
    "jigsaw",
    "venn-diagram",
    "winding-roadmap",
    "circular-flow",
    "dense-modules",
]


def _infographic_skill_md() -> str:
    rows = "\n".join(f"| `{name}` | fixture |" for name in _LAYOUTS)
    return (
        "---\nname: baoyu-infographic\n---\n\n"
        "# Baoyu Infographic (test fixture)\n\n"
        f"## Layout Gallery ({len(_LAYOUTS)})\n\n"
        "| Layout | Best For |\n|--------|----------|\n"
        f"{rows}\n\n"
        "## Style Gallery (22)\n\n"
        "| Style | Feel |\n|-------|------|\n| `craft-handmade` | fixture |\n"
    )


@pytest.fixture(autouse=True)
def baoyu_skill_fixture(tmp_path_factory, monkeypatch):
    """为每个测试注入一份可解析的最小 Baoyu 能力根。"""
    root = tmp_path_factory.mktemp("baoyu-skills")
    info = root / "baoyu-infographic"
    info.mkdir()
    (info / "SKILL.md").write_text(_infographic_skill_md(), encoding="utf-8")

    article = root / "baoyu-article-illustrator"
    article.mkdir()
    (article / "SKILL.md").write_text(
        "---\nname: baoyu-article-illustrator\n---\n\n"
        "# Baoyu Article Illustrator (test fixture)\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(SKILL_ROOT_ENV, str(root))
    return root
