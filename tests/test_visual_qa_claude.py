# -*- coding: utf-8 -*-
"""Claude Code 后端的视觉复核适配器：只测它与 codex 版分叉的那几处。

合同（提示词 / schema / 逐项判据）全部从 visual_qa_codex 复用，那边的用例已经覆盖；
这里只盯三件事：结果信封解析、失败也返回 0（结论交校验器裁决）、以及 `--add-dir`
必须放行图片目录 —— 漏掉它时 Read 会被 dontAsk 静默拒绝，模型只能凭空瞎答。
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from scripts import visual_qa_claude


# ---------- ① 结果信封解析 ----------

def test_extract_prefers_structured_output_envelope():
    payload = {"checks": {"text_match": True}, "visual_evidence": [{"trait": "x", "seen": "y"}]}
    envelope = {"type": "result", "result": "看完了", "structured_output": payload}
    assert visual_qa_claude._extract_json(json.dumps(envelope)) == payload


def test_extract_falls_back_to_fenced_json_inside_result_text():
    inner = {"checks": {"crop_safe": False}, "visual_evidence": [{"trait": "t", "seen": "s"}]}
    envelope = {"type": "result", "result": "结论如下：\n```json\n" + json.dumps(inner) + "\n```"}
    assert visual_qa_claude._extract_json(json.dumps(envelope)) == inner


def test_extract_returns_none_for_garbage():
    assert visual_qa_claude._extract_json("") is None
    assert visual_qa_claude._extract_json("图片看不清，无法判断。") is None


def test_default_reviewer_is_not_an_image_model():
    assert "image" not in visual_qa_claude.DEFAULT_MODEL
    assert visual_qa_claude.DEFAULT_MODEL != "codex-image-gen"


# ---------- ② 进程契约：失败也返回 0，raw 永远落盘，图片目录必须放行 ----------

def _fake_claude(tmp_path: Path, body: str) -> Path:
    """伪 claude：把收到的参数记进 argv.json，再按脚本要求吐一个结果信封。"""
    exe = tmp_path / "fake-claude"
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"json.dump(sys.argv[1:], open({str(tmp_path / 'argv.json')!r}, 'w'))\n"
        "sys.stdin.read()\n"
        f"sys.stdout.write({body!r})\n",
        encoding="utf-8",
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def _request(tmp_path: Path) -> Path:
    article = tmp_path / "article"
    (article / "素材").mkdir(parents=True)
    (article / "素材" / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    request = {
        "assets": [
            {
                "path": "素材/hero.png",
                "stage": "hero",
                "target_style": "claymation",
                "expected_text": ["六块学英语"],
                "required_text": ["六块学英语"],
                "required_checks": ["text_match", "crop_safe"],
                "pixel_metrics": {"width": 10, "height": 10},
                "generation": {"model": "codex-image-gen"},
                "style_contract": {"required_visual_traits": ["matte clay"]},
            }
        ]
    }
    path = article / "_visual-qa-request.json"
    path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    return path


def _run(tmp_path: Path, exe: Path) -> tuple[subprocess.CompletedProcess, Path]:
    request = _request(tmp_path)
    output = tmp_path / "candidate.json"
    env = {**os.environ, "SANSHENG_WRITE_VISUAL_QA_CLAUDE": str(exe), "SANSHENG_WRITE_VISUAL_QA_JOBS": "1"}
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(visual_qa_claude.__file__)),
         "--request", str(request), "--output", str(output)],
        capture_output=True, text=True, encoding="utf-8", env=env, check=False,
    )
    return completed, output


def test_failed_verdict_still_exits_zero_and_writes_raw(tmp_path):
    verdict = {
        "observed_text": ["六块学英语"],
        "observed_layout": "标题在上",
        "visual_evidence": [{"trait": "matte clay", "seen": "yes"}],
        "checks": {"text_match": True, "crop_safe": False},
        "notes": "标题贴边",
    }
    exe = _fake_claude(tmp_path, json.dumps({"type": "result", "structured_output": verdict}))
    completed, output = _run(tmp_path, exe)
    assert completed.returncode == 0, completed.stderr
    qa = json.loads(output.read_text(encoding="utf-8"))
    assert qa["status"] == "fail"
    assert any("crop_safe" in item for item in qa["failures"])
    assert qa["reviewer"]["backend"] == "claude-code-cli"
    raw = json.loads((tmp_path / "article" / "_visual-qa.raw.json").read_text(encoding="utf-8"))
    assert raw["status"] == "fail"
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    add_dir = argv[argv.index("--add-dir") + 1]
    assert Path(add_dir) == (tmp_path / "article" / "素材").resolve()
    assert argv[argv.index("--tools") + 1] == "Read"


def test_boolean_only_verdict_is_a_channel_failure(tmp_path):
    """只回布尔值、没有 visual_evidence：说明提示词没送达，不能当结论用。"""
    verdict = {"checks": {"text_match": True, "crop_safe": True}}
    exe = _fake_claude(tmp_path, json.dumps({"type": "result", "structured_output": verdict}))
    completed, output = _run(tmp_path, exe)
    assert completed.returncode == 0, completed.stderr
    qa = json.loads(output.read_text(encoding="utf-8"))
    assert qa["status"] == "fail"
    assert qa["assets"] == []
    assert any("visual_evidence" in item for item in qa["failures"])
