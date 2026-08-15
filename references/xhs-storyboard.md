# 小红书图文剧本提炼系统 (XHS Storyboard Extractor)

> ⚠️ **低频能力备查**（2026-08-16 标注）：本 profile 的小红书分发渠道已冻结
> （见 distribute.md 渠道配置），本文仅在用户显式要求「转图文/拆图文」时使用，
> 日常流程不加载。文内示例 prompt 是历史 Midjourney 口径，仅作剧本结构参考——
> 实际生图一律走 `baoyu-image-gen` 登记的 renderer（iron-rules.md §视觉 16），
> 且须遵守生图首过率四规则（frontmatter 剥离/具体物象/文字重叠≤1/无带字物件）。

将公众号长文浓缩为一套完整的小红书轮播图文剧本（8-12张），
确保每一张图的文案都是原文精华的重新演绎，而非简单的段落截取。

## 定位

本模块只负责**内容提炼与剧本编排**（文字层面），不负责生图。
输出物是一份结构化的 `xhs-outline.md` 文件，可直接交给 `baoyu-xhs-images` 的 Step 3 生图。

> **注**：`baoyu-xhs-images` 是小红书 + 微信图文通用接口（baoyu-skills v2.0 起统一为此名，v1.95~v1.x 期间曾短暂叫 `baoyu-image-cards`）。

> **分辨率标准**：小红书图文统一使用 **1K（1242×1660px）**，平台上传后自动压缩，2K 和 1K 展示效果无差别，但文件大小相差 4 倍。生图时在 `batch.json` 里设置 `"imageSize": "1K"`，或确认 `~/.baoyu-skills/baoyu-image-gen/EXTEND.md` 中 `Default Image Size` 为 `1K`。

```
公众号定稿.md ──[本模块]──▶ xhs-outline.md ──[baoyu-xhs-images]──▶ 图片
```

> **输出路径规则**：产物**必须落在源文章所在的文件夹下**，统一收进分发层目录 `dist/xhs/`。
> 例如「把 `<数据目录>/2-小龙虾/定稿.md` 转小红书」：
> - 剧本 → `<数据目录>/2-小龙虾/dist/xhs/xhs-outline.md`
> - 图片 → `<数据目录>/2-小龙虾/dist/xhs/images/NN-slug.png`
> - 中间工作文件（`gen.js`、`batch.json`、生图提示词目录）一并放 `dist/xhs/` 下。
>
> **不要**把图片输出到其他文章的目录或全局共享目录。
> 📌 2026-07-29 起路径从 `xhs-images/` 改为 `dist/xhs/`，与 [distribute.md](distribute.md) 的分发层目录约定统一；`distribute verify xhs` 按新路径查产物。


## 触发方式

在本 skill 体系中，用户说以下关键词时路由到本文件：

| 用户表达 | 触发 |
|---------|------|
| `写 小红书` / `转小红书` / `小红书图文` | → 本文件 |
| `提炼小红书` / `拆图文` / `做卡片` | → 本文件 |

## 核心理念

### 1. 不是"拆文章"，而是"重新讲故事"

❌ **错误做法**：把文章按段落切成 8 份，每份配一张图  
✅ **正确做法**：站在小红书用户的视角，用全新的叙事节奏重新编排原文精华

### 2. 每张图必须能独立成立，又能串联成线

- **独立性**：即使只看某一张，也能获得一个完整的信息点
- **连贯性**：从 P1 滑到最后一张，应当有明确的情绪递进和逻辑推进
- **钩子链**：每张图末尾设置"翻页钩子"，制造信息缺口驱动用户继续滑

### 3. 金句驱动

原文中的金句、数据、反直觉观点是小红书传播的核弹。提炼时优先锁定：
- 原文中最具传播力的 **3-5 句金句**
- 最震撼的 **2-3 组数据**
- 最反直觉的 **1-2 个观点**

这些是整套图文的骨架，其余内容围绕它们编排。

## 提炼工作流

### Step 1：深度阅读与精华萃取

通读原文后，按以下维度提取素材，输出一份**素材清单**：

