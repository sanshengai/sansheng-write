# 文章音乐（BGM / 主题曲）

## 当前执行方式：MiniMax 网页手动生成

默认由作者在 MiniMax 网页生成中文人声主题曲。Lyria 自动通道目前暂停，直到作者明确要求恢复；不运行自动生成器，不为推进文章要求作者登录 Google Cloud、配置 ADC、项目或 API Key，也不改走 MiniMax API。暂停的是自动生成通道，主题曲本身仍是发布必需素材。

Agent 必须先完成可直接使用的 `MiniMax-主题曲生成单.md`，再请求作者操作。不能只说“去生成一首歌”，也不能只给主题而缺完整歌词。模板见 `../templates/minimax-music-brief.template.md`。

### 1. 交付生成单

从已确认正文提炼，文件保存在本篇文章目录，并给可点击的绝对路径。必含：

- 歌名：与文章主题有关，适合唱出，不照搬整条文章标题。
- 主题与情绪：用具体生活画面说明要唱什么、情绪怎样变化，避免把技术说明直接塞进歌词。
- 可直接复制的音乐风格提示词：人声、语言、BPM、配器、氛围、段落结构、目标时长及应避免的唱法。
- 完整简体中文歌词：按主歌、副歌、桥段、尾声等实际结构写全，风格和歌词分开，便于分别复制。
- 导出与回传要求：MP3 文件名、放置目录；保留网页实际显示的模型名称或生成记录，便于登记来源。不要把建议时长或计划模型当成成品事实。

作者已有歌名、风格或歌词选择时沿用。新歌按下方品牌音乐 DNA 与风格池编写；已审批正文及 meta 不因制作生成单而改写。

### 2. 等待 MP3 时

给出完整生成单后，等待作者提供实际音频，继续可独立完成的配图、核对等工作。此时 BGM 仍待完成，不标失败、不 `skip`、不造 MP3 或来源凭证、不承诺草稿已提交。收到音频后直接续做，不重新要求正文审批。

### 3. 接收音频与来源登记

核实可播放文件与实际时长、来源后，使用 `music_manifest.py` 创建 `_music-manifest.json`，绑定文件 SHA-256、字节数、时长以及真实 `provider/model/mode`。文件名、时间戳、生成单里的计划字段和“最新候选”均不能证明实际来源。

若没有既有歌曲注册表，可先在本篇建立 `主题曲来源记录.md`，以独立条目记下作者交付事实、实际模型和文件；manifest 引用该文件和条目。已有注册表时复用，不复制另一份。模型名称不明时向作者核实，不硬填某个 MiniMax 版本。

```bash
python "$SKILL/scripts/music_manifest.py" create "<文章目录>" --audio "<实际 MP3 相对路径>" --title "<歌名>" --duration-seconds <探测时长> --provider "MiniMax" --model "<网页实际模型>" --mode "web-ui" --registry-ref "主题曲来源记录.md" --registry-entry "<实际条目 ID>"
python "$SKILL/scripts/music_manifest.py" verify "<文章目录>" --probe-duration
```

发布硬门保持通道中性：作者明确指定复用既有歌曲或其他来源时保留真实出身，不把旧歌改写成 MiniMax 新生成。

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
> 风格回避：Agent 读 `<数据目录>/articles.md` 近 3 篇「音乐风格」字段，强制避开重复。

### 人声交替（防审美疲劳）

| 维度 | 规范 |
|------|------|
| 交替规则 | 默认奇数篇=女声，偶数篇=男声（按目录序号）；`shanghai_jazz_soul` 无显式设置时默认亲密女声 |
| 女声 | 空灵、气声、偏高音区（温柔一面） |
| 男声 | 温暖、中低音、叙述感 |

---

## 主题与歌词写法

主旨先落到具体动作和物件，再写可唱的句子。选两三个与本文有关的意象，保持歌词内在连贯；副歌可以重复文章最想留下的感受。中文人声必须与本文呼应，但不要求把软件名、命令和参数唱出来。由当前 Agent 写完整歌词，不把此步骤交给尚未启动的 Lyria。

## 接入微信文章

音频文件与 manifest 验证通过后，用 `audio_cards.py::upsert_card` 的共享模板写入主题曲卡片。必须在 MD→HTML 排版之前完成；AUDIO-CARD 与可选 PODCAST-CARD 机器块先收口到 `定稿.md` 最末尾，再由 `format_layout.py --all` 按「导读 → 主题曲 → 播客 → 正文」前置。不得改动已审批的作者正文。主题曲封面按既有视觉流程处理；封面不能证明音频已经生成。

若 `podcast.wechat_embed: true`，`podcast-pregen` 会用同一模板再写「🎧 音频版本｜本期播客」卡片。发布时在微信编辑器分别插入两份原生音频；保存后从微信预览分别试听两条音频的开头/结尾 10 秒，再跑 `pipeline.py wechat-audio-check --confirm-audition`。

### 上传文件统一放在文章文件夹

运行以下命令，把人工上传用的主题曲、播客和封面放在本篇文章目录第一层（例如 `100-AI帮自己搬家/`），交付时直接给这个目录及其中音频的可点击路径，不另建“手工上传”文件夹：

```bash
python "$SKILL/scripts/pipeline.py" --dir "<文章目录>" handoff-assets
```

主题曲保留原文件名（已经在第一层就直接复用），播客为 `podcast.mp3`，封面为 `cover.png`。源文件 `dist/podcast/audio.mp3`、`素材/cover.png` 及其回执继续服务生成和发布流程；根目录提供经 SHA-256 与大小验证的上传副本，不为方便查找移走源文件。

命令只读取封存视觉凭证和音频 manifest 指定的文件，验证后才交付，根目录写 `_handoff-receipt.json`；同一快照可重复运行，现有同名不同内容文件会报错，不静默覆盖正文或其他资产。旧 `SANSHENG_WRITE_HANDOFF_DIR` 配置不再自动生效。只有作者明确要求独立导出时才使用 `--target-root <目录>`，此模式保留 `--revision r2` 的版本快照能力。

这里的交付不等于永久归档；整篇成品归档仍按 `physical-archive.md` 执行。

### 卡片设计规范

- 🔴 不做"假播放按钮"（微信原生 `mpaudio` 已有完整 UI）
- 🔴 不用 `display: flex` 包裹播放器（微信块级组件会破版）
- ✅ 两张卡共用同宽 Block 骨架与淡主题色圆角细框，只以图标、标题和用途元信息区分
- ✅ 移动端上下连续排列，不用双栏；主题曲服务“边读边听”，播客服务“代替阅读”，不互相从属

---

## 发布检查

- 实际 MP3 与 `_music-manifest.json` 已验证，生成单不能替代成品。
- `定稿.md` 含 AUDIO-CARD；开启嵌入时还有 PODCAST-CARD 与同源播客 MP3。
- 排版顺序为导读 → 主题曲 → 播客 → 正文。
- 作者在微信后台插入两份实际音频、移除占位文字，分别试听首尾后，按原流程完成官方回读检查。

## 暂停通道的维护资料

只有作者明确要求恢复或排查 Lyria 时才读 `music-lyria-paused.md`。保留历史实现和脚本便于未来恢复，不把它列为当前默认步骤。
