import json
from pathlib import Path

from PIL import Image

from scripts import pipeline


def _png(path: Path, w: int, h: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (245, 240, 230)).save(path)


def _minimal_visual_article(tmp_path: Path, *, subject="ai-product", style="claymation") -> Path:
    (tmp_path / "素材" / "infographic").mkdir(parents=True)
    (tmp_path / "素材" / "prompts").mkdir(parents=True)
    (tmp_path / "article-meta.yaml").write_text(
        f'infographic_subject: "{subject}"\ninfographic_style: "{style}"\n',
        encoding="utf-8",
    )
    (tmp_path / "素材" / "infographic" / "analysis.md").write_text(
        f"route: {subject}\nstyle: {style}\n", encoding="utf-8"
    )
    (tmp_path / "素材" / "infographic" / "structured-content.md").write_text(
        f"style: {style}\n", encoding="utf-8"
    )
    specs = [
        ("infographic-01.png", 576, 1024, "01.md"),
        ("infographic-02.png", 1024, 576, "02.md"),
        ("infographic-03.png", 1024, 576, "03.md"),
        ("infographic-04.png", 576, 1024, "04.md"),
    ]
    images = []
    logs = []
    for name, w, h, prompt_name in specs:
        rel = f"素材/{name}"
        _png(tmp_path / rel, w, h)
        (tmp_path / "素材" / "prompts" / prompt_name).write_text(
            f"---\nstyle: {style}\n---\n", encoding="utf-8"
        )
        images.append({"path": rel, "aspect": "9:16" if h > w else "16:9", "bytes": (tmp_path / rel).stat().st_size, "style": style})
        logs.append({
            "stage": "infographic",
            "tool": "baoyu-infographic",
            "output": rel,
            "cmd": f"baoyu-infographic --style {style} 素材/prompts/{prompt_name}",
        })
    (tmp_path / "素材" / "infographic" / "final-set.json").write_text(
        json.dumps({"images": images}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / ".gen-log.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in logs) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_ai_product_subject_requires_claymation(tmp_path):
    article = _minimal_visual_article(tmp_path, subject="ai-product", style="morandi-journal")
    errors = pipeline._visual_route_errors(article)
    assert any("ai-product" in e and "claymation" in e for e in errors), errors


def test_final_assets_must_match_meta_latest_log_and_prompt(tmp_path):
    article = _minimal_visual_article(tmp_path)
    log_path = article / ".gen-log.jsonl"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "stage": "infographic",
            "tool": "baoyu-infographic",
            "output": "素材/infographic-03.png",
            "cmd": "baoyu-infographic --style morandi-journal 素材/prompts/03.md",
        }, ensure_ascii=False) + "\n")
    errors = pipeline._visual_route_errors(article)
    assert any("infographic-03.png" in e and "claymation" in e for e in errors), errors


def test_visual_route_compliant_bundle_passes(tmp_path):
    article = _minimal_visual_article(tmp_path)
    assert pipeline._visual_route_errors(article) == []


def test_publish_preflight_requires_visual_qa_record(tmp_path):
    article = _minimal_visual_article(tmp_path)
    _png(article / "素材" / "cover.png", 1024, 436)
    _png(article / "素材" / "hero.png", 1024, 1024)
    (article / "定稿.md").write_text("正文", encoding="utf-8")
    (article / "定稿.html").write_text("<html><body>正文</body></html>", encoding="utf-8")
    errors = pipeline._pre_publish_errors(article)
    assert any("_visual-qa.md" in e for e in errors), errors


def test_visual_qa_record_must_cover_cover_and_infographic_checks(tmp_path):
    article = _minimal_visual_article(tmp_path)
    (article / "_visual-qa.md").write_text("# 视觉验收记录\n通过\n", encoding="utf-8")
    errors = pipeline._visual_qa_errors(article)
    assert any("封面" in e for e in errors), errors
    assert any("信息图" in e for e in errors), errors


def test_reference_declares_product_axis_precedence_and_refined_cover_cap():
    root = Path(__file__).resolve().parents[1]
    routing = (root / "references" / "image-routing.md").read_text(encoding="utf-8")
    cover = (root / "references" / "cover-styles.md").read_text(encoding="utf-8")
    assert "产品/模型轴优先于趋势结论" in routing
    assert "标题块总高度上限" in cover
    assert "禁止把 `largest` / `extra-black`" in cover
