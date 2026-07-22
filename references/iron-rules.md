# 🔴 铁律清单（所有阶段共用）

以下铁律来自实战踩坑，每条都对应一个真实失败案例。**流水线各阶段均须遵守。**

---

## 生图后端总则（key 前缀分流）

封面/信息图采用两层路由：`baoyu-cover-image` / `baoyu-infographic` 是不可跳过的语义 producer，`imagegen` / `gen_img.py` 等只是 child skill 选定的像素 renderer；renderer 不得冒充 producer。BGM 走 `generate_article_bgm.py`。完整证据链、参数与数据图防幻觉细则统一在 [image-routing.md](image-routing.md)，进入任何生图环节前必先读取。

---

## 排版→发布强制序列

任何发布操作（发草稿箱）前，**必须完成 layout 阶段**（MD→HTML 转换 + 品牌配色 + 定稿模板。绝不允许未执行排版即发布）。

## 🔴 金句卡组件

> 本条此前只散落在 `SKILL.md` 主入口、`templates/quote-card.html`、`craft-techniques.md` 三处，
> **不在本铁律总纲里** -- 而主入口宣称「iron-rules.md 集中所有硬约束」，信任该指针的模型永远读不到它，故补录归位。

- **🔴 禁止 `&ldquo;` / `&rdquo;` / `&lsquo;` 等装饰性 HTML 实体**：部分平台里会渲染成乱码（`idqu` / 方框）。卡片内要引号就写中文「」或 ""，不加任何装饰性 HTML 实体。
- **样式一律走 [templates/quote-card.html](../templates/quote-card.html)**：左竖条 + 极浅主题色文本框（深色引文），**出处行 = 发丝线 + 淡化右对齐**。禁止旧版「整块主题色渐变盒 + 白字 + 大号装饰引号」（满底厚重割裂，已取代）。
- 单篇加粗口号式金句仍 ≤2（与「文笔朴实简洁四条」同源约束）。

## 🔴 开篇策略分流（按内容类型）

写大纲 / 定开头候选前，先判内容类型再定开篇方式（唯一权威源 = [outline.md 步骤 3.5](outline.md)，本条只作集中清单指针）：

- **资讯 / 时效类**（时事新闻、新软件 / 新工具 / 新技术 / 新模型介绍、横向评测、版本更新解读）→ **直入主题**：第一句直接说「发生了什么 / 它是什么」，随即进入正文。**禁止故事钩子、禁止基础概念铺垫、禁止用个人经历开篇**；个人经历最多压成一句可信度锚放在核心事实之后。SCQA 用 ASC。
- **成果 / 实作类**（自研工具 / 网页 / skill、成果介绍、实测记录、N 款横评）→ **成果前置直入**：第一屏交付「成果是什么 + 能干什么 + 入口 + 真实产出示例」四件；「为什么做 / 制作背景 / 焦虑数据」降级到成果之后当动机、不当钩子。SCQA 用 ASC，走资讯直入类风格路由。
- **深度启发类**（趋势洞察 / 观点 / 人物 / 随笔 / 方法论）→ **可用故事钩子**：现有开篇技法库 + 开头候选盲选流程照常。
- ✅ 资讯直入 / 成果前置类走 profile 里对应的「资讯/时效风格手册」（若有）为主路由，专为时事/新工具/新模型/评测做（详见 style-routes.md + 对应 `profile/corpus/authors/*.compact.md`）。

## 钩子区加粗下限（软警告）

> 本条现为**软警告，非机器硬阻断**。曾把"读者第一段不想读第二段"归因为加粗锚点不足，是**因果倒置**——决定"想读第二段"的是**首句钩子张力 + 句间承接**（见 [writing.md §句间引力](writing.md) + SKILL.md 写作核心第 6 条），不是加粗密度。强制每 80 字一处加粗，反而把首段切成均匀要点格，读起来像 PPT 不像一个人在说话，更伤语流。

**现行做法：** 钩子区（前 3 个 ≥80 字正文段）建议有视觉锚点，但**不再机器强制**。`format_layout.py preflight_markdown` 检测到钩子区 ≥2 段无加粗时，只打 `⚠️ 提示（不阻断）`，不再 `sys.exit(2)`。加粗**上限**（防刷屏，`verify_bold_density`）保留不动。

**首段验收的正确判据（取代"有没有加粗"）：** 首句是否自带钩子张力（反直觉判断／画面／问题三选一），前两句是否互相承接（句间引力）。用内容钩子替代视觉钩子。

**踩坑教训（保留作上下文）：** 曾有一版定稿首个 H2 前多段一个加粗都没有，读者反馈"重点字段过少，看到前一段抓不到吸引人的关键词就放弃读"。再复盘判定：当时的真问题不是缺加粗，是首句没张力、句间不承接；加机器硬门是治标且反噬语流，故改为软警告 + 在写作核心补「句间引力」治本。

