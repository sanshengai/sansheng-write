#!/usr/bin/env python3
"""
🎵 公众号文章配乐生成器 (Article BGM Generator · MiniMax 版 V2)
================================================
为微信公众号文章生成 ~2-3 分钟【中文人声主题曲】（舒缓 · 空灵 · 柔美）。

引擎：MiniMax music-2.6-free（方法A：lyrics_optimizer 自动写词），国内站 api.minimaxi.com。

🔴 V2 架构变化：
    **文章提炼不再调 Gemini**（那是 Lyria 时代走 Google AI Studio 的历史包袱，MiniMax 不碰 Google）。
    改由【宿主 Agent 在 autopilot 里提炼】诗意意象，作为参数传入：
      --theme-brief  "虚无缥缈的诗意主旨叙事（一句，方法A 据此自动写词）"
      --imagery      "柔美画面词,逗号分隔,如 晨光,薄雾,潮汐"
      --song-name    "诗意短歌名"
      --style        ethereal_folk|ambient_vocal|ambient_piano|cinematic_vocal
      --gender       female|male（默认按序号奇偶交替）
    脚本退化为纯执行器：拼 V2 空灵 prompt → MiniMax 写词+生成 → 下载 → 封面 → 插卡。
    未传 --theme-brief 时用 frontmatter 规则兜底（音色通常不如 Agent 提炼空灵，会警告）。

🔴 V2 空灵升级（基于 Suno/MiniMax 实测研究）：
    ① 最大杠杆=主旨叙事写成诗意意象（方法A 下歌词决定音色空灵度）
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
    仓根 .env（cp .env.example .env）需含 MINIMAX_API_KEY（国内站 api.minimaxi.com，账户需余额>0）；
    shell 环境变量优先于 .env。未配置时本脚本打印说明后跳过（exit 0），不阻塞发布链。
    封面（可选，失败不阻塞）另需 GOOGLE_API_KEY（Vertex Express，给 gen_img.py）。

历史:
    2026-04 Lyria 3 Pro（多模态图文）→ 2026-05-29 Lyria Vertex 404 废弃 →
    2026-06-18 复活切 MiniMax（曾保留 Gemini 分析）→ 同日晚 V2 去 Gemini、Claude 提炼传参 + 空灵升级。
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
# V2 收窄乐器为 2-3 件核心（配器极简凸显空气感）；空灵专用词与物理声学质感统一在 build_minimax_prompt 公共段加。
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

# MiniMax 音乐生成端点（国内站；key 不与国际站 minimax.io 互通）
MINIMAX_ENDPOINT = "https://api.minimaxi.com/v1/music_generation"


def load_env():
    """密钥统一走 profile_config（shell env → 本仓 .env）。

    刻意**不**去读别的工具的 dotenv、也不把读到的值注入 os.environ --
    偷读别人的配置目录、顺手污染进程环境，都是意外行为。
    保留本函数名是为了兼容既有调用点；真正的读取见 minimax_key()。
    """
    return


def minimax_key(cli_value: str = "") -> str:
    """读取顺序 CLI > shell env > 仓根 .env（经 load_secret）。

    读不到返回空串，由 main 以非零退出阻断新文章发布链。
    """
    if cli_value:
        return cli_value
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import profile_config as _pc
    return _pc.load_secret("MINIMAX_API_KEY", required=False)


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
        km = re.search(rf'^\s+{key}:\s*["\']?(.*?)["\']?\s*$', block, re.MULTILINE)
        if km and km.group(1).strip():
            result[key] = km.group(1).strip()
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
# 🎼 MiniMax prompt 构建（V2 空灵升级 + 方法A）
# ============================================================
def build_minimax_prompt(theme_brief: str, imagery: list, style_key: str, gender: str) -> str:
    """构建 MiniMax music-2.6 的 V2 prompt（空灵升级 + 方法A 自动写词）。

    theme_brief：Claude 提炼的诗意主旨叙事（虚无缥缈意象一句，MiniMax 据此自动写词）。
    imagery    ：核心意象 list（柔美画面词）。
    空灵升级：aria/echoing/resonant + 配器极简 + 物理声学(airy/reverb tail/overtones)
            + 人声呼吸感 + 低 BPM；整句叙事写法（MiniMax 官方第一原则）。
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
        f"Dreamy, floating, tranquil and healing, distant and atmospheric, spacious and weightless, "
        f"wide stereo, soft dynamics, beatless and free-flowing. "
        f"Avoid: energetic, upbeat, fast tempo, driving beat, drums, heavy bass, EDM, rock, aggressive, "
        f"festive, cheerful pop, dense or busy arrangement."
    )


