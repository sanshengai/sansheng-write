#!/usr/bin/env python3
"""
🎙️ 音频转写工具（口述想法 → 写作素材）
========================================================
作者口述的选题思考（手机/电脑录音）转成文字素材，供后续大纲与写作阶段消化。
转写稿是**素材不是逐字稿**：允许模型按语义分段、少量清理语气词；
同音字/专名小错由写作阶段按上下文语义纠正，不在本脚本层追求零错字。

引擎（按可用性自动选择，--engine 可强制）：
  gemini   Google 多模态直接理解音频（质量高、秒级；需 GOOGLE_API_KEY）
           key 按前缀自动分流端点，与 gen_img.py 同一约定：
             AIza... → AI Studio    AQ.... → Vertex Express（需 GOOGLE_VERTEX_PROJECT）
  whisper  本地 faster-whisper（离线兜底；需 pip install faster-whisper）

用法：
  python transcribe_audio.py 素材/录音.m4a            # → 素材/录音.转写.md
  python transcribe_audio.py 素材/                    # 目录内音频批量转写（已有转写稿跳过）
  python transcribe_audio.py 录音.mp3 --out 思考.md   # 指定输出
  python transcribe_audio.py 录音.mp3 --engine whisper --force

集成位置：SKILL.md「素材自动读取」——素材目录出现音频先转写再读；细则 references/transcribe.md。
"""

import argparse
import base64
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Windows GBK 控制台/管道下 print 中文会 UnicodeEncodeError，强制 UTF-8
# （与 compress_images.py / prep_writing.py 同源防护）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_config as pc

AI_STUDIO = ("https://generativelanguage.googleapis.com/v1beta/"
             "models/{model}:generateContent")
VERTEX_EXPRESS = ("https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
                  "publishers/google/models/{model}:generateContent")

# 覆盖用 env：SANSHENG_WRITE_TRANSCRIBE_MODEL（默认取当前代 flash，够用且几乎不要钱）
DEFAULT_GEMINI_MODEL = "gemini-3.7-flash"

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".wma", ".amr", ".opus"}

# 单请求音频上限：规整成 16kHz 单声道 48kbps 后，25 分钟 ≈ 9MB，
# base64 后 ≈ 12MB，稳稳低于端点 20MB 请求体上限。超过就切片逐段转写再拼接。
SEGMENT_SECONDS = 1500

_MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
         ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg",
         ".opus": "audio/ogg"}

PROMPT = (
    "把这段录音转写成简体中文文本。要求：\n"
    "1) 只输出转写正文，不加任何前后缀、说明、时间戳或格式标记；\n"
    "2) 按语义分自然段；\n"
    "3) 中英夹杂处保留英文原词，产品名/专有名词照录；\n"
    "4) 忠实原话，允许少量清理无意义语气词（嗯、啊），但不改写、不概括句意；\n"
    "5) 听不清或吃不准的词标〔听不清〕，绝不靠猜补写内容——静音段就是没有内容。"
)

_RETRY_MAX_ATTEMPTS = 4
_RETRY_BASE_SECONDS = 4


def _redact(text: str) -> str:
    """key 拼在 URL query 里，异常串会带出来——外发前一律脱敏。"""
    return re.sub(r"(key=)[^&\s)\"']+", r"\1***", str(text))


def _gemini_endpoint(model: str, key: str) -> str:
    """按 key 前缀分流端点（与 gen_img.py 同一约定）。"""
    if key.startswith("AQ."):
        project = pc.load_secret(
            "GOOGLE_VERTEX_PROJECT",
            hint="AQ. 开头的 Vertex Express key 必须同时给 GCP 项目 ID（项目级端点）。",
        )
        return VERTEX_EXPRESS.format(project=project, model=model)
    return AI_STUDIO.format(model=model)


def _ffmpeg_or_die() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("[transcribe] 找不到 ffmpeg。转写前需要它把录音规整成低码率单声道，请先安装并加入 PATH。")
    return exe


