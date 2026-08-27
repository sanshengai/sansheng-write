#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""podcast_episode.py -- 把一篇定稿做成播客单集（本机生成 → 推送到 feed 主机）。

🔴 为什么在本机跑而不是服务器上跑：
NotebookLM 的登录态只有真实浏览器能维持。服务器是 headless 机器，凭证只能是
从本机拷上去的静态快照，Google 在 1-3 小时内主动判废——晨报那条链路为此
踩了整整一年，每次都要人工重登再补跑。文章音频不需要无人值守（作者发完
公众号本来就在场），本机跑登录态是新鲜的，直接绕开这个坑。

两步，可分开跑（生成要 10-20 分钟，适合后台）：

    python podcast_episode.py --dir <文章目录> generate   # → audio.mp3 + sidecar
    python podcast_episode.py --dir <文章目录> publish    # → 推送 + 重建 feed

`--dir` 放在子命令前后都认（子命令那份用 SUPPRESS 兜底，不会用默认值把前面的覆盖掉）。

sidecar（与 mp3 同名的 .json）是必需品，不是可选优化：feed 生成器对没有
sidecar 的文件要求文件名必须是纯 YYYY-MM-DD.mp3，否则**静默跳过**；就算
侥幸进了 feed，描述也会套用晨报的「今日 N 条要闻」。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from profile_config import distribute_channel  # noqa: E402
import distribute  # noqa: E402

POLL_INTERVAL = 30
POLL_TIMEOUT = 1800          # 30 分钟。长文比晨报慢，20 分钟不够。
DOWNLOAD_RETRIES = 5
DOWNLOAD_INTERVAL = 90       # status=completed 后 CDN 仍可能没同步好，晨报实测要等
MIN_AUDIO_BYTES = 100_000
PODCAST_GENERATOR_SCHEMA = 2


def log(msg: str) -> None:
    print(f"[podcast {datetime.now():%H:%M:%S}] {msg}", flush=True)


# Windows GBK 控制台吃不下 ✓/✗ 等符号，统一把标准输出重配为 UTF-8 容错模式
# （2026-07-30 实测：生成成功后打印「✓」直接 UnicodeEncodeError 崩在收尾）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def cfg() -> dict:
    return distribute_channel("podcast")


