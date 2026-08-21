#!/usr/bin/env python3
"""
🎵 公众号文章配乐生成器 (Article BGM Generator · Lyria 3 版 V2)
================================================
为微信公众号文章生成 ~2-3 分钟【中文人声主题曲】（舒缓 · 空灵 · 柔美）。

引擎：Google Lyria 3 Pro（`lyria-3-pro-preview`，自动写词），走 Vertex interactions API。

🔴 端点/凭证三件事（错任一件都会得到误导性报错，2026-08-21 实测）：
    ① 端点是 `POST /v1beta1/projects/{P}/locations/global/interactions`，
       **不是** `publishers/google/models/{M}:predict`（那是旧版音乐模型的端点形态）。
       用错 → 404 "not found or your project does not have access"，读起来像没白名单，
       其实 public preview 无需 allowlist。社区里一大片人卡在这个误判上。
    ② 只认 **OAuth2**（gcloud ADC），传 API Key → 401 "API keys are not supported"。
    ③ project 必须是**当前 ADC 账号自己有权限**的那个，否则 403
       `Permission 'aiplatform.interactions.create' denied`。
    计费走 Cloud，$300 赠金可覆盖（$0.08/首）；走 AI Studio 端点则不吃赠金。

🔴 V2 架构变化：
    **文章提炼不调任何模型**——由【宿主 Agent 在 autopilot 里提炼】诗意意象，作为参数传入：
      --theme-brief  "虚无缥缈的诗意主旨叙事（一句，方法A 据此自动写词）"
      --imagery      "柔美画面词,逗号分隔,如 晨光,薄雾,潮汐"
      --song-name    "诗意短歌名"
      --style        ethereal_folk|ambient_vocal|ambient_piano|cinematic_vocal
      --gender       female|male（默认按序号奇偶交替）
    脚本退化为纯执行器：拼 V2 空灵 prompt → Lyria 3 写词+生成 → 落地 → 封面 → 插卡。
    未传 --theme-brief 时用 frontmatter 规则兜底（音色通常不如 Agent 提炼空灵，会警告）。

🔴 V2 空灵升级（基于 Suno/MiniMax 时代实测研究，Lyria 3 沿用同一套空灵体系）：
    ① 最大杠杆=主旨叙事写成诗意意象（自动写词模式下歌词决定音色空灵度）
    ② 空灵专用词 aria/echoing/resonant/distant
    ③ 配器极简（2-3 件 + minimal/sparse backing，凸显空气感）
    ④ 物理声学质感 airy high frequencies/long reverb tail/shimmering overtones
    ⑤ 人声呼吸感 breathy/intimate/gentle vibrato/sighing（去机械感）
    ⑥ BPM 降到 55-64（空灵冥想区）

使用方法:
    # autopilot 主路径（宿主 Agent 提炼后传参）：
    python generate_article_bgm.py "<数据目录>/54-睡眠..." \\
        --theme-brief "夜深时大脑替你值一趟温柔的夜班" \\
        --imagery "薄雾,潮汐,微光" --song-name "潮汐入梦" --style ambient_piano
    # 手动兜底（无提炼，用 frontmatter）：
    python generate_article_bgm.py "<数据目录>/54-睡眠..."

前置:
    需已装 gcloud 并完成 `gcloud auth application-default login`（本脚本用 ADC 取 OAuth token）。
    project 取 GOOGLE_CLOUD_PROJECT 或 `gcloud config get-value project`。
    取不到凭证时非零退出（exit 2）阻断发布链——BGM 是发布硬门。
    封面（可选，失败不阻塞）另需 GOOGLE_API_KEY（Vertex Express，给 gen_img.py）。

历史:
    2026-04 Lyria 3 Pro（多模态图文）→ 2026-05-29 因 Vertex 404 误判为「白名单不开放」而废弃 →
    2026-06-18 复活切 MiniMax → 同日晚 V2 去 Gemini、Claude 提炼传参 + 空灵升级 →
    2026-08-20 MiniMax 音乐 API 对非历史付费用户关停（410/2153）→
    2026-08-21 查明当年的 404 实为端点形态用错（应走 interactions 而非 :predict），
              改回 Lyria 3 Pro 并实测跑通中文女声整首歌。
"""

