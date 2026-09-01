# 文章音乐（BGM / 主题曲）· 通道中性来源合同

> 从文章内容提炼主旨、生成**中文人声主题曲**、嵌入微信文章的完整 SOP。
> **可从任意步骤开始**--每步均自包含。本阶段由编排器单线程执行（契约见 references/orchestration.md）。

> ### 📌 引擎沿革
> - 2026-04 初版：Google Lyria 3 Pro（多模态图文输入）。
> - 2026-05-29 因 Vertex 全路径 404 **误判**为「项目白名单不开放」而废弃 → 切 MiniMax `music-2.6-free`。
> - 2026-08-20 MiniMax 音乐 API 对非历史付费用户关停（HTTP 410 / `status_code 2153`）。
>   按量计费 Key、订阅 Key、网页声贝三条通道实测全灭，充值升套餐均无法解锁。
> - 2026-08-21 **查明当年的 404 是端点形态用错**——Lyria 3 走 `interactions`，不是 `:predict`；
>   换对后实测跑通中文女声整首歌（176s）。Lyria 3 Pro `lyria-3-pro-preview`
>   是默认自动生成通道，不是发布硬门唯一允许的来源。
>
> Lyria 自动通道特征：① 仅文字 prompt（图片输入未在本管线启用）；② 风格池 5 种舒缓系；
> ③ 自动写词，且**歌词随响应返回**（落 `{歌名}-歌词.txt`，旧引擎「词不可控、看不到文本」的代价消失）；
> ④ 时长约 3 分钟；⑤ 计费 $0.08/首，走 Cloud，$300 赠金可覆盖。

发布硬门只认文章本地 `_music-manifest.json`：它必须绑定实际播放文件的 SHA-256、
字节数、时长，以及真实 `provider / model / mode` 与注册表引用。自动生成、外部网页
生成和复用既有主题曲都允许；任何通道切换都不得改写旧歌出身，也不得从同名 MP3、
时间戳或“最新候选”推断来源。

---

## 品牌音乐 DNA

本号的音乐基调：**温暖 · 有机 · 克制 · 舒缓空灵 · 中文人声（Mandarin vocals）**

### 全局情绪约束

| 维度 | 约束 |
|------|------|
| 默认能量级别 | calm（10 分制 3-4 分），**绝不欢快、无强节奏感** |
| BPM | 全部锁 55-68（舒缓区），不超过 70 |
| 风格倾向 | 环境浮声 / 氛围钢琴 / 空灵 / 温暖怀旧；默认 `beatless`，`shanghai_jazz_soul` 只允许非推进型轻刷鼓 |

> 🔴 **必须含中文演唱**--人声唱出文章内容，让读者直觉感到"这首歌是专为这篇文章创作的"，与文字内容一一呼应、有专属感与震撼感。纯器乐辨识度太低、给不了这种呼应，**不采用纯器乐**。

### prompt 关键词（研究固化）

- **默认必带**：`ambient / ethereal / serene / gentle / spacious / lush reverb / soft dynamics / minimalist`、具体软音色（felt piano / ambient pad / glockenspiel）、明确 BPM
- **海派爵士灵魂例外**：改用 `classic Shanghai jazz / gentle soul / vintage room / restrained phrasing / feather-light brushed drums`，结构写明「怀旧主歌 → 柔和发亮副歌」
- **禁用**：`energetic / upbeat / fast tempo / driving beat / heavy bass / EDM / rock / aggressive / festive / cheerful pop`

---

## 自动生成通道（Lyria 3）

> 🔴 **提炼环节不调任何模型**：由 **Claude 在 BGM 阶段按下面《Claude 提炼标准》提炼**，作为参数传给脚本；脚本是纯执行器（拼 V2 空灵 prompt → Lyria 3 写词生成）。
> （生成环节本身走 Google Vertex；这与「提炼不调模型」不冲突，别再沿用旧文档里"不碰 Google"的说法。）

