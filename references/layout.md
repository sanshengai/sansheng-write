# 排版发布全流程

> 微信公众号从 Markdown 定稿到发布草稿箱的完整规范。  
> **可从任意步骤开始**--每步均自包含，不需要从头读。

> 本阶段由编排器单线程执行；契约见 references/orchestration.md；正文逻辑不变（orchestrator=off 与既有完全一致）。

## 排版色值速查

品牌色 `#2F6F8F` 等基础常量见 SKILL.md。以下为排版专用的扩展色值：

| 用途 | 值 |
|------|-----|
| 浅色背景（blockquote） | `rgba(47, 111, 143,0.05)` |
| 分隔线 | `#EEEEEE` |
| 副文字/注释 | `#888888` / `#999999` |
| Logo 水印规格 | 右下角，图片宽度 12%，透明度 35%，**按右下角亮度自适应选 logo**（浅底/米白 → `logo-black.png` 深字；深底/彩色 → `logo.png` 白字；阈值 128。曾有 add_logo.js 算了亮度却没用、永远贴白 logo 导致浅底隐形的 bug，现已修复）。**禁止在生图 prompt 中加文字水印** |
| 图片质量 | **统一 1K** |

---

## 视觉层级三层表 + 用色配额（排版前自查全文彩色总量）

> 目的：把散落各处的"金句 ≤2 / 要点卡每 800-1200 字 / 配图每 300-500 字"频率约束收成一张总表，排版前一眼自查"全文彩色 / 强调是不是超量"。防两种病：① 强调满屏 = 没有重点；② 通篇灰白 = 没有锚点。

### 三层递进（所有文体通用）

| 层级 | 手段（我方组件） | 作用 | 频率配额 |
|------|-----------------|------|---------|
| **锚点层**（最强） | 金句卡（quote-card）/ 要点卡（`--takeaway`）/ 深色强调 | 核心结论、金句、最强视觉焦点 | **全文强锚点 ≤5 处**；金句卡 ≤2/篇；要点卡每 800-1200 字一个 |
| **标记层**（高频） | `<mark>` 一级主题色 `#2F6F8F` 加粗（核心）/ 二级主题色 `#7FB0C4`（次级） | 正文关键词强调、可扫读锚点 | 每段酌情；**全文加粗串起来 ≈ 能概括核心 70%**（见 [anti-ai-filter.md](anti-ai-filter.md)）；一段内强调 ≤2 种手段 |
| **容器层**（按需） | 表格 / 深读模块 / 链接卡 / Case 时间线 / 提示块 / 浅色底卡 | 引用、旁注、结构化信息、数据 | 按内容出现处；点缀组件种类 ≤3/篇（见步骤2.5 配方表） |

### 用色配额（全文彩色总量，超量即删）

- **主题色只做锚点 + 关键词点缀**，不承担正文阅读；一段内高亮 ≤2 种手段。
- 金句卡 ≤2/篇 · 要点卡每 800-1200 字 · 配图每 300-500 字 · 强锚点 ≤5 处 · 点缀组件 ≤3 种。
- 二级主题色 `#7FB0C4` 只用在"能加粗 / 有底色"处（次级标识 / 次级标题），**小字正文里慎用**（对比度偏低）。

> **灰阶承重原则**：约 90% 文字交给一套中性灰阶（正文 `#333` / 深色标题 `#26333a` / 说明 `#8a929a` / 弱提示 `#b0b6bb`），彩色只点缀--详见 [design-tokens.md · 色彩角色分工](design-tokens.md)。

---

## 步骤1：Markdown → HTML 转换

**前置检查**（排版前强制断言，任一不通过则拒绝执行）：

> 🔴 **2026-05-21 落地**：以下检查 1-7 由 `contracts.verify_publish_assets()` 自动执行，
> 由 `format_layout.py --all/--h2` 在排版前调用。任一阻塞错误 → exit 2（除非 `--skip-preflight`）。
> 另外 `contracts.verify_article_meta_lead()` 校验 `article-meta.yaml` 的 lead 块完整性（line1/line2/subtitle 必填，缺一项给警告但不阻塞）。

1. ✅ 工作目录下存在 `定稿.md`
2. ✅ `定稿.md` 含 frontmatter（title + description）；只有 H1 也可兜底但会警告
3. ✅ `定稿.md` 中**不包含** `[插图]` 占位符文字--所有图片必须已替换为 `![alt](path)` 语法
4. ✅ `素材/` 目录下的 `.png` 文件**都在** `定稿.md` 中有对应的 `![` 引用（防止图片生成了却忘记嵌入；自动排除 cover/hero/bgm_cover/logo）
5. ✅ `定稿.md` 中的 `<!-- AUDIO-CARD` **只出现一次且位于文件最末尾**（距文末 ≤800 字符），严禁出现在 `##` 标题与正文之间
6. ✅ 文末「📎 信息来源」**不使用** `###` H3 标题--应使用 `<section style="font-size: 12px; color: #999;">` 包裹的普通粗体
7. ✅ 信息来源中的条目**不使用 MD 链接语法** `[title](url)`--应为纯文本标题。MD 链接语法会触发 `--cite` 生成重复的「引用链接」底部展开
8. ✅ `baoyu-markdown-to-html` 转换时**不传 `--cite`**--信息来源已作为独立段落存在，底部引用会造成重复

**输入**：`定稿.md`  
**输出**：`定稿.html`（含 `<div id="output">` 包裹的正文）

> 全流程统一使用 `定稿.html` 文件名，不做中途改名。

### 1a. 执行转换

> **转换前先规范标点**：`python "$SKILL/scripts/normalize_cjk_punctuation.py" 定稿.md` 一键把正文中文间误用的半角 `,;:!?` 转全角（确定性、零误伤代码/URL/时间/`.mp4`/`--`）。不先做这步，后面 `format_layout --check` 的半角硬门会 exit 2 拦下。

```bash
baoyu-markdown-to-html 定稿.md --theme default --color "#2F6F8F" --keep-title
```

`--color "#2F6F8F"` 让 baoyu 将 H2/strong/blockquote border 直接输出为主题色，减少后续替换量。  
**有效 theme 值**：default / grace / simple / modern（不要自造 theme 名，baoyu 只有上面这四个）

🔴 **必带 `--keep-title`**：本 skill 的文章正文一律无 `# H1`（标题写在 frontmatter `title`，正文直接以 `## ` 开篇）。baoyu-markdown-to-html 默认 `keepTitle:false` 会把**正文第一个 heading 当文章标题吃掉**，于是 H2 少一个、`format_layout` 报「H2 数量(N-1) ≠ part_subtitles 长度(N)」并退出。显式加 `--keep-title` 才能保住全部 H2 ↔ part_subtitles 对齐。

🔴 **baoyu skill 首次用 / 换机必先装依赖**：带 `scripts/` 的 baoyu skill（baoyu-markdown-to-html、baoyu-post-to-wechat 等），plugin 同步只带源码不带 `node_modules`。首次报 `Cannot find package 'baoyu-md'` → 到该 skill 的 `scripts/` 跑 `bun install`；若紧接着报 `Export named 'preprocessMermaidInMarkdown' not found`（plugin 源码超前于已发布的 npm 包，非本机落后），补 `bun add baoyu-md@0.1.1`。两步做完即通，是一次性初始化。

### 1b. 三项全局替换（机械执行，无需判断）

```
① #d14        → #2F6F8F          （行内 <code> 红色 → 主题色）
② background: #f7f7f7  → background: rgba(47, 111, 143, 0.05)   （blockquote 灰底 → 浅色底）
③ 删除正文中的封面图 <img> 标签（src 含 cover 的那一行）
```

> 若转换时未用 `--color`，还需额外替换 `#0F4C81 → #2F6F8F`（蓝色 → 主题色）。

---