```markdown
## 素材清单

### 金句池（按传播力排序）
1. "赚着钱裁人，裁完股价涨。" ← 原文第X段
2. "会用工具的人，已经在路上了。" ← 原文结尾
3. ...

### 数据弹药库
1. 2026年Q1美国裁员9万人（超2025全年5.5万） ← 原文第X段
2. Chegg股价从$113跌到$0.57，跌幅99% ← 原文第X段
3. ...

### 核心论点（按重要性排序）
1. AI裁员的本质：不是公司不行了，而是不需要人了
2. 人类三道护城河：共情、定义问题、处理意外
3. 多元收入 > 铁饭碗
4. ...

### 情绪锚点
- 开篇情绪：焦虑、共鸣（HR递过来离职协议）
- 转折情绪：震撼（赚钱也裁人的数据）
- 希望情绪：人类并没有输（三道护城河）
- 行动情绪：30天计划（具体可执行）
- 升华情绪：不是天要塌了，是会用工具的人已经在路上了
```

### Step 2：情绪曲线设计

小红书爆款图文的核心是**情绪递进**，而非信息堆砌。

**标准情绪曲线（5段式）**：

```
情绪强度
  ▲
  │          ★ 数据震撼
  │         ╱  ╲
  │        ╱    ╲        ★ 行动希望
  │  共鸣 ╱      ╲      ╱  ╲
  │  ╱  ╱        ╲    ╱    ╲  ★ 升华金句
  │╱  ╱          ╲  ╱      ╲╱
  │  ╱            ╲╱
  │╱               转折/护城河
  └────────────────────────────▶ 翻页进度
  P1   P2   P3   P4   P5-P7  P8  P9+
 封面  痛点  数据  冲突  方案  行动 升华
```

**每张图的情绪定位**（🔴 2026-07-02：开篇情绪按文章类型分流，不再一律焦虑/共鸣）：

| 段落 | 情绪功能 | 说明 |
|------|---------|------|
| 开篇（P1-P2） | **按类型分流**：成果 / 工具文 = **成果亮相**（先晒产出，比焦虑更抓人）；资讯文 = 事实冲击；深度 / 观点文 = 共鸣 + 焦虑 | 让用户一眼看到"有个能用的东西 / 出大事了 / 说的就是我"（源公众号开篇策略分流，见 [outline.md 步骤 3.5](outline.md)） |
| 冲击（P3-P4） | 震撼+不安 | 用数据和反直觉事实制造冲击 |
| 转折（P5） | 安心+希望 | "但人类没有输"，情绪拐点 |
| 方案（P6-P8） | 掌控+行动力 | 给出具体可操作的解法 |
| 收尾（P9+） | 升华+共鸣 | 金句结尾，引发互动 |

### Step 3：剧本编排（分镜脚本）

按以下模板为每一张图编写详细脚本。
**核心原则**：
1. **文案网感化**：提炼的文案必须符合小红书调性（网感强、适当使用Emoji、短句为主、直击痛点）。抛弃原文的学术或公文腔调。
2. **纯英文高维提示词**：视觉概念必须写成标准的纯英文 AI 绘图提示词，严格遵循格式：`主体描述 + 环境背景 + 摄影/艺术风格 + 光影细节 + 渲染参数 + （如果独立生图强制加 --ar 3:4 或 --ar 4:5）`。这样可以保证喂给底层模型时具备极致的画面控制力。

```yaml
---
page: 3
position: content         # cover | content | ending
layout: dense             # sparse | balanced | dense | list | comparison | flow | mindmap | quadrant
emotion: 震撼             # 当前页的情绪定位
swipe_hook: "这还只是冰山一角👇"  # 翻页钩子
---

## P3：三个月，九万人

### 核心信息（本页必须传达的唯一要点）
AI时代的裁员不是因为"公司不行了"，而是"公司很好，但不需要你了"。

### 文案内容（要求：网感强、Emoji、短句、痛点）
- **标题**：「三个月，九万人」
- **副标题**：2026年Q1，赚着钱裁人的时代
- **要点**（适配 dense 布局，5-8个信息点）：
  - 📊 美国2026年Q1裁员9万人 (超2025全年!)
  - 🏢 亚马逊：利润飙升40%，转身裁员3万
  - 💰 甲骨文：拿真人员工的命，换AI算力
  - 📱 Block：毛利暴涨24%，当天裁员一半
  - 📉 Chegg股价闪崩99%
  - 🏦 银行圈大地震：未来3年怒砍20万岗位
- **金句**：「赚着钱裁人，裁完股价涨。」

### Midjourney Prompt（纯英文结构化，融入选定的 Style 属性）
High-density infographic data board, Hand-drawn warm vector illustration style. 2x2 grid layout showing corporate data comparisons. Cozy desktop environment in the background with soft natural sunlight pouring in. Subject features rising profit charts and down-pointing employee count arrows with cute cartoon robotic and human icons. Colors: Warm orange, golden yellow, terracotta, cream background. Soft lighting, high detailed, minimalist interface design, UI/UX aesthetics, 8k resolution, flat vector art, --ar 3:4
```