```bash
python "$SKILL/scripts/generate_article_bgm.py" "<文章目录>" \
    --theme-brief "虚无缥缈的诗意主旨叙事（一句，方法A 据此自动写词）" \
    --imagery "柔美画面词,逗号分隔,如 薄雾,潮汐,微光" \
    --song-name "既诗意又点题文章主题的短歌名" \
    --style ambient_piano --gender male

# 参数优先级：CLI > article-meta.yaml music 块 > 规则兜底
#   --theme-brief  不传则用 frontmatter digest/description 兜底（音色不如诗意提炼空灵，会警告）
#   --style  ethereal_folk|ambient_vocal|ambient_piano|cinematic_vocal|shanghai_jazz_soul（默认 ethereal_folk）
#   --gender 默认按序号奇偶交替（奇女偶男）；shanghai_jazz_soul 例外默认女声
#   --model 默认 lyria-3-pro-preview
```

## 网页生成或复用既有主题曲

先把确认过来源的实际播放文件放进文章目录，再显式创建 manifest；下列字段必须按
真实出身填写，不能把当前临时通道或未来计划中的通道倒灌给旧成品：

```bash
python "$SKILL/scripts/music_manifest.py" create "<文章目录>" \
  --audio "素材/主题曲.mp3" --title "歌名" --duration-seconds 206.2 \
  --provider "MiniMax" --model "Music 3.0" --mode "web-ui" \
  --registry-ref "人物主题曲注册表.json" --registry-entry "人物ID"
python "$SKILL/scripts/music_manifest.py" verify "<文章目录>" --probe-duration
```

随后用 `audio_cards.py` 的共享模板把主题曲卡片收口到 `定稿.md` 文末，再进入排版；
卡片歌名、manifest 歌名和权威注册表必须一致。

### 主题曲来源契约

新文章必须在文章目录保存 `_music-manifest.json`。它是选定播放文件和来源署名的唯一真源，
必须绑定精确的相对路径、SHA-256、字节数、时长，以及显式的
`origin.provider/model/mode` 和 `registry.reference/entry`。禁止通过 MP3 文件名、
修改时间或「最新」 sidecar 推断当前主题曲及其出身。用户可见标签保持通道中性；
真实 provider/model 只写入来源字段。

Lyria 生成器会自动写契约。外部网页或其他引擎生成的成品，必须用显式来源补建：

```bash
python "$SKILL/scripts/music_manifest.py" create "<文章目录>" \
  --audio "<MP3 相对路径>" --title "<歌名>" --duration-seconds 180 \
  --provider "<provider>" --model "<model>" --mode "web-ui" \
  --registry-ref "<权威注册表引用>" --registry-entry "<条目 ID>"

python "$SKILL/scripts/music_manifest.py" verify "<文章目录>" --probe-duration
```

前置：已装 gcloud 并跑过 `gcloud auth application-default login` + `gcloud config set project <PROJECT>`（脚本用 ADC 取 OAuth token；**不需要 API Key**，缺凭证 exit 2 阻断发布链）。封面（可选，失败不阻塞）另需 `GOOGLE_API_KEY`（gen_img.py 的 Vertex Express key，与本阶段凭证不是同一套）。

---

## 风格池（5 种舒缓系，与 generate_article_bgm.py 的 STYLE_POOL 同步）

| 风格 Key | 名称 | BPM | 适合文章类型 |
|----------|------|-----|------------|
| `ethereal_folk` | 空灵民谣 | 60 | 深度思考 / 观点输出 / 人物说理 |
| `ambient_vocal` | 环境浮声 | 55 | 科技探索 / 未来想象 / AI工具对比 / 前沿趋势 |
| `ambient_piano` | 氛围钢琴 | 58 | 哲思文章 / 行业反思 / 年度盘点 / 收尾感悟 |
| `cinematic_vocal` | 影视人声 | 64 | 长文特稿 / 行业深度分析 / 重磅专题 / 年终总结 |
| `shanghai_jazz_soul` | 海派爵士灵魂 | 68 | 人物往事 / 城市记忆 / 怀旧叙事 / 温柔纪实 |

> 仍停用原 `light_pop`（欢快）/ `lofi_vocal`（通用节拍）/ `warm_ballad`（叙事节奏）。
> `shanghai_jazz_soul` 不是恢复通用 lo-fi 节拍：它只在 68 BPM 下允许轻刷鼓作呼吸脉冲，明确禁止 driving beat、鼓 fill 和大乐队式炒作。
> 风格回避：脚本读 `<数据目录>/articles.md` 近 3 篇「音乐风格」字段，强制避开重复。