## 步骤2：HTML 组件自动清洗与注入

**前置检查**：工作目录下存在转换后的 `定稿.html`，且含 `<div id="output">`。

**输入**：`定稿.html`  
**输出**：`定稿.html`（组件已全部清洗和注入完成，原地更新）

> ⚠️ **强烈警告：不可再由 AI 代理手工编写正则或在脑内瞎补替换规则。必须且只能通过执行专属的高幂等程序脚手架去完成底层替换。** 
> *如果您在阅读此段文字，请直接打开您的终端隐式执行，严禁继续人肉/AI肉身替换。*

### 2a. 一键修缮指令（必跑）

AI 排版助手需要在包含 `定稿.html` 的当前工作目录下，调用以下 Python 脚本完成所有的**H2格式装配**、**表格套主题色+列宽+字号**、**AI提示词残留清除**、**引用色系清补**、**文首导读栏注入**及**末尾推荐名片注入**：

```bash
# 脚本位置：scripts/format_layout.py（本 skill 内）
# 默认 H2=PART 二级大标题，H3=时间线三级子标题
python $SKILL/scripts/format_layout.py 定稿.html --all
```

**标题层级与排版对应关系（固定规则）**：

| Markdown 层级 | 排版样式 | 视觉效果 | 说明 |
|--------------|---------|---------|------|
| `## H2` 二级标题 | **PART 编号格式** | 01 PART 左侧竖排 + 右侧标题 | 文章骨架大章节，如"认识 Claude Code""六种打开方式" |
| `### H3` 三级标题 | **时间线格式** | 主题色编号【圆角方块 24px】 + 主题色粗体标题 + 浅灰竖线包裹内容 | PART 内部的子节点。H3=方、H4(有序列表)=圆（方圆分级） |
| 有序列表 `1. 2.` = **H4 子级** | **圆形编号徽章** | 主题色【圆形 20px】编号 + 悬挂缩进（比 H3 方块略小、无竖线） | H3 之下再细分的并列步骤/要点 |
| 无序列表 `- ` | **主题色箭头 ➤** | 主题色 ➤（U+27A4 glyph）+ 悬挂缩进 | 普通并列项 |

> **写作约定**：Markdown 中 `##` 全部渲染为 PART 大标题，`###` 全部渲染为时间线子节点。脚本会自动处理，无需手动指定参数。

**导读栏自定义参数**（**每篇文章都应传入**，不传则使用通用占位文字，效果很差）：

> AI 排版助手在执行 `--lead` 时，**必须**根据文章主题提炼以下参数：
> - `--lead-line1`：标题第一行（≤8 汉字，黑色，如"六种打开方式"）
> - `--lead-line2`：标题第二行（≤8 汉字，主题色，如"一篇选对"）
> - `--lead-subtitle`：副标题描述（≤15 汉字，灰色）
> - `--lead-tag1` / `--lead-tag2`：底栏胶囊标签（≤4 汉字）
>
> 
> 🔴 **H2 副标题（必须传入，每次都容易遗漏！）**：
> AI 排版助手在执行转换时，**必须**提炼所有 H2 的核心词或短句，通过 `--part-subtitles` 传入（用英文逗号分隔，数量需与 H2 数量一致）。如果不传，则 H2 层级只有主标题，下方无灰色副标题，视觉效果大打折扣。**每篇文章排版时必须主动检查是否已传入此参数。**
```bash
python $SKILL/scripts/format_layout.py 定稿.html --all \
  --lead-line1 "顶级模型点兵" --lead-line2 "视频生成篇" \
  --lead-subtitle "一篇文章看懂中美八大主力选型" \
  --lead-tag1 "AI横评" --lead-tag2 "干货实测" \
  --part-subtitles "看懂大盘,剖析底层逻辑,实操指南,总结与避坑"
```

**【脚本幂等性保证】**
该 `format_layout.py` 内置极高幂等性，不限次数执行不产生垃圾堆砌，您可以随时通过附加的细分参数接管某个断点：
- `--h2`: 刷新原生 H2（固定 PART 编号格式）+ H3（固定时间线格式）
- `--table`: 主题色底白字 + 首行单元格列宽（`article-meta.yaml` 的 `table_widths` 大模型测算值优先，无则 sqrt 兜底）。🔴 列宽走「写进首行单元格 + `table-layout:fixed`」机制（微信安全、不被格式清算）。**按列数/内容自动分三路（草稿箱实测锁定）**：
  - **≥3 列 → 缩 11px 横滑**：表头 12px / 正文 11px + 收紧 padding；列 px 总和 ≤ ~345px（≈3 列）则 `width:100%` 铺满不滚，放不下（≥4 列或含长列）则外层 `overflow-x:auto` 横滑查看，一屏尽量多列
  - **2 列「术语\|释义」型 → 术语卡**：左列短术语(≤11 CJK)、右列长释义(≥15 CJK 且显著更长)时自动转为左竖条卡片（加粗术语 + 全宽释义），绕开窄表格挤压
  - **2 列对称数据（右列短）→ 保留 12px 改良表**
  单元格文字仍须大模型精炼（`--check` 对 >22 字单元格告警）--横滑是兜底不是纵容，多列对比表照样精简；唯「术语\|释义」的长释义交给术语卡承接
- `--lead` / `--footer`: 只盲注首尾引导板块
- `--colors`: 进行纯粹的全局引用主题色映射 + HR 压缩 + 封面图删除
- `--prompts`: 清除 Markdown 中遗留的 AI 生图提示词代码块（`> **AI生图提示词**：` + 代码块）
- `--takeaway`: 将 `> **划重点**` 引用块转换为品牌卡片组件（支持匹配带 inline style 的 `<strong>`）
- `--highlights`: 将 `<mark>重点文字</mark>` 转为**一级主题色** `#2F6F8F` 加粗，`<mark class="2">次级文字</mark>` 转为**二级主题色** `#7FB0C4` 加粗（同色相偏浅、分主次，见 [design-tokens.md §主色深浅阶](design-tokens.md)）；`***粗斜体***` 旧版兼容仅对存量 HTML 生效——🔴 **新文章禁用 `***粗斜体***`**：baoyu 转换器会把 CJK 粗斜体吃成空 `<em>`、标记文字整个消失（2026-07-11 实证），**必须用 `<mark>` 标签**（HTML passthrough，不过转换器）

> **H3 时间线视觉规范**（自动应用于所有 `###` 三级标题；圆→方）：
> - 编号：24px **圆角方块**（`border-radius:6px`）主题色底白色序号，标题 16-17px 主题色粗体
> - **自动去除标题中的前导序号**：`"1. 记忆系统"` → `"记忆系统"`（避免与方块序号重复）
> - 竖线：`2px solid rgba(0,0,0,0.06)`（浅灰若隐若现，不喧宾夺主）
> - 竖线从方块下方开始（margin-top: 6px），不穿过方块；随内容收尾（padding-bottom: 2px）
> - 双容器结构：外层 section 做定位容器（无 border-left），内层 section 承载 border-left + 内容
> - 自动剥离 H3 原有的 `border-left` 和 `padding-left`（避免双线视觉冲突）
> - **方圆层级**：H3=圆角方块(24px 大) ＞ H4 有序列表=圆形(20px 小)，方/圆 + 大/小双重信号分级（见 layout-reference.md §列表 / H4 子级排版）

> **链接卡 / 文末深读模块**（禁手敲）：正文里单条可复制链接用 [templates/link-card.html](../templates/link-card.html)；文末独立成块的深读栏/引流框用 [templates/deep-read-section.html](../templates/deep-read-section.html)。两者 URL 一律左对齐 + `word-break:break-all` + 浅色框 + 「复制到浏览器打开」，整模块走主题色系浅底、不嵌黑块。详见 layout-reference.md §链接卡 + 文末「深读入口 / 引流框」。

