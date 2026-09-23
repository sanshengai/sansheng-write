# -*- coding: utf-8 -*-
"""音频封面 46px 盲配（references/music.md §验收：盲配测试）。

分三层测：
- 纯逻辑（`build_candidates` 取标题/打乱、`_judge` 判定）——不碰子进程，不碰真实图片。
- 总控 `run_blind_match`——monkeypatch 掉唯一的子进程调用 `_invoke_model`，覆盖
  pass / 一张配错 fail / 模型输出无法解析 / 未配置时 skipped / 作品库不可用的退化。
- 一条不打桩的进程契约测试（`_invoke_model` 本身），确认命令行、图片路径真的传给了
  子进程、`_extract_json` 真的能拆出结果——和 `test_visual_qa_claude.py` 同一手法。

不得真的调用模型或联网：除最后一条契约测试用一个假 `claude` 可执行文件外，
其余全部通过 monkeypatch `_invoke_model` / `build_candidates` / `_resolve_claude` 控制。
"""
from __future__ import annotations

import json
import re
import stat
import sys
from pathlib import Path

import pytest
from PIL import Image

from scripts import cover_blind_match as bm
from scripts.article_paths import process_file
from scripts import works_registry


# ---------- 纯逻辑：build_candidates ----------

def _write_works(path: Path, entries: list[dict]) -> None:
    works_registry.save_works(entries, path=path)


def test_build_candidates_uses_recent_five_and_excludes_self(tmp_path, monkeypatch):
    works_path = tmp_path / "works.yaml"
    _write_works(works_path, [
        {"seq": 100, "title": "老文章A", "status": "published", "date": "2026-08-01"},
        {"seq": 101, "title": "老文章B", "status": "published", "date": "2026-08-10"},
        {"seq": 102, "title": "老文章C", "status": "published", "date": "2026-08-20"},
        {"seq": 103, "title": "老文章D", "status": "published", "date": "2026-08-25"},
        {"seq": 104, "title": "老文章E", "status": "published", "date": "2026-08-28"},
        {"seq": 105, "title": "老文章F（超出最近5篇窗口）", "status": "published", "date": "2026-07-01"},
        {"seq": 106, "title": "本篇不该混进候选池", "status": "draft", "date": "2026-09-01"},
    ])
    monkeypatch.setenv("SANSHENG_WRITE_WORKS_FILE", str(works_path))
    article_dir = tmp_path / "106-本篇"
    article_dir.mkdir()

    candidates, degraded, reason = bm.build_candidates(article_dir, "本篇真实标题", exclude_seq=106)

    assert not degraded and reason is None
    titles = {c["title"] for c in candidates}
    assert len(candidates) == 6  # 本篇 + 最近 5 篇
    assert "本篇真实标题" in titles
    assert "本篇不该混进候选池" not in titles
    assert "老文章F（超出最近5篇窗口）" not in titles
    targets = [c for c in candidates if c["is_target"]]
    assert len(targets) == 1 and targets[0]["title"] == "本篇真实标题"


def test_build_candidates_degrades_to_placeholders_when_works_library_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_WRITE_WORKS_FILE", str(tmp_path / "does-not-exist.yaml"))
    article_dir = tmp_path / "999-本篇"
    article_dir.mkdir()

    candidates, degraded, reason = bm.build_candidates(article_dir, "本篇标题", exclude_seq=999)

    assert degraded and reason
    titles = {c["title"] for c in candidates}
    assert "本篇标题" in titles
    assert set(bm.PLACEHOLDER_TITLES).issubset(titles)
    assert len(candidates) == 1 + len(bm.PLACEHOLDER_TITLES)


def test_build_candidates_shuffle_is_reproducible_for_same_article_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_WRITE_WORKS_FILE", str(tmp_path / "missing.yaml"))
    article_dir = tmp_path / "50-同一篇"
    article_dir.mkdir()

    first, _, _ = bm.build_candidates(article_dir, "标题", exclude_seq=50)
    second, _, _ = bm.build_candidates(article_dir, "标题", exclude_seq=50)

    assert first == second


def test_seed_from_name_is_a_deterministic_function_of_the_name():
    assert bm._seed_from_name("108-同一篇") == bm._seed_from_name("108-同一篇")
    assert bm._seed_from_name("108-同一篇") != bm._seed_from_name("109-另一篇")


# ---------- 纯逻辑：_judge ----------

def _candidates(target_index: int = 2) -> list[dict]:
    return [
        {"index": i, "title": ("本篇" if i == target_index else f"别篇{i}"), "is_target": i == target_index}
        for i in (1, 2, 3)
    ]