import os
import sys
import argparse
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# Windows GBK 控制台下 print 含 emoji/全角会 UnicodeEncodeError（成功路径也会崩、退出码非0）。
# 强制 stdout/stderr UTF-8（与 format_layout.py / normalize_cjk_punctuation.py 同源防护，
# 2026-06-25 补：59 号 BGM 生成在 cp936 控制台 emoji print 崩，须加这段）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


# ============================================================
# 🎵 音乐风格偏好配置（V2：4 种舒缓系，BPM 降 55-64，配器收窄 2-3 件）
# ============================================================
# 硬约束：所有 BGM 必须【舒缓·空灵·环境浮声/氛围钢琴】，绝不欢快、无强节奏感。
# V2 收窄乐器为 2-3 件核心（配器极简凸显空气感）；空灵专用词与物理声学质感统一在 build_music_prompt 公共段加。
STYLE_POOL = {
    "ethereal_folk": {
        "name": "空灵民谣", "bpm": "60",
        "description": "ethereal and dreamy Chinese folk, acoustic, spacious and airy",
        "instruments": "softly fingerpicked acoustic guitar and ambient reverb piano",
        "best_for": ["深度思考", "观点输出", "人物说理"],
    },
    "ambient_vocal": {
        "name": "环境浮声", "bpm": "55",
        "description": "ambient and floating, a dreamy environmental soundscape, distant and otherworldly",
        "instruments": "warm ambient pads and a distant reverb piano with ethereal vocal layers",
        "best_for": ["科技探索", "未来想象", "AI工具对比", "前沿趋势"],
    },
    "ambient_piano": {
        "name": "氛围钢琴", "bpm": "58",
        "description": "ambient piano-driven, contemplative, minimalist and weightless",
        "instruments": "soft felt piano and a warm ambient pad over a gentle evolving drone",
        "best_for": ["哲思文章", "行业反思", "年度盘点", "收尾感悟"],
    },
    "cinematic_vocal": {
        "name": "影视人声", "bpm": "64",
        "description": "calm and intimate cinematic vocal, tender and emotional, never epic or aggressive",
        "instruments": "soft sustained strings and piano with gentle choir-like backing pads",
        "best_for": ["长文特稿", "行业深度分析", "重磅专题", "年终总结"],
    },
}

# 人声性别交替（防审美疲劳，奇偶交替）；V2 加呼吸感词去机械感
VOCAL_STYLES = {
    "female": {
        "description": "an ethereal female voice, breathy and crystal-clear, airy and floating with gentle vibrato, "
                       "soft and intimate, singing softly in Mandarin Chinese",
        "label": "空灵女声",
    },
    "male": {
        "description": "a warm male voice, breathy and intimate, gentle and unhurried with a soft sighing delivery, "
                       "tender and comforting, singing softly in Mandarin Chinese",
        "label": "温暖男声",
    },
}

# 🔴 Lyria 3 走 Vertex 的 interactions API，**不是** publishers/models/{M}:predict。
#    用错端点会返回 404 "not found or your project does not have access"，措辞极具误导性
#    （会让人以为要申请白名单；实际 public preview 无需 allowlist，纯粹是端点形态错）。
#    判据：404=端点形态错 / 401=该用 OAuth 而非 API key / 403 denied=project 选错。
VERTEX_INTERACTIONS = ("https://aiplatform.googleapis.com/v1beta1"
                       "/projects/{project}/locations/global/interactions")
DEFAULT_LYRIA_MODEL = "lyria-3-pro-preview"   # 🔴 固定用这一个，别换：其余 Google 音乐模型要么无人声要么只出 30s


def load_env():
    """保留函数名兼容既有调用点。

    Lyria 3 不使用 API Key：interactions API 只认 OAuth2
    （传 api key 会得 401 "API keys are not supported by this API"）。
    凭证改由 gcloud ADC 提供，见 gcloud_access_token() / vertex_project()。
    """
    return


def _run(cmd: list) -> str:
    """跑一条命令拿 stdout（失败返回空串，不抛）。"""
    import subprocess
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                             shell=(os.name == "nt"))
        if out.returncode != 0:
            return ""
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def gcloud_access_token(cli_value: str = "") -> str:
    """OAuth2 access token：CLI > GOOGLE_OAUTH_TOKEN > gcloud ADC。

    读不到返回空串，由 main 以非零退出阻断新文章发布链（BGM 是发布硬门）。
    """
    if cli_value:
        return cli_value
    env_tok = os.environ.get("GOOGLE_OAUTH_TOKEN", "").strip()
    if env_tok:
        return env_tok
    return _run(["gcloud", "auth", "application-default", "print-access-token"])