### 人声交替（防审美疲劳）

| 维度 | 规范 |
|------|------|
| 交替规则 | 默认奇数篇=女声，偶数篇=男声（按目录序号）；`shanghai_jazz_soul` 无显式设置时默认亲密女声 |
| 女声 | 空灵、气声、偏高音区（温柔一面） |
| 男声 | 温暖、中低音、叙述感 |

---

## 🔴 Claude 提炼标准（自动写词的最大杠杆）

Lyria 3 按 `theme_brief` **自动写词**，而**歌词内容直接决定音色空灵度**（实测：模型按歌词语义决定配器与唱法）。所以 Claude 提炼时务必：

| 要素 | 标准 |
|---|---|
| **theme_brief** | 提炼成**虚无缥缈的诗意意象一句**（留白、柔美、有画面），**不是信息性概括**。<br>例（睡眠主题文）：❌「睡眠是大脑的免费夜班」 ✅「夜里有人替你点一盏灯，收走一天的尘埃」 |
| **imagery** | 2-3 个**柔美具体画面词**（薄雾/潮汐/微光/晨光/星河）；**禁抽象大词**（智慧/治愈/未来/科技） |
| **song_name** | 🔴 **既诗意又点题文章主题**--让读者一看歌名就联想到文章讲什么。<br>例（睡眠文）：❌《替你点灯》(看不出讲睡眠) ✅《替你值夜》《大脑的夜班》(点题"睡眠/夜班"+诗意) |
| **style** | 5 选 1：哲思/治愈/盘点→`ambient_piano`；科技/未来→`ambient_vocal`；深度/观点→`ethereal_folk`；长文特稿→`cinematic_vocal`；人物往事/城市记忆/怀旧叙事→`shanghai_jazz_soul` |
| **gender** | 默认按序号奇偶交替（奇女偶男）；`shanghai_jazz_soul` 默认女声；CLI / meta 显式设置始终优先 |

脚本据此拼 V2 prompt：前 4 种沿用空灵极简体系（`aria`/`echoing`/`resonant` + 物理声学质感）；`shanghai_jazz_soul` 单独走亲密人声、轻刷鼓和 vintage room 体系，避免与 `beatless` / 禁鼓约束自相矛盾。

> 词不可控/看不到文本是方法A 的固有代价；质量靠**诗意提炼 + V2 空灵 prompt + 必要时换 `--style` 重生成**。

---

## API 调用要点（Vertex Lyria 3 · interactions）

| 项 | 值 |
|----|----|
| 端点 | `POST https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/global/interactions` |
| 鉴权 | `Authorization: Bearer $(gcloud auth application-default print-access-token)` |
| 模型 | `lyria-3-pro-preview` — 本管线**固定用这一个**，不要换 |
| 入参 | `{"model": "...", "input": "<自然语言描述，含风格/人声/配器/主旨/简体中文歌词要求>"}` |
| 返回 | 同步；`outputs[]` 含 `type=audio`（**内联 base64 mp3**，无链接过期问题）、`type=text`×2（歌词 / caption） |
| 计费 | $0.08/首（Clip $0.04）。走 `aiplatform.googleapis.com` = Cloud 计费，**$300 赠金覆盖** |

### 🔴 三个坑（错任一个都报错，且报错措辞会把人带偏）

| 现象 | 真正原因 |
|------|----------|
| **404** `not found or your project does not have access` | 用了 `publishers/google/models/{M}:predict`——那是旧版音乐模型的端点形态，对 Lyria 3 必然 404。**不是**没白名单（public preview 无需 allowlist），社区里大批人卡在这个误判上，本管线 2026-05 也栽在这里 |
| **401** `API keys are not supported by this API` | interactions 只认 OAuth2。`.env` 里那把 `AQ.` 开头的 Vertex Express key 用不了（它是给 `gen_img.py` 的） |
| **403** `Permission 'aiplatform.interactions.create' denied` | project 选错。必须用**当前 ADC 账号自己有权限**的 project，别拿 `.env` 里的 `GOOGLE_VERTEX_PROJECT` |

