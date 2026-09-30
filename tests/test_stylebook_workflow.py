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
from scripts.stylebook_workflow import validate, collect_host_result, digest, produce_candidate
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


def host_result_fixture(tmp_path, monkeypatch, *, text=None):
    from PIL import Image
    plan = setup_plan(tmp_path, monkeypatch)
    if text is not None:
        plan["cover"]["text"] = text
        (tmp_path / "visual-plan.json").write_text(json.dumps(plan, ensure_ascii=False))
    _, errors = compile_visual_plan(tmp_path)
    assert not errors
    pending, errors = render_visuals(tmp_path)
    assert not errors
    host = {key: value for key, value in pending.items() if key != "path"}
    image = tmp_path / "actual-tool-output.png"
    Image.new("RGB", (128, 128), "ivory").save(image)
    task = host["requests"][0]
    submitted = {"schema_version": 1, "backend": "image_gen.imagegen", "invocation_status": "succeeded",
                 "host_request_path": str(Path(pending["path"]).relative_to(tmp_path)),
                 "host_request_digest": digest(host), "request_id": host["request_id"], "id": task["id"],
                 "call": task["call"], "tool_output": "Synthetic tool response for tests only",
                 "output": {"path": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}}
    path = tmp_path / "host-result.json"
    path.write_text(json.dumps(submitted))
    return path, submitted, image


def test_collect_preserves_exact_raw_and_host_boundary_without_final_receipt(tmp_path, monkeypatch):
    path, _, image = host_result_fixture(tmp_path, monkeypatch)
    result, errors = collect_host_result(tmp_path, path)
    assert not errors
    assert result["status"] == "raw_collected_pending_production"
    assert result["source_strength"] == "host_attested"
    assert result["independent_invocation_verified"] is False
    assert result["actual_model"] is None and result["actual_cost"] is None
    assert (tmp_path / result["raw_path"]).read_bytes() == image.read_bytes()
    old_receipt = Path(result["receipt_path"]).read_bytes()
    again, errors = collect_host_result(tmp_path, path)
    assert not errors and again["receipt_path"] == result["receipt_path"]
    assert Path(result["receipt_path"]).read_bytes() == old_receipt
    assert not (tmp_path / "素材/cover.png").exists()
    manifest, errors = build_visual_manifest(tmp_path)
    assert not manifest and errors