> 💡 **导读引用块（正文前）规范**：如果 Markdown 正文开头包含 `> **导读**`，其内部的导读段落文字字号必须比正文小 2 号（即 `14px`，由于基准字号是 16px）。已集成到 format_layout.py 自动处理中。

> ⚠️ **关注卡片去重规则**：`generate_recommend_html.py` 的输出已包含 `mp-common-profile` 关注卡片，`format_layout.py` 的 `--footer` 模块**不再重复追加**。如发现关注卡片重复，检查是否有旧版脚本或手动插入导致。

---

## 步骤2.5：文章类型 → 版式组件配方表（🔴 2026-07-07 新增，装配前先查）

> **为什么要有配方**：拿到组件库就逐段随机选，会让同类文章排版气质飘忽、或点缀堆砌显花哨。配方表按 [outline.md 步骤3 文体识别](outline.md) 定的**文体**，规定每类文章的「核心组件组合（排版主旋律）+ 点缀组件（限量）」--同文体排版稳定、不同文体有辨识差异。
>
> **硬约束**：一篇文章**点缀组件种类 ≤3**（核心组件不限，点缀别超 3 种）；超了就是花哨，删到 3 种内。
>
> **固定结构（所有文体共用，不计入点缀配额）**：封面（3f）→ 导读栏（lead-section）→ 正文 → 推荐阅读 + 关注卡（`--footer`）；信息图（3e）每篇必执行。

| 文体（outline 步骤3） | 核心组件组合（排版主旋律） | 点缀组件（≤3 种/篇，按内容出现处用） | 慎用 / 少用 |
|---|---|---|---|
| **深度文** | H2 大编号 + 正文段落 + 金句卡（quote-card）+ 要点卡（`--takeaway` 收束观点）+ 概念配图 | Case 时间线（case-timeline）、深读模块（deep-read-section）、居中金句 | 表格（深度文少硬数据）、步骤条 |
| **清单文** | H2 大编号 + H3 方块子标题（每项）+ 要点卡（每项结论）+ 对比块 / 表格（横向比较） | 数字强调卡、pill / 主题色箭头列表、信息图 | 长 Case 叙事 |
| **教程文** | H2 大编号 + H3 步骤子标题 + 代码块 / 命令 + 步骤条 + 待补素材占位 | 提示 / 警告块、参数对比表、概念配图 | 金句卡（教程重操作、轻金句） |

> **混合文体**（outline 允许两两混合）：主文体走其配方；嵌入文体段落**在该段内**切到嵌入文体核心组件（如深度文末段嵌清单文 → 该段用 H3 每项 + 要点卡），全篇点缀配额**合并**算 ≤3。
>
> **组件出处**：H2/H3/H4/列表/要点卡/表格 走 `format_layout.py`（`--h2 / --table / --takeaway`）；金句卡 `templates/quote-card.html`；Case 时间线 `templates/case-timeline.html`；深读模块 `templates/deep-read-section.html`。**对比块 / 步骤条 / 数字强调卡（2026-07-07 P1-4B 已建）走 `format_layout.py` 自包含注释指令**，`--all` 自动处理，写作阶段在 `定稿.md` 直接写：
> - **数字强调卡** `<!-- stat: 数字|单位|说明 ; 数字2|单位2|说明2 -->`（1-3 张一行，大号主题色数字，适合摆「300 美元 / 90 天」这类关键量）
> - **步骤条** `<!-- steps: 步骤一 || 步骤二 || 步骤三 -->`（竖排主题色圆号，教程/流程用）
> - **对比块** `<!-- compare: 旧标题|旧内容 || 新标题|新内容 -->`（并排双栏，左灰「旧」右主题色「新」，新旧/优劣对照用；不用红色，靠灰 / 主题色区分）
>
> 配色一律走 [design-tokens.md](design-tokens.md) SSOT，**勿手写色值**。

---

## 步骤3：配图

**前置检查**：`定稿.html` 已完成组件替换（H2 PART 格式 + H3 时间线 + 导读栏已插入）。

**输入**：`定稿.html` + 文章定稿内容  
**输出**：`定稿.html`（含图片标签），图片文件存至 `素材/` 目录

### 图片全局规则（每张图均适用）

| 规则 | 要求 |
|------|------|
| 分辨率 | **统一 1K 目标带**；由实际 renderer 使用它支持的合法尺寸参数，禁止把某一后端的 `--quality/--imageSize` 当成跨后端通用参数 |
| Logo 水印 | **所有 AI 生成图片**右下角加 logo，使用 `add_logo.js`（见下方命令） |
| Logo 水印例外 | ① 网络搜索的真实人物/事件照片**不加**水印；② `hero.png` 和 `bgm_cover.png`（尺寸太小，打水印反而影响观感）**不加**水印 |
| 图片存放 | 统一存至 `<数据目录>/{N}-{选题名}/素材/` |
| HTML 属性 | 所有 `<img>` 必须同时有 `src`（相对路径）和 `data-local-path`（绝对路径） |

**Logo 水印统一命令**：
```bash
# 单张
node "$SKILL/scripts/add_logo.js" 素材/图片名.png

# 批量所有 AI 生图
node "$SKILL/scripts/add_logo.js" "素材/*.png"
```

Logo 规格：右下角，图片宽度 12%，透明度 35%，统一使用 `logo.png`。**严禁在生图 prompt 中加入任何文字水印**--水印只通过 `add_logo.js` 后期叠加图形 logo，不在 AI 生图阶段嵌入任何文字。

🔴 **批量 add_logo 后必验完整性**：`add_logo.js "素材/*.png"` 一次处理多张时**偶发把某张 PNG 写截断**（后续 `compress_images.py` 报 `image file is truncated`、微信发布缺图）。加完水印立即跑一次完整性校验，命中损坏的就**重新生成那一张 + 单张 `add_logo.js 素材/坏图.png`**（单张处理不复发）：

```bash
python -c "import glob;from PIL import Image;[(Image.open(f).load(),print('ok',f)) for f in glob.glob('素材/*.png')]"
```

### 3a. 配图节奏

每 300-500 字必须有一个视觉元素（图片/信息卡片/表格/引用块）。

> **对比/并列内容必须用表格**：当文章中出现多个选项、方案、工具的并列对比时（如"六种打开方式"），**必须转换为对比表格**，不能只用段落罗列。
> 🔵 **表格文案极简/短语化原则（极重要）**：为适配手机窄屏显示，**多列对比表的单元格应只提炼精简关键词（如：“30-90秒/任务”），禁止大段文字或整段长句**。内容高度紧凑，配合 `--table` 的 ≥3 列 11px 横滑（列多则横滑，不再折行变形）。即使初稿出现长句，也在排版阶段主动缩减提炼。
> ⭐ **例外--「术语\|释义」型 2 列表**：左列是术语/概念、右列是整句解释时，**不必强压短语**--`--table` 会自动转为「术语卡」（左竖条 + 加粗术语 + 全宽释义）承接长释义，比挤在窄表格里更好读。

| 文章位置 | 视觉密度 |
|---------|---------|
| **第一屏（破墙）** 🔴 | **导读栏之后、第一个 H2 之前必须有 ≥1 张全宽视觉元素**--把开篇那张 9:16 信息图（见 §3e）上提到这里，别等钩子段全部讲完才在第一个 H2 前出现 |
| 前 30% | 每 200-300 字一张图（快速留住读者） |
| 中 50% | 每 400-500 字一张图 |
| 后 20% | 以文字为主，信息图收尾 |