> 🔴 **歌词默认出繁体**——prompt 必须显式写「Simplified Chinese（简体中文，NOT traditional）」，
> `build_music_prompt()` 已内置该约束，改 prompt 时不要删掉。
> 🔴 **只用 `lyria-3-pro-preview`**。Google 还有别的音乐模型，但要么纯器乐没人声、要么只出 30 秒片段，都顶不了主题曲——本管线不提供切换选项，避免选错。

---

## 微信文章插入（同级双音频卡）

> 🔴 **顺序铁律**：`generate_article_bgm.py` 必须在 MD→HTML 排版**之前**执行（先生成 mp3 + 把卡片写入 定稿.md，排版才渲染出卡片）。
> 🔴 **位置铁律**：脚本先把 `AUDIO-CARD` 与可选 `PODCAST-CARD` 机器块收口到 `定稿.md` **最末尾**；`format_layout.py --all` 再按「导读 → 主题曲 → 播客 → 正文」前置。严禁直接写在开头（会被 baoyu-md 误吞进 `<meta description>` 导致 head 崩坏）。

脚本会自动：
1. 生成 `{歌名}.mp3` + `{歌名}.json`（生成元数据）+ `_music-manifest.json`（发布来源契约）
2. 调 `gen_img.py` 生成 1:1 主题曲封面 `素材/bgm_cover.png`（不打水印）
3. 用 `audio_cards.py` 的共享模板写入「🎵 阅读配乐｜本文主题曲」卡片

若 `podcast.wechat_embed: true`，`podcast-pregen` 会用同一模板再写「🎧 音频版本｜本期播客」卡片。发布时在微信编辑器分别插入两份原生音频；保存后从微信预览分别试听两条音频的开头/结尾 10 秒，再跑 `pipeline.py wechat-audio-check --confirm-audition`。

需要把人工上传所需资产导出到浅层目录时，先配置
`SANSHENG_WRITE_HANDOFF_DIR`，再运行：

> 这里的 handoff 是给微信后台手工上传的临时资产包，不是文章永久归档目录；整篇成品必须按 `physical-archive.md` 走 `physical-archive`。

```bash
python "$SKILL/scripts/pipeline.py" --dir "<文章目录>" handoff-assets
# 目标已有不同快照时不覆盖；显式建新版：
python "$SKILL/scripts/pipeline.py" --dir "<文章目录>" handoff-assets --revision r2
# 临时覆盖 .env 目标也可显式传：
python "$SKILL/scripts/pipeline.py" --dir "<文章目录>" handoff-assets --target-root "<浅层目录>"
```

命令只会取已封存视觉凭证的封面、主题曲 manifest 绑定文件，以及可选的播客
manifest 绑定文件。逐项验证后通过同级临时目录原子落盘；同快照幂等，
不同快照拒绝覆盖，交接凭证不写时间戳以保持可重现。

### 卡片设计规范

- 🔴 不做"假播放按钮"（微信原生 `mpaudio` 已有完整 UI）
- 🔴 不用 `display: flex` 包裹播放器（微信块级组件会破版）
- ✅ 两张卡共用同宽 Block 骨架与淡主题色圆角细框，只以图标、标题和用途元信息区分
- ✅ 移动端上下连续排列，不用双栏；主题曲服务“边读边听”，播客服务“代替阅读”，不互相从属

---

## 发布检查

- ☐ BGM 已生成（**排版之前**）：`{歌名}.mp3` + `_music-manifest.json` + `素材/bgm_cover.png`
- ☐ `定稿.md` 含 AUDIO-CARD；开启嵌入时还含 PODCAST-CARD 与同源播客 MP3
- ☐ 已重新走排版管线，固定顺序为导读 → 主题曲 → 播客 → 正文
- ☐ 两份 MP3 已插入各自卡片并删除占位文字
- ☐ `wechat-audio-check --confirm-audition` 官方全文回读通过，微信预览已分别试听两条音频的开头/结尾 10 秒

---

*来源合同通道中性；Lyria 3 Pro 是默认自动生成器，网页生成与既有成品必须保留各自真实署名。*
