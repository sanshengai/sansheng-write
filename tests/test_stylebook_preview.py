"""Optional peer-Skill preview: source binding and separation from the release chain."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.stylebook_preview import compile_preview


def _stylebook() -> Path:
    candidate = Path(__file__).resolve().parents[2] / "sansheng-image"
    if not (candidate / "scripts/stylebook/plan.py").is_file():
        pytest.skip("画风库是可选的独立 Skill，本测试需要相邻的本体")
    return candidate


def _plan(article: Path, *, with_image: bool) -> dict:
    quote = "工具先下载，然后验证来源"
    image = {"id": "01", "position": f"§1「{quote}」之后", "source_quote": quote,
             "shape": "steps", "form": "structure", "structure": "flow",
             "points": ["先下载工具", "再验证来源"], "what": "下载与来源验证流程",
             "subject": "A downloaded software package followed by an official source verification marker",
             "why": "两个动作有顺序关系，读者需看清下载后再验证来源"}
    return {"version": 3, "source": {"path": "定稿.md", "sha256": hashlib.sha256(article.read_bytes()).hexdigest()},
            "scene": "wxillus", "style": {"code": "C01", "source": "factory", "why": "公开默认画风用于预览集成"},
            "coverage": [{"claim": "下载并验证来源", "source_quote": quote,
                          "decision": "image" if with_image else "text_sufficient",
                          "image_ids": ["01"] if with_image else [],
                          "why": "两个动作有先后关系，流程图能帮助理解" if with_image else
                                 "原文只包含两个明确动作，顺序清楚，图像不会增加必要信息"}],
            "items": [image] if with_image else []}


def test_preview_keeps_exact_prompt_and_source_without_touching_release_inputs(tmp_path):
    article = tmp_path / "定稿.md"
    article.write_text("工具先下载，然后验证来源。", encoding="utf-8")
    plan = tmp_path / "stylebook-plan.json"
    plan.write_text(json.dumps(_plan(article, with_image=True), ensure_ascii=False), encoding="utf-8")
    receipt, errors = compile_preview(tmp_path, plan, stylebook_root=str(_stylebook()))
    assert not errors
    assert receipt["status"] == "preview_only" and receipt["renderer"] is None
    assert receipt["plan_review"] == "not_run" and receipt["new_image_count"] == 1
    image = receipt["images"][0]
    assert image["manifest"]["source"]["sha256"] == receipt["article_sha256"]
    assert image["manifest"]["source"]["quote"] == "工具先下载，然后验证来源"
    assert "official source verification marker" in image["compiled"]["prompt"]
    assert len(receipt["method_source"]["digest"]) == 64
    assert not (tmp_path / "visual-plan.json").exists()
    assert not (tmp_path / "素材/render-batch.json").exists()
    assert not (tmp_path / "素材/visual-compile-receipt.json").exists()

    frozen = Path(receipt["path"]).read_bytes()
    article.write_text("工具先下载，然后验证来源。新增一句。", encoding="utf-8")
    stale, problems = compile_preview(tmp_path, plan, stylebook_root=str(_stylebook()))
    assert stale is None and any("SHA-256 失效" in issue for issue in problems)
    assert Path(receipt["path"]).read_bytes() == frozen


def test_zero_image_preview_is_explicit_and_rejects_foreign_article(tmp_path):
    article = tmp_path / "定稿.md"
    article.write_text("工具先下载，然后验证来源。", encoding="utf-8")
    plan = tmp_path / "stylebook-plan.json"
    data = _plan(article, with_image=False)
    plan.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    receipt, errors = compile_preview(tmp_path, plan, stylebook_root=str(_stylebook()))
    assert not errors and receipt["new_image_count"] == 0 and receipt["images"] == []
    assert receipt["plan_review"] == "not_run"

    foreign = tmp_path / "other.md"
    foreign.write_bytes(article.read_bytes())
    data["source"]["path"] = "other.md"
    plan.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    invalid, problems = compile_preview(tmp_path, plan, stylebook_root=str(_stylebook()))
    assert invalid is None and any("当前文章" in issue for issue in problems)