> 🔴 **第一屏破墙（"大段文字吓退读者"诉求）**：实测开篇常是"导读栏（78px 小图）+ 三四百字纯文字"，第一张全宽大图要滑很久才出现，读者一上来就面对字墙。规则修订：开篇若**连续 3 段以上纯文字**，必须为破墙保留 ≥1 张视觉元素，**不走决策树第 ⑥ 步的"不配图让段落呼吸"兜底**（该兜底只对中后段生效）。开篇那张 9:16 信息图本就存在（不增图数），只是把它的纵向落点**前移到第一屏**。

### 3a-1. 通道分工速查表（每张图开生图前必查）

> 🔴 **配图通道是有分工的**。同一段落不允许同时来自 3c + 3e + 3g 三个通道（视觉重复）。Claude 在排版阶段读全文判断时，对每张图按下表对号入座。

| 通道 | 工具 | 何时用（决策口诀） | 视觉特点 |
|------|------|-------------------|---------|
| **3b** 真实图 | WebSearch | 文中出现**真实人物名 / 真实事件**（如奥特曼 / GPT-5.5 发布会） | 真实照片，16:9，有图注 |
| **3c** 叙事插图 | baoyu-article-illustrator | **单一物件 / 隐喻 / 氛围画面** -- 没有"结构化信息"诉求，纯情绪锚点 | claymation 手绘感，温度强 |
| **3d** 数据图表 | matplotlib 本地 | **有具体数值**（柱/折线/饼/雷达/排名） | 主题色 flat-design，精确 |
| **3e** 信息图 | baoyu-infographic | **有结构化信息但元素位置可由 AI 拼装**（多元素关系 / 数据对比拼贴 / 知识结构卡） | 21 layout × 21 style，密度感强 |
| **3g** 精确图 | baoyu-diagram → SVG → PNG | **流程 / 时序 / 架构 / 原理示意 -- 元素位置/箭头方向必须 100% 精确** | SVG 矢量，工程感重 |

**自动决策树（Claude 在排版阶段对每个候选配图位置走一遍）**：

```
① 是真实人物/事件吗？
   是 → 3b WebSearch（不走 AI 生图）
   否 → 进入 ②

② 这段需要展示具体数值（柱/折线/饼/排名）吗？
   是 → 3d matplotlib 本地脚本
   否 → 进入 ③

③ 这段有 ≥ 5 个步骤/节点/模块，且顺序/依赖/拓扑是论点核心吗？
   是 → 进入 3g 决策（见 3g.触发器）
   否 → 进入 ④

④ 这段是"建立直觉式机制图解"吗？（"原理是怎么工作的"）
   是 → 进入 3g.illustrative（精确画机制）
   否 → 进入 ⑤

⑤ 这段是"信息密度型展示"（多元素关系 / 多源证据 / 知识结构）吗？
   是 → 3e baoyu-infographic（让 baoyu 的 21 layout 自动选）
   否 → 进入 ⑥

⑥ 这段是"单一物件 / 隐喻 / 纯氛围画面"吗？
   是 → 3c baoyu-article-illustrator（叙事感）
   否 → 不配图，让段落呼吸（🔴 开篇第一屏例外：连续 3 段以上纯文字必须破墙，见 §3a 第一屏破墙，不走本兜底）
```

**冲突仲裁（同一段落多个候选时）**：3g > 3e > 3c > 不配图。理由：精确性 > 密度 > 氛围。**开篇第一屏破墙优先**：开篇若要在"不配图"和"配一张破墙图"之间仲裁，一律配图（兜底的"不配图"在开篇关闭）。

### 3b. 真实人物 / 事件配图

发现真实人物或真实事件时：
1. 用 Tavily/WebSearch 搜索真实照片（官方/新闻/公开演讲照片）
2. 选最具代表性、画质最高一张，16:9 裁切，宽度 677px
3. 插入首次出场段落之后
4. **必须加图注**（人名/事件名 + 时间 + 来源）
5. **不加** logo 水印

```html
<section style="margin:20px 0; text-align:center;">
  <img src="素材/photo.png" data-local-path="<数据目录>/{N}-{选题名}/素材/photo.png" style="width:100%; border-radius:6px; display:block;">
  <section style="font-size:12px; color:#999; margin-top:8px; letter-spacing:0.5px;">人物名 · 时间/场合 | 图源：来源</section>
</section>
```

**禁止**：用 AI 生成的人物照片替代真实照片。

### 3c. 概念解释配图（baoyu-article-illustrator）

抽象概念首次出现时，调用 `/baoyu-article-illustrator` 生成（风格由 EXTEND.md 自动控制，默认 `claymation` + `warm` 色调）：

| 场景 | 图片类型 | 参数 |
|------|---------|------|
| 抽象概念可视化 | 比喻/类比图（type: `scene`） | 16:9，1K |
| 流程/步骤 | 流程图（type: `flowchart`） | 16:9，1K |
| 对比论述 | 左右对比图（type: `comparison`） | 16:9，1K |

> **必须调用 `/baoyu-article-illustrator` skill**，不要直接写 `baoyu-image-gen` inline prompt。风格和语言通过 EXTEND.md 统一管理，避免每次手写 prompt 导致风格不一致。

生成后执行 add_logo.js 加水印。

### 3d. 数据图表配图（baoyu-image-gen）

写作阶段用 `<!-- chart: type | 标题 -->` 标记的数据表格，排版阶段**必须转换为图表图片**。纯表格在手机端阅读体验差，图表更直观且提升视觉节奏。

#### 识别与转换流程

1. 搜索 `定稿.md` 中所有 `<!-- chart:` 标记
2. 提取紧跟其后的 Markdown 表格数据
3. 用 `baoyu-image-gen` 生成对应类型的图表图片
4. 在 `定稿.html` 中将原表格替换为图片

#### 图表类型与 prompt 要求

| 标记 | 图表类型 | prompt 关键词 | 适用场景 |
|------|---------|--------------|---------|
| `bar` | 柱状图 | bar chart, vertical bars | 3+ 项数据量级对比 |
| `line` | 折线图 | line chart, trend | 时间序列变化趋势 |
| `radar` | 雷达图 | radar/spider chart | 多维度评分评测 |
| `pie` | 饼图 | pie chart, proportions | 占比/份额分布 |
| `compare` | 对比图 | comparison, side-by-side | A vs B 方案对比 |

#### 统一视觉规范

| 规则 | 要求 |
|------|------|
| 主色 | 主题色 `#2F6F8F` 为主数据色 |
| 辅色 | `#A0D2C4`（浅色）、`#E8F5F0`（极浅色）、`#999999`（灰色对比项） |
| 背景 | 纯白 `#FFFFFF`，干净无杂纹 |
| 文字 | **必须中文**，prompt 中标注 `[Text Content - MUST BE IN CHINESE]` |
| 尺寸 | 16:9，1K |
| 风格 | flat design / clean infographic，禁止 3D 效果和渐变花哨 |
| 字体效果 | 数据标签清晰可读，标题加粗居中 |

#### prompt 模板

```
A clean flat-design {chart_type} infographic on white background.
Title: "{图表标题}" [Text Content - MUST BE IN CHINESE]
Data: {数据项和数值}
Color scheme: primary #2F6F8F (brand green), secondary #A0D2C4 (light green), accent #999999 (gray).
Style: minimal, professional, no 3D effects, no gradients, clear data labels in Chinese.
```

#### 示例

Markdown 中的标记：
```markdown
<!-- chart: bar | 2025年Q1智能家居品牌市场份额 -->
| 品牌 | 市场份额 |
|------|---------|
| 小米 | 35% |
| 华为 | 28% |
| 美的 | 15% |
| 其他 | 22% |
```

生成命令：
```bash
数值型柱/折/饼/雷达图不要调用生图模型；按本节数据表用 matplotlib/pyecharts 本地渲染并保留 `.py` 源文件。
```

生成后执行 add_logo.js 加水印，插入 HTML 替换原表格。

> **注意**：如果数据较简单（仅 2 行对比），保留表格即可，不必强制转图表。图表适用于 3 项及以上数据或需要展示趋势/比例的场景。

