"""Media-only equivalence must not invalidate good audio or hide real input drift."""
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import distribute
import podcast_episode as pe
from assemble_release import strip_machine_assembly
from podcast_source import LEGACY_REPRESENTATION, normalized_source


@pytest.fixture
def article(tmp_path, monkeypatch):
    root = tmp_path / "article"
    root.mkdir()
    (root / "定稿.md").write_text('# 标题\n\n正文需要保留。\n\n![示例图](old.webp "图片说明")\n')
    (root / ".state.json").write_text(json.dumps({"stages": {"writing": {"title_final": "标题"}}}))
    image = Image.new("RGBA", (8, 8), (20, 80, 160, 255))
    image.save(root / "old.webp", lossless=True)
    image.save(root / "new.png")
    prompt = root / "focus.md"
    prompt.write_text("基于正文讨论，不增加新事实")
    config = {"enabled": True, "focus_prompt": str(prompt), "language": "zh", "length": "default"}
    monkeypatch.setattr(pe, "cfg", lambda: config)
    output = distribute.channel_dir(root, "podcast")
    output.mkdir(parents=True)
    (output / "audio.mp3").write_bytes(b"existing-audio")
    (output / "audio.json").write_text('{"description":"原节目"}')
    return root, config


def seal(article, *, legacy=False, snapshot=True):
    root, config = article
    mp3 = distribute.channel_dir(root, "podcast") / "audio.mp3"
    original = (root / "定稿.md").read_text()
    source = strip_machine_assembly(original) if legacy else normalized_source(root, original)
    source_sha = distribute._digest(source)
    kwargs = {"source_representation": LEGACY_REPRESENTATION} if legacy else {}
    gen_sha = pe.generation_digest(root, config, source_override=source_sha, **kwargs)
    distribute.set_status(root, "podcast", "drafted", source_digest=source_sha,
                          generation_digest=gen_sha, audio_sha256=hashlib.sha256(mp3.read_bytes()).hexdigest())
    if legacy:
        manifest = {"schema_version": 1, "source_digest": source_sha, "generation_digest": gen_sha,
                    "audio_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(), "bytes": mp3.stat().st_size,
                    "duration_seconds": 123, "codec_name": "mp3"}
        pe._audio_manifest_path(mp3).write_text(json.dumps(manifest))
        if snapshot:
            folder = root / "素材/stylebook-sources"
            folder.mkdir(parents=True)
            (folder / (hashlib.sha256(original.encode()).hexdigest() + ".md")).write_text(original)
    else:
        pe._write_audio_manifest(root, mp3, config, {"duration_seconds": 123, "codec_name": "mp3"})
    return mp3


def convert_reference(root):
    draft = root / "定稿.md"
    draft.write_text(draft.read_text().replace("old.webp", "new.png"))


@pytest.mark.parametrize("legacy", [False, True])
def test_lossless_conversion_reuses_audio_and_preserves_original_receipt(article, monkeypatch, legacy):
    root, config = article
    mp3 = seal(article, legacy=legacy)
    receipt = pe._audio_manifest_path(mp3).read_bytes()
    before = distribute.read_state(root)["channels"]["podcast"]
    convert_reference(root)
    monkeypatch.setattr(pe, "run_nlm", lambda *a, **k: pytest.fail("must not generate"))
    assert pe.generation_is_fresh(root, config)
    assert pe.cmd_generate(root) == 0
    assert pe._audio_manifest_path(mp3).read_bytes() == receipt
    assert distribute.read_state(root)["channels"]["podcast"]["generation_digest"] == before["generation_digest"]


def test_legacy_exact_source_remains_compatible_but_equivalence_needs_snapshot(article):
    root, config = article
    seal(article, legacy=True, snapshot=False)
    assert pe.generation_is_fresh(root, config)
    convert_reference(root)
    assert not pe.generation_is_fresh(root, config)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("change", ["prose", "caption", "image_title", "prompt", "image", "audio", "length"])
