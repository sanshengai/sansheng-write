# -*- coding: utf-8 -*-
"""文末双模块必须走标准模板，不能用普通标题或裸链接冒充。"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import contracts  # noqa: E402
import profile_config  # noqa: E402


def _article(tmp_path: Path) -> Path:
    d = tmp_path / "1-test"
    d.mkdir()
    (d / "定稿.md").write_text(
        "---\ntitle: 测试\ndescription: 摘要\n---\n\n# 测试\n\n正文。\n",
        encoding="utf-8",
    )
    (d / "article-meta.yaml").write_text(
        "weave:\n"
        "  link: \"联动旧文 https://mp.weixin.qq.com/s/old\"\n"
        "  base: \"自有站点 https://example.com\"\n"
        "endmatter:\n"
        "  version: 1\n"
        "  deep_read: true\n"
        "  sources: auto\n",
        encoding="utf-8",
    )
    (d / "_fact-check.md").write_text(
        "核验来源：https://source.example/report\n", encoding="utf-8"
    )
    return d


def test_endmatter_markers_are_hard_gates(tmp_path, monkeypatch):
    d = _article(tmp_path)
    monkeypatch.setattr(profile_config, "identity", lambda: {"site": "https://example.com"})

    result = contracts.verify_publish_assets(str(d))
    assert result["verdict"] == "fail"
    assert any("SANSHENG-DEEP-READ" in e for e in result["errors"])
    assert any("SANSHENG-SOURCES" in e for e in result["errors"])


def test_standard_deep_read_and_sources_pass(tmp_path, monkeypatch):
    d = _article(tmp_path)
    monkeypatch.setattr(profile_config, "identity", lambda: {"site": "https://example.com"})
    with (d / "定稿.md").open("a", encoding="utf-8") as f:
        f.write(
            "\n<!-- SANSHENG-DEEP-READ -->\n"
            "<section>DEEP READ 继续往下读 "
            "https://mp.weixin.qq.com/s/old https://example.com</section>\n"
            "<!-- SANSHENG-SOURCES -->\n"
            "<section>SOURCES 信息来源 https://source.example/report</section>\n"
        )

    result = contracts.verify_publish_assets(str(d))
    assert result["verdict"] == "ok", result["errors"]
    assert result["checks_passed"] == result["checks_total"] == 9