> **⚠️ 数据确认后再生图**：baoyu-image-gen 生成的是图片而非可编辑图表，数据修改后需重新生成。务必先确认数据准确性，再执行生图命令。纯数据图（柱/折线/饼）也可考虑用 Python matplotlib + 品牌色参数本地生成，更快更精确。

### 3e. 全文贯穿信息图（baoyu-infographic，每篇必执行）

> 🔴 **必须通过 Skill 工具调用 `baoyu-infographic` skill，严禁直接调用底层 `baoyu-image-gen/main.ts` 或内置生图工具（`generate_image`、`internal_image_gen`、`imagine` 全部黑名单）。**
> 直接调底层会跳过 baoyu-infographic 的内容分析、layout/style 选型与结构稿，输出降级为氛围图。renderer 可由 child skill 选择，但 producer 必须是 `baoyu-infographic`。

#### 数量与分布规则（2026-05-04 升级）

每篇文章信息图**≥ 4 张**，按"开篇 + 中间 + 结尾"全文贯穿分布，不再只放文末：

| 位置 | 比例 | 数量 | 用途 |
|------|------|------|------|
| **开篇** | 9:16 portrait | 1 张 | 🔴 **第一屏破墙图**--嵌得尽量靠前（导读栏之后、开篇连续纯文字 ≤3 段处即出），别等钩子全部讲完才在第一个 H2 前出现（见 §3a 第一屏破墙）。仍是"导读后第一张视觉锚点，提炼核心论点"，只是落点前移 |
| **中间** | 16:9 landscape | ≥ 2 张 | 每个主要 PART 模块之间插一张，承接论据/数据/对比 |
| **结尾** | 9:16 portrait | 1 张 | 文末总结/行动建议/价值升维 |

5 个 PART 文章建议分布：开篇 1 + 中间 2-3 + 结尾 1 = 4-5 张。
3-4 个 PART 文章建议分布：开篇 1 + 中间 2 + 结尾 1 = 4 张（最少）。

#### 默认参数（本 skill 业务约定）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--style` | `claymation` 或 `morandi-journal`（按文章类型二选一） | claymation = AI 工具/教程/产品评测；morandi-journal = 趋势/商业/人文/育儿/温和议题。同篇不混风格，缺省默认 claymation。详见 [image-routing.md 信息图 style 选择铁律](image-routing.md)。craft-handmade 等其余 20 种已封存 |
| `--aspect` | 按位置：开篇/结尾 `9:16`，中间 `16:9` | **必传**，不接受默认 |
| `--lang` | `zh` | 简体中文标签，违反则 verify 阶段拦截 |
| renderer 尺寸 | 1K 目标带 | 由 child skill 对实际 renderer 传合法参数；不要把某后端的 `--quality/--imageSize` 生搬到 baoyu 语义调用 |
| `--layout` | 自动（根据内容选） | 不强制；若手动指定见下表 |

**Layout 选型参考（21 种中常用 7 种）：**

| 内容特征 | 推荐 layout |
|---------|-------------|
| 旅程/成长/里程碑 | `winding-roadmap` 或 `linear-progression` |
| 多主题概览/卡片网格 | `bento-grid` |
| 流程/历史/时间线 | `linear-progression` |
| 多因素对比 | `comparison-matrix` |
| 两方对照 | `binary-comparison` |
| 层级/成熟度 | `hierarchical-layers` |
| 因果根因分析 | `hub-spoke` 或自动 |

#### 调用模板

🟢 **正确做法**：通过 Skill 工具调用 `baoyu-infographic` skill：

```
Skill(skill="baoyu-skills:baoyu-infographic", args="
内容 prompt（从文章核心知识结构提炼，全中文）
--style claymation   # 或 morandi-journal，按文章类型二选一（同篇统一）
--aspect 9:16   # 或 16:9，按位置定
--lang zh
--layout bento-grid   # 可选，不传则自动
最终 prompt：素材/prompts/final/infographic-NN.md
输出：素材/infographic-NN.png
")
```

❌ **错误做法**（已被 verify 严格白名单拦截）：
- 直接 `bun baoyu-image-gen/main.ts --promptfiles ...`（跳过 baoyu-infographic 的专业系统）
- 用通用 `generate_image` 内置工具（黑名单）

#### 内容要求

从文章深度提炼核心知识结构，含文字标签、数据对比、逻辑关系。禁止纯氛围画面。**标签文字必须是中文**--英文标签会直接违反 `verify infographic` 的语言断言。

#### 生成后强制登记

```bash
python "$SKILL/scripts/pipeline.py" log infographic baoyu-infographic \
  --output 素材/infographic-01.png \
  --prompt 素材/prompts/final/infographic-01.md \
  --renderer imagegen --model '<实际模型>' \
  --cmd "Skill baoyu-skills:baoyu-infographic --aspect 9:16 --layout bento-grid ..."
```

producer **必须**是 `baoyu-infographic`（精确拓扑图例外为 `baoyu-diagram`）；renderer 单独记录。verify 会校验两层、prompt/output 摘要与 model。

生成后统一执行 add_logo.js 加水印。**🔴 严禁在 prompt 里加任何水印文字，AI 会把它渲染成图片内容，导致出现双重水印。水印只通过 add_logo.js 后期叠加。**

**插入 HTML**（≥4 张贯穿全文，按位置嵌入：开篇 9:16 → 中间 16:9 ×≥2 → 结尾 9:16；每张一个 `<section>`，下例示开篇 + 一张中间，其余同理）：
```html
<!-- 开篇 9:16 -->
<section style="margin: 32px 8px 16px;">
  <img src="素材/infographic1.png" data-local-path="绝对路径" style="width:100%; display:block; border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.08);">
</section>
<!-- 中间 16:9（≥2 张，分散嵌入正文对应段落）-->
<section style="margin: 16px 8px 32px;">
  <img src="素材/infographic2.png" data-local-path="绝对路径" style="width:100%; display:block; border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.08);">
</section>
<!-- …中间其余 16:9 / 结尾 9:16 同样各一个 <section>，共 ≥4 张 -->
```

### 3f. 封面图（baoyu-cover-image，每篇必执行）

> 🔴 **必须调用 `/baoyu-cover-image` skill，严禁用内置工具或自写脚本替代。**
>
> 通用默认偏好可放 `~/.baoyu-skills/baoyu-cover-image/EXTEND.md`；本篇 `article-meta.yaml`、blueprint 与 `cover-styles.md` 的明确值优先，EXTEND 不得反向覆盖。

封面图**不嵌入正文**，后续在微信后台设置为「封面图片」属性。

> 🎨 **三大关键词**：**简洁、直观、有画面感**。

**前置步骤（调用 baoyu skill 前必须完成）：**

1. 通读全文 + 标题 → 提炼出**一个核心论点**
2. 将论点转化为**具体、广为人知的视觉符号**（强制查证官方标志，禁止 AI 凭空捏造）
3. **选封面风格**：默认且锁定 `montage-evidence`；只有 `article-meta.yaml` 明确填其他 `cover_style`，才视为有意 override。禁止从历史 prompt/EXTEND 自动换回 conceptual、focus 或旧五选一逻辑。
4. **提炼封面文字**：主标题（3-7 字核心冲突词）+ 副标题（6-12 字价值点），**严禁照搬文章标题**
5. 最终 prompt 固定写 `素材/prompts/final/cover.md`：默认 `montage-evidence` 为**左侧文字、右侧证据拼贴**，标题块总高 18--22%；明确禁止 `largest` / `extra-black` / `ultra-black`。

> 详细的辨识度优先级、示例、"缩略图测试"标准和背景点缀规范见 EXTEND.md。