def vertex_project(cli_value: str = "") -> str:
    """Vertex project：CLI > GOOGLE_CLOUD_PROJECT > gcloud 当前配置。

    🔴 必须是**当前 ADC 账号自己有权限**的 project。拿 A 账号的 token 去打 B 账号的
    project 会得 403 `Permission 'aiplatform.interactions.create' denied`——
    本仓 .env 里那个 GOOGLE_VERTEX_PROJECT 是给 gen_img.py 的 Express key 用的，
    与 ADC 账号可能不是同一个，**不要**拿来当这里的默认值。
    """
    if cli_value:
        return cli_value
    env_proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if env_proj:
        return env_proj
    return _run(["gcloud", "config", "get-value", "project"])


def resolve_model(cli_value: "str | None", meta_value: "str | None") -> str:
    """决定本次用哪个模型：CLI > article-meta.yaml > 默认，但**过滤掉历史引擎遗留值**。

    🔴 为什么要过滤：存量文章的 `article-meta.yaml` 里躺着当年的 model 值
    （MiniMax 时代的 `music-2.6-free` 等，本仓 32 篇）。那是「当初用什么生成的」
    的**历史记录**，不是「下次该用什么」的配置。

    不去批量改那些存档——改了等于伪造历史，92 篇的主题曲确实是 MiniMax 生成的。
    改成在这里挡：非 `lyria-` 前缀一律忽略并告警，让存档保持诚实、让生成用当前引擎。
    否则旧值会盖过默认模型、被原样发给 Vertex 而报错。
    """
    cli_value = str(cli_value or "").strip()
    if cli_value:
        return cli_value
    meta_value = str(meta_value or "").strip()
    if meta_value and not meta_value.startswith("lyria-"):
        print(f"⚠️  article-meta.yaml 里的 music.model 是「{meta_value}」——历史引擎遗留值，已忽略。")
        print(f"    本次使用 {DEFAULT_LYRIA_MODEL}（该 meta 保持原样，它记录的是当初的生成来源）。")
        meta_value = ""
    return meta_value or DEFAULT_LYRIA_MODEL


def find_article_file(article_dir: Path) -> Path:
    """在文章目录中查找 Markdown 原文"""
    candidates = ["定稿.md", "article.md", "README.md", "index.md"]
    for name in candidates:
        f = article_dir / name
        if f.exists():
            return f
    md_files = [p for p in article_dir.glob("*.md") if "backup" not in p.name.lower()]
    if md_files:
        return md_files[0]
    raise FileNotFoundError(f"在 {article_dir} 中未找到文章 Markdown 文件")


def determine_vocal_gender(article_dir: Path) -> str:
    """根据文章序号决定男女声交替：奇数篇女声，偶数篇男声；无法判断默认女声。"""
    dir_name = article_dir.name
    parts = dir_name.split("-", 1)
    try:
        num = int(parts[0])
        return "female" if num % 2 == 1 else "male"
    except (ValueError, IndexError):
        return "female"


def _yaml_scalar_without_comment(raw: str) -> str:
    """解析轻量 YAML 标量，并忽略引号外的行尾注释。"""
    value = raw.strip()
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        escaped = False
        for index, char in enumerate(value[1:], start=1):
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                return value[1:index].strip()
            escaped = False
        return value[1:].strip()
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def read_article_meta_music(article_dir: Path) -> dict:
    """从 article-meta.yaml 读 music.style/gender/model/song_name（轻量正则，不依赖 yaml 库）。

    让 article-meta.yaml 的 music 块也能驱动 BGM（CLI 显式参数仍优先）。无文件/无块返回 {}。
    """
    meta_file = article_dir / "article-meta.yaml"
    if not meta_file.exists():
        return {}
    text = meta_file.read_text(encoding="utf-8")
    m = re.search(r'^music:\s*\n((?:[ \t]+\S.*\n?)+)', text, re.MULTILINE)
    if not m:
        return {}
    block, result = m.group(1), {}
    for key in ("style", "gender", "model", "song_name"):
        km = re.search(rf'^\s+{key}:\s*(.*?)\s*$', block, re.MULTILINE)
        value = _yaml_scalar_without_comment(km.group(1)) if km else ""
        if value:
            result[key] = value
    return result