## 文笔朴实简洁四条

🔴 写作时强制遵守的文笔铁律，违一条就要重写当段：

1. **能删的字一律删**——形容词、副词、连接词「然后/接着/那么/其实」、口头禅「我觉得/我认为/应该说」、修饰短句，看到就删。一段 3 句话能讲清的事，不要写成 5 句。
2. **段落短促**——单段超 100 字就自检能否拆分或减半。优秀白话样本里大量 1-2 句成段，这是节奏不是排版。
3. **不堆"高级词"**——「赋能 / 沉淀 / 打通 / 链路 / 底层逻辑 / 价值观」这种 AI 套话词出现 ≥3 次必须重写。改用具体动词+具体名词的大白话。
4. **白话试纸**——每段写完读出声。"我跟朋友讲不会这么说" / "我自己都觉得绕" / "省了不影响意思"——三种感觉任何一种出现，退回去改。

**样本库参照**：每次进入写作阶段前，**至少抽 2-3 篇本次风格路由对应的样本通读**。样本来自 profile 自备语料池（`profile/corpus/samples/{作者}/` 精选小池，无对应作者回退 `profile/corpus/voice-samples.md`）。抽样建议见 [writing.md §样本库参照](writing.md)。

## 流水线隔离铁律

封面图、信息图必须有明确的中文文字约束 + 符合品牌调性的 Prompt 重组机制。不能随便一句话直接扔给内置生图模型，必须严格走 baoyu 技能库的指定入口：

| 阶段 | **唯一允许**的入口 | 严禁 |
|---|---|---|
| 封面图 cover.png | `baoyu-skills:baoyu-cover-image` skill（必须读 [cover-styles.md](cover-styles.md) **顶部 override** 写入 montage-evidence prompt 后再调用） | 直接调 `baoyu-skills:baoyu-image-gen` / 套用历史文章 `cover.md` 模板（conceptual / focus 老风格全部封存）|
| 信息图 infographic*.png | `baoyu-skills:baoyu-infographic` skill（**style 二选一**）：① 具名 AI 模型/工具/产品/功能承担信息架构主轴（含新品盘点、模型发布、N 款横评，即使外层是行业趋势）→ `claymation` **暖米黄轻盈版**；②现象/商业/人文判断承担主轴、产品仅作例子 → `morandi-journal`。**产品/模型轴优先于趋势结论**，单篇风格统一。其他 20 种 style 全部封存。完整规则见 [image-routing.md §信息图 style 选择铁律](image-routing.md) | 直接调 baoyu-image-gen batch / 选 claymation 深色版（已封存）/ craft-handmade / 其他封存 style / 同篇混风格 |
| 组件小图 hero | `baoyu-skills:baoyu-image-gen`（仅这类小图允许）`--ar 1:1 --quality normal` | 走 cover-image 或 infographic skill（杀鸡用牛刀）|
| 数据图（雷达/折线/柱状/饼） | 本地 `matplotlib` / `pyecharts` 脚本 + `.py` 留在文章目录 | 任何 baoyu-* skill / 大模型生图（数据图防幻觉铁律）|

**典型踩坑（保留作上下文）**：
- autopilot 跑封面时跳过 `cover-styles.md`，套用旧 conceptual 模板 → 生成 briefing 风格而非 montage-evidence
- 信息图用 `baoyu-image-gen` batch 跑而不是 `baoyu-skills:baoyu-infographic` → 全是暗黑科技风，没有 claymation 暖米黄质感

**操作前自检**：进入任一生图阶段前**必须**自问"我用的入口是上表第 2 列吗"，对不上立即停。

## 🔴 生图分辨率铁律（1K 横切）

**所有 `baoyu-*` 生图产出统一 1K 分辨率：长边 ≈1024px（达标带 [900,1200]），宽高比按场景路由不变**（封面 2.35:1 / 信息图 9:16·16:9 / 组件小图 1:1）。旧的 ≥1000px / ≥1500px 下限一律被本铁律收敛到 1K。**例外**：`matplotlib`/`pyecharts` 数据图表走本地脚本 `dpi=300`，**不**受 1K 限制（由数据图防幻觉铁律单独管）。fan-out 新产出的信息图集合由 `scripts/contracts.py:verify_infographic_set` 按真实像素机器校验 1K（tier-2，仅对新产出强制、不追溯历史冻结 golden）。详见 [image-routing.md](image-routing.md) §1K 分辨率横切规范。

## 生图后端铁律

**生图工具选择、参数、禁用项、数据图防幻觉等所有规则统一在 [image-routing.md](image-routing.md)。** 进入任何生图环节前必先读取该文件。核心原则：严禁调用 Agent 原生 `generate_image` / `internal_image_gen` / `imagine`（会破 2.35:1 封面比例）；数值型图表（雷达/折线/柱状/饼）严禁大模型生图，必须用 `matplotlib` / `pyecharts` 本地脚本渲染并把 .py 留在文章目录内供复核。

