"""水印与后处理台账（2026-09-23 审计 G1）。

第 108 篇的真实顺序：add_logo 因 ``@workspace/`` 没被 Node 解析、找不到 logo
静默跳过 → compress 把封面记进台账（stage=compressed）→ 再跑 add_logo 时
「sha 相同即跳过」，封面永远没有水印，而水印阶段验收只看「素材里有 PNG」。
这里用真实的 node + jimp 跑 add_logo.js，把这条链路钉住。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compress_images as ci  # noqa: E402
import pipeline  # noqa: E402

NODE = shutil.which("node")
HAS_JIMP = (SCRIPTS / "node_modules" / "jimp").is_dir()
needs_node = pytest.mark.skipif(not (NODE and HAS_JIMP), reason="需要 node 与 scripts/node_modules/jimp")


def _png(path: Path, size=(800, 400), color=(20, 20, 24)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _ledger(directory: Path) -> dict:
    return json.loads((directory / ci.LEDGER_NAME).read_text(encoding="utf-8"))


def _workspace(tmp_path: Path, *, with_logo: bool = True) -> tuple[Path, Path]:
    """造一棵最小工作树：.git + profile/brand/logo.png + 文章目录/素材/cover.png。"""
    ws = tmp_path / "ws"
    (ws / ".git").mkdir(parents=True)
    if with_logo:
        _png(ws / "profile" / "brand" / "logo.png", size=(200, 60), color=(250, 250, 250))
        _png(ws / "profile" / "brand" / "logo-black.png", size=(200, 60), color=(10, 10, 10))
    else:
        (ws / "profile" / "brand").mkdir(parents=True)
    article = ws / "文稿" / "1-测试"
    _png(article / "素材" / "cover.png")
    return ws, article


def _run_logo(article: Path, profile_value: str = "@workspace/profile") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SANSHENG_WRITE_")}
    env["SANSHENG_WRITE_PROFILE_DIR"] = profile_value
    return subprocess.run(
        [NODE, str(SCRIPTS / "add_logo.js"), "素材/*.png"],
        cwd=article, env=env, capture_output=True, text=True, timeout=120,
    )


# ---------- 压缩继承「已打水印」 ----------

def test_compress_carries_watermark_forward_when_bytes_untouched(tmp_path):
    path = _png(tmp_path / "素材" / "cover.png")
    ci.record_ledger(path, "logo")
    ci.compress_one(path, 2.0, verbose=False)
    entry = _ledger(tmp_path / "素材")["cover.png"]
    assert entry["stage"] == "compressed"
    assert entry["watermarked"] is True


def test_compress_without_prior_logo_records_not_watermarked(tmp_path):
    path = _png(tmp_path / "素材" / "cover.png")
    ci.compress_one(path, 2.0, verbose=False)
    assert _ledger(tmp_path / "素材")["cover.png"]["watermarked"] is False


def test_compress_does_not_inherit_watermark_after_rerender(tmp_path):
    path = _png(tmp_path / "素材" / "cover.png")
    ci.record_ledger(path, "logo")
    _png(path, color=(90, 10, 10))  # 重渲：字节变了，旧水印不再作数
    ci.compress_one(path, 2.0, verbose=False)
    assert _ledger(tmp_path / "素材")["cover.png"]["watermarked"] is False


# ---------- add_logo.js 端到端 ----------

@needs_node
def test_workspace_placeholder_resolves_and_stamps(tmp_path):
    _, article = _workspace(tmp_path)
    before = ci._sha256(article / "素材" / "cover.png")
    result = _run_logo(article)
    assert result.returncode == 0, result.stderr + result.stdout
    assert ci._sha256(article / "素材" / "cover.png") != before
    assert _ledger(article / "素材")["cover.png"]["watermarked"] is True


@needs_node
def test_compress_first_then_logo_still_stamps(tmp_path):
    """第 108 篇的顺序：先压缩（无水印）再打水印，必须真的打上。"""
    _, article = _workspace(tmp_path)
    cover = article / "素材" / "cover.png"
    ci.compress_one(cover, 2.0, verbose=False)
    compressed = ci._sha256(cover)
    result = _run_logo(article)
    assert result.returncode == 0, result.stderr + result.stdout
    assert ci._sha256(cover) != compressed, "压缩过但没打水印的封面被误判成已处理"
    assert _ledger(article / "素材")["cover.png"]["watermarked"] is True


@needs_node
def test_rerun_after_logo_and_compress_does_not_double_stamp(tmp_path):
    _, article = _workspace(tmp_path)
    cover = article / "素材" / "cover.png"
    assert _run_logo(article).returncode == 0
    ci.compress_one(cover, 2.0, verbose=False)
    settled = ci._sha256(cover)
    result = _run_logo(article)
    assert result.returncode == 0
    assert ci._sha256(cover) == settled, "打过水印又压缩过的图被二次叠水印"


@needs_node
def test_configured_profile_without_logo_fails_loudly(tmp_path):
    _, article = _workspace(tmp_path, with_logo=False)
    result = _run_logo(article)
    assert result.returncode == 2
    assert "找不到品牌 logo" in result.stderr


# ---------- 水印阶段验收 ----------

def test_verify_flags_cover_without_watermark(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_profile_logo_available", lambda: True)
    mat = tmp_path / "素材"
    path = _png(mat / "cover.png")
    ci.compress_one(path, 2.0, verbose=False)  # 只压缩没打水印
    errors = pipeline._watermark_ledger_errors(mat)
    assert errors and "没打上品牌水印" in errors[0]


def test_verify_passes_watermarked_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_profile_logo_available", lambda: True)
    mat = tmp_path / "素材"
    path = _png(mat / "cover.png")
    ci.record_ledger(path, "logo")
    ci.compress_one(path, 2.0, verbose=False)
    assert pipeline._watermark_ledger_errors(mat) == []


def test_verify_flags_cover_changed_after_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_profile_logo_available", lambda: True)
    mat = tmp_path / "素材"
    path = _png(mat / "cover.png")
    ci.record_ledger(path, "logo")
    _png(path, color=(1, 2, 3))
    errors = pipeline._watermark_ledger_errors(mat)
    assert errors and "又被改过" in errors[0]


def test_verify_skips_when_profile_has_no_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_profile_logo_available", lambda: False)
    mat = tmp_path / "素材"
    _png(mat / "cover.png")
    assert pipeline._watermark_ledger_errors(mat) == []


def test_verify_stage_logo_wires_ledger_check(tmp_path, monkeypatch):
    """走 verify_stage('logo') 的完整入口，防止台账检查被从阶段验收里摘掉。"""
    monkeypatch.setattr(pipeline, "_profile_logo_available", lambda: True)
    mat = tmp_path / "素材"
    path = _png(mat / "cover.png")
    ci.compress_one(path, 2.0, verbose=False)
    result = pipeline.verify_stage("logo", tmp_path, {"stages": {}})
    passed, errors = result[0], result[1]
    assert not passed
    assert any("没打上品牌水印" in e for e in errors)
