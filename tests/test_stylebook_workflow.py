"""Actual contract/CLI checks for the opt-in article Stylebook route."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.assemble_release import author_content_sha256, assemble_release_markdown
from scripts.evidence import build_visual_manifest
from scripts.render_visuals import render_visuals
from scripts.stylebook_workflow import validate
from scripts.visual_workflow import compile_visual_plan, validate_visual_plan


def setup_plan(tmp_path, monkeypatch, *, body=True):
    root = Path(__file__).resolve().parents[2] / "sansheng-stylebook"
    if not (root / "scripts/stylebook/plan.py").is_file():
        pytest.skip("需要相邻的可选画风手册本体")
    monkeypatch.setenv("SANSHENG_STYLEBOOK_ROOT", str(root))
    article = tmp_path / "定稿.md"
    article.write_text("工具先下载，然后验证来源。\n")
    code = "C31@r" + str(json.loads((root / "styles/C31/contract.json").read_text())["revision"])
    sha = hashlib.sha256(article.read_bytes()).hexdigest()
    item = {"id": "01", "position": "「工具先下载，然后验证来源。」之后", "source_quote": "工具先下载，然后验证来源。",
            "shape": "steps", "form": "structure", "structure": "flow",
            "points": ["先下载工具", "再验证来源"], "what": "下载与验证", "subject": "A package then a source verification check",
            "why": "两个动作存在明确先后关系，流程图能展示对应顺序。", "use_anchor": False}
    plan = {"schema_version": 2, "workflow": "stylebook-v1",
            "source": {"sha256": sha, "author_content_sha256": author_content_sha256(article.read_text())},
            "group": {"style": code}, "renderer": {"backend": "host-imagegen"},
            "article_plan": {"version": 3, "scene": "wxillus", "source": {"path": "定稿.md", "sha256": sha},
                             "style": {"code": code, "source": "explicit", "why": "作者显式选择本次画风"},
                             "coverage": [{"claim": "下载与验证", "source_quote": item["source_quote"],
                                           "decision": "image" if body else "text_sufficient", "image_ids": ["01"] if body else [],
                                           "why": "两个动作的顺序通过图解表达更清晰" if body else "只有两步的短文文字本身已经表达顺序，无需新增正文图"}],
                             "items": [item] if body else []},
            "cover": {"style": code, "format": "wechat-cover-head", "use_anchor": False,
                      "source": {"sha256": sha, "quote": item["source_quote"]},
                      "content": {"subject": "A small package with a source check inside one rounded pastel card"},
                      "text": {"mode": "none"}}}
    (tmp_path / "visual-plan.json").write_text(json.dumps(plan, ensure_ascii=False))
    return plan


@pytest.mark.parametrize("body", [False, True])
def test_actual_compile_and_render_entry_preserve_pending_and_old_contract(tmp_path, monkeypatch, body):
    setup_plan(tmp_path, monkeypatch, body=body)
    result, errors = compile_visual_plan(tmp_path)
    assert not errors and result["prompt_count"] == 1 + int(body)
    frozen = Path(result["request_path"]).read_bytes()
    pending, errors = render_visuals(tmp_path)
    assert not errors and pending["status"] == "pending_host"
    assert len(pending["requests"]) == 1 + int(body)
    assert not (tmp_path / "素材/cover.png").exists()
    manifest, errors = build_visual_manifest(tmp_path)
    assert not manifest and errors
    assembled, errors = assemble_release_markdown(tmp_path)
    assert assembled is None and errors
    assert Path(result["request_path"]).read_bytes() == frozen


def test_pending_requests_reject_changed_prompt_and_author_text(tmp_path, monkeypatch):
    setup_plan(tmp_path, monkeypatch)
    compiled, errors = compile_visual_plan(tmp_path)
    assert not errors
    path = tmp_path / "素材/render-batch.json"
    before = path.read_bytes()
    batch = json.loads(before)
    batch["tasks"][0]["compiled"]["prompt"] += " replacement"
    path.write_text(json.dumps(batch))
    pending, errors = render_visuals(tmp_path)
    assert pending is None and errors
    path.write_bytes(before)
    (tmp_path / "定稿.md").write_text("替换作者正文")
    pending, errors = render_visuals(tmp_path)
    assert pending is None and any("原文" in x for x in errors)
    assert Path(compiled["request_path"]).exists()


def test_reference_mutation_and_unknown_local_selection_reject_real_render_entry(tmp_path, monkeypatch):
    from PIL import Image
    plan = setup_plan(tmp_path, monkeypatch)
    ref = tmp_path / "ref.png"
    Image.new("RGB", (128, 128), "ivory").save(ref)
    plan["cover"]["references"] = [{"path": "ref.png", "role": "style"}]
    (tmp_path / "visual-plan.json").write_text(json.dumps(plan, ensure_ascii=False))
    result, errors = compile_visual_plan(tmp_path)
    assert not errors
    pending, errors = render_visuals(tmp_path, only={"01"})
    assert not errors and [x["id"] for x in pending["requests"]] == ["01"]
    pending, errors = render_visuals(tmp_path, only={"not-a-task"})
    assert pending is None and errors
    Image.new("RGB", (128, 128), "black").save(ref)
    pending, errors = render_visuals(tmp_path)
    assert pending is None and any("参考图" in x for x in errors)


def test_version_pairs_group_conflicts_and_empty_source_fail_closed(tmp_path, monkeypatch):
    plan = setup_plan(tmp_path, monkeypatch)
    for field, value in [("schema_version", 9), ("schema_version", 2.0), ("workflow", "unknown"), ("source", {}), ("source", [])]:
        changed = copy.deepcopy(plan)
        changed[field] = value
        assert validate(changed)
    changed = copy.deepcopy(plan)
    changed["cover"]["style"] = "C01@r1"
    assert validate_visual_plan(changed)
    (tmp_path / "定稿.md").write_bytes(b"")
    result, errors = compile_visual_plan(tmp_path)
    assert result is None and errors


def test_actual_cli_cannot_claim_pending_requests_as_rendered(tmp_path, monkeypatch):
    setup_plan(tmp_path, monkeypatch)
    entry = Path(__file__).resolve().parents[1] / "scripts/pipeline.py"
    compiled = subprocess.run([sys.executable, str(entry), "--dir", str(tmp_path), "compile-visuals"], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    pending = subprocess.run([sys.executable, str(entry), "--dir", str(tmp_path), "render-visuals"], capture_output=True, text=True)
    assert pending.returncode == 3 and "尚未生成成品" in pending.stdout