def test_real_input_changes_reject_reuse(article, legacy, change):
    root, config = article
    mp3 = seal(article, legacy=legacy)
    convert_reference(root)
    draft = root / "定稿.md"
    if change == "prose":
        draft.write_text(draft.read_text().replace("正文需要保留", "完全不同的结论"))
    elif change == "caption":
        draft.write_text(draft.read_text().replace("示例图", "另一种含义"))
    elif change == "image_title":
        draft.write_text(draft.read_text().replace("图片说明", "新的图片说明"))
    elif change == "prompt":
        Path(config["focus_prompt"]).write_text("全新主持方向")
    elif change == "image":
        Image.new("RGB", (8, 8), "red").save(root / "new.png")
    elif change == "audio":
        mp3.write_bytes(b"changed audio")
    else:
        config["length"] = "long"
    assert not pe.generation_is_fresh(root, config)


def test_old_snapshot_or_referenced_image_missing_rejects_equivalence(article):
    root, config = article
    seal(article, legacy=True)
    convert_reference(root)
    (root / "old.webp").unlink()
    assert not pe.generation_is_fresh(root, config)


def test_new_manifest_requires_untampered_snapshot(article):
    root, config = article
    mp3 = seal(article)
    manifest = json.loads(pe._audio_manifest_path(mp3).read_text())
    snapshot = root / manifest["source_snapshot"]
    snapshot.write_text("forged")
    assert not pe.generation_is_fresh(root, config)
    snapshot.unlink()
    assert not pe.generation_is_fresh(root, config)


def test_source_normalization_preserves_code_remote_links_and_prose(article):
    root, _ = article
    original = '正文 old.webp。\n```md\n![图](old.webp)\n```\n![图](https://example.com/old.webp)\n'
    assert normalized_source(root, original) == original
    assert normalized_source(root, original.replace("old.webp", "new.png")) != normalized_source(root, original)
    assert normalized_source(root, '![说明](old.webp)\n') == normalized_source(root, '![说明](new.png)\n')
    assert normalized_source(root, '![说明](missing.png)\n') == '![说明](missing.png)\n'


def test_publish_preserves_legacy_generation_inputs_after_equivalent_reuse(article, monkeypatch):
    root, config = article
    mp3 = seal(article, legacy=True)
    original_receipt = pe._audio_manifest_path(mp3).read_bytes()
    original_entry = distribute.read_state(root)["channels"]["podcast"]
    convert_reference(root)
    config.update(remote_host="test-host", remote_episodes_dir="/test", feed_rebuild_command="rebuild")
    monkeypatch.setattr(pe.shutil, "which", lambda name: name)
    monkeypatch.setattr(pe, "_scp_with_retry", lambda *a: True)
    monkeypatch.setattr(pe.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert pe.cmd_publish(root, confirm=True) == 0
    published = distribute.read_state(root)["channels"]["podcast"]
    assert published["source_digest"] == original_entry["source_digest"]
    assert published["generation_digest"] == original_entry["generation_digest"]
    assert pe._audio_manifest_path(mp3).read_bytes() == original_receipt
    assert pe.generation_is_fresh(root, config)


def test_publish_contract_accepts_equivalence_and_rejects_caption_change(article, monkeypatch):
    import contracts
    root, config = article
    seal(article, legacy=True)
    convert_reference(root)
    draft = root / "定稿.md"
    draft.write_text(draft.read_text() + '\n<!-- AUDIO-CARD-START -->音乐<!-- AUDIO-CARD-END -->\n'
                     '<!-- PODCAST-CARD-START -->节目<!-- PODCAST-CARD-END -->\n')
    monkeypatch.setattr(distribute, "podcast_wechat_embed_enabled", lambda: True)
    assert not [e for e in contracts.verify_publish_assets(str(root))["errors"] if "播客" in e]
    draft.write_text(draft.read_text().replace("示例图", "新说明"))
    assert [e for e in contracts.verify_publish_assets(str(root))["errors"] if "播客" in e]


def test_mutation_of_body_comparison_admits_changed_prose(article):
    root, config = article
    seal(article, legacy=True)
    convert_reference(root)
    draft = root / "定稿.md"
    draft.write_text(draft.read_text().replace("正文需要保留", "错误地复用另一篇"))
    assert not pe.generation_is_fresh(root, config)
    code = Path(pe.__file__).read_text()
    guard = 'if old_body == current_body and expected == manifest["generation_digest"]:'
    assert code.count(guard) == 1
    mutant = types.ModuleType("mutated_podcast")
    mutant.__file__ = pe.__file__
    exec(compile(code.replace(guard, 'if expected == manifest["generation_digest"]:'), pe.__file__, "exec"), mutant.__dict__)
    assert mutant.generation_is_fresh(root, config)