def generation_digest(article_dir: Path, c: dict | None = None) -> str:
    """绑定真正影响节目内容的输入；缺任何一项都不得复用旧音频。"""
    c = c or cfg()
    prompt = Path(str(c.get("focus_prompt") or "")).expanduser()
    prompt_sha = (
        hashlib.sha256(prompt.read_bytes()).hexdigest() if prompt.is_file() else ""
    )
    payload = {
        "schema": PODCAST_GENERATOR_SCHEMA,
        "source_digest": distribute.source_digest(article_dir, "podcast"),
        "title": distribute.read_final_title(article_dir),
        "focus_prompt_sha256": prompt_sha,
        "language": str(c.get("language") or "zh"),
        "length": str(c.get("length") or "default"),
        "format": "deep_dive",
    }
    return distribute._digest(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def generation_is_fresh(article_dir: Path, c: dict | None = None) -> bool:
    c = c or cfg()
    mp3 = distribute.channel_dir(article_dir, "podcast") / "audio.mp3"
    entry = (distribute.read_state(article_dir).get("channels", {}).get("podcast") or {})
    return (
        mp3.is_file()
        and not distribute._is_drifted(article_dir, "podcast")
        and entry.get("generation_digest") == generation_digest(article_dir, c)
        and entry.get("audio_sha256") == hashlib.sha256(mp3.read_bytes()).hexdigest()
    )


def validate_audio(path: Path) -> tuple[bool, str]:
    """用 ffprobe 验证候选确有音频流与正时长，避免半文件覆盖已可用旧件。"""
    if not path.is_file() or path.stat().st_size < MIN_AUDIO_BYTES:
        return False, "文件不存在或过小"
    probe = shutil.which("ffprobe")
    if not probe:
        return False, "找不到 ffprobe"
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=codec_name,duration", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        duration = float((streams[0] if streams else {}).get("duration") or 0)
        if result.returncode != 0 or not streams or duration <= 0:
            return False, (result.stderr or "无有效音频流/时长").strip()[:200]
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return False, str(exc)[:200]
    return True, ""


def _nlm_bin() -> str:
    explicit = str(cfg().get("nlm_bin") or "").strip()
    if explicit:
        return explicit
    return shutil.which("nlm") or str(Path.home() / ".local" / "bin" / "nlm")


def _try_auto_login() -> bool:
    """登录态失效时自动弹浏览器授权（2026-07-30 sandy 拍板固化的规则）：
    检测到过期不再只提示「请运行 nlm login」，而是直接替作者拉起 `nlm login`
    （启动 Chrome 走 CDP，作者在旁时点一下即完成）。无人值守环境可用
    SANSHENG_NLM_NO_AUTOLOGIN=1 关回纯提示模式。登录成功后做一次只读探针确认。"""
    if os.environ.get("SANSHENG_NLM_NO_AUTOLOGIN") == "1":
        return False
    log("  检测到登录态失效，自动弹出浏览器登录（nlm login）…")
    try:
        subprocess.run([_nlm_bin(), "login"], timeout=420, check=False)
    except Exception as e:                                     # noqa: BLE001
        log(f"  自动登录拉起失败：{str(e)[:200]}")
        return False
    try:
        run_nlm("notebook", "list", "--json", want_json=True, timeout=60)
        log("  ✓ 登录态已恢复，继续原流程")
        return True
    except Exception:                                          # noqa: BLE001
        return False


def run_nlm(*args: str, timeout: float = 600, want_json: bool = False):
    """跑 nlm。0.9.x 起各子命令都支持 --json，不必再从纯文本里 regex 抠 ID。"""
    cmd = [_nlm_bin(), *args]
    log(f"$ nlm {' '.join(args[:3])}{'…' if len(args) > 3 else ''}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"nlm {' '.join(args[:3])} 失败 (rc={r.returncode})\n"
            f"stderr: {(r.stderr or '')[:400]}\nstdout: {(r.stdout or '')[:400]}"
        )
    out = (r.stdout or "").strip()
    if not want_json:
        return out
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # 少数子命令即使给了 --json 也可能回落纯文本；交给调用方兜底
        return {"_raw": out}


def _retry(label: str, fn, attempts: int = 3, waits=(20, 45)):
    """网络抖动当场自愈。晨报踩过两次 create/source add 死于瞬时网络错误。"""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:                       # noqa: BLE001
            last = e
            log(f"  {label} 失败 {i + 1}/{attempts}: {str(e)[:200]}")
            if i < attempts - 1:
                w = waits[min(i, len(waits) - 1)]
                log(f"  等 {w}s 重试…")
                time.sleep(w)
    raise last


def _extract_id(payload, *keys: str) -> str:
    if isinstance(payload, dict):
        for k in keys:
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        raw = payload.get("_raw", "")
    else:
        raw = str(payload)
    m = re.search(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                  r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b", raw)
    return m.group(1) if m else ""


def _safe_stem(text: str) -> str:
    """文件名安全化。斜杠冒号等在 Windows/Linux 都是非法字符。"""
    cleaned = re.sub(r'[/\\:*?"<>|]', "", text).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned[:40] or "episode"


# ===== generate =====

def cmd_generate(article_dir: Path, keep_notebook: bool = False) -> int:
    c = cfg()
    if not c.get("enabled"):
        log("✗ profile 里 podcast 未启用")
        return 2

    final_md = article_dir / "定稿.md"
    if not final_md.is_file():
        log(f"✗ 找不到 {final_md}")
        return 2

    # 🔴 2026-08-16 预生成短路（审计 P4）：`pipeline.py podcast-pregen` 允许在
    #    定稿冻结点就后台生成音频（NotebookLM 实测 ~18 分钟，是 finalize 串行链
    #    里最大的阻塞项，89 篇它一失败官网同步跟着晚了 5 小时）。finalize 到点
    #    再调本函数时，只要「音频在 + 状态已 drafted/dispatched + source_digest
    #    与当前定稿一致」就直接取件：不重进 NotebookLM，只把预生成时还拿不到的
    #    永久链接补进 sidecar/shownotes。定稿在预生成后又被改过（digest 漂移）
    #    则照常走完整生成——短路永远不会拿旧音频配新定稿。
    out_dir = distribute.channel_dir(article_dir, "podcast")
    mp3 = out_dir / "audio.mp3"
    if (
        mp3.is_file()
        and mp3.with_suffix(".json").is_file()
        and distribute.get_status(article_dir, "podcast") in {"drafted", "dispatched"}
        and generation_is_fresh(article_dir, c)
    ):
        log("✓ 已有与当前定稿一致的预生成音频，跳过生成（取件模式）")
        refresh_sidecar_url(article_dir, mp3,
                            smax=int(c.get("shownotes_max") or 800))
        return 0

    prompt_path = Path(str(c.get("focus_prompt") or "")).expanduser()
    if not str(prompt_path) or not prompt_path.is_file():
        log("✗ profile 的 podcast.focus_prompt 未配置或文件不存在")
        log("  主持风格提示词决定节目调性，不能缺——照搬晨报的播报体会很怪")
        return 2
    focus = prompt_path.read_text(encoding="utf-8").strip()

    title = distribute.read_final_title(article_dir)
    if not title:
        log("✗ 读不到定稿标题")
        return 2

    out_dir = distribute.channel_dir(article_dir, "podcast")
    out_dir.mkdir(parents=True, exist_ok=True)
    m4a = out_dir / "_raw.m4a"
    mp3 = out_dir / "audio.mp3"

    log(f"文章：{title}")
    log(f"提示词：{prompt_path.name}（{len(focus)} 字）")

    # 登录态失效若不在创建前拦下，create 可能侥幸成功、后续 status 查询却连续
    # 失败 30 分钟，最后只留下一个已完成但没下载的孤儿 artifact。先做只读探针，
    # 让人工边界停在真实的认证动作，而不是让作者去 NotebookLM 手动生成音频。
    try:
        run_nlm("notebook", "list", "--json", want_json=True, timeout=60)
    except Exception as e:                                  # noqa: BLE001
        msg = str(e)
        if "Authentication expired" in msg or "nlm login" in msg or "认证" in msg:
            # 🔴 2026-08-14 第 89 篇实跑修的假失败：这里原本自动登录成功后走
            #    `pass`，**没有 return/continue**，于是直接掉进下面那行
            #    「连接预检失败」并 return 1 —— 浏览器授权明明成功了（拿到 38 个
            #    cookie），流程却报错退出，还提示作者「请运行 nlm login」。
            #    实测：独立跑 `nlm notebook list` 是通的，重跑 finalize 即成功。
            #    登录成功就必须继续往下走，不能再落进失败分支。
            if _try_auto_login():
                log("  ✓ 凭证已刷新，继续生成流程")
            else:
                log("✗ NotebookLM 登录态已失效，请先运行 `nlm login`")
                log("  这一步只恢复真实浏览器授权；音频生成、下载、转码和发布仍由脚本完成")
                return 3
        else:
            log(f"✗ NotebookLM 连接预检失败：{msg[:240]}")
            return 1

    # 1. notebook
    nb = _extract_id(
        _retry("create notebook", lambda: run_nlm(
            "notebook", "create", f"深聊 {title[:30]}", "--json", want_json=True, timeout=90)),
        "id", "notebook_id")
    if not nb:
        log("✗ 没拿到 notebook id")
        return 1
    log(f"notebook: {nb}")

    try:
        # 2. 喂裸 markdown。**不做二次提炼**——晨报验证过，提炼一遍反而丢细节。
        # 只喂作者正文。微信信息图与双音频卡属于机器装配；把它们送入模型会
        # 让占位提示进入节目素材，并导致纯样式改动误触发整集重生成。
        source_text = distribute.source_text_for_channel(article_dir, "podcast")
        with tempfile.TemporaryDirectory(prefix="sansheng-podcast-") as tmp:
            source_md = Path(tmp) / "article.md"
            source_md.write_text(source_text, encoding="utf-8")
            _retry("source add", lambda: run_nlm(
                "source", "add", nb, "--file", str(source_md),
                "--wait", "--wait-timeout", "240", timeout=300))

        # 3. 建音频
        art = _extract_id(
            _retry("audio create", lambda: run_nlm(
                "audio", "create", nb,
                "--format", "deep_dive",
                "--length", str(c.get("length") or "default"),
                "--language", str(c.get("language") or "zh"),
                "--focus", focus,
                "--confirm", "--json", want_json=True, timeout=180)),
            "artifact_id", "id")
        if not art:
            log("✗ 没拿到 artifact id")
            return 1
        log(f"artifact: {art}")

        # 4. 轮询
        log(f"轮询生成状态（最长 {POLL_TIMEOUT // 60} 分钟）…")
        deadline = time.time() + POLL_TIMEOUT
        status = "unknown"
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            try:
                out = run_nlm("studio", "status", nb, "--json", want_json=True, timeout=90)
                items = out if isinstance(out, list) else (out.get("artifacts") or [])
                target = next((a for a in items
                               if a.get("id") == art or a.get("artifact_id") == art), None)
                status = (target or {}).get("status", status)
                log(f"  status={status}")
                if status == "completed":
                    break
                if status == "failed":
                    log(f"✗ NotebookLM 报 failed：https://notebooklm.google.com/notebook/{nb}")
                    return 1
            except Exception as e:                   # noqa: BLE001
                msg = str(e)
                if "Authentication expired" in msg or "nlm login" in msg or "认证" in msg:
                    if _try_auto_login():
                        continue  # 登录态已恢复，继续轮询
                    log("✗ 生成期间 NotebookLM 登录态失效，请运行 `nlm login` 后续接")
                    log(f"  notebook 保留供排障：https://notebooklm.google.com/notebook/{nb}")
                    keep_notebook = True
                    return 3
                log(f"  查询出错（继续轮询）：{msg[:150]}")
        else:
            log(f"✗ 超时（{POLL_TIMEOUT // 60} 分钟）未完成，最后状态 {status}")
            log(f"  手动查看：https://notebooklm.google.com/notebook/{nb}")
            return 1

        # 5. 下载。status=completed 不等于 CDN 已同步好，晨报实测要等好几分钟。
        for i in range(1, DOWNLOAD_RETRIES + 1):
            try:
                run_nlm("download", "audio", nb, "-o", str(m4a), "--no-progress", timeout=300)
                if m4a.is_file() and m4a.stat().st_size > MIN_AUDIO_BYTES:
                    break
                log(f"  文件过小/不存在 ({i}/{DOWNLOAD_RETRIES})")
            except Exception as e:                   # noqa: BLE001
                log(f"  下载失败 {i}/{DOWNLOAD_RETRIES}: {str(e)[:150]}")
            if i < DOWNLOAD_RETRIES:
                log(f"  等 {DOWNLOAD_INTERVAL}s…")
                time.sleep(DOWNLOAD_INTERVAL)
        else:
            log("✗ 下载持续失败")
            return 1

        # 6. 转码
        ff = shutil.which("ffmpeg")
        if not ff:
            log("✗ 找不到 ffmpeg")
            return 1
        candidate = out_dir / "audio.next.mp3"
        candidate.unlink(missing_ok=True)
        try:
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(m4a),
                            "-codec:a", "libmp3lame", "-b:a", "96k", str(candidate)],
                           check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            candidate.unlink(missing_ok=True)
            log(f"✗ ffmpeg 转码失败，已保留原 audio.mp3：{str(exc)[:200]}")
            return 1
        valid, reason = validate_audio(candidate)
        if not valid:
            candidate.unlink(missing_ok=True)
            log(f"✗ 候选音频验证失败，已保留原 audio.mp3：{reason}")
            return 1
        candidate.replace(mp3)
        m4a.unlink(missing_ok=True)
        log(f"✓ {mp3}  ({mp3.stat().st_size // 1024} KB)")

        # 7. sidecar
        write_sidecar(article_dir, mp3, title, c)
        distribute.set_status(article_dir, "podcast", "drafted",
                              source_digest=distribute.source_digest(
                                  article_dir, "podcast"),
                              generation_digest=generation_digest(article_dir, c),
                              audio_sha256=hashlib.sha256(mp3.read_bytes()).hexdigest())
        return 0
    finally:
        if not keep_notebook:
            try:
                run_nlm("notebook", "delete", nb, "--confirm", timeout=90)
                log("已清理 notebook")
            except Exception as e:                   # noqa: BLE001
                log(f"（清理 notebook 失败，可忽略：{str(e)[:120]}）")


def strip_category_prefix(title: str, prefixes: list[str]) -> str:
    """去掉文章标题自带的分类前缀，避免单集标题出现两道竖线。

    标题常写成「洞察 | 正文标题」，播客再套一层「深聊 | 」就成了
    「深聊 | 洞察 | 正文标题」——在播客 App 的列表里又长又难看。

    🔴 只认 profile 里**显式列出**的分类词，不做任何模式猜测。
    先前试过「吃掉分隔符前 6 字以内的第一段」这种启发式，当场就把
    「这届年轻人 | 到底在焦虑什么」切成了「到底在焦虑什么」——那半句是
    标题本身。标题多两个字只是不好看，切错了是事故，所以宁可不切：
    没配 `episode_title_strip_prefixes` 就原样保留。
    """
    for p in prefixes:
        p = str(p).strip()
        if not p:
            continue
        for sep in ("|", "｜"):
            head = f"{p} {sep} "
            if title.startswith(head):
                return title[len(head):].lstrip()
            head = f"{p}{sep}"
            if title.startswith(head):
                return title[len(head):].lstrip()
    return title


def write_sidecar(article_dir: Path, mp3: Path, title: str, c: dict) -> Path:
    """写 feed 生成器要读的 sidecar。"""
    prefix = str(c.get("episode_title_prefix") or "深聊 | ")
    strip_list = c.get("episode_title_strip_prefixes") or []
    ep_title = f"{prefix}{strip_category_prefix(title, strip_list)}"
    tmax = int(c.get("episode_title_max") or 60)
    if len(ep_title) > tmax:
        ep_title = ep_title[:tmax - 1] + "…"

    meta = distribute.read_article_meta(article_dir)
    desc = str(meta.get("digest") or "").strip()
    url = distribute.read_wechat_url(article_dir)
    if url:
        desc = f"{desc}\n\n原文：{url}".strip()
    smax = int(c.get("shownotes_max") or 800)

    side = mp3.with_suffix(".json")
    side.write_text(json.dumps({
        "title": ep_title,
        "description": desc[:smax],
        "pub_date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kind": "article",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"✓ sidecar: {side.name}")

    shownotes = mp3.parent / "shownotes.md"
    body = f"# {ep_title}\n\n{desc}\n"
    if not shownotes.exists():
        shownotes.write_text(body, encoding="utf-8")
    elif shownotes.read_text(encoding="utf-8") != body:
        # 不覆盖：这份可能被人改过，手写的 shownotes 比自动生成的值钱。
        # 但也不能默默留着——重跑之后它会与本集实际标题/摘要不一致，
        # 而 shownotes 是**读者在播客 App 里真正看到的那段文字**。
        log(f"⚠ {shownotes.name} 已存在且与本次内容不一致，未覆盖")
        log(f"  若不是你手动改的，删掉它重跑即可刷新（当前标题应为：{ep_title}）")
    return side


def refresh_sidecar_url(article_dir: Path, mp3: Path, *, smax: int = 800) -> None:
    """把预生成时还不存在的永久链接补进 sidecar / shownotes（取件模式专用）。

    预生成发生在 release-to-draft 之前，`write_sidecar` 那时拿不到 wechat_url，
    「原文：URL」这行就缺。finalize 取件时链接已登记，在这里补上。
    shownotes 只在**仍是机器生成形态**（与旧 sidecar 逐字一致）时同步——
    手改过的不动，与 write_sidecar 的不覆盖设计同构。
    """
    side = mp3.with_suffix(".json")
    if not side.is_file():
        return
    url = distribute.read_wechat_url(article_dir)
    if not url:
        return
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    desc = str(data.get("description") or "")
    if url in desc:
        return
    old_title = str(data.get("title") or "")
    old_body = f"# {old_title}\n\n{desc}\n"
    new_desc = f"{desc}\n\n原文：{url}".strip()[:smax]
    data["description"] = new_desc
    side.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    log("✓ sidecar 补写原文链接")
    shownotes = mp3.parent / "shownotes.md"
    if shownotes.is_file():
        if shownotes.read_text(encoding="utf-8") == old_body:
            shownotes.write_text(f"# {old_title}\n\n{new_desc}\n", encoding="utf-8")
            log("✓ shownotes 补写原文链接")
        else:
            log("⚠ shownotes 已被手改，未自动补原文链接")


# ===== publish =====

def cmd_publish(article_dir: Path, confirm: bool = False) -> int:
    c = cfg()
    out_dir = distribute.channel_dir(article_dir, "podcast")
    mp3 = out_dir / "audio.mp3"
    side = mp3.with_suffix(".json")

    if not mp3.is_file() or not side.is_file():
        log(f"✗ 缺 audio.mp3 或 sidecar，先跑 generate（{out_dir}）")
        return 2
    if not generation_is_fresh(article_dir, c):
        log("✗ 播客音频与当前定稿/标题/提示词/生成参数不一致；请先重跑 generate")
        return 2

    host = str(c.get("remote_host") or "").strip()
    remote_dir = str(c.get("remote_episodes_dir") or "").strip()
    rebuild = str(c.get("feed_rebuild_command") or "").strip()
    if not (host and remote_dir and rebuild):
        log("✗ profile 缺 podcast.remote_host / remote_episodes_dir / feed_rebuild_command")
        return 2

    title = distribute.read_final_title(article_dir)
    stem = f"{datetime.now():%Y-%m-%d}-{_safe_stem(title)}"
    log(f"远端文件名：{stem}.mp3 (+ .json)")

    if not confirm:
        log("dry-run：加 --confirm 才真正上传并重建 feed（这一步对外可见）")
        return 0

    scp = shutil.which("scp")
    ssh = shutil.which("ssh")
    if not (scp and ssh):
        log("✗ 找不到 scp/ssh")
        return 2

    # 🔴 先传 sidecar 再传 mp3。反过来的话，两次传输之间若正好触发 feed 重建，
    # mp3 会被当成「无 sidecar 且文件名非纯日期」而静默跳过。
    for src, dst in ((side, f"{stem}.json"), (mp3, f"{stem}.mp3")):
        r = subprocess.run([scp, str(src), f"{host}:{remote_dir}/{dst}"])
        if r.returncode != 0:
            log(f"✗ 上传 {dst} 失败")
            return 1
        log(f"  ✓ {dst}")

    r = subprocess.run([ssh, host, rebuild])
    if r.returncode != 0:
        log("✗ feed 重建失败（音频已上传，修好后重跑本命令即可）")
        return 1

    distribute._write_json(out_dir / distribute.RECEIPT_FILE, {
        "channel": "podcast",
        "mode": "rss",
        "remote_stem": stem,
        "published_at": distribute._now(),
        "source_digest": distribute.source_digest(article_dir, "podcast"),
        "generation_digest": generation_digest(article_dir, c),
        "audio_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
        "note": "已上传并重建 feed；平台侧 1-12 小时内抓取",
    })
    distribute.set_status(
        article_dir, "podcast", "dispatched",
        source_digest=distribute.source_digest(article_dir, "podcast"),
        generation_digest=generation_digest(article_dir, c),
        audio_sha256=hashlib.sha256(mp3.read_bytes()).hexdigest(),
    )
    log("✓ 已上线，平台 1-12 小时内自动抓取（不需要手动操作）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="podcast_episode.py", description="文章 → 播客单集")
    ap.add_argument("--dir", default=".", help="文章目录")

    # `--dir` 子命令前后都能写。子命令那份的默认值必须是 SUPPRESS：
    # argparse 的子解析器会把自己的默认值写进同一个 namespace，
    # 用普通默认值会让 `--dir X generate` 里的 X 被子命令的默认值悄悄覆盖掉
    # ——参数被无声吃掉，然后在当前目录找不到定稿，报的错还指不到真原因。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=argparse.SUPPRESS, help="文章目录")

    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", parents=[common],
                       help="本机生成音频 + sidecar（10-20 分钟）")
    g.add_argument("--keep-notebook", action="store_true", help="不删 NotebookLM notebook（排障用）")
    p = sub.add_parser("publish", parents=[common], help="上传到 feed 主机并重建 feed")
    p.add_argument("--confirm", action="store_true")

    a = ap.parse_args(argv)
    d = Path(a.dir).resolve()
    if not d.is_dir():
        log(f"✗ 目录不存在：{d}")
        return 2
    if a.cmd == "generate":
        return cmd_generate(d, a.keep_notebook)
    return cmd_publish(d, a.confirm)


if __name__ == "__main__":
    sys.exit(main())