# ============================================================
# 🚀 MiniMax 音乐生成（裸 REST，方法A 自动写词，同步返回 + 下载）
# ============================================================
def generate_music_minimax(prompt: str, output_path: Path, minimax_key: str,
                           model: str = "music-2.6-free") -> "dict | None":
    """调用 MiniMax music_generation 生成中文人声歌曲并下载到 output_path。

    方法A：lyrics_optimizer=true + 不传 lyrics → 模型按 prompt 自动写词演唱。
    成功返回 extra_info（含 music_duration 等）；失败返回 None。
    """
    body = {
        "model": model,
        "prompt": prompt,
        "lyrics_optimizer": True,        # 方法A：自动写词
        "is_instrumental": False,        # 要人声唱文章内容
        "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"},
        "output_format": "url",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    print(f"  🚀 正在调用 MiniMax {model} 生成中文人声主题曲（方法A 自动写词，预计 1-3 分钟）...")
    print("  ⏳ 请耐心等待...\n")
    try:
        req = urllib.request.Request(
            MINIMAX_ENDPOINT, data=data,
            headers={"Authorization": f"Bearer {minimax_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ❌ HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 请求失败：{e}")
        return None

    base = result.get("base_resp", {}) or {}
    if base.get("status_code") != 0:
        print(f"  ❌ MiniMax 错误 {base.get('status_code')}: {base.get('status_msg')}")
        if base.get("status_code") == 1008:
            print("  ⚠️ 账户余额不足 → 登录 platform.minimaxi.com 用户中心-余额 充值后重试。")
        return None

    audio = (result.get("data") or {}).get("audio")
    if not audio or not str(audio).startswith("http"):
        print(f"  ❌ 未返回音频 URL：{json.dumps(result, ensure_ascii=False)[:200]}")
        return None

    try:
        urllib.request.urlretrieve(audio, output_path)
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 音频下载失败：{e}")
        return None

    extra = result.get("extra_info", {}) or {}
    print(f"  ✅ 生成成功！时长 ~{extra.get('music_duration', 0) / 1000:.0f}s，已保存：{output_path.name}")
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
        description="🎵 公众号文章配乐生成器（MiniMax 版 V2）— Claude 提炼诗意意象 + MiniMax 写词生成"
    )
    parser.add_argument("article_dir", help="文章目录路径")
    parser.add_argument("--minimax-key", default=None,
                        help="MiniMax 国内站 API Key（默认经 minimax_key() 读 shell env → 仓根 .env）")
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
                        help="MiniMax 模型（默认 article-meta.yaml music.model，再兜底 music-2.6-free）")
    parser.add_argument("--output", default=None, help="输出 MP3 文件路径")
    args = parser.parse_args()

    # key 解析统一走 minimax_key()（CLI > shell env > 仓根 .env）。修复（复核 F1）：
    # 原先 argparse default 只读 os.getenv，.env 里的配置被绕过、minimax_key() 成死代码。
    args.minimax_key = minimax_key(args.minimax_key or "")
    if not args.minimax_key:
        print("❌ 未配置 MINIMAX_API_KEY —— 新文章的 BGM 是发布硬门，禁止静默跳过。")
        print("    请 cp .env.example .env 后填 MINIMAX_API_KEY（MiniMax 国内站，账户需余额），")
        print("    或 export MINIMAX_API_KEY=... / 用 --minimax-key 传入。")
        sys.exit(2)

    article_dir = Path(args.article_dir).resolve()
    if not article_dir.is_dir():
        print(f"❌ 错误：目录不存在: {article_dir}")
        sys.exit(1)

    print("=" * 60)
    print("🎵 公众号文章配乐生成器（MiniMax V2 · Claude 提炼）")
    print("=" * 60)

    # ── Step 1: 文件 + 提炼来源（优先级 CLI > article-meta.yaml > 规则兜底）──
    article_file = find_article_file(article_dir)
    meta_music = read_article_meta_music(article_dir)
    print(f"\n📄 文章: {article_file.name}")
    print(f"📰 标题: {article_title(article_file, article_dir)}")

    model = args.model or meta_music.get("model") or "music-2.6-free"
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
    music_prompt = build_minimax_prompt(theme_brief, imagery, style_key, gender)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_song_name = re.sub(r'[\\/:*?"<>|]', '-', song_name)
    output_path = Path(args.output).resolve() if args.output else article_dir / f"{safe_song_name}.mp3"
    print(f"\n🎧 输出: {output_path.name}")

    extra = generate_music_minimax(music_prompt, output_path, args.minimax_key, model)
    if extra is None:
        print("\n❌ 生成失败。可能原因：余额不足 / 安全过滤 / 网络超时。建议重试或换 --style。")
        sys.exit(1)

    # ── Step 3: 收尾（元数据 / 封面 / 插卡）──
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"  ✅ 生成成功！  {output_path}")
    print(f"  📊 {size_mb:.1f} MB · ~{extra.get('music_duration', 0) / 1000:.0f}s · "
          f"{style_info['name']} · {vocal_info['label']}")
    print(f"{'=' * 60}")

    meta = {
        "article": str(article_file), "engine": "minimax", "model": model,
        "method": "A (lyrics_optimizer 自动写词)", "prompt_version": "v2",
        "style": style_key, "style_name": style_info["name"],
        "gender": gender, "vocal_label": vocal_info["label"],
        "theme_brief": theme_brief, "imagery": imagery, "song_name": song_name,
        "prompt": music_prompt, "output": str(output_path),
        "extra_info": extra, "generated_at": timestamp,
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📋 元数据: {output_path.with_suffix('.json').name}")

    generate_music_cover(song_name, imagery, output_path.parent)
    insert_audio_card(article_file, style_info["name"], song_name)

    print("\n🚀 请手动上传音频至微信素材库（手动上传才能设置音乐封面图）")
    print(f"  📁 音频: {output_path}")
    print(f"  🖼️ 封面: {output_path.parent / '素材' / 'bgm_cover.png'}")
    print("  ℹ️  路径: 微信后台 → 素材管理 → 音频 → 上传；插入时定位到卡片占位处。")


if __name__ == "__main__":
    main()