def probe_duration(path: Path) -> float:
    """ffprobe 拿时长（秒）；拿不到返回 0（按不切片处理）。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def normalize_audio(src: Path, workdir: Path) -> list[Path]:
    """规整为 16kHz 单声道 48kbps mp3；超长自动切片。返回待转写分段列表（有序）。"""
    ffmpeg = _ffmpeg_or_die()
    norm = workdir / "norm.mp3"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-b:a", "48k", str(norm)],
        check=True, timeout=600,
    )
    if probe_duration(norm) <= SEGMENT_SECONDS:
        return [norm]
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(norm),
         "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
         "-c", "copy", str(workdir / "seg_%03d.mp3")],
        check=True, timeout=600,
    )
    return sorted(workdir.glob("seg_*.mp3"))


# ---------------------------------------------------------------- gemini 引擎

def _gemini_call(url: str, key: str, body: dict) -> dict:
    # key 走 x-goog-api-key 请求头不进 URL（与 gen_img.py 同源：不落 argv、不落异常串）
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    last_err = ""
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=280) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last_err = _redact(e.read().decode(errors="replace")[:500])
            retriable = e.code in (429, 500, 503)
            if retriable and attempt < _RETRY_MAX_ATTEMPTS:
                wait = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                print(f"  HTTP {e.code}，{wait}s 后重试（{attempt}/{_RETRY_MAX_ATTEMPTS - 1}）",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"[transcribe] Gemini 调用失败 HTTP {e.code}：{last_err}")
    sys.exit(f"[transcribe] Gemini 重试耗尽：{last_err}")


def transcribe_gemini(segments: list[Path], model: str) -> str:
    key = pc.load_secret(
        "GOOGLE_API_KEY",
        hint="AI Studio 的 AIza... 或 Vertex Express 的 AQ... 都行，脚本按前缀自动分流端点；"
             "没有 Google key 可 --engine whisper 走本地转写。",
    )
    url = _gemini_endpoint(model, key)
    parts_out = []
    for i, seg in enumerate(segments, 1):
        if len(segments) > 1:
            print(f"  分段 {i}/{len(segments)} …", file=sys.stderr)
        b64 = base64.b64encode(seg.read_bytes()).decode()
        resp = _gemini_call(url, key, {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": "audio/mpeg", "data": b64}},
                {"text": PROMPT},
            ]}],
        })
        cands = resp.get("candidates") or []
        parts = (cands[0].get("content", {}) or {}).get("parts", []) if cands else []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            sys.exit("[transcribe] Gemini 返回为空（candidates 无文本），原始响应键："
                     f"{sorted(resp.keys())}")
        parts_out.append(text)
    return "\n\n".join(parts_out)


# ---------------------------------------------------------------- whisper 引擎

def transcribe_whisper(segments: list[Path], language: str) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("[transcribe] faster-whisper 未安装。请：pip install faster-whisper；"
                 "或配置 GOOGLE_API_KEY 走 gemini 引擎。")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    chunks = []
    for seg in segments:
        segs, _info = model.transcribe(str(seg), language=language,
                                       vad_filter=True, word_timestamps=False)
        prev_end = None
        for s in segs:
            # 长停顿（>1.5s）当作自然段边界，转写稿不至于糊成一整块
            gap = "\n\n" if (prev_end is not None and s.start - prev_end > 1.5) else ""
            chunks.append(gap + s.text.strip())
            prev_end = s.end
    return "".join(
        c if c.startswith("\n") else (" " + c) for c in chunks
    ).strip()


# ---------------------------------------------------------------- 主流程

def pick_engine(requested: str) -> str:
    if requested != "auto":
        return requested
    if pc.load_secret("GOOGLE_API_KEY", required=False):
        return "gemini"
    try:
        import faster_whisper  # noqa: F401
        return "whisper"
    except ImportError:
        sys.exit("[transcribe] 两个引擎都不可用：没配 GOOGLE_API_KEY，也没装 faster-whisper。\n"
                 "          任配其一即可：cp .env.example .env 填 GOOGLE_API_KEY，"
                 "或 pip install faster-whisper。")


def output_path_for(audio: Path, out: str | None) -> Path:
    return Path(out).resolve() if out else audio.with_name(audio.stem + ".转写.md")


def transcribe_one(audio: Path, engine: str, model: str, language: str,
                   out: str | None, force: bool) -> Path | None:
    target = output_path_for(audio, out)
    if target.exists() and not force:
        print(f"SKIP  {audio.name} -- 已有 {target.name}（--force 重跑）")
        return None
    duration = probe_duration(audio)
    workdir = Path(tempfile.mkdtemp(prefix="transcribe_"))
    try:
        segments = normalize_audio(audio, workdir)
        t0 = time.time()
        if engine == "gemini":
            model = model or os.environ.get("SANSHENG_WRITE_TRANSCRIBE_MODEL",
                                            "").strip() or DEFAULT_GEMINI_MODEL
            text = transcribe_gemini(segments, model)
            engine_label = f"gemini/{model}"
        else:
            text = transcribe_whisper(segments, language)
            engine_label = "faster-whisper/small"
        elapsed = time.time() - t0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    header = (f"<!-- 转写素材 · 源文件 {audio.name}"
              + (f" · 时长 {duration:.0f}s" if duration else "")
              + f" · 引擎 {engine_label}"
              + f" · {_dt.date.today().isoformat()} -->\n\n")
    target.write_text(header + text + "\n", encoding="utf-8")
    print(f"OK    {audio.name} → {target}  （{elapsed:.0f}s，{len(text)} 字）")
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description="口述音频 → 写作素材转写稿")
    ap.add_argument("input", help="音频文件，或含音频的目录（如 素材/）")
    ap.add_argument("--out", help="输出路径（仅单文件时有效；默认 <同名>.转写.md）")
    ap.add_argument("--engine", choices=["auto", "gemini", "whisper"], default="auto")
    ap.add_argument("--model", help=f"gemini 引擎模型名（默认 {DEFAULT_GEMINI_MODEL}，"
                                    "也可用 SANSHENG_WRITE_TRANSCRIBE_MODEL 覆盖）")
    ap.add_argument("--lang", default="zh", help="whisper 引擎语言（默认 zh）")
    ap.add_argument("--force", action="store_true", help="已有转写稿也重跑")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if src.is_dir():
        audios = sorted(p for p in src.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if not audios:
            sys.exit(f"[transcribe] 目录里没有音频文件：{src}")
        if args.out:
            sys.exit("[transcribe] --out 只支持单文件输入。")
    elif src.is_file():
        if src.suffix.lower() not in AUDIO_EXTS:
            sys.exit(f"[transcribe] 不认识的音频格式 {src.suffix}（支持：{' '.join(sorted(AUDIO_EXTS))}）")
        audios = [src]
    else:
        sys.exit(f"[transcribe] 找不到输入：{src}")

    engine = pick_engine(args.engine)
    done = [transcribe_one(a, engine, args.model, args.lang, args.out, args.force)
            for a in audios]
    written = [p for p in done if p]
    print(f"\n完成 {len(written)}/{len(audios)}，引擎 {engine}。")


if __name__ == "__main__":
    main()