@pytest.mark.parametrize("mutation", ["pending", "prompt", "hash", "no_output", "empty", "non_image", "old_source", "wrong_task", "host_request"])
def test_collect_rejects_mutants_at_actual_consumer(tmp_path, monkeypatch, mutation):
    path, result, image = host_result_fixture(tmp_path, monkeypatch)
    if mutation == "pending":
        result["invocation_status"] = "pending"
    elif mutation == "prompt":
        result["call"]["prompt"] += " abbreviated"
    elif mutation == "hash":
        result["output"]["sha256"] = "0" * 64
    elif mutation == "no_output":
        result["tool_output"] = ""
    elif mutation in ("empty", "non_image"):
        image.write_bytes(b"" if mutation == "empty" else b"not a picture")
        result["output"]["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    elif mutation == "old_source":
        (tmp_path / "定稿.md").write_text("作者改稿了")
    elif mutation == "wrong_task":
        result["id"] = "unknown"
    else:
        host_path = tmp_path / result["host_request_path"]
        host = json.loads(host_path.read_text())
        host["requests"][0]["call"]["prompt"] += " forged"
        host_path.write_text(json.dumps(host))
    path.write_text(json.dumps(result))
    collected, errors = collect_host_result(tmp_path, path)
    assert collected is None and errors
    assert not (tmp_path / "素材/stylebook-results").exists()


def test_actual_collect_cli_reports_raw_only(tmp_path, monkeypatch):
    path, _, _ = host_result_fixture(tmp_path, monkeypatch)
    entry = Path(__file__).resolve().parents[1] / "scripts/pipeline.py"
    run = subprocess.run([sys.executable, str(entry), "--dir", str(tmp_path), "collect-stylebook-result", "--result", str(path)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "最终制作与 QA 尚未完成" in run.stdout


def test_second_candidate_preserves_first_and_detects_damaged_saved_raw(tmp_path, monkeypatch):
    from PIL import Image
    path, submitted, image = host_result_fixture(tmp_path, monkeypatch)
    first, errors = collect_host_result(tmp_path, path)
    assert not errors
    first_raw = (tmp_path / first["raw_path"]).read_bytes()
    Image.new("RGB", (128, 128), "navy").save(image)
    submitted["output"]["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    path.write_text(json.dumps(submitted))
    second, errors = collect_host_result(tmp_path, path)
    assert not errors and second["raw_path"] != first["raw_path"]
    assert (tmp_path / first["raw_path"]).read_bytes() == first_raw
    assert Path(first["receipt_path"]).exists()
    (tmp_path / second["raw_path"]).write_bytes(b"damaged")
    refused, errors = collect_host_result(tmp_path, path)
    assert refused is None and any("拒绝覆盖" in value for value in errors)


def test_production_exports_real_pixels_and_preserves_pending_qa(tmp_path, monkeypatch):
    path, _, raw = host_result_fixture(tmp_path, monkeypatch)
    collected, errors = collect_host_result(tmp_path, path)
    assert not errors
    made, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert not errors, errors
    assert made["status"] == "produced_pending_qa"
    from PIL import Image
    with Image.open(tmp_path / made["files"]["main"]) as image:
        assert image.width > image.height
    assert made["outputs"]["main"]["sha256"] == hashlib.sha256((tmp_path / made["files"]["main"]).read_bytes()).hexdigest()
    assert not (tmp_path / "素材/cover.png").exists()
    assert raw.exists()
    repeated, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert not errors and repeated["production_id"] == made["production_id"]
    (tmp_path / made["files"]["main"]).write_bytes(b"replacement")
    refused, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert refused is None and any("拒绝覆盖" in value for value in errors)


@pytest.mark.parametrize("mutation", ["raw", "receipt", "plan", "article"])
def test_production_rejects_stale_or_replaced_inputs(tmp_path, monkeypatch, mutation):
    path, _, _ = host_result_fixture(tmp_path, monkeypatch)
    collected, errors = collect_host_result(tmp_path, path)
    assert not errors
    receipt = Path(collected["receipt_path"])
    if mutation == "raw":
        (tmp_path / collected["raw_path"]).write_bytes(b"replacement")
    elif mutation == "receipt":
        value = json.loads(receipt.read_text())
        value["id"] = "01"
        receipt.write_text(json.dumps(value))
    elif mutation == "article":
        (tmp_path / "定稿.md").write_text("changed")
    else:
        plan = json.loads((tmp_path / "visual-plan.json").read_text())
        plan["cover"]["content"]["subject"] += " changed"
        (tmp_path / "visual-plan.json").write_text(json.dumps(plan))
    made, errors = produce_candidate(tmp_path, receipt)
    assert made is None and errors
    assert not (tmp_path / "素材/stylebook-final").exists()


def test_production_detects_article_mutation_during_actual_export(tmp_path, monkeypatch):
    import importlib
    path, _, _ = host_result_fixture(tmp_path, monkeypatch)
    collected, errors = collect_host_result(tmp_path, path)
    assert not errors
    exporter = importlib.import_module("stylebook.export")
    original = exporter.export

    def changing_export(*args, **kwargs):
        result = original(*args, **kwargs)
        (tmp_path / "定稿.md").write_text("changed during production")
        return result

    monkeypatch.setattr(exporter, "export", changing_export)
    made, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert made is None and any("过程中" in value for value in errors)
    assert not (tmp_path / "素材/stylebook-final").exists()


def test_actual_overlay_tracks_font_bytes_and_rejects_font_change_during_export(tmp_path, monkeypatch):
    import importlib
    from PIL import Image, ImageFont
    spec = {"mode": "overlay", "items": [{"text": "来源", "box": [0.1, 0.1, 0.5, 0.5], "require_blank": True,
                                         "font_px": 48, "min_px": 40}]}
    path, _, _ = host_result_fixture(tmp_path, monkeypatch, text=spec)
    collected, errors = collect_host_result(tmp_path, path)
    assert not errors
    overlay = importlib.import_module("stylebook.overlay")
    try:
        font = overlay._font("regular", 48, "sans")
    except ValueError:
        pytest.skip("当前环境未安装真实中文字体")
    test_font = tmp_path / "real-font-copy.otf"
    test_font.write_bytes(Path(font.path).read_bytes())
    monkeypatch.setattr(overlay, "_font", lambda weight, size, family="sans": ImageFont.truetype(str(test_font), size, index=font.index))
    made, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert not errors, errors
    assert made["dependencies_sha256"][str(test_font)] == hashlib.sha256(test_font.read_bytes()).hexdigest()
    with Image.open(tmp_path / made["files"]["main"]) as image:
        assert min(image.convert("L").getextrema()) < 80  # Blank ivory raw acquired visible lettering.
    exporter = importlib.import_module("stylebook.export")
    original = exporter.export

    def changing_font(*args, **kwargs):
        result = original(*args, **kwargs)
        test_font.write_bytes(test_font.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(exporter, "export", changing_font)
    refused, errors = produce_candidate(tmp_path, Path(collected["receipt_path"]))
    assert refused is None and any("过程中" in value for value in errors)


def test_adopt_final_metadata_uses_explicit_stylebook_contract(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from scripts.release_job import _validate_final_and_meta
    plan = setup_plan(tmp_path, monkeypatch)
    draft = tmp_path / "定稿.md"
    draft.write_text("工具先下载，然后验证来源。\n" * 150)
    content_sha = hashlib.sha256(draft.read_bytes()).hexdigest()
    plan["source"]["sha256"] = content_sha
    plan["source"]["author_content_sha256"] = author_content_sha256(draft.read_text())
    plan["article_plan"]["source"]["sha256"] = content_sha
    plan["cover"]["source"]["sha256"] = content_sha
    plan_path = tmp_path / "visual-plan.json"
    plan_path.write_text(json.dumps(plan))
    meta = tmp_path / "article-meta.yaml"
    meta.write_text('title: "教程 | 下载与验证"\ncategory: TUT\noutward_category: tutorial\ntags: [AI工具]\ndigest: 下载后验证来源。\n')
    assert not _validate_final_and_meta(draft, meta)[1]
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/pipeline.py"), "adopt-final"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 2 and "不得替作者自签" in result.stdout
    assert not (tmp_path / ".state.json").exists()
    assert not list(tmp_path.rglob("_release-job.json"))

    # 同一真实消费者路径：正文漂移和缺锁合同均不得借新路线绕过。
    draft.write_text(draft.read_text() + "改变作者正文")
    assert any("正文摘要" in x for x in _validate_final_and_meta(draft, meta)[1])
    draft.write_text("工具先下载，然后验证来源。\n" * 150)
    plan["group"]["style"] = "C31"
    plan_path.write_text(json.dumps(plan))
    assert any("锁定样式" in x for x in _validate_final_and_meta(draft, meta)[1])
    plan["schema_version"] = 3
    plan_path.write_text(json.dumps(plan))
    assert any("schema_version" in x for x in _validate_final_and_meta(draft, meta)[1])

    # 移除显式选择后，缺少旧粘土配置必须被拒绝。
    plan_path.unlink()
    assert any("claymation" in x for x in _validate_final_and_meta(draft, meta)[1])