### Step 4：文字乱码防控机制

#### 生图前：提示词排版与文字规范

在生成给大模型的提示词（Prompt）时，必须严格保留我们在 `xhs-outline.md` 中提炼的所有文字细节。小红书干货图文的灵魂是**高密度的排版与文字信息结构**，绝对不能因为害怕模型生出少量乱码就把文字删减掉，从而导致画面"空洞"、"没有实质内容"。

请在 Prompt 中强制注入以下指令，逼迫 AI 生成极具结构感的文字排版（如果用户未来挂载了阿里通义万象模型，这些文字将完美汉化呈现；即使用 Gemini，也会生成具备高度排版美感、待配字的干货卡片效果，而不是空洞的纯画图）：

```markdown
## Text Rendering & Layout Rules (CRITICAL)

1. This is a HIGH-DENSITY INFOGRAPHIC. You MUST render the detailed typographic layout for the exact Chinese text provided in the "Text Content" section below.
2. Structure the text exactly as provided (Titles, Subtitles, Bullet Points). Do not omit the structural elements.
3. Use bold, eye-catching text boxes for Titles. Use structured list formatting (ticks, dots, numbered icons) for the Points.
4. DO NOT render an empty decorative illustration. The canvas must be filled with structured information blocks, flowcharts, or grids as specified in the Layout.
5. Even if you cannot render Chinese characters perfectly, DO NOT omit them. Render the layout, typography hierarchy, and placeholders so the infographic design is functionally complete.
```

#### 生图后：视觉复查流程

每张图生成完毕后，执行以下复查：

```
生成图片
   │
   ▼
AI 视觉审查（view_file 查看图片）
   │
   ├─ ✅ 文字清晰可读 → 通过，继续下一张
   │
   └─ ❌ 发现乱码/错字/多余文字
        │
        ▼
      修改 prompt（加强文字约束或减少文字量）
        │
        ▼
      重新生成（最多重试2次）
        │
        ├─ ✅ 通过 → 继续
        └─ ❌ 仍然失败 → 标记为"需手动配字"，
                         生成纯视觉版（不含文字）
```

## 图片数量决定逻辑

不拘泥于固定张数。根据原文内容量和信息密度，在 **6 - 16 张**图片里浓缩体现、动态决定：

| 原文字数 | 核心论点数 | 建议图片数 | 结构 |
|---------|-----------|-----------|------|
| < 3000字 | 2-3个 | 6-8张 | 封面 + 2-3内容 + 1-2方案 + 结尾 |
| 3000-6000字 | 3-5个 | 8-10张 | 封面 + 导读 + 3-4内容 + 2-3方案 + 结尾 |
| 6000-10000字 | 5-8个 | 10-12张 | 封面 + 导读 + 4-6内容 + 3-4方案 + 金句 + 结尾 |
| > 10000字 | 8+个 | 13-16张 | 封面 + 痛点爆破 + 极密干货输出 + 方案地图 + 升华结尾 |

## 布局分配策略

**必须遵循的铁律**：每套图文中，至少使用 **4种不同布局**。

### 按页面位置的布局推荐

| 页面位置 | 推荐布局 | 理由 |
|---------|---------|------|
| P1 封面 | `sparse` | 最大视觉冲击，标题一目了然 |
| P2 导读/痛点 | `balanced` | 建立上下文，不宜太密 |
| P3 数据/事实 | `dense` | 信息密度拉满，满足"干货感" |
| P4 对比/冲突 | `comparison` | 左右分栏，视觉对比极强 |
| P5 核心框架 | `dense` 或 `list` | 体系化呈现（如"三道护城河"） |
| P6-P7 方案/步骤 | `flow` 或 `list` | 流程图或清单，可操作感强 |
| P8 行动计划 | `list` | 勾选框清单，收藏价值高 |
| P9+ 结尾 | `sparse` | 金句 + CTA，干净有力 |

