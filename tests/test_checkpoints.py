# -*- coding: utf-8 -*-
"""人工检查点闸门（workflow.checkpoints）：解析 + verify 硬拦 + 默认关闭。"""
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import profile_config  # noqa: E402
from pipeline import _checkpoint_errors  # noqa: E402


def _make_profile(tmp_path, checkpoints_yaml: str) -> Path:
    p = tmp_path / "profile"
    p.mkdir()
    (p / "brand.yaml").write_text(
        "workflow:\n  checkpoints: " + checkpoints_yaml + "\n", encoding="utf-8"
    )
    return p


def _with_profile(monkeypatch, profile: Path):
    monkeypatch.setenv("SANSHENG_WRITE_PROFILE_DIR", str(profile))
    profile_config._reset_cache_for_tests()


def test_checkpoints_off_by_default(tmp_path):
    """conftest 钉在 example profile：未配置 workflow → 闸门全关（原全自动行为）。"""
    profile_config._reset_cache_for_tests()
    assert profile_config.workflow_checkpoints() == []
    assert _checkpoint_errors("outline", tmp_path) == []
    assert _checkpoint_errors("writing", tmp_path) == []


def test_workflow_checkpoints_parse_and_filter(tmp_path, monkeypatch):
    """list / csv 两种写法都收，非法值被滤掉。"""
    try:
        _with_profile(monkeypatch, _make_profile(tmp_path, "[blueprint, draft, bogus]"))
        assert profile_config.workflow_checkpoints() == ["blueprint", "draft"]
        (tmp_path / "profile" / "brand.yaml").write_text(
            'workflow:\n  checkpoints: "draft, blueprint"\n', encoding="utf-8"
        )
        profile_config._reset_cache_for_tests()
        assert profile_config.workflow_checkpoints() == ["draft", "blueprint"]
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_PROFILE_DIR", raising=False)
        profile_config._reset_cache_for_tests()


def test_checkpoint_gate_blocks_then_structured_anchor_passes(tmp_path, monkeypatch):
    """启用双闸：只有文件名不算过闸，蓝图必须含标题/开头/大纲/视觉路由。"""
    try:
        _with_profile(monkeypatch, _make_profile(tmp_path, "[blueprint, draft]"))
        art = tmp_path / "art"
        art.mkdir()

        errs = _checkpoint_errors("outline", art)
        assert errs and "blueprint" in errs[0] and "_blueprint-approval.md" in errs[0]
        errs = _checkpoint_errors("writing", art)
        assert errs and "draft" in errs[0] and "_draft-approval.md" in errs[0]

        (art / "_blueprint-approval.md").write_text("标题1/开头A/大纲OK", encoding="utf-8")
        (art / "_draft-approval.md").write_text("过", encoding="utf-8")
        errs = _checkpoint_errors("outline", art)
        assert errs and "视觉路由" in errs[0]

        (art / "_blueprint-approval.md").write_text(
            "作者指定标题：标题1\n开头：A\n大纲：通过\n"
            "封面风格：montage-evidence\n"
            "信息图主题：ai-product\n信息图风格：claymation\n",
            encoding="utf-8",
        )
        assert _checkpoint_errors("outline", art) == []
        assert _checkpoint_errors("writing", art) == []

        # 其他 stage 永不设闸
        assert _checkpoint_errors("cover", art) == []
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_PROFILE_DIR", raising=False)
        profile_config._reset_cache_for_tests()


def test_single_gate_only(tmp_path, monkeypatch):
    """只开 draft 闸时，outline 不受影响。"""
    try:
        _with_profile(monkeypatch, _make_profile(tmp_path, "[draft]"))
        art = tmp_path / "art"
        art.mkdir()
        assert _checkpoint_errors("outline", art) == []
        assert _checkpoint_errors("writing", art) != []
    finally:
        monkeypatch.delenv("SANSHENG_WRITE_PROFILE_DIR", raising=False)
        profile_config._reset_cache_for_tests()
