import json
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from scripts import pipeline
from scripts.baoyu_contract import build_anchors
from scripts.evidence import (
    seal_visual_receipt,
    stable_digest,
    sha256_file,
    verify_publish_receipt,
    verify_publish_ready,
    verify_visual_receipt,
    write_publish_receipt,
    write_publish_ready,
)


def _png(path: Path, size=(1200, 675), color=(220, 210, 190)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _visual_bundle(root: Path) -> Path:
    (root / "素材/prompts/final").mkdir(parents=True)
    (root / "article-meta.yaml").write_text(
        "title: 视觉合同\n"
        "cover_style: montage-evidence\n"
        "lead:\n"
        "  line1: 规则不能丢\n"
        "  line2: 弱模型也能稳\n"
        "  accent: 也能稳\n"
        "  subtitle: 文章导读\n"
        "  tag1: 硬门\n"
        "  tag2: 证据链\n"
        "infographic_subject: ai-product\ninfographic_style: claymation\n",
        encoding="utf-8",
    )
    specs = [("cover", "cover.png", (1200, 510))]
    specs += [
        ("infographic", "infographic-01.png", (576, 1024)),
        ("infographic", "infographic-02.png", (1024, 576)),
        ("infographic", "infographic-03.png", (1024, 576)),
        ("infographic", "infographic-04.png", (576, 1024)),
    ]
    specs += [("hero", "hero.png", (1024, 1024))]
    logs = []
    for i, (stage, name, size) in enumerate(specs):
        output = root / "素材" / name
        prompt = root / "素材/prompts/final" / f"{stage}-{i}.md"
        _png(output, size=size)
        prompt.write_text(
            "---\nstyle: claymation\n---\n精致、克制、清晰。\n", encoding="utf-8"
        )
        producer = "sansheng-write.visual-planner"
        logs.append({
            "schema_version": 3,
            "record_id": f"rec-{i}",
            "stage": stage,
            "producer": producer,
            "producer_chain": [producer],
            "method_sources": (
                ["baoyu-article-illustrator"]
                if stage == "hero"
                else ["baoyu-infographic"]
                if stage == "infographic"
                else []
            ),
            "tool": producer,
            "renderer": "baoyu-image-gen",
            "model": "test-model",
            "output": f"素材/{name}",
            "output_sha256": sha256_file(output),
            "prompt": f"素材/prompts/final/{stage}-{i}.md",
            "prompt_sha256": sha256_file(prompt),
            "cmd": f"{producer} --style claymation 素材/prompts/final/{stage}-{i}.md",
        })
    (root / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in logs) + "\n",
        encoding="utf-8",
    )
    (root / "visual-plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cover": {
                    "title": "测试封面",
                    "subtitle": "测试副标题",
                    "visual_facts": ["事实"],
                },
                "hero": {"title": "测试 Hero", "visual_facts": ["事实"]},
                "infographics": [
                    {
                        "id": f"{index:02d}",
                        "expected_text": [f"图 {index}"],
                    }
                    for index in range(1, 5)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "定稿.md").write_text(
        "\n".join(
            f"![图](素材/infographic-{index:02d}.png)" for index in range(1, 5)
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "定稿.html").write_text(
        '<img src="素材/hero.png">\n',
        encoding="utf-8",
    )
    scripts_dir = Path(__file__).parents[1] / "scripts"
    # Baoyu 依赖锚点：正式流程由 compile-visuals 写入 render-batch.json，
    # 发布期重新解析磁盘上的 Baoyu 文档比对。测试里用 conftest 注入的 fixture 生成。
    (root / "素材/render-batch.json").write_text(
        json.dumps(
            {"schema_version": 1, **build_anchors(), "tasks": []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "素材/visual-compile-receipt.json").write_text(
        json.dumps(
            {
                "plan_digest": stable_digest(
                    json.loads((root / "visual-plan.json").read_text(encoding="utf-8"))
                ),
                "validator_hashes": {
                    "visual_qa.py": sha256_file(scripts_dir / "visual_qa.py"),
                    "visual_qa_codex.py": sha256_file(
                        scripts_dir / "visual_qa_codex.py"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    from scripts.visual_qa import build_qa_request

    request, errors = build_qa_request(root)
    assert errors == []
    request_path = root / "_visual-qa-request.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    qa = {
        "schema_version": 1,
        "status": "pass",
        "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        "reviewer": {
            "role": "independent-visual-reviewer",
            "model": "review-model",
            "run_id": "fixture-run",
            "independent": True,
        },
        "assets": [
            {
                "path": asset["path"],
                "sha256": asset["sha256"],
                "observed_text": asset["expected_text"],
                "checks": {
                    name: True
                    for name in asset.get("required_checks")
                    or request["contract"]["required_checks"]
                },
                "notes": "",
            }
            for asset in request["assets"]
        ],
    }
    (root / "_visual-qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "_visual-qa.md").write_text(
        "# 视觉验收\n\n> 此文件由 _visual-qa.json 派生\n", encoding="utf-8"
    )
    return root


def test_visual_receipt_binds_final_bytes(tmp_path):
    article = _visual_bundle(tmp_path)
    receipt, errors = seal_visual_receipt(article)
    assert receipt and errors == []
    _png(article / "素材/cover.png", size=(1200, 510), color=(10, 20, 30))
    _, errors = verify_visual_receipt(article)
    assert any("旧 visual receipt 失效" in e for e in errors), errors


def test_visual_receipt_binds_visual_profile_trace(tmp_path):
    article = _visual_bundle(tmp_path)
    recipe = pipeline._visual_recipe("warm-light-clay")
    meta = article / "article-meta.yaml"
    meta.write_text(
        meta.read_text(encoding="utf-8") + "visual_profile: warm-light-clay\n",
        encoding="utf-8",
    )
    records = [
        json.loads(line)
        for line in (article / ".gen-log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for record in records:
        record["visual_profile"] = "warm-light-clay"
        record["visual_profile_sha256"] = recipe["sha256"]
        record["host_agent"] = "codex"
        record["orchestrator_skill"] = "sansheng-write"
        record["extend_sha256"] = "abc123"
    (article / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n",
        encoding="utf-8",
    )

    receipt, errors = seal_visual_receipt(article)

    assert receipt and errors == []
    assert receipt["manifest"]["meta"]["visual_profile"] == "warm-light-clay"
    assert receipt["manifest"]["assets"][1]["visual_profile_sha256"] == recipe["sha256"]
    assert receipt["manifest"]["assets"][1]["host_agent"] == "codex"
    assert receipt["manifest"]["assets"][1]["extend_sha256"] == "abc123"


def test_visual_receipt_includes_hero_when_present(tmp_path):
    article = _visual_bundle(tmp_path)
    hero = article / "素材/hero.png"
    prompt = article / "素材/prompts/final/hero.md"
    _png(hero, size=(1024, 1024))
    prompt.write_text("---\nstyle: claymation\n---\n浅色 Hero\n", encoding="utf-8")
    with (article / ".gen-log.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "schema_version": 3,
            "record_id": "rec-hero",
                "stage": "hero",
                "producer": "sansheng-write.visual-planner",
                "producer_chain": ["sansheng-write.visual-planner"],
                "method_sources": ["baoyu-article-illustrator"],
                "tool": "sansheng-write.visual-planner",
            "renderer": "baoyu-image-gen",
            "model": "test-model",
            "output": "素材/hero.png",
            "output_sha256": sha256_file(hero),
            "prompt": "素材/prompts/final/hero.md",
            "prompt_sha256": sha256_file(prompt),
            "cmd": "gen_img 素材/prompts/final/hero.md 素材/hero.png",
        }, ensure_ascii=False) + "\n")

    receipt, errors = seal_visual_receipt(article)

    assert receipt and errors == []
    assert any(asset["path"] == "素材/hero.png" for asset in receipt["manifest"]["assets"])


def test_publish_receipt_binds_html_hero_and_visuals(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>v1</html>", encoding="utf-8")
    assert write_publish_ready(article)[1] == []
    assert write_publish_receipt(article, "draft-1")[1] == []
    (article / "定稿.html").write_text("<html>v2</html>", encoding="utf-8")
    _, errors = verify_publish_receipt(article, "draft-1")
    assert any("必须重推" in e for e in errors), errors


def test_publish_ready_is_preflight_and_invalidates_on_local_change(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>v1</html>", encoding="utf-8")
    assert write_publish_ready(article)[1] == []
    (article / "定稿.html").write_text("<html>changed</html>", encoding="utf-8")
    _, errors = verify_publish_ready(article)
    assert any("publish-ready 后" in e for e in errors), errors


def test_publish_done_force_cannot_bypass_inline_gate(tmp_path):
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    pipeline.save_state(tmp_path, state)
    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_done(
            "publish", tmp_path, ["draft_media_id=draft-unsafe"], force=True
        )
    assert exc.value.code == 2
    saved = pipeline.load_state(tmp_path)
    assert saved["stages"]["publish"]["status"] == "pending"
    assert "draft_media_id" not in saved["stages"]["publish"]
    assert not (tmp_path / "_publish-receipt.json").exists()


def test_manual_draft_id_cannot_replace_existing_receipt_or_state(tmp_path, monkeypatch):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    _png(article / "素材/hero.png", size=(1024, 1024))
    (article / "定稿.html").write_text("<html>ready</html>", encoding="utf-8")
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "run_id": "run-fixture",
        "stages": {stage: {"status": "done"} for stage in pipeline.STAGE_ORDER},
    }
    state["stages"]["publish"]["draft_media_id"] = "trusted-id"
    pipeline.save_state(article, state)
    assert write_publish_ready(article)[1] == []
    receipt_path = article / pipeline.PUBLISH_RECEIPT_FILE
    receipt_path.write_text('{"draft_media_id":"trusted-id"}\n', encoding="utf-8")
    before_receipt = receipt_path.read_bytes()
    before_state = (article / pipeline.STATE_FILE).read_bytes()
    monkeypatch.setattr(
        pipeline, "verify_stage", lambda *args, **kwargs: (False, ["forced failure"])
    )

    with pytest.raises(SystemExit) as exc:
        pipeline.cmd_done("publish", article, ["draft_media_id=new-id"], force=True)
    assert exc.value.code == 2
    assert receipt_path.read_bytes() == before_receipt
    assert (article / pipeline.STATE_FILE).read_bytes() == before_state
    saved = pipeline.load_state(article)
    assert saved["stages"]["publish"]["draft_media_id"] == "trusted-id"


def test_status_detects_prompt_and_qa_drift(tmp_path):
    article = _visual_bundle(tmp_path)
    assert seal_visual_receipt(article)[1] == []
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "run_id": "run-fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    for stage in ("cover", "infographic", "logo", "publish"):
        state["stages"][stage] = {
            "status": "done",
            "artifact_digest": pipeline._stage_artifact_digest(article, stage),
        }
    pipeline.save_state(article, state)
    prompt = article / "素材/prompts/final/cover-0.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    pipeline.cmd_status(article)
    saved = pipeline.load_state(article)
    assert saved["stages"]["cover"]["status"] == "dirty"
    assert saved["stages"]["logo"]["status"] == "dirty"
    assert saved["stages"]["publish"]["status"] == "dirty"

    # 重建干净摘要后只改 QA，logo 与 publish 也必须自动失效。
    for stage in ("cover", "infographic", "logo", "publish"):
        state["stages"][stage] = {
            "status": "done",
            "artifact_digest": pipeline._stage_artifact_digest(article, stage),
        }
    pipeline.save_state(article, state)
    qa = article / "_visual-qa.json"
    payload = json.loads(qa.read_text(encoding="utf-8"))
    payload["reviewer"]["run_id"] = "changed-run"
    qa.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pipeline.cmd_status(article)
    saved = pipeline.load_state(article)
    assert saved["stages"]["logo"]["status"] == "dirty"
    assert saved["stages"]["publish"]["status"] == "dirty"


def test_stage_timestamps_preserved_and_downstream_invalidated(tmp_path, monkeypatch):
    times = iter(["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"])
    monkeypatch.setattr(pipeline, "_now_iso", lambda: next(times))
    (tmp_path / "定稿.html").write_text("v1", encoding="utf-8")
    state = {
        "schema_version": 2,
        "topic_id": "fixture",
        "stages": {stage: {"status": "pending"} for stage in pipeline.STAGE_ORDER},
    }
    for upstream in pipeline.STAGE_ORDER[:pipeline.STAGE_ORDER.index("layout")]:
        state["stages"][upstream]["status"] = "done"
    state["stages"]["logo"]["status"] = "done"
    state["stages"]["publish"]["status"] = "done"
    pipeline._record_stage_success(tmp_path, state, "layout")
    first = state["stages"]["layout"]["first_completed_at"]
    (tmp_path / "定稿.html").write_text("v2", encoding="utf-8")
    pipeline._record_stage_success(tmp_path, state, "layout")
    assert state["stages"]["layout"]["first_completed_at"] == first
    assert state["stages"]["layout"]["last_verified_at"] != first
    assert state["stages"]["logo"]["status"] == "dirty"
    assert state["stages"]["publish"]["status"] == "dirty"