## 组件小图铁律

文章排版强依赖一张 1:1 配图——`hero.png`（配套文章导读栏右侧）。写作流水线必须确保它在素材库就位。**这张图尺寸很小，不打水印**——`add_logo.js` 已在工具层内置跳过清单（`hero.png`、以及历史遗留的 `bgm_cover.png` / `music_cover.png` 兜底兼容），批量执行 `"素材/*.png"` 时会自动跳过，无需手动过滤。

## hero.png 唯一位置铁律

`hero.png` 的**唯一合法位置是导读栏内部**——由 `format_layout.py` 的 `process_lead` 自动从 `素材/hero*.png` 取图嵌入。

**严禁**在 `定稿.md` 里手动写 `![导读图](素材/hero.png)` 或类似图片引用——经 markdown→html 转换后会留在正文，与导读栏内的 hero 重复展示。

**自动防御**：`format_layout.py` 已在 `_purge_orphan_hero_in_body` 中检测并清除正文内独立的 hero 图，但规则层仍要求作者**不要在 .md 里手动嵌 hero**（避免依赖防御兜底）。历史 .md 残留的手动 hero 引用属于历史遗留，新文章**禁止照搬**。

## H2 只写纯标题铁律（禁止手写 PART 前缀）

MD 里 `## 二级标题` **只写主标题本身**，**严禁**手写 "PART NN｜" / "PART NN |" / "PART NN - " 前缀。

**触发原因**：`format_layout.py` 的 `_build_part_h2` 会自动在 H2 左侧生成竖排 "NN / PART" 小块、右侧放主标题。若 MD 里写 `## PART 01｜新国标到底定了什么`，右侧主标题原样显示为 "PART 01｜新国标到底定了什么"——与左侧的 "01 / PART" 小块重复，视觉上变成两个 PART 01。

**操作规范**：
- ✅ 正确：`## 新国标到底定了什么`
- ❌ 错误：`## PART 01｜新国标到底定了什么` / `## PART 01 | ...` / `## Part 1｜...`

**副标题处理**：副标题（如"新国标拆解"）写到 `article-meta.yaml` 的 `part_subtitles` 数组，按 H2 序号对齐；**不**写在 MD 的 H2 行内。

**自动防御**：`_clean_h2_text` 已加 `^PART\s*\d+\s*[|｜]?\s*` 正则剥离（兜底），但规则层仍要求**一次到位**，不依赖兜底。大纲阶段给主笔的 H2 示例也禁止带 PART 前缀。

## H3 只写纯标题铁律（禁止手写"一、" / "1." / "①" 编号前缀）

MD 里 `### 三级标题` **只写主标题本身**，**严禁**手写中文数字 `一、二、三、`、阿拉伯数字 `1. 2. 3.`、圈号 `①②③`、括号编号 `(1) （一）` 等任何编号前缀。

**触发原因**：`format_layout.py` 的 `process_h3` 会自动在 H3 左侧生成主题色【圆角方块】数字编号（1、2、3、4… 按 PART 内顺序重置）。若 MD 里写 `### 一、独立的侧边栏 UI`，方块"1"+ 标题里的"一、"会同位置叠加显示，视觉上变成 `①一、独立的侧边栏 UI`，编号重复。

**操作规范**：
- ✅ 正确：`### 独立的侧边栏 UI，分成三个区`
- ❌ 错误：`### 一、独立的侧边栏 UI` / `### 1. 独立的侧边栏 UI` / `### ① 独立的侧边栏 UI` / `### （一）独立的侧边栏 UI`

**自动防御**：`_clean_h3` 已加防御性剥离（中文数字/阿拉伯数字/圈号/中英括号编号），但规则层仍要求**一次到位**，不依赖兜底。大纲阶段给主笔的 H3 示例也禁止带任何编号前缀。

## H2 副标题预填铁律

`article-meta.yaml` 的 `part_subtitles` 必须在**首次跑 `format_layout.py --all` 之前**就按 H2 数量按序填好。

**触发原因**：H2 → PART 编号格式只有第一次有完整重排机会；首次 `--all` 跑完后再补 yaml 跑 `--h2`，原本会因为「PART 块已存在」被跳过。

**当前状态**：`process_h2` 已升级支持「先还原已转换块为裸 H2 再重建」（`_revert_part_h2`），所以二次跑不再失败。但**仍要求 yaml 一次到位**，原因：
1. 二次跑会清掉读者可能已手动微调的 PART 区视觉（覆盖式重建）
2. autopilot 状态卡的「洗色」步骤要求一次跑通，不该依赖人工兜底

