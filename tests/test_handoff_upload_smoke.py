"""交接 → 官网扫描契约 → 播客上传的端到端烟测（2026-09-23 审计 M5）。

用真实形态的文件名（空格、两个竖线、全角标点）走完整条链，而不是分别断言各函数的
返回值：此前播客 scp 的单测恰好断言了「远端路径带引号」那个 bug 本身，交接到下游
消费者之间也没有任何一条测试。播客上传用 PATH 里的假 scp / ssh 记录真实子进程参数。
"""
import json
import sys
from pathlib import Path

import pytest

import scripts.pipeline as pipeline  # noqa: F401  触发 scripts/ 进 sys.path
import distribute
import podcast_episode
from scripts.evidence import sha256_file
from scripts.handoff_assets import export_handoff_assets
from scripts.music_manifest import write_music_manifest

TITLE = "资讯 | Opus 5.5 与 GPT-6 Sol 同夜发布：一个追 Fable，一个砍半价"
SONG = "Opus 和 Sol 同一夜"
PODCAST_NAME = f"播客 | {TITLE}.mp3"


def _article(tmp_path: Path) -> tuple[Path, object, object]:
    article = tmp_path / "108-同夜发布"
    materials = article / "素材"
    materials.mkdir(parents=True)
    cover = materials / "cover.png"
    cover.write_bytes(b"sealed-cover")
    (materials / "bgm_cover.png").write_bytes(b"theme-cover")
    (materials / "podcast_cover.png").write_bytes(b"podcast-cover")
    (article / "article-meta.yaml").write_text(f'title: "{TITLE}"\n', encoding="utf-8")
    (article / "定稿.md").write_text(f"# {TITLE}\n\n正文。\n", encoding="utf-8")
    theme = article / f"{SONG}.mp3"
    theme.write_bytes(b"theme-audio")
    write_music_manifest(
        article, theme, title=SONG, duration_seconds=186.0, provider="example-provider",
        model="music-model", mode="web_manual", registry_reference="catalog/theme-songs.json",
        registry_entry="smoke",
    )
    podcast_dir = article / "dist/podcast"
    podcast_dir.mkdir(parents=True)
    audio = podcast_dir / "audio.mp3"
    audio.write_bytes(b"podcast-audio")
    (podcast_dir / "audio.json").write_text("{}", encoding="utf-8")
    (podcast_dir / "audio.manifest.json").write_text(json.dumps({
        "schema_version": 1, "audio_sha256": sha256_file(audio),
        "bytes": audio.stat().st_size, "duration_seconds": 600.0,
    }), encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "manifest": {"schema_version": 1, "assets": [{
            "stage": "cover", "path": "素材/cover.png",
            "sha256": sha256_file(cover), "bytes": cover.stat().st_size,
        }]},
        "manifest_digest": "visual-manifest",
    }
    return (article, lambda _d: (receipt, []),
            lambda p: (600.0, "") if p.name == "audio.mp3" else (186.0, ""))


def _fake_bin(tmp_path: Path, monkeypatch) -> Path:
    """PATH 最前面放假 scp / ssh：把收到的 argv 逐行记进 calls.jsonl，退出 0。"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "calls.jsonl"
    for name in ("scp", "ssh"):
        exe = bindir / name
        exe.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:], ensure_ascii=False) + '\\n')\n",
            encoding="utf-8",
        )
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{__import__('os').environ.get('PATH', '')}")
    return log


def test_handoff_then_scan_contract_then_podcast_upload(tmp_path, monkeypatch):
    article, verify_visual, probe = _article(tmp_path)
    bgm_before = pipeline._stage_artifact_digest(article, "bgm")

    # ① 交接：上传文件放文章第一层，文件名保留空格与竖线
    target, status, errors = export_handoff_assets(article, duration_probe=probe, visual_verifier=verify_visual)
    assert (target, status, errors) == (article, "created", [])
    top = {p.name for p in article.iterdir() if p.is_file()}
    assert {f"{SONG}.mp3", PODCAST_NAME, "cover.png", "音乐封面.png", "播客封面.png"} <= top
    # 交接副本不能把主题曲阶段标脏（审计 F2）
    assert pipeline._stage_artifact_digest(article, "bgm") == bgm_before

    # ② 官网扫描契约：主题曲只认 _music-manifest.json，第一层的播客 mp3 不能被当成主题曲
    manifest = json.loads((article / "_music-manifest.json").read_text(encoding="utf-8"))
    theme = article / manifest["theme"]["playback"]["path"]
    assert theme.is_file() and theme.name == f"{SONG}.mp3"
    assert not theme.name.startswith("播客")

    # ③ 播客上传：真实子进程调用，远端名是安全 slug，本地路径作为单个参数传递
    log = _fake_bin(tmp_path, monkeypatch)
    monkeypatch.setattr(podcast_episode, "cfg", lambda: {
        "remote_host": "podcast@example.invalid",
        "remote_episodes_dir": "/srv/podcast/episodes",
        "feed_rebuild_command": "rebuild-feed",
    })
    monkeypatch.setattr(podcast_episode, "generation_is_fresh", lambda *a, **k: True)
    monkeypatch.setattr(podcast_episode, "generation_digest", lambda *a, **k: "g")
    assert podcast_episode.cmd_publish(article, confirm=True) == 0

    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [c[0] for c in calls] == ["scp", "scp", "ssh"]
    sidecar, mp3, ssh = calls
    assert sidecar[1] == str(article / "dist/podcast/audio.json")   # 先传 sidecar
    assert mp3[1] == str(article / "dist/podcast/audio.mp3")
    for call in (sidecar, mp3):
        remote = call[2]
        assert remote.startswith("podcast@example.invalid:/srv/podcast/episodes/")
        name = remote.rsplit("/", 1)[1]
        assert not any(ch in name for ch in " |'\"")
        assert "资讯" not in name   # 栏目前缀不进远端名
    assert ssh == ["ssh", "podcast@example.invalid", "rebuild-feed"]
    assert distribute.get_status(article, "podcast") == "dispatched"


def test_upload_refuses_unsafe_remote_name():
    """反例：远端名一旦带空格或竖线就拒绝，不指望 SFTP 替我们处理引号。"""
    with pytest.raises(ValueError):
        podcast_episode.scp_remote("h", "/srv", PODCAST_NAME)