> **封面图生成铁律**：封面图**必须且只能**通过 `baoyu-cover-image` 技能工作流生成。
> - ❌ **严禁**使用 `generate_image` 工具（只能输出 1:1，无法控制宽屏比例）
> - ❌ **严禁**直接调用 `baoyu-image-gen`（绕过封面图规范）
> - ✅ **唯一正确做法**：按 `baoyu-cover-image` SKILL.md 的完整工作流执行

**调用命令**（aspect/rendering/text/mood/palette/type 等参数已在 EXTEND.md 中预设，只需 `--quick`）：

```
/baoyu-cover-image 定稿.md --quick
```

**生成后**：
1. 原始 renderer 输出存至 `素材/cover.png`
2. **加 logo 前立即登记 v2 证据**：
   ```bash
   python "$SKILL/scripts/pipeline.py" log cover baoyu-cover-image \
     --output 素材/cover.png --prompt 素材/prompts/final/cover.md \
     --renderer imagegen --model '<实际模型>' --cmd "/baoyu-cover-image 定稿.md --quick"
   ```
3. 再执行 add_logo.js + compress；全部最终图逐张 QA 后执行 `pipeline.py seal visual`

**验收 checklist**：
- ☐ 深色底 + 局部美感点缀（非均匀撒星点）
- ☐ 左侧文字块总高 18--22%，主副层级精致，不是海报巨字
- ☐ 右侧证据拼贴反映核心论点，不侵占左侧文字安全区
- ☐ 文字高光：主标题内提炼出核心字词，统一使用主题色 `#2F6F8F` 进行点缀与轻微强调，整体风格保持克制不突兀
- ☐ 右下角干净（Logo 由 add_logo.js 后期叠加）
- ☐ 缩略图测试：缩至 140×60px 后主体仍可辨识（推荐卡片封面尺寸）

### 3g. 精确技术图表（baoyu-diagram，按需触发）

> 🟡 **低频但精确的备选通道**（2026-05-04 接入）。仅在 3a-1 决策树判定"步骤/节点 ≥ 5 个 + 顺序/拓扑是论点核心"时触发。否则用 3e baoyu-infographic 即可。预计每 5-8 篇用 1 次。

#### 3g.触发器：先决定要不要用 3g，再决定用哪种 type

**第一步：是否启用 3g？两个条件全满足才启用**：

| 条件 | 判定 |
|------|------|
| ① 这段内容**步骤 / 节点 / 模块 / 角色 ≥ 5 个** | 数一遍 |
| ② **顺序 / 依赖 / 通信 / 拓扑关系**是这段的核心论点（不是装饰） | "如果删掉这张图，读者就理解不了这段" → ✅ |

任一条件不满足 → 退回 3e baoyu-infographic（信息密度型拼贴够用）。

**第二步：5 种 type 选哪个？按内容关键词匹配**：

```
段落出现的关键词 / 内容特征                          → 推荐 type
═══════════════════════════════════════════════════
步骤 / 工作流 / 怎么操作 / 第一步 / 状态机 / 生命周期    → flowchart
─────────────────────────────────────────────────
调用 / 请求 / 响应 / 协议 / 握手 / 认证                → sequence
API / Webhook / OAuth / TCP / 数据流 / 谁先发          → sequence
─────────────────────────────────────────────────
组成 / 架构 / 分层 / 模块 / 拓扑 / 端·网关·云          → structural
组件关系 / 什么里面有什么                              → structural
─────────────────────────────────────────────────
原理 / 怎么工作 / 为什么这样 / 底层机制                → illustrative
建立直觉 / 直观解释 / 我画给你看                       → illustrative ⭐ 最常用
─────────────────────────────────────────────────
类 / 继承 / 数据模型 / UML / 接口                     → class（极少触发）
═══════════════════════════════════════════════════
匹配不到任何关键词                                     → illustrative（兜底，最自由形式）
```

#### 3g.5 种 type 速查（详见 `baoyu-diagram` skill 文档）

| type | 一句话 | 典型应用 |
|------|--------|-----------------|
| `flowchart` | 一步一步怎么做 | 教程文 / 工作流文 |
| `sequence` | 谁先发消息给谁 | API 调用 / 数据流文 |
| `structural` | 什么里面有什么 | 产品深度文 / 体系拆解文 |
| `illustrative` | 画给你看到底怎么回事 | 任何"建立直觉"的抽象概念 |
| `class` | 类型怎么继承 | 几乎不用（开发者向） |

#### 3g.调用流程（4 步）

🟢 **正确做法**（必走 Skill 工具入口，不直接调底层）：

```
Skill(skill="baoyu-skills:baoyu-diagram", args="
<内容描述：从段落提炼的核心结构 + 5 个以上节点>
--type sequence            # 5 选 1，按 3g.触发器决定
--lang zh                  # 中文标签
--out 素材/diagram_NN_<slug>.svg
")
```

#### 3g.必须显式覆写品牌色（双色铁律）

baoyu-diagram **默认是多彩配色**（cyan / emerald / violet / amber / rose），跟本 skill 的"主题色 + 黑白灰"双色铁律冲突。每次调用 prompt 中**必须**加入以下覆写指令：

```
品牌色覆写要求（CRITICAL）：
- 所有 stroke 颜色：主题色 #2F6F8F（主线）/ 黑色 #000000（次线）
- 所有 fill 颜色：白色 #FFFFFF（节点底色）/ 深炭 #0E0E10（强调框）/ 浅色 #e9f2f5（次级填充）
- 文字颜色：深灰 #2C2C2C（正文）/ 主题色（重点）/ 中灰 #666666（注释）
- 严禁出现 cyan / emerald / violet / amber / rose / blue / red / orange 任何彩色
- 严禁渐变色 / 阴影 / 高光（保持 flat 矢量）
- 深色模式自适应：内嵌 @media (prefers-color-scheme: dark) 规则保留
```

#### 3g.SVG → PNG 转换（强制，微信不支持内嵌 SVG）

baoyu-diagram 输出 `.svg`，但微信公众号渲染 SVG 不稳定。**必须**用 `svg_to_png.py` 转 PNG 再嵌入：

```bash
# 转 PNG（DPR=2 高清 + 品牌色校验）
python "$SKILL/scripts/svg_to_png.py" 素材/diagram_01_xxx.svg \
  --check-brand \
  --width 1200

# 输出：素材/diagram_01_xxx.png
```

`--check-brand` 会扫描 SVG 中的颜色，违规直接退出（这是 prompt 覆写没生效的兜底）。

#### 3g.加水印 + 嵌入 HTML

```bash
node "$SKILL/scripts/add_logo.js" 素材/diagram_01_xxx.png
```

```html
<section style="margin: 24px 8px;">
  <img src="素材/diagram_01_xxx.png" data-local-path="绝对路径"
       style="width:100%; display:block; border-radius:6px; box-shadow:0 1px 6px rgba(0,0,0,0.06);">
</section>
```

#### 3g.生成后强制登记

```bash
python "$SKILL/scripts/pipeline.py" log infographic baoyu-diagram \
  --output 素材/diagram_01_xxx.png \
  --cmd "Skill baoyu-diagram --type sequence --lang zh + svg_to_png.py --check-brand"
```

> 注：3g 与 3e 共用 `infographic` 阶段的 log（都是"信息图"大类），白名单允许 `baoyu-infographic` 和 `baoyu-diagram` 两种工具。

#### 3g.不启用条件（任一满足就退回 3e）

- 文章是观察/反思/感性类
- 步骤少于 5 个
- 主要是"展示信息"而非"展示流程"
- 文章总长 < 5000 字（多花一步 SVG→PNG 的 ROI 太低）
- 配图位置不在文章核心论证段落（只是装饰性视觉）

### 3h. 配图压缩（compress_images.py，发布前必跑）