**操作时机**：在写作阶段确定 H2 大纲时即写入 yaml；进入 layout 阶段前 `pipeline.py verify layout`（如启用）应做「`H2 数 == part_subtitles 长度`」断言。

## BGM 非可选铁律

🔴 **所有文章都必须配主题曲 BGM**——不分文章类型，工具评测 / 教程 / 清单 / 盘点这类"看着不像需要配乐"的也一律配，**不得以"这篇不需要音乐"为由跳过 `bgm` 阶段**。

- autopilot 的 STAGE_ORDER 已默认含 `bgm`（layout 前）；**手动 / 分阶段写作时同样必须**跑 `generate_article_bgm.py` + `pipeline.py verify bgm`，再进排版。
- 唯一例外：用户当次明确说"这篇不要音乐"。否则缺 BGM = 这篇没写完。
- 踩坑教训：曾自作主张判定"AI 工具评测不需要配乐"跳过 BGM，被纠正后补上。

## AUDIO-CARD 位置铁律

> `generate_article_bgm.py` 生成的 `<!-- AUDIO-CARD-START -->`…`<!-- AUDIO-CARD-END -->` 块**必须放在 `定稿.md` 最末尾**（脚本自动追加），由 `format_layout.py --all` 的"音乐栏前置"逻辑自动上移到导读栏下方渲染。
> 🔴 严禁放在文章开头（会被 baoyu-md 误吞进 `<meta description>` 导致 head 崩坏）。
> 注：`contracts.py` 的 AUDIO-CARD publish 校验是**软兜底**（技术上不存在不阻塞，仅用于兼容历史无 BGM 文章）；但按上方「BGM 非可选铁律」，**新文章一律配 BGM**，真正的硬关卡是 BGM stage 的 `pipeline.py verify bgm`（硬查 mp3 + 卡片），手动 / 分阶段流程也必须过这道。

## AI 残留物清除铁律

发布前，定稿正文里**绝不能残留**从 AI 抓料 / 生成时带进来的痕迹——它们的存在本身就暴露"没清理干净"，与文字写得多像人无关：
- **AI 工具 URL 尾巴**：`?utm_source=chatgpt.com` / `claude.ai` / `perplexity.ai` 等参数，粘链接时一并带进来的，删到只留干净 URL。
- **chat 引用标记**：`citeturn0search1` / `oai_citation` / `turnXsearchX` 这类模型检索残留标记。
- **未填占位符**：`[待核实]` / `[待补充]` / `[INSERT ...]` / `[⚠️ 请在此补充…]`（人类经验插槽的占位符）/ 日期占位 `2026-XX-XX`——发布前必须填实或删除，不许带着占位符发出去。

机器兜底：`contracts._AI_ARTIFACT_HARD` 扫**原文**（不经 strip），排版 preflight 命中即 `exit 2`。但机器只认固定 token，别的残留仍靠发布前肉眼扫一遍。

## 信息来源格式铁律

文末的「📎 信息来源」**严禁使用 `###` H3 标题**（会被 `format_layout.py` 转为时间线格式）。必须用 `<section style="font-size: 12px; color: #999;">` 包裹的普通 `**粗体**` 段落，与正文视觉上明确区分。

## 知识图与插图位置铁律

文章内的数据对比插图（如雷达图、横评表）必须嵌入在正文的对应段落中，**绝不可堆砌在文末**。此外必须生成一组**≥4 张贯穿全文**的信息图（知识图卡片）：**开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1**，分别嵌入开篇、正文中段、结尾对应位置（贯穿全文，**不再是文末堆砌 2 张**的旧模型）。机器校验见 `contracts.py:verify_infographic_set` / `pipeline.py verify infographic`（≥4 张 + 构成 + 1K）。

## 时间线 H3 格式铁律

如果文章中出现并行排列的 3-5 条关键点、决策树或问题清单（例如"国内用户的几个现实问题"），**禁止使用数字有序列表（`1. 2. 3.`）**，必须将每一个要点写成 `###` 子节点（如 `### 官方定价没涨`），以便排版阶段自动触发"主题色编号【圆角方块】+竖线"的时间线格式。