def test_judge_passes_when_every_image_picks_the_target():
    payload = {"choices": [
        {"image": "theme_cover", "chosen_index": 2, "confidence": "high", "description": "见太阳浮雕 Sol"},
        {"image": "podcast_cover", "chosen_index": 2, "confidence": "medium", "description": "见并排数字"},
    ]}
    results, ok, err = bm._judge(payload, _candidates(), ["theme_cover", "podcast_cover"])
    assert ok and err is None
    assert all(r["correct"] for r in results)


def test_judge_fails_when_one_image_picks_the_wrong_title():
    payload = {"choices": [
        {"image": "theme_cover", "chosen_index": 2, "confidence": "high", "description": "见太阳浮雕 Sol"},
        {"image": "podcast_cover", "chosen_index": 1, "confidence": "low", "description": "像星芒，猜别篇1"},
    ]}
    results, ok, err = bm._judge(payload, _candidates(), ["theme_cover", "podcast_cover"])
    assert not ok and err is None
    wrong = next(r for r in results if r["image"] == "podcast_cover")
    assert not wrong["correct"] and wrong["chosen_title"] == "别篇1"
    assert "像星芒" in wrong["description"]
    right = next(r for r in results if r["image"] == "theme_cover")
    assert right["correct"]


@pytest.mark.parametrize("payload", [
    {},
    {"choices": "not-a-list"},
    {"choices": []},
    {"choices": [{"image": "theme_cover", "chosen_index": 2, "confidence": "high", "description": "x"}]},
    {"choices": [
        {"image": "theme_cover", "chosen_index": 99, "confidence": "high", "description": "x"},
        {"image": "podcast_cover", "chosen_index": 2, "confidence": "high", "description": "x"},
    ]},
    "不是字典",
    None,
])
def test_judge_reports_clear_error_for_unusable_payload(payload):
    results, ok, err = bm._judge(payload, _candidates(), ["theme_cover", "podcast_cover"])
    assert not ok and not results and err


# ---------- 缩略图 ----------

def test_make_blind_thumb_downscales_then_upscales_to_138(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (777, 777), (5, 5, 5)).save(src)
    dest = tmp_path / "thumb.png"

    bm._make_blind_thumb(src, dest)

    with Image.open(dest) as out:
        assert out.size == (bm.THUMB_BIG, bm.THUMB_BIG) == (138, 138)


# ---------- 总控 run_blind_match（monkeypatch 掉 _invoke_model） ----------

def _cover_pair(article_dir: Path) -> dict[str, Path]:
    theme = article_dir / "音乐封面.png"
    podcast = article_dir / "播客封面.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(theme)
    Image.new("RGB", (64, 64), (200, 100, 50)).save(podcast)
    return {"theme_cover": theme, "podcast_cover": podcast}


def _force_claude_available(monkeypatch):
    monkeypatch.setattr(bm, "_resolve_claude", lambda name: sys.executable)


def _patch_candidates(monkeypatch, candidates, degraded=False, reason=None):
    monkeypatch.setattr(bm, "build_candidates", lambda *a, **kw: (candidates, degraded, reason))


def test_run_blind_match_pass_writes_credential_and_review(tmp_path, monkeypatch):
    _force_claude_available(monkeypatch)
    _patch_candidates(monkeypatch, _candidates(target_index=2))
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)

    def fake_invoke(image_paths, prompt, schema, *, model, claude_bin, **kw):
        assert set(image_paths) == {"theme_cover", "podcast_cover"}
        for path in image_paths.values():
            assert path.is_file()  # 缩略图真的落盘了
        return {"choices": [
            {"image": "theme_cover", "chosen_index": 2, "confidence": "high", "description": "见太阳浮雕 Sol"},
            {"image": "podcast_cover", "chosen_index": 2, "confidence": "high", "description": "见并排 5.5 与 6"},
        ]}, None

    monkeypatch.setattr(bm, "_invoke_model", fake_invoke)
    outcome = bm.run_blind_match(article_dir, covers, article_title="本篇", exclude_seq=108)

    assert outcome == {"status": "pass", "errors": [], "warnings": []}
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["status"] == "pass" and len(credential["results"]) == 2
    review = process_file(article_dir, bm.REVIEW_FILE).read_text(encoding="utf-8")
    assert "自动盲配" in review and "✅" in review and "❌" not in review