def fallback_brief(article_dir: Path, article_file: Path) -> str:
    """无 --theme-brief 时的规则兜底（建议优先由 Claude 提炼诗意意象传入，音色更空灵）。

    取 frontmatter digest/description，其次 title，其次首个 H1，兜底目录名。
    """
    text = article_file.read_text(encoding="utf-8")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    brief = ""
    if fm:
        for field in ("digest", "description"):
            dm = re.search(rf'^\s*{field}:\s*["\']?(.+?)["\']?\s*$', fm.group(1), re.MULTILINE)
            if dm and dm.group(1).strip():
                brief = dm.group(1).strip()
                break
        if not brief:
            tm = re.search(r'^\s*title:\s*["\']?(.+?)["\']?\s*$', fm.group(1), re.MULTILINE)
            if tm:
                brief = tm.group(1).strip()
    if not brief:
        hm = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        brief = hm.group(1).strip() if hm else article_dir.name
    return re.sub(r"[*_`#]", "", brief).strip()


def article_title(article_file: Path, article_dir: Path) -> str:
    """提取文章标题（frontmatter title > 首个 H1 > 目录名），仅用于日志/歌名兜底。"""
    text = article_file.read_text(encoding="utf-8")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    tm = re.search(r"^\s*title:\s*[\"']?(.+?)[\"']?\s*$", fm.group(1), re.MULTILINE) if fm else None
    hm = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return (tm.group(1).strip() if tm else (hm.group(1).strip() if hm else article_dir.name))


# ============================================================
# 🎼 音乐 prompt 构建（V2 空灵升级 · Lyria 3 自动写词）
# ============================================================
def build_music_prompt(theme_brief: str, imagery: list, style_key: str, gender: str) -> str:
    """构建 Lyria 3 的 V2 prompt（空灵升级 + 自动写词）。

    theme_brief：Claude 提炼的诗意主旨叙事（虚无缥缈意象一句，Lyria 3 据此自动写词）。
    imagery    ：核心意象 list（柔美画面词）。
    空灵升级：aria/echoing/resonant + 配器极简 + 物理声学(airy/reverb tail/overtones)
            + 人声呼吸感 + 低 BPM；整句叙事写法。
    🔴 必须显式要求**简体中文**歌词：Lyria 3 不加约束时默认写繁体（实测），
       公众号读者看到繁体会出戏。
    """
    style = STYLE_POOL.get(style_key, STYLE_POOL["ethereal_folk"])
    vocal = VOCAL_STYLES[gender]
    imagery_str = "、".join([x for x in imagery[:3] if x])
    img_clause = f"，意象是{imagery_str}" if imagery_str else ""
    brief = (theme_brief or "").strip()
    return (
        f"An extremely serene, ethereal and weightless Chinese Mandarin song at a slow {style['bpm']} BPM, "
        f"{style['description']}. "
        f"Vocal: {vocal['description']}, like a soft aria — resonant and gently echoing through wide open spaces. "
        f"Instrumentation: minimal and sparse, only {style['instruments']}, "
        f"with airy high frequencies, a long lush reverb tail and shimmering overtones, "
        f"plenty of space and silence between phrases. "
        f"关于「{brief}」{img_clause}。"
        f"Lyrics: write the lyrics yourself in **Simplified Chinese** (简体中文, NOT traditional), "
        f"poetic and restrained, echoing the theme above line by line. "
        f"Dreamy, floating, tranquil and healing, distant and atmospheric, spacious and weightless, "
        f"wide stereo, soft dynamics, beatless and free-flowing. "
        f"Avoid: energetic, upbeat, fast tempo, driving beat, drums, heavy bass, EDM, rock, aggressive, "
        f"festive, cheerful pop, dense or busy arrangement."
    )


