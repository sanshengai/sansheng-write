import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

from scripts.evidence import seal_visual_receipt


PRODUCER = "sansheng-write.visual-planner"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _article(root: Path) -> Path:
    (root / "素材/prompts/final").mkdir(parents=True)
    (root / "article-meta.yaml").write_text(
        'title: "视觉合同"\n'
        'lead:\n'
        '  line1: "规则不能丢"\n'
        '  line2: "弱模型也能稳"\n'
        '  subtitle: "视觉发布合同"\n'
        '  tag1: "硬门"\n'
        '  tag2: "证据链"\n'
        'cover_keywords: "规则 合同 BIRTH CARE CITY"\n'
        'cover_style: "montage-evidence"\n'
        'infographic_subject: "ai-product"\n'
        'infographic_style: "claymation"\n'
        'visual_profile: "warm-light-clay"\n',
        encoding="utf-8",
    )
    plan = {
        "schema_version": 1,
        "cover": {
            "title": "视觉合同",
            "subtitle": "发布不能靠猜",
            "visual_facts": ["证据链"],
        },
        "hero": {"title": "视觉合同", "visual_facts": ["独立复核"]},
        "infographics": [
            {
                "id": f"{index:02d}",
                "position": "opening" if index == 1 else "closing" if index == 4 else "middle",
                "aspect_ratio": "9:16" if index in (1, 4) else "16:9",
                "title": f"步骤 {index}",
                "layout": "flow",
                "expected_text": [f"步骤 {index}", f"证据 {index}"],
                "facts": [f"事实 {index}"],
            }
            for index in range(1, 5)
        ],
    }
    (root / "visual-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )
    specs = [
        ("cover", "cover.png", (1200, 510), ["视觉合同", "发布不能靠猜"]),
        ("hero", "hero.png", (1024, 1024), ["视觉合同"]),
        ("infographic", "infographic-01.png", (576, 1024), ["步骤 1", "证据 1"]),
        ("infographic", "infographic-02.png", (1024, 576), ["步骤 2", "证据 2"]),
        ("infographic", "infographic-03.png", (1024, 576), ["步骤 3", "证据 3"]),
        ("infographic", "infographic-04.png", (576, 1024), ["步骤 4", "证据 4"]),
    ]
    logs = []
    for index, (stage, name, size, _) in enumerate(specs):
        output = root / "素材" / name
        Image.new("RGB", size, (242, 236, 224)).save(output)
        prompt = root / "素材/prompts/final" / f"{Path(name).stem}.md"
        prompt.write_text(
            "---\nstyle: claymation\n---\ncanonical prompt\n", encoding="utf-8"
        )
        logs.append(
            {
                "schema_version": 3,
                "record_id": f"rec-{index}",
                "stage": stage,
                "producer": PRODUCER,
                "tool": PRODUCER,
                "renderer": "baoyu-image-gen",
                "renderer_revision": "rev-1",
                "provider": "google",
                "model": "generation-model",
                "output": f"素材/{name}",
                "output_sha256": _sha(output),
                "prompt": f"素材/prompts/final/{Path(name).stem}.md",
                "prompt_sha256": _sha(prompt),
            }
        )
    (root / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in logs) + "\n",
        encoding="utf-8",
    )
    return root