> 🟢 **每篇必执行**。位置：在 `add_logo.js` 加水印之后、`baoyu-post-to-wechat` 推送之前。

#### 为什么必须做

实测某篇多图文章的配图大小：
- `infographic*.png` 平均 ~5.4 MB
- `cover.png` ~4.4 MB
- `illust_*.png` 平均 ~4.5 MB

未压缩直接走 `baoyu-post-to-wechat` API 的后果（实测记录）：
- 上传慢（45+ MB 总流量）
- 微信端**自动转 JPEG 82 quality**，不可控压缩，logo 透明边缘出毛刺
- 9 张图 × 5MB 抓数据慢，每次推草稿箱要等

跑完 `compress_images.py` 后：
- 文件大小降至 1-2 MB（保持 PNG 格式，不转 JPEG）
- 微信端不再触发强压
- Logo 透明边缘清晰
- API 上传速度 3-5 倍提升

#### 为什么用 compress_images.py 而不是 baoyu-compress-image

`baoyu-compress-image` 底层是 ImageMagick `convert`，在 Windows + 中文路径下崩溃
（曾在中文工作目录下首发踩坑--本 skill 的工作目录恰恰是中文路径）。`compress_images.py`
用 Pillow 实现、中文路径友好，是本 skill 指定的压缩工具。

#### 调用模板

```bash
# 批量（推荐）
python "$SKILL/scripts/compress_images.py" 素材/ --max-mb 2

# 单张
python "$SKILL/scripts/compress_images.py" 素材/cover.png
```

策略：≤ `--max-mb` 的文件只做 optimize 轻量瘦身；超阈值的等比缩长边到 1024px（1K 横切规范）。

#### 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--max-mb` | 2.0 | 超过即等比缩长边到 1K（1024px） |
| `--quiet` | 关 | 只输出总结，不逐张打印 |
| 输入路径 | - | 单文件 / 目录（目录下所有 `*.png`） |

#### 在流水线中的位置

```
配图阶段执行顺序（每张图都要走完）：
1. 生图（baoyu-cover-image / baoyu-infographic / baoyu-diagram → svg_to_png）
2. add_logo.js 加水印
3. ⭐ compress_images.py 压缩  ← 本步
4. 嵌入 定稿.html
5. baoyu-post-to-wechat 推送
```

#### 验收

- ☐ 所有 `素材/*.png` 文件大小 ≤ 2 MB
- ☐ Logo 水印仍清晰（压缩不影响透明边缘）
- ☐ 微信 API 上传日志中**未出现** "compressed X.XX MB source below 1MB, encoded as JPEG" 强压提示

#### 例外

- `hero.png` / `bgm_cover.png` / `music_cover.png`：脚本内置跳过清单（组件小图，无需压缩）
- 真实人物照片（3b 通道，WebSearch 来的）：通常已被 CDN 压缩过，再跑一次也无害

---

## 步骤4：发布前检查与字符压缩

**前置检查**：`定稿.html` 已完成配图（含 `<img>` 标签和 `data-local-path`）。

**输入**：`定稿.html`（含图片）  
**输出**：`定稿.html`（通过检查，可发布）

### 4a. 自动化预检（一键完成）

以下检查已集成到 `format_layout.py --check`，**必须通过后才能发布**：

```bash
python $SKILL/scripts/format_layout.py 定稿.html --check
```

自动检查项：
- **品牌色**：扫描 `#0F4C81`（蓝色）、`#d14`（红色）、`#f7f7f7`（灰色）残留
- **组件完整性**：导读栏、H2 格式、推荐阅读、关注卡片
- **关注卡片 data-id** Base64 padding 完整性
- **图片 data-local-path** 属性检查
- **导读栏文案**：检测是否仍使用默认占位文字
- **封面图标签**：是否残留在正文中
- **裸 URL 门**（`pipeline.py verify layout` 阶段 `verify_no_bare_url`）：正文里完整 URL（≥18 字符、带 `/路径`）必须装进 link-card / deep-read 模板的 `word-break` 浅框；裸放在正文段落 / 划重点 / 文末手敲段 → **硬 fail**（根因：微信对含长 URL 的行两端对齐 → 分散对齐 + 难复制。修法：挪进 `link-card.html`（单条）或 `deep-read-section.html`（文末/多条））

> 建议在 `--all` 后直接追加 `--check`：`python format_layout.py 定稿.html --all --check`

### 4b. AI 巡航复核（自动化脚本无法覆盖的项）

在正式调用发布 API 前，AI 必须调取系统内建判定能力，自行在后台建立质检线程：
- [x] 加粗部分串起来能概括全文 70% 信息吗？如果不能，自己回去用正则或编辑能力重新加粗。
- [x] 全文无连续 3 屏以上纯文字？如果有，立马跑去生成一个图表或切分卡片。
- [x] 真实人物/事件配了真实照片（16:9，有图注）？
- [x] 所有 AI 生图已确定执行过 `add_logo.js` 盖章？
- [x] 导读栏的 Hero 图是否按照 1:1 单独生成并正确嵌入？不准偷懒套用宽版封面。
- [x] 所有图片有 `border-radius:6-8px` 和 `display:block`（这应由清洗脚本保证，你负责最后过眼）。
- [x] 文末引流地址 + 正文里任何完整 URL 全部走 `link-card` / `deep-read-section` 模板（**无裸 URL 段落 / 无手敲文末网址**）？入口名（GitHub / 国内直达 / 在线解析）是品牌绿小标题、不是跟正文一样字号手动加粗？（裸 URL 会被 `verify_no_bare_url` 硬门拦下，别等报错才改）

### 4e. 结尾组件：推荐阅读 + 关注卡片

结尾组件分两部分，直接写入文章 HTML，无需进入微信编辑器手动操作。

#### 推荐阅读卡片（3 篇，自动填充）

**数据来源**：从 `<数据目录>/works.yaml` 取**已发布**条目，按**发布日倒序**排列，**仅推有封面的**，再按「一三五」规则取**第 1 / 3 / 5 篇**（跳过第 2、4 篇）；若某位缺封面则**顺延就近一篇且不重复**，取其**封面 + 微信链接**（标题仅作 `<img alt>`，纯封面卡不渲染标题/摘要文字），自动填入模板。

> **封面图比例规范**：推荐卡片的封面图必须使用 **2.35:1 比例**的图片（即各文章 `素材/cover.png`）。
> - ❌ 禁止使用微信 CDN 返回的方形缩略图 URL（经压缩后为 1:1 方形，视觉变形）
> - ✅ 正确做法：从对应文章目录 `<数据目录>/{N}-{选题名}/素材/cover.png` 取本地文件，通过 API 上传获得微信 CDN URL
> - 封面来自 `works.yaml` 的 `cover` 相对路径（由 `pipeline.py archive` 自动写入），脚本在生成推荐HTML时据此上传并替换为CDN链接

> 严格注意：这一切已在 `format_layout.py --footer` 中完全自动化。任何时候**都不需要**你再要求人类通过“复制粘贴”动作贴到 HTML 里了。直接驱动该脚本即可！

每张卡片采用**纯封面全宽长条**布局结构：

- **结构**：`<section><a href="..."><img></a></section>`，封面图 `width:100%`、圆角 `border-radius:6-8px`，整张图即点击区。
- **取消右侧文字**：不再渲染标题、摘要、阅读全文等文字单元格，仅展示全宽封面。

> **⚠️ 微信 HTML 兼容性关键规则（必须遵守）**
>
> 纯封面卡只有一个链接元素，绑定规则唯一：
> - `<section>` 包 `<a>` 包 `<img>`（**块包行内**）-- `<a>` 直接包裹 `<img>` 是行内包行内、合法；
>   **绝不能让 `<a>` 包裹块级 `<section>`**（微信编辑器对此支持不稳定，偶发"系统错误"）。
> - `<img>` 用 `width:100%; display:block`，整张封面即点击区，跳转到该文章微信永久链接。
> - 不再有标题/副标题/阅读全文等文字链接（纯封面版已取消右侧文字）。
>
> **禁用**：`data-local-path`、`box-shadow`、`<style>` 标签块。
>
> （历史的 table 左图右文「方案 A 整卡链接 / 方案 B 分散式链接」已随纯封面改版废弃，见 git 历史。）
  