def test_run_blind_match_fails_when_one_cover_is_mismatched(tmp_path, monkeypatch):
    _force_claude_available(monkeypatch)
    _patch_candidates(monkeypatch, _candidates(target_index=2))
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)

    def fake_invoke(image_paths, prompt, schema, *, model, claude_bin, **kw):
        return {"choices": [
            {"image": "theme_cover", "chosen_index": 1, "confidence": "medium", "description": "像星芒，猜别篇1"},
            {"image": "podcast_cover", "chosen_index": 2, "confidence": "high", "description": "见并排数字"},
        ]}, None

    monkeypatch.setattr(bm, "_invoke_model", fake_invoke)
    outcome = bm.run_blind_match(article_dir, covers, article_title="本篇", exclude_seq=108)

    assert outcome["status"] == "fail"
    assert outcome["errors"] and "像星芒" in outcome["errors"][0]
    assert "_audio-cover-plan.json" in outcome["errors"][0] and "--force" in outcome["errors"][0]
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["status"] == "fail"
    review = process_file(article_dir, bm.REVIEW_FILE).read_text(encoding="utf-8")
    assert "❌ 配错" in review


def test_run_blind_match_errors_when_model_output_unparseable(tmp_path, monkeypatch):
    _force_claude_available(monkeypatch)
    _patch_candidates(monkeypatch, _candidates())
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)
    monkeypatch.setattr(
        bm, "_invoke_model",
        lambda *a, **kw: (None, "结论不是合法 JSON；原文前 300 字：图片看不清，无法判断。"),
    )

    outcome = bm.run_blind_match(article_dir, covers, article_title="本篇", exclude_seq=108)

    assert outcome["status"] == "error"
    assert outcome["errors"] and "不是合法 JSON" in outcome["errors"][0]
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["status"] == "error"
    # 没取得真正的判定结果，不追加人读摘要——review.md 只记真实配对结果。
    assert not process_file(article_dir, bm.REVIEW_FILE).is_file()


def test_run_blind_match_skipped_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv(bm.ENV_OFF, "off")
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)

    outcome = bm.run_blind_match(article_dir, covers, article_title="标题", exclude_seq=108)

    assert outcome["status"] == "skipped" and not outcome["errors"] and outcome["warnings"]
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["skipped_reason"] == "skipped_by_env"


def test_run_blind_match_skipped_when_claude_cli_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "_resolve_claude", lambda name: "/definitely/not/a/real/claude/binary")
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)

    outcome = bm.run_blind_match(article_dir, covers, article_title="标题", exclude_seq=108)

    assert outcome["status"] == "skipped" and not outcome["errors"] and outcome["warnings"]
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["skipped_reason"] == "claude_cli_not_found"


def test_run_blind_match_degrades_end_to_end_when_works_library_unavailable(tmp_path, monkeypatch):
    """不打桩 build_candidates，让真实退化路径跑一遍：作品库缺失 → 占位干扰标题 → 仍然判定。"""
    _force_claude_available(monkeypatch)
    monkeypatch.setenv("SANSHENG_WRITE_WORKS_FILE", str(tmp_path / "missing-works.yaml"))
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)

    def fake_invoke(image_paths, prompt, schema, *, model, claude_bin, **kw):
        match = re.search(r"(\d+)\. 本篇真实标题\b", prompt)
        assert match, "prompt 里应该能找到本篇标题对应的编号"
        target_index = int(match.group(1))
        return {
            "choices": [
                {"image": key, "chosen_index": target_index, "confidence": "high", "description": "占位描述"}
                for key in image_paths
            ]
        }, None

    monkeypatch.setattr(bm, "_invoke_model", fake_invoke)
    outcome = bm.run_blind_match(article_dir, covers, article_title="本篇真实标题", exclude_seq=108)

    assert outcome["status"] == "pass"
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["degraded"] is True and credential["degraded_reason"]
    other_titles = {c["title"] for c in credential["candidates"] if not c["is_target"]}
    assert other_titles.issubset(set(bm.PLACEHOLDER_TITLES))


# ---------- 进程契约（不打桩 _invoke_model 本身，只假装 claude 可执行文件） ----------

def _fake_claude_script(tmp_path: Path, body: str) -> Path:
    """伪 claude：把收到的参数记进 argv.json，再吐一个 Claude Code CLI 风格的结果信封。"""
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


def test_invoke_model_builds_command_and_parses_result_envelope(tmp_path):
    verdict = {"choices": [{"image": "theme_cover", "chosen_index": 1, "confidence": "high", "description": "d1"}]}
    exe = _fake_claude_script(tmp_path, json.dumps({"type": "result", "structured_output": verdict}))
    image_dir = tmp_path / "imgs"
    image_dir.mkdir()
    thumb = image_dir / "theme_cover.png"
    Image.new("RGB", (10, 10)).save(thumb)

    payload, error = bm._invoke_model(
        {"theme_cover": thumb}, "prompt-body", {"type": "object"},
        model="claude-sonnet-5", claude_bin=str(exe),
    )

    assert error is None and payload == verdict
    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
    assert argv[argv.index("--tools") + 1] == "Read"
    assert Path(argv[argv.index("--add-dir") + 1]) == image_dir


