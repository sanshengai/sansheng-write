# 文章音乐生成（BGM / 主题曲）· MiniMax 版

> 从文章内容提炼主旨、生成**中文人声主题曲**、嵌入微信文章的完整 SOP。
> **可从任意步骤开始**--每步均自包含。本阶段由编排器单线程执行（契约见 references/orchestration.md）。

> ### 📌 引擎沿革
> - 初版：Google Lyria 3 Pro（多模态图文输入）。
> - 因 Lyria 3 在 Vertex AI 全路径 404（项目白名单不开放）**废弃**。
> - **现引擎：MiniMax `music-2.6-free`**。与 Lyria 版差异：
>   ① 不支持图片输入（仅文字 prompt）；② 风格池收窄为 4 种舒缓系；③ 走**方法A**（`lyrics_optimizer` 自动写词）；④ 时长不锁（公众号无硬控）。

---

## 品牌音乐 DNA

本号的音乐基调：**温暖 · 有机 · 克制 · 舒缓空灵 · 中文人声（Mandarin vocals）**

### 全局情绪约束

| 维度 | 约束 |
|------|------|
| 默认能量级别 | calm（10 分制 3-4 分），**绝不欢快、无强节奏感** |
| BPM | 全部锁 62-72（舒缓空灵区），不超过 75 |
| 风格倾向 | 环境浮声 / 氛围钢琴 / 空灵；prompt 统一带 `no driving beat / beatless` |

> 🔴 **必须含中文演唱**--人声唱出文章内容，让读者直觉感到"这首歌是专为这篇文章创作的"，与文字内容一一呼应、有专属感与震撼感。纯器乐辨识度太低、给不了这种呼应，**不采用纯器乐**。

### prompt 关键词（研究固化）

- **必带**：`ambient / ethereal / serene / gentle / spacious / lush reverb / soft dynamics / minimalist`、具体软音色（felt piano / ambient pad / glockenspiel）、明确 BPM
- **禁用**：`energetic / upbeat / fast tempo / driving beat / heavy bass / EDM / rock / aggressive / festive / cheerful pop`

---

## 核心脚本（V2：Claude 提炼诗意意象 → 传参）

> 🔴 **不调 Google**（那是 Lyria 时代走 Google AI Studio 的历史包袱，MiniMax 不碰 Google）。由 **Claude 在 BGM 阶段按下面《Claude 提炼标准》提炼**，作为参数传给脚本；脚本是纯执行器（拼 V2 空灵 prompt → MiniMax 写词生成）。

```bash
python "$SKILL/scripts/generate_article_bgm.py" "<文章目录>" \
    --theme-brief "虚无缥缈的诗意主旨叙事（一句，方法A 据此自动写词）" \
    --imagery "柔美画面词,逗号分隔,如 薄雾,潮汐,微光" \
    --song-name "既诗意又点题文章主题的短歌名" \
    --style ambient_piano --gender male

# 参数优先级：CLI > article-meta.yaml music 块 > 规则兜底
#   --theme-brief  不传则用 frontmatter digest/description 兜底（音色不如诗意提炼空灵，会警告）
#   --style  ethereal_folk|ambient_vocal|ambient_piano|cinematic_vocal（默认 ethereal_folk）
#   --gender 默认按序号奇偶交替（奇女偶男）；--model 默认 music-2.6-free 限免
```

前置：`.env` 需含 `MINIMAX_API_KEY`（国内站 api.minimaxi.com，账户需余额>0）。封面（可选，失败不阻塞）另需 `GOOGLE_API_KEY`（gen_img.py 用）。

---

## 风格池（4 种舒缓系，与 generate_article_bgm.py 的 STYLE_POOL 同步）

| 风格 Key | 名称 | BPM | 适合文章类型 |
|----------|------|-----|------------|
| `ethereal_folk` | 空灵民谣 | 70 | 深度思考 / 观点输出 / 人物说理 |
| `ambient_vocal` | 环境浮声 | 62 | 科技探索 / 未来想象 / AI工具对比 / 前沿趋势 |
| `ambient_piano` | 氛围钢琴 | 66 | 哲思文章 / 行业反思 / 年度盘点 / 收尾感悟 |
| `cinematic_vocal` | 影视人声 | 72 | 长文特稿 / 行业深度分析 / 重磅专题 / 年终总结 |

> 已砍掉原 `light_pop`（欢快）/ `lofi_vocal`（节拍）/ `warm_ballad`（叙事节奏）。
> 风格回避：脚本读 `<数据目录>/articles.md` 近 3 篇「音乐风格」字段，强制避开重复。

### 人声交替（防审美疲劳）

| 维度 | 规范 |
|------|------|
| 交替规则 | 奇数篇=女声，偶数篇=男声（按目录序号） |
| 女声 | 空灵、气声、偏高音区（温柔一面） |
| 男声 | 温暖、中低音、叙述感 |

---

