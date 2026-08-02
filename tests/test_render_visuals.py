import json
import sys
from pathlib import Path

VISUAL_PRODUCER = "sansheng-write.visual-planner"


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
                    # 显式 provider 会绕开 baoyu-image-gen，新契约要求写明理由
                    # （2026-08-02）：否则 _load_policy 直接拒绝该项。
                    {
                        "id": "primary",
                        "provider": "broken",
                        "model": "model-a",
                        "quality": "2k",
                        "imageSize": "1K",
                        "override_baoyu_reason": "test fixture: 验证降级链",
                    },
                    {
                        "id": "fallback",
                        "provider": "working",
                        "model": "model-b",
                        "quality": "2k",
                        "imageSize": "1K",
                        "override_baoyu_reason": "test fixture: 验证降级链",
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


def test_fallback_keeps_canonical_prompt_and_aspect_unchanged(tmp_path):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    receipt, errors = render_visuals(
        article,
        renderer_command=_fake_renderer(tmp_path),
        renderer_revision="test-revision",
    )

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


def test_render_log_records_truthful_producer_renderer_and_revision(tmp_path):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    _, errors = render_visuals(
        article,
        renderer_command=_fake_renderer(tmp_path),
        renderer_revision="test-revision",
    )

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


def test_no_configured_renderer_success_means_nonzero_contract(tmp_path):
    from scripts.render_visuals import render_visuals

    article = _article(tmp_path)
    policy = json.loads((article / "renderer-policy.json").read_text(encoding="utf-8"))
    policy["renderers"] = policy["renderers"][:1]
    (article / "renderer-policy.json").write_text(json.dumps(policy), encoding="utf-8")

    receipt, errors = render_visuals(
        article,
        renderer_command=_fake_renderer(tmp_path),
        renderer_revision="test-revision",
    )

    assert receipt is None
    assert any("simulated 503" in error for error in errors)
    assert not (article / "素材/render-receipt.json").exists()


def test_native_google_policy_bypasses_baoyu_and_records_actual_model(tmp_path):
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
                        "override_baoyu_reason": "test fixture: 专测绕过 Baoyu 的原生 Google 路径",
                        "model": "gemini-3.1-flash-image",
                        "quality": "1k",
                        "imageSize": "1K",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_native(cwd, tasks, renderer, jobs):
        results = []
        for task in tasks:
            output = cwd / "素材" / task["image"]
            output.write_bytes(b"\x89PNG\r\n\x1a\n" + task["id"].encode("utf-8"))
            results.append(
                {
                    "id": task["id"],
                    "provider": "google",
                    "model": "gemini-2.5-flash-image",
                    "renderer": "gen_img",
                    "outputPath": str(output),
                    "success": True,
                    "attempts": 1,
                    "error": None,
                }
            )
        return {"returncode": 0, "results": results}

    receipt, errors = render_visuals(
        article,
        native_google_renderer=fake_native,
        renderer_revision="native-test-revision",
    )

    assert errors == []
    assert receipt["status"] == "done"
    assert {asset["renderer"] for asset in receipt["assets"]} == {"gen_img"}
    assert {asset["provider"] for asset in receipt["assets"]} == {"google"}
    assert {asset["model"] for asset in receipt["assets"]} == {
        "gemini-2.5-flash-image"
    }


def test_partial_native_success_is_logged_for_resume(tmp_path):
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
                        "override_baoyu_reason": "test fixture: 专测绕过 Baoyu 的原生 Google 路径",
                        "model": "gemini-3.1-flash-image",
                        "quality": "1k",
                        "imageSize": "1K",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def partial_native(cwd, tasks, renderer, jobs):
        results = []
        for task in tasks:
            success = task["id"] != "hero"
            output = cwd / "素材" / task["image"]
            if success:
                output.write_bytes(b"\x89PNG\r\n\x1a\n" + task["id"].encode("utf-8"))
            results.append(
                {
                    "id": task["id"],
                    "provider": "google",
                    "model": renderer["model"],
                    "renderer": "gen_img",
                    "outputPath": str(output),
                    "success": success,
                    "attempts": 1,
                    "error": None if success else "simulated 429",
                }
            )
        return {"returncode": 1, "results": results}

    receipt, errors = render_visuals(
        article,
        native_google_renderer=partial_native,
        renderer_revision="native-test-revision",
    )

    assert receipt is None
    assert any("simulated 429" in error for error in errors)
    records = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {record["output"] for record in records} == {
        "素材/cover.png",
        "素材/infographic-01.png",
    }


def test_native_google_route_preflight_fails_before_any_render_call(tmp_path):
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
                        "override_baoyu_reason": "test fixture: 专测绕过 Baoyu 的原生 Google 路径",
                        "model": "gemini-3-pro-image",
                        "quality": "1k",
                        "imageSize": "1K",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    receipt, errors = render_visuals(
        article,
        native_google_renderer=lambda *args: calls.append(args),
        google_route_preflight=lambda _model: (_ for _ in ()).throw(
            SystemExit("缺 publishers/google")
        ),
    )

    assert receipt is None
    assert calls == []
    assert any("端点预检失败" in error and "publishers/google" in error for error in errors)


def test_candidates_require_explicit_selection_before_final_receipt(tmp_path):
    from scripts.render_visuals import render_visuals, select_visual_candidates

    article = _article(tmp_path)
    receipt, errors = render_visuals(
        article,
        renderer_command=_fake_renderer(tmp_path),
        renderer_revision="test-revision",
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


def test_incomplete_candidate_run_cannot_be_marked_selected(tmp_path):
    from scripts.render_visuals import render_visuals, select_visual_candidates

    article = _article(tmp_path)
    receipt, errors = render_visuals(
        article,
        renderer_command=_fake_renderer(tmp_path),
        renderer_revision="test-revision",
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
    assert any("本地模板绘制图中文字" in error for error in errors)