🔴 **写 H3 时不带编号前缀**——圆角方块数字由 `process_h3` 自动生成，主笔写 `### 1. 官方定价没涨` 会和方块编号撞，必须写 `### 官方定价没涨`（详见上方 [H3 只写纯标题铁律](#h3-只写纯标题铁律)）。

## 文章导读不内嵌音乐栏

导读内容由正文顶部的 `> **导读：** ...` 引用块提供（见 writing.md），**不要**在 `<!-- AUDIO-CARD-START -->`…`<!-- AUDIO-CARD-END -->` 块内部再嵌入「📍 文章导读」段落——否则排版前置后会出现两个导读，造成内容重复。

## 作品库 cover 字段铁律

封面字段由 `pipeline.py archive` 从 `素材/cover.png` **自动写入** `{数据目录}/works.yaml` 的 `cover` 字段；`articles.md` 是从作品库自动生成的视图（禁止手改）。AI **不得**手填或手改 `articles.md` 的封面行。`cover` 字段缺失要在 article-meta / cover 阶段解决（确保 `素材/cover.png` 就位），不要在归档/视图层补。否则 `generate_recommend_html.py` 会回退到默认 logo，导致推荐阅读卡片显示的是 logo 而非封面。

## pipeline 状态校验铁律

`pipeline.py verify <stage>` 必须校验对应阶段产出物的**文件是否实际存在**（cover / hero 的 PNG，信息图集合 `infographic*.png` ≥4 张，`pipeline.py verify bgm` 硬查 mp3 + AUDIO-CARD 卡片「本文主题曲」是否就位），不能只根据 `.state.json` 的标志位判定为 done。进入 layout/publish 阶段前若发现素材缺失，必须 fail-fast 并阻断流水线；历史 state 若标 done 但文件不存在，需强制回退到 pending。

## subagent 协作铁律（编排器）

编排器模式下，subagent 是"无状态执行单元"，状态与恢复决策权完全归编排器：

- 🔴 subagent 不得自行 `pipeline.py skip` 绕过失败 —— 失败只回传现场，恢复决策归编排器
- 🔴 subagent 不得读写 `.state.json` —— 单一状态写者只有编排器
- 🔴 subagent 必须回传结构化错误现场（阶段名/错误/已尝试），禁静默吞错

## 封面内容提炼前置铁律（content-derived 方法）

🔴 **动笔写 montage-evidence prompt 前，必须先从定稿里抽出「封面四件套」并写进 cover.md 顶部 `CONTENT CONTEXT` 注释块**：① 主题一句话 ② 调性（冷静拆解 / 反差观察 / 工具实操…）③ 全文最锋利的一句结论或反差（将进 L2 主题色末段 + 英文 ghost）④ 一个能承载该结论的具象隐喻物件（将进右侧主物件）。

- 四件套没抽完不准写 prompt——封面的**主物件 / 徽章 / 英文 ghost 本质都是文章内容的视觉压缩**，跳过提炼就会画成"好看但与文章无关"的装饰图（同源教训：信息图"风格对、信息为零"）。
- 🔴 **贴内容自检**：若主物件 / 徽章数字 / 英文 ghost 三词换一篇文章照样能用，说明它们没贴住本文，打回重提炼。

## 封面图文字样式铁律

`cover.md` prompt 必须满足（**文字层不可改，背景与构图按风格池切换**）：
1. **关键词高亮**：主标题只给核心关键词（如数字、人物、对比词）上主题色 #2F6F8F + 加粗，其余部分保持白/浅灰。严禁整句全绿或全黑。
2. **副标题分层**：副标题拆成 3–4 段不同字重/透明度/强调，制造视觉层次——比如"AI 时代最稀缺的不是 / 技术能力 / 而是 / 判断力"四段分别对应 gray-300 / white-500-strikethrough / gray-400 / primary-800-glow。严禁副标题单一字重一行到底。
3. **背景色板**（只在两种深色里选，由所选风格决定，严禁自由发挥）：
   - 深炭 `#0E0E10`（风格 A briefing / C montage-evidence / D montage-pipeline 用）
   - 纯黑星河 `#030712`（风格 B noir，近黑偏冷蓝 + 银河若隐若现）
   - 严禁纯黑 `#000`、亮背景、未列入的任何色调
   - 历史下架背景：墨绿星河 `#12252E`（obsidian）已下架，仅老文章保留，新文章不再可选
4. **文字位置铁律**：文字必须在画面的**右侧**（左图右字）或**右上对角**（对角式）或**左半**（montage 左文右拼贴），**绝不允许上下堆叠**（文字在视觉主体的正上方或正下方）。原 `monument`（中轴居中）和 `horizon`（横向贯穿 + 上下贴边文字）两种上下堆叠版式已删除——实测会严重挤压主标题字号，在缩略图上不醒目。
5. 🔴 **风格固化为 `montage-evidence`**：原 5 风格池（briefing / noir / montage-evidence / montage-pipeline / montage-starry）已 **override 为统一 montage-evidence**，其他 4 种封存。生成 cover.md prompt 时**必须**：
   - 先读 [cover-styles.md](cover-styles.md) **顶部 override** 段（H1 后第一段）
   - 严格套用 `montage-evidence` 模板（参考仓内标杆 prompt）
   - 三件套必带：① 英文 OVERSIZED GHOST-WATERMARK（3 关键词 × 连接，~155% L1 字号，下部羽化）② 中文 L1 + L2（关键词主题色）③ 3 个 quiet-pill emoji 胶囊 + 右侧拼贴区（主物件 + 2-3 个黑底主题色描边徽章 + 虚线箭头）
   - **严禁套用旧 conceptual 模板**（已被 override 封存）
   - 自动选择算法（亚型回避 / 近 3 篇回避 / starry 频率上限）**全部失效** -- 默认走 montage-evidence，不做风格挑选
   - 例外：`article-meta.yaml` 显式填其他 `cover_style` 值时可激活（需明确意图，不建议）
6. 🔴 **禁止 AI 在画面渲染品牌名/编号/署名小字**：
   - **严禁**让 AI 在右下角或任何位置写品牌名 / 账号名 / 期号（"No.XX"）/ "·深度文" / 署名等品牌识别文字
   - 原因：`add_logo.js` 在排版后会自动在右下角叠加品牌 Logo（按背景亮度选黑/白版）。AI 再渲染品牌名小字会与 Logo 视觉重复。
   - 写 cover.md prompt 时必须显式加一句 forbidden：`No brand name, account name, issue number, or any signature text rendered in the image — the brand logo will be added in post-processing.`
   - 主标题、副标题、关键词高亮等"内容文字"照常写——只禁"品牌识别小字"
7. **三级字号 + 字重落差**：封面文字三层尺寸肉眼可辨递减——**L1 > L2 > 胶囊文字**，胶囊文字固定为 L1 字号的 ~30% 且明显小于 L2（胶囊是最末级参数标签，不许大到接近 L2 抢主标题权重）。中文 L1 用最重字重（extra-bold / black，主结论）、L2 降一档（bold / semibold，补充语境），靠**字重差**立主次，配合 L2 末尾词主题色，做出"一眼看到 L1、再读 L2"的阅读顺序，**严禁 L1=L2 同字重一刀切**。
8. 🔴 **封面 prompt FORBIDDEN 必带锚句清单**（写完逐条对勾，缺一不算合格）：
   - ① 标题用文章原标题，禁模型自创 / 改写
   - ② 中文 L2 单行不拆，逗号是标点非断行点
   - ③ 禁用 `<green></green>` 等 XML markup 标主题色（会被当断行致拆行 + 字符重复），改写「后 N 字 in PRIMARY #2F6F8F」
   - ④ 禁渲染品牌名 / 编号 / 署名小字：`No brand name, account name, issue number, or signature text rendered in the image — the brand logo will be added in post-processing.`
   - ⑤ **hex 与色名禁入图**：`Color hex codes (#2F6F8F / #0E0E10 …) and color names (primary / charcoal) are rendering guidance ONLY — never render any hex code, color name, or palette label as visible text in the image.`（部分模型文字渲染强，易把反复出现的 hex 当图内文字画出来）
   - ⑥ 英文 ghost 极深灰 #1F1F25，一眼读不出才算对

## 封面文字禁补字铁律（text-correction policy）

🔴 **cover.png 上的标题 / 副标题 / 徽章文字若糊字 / 错字 / 不清晰，严禁用 Pillow / ImageMagick / SVG / canvas 在生成位图上覆盖、描边、重写、抹除文字**——盖图后字体与抗锯齿对不齐主题色、廉价感立现。唯一允许的修法：① 改 prompt（把出错文字单独强调 `render exactly`）重生；② 降一档文字密度重生（如某行长文案改短、或该信息改由徽章承载）；并保留旧候选对比。

- `gen_img.py` 内置的 PIL 只许做缩 1K / 裁切 / 补边 / 压缩，**绝不许改文字像素**（顺手 overlay 补字 = 本铁律头号违规）。

## 文章流程必经 pipeline 铁律

🔴 **任何 `{数据目录}/{N}/` 文章工作（含 compaction 续接、局部改稿）都必须走 `pipeline.py` 状态机逐项打勾，严禁把 baoyu / format_layout / 发布工具当散件直接调、绕过清单。**

- **开局**：进入任何 `{数据目录}/{N}/` 目录第一件事 `pipeline.py status`，看 STAGE_ORDER 哪些 stage 没过，逐项补齐。别把"改稿"当成可以跳过 pipeline 的散活。
- **发布前硬闸**：调发布工具之前**必须先** `pipeline.py verify publish --pre` 通过并写 `_publish-ready.json`。它要求 publish 之前所有阶段均为 done，并硬查 canonical prompt、视觉 receipt、cover/hero/≥4 信息图与 HTML。微信返回 media_id 后再执行 `done publish draft_media_id=...` 写最终 receipt。任一命令非零退出即不准继续。
- **按 skill 既定两层路由走，别用全局默认**：先走对应 baoyu producer，再由 child skill 选择 renderer；BGM 按「BGM 非可选铁律」。
- **踩坑教训**：曾没走 pipeline、发布工具直调绕过 `verify_publish_assets`，连漏 BGM + hero，还误用全局默认生图后端。教训＝skill 有计划但没进它的计划，发布闸不强制就会被绕过。

## 发布完整性铁律

进入 publish 阶段前必须逐一校验素材到位：`cover.png`（2.35:1，1K）、`hero.png`（1:1，无文字）、**信息图集合 `infographic*.png` ≥4 张（2×9:16 开篇/结尾 + ≥2×16:9 中间，1K）**、**BGM（`{歌名}.mp3` + AUDIO-CARD 卡片）**。任一缺失或信息图不足 4 张均视为 publish 阻塞，必须补齐后再走发布工具。
> 🔴 **信息图无豁免**：评测 / 截图密集型文章**也不豁免** ≥4 信息图——截图与信息图**并存**（文章内图片两者结合稍多可接受），截图**不替代**信息图。
> 🔴 **BGM 为强约束，但当前非机器硬门（如实口径）**：BGM 是**流程强约束**（见「BGM 非可选铁律」，一律配、缺 BGM = 没写完），但机制上**不是**代码强制的发布硬门，别把它当成 pipeline 会自动拦下的闸：
>   - `pipeline.py` 的 `NEVER_SKIP_STAGES` **不含 `bgm`** —— `pipeline.py skip bgm` **无需 `--force` 即可绕过**（不像 writing/cover/infographic/layout/publish 那样被黑名单拦）。
>   - `verify_publish_assets`（publish 门）对 AUDIO-CARD 缺失是**软兜底**：仅当 `.state.json` 里 `bgm` 阶段已标 `done` 才硬拦 AUDIO-CARD 缺失；`bgm` 为 `pending`/`skip`/无 state 时**放行**（兼容历史无 BGM 文章）。因此「跳过 bgm → publish」这条路径校验门**不会**报错。
>   - 真正硬查 mp3 + AUDIO-CARD 卡片的是**单独的** `pipeline.py verify bgm`，但它只有在你主动跑到 bgm 阶段时才触发，不是 publish 阶段的前置门。
>   - 保留合法例外：用户当次明确说「这篇不要音乐」时可 `skip bgm`。
>   - ⚠️ 结论：BGM 的「必配」靠**流程纪律 + autopilot STAGE_ORDER 默认含 bgm**保证，**不靠**校验门兜底。与 [autopilot.md](autopilot.md) §step 8 已有的诚实表述一致。同理 ≥4 信息图的硬闸 = `pipeline.py verify infographic`（一直存在，绕过 pipeline 就不触发）。

## cover / hero 角色分离铁律

`cover.png` 和 `hero.png` 是**两个独立产物**，绝不可混用文件名：

| 文件 | 用途 | 尺寸 | 文字 | 谁生成 |
|---|---|---|---|---|
| `素材/cover.png` | 头图 / 文章主封面 | 2.35:1，≥1K | 有（标题 + 副标题 + emoji 胶囊）| `/baoyu-cover-image` 或 cover prompt |
| `素材/hero.png` | 导读栏右上角小贴图 | 1:1，1K | **无文字**，纯装饰 flat-vector | 单独的 hero prompt，主体常为文章核心隐喻物件 |
| `素材/bgm_cover.png` | 音乐卡片封面（不参与 publish 阻塞） | 1:1，1K | 一般无 | BGM 阶段 `generate_article_bgm.py`（走 gen_img.py） |

🔴 **禁止在 cover prompt frontmatter 写 `output: "../hero.png"`** — 这会把封面图覆盖到 hero.png，导致导读栏小贴图变成被压扁的 2.35:1 大封面。
`pipeline.py verify cover` 现已强制校 `素材/prompts/*cover*.md` 的 frontmatter，发现 output 指向 hero 文件名会 fail。

## 不可 skip 的 stage 铁律

下列 stage 是发布必需的硬性产物，`pipeline.py skip <stage>` 拒绝执行（除非加 `--force` 显式确认）：

- `writing` — 没正文还发什么
- `cover` — 没封面无法推草稿
- `infographic` — ≥4 张贯穿全文信息图（2×9:16 + ≥2×16:9，参见上方「知识图与插图位置铁律」），缺了 publish verify 会拦
- `layout` — 没排版的 md 不可发布
- `publish` — 没推草稿就没发布

踩坑教训：曾跑 `pipeline.py skip infographic`，pipeline **直接接受**，导致整篇文章漏了整组信息图直到 publish 后才被发现。`cmd_skip()` 现已加 `NEVER_SKIP_STAGES` 黑名单 + 友好错误提示。

## 信息图风格固化铁律

一组 ≥4 张贯穿全文的信息图（`infographic*.png`：2×9:16 开篇/结尾 + ≥2×16:9 中间）**必须**满足：

1. **必走 `/baoyu-infographic` skill**，禁止手写 SVG / 直接调 `baoyu-image-gen` / 用 `baoyu-diagram` 替代（baoyu-diagram 只给"精确流程图"用，不给"信息汇总卡"用）
2. **风格按信息架构主轴二选一**：`infographic_subject: ai-product`（具名 AI 模型/工具/产品/功能作卡片或对比轴）固定 `claymation`；`infographic_subject: phenomenon`（现象/商业/人文关系作主轴）固定 `morandi-journal`。混合题材一律**产品/模型轴优先于趋势结论**。同篇不混风格；两字段都必须在 `article-meta.yaml` 显式指定。craft-handmade 等其余风格只作历史兼容，新文章禁止。
3. **必须用 v2 日志记录**：`pipeline.py log infographic baoyu-infographic --output ... --prompt 素材/prompts/final/... --renderer ... --model ... --cmd "..."`。没有 producer + renderer + model + prompt/output hash 的 PNG 视为来源不明

踩坑教训：曾手写 SVG 跳过 baoyu-infographic 流程，pipeline 因为没记录在 .gen-log 里**没拦下来**。`verify infographic` 现已加 3 道关卡：
- gen-log 必须有 infographic 记录
- 记录的 producer 必须是 baoyu-infographic；renderer 单独记录，不能互相顶替
- 每张最终图的最新精确 output 记录必须含 `--style claymation` 或 `--style morandi-journal`，并引用实际 prompt 文件；meta / analysis / structured / prompt / gen-log / final-set 六处必须一致
- 发布前必须对 logo/压缩后的最终图逐张 QA，写 `_visual-qa.md` 并执行 `pipeline.py seal visual`；`done publish draft_media_id=...` 内联硬查，`--force` 不准绕过

## 模型对比内容铁律

写模型对比 / AI 产品评测 / 新品速递类文章时，默认只讨论各厂**当前官网在售或刚发布**的顶级型号（旗舰/Pro/Ultra/Max/最新代号）。旧代或已过时型号，除非用户明确要求做"XX 代 vs YY 代"的纵向对比，否则不主动提——读者对旧模型会"没有感觉"，混着讲会冲淡文章价值。

涉及具体版本号、发布时间、价格、能力参数等数字时，必须以**官网为第一信源**，再用权威科技媒体（如 The Verge / Ars Technica / 36氪 / 量子位）**交叉核对**。信息无法确认时显式标「待用户核实」，不得凭训练知识或搜索摘要硬给数字。

## 敏感议题用词铁律（平台防下架）

写文章涉及 "翻墙、VPN、代理、境外 API 访问、境外 AI 产品使用条件" 等敏感主题时，默认使用**中性表述**：

| ❌ 原表述 | ✅ 改用 |
|---|---|
| 需要翻墙 / 用 VPN / 科学上网 | 需要海外网络环境 / 需要境外访问条件 |
| 登录 Google / OpenAI | 在支持 Google（OpenAI）服务的地区 |
| 挂代理 | 使用合规的网络访问方式 |

排版完成后、进入 publish 阶段前，主动对全文扫描涉敏段落，列给用户确认再发布。**生产级 guardrail**——曾有一篇因涉翻墙用词被公众号平台下架，触发即阻断发布流程。

## 破折号统一用 `--`（禁止全角 `——`）

写给读者看的文字内容里，所有需要破折号的位置，**统一用两个英文连字符 `--`** 替代中文全角破折号 `——`。这是本 skill 的硬规则。

**操作规范**：
- ✅ 正确：`下面这件事很重要 -- 你必须知道`
- ❌ 错误：`下面这件事很重要——你必须知道`

**适用范围**（所有 → 读者的文字）：
- 大纲、正文、定稿、改稿、磨稿
- 文章 frontmatter 的 description / subtitle
- 各平台摘要 / 文案
- 标题、章节副标题、金句、划重点卡片、KPI 卡片
- 包括 markdown 引用块、加粗、列表项、表格里的破折号
- 发布工具推送的 HTML 里也要统一

**不适用**（保留 `——`）：
- 历史已发布的文章（articles.md、history.yaml 里的旧条目）—— 不追溯
- 引用他人原文（直接引语里保持原作样式）
- skill 内部 reference / 注释 / 文档（这些不是给读者看的内容）

**Why**：写作偏好。`——` 在部分平台渲染下行高诡异、转图时排版不齐、跨平台一致性差；`--` 在所有渠道渲染稳定。

**写作期立即执行**：
- 主笔写每段时实时用 `--`，不用 `——`
- 如有遗漏，磨稿阶段全局 `Find: ——` `Replace: --` 一次性清理
- format_layout.py 排版前可加可选的 `--` 校验提醒（`--check` 模式）

**自动防御（可选）**：`format_layout.py` 可在 layout 阶段扫一次正文里有无 `——`，发现即警告（不强制阻断，只提示作者磨稿时清理）。