## 🔴 Claude 提炼标准（方法A 的最大杠杆）

方法A 下 MiniMax 按 `theme_brief` **自动写词**，而**歌词内容直接决定音色空灵度**（实测：AI 分析歌词给适配风格）。所以 Claude 提炼时务必：

| 要素 | 标准 |
|---|---|
| **theme_brief** | 提炼成**虚无缥缈的诗意意象一句**（留白、柔美、有画面），**不是信息性概括**。<br>例（睡眠主题文）：❌「睡眠是大脑的免费夜班」 ✅「夜里有人替你点一盏灯，收走一天的尘埃」 |
| **imagery** | 2-3 个**柔美具体画面词**（薄雾/潮汐/微光/晨光/星河）；**禁抽象大词**（智慧/治愈/未来/科技） |
| **song_name** | 🔴 **既诗意又点题文章主题**--让读者一看歌名就联想到文章讲什么。<br>例（睡眠文）：❌《替你点灯》(看不出讲睡眠) ✅《替你值夜》《大脑的夜班》(点题"睡眠/夜班"+诗意) |
| **style** | 4 选 1：哲思/治愈/盘点→`ambient_piano`；科技/未来→`ambient_vocal`；深度/观点→`ethereal_folk`；长文特稿→`cinematic_vocal` |
| **gender** | 默认按序号奇偶交替（奇女偶男），防审美疲劳 |

脚本据此拼 V2 空灵 prompt（`aria`/`echoing`/`resonant` + 配器极简 + 物理声学 `airy high freq`/`long reverb tail`/`shimmering overtones` + 人声呼吸感 + 55-64 BPM）。

> 词不可控/看不到文本是方法A 的固有代价；质量靠**诗意提炼 + V2 空灵 prompt + 必要时换 `--style` 重生成**。

---

## API 调用要点（MiniMax music_generation）

| 项 | 值 |
|----|----|
| 端点 | `POST https://api.minimaxi.com/v1/music_generation`（国内站，key 不与 minimax.io 互通） |
| 鉴权 | `Authorization: Bearer {MINIMAX_API_KEY}`（无需 GroupId） |
| 模型 | `music-2.6-free`（限免，需账户余额 >0）/ `music-2.6`（付费） |
| 入参 | `prompt` + `lyrics_optimizer=true` + `is_instrumental=false` + `audio_setting{44100/256000/mp3}` + `output_format=url` |
| 返回 | 同步，`data.audio` 为 url（24h 有效），下载落 `<文章目录>/{歌名}.mp3` |
| 常见错误 | `1008 余额不足` → 登录 platform.minimaxi.com 用户中心-余额 充值 |

---

## 微信文章插入（AUDIO-CARD 引导卡片）

> 🔴 **顺序铁律**：`generate_article_bgm.py` 必须在 MD→HTML 排版**之前**执行（先生成 mp3 + 把卡片写入 定稿.md，排版才渲染出卡片）。
> 🔴 **位置铁律**：脚本把 `<!-- AUDIO-CARD-START -->`…`<!-- AUDIO-CARD-END -->` 块追加到 `定稿.md` **最末尾**；`format_layout.py --all` 自动前置到导读栏下方。严禁放在开头（会被 baoyu-md 误吞进 `<meta description>` 导致 head 崩坏）。

脚本会自动：
1. 生成 `{歌名}.mp3` + `{歌名}.json`（元数据）
2. 调 `gen_img.py` 生成 1:1 主题曲封面 `素材/bgm_cover.png`（不打水印）
3. 把含「👉 请将光标定位于此插入音频」占位框的 Block 级卡片追加到 `定稿.md` 末尾

发布时：微信后台 → 素材管理 → 音频 → 上传 mp3（可设封面图 bgm_cover.png）；编辑器里定位到卡片占位处插入音频。

### 卡片设计规范

- 🔴 不做"假播放按钮"（微信原生 `mpaudio` 已有完整 UI）
- 🔴 不用 `display: flex` 包裹播放器（微信块级组件会破版）
- ✅ 上下流式 Block 容器：顶部标题栏「🎵 本文主题曲」（不显歌名，避免与微信自带重复）+ 下部留空给 `<mpvoice>`
- ✅ 边框 `rgba(47, 111, 143,0.15)` 淡主题色圆角细框

---

## 发布检查

- ☐ BGM 已生成（**排版之前**）：`{歌名}.mp3` + `素材/bgm_cover.png`
- ☐ `定稿.md` 含 AUDIO-CARD 引导卡片（关键字「本文主题曲」）
- ☐ 已重新走排版管线（MD→HTML + format_layout.py --all），卡片前置到导读下方
- ☐ MP3 已上传微信素材库、封面选 `bgm_cover.png`
- ☐ 手机端预览可正常播放

---

*引擎 Lyria → MiniMax music-2.6-free，方法A 自动写词，风格池收窄 4 种舒缓系。*
