import json
import sys
from pathlib import Path

import pytest

VISUAL_PRODUCER = "sansheng-write.visual-planner"


def test_native_raster_guard_rejects_svg_payload_saved_as_png(tmp_path):
    from scripts.render_visuals import _validate_native_raster_output

    disguised = tmp_path / "cover.png"
    disguised.write_text('<svg><text>后期补字</text></svg>', encoding="utf-8")

    with pytest.raises(RuntimeError, match="禁止把 SVG/HTML/Canvas"):
        _validate_native_raster_output(disguised)


def test_native_raster_guard_accepts_png_signature(tmp_path):
    from scripts.render_visuals import PNG_SIGNATURE, _validate_native_raster_output

    rendered = tmp_path / "cover.png"
    rendered.write_bytes(PNG_SIGNATURE + b"generated-pixels")

    _validate_native_raster_output(rendered)


def _article(root: Path) -> Path:
    prompts = root / "素材/prompts/final"
    prompts.mkdir(parents=True)
    tasks = [
        ("cover", "cover.md", "cover.png", "2.35:1"),
        ("hero", "hero.md", "hero.png", "1:1"),
        ("infographic-01", "infographic-01.md", "infographic-01.png", "9:16"),
    ]
    for task_id, prompt, _, _ in tasks:
        style = "montage-evidence" if task_id == "cover" else "claymation"
        profile = (
            ""
            if task_id == "cover"
            else 'visual_profile: "warm-light-clay"\nvisual_profile_sha256: "profile-sha"\n'
        )
        (prompts / prompt).write_text(
            f'---\nstyle: "{style}"\n{profile}---\nprompt={prompt}\n',
            encoding="utf-8",
        )
    (root / "素材/render-batch.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "producer": VISUAL_PRODUCER,
                "jobs": 2,
                "tasks": [
                    {
                        "id": task_id,
                        "promptFiles": [f"prompts/final/{prompt}"],
                        "image": image,
                        "ar": ar,
                        "producer_chain": [VISUAL_PRODUCER],
                        "method_sources": (
                            ["baoyu-article-illustrator"]
                            if task_id == "hero"
                            else ["baoyu-infographic"]
                            if task_id.startswith("infographic")
                            else []
                        ),
                    }
                    for task_id, prompt, image, ar in tasks
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "renderer-policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "renderers": [
                    {
                        "id": "primary",
                        "provider": "broken",
                        "model": "model-a",
                        "quality": "2k",
                        "imageSize": "1K",
                    },
                    {
                        "id": "fallback",
                        "provider": "working",
                        "model": "model-b",
                        "quality": "2k",
                        "imageSize": "1K",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def _fake_renderer(root: Path) -> list[str]:
    script = root / "fake_renderer.py"
    script.write_text(
        """
import json
import pathlib
import sys

args = sys.argv[1:]
if "--help" in args:
    print("--batchfile --jobs --json --promptfiles --image --provider --model --ar --quality --imageSize")
    raise SystemExit(0)
batch_path = pathlib.Path(args[args.index("--batchfile") + 1])
batch = json.loads(batch_path.read_text(encoding="utf-8"))
log_path = batch_path.parent / "fake-invocations.jsonl"
with log_path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(batch, ensure_ascii=False) + "\\n")
results = []
for task in batch["tasks"]:
    provider = task.get("provider")
    output = (batch_path.parent / task["image"]).resolve()
    success = provider != "broken"
    if success:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + task["id"].encode("utf-8"))
    results.append({
        "id": task["id"],
        "provider": provider,
        "model": task.get("model"),
        "outputPath": str(output),
        "success": success,
        "attempts": 1,
        "error": None if success else "simulated 503",
    })
print(json.dumps({
    "mode": "batch",
    "total": len(results),
    "succeeded": sum(1 for item in results if item["success"]),
    "failed": sum(1 for item in results if not item["success"]),
    "results": results,
}))
raise SystemExit(0 if all(item["success"] for item in results) else 1)
""".lstrip(),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def _install_fake_renderer(monkeypatch, root: Path) -> None:
    from scripts import render_visuals

    command = _fake_renderer(root)
    monkeypatch.setattr(
        render_visuals,
        "resolve_renderer_command",
        lambda: (command, "test-revision", []),
    )


def test_probe_requires_baoyu_batch_capabilities(tmp_path):
    from scripts.render_visuals import probe_renderer

    command = _fake_renderer(tmp_path)
    probe = probe_renderer(command)

    assert probe["ok"] is True
    assert probe["renderer"] == "baoyu-image-gen"
    assert "--batchfile" in probe["capabilities"]


def test_renderer_discovery_prefers_shared_skill_entry(tmp_path, monkeypatch):
    from scripts import render_visuals

    shared = tmp_path / ".codex/skills/baoyu-image-gen"
    (shared / "scripts").mkdir(parents=True)
    (shared / "scripts/main.ts").write_text("// shared renderer\n", encoding="utf-8")
    stale = (
        tmp_path
        / ".codex/plugins/cache/baoyu-skills/old/skills/baoyu-image-gen"
    )
    (stale / "scripts").mkdir(parents=True)
    (stale / "scripts/main.ts").write_text("// stale cache\n", encoding="utf-8")
    monkeypatch.setattr(render_visuals.Path, "home", lambda: tmp_path)

    candidates = render_visuals._candidate_renderer_dirs()

    assert candidates[0] == shared.resolve()
    assert stale.resolve() in candidates


def test_renderer_command_environment_override_cannot_bypass_baoyu(tmp_path, monkeypatch):
    from scripts import render_visuals

    baoyu = tmp_path / "baoyu-image-gen"
    (baoyu / "scripts").mkdir(parents=True)
    entrypoint = baoyu / "scripts/main.ts"
    entrypoint.write_text("// baoyu renderer\n", encoding="utf-8")
    monkeypatch.setenv("SANSHENG_WRITE_IMAGE_COMMAND", "malicious-renderer --accept-all")
    monkeypatch.setattr(render_visuals, "_candidate_renderer_dirs", lambda: [baoyu])
    monkeypatch.setattr(render_visuals.shutil, "which", lambda name: "bun.exe" if name == "bun" else None)

    command, _, errors = render_visuals.resolve_renderer_command()

    assert errors == []
    assert command == ["bun.exe", str(entrypoint)]


def test_fallback_keeps_canonical_prompt_and_aspect_unchanged(tmp_path, monkeypatch):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    _install_fake_renderer(monkeypatch, tmp_path)
    receipt, errors = render_visuals(article)

    assert errors == []
    assert receipt["status"] == "done"
    calls = [
        json.loads(line)
        for line in (article / "素材/fake-invocations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(calls) == 2
    first = {
        task["id"]: (task["promptFiles"], task["ar"]) for task in calls[0]["tasks"]
    }
    second = {
        task["id"]: (task["promptFiles"], task["ar"]) for task in calls[1]["tasks"]
    }
    assert first == second
    assert {task["provider"] for task in calls[0]["tasks"]} == {"broken"}
    assert {task["provider"] for task in calls[1]["tasks"]} == {"working"}


def test_render_log_records_truthful_producer_renderer_and_revision(tmp_path, monkeypatch):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    _install_fake_renderer(monkeypatch, tmp_path)
    _, errors = render_visuals(article)

    assert errors == []
    records = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3
    assert {record["producer"] for record in records} == {VISUAL_PRODUCER}
    assert {record["renderer"] for record in records} == {"baoyu-image-gen"}
    assert {record["provider"] for record in records} == {"working"}
    assert {record["model"] for record in records} == {"model-b"}
    assert {record["renderer_revision"] for record in records} == {"test-revision"}
    assert all(record["prompt_sha256"] and record["output_sha256"] for record in records)
    info_records = [record for record in records if record["stage"] == "infographic"]
    assert info_records[0]["style"] == "claymation"
    assert info_records[0]["visual_profile"] == "warm-light-clay"
    final_set = json.loads(
        (article / "素材/infographic/final-set.json").read_text(encoding="utf-8")
    )
    assert {image["style"] for image in final_set["images"]} == {"claymation"}


def test_no_configured_renderer_success_means_nonzero_contract(tmp_path, monkeypatch):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    policy = json.loads((article / "renderer-policy.json").read_text(encoding="utf-8"))
    policy["renderers"] = policy["renderers"][:1]
    (article / "renderer-policy.json").write_text(json.dumps(policy), encoding="utf-8")

    _install_fake_renderer(monkeypatch, tmp_path)
    receipt, errors = render_visuals(article)

    assert receipt is None
    assert any("simulated 503" in error for error in errors)
    assert not (article / "素材/render-receipt.json").exists()


def test_native_google_policy_is_rejected_before_any_render_call(tmp_path):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    (article / "renderer-policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "renderers": [
                    {
                        "id": "native-google",
                        "provider": "sansheng-google",
                        "model": "gemini-3.1-flash-image",
                        "quality": "1k",
                        "imageSize": "1K",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    receipt, errors = render_visuals(article)

    assert receipt is None
    assert any("绕过 baoyu-image-gen" in error and "不允许授权例外" in error for error in errors)


def test_candidates_require_explicit_selection_before_final_receipt(tmp_path, monkeypatch):
    from scripts.render_visuals import render_visuals, select_visual_candidates

    article = _article(tmp_path)
    _install_fake_renderer(monkeypatch, tmp_path)
    receipt, errors = render_visuals(
        article,
        candidate_count=2,
    )

    assert errors == []
    assert receipt["status"] == "selection-required"
    manifest_path = article / "素材/candidates/candidate-set.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "selection-required"
    assert all(len(options) == 2 for options in manifest["tasks"].values())

    final, selection_errors = select_visual_candidates(
        article,
        {task_id: 1 for task_id in manifest["tasks"]},
    )

    assert selection_errors == []
    assert final["status"] == "done"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "selected"
    assert (article / "素材/cover.png").is_file()


def test_incomplete_candidate_run_cannot_be_marked_selected(tmp_path, monkeypatch):
    from scripts.render_visuals import render_visuals, select_visual_candidates

    article = _article(tmp_path)
    _install_fake_renderer(monkeypatch, tmp_path)
    receipt, errors = render_visuals(
        article,
        candidate_count=2,
    )
    assert errors == []
    manifest_path = article / "素材/candidates/candidate-set.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requested_candidate_count"] = 3
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    final, selection_errors = select_visual_candidates(
        article,
        {task_id: 1 for task_id in manifest["tasks"]},
    )

    assert final is None
    assert any("候选生成不完整" in error for error in selection_errors)


def test_template_safe_policy_is_rejected_to_keep_text_model_native(tmp_path):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    (article / "renderer-policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "renderers": [
                    {
                        "id": "reviewed-template",
                        "provider": "sansheng-template-safe",
                        "model": "Pillow-reviewed-template",
                        "quality": "1k",
                        "imageSize": "1K",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    receipt, errors = render_visuals(article)

    assert receipt is None
    assert any("绕过 baoyu-image-gen" in error and "不允许授权例外" in error for error in errors)