def _reviewer(
    root: Path,
    *,
    model: str = "review-model",
    omit_text: bool = False,
    split_first: bool = False,
    omit_style_contract: bool = False,
) -> list[str]:
    script = root / (
        f"reviewer-{model}-{omit_text}-{split_first}-{omit_style_contract}.py"
    )
    script.write_text(
        f"""
import hashlib
import json
import pathlib
import sys

args = sys.argv[1:]
request_path = pathlib.Path(args[args.index("--request") + 1])
output_path = pathlib.Path(args[args.index("--output") + 1])
request = json.loads(request_path.read_text(encoding="utf-8"))
assets = []
for asset in request["assets"]:
    observed = list(asset["expected_text"])
    if {str(omit_text)} and observed:
        observed = observed[:-1]
    if {str(split_first)} and asset["path"] == "素材/cover.png" and observed:
        first = observed.pop(0)
        observed = [first[:2], first[2:], *observed]
    required_checks = list(asset.get("required_checks") or request["contract"]["required_checks"])
    checks = {{name: True for name in required_checks}}
    if {str(omit_style_contract)}:
        checks.pop("style_contract_match", None)
    assets.append({{
        "path": asset["path"],
        "sha256": asset["sha256"],
        "observed_text": observed,
        "checks": checks,
        "notes": ""
    }})
payload = {{
    "schema_version": 1,
    "status": "pass",
    "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
    "reviewer": {{
        "role": "independent-visual-reviewer",
        "model": "{model}",
        "run_id": "fresh-run-001",
        "independent": True
    }},
    "assets": assets
}}
output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
""".lstrip(),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def test_external_visual_reviewer_writes_structured_source_and_derived_markdown(tmp_path):
    from scripts.visual_qa import build_qa_request, run_visual_qa

    article = _article(tmp_path)
    request, request_errors = build_qa_request(article)
    assert request_errors == []
    cover = next(asset for asset in request["assets"] if asset["stage"] == "cover")
    info = next(asset for asset in request["assets"] if asset["stage"] == "infographic")
    assert cover["target_style"] == "montage-evidence"
    assert "BIRTH × CARE × CITY" in cover["expected_text"]
    assert cover["style_contract"]["layout"] == "left-50-gap-6-right-44"
    assert "style_contract_match" in cover["required_checks"]
    assert "composition_contract_match" in cover["required_checks"]
    assert info["target_style"] == "claymation"
    assert info["style_contract"]["visual_profile"] == "warm-light-clay"
    assert "style_contract_match" in info["required_checks"]
    qa, errors = run_visual_qa(article, reviewer_command=_reviewer(tmp_path))

    assert errors == []
    assert qa["status"] == "pass"
    assert qa["reviewer"]["independent"] is True
    assert (article / "_visual-qa.json").is_file()
    markdown = (article / "_visual-qa.md").read_text(encoding="utf-8")
    assert "此文件由 _visual-qa.json 派生" in markdown
    assert "✅" in markdown


def test_qa_rejects_reviewer_that_does_not_confirm_target_style(tmp_path):
    from scripts.visual_qa import run_visual_qa

    article = _article(tmp_path)
    qa, errors = run_visual_qa(
        article,
        reviewer_command=_reviewer(tmp_path, omit_style_contract=True),
    )

    assert qa is None
    assert any("style_contract_match" in error for error in errors)


def test_qa_rejects_checked_box_markdown_without_structured_result(tmp_path):
    article = _article(tmp_path)
    (article / "_visual-qa.md").write_text(
        "- [x] 我看过了\n结论：通过\n", encoding="utf-8"
    )

    receipt, errors = seal_visual_receipt(article)

    assert receipt is None
    assert any("_visual-qa.json" in error for error in errors)


def test_qa_rejects_missing_expected_ocr_text_even_if_model_says_pass(tmp_path):
    from scripts.visual_qa import run_visual_qa

    article = _article(tmp_path)
    qa, errors = run_visual_qa(
        article, reviewer_command=_reviewer(tmp_path, omit_text=True)
    )

    assert qa is None
    assert any("expected_text" in error for error in errors)
    assert not (article / "_visual-qa.json").exists()


def test_qa_accepts_one_expected_line_split_into_adjacent_observed_fragments(tmp_path):
    from scripts.visual_qa import run_visual_qa

    article = _article(tmp_path)
    qa, errors = run_visual_qa(
        article, reviewer_command=_reviewer(tmp_path, split_first=True)
    )

    assert errors == []
    assert qa["status"] == "pass"


def test_qa_reviewer_must_be_independent_from_generation_model(tmp_path):
    from scripts.visual_qa import run_visual_qa

    article = _article(tmp_path)
    qa, errors = run_visual_qa(
        article, reviewer_command=_reviewer(tmp_path, model="generation-model")
    )

    assert qa is None
    assert any("独立" in error for error in errors)


def test_visual_seal_binds_structured_qa_and_exact_final_image_bytes(tmp_path):
    from scripts.visual_qa import run_visual_qa

    article = _article(tmp_path)
    assert run_visual_qa(article, reviewer_command=_reviewer(tmp_path))[1] == []
    receipt, errors = seal_visual_receipt(article)
    assert errors == []
    assert receipt["qa_path"] == "_visual-qa.json"

    Image.new("RGB", (1200, 510), (10, 20, 30)).save(article / "素材/cover.png")
    receipt, errors = seal_visual_receipt(article)
    assert receipt is None
    assert any("sha256" in error or "字节" in error for error in errors)