### 布局混搭示例（9张图文）

```
P1: sparse    → 封面（标题+情绪画面）
P2: balanced  → 痛点共鸣（故事切入）
P3: dense     → 数据震撼（2x2裁员数据网格）
P4: comparison→ 新旧逻辑对比（左右分栏）
P5: dense     → 三道护城河（知识卡片）
P6: flow      → 个人转型路径（路线图）
P7: list      → 30天行动计划Part1（清单）
P8: balanced  → 30天行动计划Part2（工具推荐）
P9: sparse    → 金句收尾（升华+CTA）
```

## 输出格式

最终输出文件：`xhs-outline.md`

```yaml
---
source: 定稿.md
title: "AI会否取代你的工作"
xhs_title: "2026赚钱也裁人｜但人类有三道护城河"
style: warm
image_count: 9
emotion_arc: 共鸣→震撼→转折→行动→升华
layouts_used: [sparse, balanced, dense, comparison, flow, list]
golden_quotes:
  - "赚着钱裁人，裁完股价涨。"
  - "掌握AI工具的人，会淘汰那些拒绝使用AI的人。"
  - "会用工具的人，已经在路上了。"
generated: 2026-04-01 13:00
---

## P1 of 9
...（每张图的完整脚本，格式同 Step 3 模板）
```

## 钩子策略参考

每张图末尾的"翻页钩子"类型：

| 钩子类型 | 示例 | 适用位置 |
|---------|------|---------|
| 悬念钩 | "但真正可怕的还在后面👇" | P2→P3 |
| 数字钩 | "接下来的数据会让你坐不住👇" | P1→P2 |
| 反转钩 | "然而，人类并没有输👇" | P3→P4 |
| 方案钩 | "怎么破？往下看👇" | P4→P5 |
| 行动钩 | "30天破局计划来了👇" | P6→P7 |
| 金句钩 | "最后一句话送给你👇" | P8→P9 |

## 质量检查清单

提炼完成后，逐条核对：

- [ ] **金句锁定**：是否提取了原文中最具传播力的 3-5 句金句？
- [ ] **数据弹药**：关键数据是否准确完整？
- [ ] **情绪曲线**：从 P1 到最后一张，情绪是否有明确的起伏和递进？
- [ ] **布局多样**：是否使用了至少 4 种不同布局？
- [ ] **独立可读**：每张图单独看，是否能获得一个完整信息点？
- [ ] **连贯叙事**：连续滑动，是否能感受到连贯的故事线？
- [ ] **钩子完整**：每张内容图（非末尾图）是否都有翻页钩子？
- [ ] **金句收尾**：最后一张是否以金句或升华语句结尾？
- [ ] **文字精简**：每张图的文案是否足够精炼（避免大段文字）？
- [ ] **原文忠实**：所有观点和数据是否忠实于原文，未添加捏造内容？

### Step 5：交给已配置的渲染适配器

当系统输出 `xhs-outline.md` 后，若当前任务明确包含出图，则继续调用已配置的卡片渲染适配器；若只要求脚本或大纲，则停在该文件，不擅自扩大任务范围。

1. **结构稿是单一真源**：渲染器只能消费 `xhs-outline.md`，不得重新分析后改写观点、数据或页序。
2. **直接编译 Prompt**：每页按已经确定的布局、文字和视觉规范编译为独立 prompt，不重复向用户确认已确定事项。
3. **⚠️ 禁止串接封面参考图**：各页构图差异很大，不得把封面作为后续页面的结构参考；连贯性只由统一 Style、调色板和字体规则维持。
4. **逐页留证**：记录 prompt 哈希、渲染器、provider、model、输出文件与字节哈希；失败必须显式停止，不得换一条未声明链路绕过。
5. **独立验收**：渲染完成后逐页检查文字、版式、信息忠实度和页间一致性，通过后再加水印与交付。