# ============================================================
# 🚀 Lyria 3 音乐生成（Vertex interactions + OAuth，自动写词，同步返回内联音频）
# ============================================================
def generate_music_lyria3(prompt: str, output_path: Path, token: str, project: str,
                          model: str = DEFAULT_LYRIA_MODEL) -> "dict | None":
    """调用 Vertex Lyria 3 生成中文人声整首歌并写入 output_path（mp3）。

    与旧 MiniMax 版的关键差异：
      · 端点是 interactions（非 :predict），鉴权是 OAuth2（非 API Key）；
      · 同步返回**内联 base64 音频**（非 url），无需二次下载、不存在链接过期；
      · **同时返回歌词全文**（带段落标签与逐句时间戳）与 caption（bpm/时长/分段配器）。
        旧引擎「词不可控、看不到文本」的固有代价在这里消失了，歌词落进元数据 json。

    成功返回 extra（music_duration/lyrics/caption 等）；失败返回 None。
    """
    body = {"model": model, "input": prompt}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    url = VERTEX_INTERACTIONS.format(project=project)

    print(f"  🚀 正在调用 Vertex {model} 生成中文人声主题曲（自动写词，预计 1-3 分钟）...")
    print("  ⏳ 请耐心等待...")
    try:
        req = urllib.request.Request(
            url, data=data,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=900) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        print(f"  ❌ HTTP {e.code}: {detail}")
        if e.code == 404:
            print("  ⚠️ 404 通常不是「没白名单」，而是端点形态错——Lyria 3 必须走 interactions，"
                  "不能用 publishers/models/<model>:predict。")
        elif e.code == 401:
            print("  ⚠️ 401 = 传了 API Key。interactions 只认 OAuth2，请用 gcloud ADC token。")
        elif e.code == 403:
            print(f"  ⚠️ 403 = 当前 ADC 账号在 project「{project}」上无 aiplatform.interactions.create "
                  "权限。换成该账号自己的 project（gcloud config get-value project）。")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 请求失败：{e}")
        return None

    if isinstance(result, list):
        result = result[0] if result else {}
    if result.get("status") != "completed":
        print(f"  ❌ 未完成：status={result.get('status')} "
              f"{json.dumps(result, ensure_ascii=False)[:200]}")
        return None

    audio_b64, texts = "", []
    for out in result.get("outputs", []) or []:
        if out.get("type") == "audio":
            audio_b64 = out.get("data") or ""
        elif out.get("type") == "text":
            texts.append(out.get("text") or "")
    if not audio_b64:
        print(f"  ❌ 未返回音频：{json.dumps(result, ensure_ascii=False)[:200]}")
        return None

    import base64
    try:
        output_path.write_bytes(base64.b64decode(audio_b64))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 音频写入失败：{e}")
        return None

    # outputs 里第 1 段 text 是歌词，第 2 段是 caption（含 bpm / duration_secs / 分段配器描述）
    lyrics = texts[0] if texts else ""
    caption = texts[1] if len(texts) > 1 else ""
    duration_ms = 0
    m = re.search(r"duration_secs:\s*([\d.]+)", caption)
    if m:
        duration_ms = int(float(m.group(1)) * 1000)

    extra = {
        "music_duration": duration_ms,
        "interaction_id": result.get("id", ""),
        "lyrics": lyrics,
        "caption": caption,
    }
    print(f"  ✅ 生成成功！时长 ~{duration_ms / 1000:.0f}s，已保存：{output_path.name}")
    if lyrics:
        first = [ln for ln in lyrics.splitlines()
                 if ln.strip() and not ln.strip().startswith("[[")]
        if first:
            print(f"  📝 歌词首句：{first[0].strip()[:40]}")
    return extra