（附源码见 `scripts/generate_recommend_html.py` 中 `generate_single_card_html` 方法）

#### 关注卡片（mp-common-profile 官方组件）

放在推荐阅读卡片之后，使用微信官方 `mp-common-profile` 组件。该组件由微信原生渲染，自带头像、关注按钮和跳转功能。

> 🔴 **排查确认：以下三个条件缺一不可，任一缺失 API 提交即报"信息错误"！**

| # | 必须条件 | 错误写法 | 正确写法 |
|---|---------|---------|--------|
| 1 | **data-id 完整 Base64 padding** | `QWJjRGVmR2g=` (1个=) | `QWJjRGVmR2g==` (2个=) |
| 2 | **外层 section 带指定 class** | `<section style="margin:...">`（无 class） | `<section class="mp_profile_iframe_wrp custom_select_card_wrp">` |
| 3 | **组件标签带 class + data-pluginname** | `<mp-common-profile>` 裸写 | `class="mpprofile js_uneditable custom_select_card mp_profile_iframe"` + `data-pluginname="mpprofile"` |

```html
<section class="mp_profile_iframe_wrp custom_select_card_wrp">
  <mp-common-profile
    class="mpprofile js_uneditable custom_select_card mp_profile_iframe"
    data-pluginname="mpprofile"
    data-nickname="你的公众号名"
    data-alias="你的微信号"
    data-headimg="你的头像 URL（公众号后台「账号详情」可查）"
    data-signature="你的一句话简介（引号用 &quot; 实体编码）"
    data-id="你的公众号 Biz 码（base64，padding 必须完整，如 …==）"
    data-service_type="1">
  </mp-common-profile>
</section>
```

**参数说明**：
- 上列各 `data-*` 值来自 `profile/brand.yaml` 的 `identity` 段，由 `--footer` 自动填充（这里展示的是占位示例）；`data-id` 为公众号 Biz 码（Base64，padding 必须完整），`data-alias` 为微信号
- `data-signature` 中的引号必须用 `&quot;` 实体编码
- 如需更新名片信息，在微信编辑器中手动插入 → F12 → Elements → 右键 Copy outerHTML

> 模板：`templates/footer-recommended.html`

### 4f. 组件完整性检查

- ☐ 导读栏插在 `<div id="output">` 最前面（不在 body 后）
- ☐ 所有 H2 PART 节和 H3 时间线节的 `</section>` 完整闭合
- ☐ 文末留言引导位已插入（互动提问放**排版层**这里，不进正文结尾--正文默认冷收，废除"结尾三段式互动"检查项，见 [craft-techniques.md §结尾技法](craft-techniques.md)）
- ☐ 推荐阅读卡片已插入（3 篇），每篇 = 一张全宽封面图（可点击跳转），无右侧文字，卡片间靠 margin 间隔
- ☐ 关注卡片已插入（`mp-common-profile` 组件），**必须含 `class` 和 `data-pluginname` 属性**
- ☐ 关注卡片 `data-id` Base64 padding 完整（`QWJjRGVmR2g==` 双等号）

---

## 步骤5：发布

步骤4 全部检查通过后，进入发布阶段。执行 `写 发布` 加载 [publish.md](publish.md) 完成发布流程。

---

## 常见故障速查

| 症状 | 原因 | 解决 |
|------|------|------|
| 微信 API 报"信息错误" | `data-id` Base64 padding 不完整（少一个 `=`） | 确保 `QWJjRGVmR2g==`（双等号） |
| 关注卡片不显示 | 缺少 `class` 或 `data-pluginname` 属性 | 用步骤 4e 的完整模板替换 |
| H2/H3 样式未生效 | 未执行 `format_layout.py --all` 或 HTML 中无 `<div id="output">` | 确认前置条件后重跑脚本 |
| 残留蓝色/红色 | baoyu 转换时未加 `--color "#2F6F8F"` | 跑 `--colors` 模块或手动替换 |
| 导读栏显示默认占位文字 | 未传入 `--lead-line1` 等参数 | 补传导读栏参数后重跑 `--lead` |
| 推荐卡片封面图变形 | 使用了微信 CDN 缩略图（1:1） | 改用本地 2.35:1 封面图上传 |
| 多列表手机端挤压/折行 | ≥3 列内容偏长 | 已由 `--table` 自动缩 11px + 放不下横滑兜底；仍宜精简单元格短语 |
| 2 列术语表挤成多排 | 右列是整句释义硬塞窄列 | 已由 `--table` 自动转「术语卡」承接；无需手改 |

---

## 参考资料（按需加载）

排版过程中遇到样式异常、表格问题或微信过滤报错时，加载以下文件排查：

| 文件 | 内容 |
|------|------|
| [layout-reference.md](layout-reference.md) | 踩坑字典、表格设计规范、兼容表格写法、分隔线样式、导读栏 Logo 规范 |
| [wechat-compat.md](wechat-compat.md) | 完整微信 HTML/CSS 兼容性规则数据库（标签白名单、属性过滤矩阵、图片/SVG 规则） |

> 日常执行排版 SOP（步骤 1-5）时**不需要**加载这些参考文件。

---

## 排版完成后的下一步建议（自动出现，让创作者选）

> 🔴 **默认"不弹菜单、直接续跑到草稿箱"：** 默认模式（含普通"写一篇文章"请求）排版完成后**不再停下来给下面这个 1/2/3 选择菜单**，直接续跑配图 / BGM / 发布 → 推微信草稿箱（禁止止步于排版）。本菜单**仅在你明确要求逐步确认**时才弹；硬阻塞（缺封面反复失败 / 凭证 invalid / 自检 Error 修不掉）才停下来报告。

> `format_layout.py --all` 跑完、 `定稿.html` 自检通过后（**仅当你要求逐步确认**），**主动**给出 3-5 个下一步具体选项。

按当前 HTML 状态，从下面这组里挑 3-5 条贴合的：

- **直接进入发布**（走 [publish.md](publish.md) -- baoyu-post-to-wechat 推到微信草稿箱）
- **加封面图**（如果还没做封面 → [cover-styles.md](cover-styles.md) 选风格 → baoyu-image-gen 出图 → 注入到草稿箱）
- **预发布自检**（跑 `format_layout.py --check` 一次完整自检，扫品牌色残留、加粗密度、表格变形、关注卡片、推荐阅读卡）
- **学习我的排版调整**（如果你手改了 HTML → 比对 `定稿.html` 排版前后差异 → [learn-edits.md](learn-edits.md) 沉淀 pattern）
- **暂存 HTML，下次发布**（更新 `.state.json` 把 `layout=done` + `publish=pending`）
- **转小红书图文**（→ [xhs-storyboard.md](xhs-storyboard.md) -- 长文压成轮播剧本 → baoyu-xhs-images 出图）

**给选项的写法范例：**

> 排版已完成，HTML 已生成。下一步你想--
> 1. 直接发到微信草稿箱
> 2. 跑一次 `format_layout.py --check` 全量自检再发
> 3. 还没做封面图，先去出封面
> 4. 顺便把这篇拆成小红书轮播
> 5. 暂存，下次再发
>
> 默认走 1。

**为什么必要：** 排版完成不等于可以发布 -- 封面图、自检常被遗漏。给具体选项 = 让流程链条不掉环。

---

*建立于 2026-03-22，重构于 2026-04-11，渐进式披露于 2026-04-28*