def test_invoke_model_reports_clear_error_when_claude_exits_nonzero(tmp_path):
    exe = tmp_path / "fake-claude"
    exe.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\nsys.exit(1)\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    image_dir = tmp_path / "imgs"
    image_dir.mkdir()
    thumb = image_dir / "theme_cover.png"
    Image.new("RGB", (10, 10)).save(thumb)

    payload, error = bm._invoke_model(
        {"theme_cover": thumb}, "prompt-body", {"type": "object"},
        model="claude-sonnet-5", claude_bin=str(exe),
        timeout=5, retry_timeout=5, retry_pause=0,
    )

    assert payload is None and error and "exit=1" in error


# ---------- 已有结论继续生效（重跑 handoff 不能绕过配错） ----------

def _mismatch_invoke(image_paths, prompt, schema, *, model, claude_bin, **kw):
    return {"choices": [
        {"image": "theme_cover", "chosen_index": 1, "confidence": "high", "description": "太阳星芒"},
        {"image": "podcast_cover", "chosen_index": 2, "confidence": "high", "description": "并排数字"},
    ]}, None


def _must_not_invoke(*a, **kw):
    raise AssertionError("封面没变、结论已定，不该再调模型")


def _failed_article(tmp_path, monkeypatch):
    _force_claude_available(monkeypatch)
    _patch_candidates(monkeypatch, _candidates(target_index=2))
    article_dir = tmp_path / "108-测试文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)
    monkeypatch.setattr(bm, "_invoke_model", _mismatch_invoke)
    assert bm.run_blind_match(article_dir, covers, article_title="本篇")["status"] == "fail"
    return article_dir, covers


def test_recheck_keeps_failure_for_unchanged_covers(tmp_path, monkeypatch):
    article_dir, covers = _failed_article(tmp_path, monkeypatch)
    monkeypatch.setattr(bm, "_invoke_model", _must_not_invoke)
    outcome = bm.recheck_existing(article_dir, covers, article_title="本篇")
    assert outcome["status"] == "fail" and "太阳星芒" in outcome["errors"][0]


def test_recheck_reruns_when_cover_replaced(tmp_path, monkeypatch):
    article_dir, covers = _failed_article(tmp_path, monkeypatch)
    Image.new("RGB", (64, 64), (0, 200, 0)).save(covers["theme_cover"])
    calls = []

    def passing(image_paths, prompt, schema, **kw):
        calls.append(1)
        return {"choices": [
            {"image": k, "chosen_index": 2, "confidence": "high", "description": "d"} for k in image_paths
        ]}, None

    monkeypatch.setattr(bm, "_invoke_model", passing)
    assert bm.recheck_existing(article_dir, covers, article_title="本篇")["status"] == "pass"
    assert calls == [1]


def test_recheck_without_credential_does_nothing(tmp_path, monkeypatch):
    article_dir = tmp_path / "90-历史文章"
    article_dir.mkdir()
    covers = _cover_pair(article_dir)
    monkeypatch.setattr(bm, "_invoke_model", _must_not_invoke)
    assert bm.recheck_existing(article_dir, covers, article_title="旧文")["status"] == "absent"


def test_recheck_env_off_overrides_recorded_failure(tmp_path, monkeypatch):
    article_dir, covers = _failed_article(tmp_path, monkeypatch)
    monkeypatch.setenv(bm.ENV_OFF, "off")
    outcome = bm.recheck_existing(article_dir, covers, article_title="本篇")
    assert outcome["status"] == "skipped" and outcome["errors"] == []
    credential = json.loads(process_file(article_dir, bm.BLINDMATCH_FILE).read_text(encoding="utf-8"))
    assert credential["skipped_reason"] == "skipped_by_env"


def test_invoke_model_retries_after_timeout(tmp_path):
    marker = tmp_path / "first-call-done"
    verdict = {"choices": [{"image": "theme_cover", "chosen_index": 1, "confidence": "high", "description": "d"}]}
    exe = tmp_path / "fake-claude"
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, time, pathlib\n"
        "sys.stdin.read()\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "if not marker.exists():\n"
        "    marker.write_text('1')\n"
        "    time.sleep(10)\n"
        f"sys.stdout.write({json.dumps({'type': 'result', 'structured_output': verdict})!r})\n",
        encoding="utf-8",
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    image_dir = tmp_path / "imgs"
    image_dir.mkdir()
    thumb = image_dir / "theme_cover.png"
    Image.new("RGB", (10, 10)).save(thumb)

    payload, error = bm._invoke_model(
        {"theme_cover": thumb}, "prompt-body", {"type": "object"},
        model="claude-sonnet-5", claude_bin=str(exe),
        timeout=1, retry_timeout=10, retry_pause=0,
    )

    assert error is None and payload == verdict