# ============================================================
# 🖼️ 主题曲封面（gen_img.py 直调 Vertex，1:1，不打水印）
# ============================================================
def generate_music_cover(song_name: str, imagery: list, output_dir: Path):
    """自动生成主题曲封面 bgm_cover.png（1:1，gen_img.py 直调 Vertex 端点；失败不阻塞）。"""
    import subprocess
    print("\n  🖼️ 正在自动生成主题曲封面图...")
    # 主题色取自 profile（默认中性 slate #2F6F8F）；缺 profile 时回退默认
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from profile_config import colors as _colors
        _primary = _colors().get("primary") or "#2F6F8F"
    except Exception:
        _primary = "#2F6F8F"
    imagery_str = ", ".join([x for x in imagery if x]) or "soft abstract horizon"
    prompt = (
        f"A cinematic, painterly album cover for a Mandarin vocal song titled \"{song_name}\". "
        f"Visual theme: {imagery_str}. "
        f"Mood: contemplative, intimate, unrushed, ambient lighting with deep warm horizon glow. "
        f"Color palette: deep cinematic dark background with a muted accent of {_primary}, "
        f"warm cream highlights, a single warm ember spark. "
        f"Style: hand-painted digital, soft edges, subtle gradients, single central focal element, "
        f"ample negative space. Must look like a legitimate album cover, not an infographic. "
        f"NO realistic people, NO text, NO watermark, NO logos, NO UI elements. 1:1 square aspect ratio."
    )
    materials_dir = output_dir / "素材"
    materials_dir.mkdir(parents=True, exist_ok=True)
    img_path = materials_dir / "bgm_cover.png"

    gen_img = Path(__file__).resolve().parent / "gen_img.py"
    if not gen_img.exists():
        print("  ⚠️ 未找到 gen_img.py，跳过封面生成。")
        return
    prompt_dir = output_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / "bgm_cover.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    cmd = [sys.executable, str(gen_img), str(prompt_file), str(img_path),
           # 🔴 不带 -preview：该模型已转正，preview 的 ID 一律 404，
           # 而 gen_img 的降级链会先撞 404 再发真请求（白打一发空枪）。
           "gemini-3.1-flash-image", "1024", "1024"]
    try:
        print("  🚀 调用 gen_img.py 生成 1:1 方形封面（Vertex 端点）...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if img_path.exists():
            print(f"  ✅ 封面图生成成功: {img_path.name}（尺寸小，不打水印）")
        else:
            print(f"  ⚠️ 封面图生成未果: {(result.stderr or result.stdout).strip()[:300]}")
    except subprocess.TimeoutExpired:
        print("  ⚠️ gen_img.py 调用超时（300s），跳过封面生成。可手动重试。")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 自动生成音乐封面出错: {e}")


def ensure_description_frontmatter(article_path: Path) -> None:
    """确保 md 顶部有 description frontmatter（防 AUDIO-CARD 块被 baoyu-md 误吞进 <meta description>）。"""
    content = article_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if fm_match and re.search(r"^\s*description\s*:", fm_match.group(1), re.MULTILINE):
        return
    title_match = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else article_path.stem
    title_clean = re.sub(r"[*_`\[\]()]", "", title).strip()
    desc = title_clean.replace('"', "'")[:120]
    if fm_match:
        existing = fm_match.group(1).rstrip()
        new_content = f"---\n{existing}\ndescription: \"{desc}\"\n---\n" + content[fm_match.end():]
    else:
        new_content = f"---\ntitle: \"{title_clean}\"\ndescription: \"{desc}\"\n---\n\n" + content
    article_path.write_text(new_content, encoding="utf-8")
    print(f"  🛡️  已为 {article_path.name} 注入 description frontmatter（防 MD→HTML head 崩坏）")


def insert_audio_card(article_path: Path, style_name: str, song_name: str):
    """把音频引导卡片（含「请将光标定位于此插入音频」占位框）追加到 定稿.md 末尾。

    铁律：AUDIO-CARD 必须位于文件最末尾；排版阶段 format_layout.py --all 会自动前置到导读栏下方。
    """
    ensure_description_frontmatter(article_path)
    content = article_path.read_text(encoding="utf-8")
    if "<!-- AUDIO-CARD-START -->" in content or "本文主题曲" in content:
        print("  ⏭️  文中已存在音频引导卡片，跳过插入。")
        return

    audio_card = f"""
<!-- AUDIO-CARD-START -->
<section style="margin: 20px 0; padding: 16px; border: 1px solid #d7e3ea; border-radius: 10px; background: #f2f7f9;">
  <section style="display: table; width: 100%; margin-bottom: 12px; border-bottom: 1px dashed #d7e3ea; padding-bottom: 8px;">
    <section style="display: table-cell; text-align: left; vertical-align: middle; font-size: 14px; color: #2F6F8F; font-weight: bold;"><span style="font-size: 16px; margin-right: 4px;">🎵</span>本文主题曲</section>
    <section style="display: table-cell; text-align: right; vertical-align: middle; font-size: 12px; color: #8a929a; font-weight: normal;">AI 生成 · {style_name}</section>
  </section>
  <!-- 预留插入位置 -->
  <p style="text-align: center; margin: 10px 0; color: #b0b6bb; font-size: 13px;">（👉 请将光标定位于此，删除本段文字并插入音频）</p>
</section>
<!-- AUDIO-CARD-END -->
"""
    article_path.write_text(content.rstrip() + "\n\n" + audio_card.strip() + "\n", encoding="utf-8")
    print(f"  ✅ 音频引导卡片已追加到 {article_path.name} 末尾（排版时自动前置到导读下方）")

    html_path = article_path.parent / "定稿.html"
    if html_path.exists():
        html_content = html_path.read_text(encoding="utf-8")
        if "<!-- AUDIO-CARD-START -->" not in html_content and "本文主题曲" not in html_content:
            print("\n  ⚠️  检测到 定稿.html 已存在但不含音频卡片。卡片已写入 定稿.md，")
            print("  ⚠️  发布前请重新走排版管线（baoyu-markdown-to-html + format_layout.py --all）。\n")


def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="🎵 公众号文章配乐生成器（Lyria 3 版 V2）— Claude 提炼诗意意象 + Lyria 3 写词生成"
    )
    parser.add_argument("article_dir", help="文章目录路径")
    parser.add_argument("--oauth-token", default=None,
                        help="Vertex OAuth2 token（默认 GOOGLE_OAUTH_TOKEN → gcloud ADC）。"
                             "🔴 不是 API Key —— interactions API 传 API Key 会 401")
    parser.add_argument("--project", default=None,
                        help="Vertex project（默认 GOOGLE_CLOUD_PROJECT → gcloud config）。"
                             "须是当前 ADC 账号自己有权限的 project，否则 403")
    parser.add_argument("--theme-brief", default=None,
                        help="🔴 Claude 提炼的诗意主旨叙事（虚无缥缈意象一句，方法A 据此自动写词）。"
                             "不传则用 frontmatter 规则兜底（音色不如诗意提炼空灵）")
    parser.add_argument("--imagery", default=None,
                        help="核心意象，逗号分隔（柔美画面词，如 晨光,薄雾,潮汐；忌抽象大词）")
    parser.add_argument("--song-name", default=None, help="诗意短歌名（默认从标题兜底）")
    parser.add_argument("--style", choices=list(STYLE_POOL.keys()), default=None,
                        help="风格（默认 article-meta.yaml music.style，再兜底 ethereal_folk）")
    parser.add_argument("--gender", choices=["male", "female"], default=None,
                        help="人声性别（默认按文章序号奇偶交替）")
    parser.add_argument("--model", default=None,
                        help=f"Lyria 模型（默认 article-meta.yaml music.model，再兜底 {DEFAULT_LYRIA_MODEL}）。"
                             "🔴 固定 lyria-3-pro-preview，除非你明确知道在做什么，否则不要传")
    parser.add_argument("--output", default=None, help="输出 MP3 文件路径")
    parser.add_argument(
        "--skip-cover",
        action="store_true",
        help="只生成主题曲与 AUDIO-CARD，不调用 Google 生成 bgm_cover.png",
    )
    args = parser.parse_args()

    # 凭证解析：CLI > 环境变量 > gcloud ADC。BGM 是发布硬门，取不到就非零退出阻断。
    args.oauth_token = gcloud_access_token(args.oauth_token or "")
    args.project = vertex_project(args.project or "")
    if not args.oauth_token:
        print("❌ 取不到 Vertex OAuth token —— 新文章的 BGM 是发布硬门，禁止静默跳过。")
        print("    请先 gcloud auth application-default login，")
        print("    或 export GOOGLE_OAUTH_TOKEN=... / 用 --oauth-token 传入。")
        print("    🔴 注意：Lyria 3 的 interactions API 不收 API Key，只认 OAuth2。")
        sys.exit(2)
    if not args.project:
        print("❌ 取不到 Vertex project。请 gcloud config set project <PROJECT>，")
        print("    或 export GOOGLE_CLOUD_PROJECT=... / 用 --project 传入。")
        print("    🔴 必须是当前 ADC 账号自己有权限的 project，否则 403 denied。")
        sys.exit(2)

    article_dir = Path(args.article_dir).resolve()
    if not article_dir.is_dir():
        print(f"❌ 错误：目录不存在: {article_dir}")
        sys.exit(1)

    print("=" * 60)
    print("🎵 公众号文章配乐生成器（Lyria 3 V2 · Claude 提炼）")
    print("=" * 60)

    # ── Step 1: 文件 + 提炼来源（优先级 CLI > article-meta.yaml > 规则兜底）──
    article_file = find_article_file(article_dir)
    meta_music = read_article_meta_music(article_dir)
    print(f"\n📄 文章: {article_file.name}")
    print(f"📰 标题: {article_title(article_file, article_dir)}")

    model = resolve_model(args.model, meta_music.get("model"))
    gender = args.gender or meta_music.get("gender") or determine_vocal_gender(article_dir)
    if gender not in VOCAL_STYLES:
        gender = determine_vocal_gender(article_dir)
    vocal_info = VOCAL_STYLES[gender]

    style_key = args.style or meta_music.get("style")
    if not style_key or style_key not in STYLE_POOL:
        style_key = "ethereal_folk"
    style_info = STYLE_POOL[style_key]

    imagery = [x.strip() for x in args.imagery.split(",")] if args.imagery else []
    theme_brief = (args.theme_brief or "").strip()
    if not theme_brief:
        theme_brief = fallback_brief(article_dir, article_file)
        print("⚠️  未传 --theme-brief，用 frontmatter 规则兜底。")
        print("   （建议由 Claude 提炼【虚无缥缈的诗意意象】传入，方法A 下歌词更空灵→音色更柔美）")

    song_name = args.song_name or meta_music.get("song_name") or article_title(article_file, article_dir)[:10] or "无名之歌"

    print(f"🎤 人声: {vocal_info['label']}（奇偶交替）")
    print(f"🎵 风格: {style_info['name']}（{style_info['bpm']} BPM）")
    print(f"🎵 歌名: {song_name}")
    print(f"💭 主旨: {theme_brief}")
    if imagery:
        print(f"🖼️  意象: {', '.join(imagery)}")

    # ── Step 2: 构建 V2 prompt + 生成 ──
    music_prompt = build_music_prompt(theme_brief, imagery, style_key, gender)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_song_name = re.sub(r'[\\/:*?"<>|]', '-', song_name)
    output_path = Path(args.output).resolve() if args.output else article_dir / f"{safe_song_name}.mp3"
    print(f"\n🎧 输出: {output_path.name}")

    extra = generate_music_lyria3(music_prompt, output_path, args.oauth_token, args.project, model)
    if extra is None:
        print("\n❌ 生成失败。看上面的 HTTP 码定位：404=端点形态 / 401=凭证类型 / 403=project 权限；"
              "其余多为安全过滤或超时，可重试或换 --style。")
        sys.exit(1)

    # ── Step 3: 收尾（元数据 / 封面 / 插卡）──
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"  ✅ 生成成功！  {output_path}")
    print(f"  📊 {size_mb:.1f} MB · ~{extra.get('music_duration', 0) / 1000:.0f}s · "
          f"{style_info['name']} · {vocal_info['label']}")
    print(f"{'=' * 60}")

    meta = {
        "article": str(article_file), "engine": "lyria3", "model": model,
        "endpoint": VERTEX_INTERACTIONS.format(project=args.project),
        "method": "Lyria 3 自动写词（歌词随响应返回，见 lyrics 字段）", "prompt_version": "v2",
        "style": style_key, "style_name": style_info["name"],
        "gender": gender, "vocal_label": vocal_info["label"],
        "theme_brief": theme_brief, "imagery": imagery, "song_name": song_name,
        "prompt": music_prompt, "output": str(output_path),
        "extra_info": extra, "generated_at": timestamp,
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📋 元数据: {output_path.with_suffix('.json').name}")

    # 歌词单独落一份纯文本，便于人工校对（旧 MiniMax 引擎拿不到歌词，这是 Lyria 3 新增能力）
    if extra.get("lyrics"):
        lyrics_path = output_path.with_name(output_path.stem + "-歌词.txt")
        lyrics_path.write_text(extra["lyrics"], encoding="utf-8")
        print(f"  📝 歌词: {lyrics_path.name}")

    if args.skip_cover:
        print("  ⏭️ 已按参数跳过 Google 主题曲封面生成。")
    else:
        generate_music_cover(song_name, imagery, output_path.parent)
    insert_audio_card(article_file, style_info["name"], song_name)

    print("\n🚀 请手动上传音频至微信素材库（手动上传才能设置音乐封面图）")
    print(f"  📁 音频: {output_path}")
    if not args.skip_cover:
        print(f"  🖼️ 封面: {output_path.parent / '素材' / 'bgm_cover.png'}")
    print("  ℹ️  路径: 微信后台 → 素材管理 → 音频 → 上传；插入时定位到卡片占位处。")


if __name__ == "__main__":
    main()
