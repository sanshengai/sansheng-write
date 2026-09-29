"""Explicit, non-publishing Stylebook bridge for an existing article draft.

This preview never replaces visual-plan.json, render-batch.json, or release receipts.
It verifies the article binding and preserves the actual Stylebook prompt and method files
so the later renderer/QA migration has a reviewable input.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_root(explicit: str | None) -> Path:
    if explicit:
        roots = [Path(explicit).expanduser()]
    else:
        roots = [Path.home() / ".agents/skills/sansheng-stylebook",
                 Path.home() / ".codex/skills/sansheng-stylebook"]
    for root in roots:
        root = root.resolve()
        if (root / "SKILL.md").is_file() and (root / "scripts/stylebook/plan.py").is_file():
            return root
    raise ValueError("找不到画风手册本体；用 --stylebook-root 指定已安装的 sansheng-stylebook")


def _method_anchor(root: Path, styles: set[str]) -> dict:
    paths = ["SKILL.md", "references/planning.md", "scripts/stylebook/plan.py",
             "scripts/stylebook/compile.py", "scripts/stylebook/contract.py",
             "scenes/scenes.json", "formats/formats.json"]
    paths.extend(f"styles/{code}/contract.json" for code in sorted(styles))
    hashes = {rel: _sha(root / rel) for rel in paths}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"name": "sansheng-stylebook", "root": str(root), "files": hashes, "digest": digest}


def compile_preview(article_dir: Path, plan_path: Path, *, stylebook_root: str | None = None) -> tuple[dict | None, list[str]]:
    article_dir = Path(article_dir).resolve()
    plan_path = Path(plan_path).resolve()
    article = article_dir / "定稿.md"
    if not article.is_file() or not plan_path.is_file():
        return None, ["需要文章目录中的 定稿.md 和显式指定的画风手册计划文件"]
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        root = _skill_root(stylebook_root)
        source = Path(plan["source"]["path"])
        source = (plan_path.parent / source).resolve() if not source.is_absolute() else source.resolve()
        if source != article:
            return None, ["画风手册计划 source.path 必须指向当前文章的 定稿.md"]
        if plan.get("version") != 3 or plan.get("scene") != "wxillus":
            return None, ["写作预览只接受 v3 公众号文章配图计划"]
        if plan["source"]["sha256"] != _sha(article):
            return None, ["定稿.md 已变化，画风手册计划的原文 SHA-256 失效"]
        scripts = str(root / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        module = importlib.import_module("stylebook.plan")
        compiler = importlib.import_module("stylebook.compile")
        if not Path(module.__file__).resolve().is_relative_to(root):
            return None, ["加载到的画风手册模块与指定本体不一致"]
        errors, warnings = module.check(plan, base_path=plan_path.parent)
        if errors:
            return None, errors
        manifests = module.manifests(plan)
        compiled = []
        for manifest in manifests:
            image_id = manifest.pop("_id")
            result = compiler.compile_manifest(manifest)
            compiled.append({"id": image_id, "manifest": manifest, "compiled": result.to_dict()})
        styles = {str(plan["style"]["code"]).split("@")[0]}
        styles.update(str(item["style"]).split("@")[0] for item in plan["items"] if item.get("style"))
        anchor = _method_anchor(root, styles)
        receipt = {"schema_version": 1, "status": "preview_only", "producer": "sansheng-stylebook.plan",
                   "renderer": None, "plan_review": "not_run", "article_sha256": _sha(article),
                   "plan_sha256": _sha(plan_path), "method_source": anchor,
                   "warnings": warnings, "new_image_count": len(compiled), "images": compiled}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return None, [f"画风手册预编译失败：{exc}"]

    out_dir = article_dir / "素材"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"stylebook-preview-{receipt['plan_sha256'][:12]}.json"
    payload = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if dest.exists() and dest.read_text(encoding="utf-8") != payload:
        return None, [f"同一计划的预编译证据已存在但内容不同：{dest}；保留旧件并检查本体是否变化"]
    if not dest.exists():
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, dest)
    receipt["path"] = str(dest)
    return receipt, []
