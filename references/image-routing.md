# 🟢 生图工具唯一路由决策树

## 🔴 第零分支：人物/新闻事件配图 = 搜真实新闻照，不生图

文章讨论**关键新闻人物**（中英文人名皆算，如某位工程师、某位创始人、某位企业高管）或**重大新闻事件**时，**主动**搜索并截取真实新闻照片插入正文--AI 生成人物肖像一律禁止（既失真又有肖像权风险）。这是配图路由的第一判定：先问"这是真人真事吗"，是 → 走本节搜图；否 → 走下方生图决策树。

**执行 SOP：**

1. **搜图**：用带图片检索能力的搜索工具（如 `firecrawl_search` 带 `sources: [{type: "images"}]`，返回 imageWidth/imageHeight 可预筛），关键词 = `人名 + 公司/身份 + photo`。信源优先级：新闻媒体现场照 > 本人官网 bio/press 页 > 会议演讲者页。**避开**：视频平台缩略图（叠大字标题）、播客双人分屏截图、戴墨镜/侧脸照、带第三方网站描边的图、社媒中转链（不稳定）。
2. **下载**：`curl -sL -A "<浏览器UA>"`；原图宽 <800px 的换候选。
3. **肉眼核验**（Read 工具看图，硬门）：主体明显突出、正脸清晰可辨、无第三方 UI/字幕/水印压身。
4. **16:9 截取**：Pillow `crop((0, y_top, w, y_top + round(w*9/16)))` 全宽窗口，纵向选窗保主体--**头顶不贴边、下巴不出框、绝不截半边脸**；🔴 **只裁不缩放拉伸**（等比无所谓，改变纵横比的 resize 禁止）。裁后**再 Read 核验一次**构图。16:9 的用意：压缩视觉高度，不挤占正文阅读。
5. **落盘**：`素材/news-<人名小写>.jpg`（quality 88）。🔴 `news-` 前缀是协议：`add_logo.js` 按前缀跳过水印（新闻照非本号产物，打品牌水印=冒认版权）；不登记 `.gen-log.jsonl`（非 AI 生成图）；<2MB 不用压缩。
6. **插入定稿.md**：标准 md 图片语法（路径正斜杠）+ 紧跟一行图注：
   `<section style="text-align:center;font-size:12px;color:#999999;">人物身份一句话｜图源：XXX</section>`
   🔴 图注必须用 `<section>`（p/section 等 HTML 块行已豁免出 preflight 开篇锚点统计，section 与信息来源栏同先例最稳）。图注身份描述必须与照片真实场景相符，别张冠李戴（会场照不能写成"对谈现场"）。
7. **位置与密度**：插在该人物**首次被完整介绍的段落之后**；一篇 2-4 张为宜，与信息图错开、不连排。

## 🔴 第零分支之二：厂商官方产品截图 = 抓官方素材，不生图

文章**评测 / 对比 / 解读某个软件产品**时（如 Claude Code、Codex、某 App），要让读者看到"这软件跑起来长什么样"，走本节抓**官方产品界面截图**--AI 生图画不出真实 UI（画出来的是幻觉界面，一眼假、且等于伪造产品外观）。判定：出现"某软件/某产品长什么样、界面、运行效果"→ 本节；产品的**抽象概念/架构/数据**才走下方生图决策树。

**执行 SOP：**

1. **找图源**（按可得性排序）：① 厂商 GitHub 仓库的 `README.md` / `.github/` 目录（常有 splash / demo 截图，`raw.githubusercontent.com` 直取，最稳）；② 官方产品页 / 文档站 / 官方博客的 HTML 里 `<img src>` 与 `og:image`（`curl -sL <页面> | grep -oE '...(png|webp|jpg)'` 捞资源路径）；③ 实在没有 → 无头浏览器导航官方页截图。
2. **下载**：`curl -sL "<url>" -o 素材/vendor-<产品>-<形态>.png`（URL 含 `?`/`&` 必须加引号）。webp/avif 用 Pillow 转 PNG。
3. **肉眼核验**（Read 工具看图，硬门）：① 画面确实是**软件界面**（终端 / 工作台 / 对话框），不是 logo、营销插画、人像、占位图；② **四边不被裁切**（官方营销图常做局部特写，右侧文字断在边缘的一律弃用）；③ 图里的版本号 / 模型名与文章讨论的时间窗口**不要差太远**（差一两个版本可接受，差几十个版本会被懂行读者抓）。不合格 → 换候选，别将就。
4. **落盘**：`素材/vendor-*.png`。🔴 `vendor-` 前缀是协议：`add_logo.js` 按前缀跳过水印（**厂商官方素材非本号产物，打自家水印=冒认版权**，与 `news-` 同源）；不登记 `.gen-log.jsonl`（非 AI 生成图）；>2MB 才压缩。
5. **插入定稿.md**：与新闻照同构 -- 简短 alt 的标准 md 图片语法 + 紧跟一行 `<section>` 图注，**图注必须标图源厂商**：
   `<section style="text-align:center;font-size:12px;color:#999999;">这张图里能看到什么（一句话）｜图源：XXX 官方</section>`
6. **位置**：插在**正文刚讲完该界面对应的机制之后**（先说清机制，再上图印证）；图后可接一句"看这里"式的读图指引，但**只指正文论点相关的那一处**，不复述图里显而易见的东西。
7. **版权兜底**：文末「📎 信息来源」栏必须有一条说明"文中软件界面图均为 XX 官方公开素材，版权归各自所有，此处作评述引用"。

## 🟢 第零·五分支：作者供图（截图 / 实拍）= `shot-` 前缀，不走生图、不加水印（2026-07-21 实战固化）

作者自己提供的截图 / 实拍素材（如系统通知邮件、后台页面、软件界面、官网价格页、桌面同屏照），与 AI 生图、新闻搜图都不同，按本节处理：

1. **落盘**：复制进 `素材/`，命名 `shot-<主题>.<ext>`（如 `shot-mail.jpg`）。🔴 不要拖 `素材/prompts/` 里。
2. **不加水印**：`shot-*` 是作者自有素材，不跑 `add_logo.js`（同 `news-` 前缀的处理逻辑；批量跑 add_logo 时如被误伤，重拷原图即可）。
3. **不登记 `.gen-log.jsonl`**：非 AI 生成图，`pipeline.py log` 只记 AI 产物。
4. **必须带图注**：标准 md 图片语法 + 紧跟一行 `<section style="text-align:center;font-size:12px;color:#999999;">内容一句话｜图源：我的桌面 / 我的邮箱 / XX 官网</section>`。
5. **嵌入正文才过门**：`verify_publish_assets` 要求 `素材/*.png` 全部在 `定稿.md` 中有 `![` 引用（cover/hero/bgm_cover 等组件小图除外）--shot 图拷进来不嵌会阻塞排版。
6. **废图进 `素材/未采用/`**：该子目录的 PNG **不参与**嵌入断言与压缩，废弃候选统一挪进去，别删（留作复盘）。
7. **一手事实对齐**：截图里的时间戳 / 数字 / 状态（如表单提交时间）是一手事实，**写正文时必须与截图一致**--正文叙述与供图打架是冷读最疼的断点（典型形态：正文写「8:35 提交申诉」，另一张截图却显示相关事件 8:42 才发生，时间顺序写反了）。

---

## 🟢 两层路由：baoyu 是语义生产者，imagegen/gen_img 是像素渲染器

封面与信息图必须先走专业 Skill，不能把“能出一张 PNG”误当成“走完专业视觉流程”：

| 层 | 职责 | 封面 | 信息图 |
|---|---|---|---|
| **producer** | 分析文章、选构图/版式、套 style/palette、生成最终 prompt | `baoyu-skills:baoyu-cover-image` | `baoyu-skills:baoyu-infographic`（精确拓扑例外 `baoyu-diagram`） |
| **renderer** | 把已确认 prompt 渲染成像素 | child skill 选定的 `imagegen` / `gen_img` / 兼容后端 | 同左 |

🔴 `gen_img.py`、原生 `imagegen`、`baoyu-image-gen` 都只能记为 **renderer**；直接拿它们写 prompt 或出最终图，不能在日志里冒充 `baoyu-cover-image` / `baoyu-infographic` producer。

### canonical prompt 与一次确认

1. 候选 prompt 可放 `素材/prompts/candidates/`；最终选中的唯一版本必须复制到 `素材/prompts/final/`。
2. `pipeline.py log` 只接受 `素材/prompts/final/*.md` 作为封面/信息图最终记录，并同时记 producer、renderer、model、prompt/output SHA-256。
3. 用户已要求“完整流程 / 一路到草稿箱”或已批准 blueprint 时，这份外层确认同时覆盖 child skill 的版式、风格与 quick-mode 选项；主流程把已确认参数显式传给 child skill，**不再为同一组选项二次打断用户**。分析稿、结构稿、prompt 落盘步骤仍不得省略。
4. 私有偏好放 `~/.baoyu-skills/<skill>/EXTEND.md`；外层 `article-meta.yaml` 与 blueprint 的本篇明确值优先。

标准顺序：

```text
baoyu producer 分析/选型 → 写 canonical prompt → renderer 出原始 PNG
→ pipeline.py log（登记原始渲染字节）→ add_logo/compress
→ Agent 逐张看最终图并写 _visual-qa.md → pipeline.py seal visual
→ publish 内联门 → 微信草稿 → publish receipt
```

`gen_img.py` 仍是可选 renderer，负责 provider 分流、比例和确定性缩放；但是否使用它由 child skill / 当前 agent 能力决定，不能越过 producer。密钥只从环境变量读取，不写入 prompt、日志或仓库。

### 🔴 信息图 = 内容总结 + 版式 + 风格；producer 负责思考，renderer 只负责渲染

**信息图 ≠ 概念插画。** 最容易犯的错是画一堆好看的黏土场景，风格对、信息为零--读者一眼看穿"没有文章总结"。信息图的核心价值是「先分析该段内容 → 从常见版式里选一个（清单 / 左右对比 / 箭头流程 / 分区矩阵…）→ 把文章里的实际要点·数据当图内文字排进去」，风格只是最后一层皮。

每张信息图的 prompt 必须含三件套：
1. **真实内容**：该段的 3-6 个原文要点 / 数字 / 标签（如清单那几项、成本分层的具体名目、流程的几步）作为**图内可读中文文字**；
2. **版式骨架**：一个明确的信息结构（checklist 行列 / 左右对比 / 箭头流程 / 分区矩阵），不是"一座房子+几个图标"的随意摆放；
3. **风格**：从下文「信息图 style 二选一」定的 `claymation` 或 `morandi-journal` 里取配色 hex / 视觉元素 / **Avoid 清单**（如某些风格明确 "Avoid: emoji / pure white background"），拼进 prompt。

**自检红线**：若一张图的 prompt 通篇只在描述"物件 / 场景"、没有一句来自原文的要点文字 → 那是装饰插画不是信息图，**打回重写**。同篇 4 张共用同一 style 描述 → 风格一致。

⚠️ **代价权衡**：图内中文要点多 → image 模型偶尔糊字 / 错字，须生成后逐张核验、糊的重生；糊字严重且要点是精确数据的，改走本地 matplotlib/pyecharts（文字 100% 准）。**宁可糊字重生，也不退回"零信息的好看场景"。**

---

## 生图路由表

任何封面/信息图最终产物必须在**原始 PNG 生成后、加 logo 前**立即写入 `.gen-log.jsonl`：

```bash
python "$SKILL/scripts/pipeline.py" log <stage> <producer> \
  --output 素材/xxx.png \
  --prompt 素材/prompts/final/xxx.md \
  --renderer <renderer> --model <model> --cmd "原始调用摘要"
```

| 场景 | producer → renderer | 关键约定 | 产物要求 |
|-----|---------|---------|---------|
| 微信头图 / 封面图 | `baoyu-cover-image` → child 选定 renderer | canonical prompt 固定 `素材/prompts/final/cover.md` | 默认风格见 cover-styles.md，2.35:1，标题块 18--22% |
| 全文贯穿信息图 ≥ 4 张 | `baoyu-infographic` → child 选定 renderer | style 二选一；每张一份 final prompt | 开篇/结尾 9:16 各 1 张 + 中间 16:9 ≥ 2 张，中文标签 |
| 精确流程/时序/架构/原理图（低频） | `baoyu-diagram` → `svg_to_png.py` → PNG | `--type flowchart\|sequence\|structural\|illustrative` + 必须强制覆写主题色 | 仅 ≥5 节点 + 拓扑/顺序是核心论点时启用，详见 layout.md 3g |
| 正文导读栏小图（hero） | `gen_img.py` | `1:1`，model `gemini-3.1-flash-image-preview` | 1:1 方图（bgm_cover 由 BGM 阶段 gen_img.py 产出，不走此路由） |
| 正文叙事插图 | `gen_img.py` | 按场景比例，1K；**画风并入本篇 `infographic_style`**，立意走「隐喻三步法」（见下文「正文叙事插图」节） | 单图单概念 + 每篇不复用旧构图 |
| 社媒图卡 / 小红书轮播 / 微信图文 | `baoyu-xhs-images` | `--style xxx --layout yyy --palette zzz` | 12 风格 × 8 布局 × 3 palette |
| 数值型图表（雷达/折线/柱状/饼） | 本地 Python 脚本 `matplotlib` / `pyecharts` | -- | **严禁大模型生图**，见数据图防幻觉铁律 |
| **配图后处理（每篇必跑）** | `compress_images.py` | `--max-mb 2` | 在 `add_logo.js` 之后、推送之前；每张 PNG ≤ 2 MB（详见 layout.md 3h） |

🔴 **每次生图必须显式传目标尺寸/比例，不要依赖默认值**：本 skill 场景各处比例不同--hero 是 `1:1`、infographic 是 `9:16` / `16:9`、cover 是 `2.35:1`、bgm_cover 是 `1:1`。遗漏就会默默得到错误比例的图，排版时才发现。

**落地规则：**
1. 每次生图前，先在心里对号入座「我现在要生的图属于路由表哪一行」。对不上就停下问用户，绝不让通用生图接管。
2. 封面图严格使用锁定的品牌调性参数（`--palette dark --rendering minimal --font clean --mood bold`），文字排版铁律见下。
3. 生成完成后，**同一轮回复内、加 logo 前**立即用 v2 参数 `pipeline.py log` 记录。缺 producer/renderer/model/hash/canonical prompt 任一项都会阻断。
4. `pipeline.py verify cover/infographic` 会核对 producer 白名单、renderer、prompt/output 摘要、style、比例和分辨率；`seal visual` 再绑定后处理后的最终字节。
5. **迁移旧文章**（`.gen-log.jsonl` 缺失）时允许加 `--legacy` 临时放过，新文章严禁使用。

**封面文字排版铁律**（cover.md prompt 必守）：
- **关键词高亮**：主标题只给核心关键词（数字、对比词、人物）上主题色 `#2F6F8F` + 加粗，其余部分保持白/浅灰。**严禁整句全色或全黑**。
- **副标题分层**：副标题拆成 3–4 段不同字重/透明度/强调（**双色铁律内**：仅用主题色 `#2F6F8F` / 纯白，靠字号 / 字重 / 透明度 ≥70% 分层；**严禁灰色相**）。**严禁副标题单一字重一行到底**。
- **留白比例**：布局侧别由 `cover-styles.md` 决定；默认 `montage-evidence` 是左侧文字、右侧证据拼贴，标题块总高 18--22%，不得反转套用旧 EXTEND。
- **背景基调**：深色底（#0E0E10 左右）+ 主题色微光晕，**严禁纯黑或亮背景**。
- 🔴 **禁止 AI 渲染品牌识别小字**：右下角不写任何品牌名/编号/署名 -- `add_logo.js` 后期会自动叠加品牌 Logo，再渲染就重复。prompt 必须显式 forbidden 这一条。

**数据图防幻觉：** 数值型图表（雷达/折线/柱状/饼/跑分）**严禁扔给大模型生图**--大模型会把 7 维画成 5 维、数值胡乱标注。必须写 Python 脚本（`matplotlib` / `pyecharts`）精确渲染保存本地 png，且 `.py` 脚本本身留在文章目录内以便复核。`pipeline.py verify` 会做"图表产物必须伴随本地 .py 脚本"断言，缺脚本直接拦截。大模型仅限用来生成思维导图、架构流程等"感性知识图"。

**Agent 原生工具黑名单：** 严禁调用 `generate_image` / `internal_image_gen` / `imagine`（小写内置工具）--它们会把输出锁死为 1:1，破坏微信封面 2.35:1 的硬性要求。

---

## 🔴 信息图 style 选择铁律（二选一）

信息图风格只允许在 2 种里二选一：

| 风格 | 适用题材 | 视觉气质 |
|---|---|---|
| **`claymation` 暖米黄轻盈版** | AI 工具教程 / 产品评测 / 功能解读 / 实操指南 / 技术拆解 | 立体黏土卡片 + 暖米黄背景 #F5F0E6 + 主题色 + 米白 + 浅灰 + 轻盈温暖、有故事感 |
| **`morandi-journal` 莫兰迪杂志风** | 行业趋势 / 商业评论 / 人文反思 / 价值判断 / 生活方式 / 温和议题 | 莫兰迪柔色（灰绿/桃/浅紫/暖黄）+ 手绘 doodle + washi tape + bullet journal 质感 |

### 🔴 一句话判定法

- 「解释一个工具怎么用 / 一个产品怎么样」→ **claymation 暖米黄**
- 「评一个现象 / 一个趋势 / 一个价值观」→ **morandi-journal**

### 🔴 混合题材优先级：先看信息架构主轴，不看文体标签

两种气质都沾时，**产品/模型轴优先于趋势结论**：只要信息图的卡片、对比列、时间线或结论主要围绕
具名 AI 模型 / 工具 / 产品 / 功能展开（新品速递、模型发布盘点、N 款横评、版本更新解读都算），
即使文章外层是「资讯 / 行业趋势 / 商业评论」，仍归 `ai-product` → **claymation**。只有产品名只是
支撑观点的例子、信息图主轴本身是现象 / 商业关系 / 人文判断时，才归 `phenomenon` →
**morandi-journal**。不得再用模糊的「读者主要想听你怎么看」覆盖产品型信息架构。

`article-meta.yaml` 必须同时显式写：

```yaml
infographic_subject: "ai-product"      # 或 phenomenon
infographic_style: "claymation"        # ai-product 固定 claymation；phenomenon 固定 morandi-journal
visual_profile: "warm-light-clay"      # claymation 必填；morandi-journal 留空
```

这是机器门的 SSOT；`analysis.md`、`structured-content.md`、prompt frontmatter、最新精确 output 的
gen-log 与 `final-set.json` 必须全部一致，否则 `pipeline.py verify infographic` 阻断。`visual_profile`
是配方名，不是另一套发布版本号；实际参数用内容摘要 `visual_profile_sha256` 防静默漂移。

### 🔴 同篇不混风格

**单篇文章所有信息图（≥4 张）必须风格统一，禁止 claymation + morandi-journal 在同一篇里混用**。视觉系统会乱（暖米黄黏土的立体感跟莫兰迪杂志的手绘 doodle 放一起会打架）。

### 🔴 二选一是硬约束

- 其他风格（craft-handmade / knolling / hand-drawn-edu / storybook-watercolor / claymation 深色版 等）**全部封存**，新文章不再选用。深色背景版 claymation 属历史遗留，文字太厚重、颜色太深、压抑，新文章不再选。
- `article-meta.yaml` 加 `infographic_style` 字段显式指定 `claymation` 或 `morandi-journal`。
- 完全没指定时默认 `claymation`（AI 工具类主线题材占多数）。

### 写 prompt 时
- frontmatter 必写 `style: claymation` 或 `style: morandi-journal`
- `claymation` 先在文章目录运行：

  ```bash
  python "$SKILL/scripts/pipeline.py" visual-contract
  ```

  把输出的 `visual_profile`、`visual_profile_sha256`、`palette_background`、
  `palette_accent` 原样复制到**每一张信息图与 Hero** 的 canonical prompt frontmatter。
- Prompt 正文同时明确：暖米黄/暖象牙背景、浅色调、哑光软黏土、柔和漫射光与低对比；
  不得正向要求 charcoal/dark/black background、navy/steel blue、brick red、mustard yellow、
  metallic/chrome/neon 或 high contrast。若在 Avoid 句里出现这些词不算违规。
- `pipeline.py log infographic|hero ...` 会在登记证据前先校 prompt 与最终像素；缺配方、
  hash 漂移、暗部面积过大、平均亮度过低或过饱和都会立即阻断。日志自动记录
  `visual_profile(_sha256)`；跨 Agent 排障时可加 `--host-agent` 与 `--extend-sha256`。

### 🔴 Hero 与信息图共用浅色配方

`素材/hero.png` 不是“科技感自由发挥区”。`claymation` 文章的 Hero 必须使用同一个
`warm-light-clay` 配方、同一主题主色和同一材质/光照约束，canonical prompt 放
`素材/prompts/final/`，并用 `pipeline.py log hero ...` 登记。最终像素与四张信息图走同一色调门；
深色金属、黑底霓虹、电影级高反差即使构图好看也打回重生。

### Renderer 策略：固定合同，不固定厂商

不要因为某一篇深色成图就把 `renderer` 永久钉死。2026-07-23 用同一份
`warm-light-clay` Prompt 对 Gemini 与 GPT Image 做 A/B：两者均通过色调门
（平均亮度约 215 / 206，暗部占比均低于 2%），差异明显小于“Prompt 配色被改写”造成的漂移。
因此当前策略是：producer 仍走 baoyu 专业流程，像素后端可按可用性选择；真正不可变的是
profile 配方、canonical prompt、日志摘要与最终像素门。只有后续**同 Prompt、同构图规格**
连续复现某后端越线，才讨论固定 renderer，不能用非对照样本归因。

### 🔴 生成后视觉 QA（不向用户停顿，但 Agent 必须看图）

四张图生成后逐张打开核验：画风、图中文字、信息层级、乱码/杂字、Logo 冲突与裁切安全区；失败就改
prompt 重生。结果落工作目录 `_visual-qa.md`。`claymation` 除原有检查外，必须显式记录
**背景、主色、禁用色、材质、写实感、Hero 一致性**，总勾选项不少于 12 条并写最终「通过」。
QA 对象必须是 **add_logo + compress 之后的最终字节**；通过后执行 `pipeline.py seal visual`。
调用微信前必须先跑 `pipeline.py verify publish --pre` 写 `_publish-ready.json`；
`done publish draft_media_id=...` 会复验 ready、内联重跑全部门并写最终 receipt，`--force` 也不能绕过。
「后端零停顿」只是不打断用户，绝不等于生成即发布、跳过 Agent 自检。

推荐记录骨架：

```markdown
# 视觉验收记录
- [x] 封面主标题与缩略图主次
- [x] 封面无杂字
- [x] 封面裁切安全
- [x] 图 1 信息图逐字核对
- [x] 图 2 信息图逐字核对
- [x] 图 3 信息图逐字核对
- [x] 图 4 信息图逐字核对
- [x] 四张信息图风格一致
- [x] 背景为暖米黄/暖象牙浅色
- [x] 主色与 visual-contract 输出一致
- [x] 禁用色未成为主视觉
- [x] 材质为哑光软黏土
- [x] 无金属/照片级写实感
- [x] Hero 与信息图同配方

结论：通过
```

---

## 🟢 正文叙事插图（隐喻立意 + 画风并入信息图系）

> **定位**：叙事插图 ≠ 信息图。信息图排「原文要点 + 版式」（信息密度型）；叙事插图给正文一个**概念的视觉隐喻**——把一段的抽象论点变成一眼看懂的画面，配合叙事节奏。以下立意/构图/质检方法借鉴 `ian-xiaohei-illustrations`（MIT），**只取方法论、不用其「小黑」IP**。

### 🔴 画风：并入本篇信息图风格系（不另立第三套画风）

叙事插图**沿用本篇 `infographic_style` 的视觉气质**——`claymation` 篇 → 黏土系叙事图，`morandi-journal` 篇 → 莫兰迪杂志系叙事图。同篇里「封面(montage) + 信息图 + 叙事插图」中，**信息图与叙事插图共用一个视觉系统**，不引入白底线稿等第三套画风，避免同篇视觉打架（2026-07-13 sandy 拍板 B-2：并入信息图系，而非新增独立画风）。

### 🔴 原创隐喻三步法（治「AI 配图千篇一律、一上来就画通用场景」）

别直接画"一个人对着电脑""一堆齿轮"这类万能场景。按三步把抽象概念落成一个具体、略反常的画面：

1. **抽象概念** → 抓这段最核心的一个论点（如「成本被压到三分之一」「数据被漏掉」「多智能体并行」）；
2. **物理动作** → 翻译成一个具体物理动作：卡住 / 漏掉 / 变重 / 被挤 / 分叉 / 倒灌 / 层叠…；
3. **低科技实物** → 给动作配一个日常低科技实物做载体：箱子 / 漏斗 / 秤 / 管道 / 抽屉 / 阶梯 / 天平…，让画面**主体去执行这个动作**（漏斗在漏、秤在压、管道在倒灌）。

**单图单概念**（一个概念一张图，别把三件事堆一张）；**每篇重新发明隐喻、不复用旧构图**（复用会让不同文章的插图撞脸，丢掉「这篇专属」的信息量）。

### 🔴 叙事插图 QA 门（仿 ian「失败信号 + 交付判断」双层，与信息图自检红线同构）

出图后逐张自检：

- **失败信号（命中即打回重画）**：① 通篇只有装饰物件、没有承载本段论点的那个动作/隐喻（= 装饰画，同信息图「零信息好看场景」红线）；② 复用了本文别处或旧文的构图；③ 一张图塞了 ≥2 个概念；④ 图内文字糊字/错字。
- **交付判断（正向锚）**：遮住配文只看图，能不能猜到这段在讲什么核心概念？能 → 过；只觉得「好看但不知所云」→ 隐喻没立住，回第一步重想。

### 🔴 图内文字护栏（全生图通用，借鉴 baoyu-image-gen 两条栅格图硬护栏）

任何 AI 生图（封面 / 信息图 / 叙事插图 / hero）**图内文字出错时，禁止用 PS / ImageMagick / 任何工具在成图上「覆盖修字」**——覆盖会留痕且字体不匹配。**唯一正确做法 = 改 prompt 重新生成**；糊字严重且是精确数据的，改走本地 matplotlib（文字 100% 准，见数据图防幻觉铁律）。同理**禁止用 SVG/HTML/canvas 假冒栅格图**冒充生图产物。

---

## 🔴 1K 分辨率横切规范（所有生图统一）

**所有经生图工具产出的 PNG（封面 / 信息图 / 组件小图 / 叙事插图 / 社媒图卡），分辨率统一为 1K -- 长边 ≈ 1024px，宽高比按各场景路由不变。**

- **判定带**：长边落在 `[900, 1200]` 视为达标（1K 标称 1024，容差吸收各生成器/压缩链路取整；常见落点 960/1000/1024/1080/1152 均在带内）。
- **比例不变**：1K 只约束**长边像素**，不改各场景宽高比--封面仍 2.35:1、信息图开篇/结尾 9:16、中间 16:9、组件小图 1:1。
- **🟢 例外：matplotlib / pyecharts 数据图表不受 1K 限制**--数据图走本地脚本 `dpi=300`（正式）按内容尺寸渲染，由「数据图防幻觉铁律」单独约束，**不**纳入 1K 横切带。
- **机器校验**：新产出的信息图集合由 `scripts/contracts.py:verify_infographic_set` 在验证门按**实际像素**判 1K（与 ≥4 张 / 9:16+16:9 构成 / ≤2MB 同关）。此门是语义关、**只对新产出强制，不追溯历史冻结 golden**。
- 🔴 **image 模型出图常无视目标尺寸、原生吐更大长边（如 1376 / 1584）-- 超出 [900,1200] 带**。`gen_img.py` 已内置"出图后 PIL 缩到精确目标尺寸"这一步（9:16→576×1024、16:9→1024×576、2.35:1→1024×434、1:1→1024×1024）；aspect 容差只有 ±2px，缩放按"精确目标尺寸"而非"只缩长边"（768×1376 只缩长边到 1024 得 572×1024，差 4px 会 aspect 判否）。
- 🔴 **信息图文件名必须 `infographic-*.png`（`infographic` 前缀）**：`pipeline.py verify infographic` 用 `素材/glob("infographic*.png")` 数张数，命名成 `info-*` / `图1-*` 等会被判「0 张」失败。封面固定 `cover.png`、导读 `hero.png`、信息图 `infographic-NN-主题.png`。

---

## 📊 matplotlib 本地渲染规范（数据图专用）

### 哪些图走 matplotlib，哪些走生图模型

| 图表类型 | 走 matplotlib ✅ | 走生图模型 ❌ |
|---------|----------------|-----------|
| 横向条形图（价格/配额/排名对比） | ✅ | -- |
| 纵向柱状图（时序/周期对比） | ✅ | -- |
| 折线图（趋势、增长曲线） | ✅ | -- |
| 饼图/环形图（占比） | ✅ | -- |
| 雷达图（多维评分） | ✅（优先 pyecharts） | -- |
| 含具体数值的对比矩阵 | ✅ | -- |
| 思维导图、架构流程图 | -- | ✅ baoyu-diagram |
| 知识图卡片（无具体数值） | -- | ✅ 信息图 |
| 封面图 | -- | ✅ baoyu-cover-image producer → 选定 renderer |
| 叙事插图 | -- | ✅ baoyu-article-illustrator producer → 选定 renderer |

> **判断口诀：有数值 → matplotlib；纯图示/知识图 → 生图模型。**

### baoyu-diagram（精确图专用通道，按需触发）

`baoyu-diagram` 输出**严格精确**的架构图 / 流程图 / 时序图 / 类图 / 数据流图 SVG（Claude 直接手算坐标写代码，元素位置 100% 精确）。

**适用场景**（layout.md 3g 触发器决定，自动判定）：
- 技术教程类文章（how-to）
- 多源协同流程文
- 系统拆解文（多组件架构 / 分层架构）
- 抽象机制图解（分级模型 / 颗粒度错配等）

**不适用场景**：观察/反思/感性文（直接走信息图即可）、步骤少于 5 个、文章总长 < 5000 字。

**调用流程（4 步）**：
1. 通过 Skill 工具调用 `baoyu-skills:baoyu-diagram`
2. **必须**显式覆写 prompt 中的颜色为主题色 + 黑白灰双色（baoyu-diagram 默认多彩，违反双色铁律）
3. SVG 输出后调 `scripts/svg_to_png.py --check-brand --width 1200` 转 PNG（自动主题色校验）
4. `add_logo.js` 加水印 → 嵌入正文

详见 [layout.md 3g 章节](layout.md) 完整规则（含 5 种 type 触发器、主题色覆写模板、SVG→PNG 转换命令）。

### 社媒图卡后端：baoyu-xhs-images（统一接口）

`baoyu-xhs-images` 是社媒图卡通用接口--12 风格 × 8 布局 × 3 palette，覆盖小红书 + 微信图文 + 微博九宫格等所有社媒图卡场景。本 skill 的 xhs-storyboard 路径走 `baoyu-xhs-images`。

---

### 品牌样式标准

品牌 token（配色/圆角/署名）集中在 `profile/brand.yaml`，渲染期由 `format_layout.py` 的 `process_theme()` 换皮。下面的 hex 是默认中性主题（primary `#2F6F8F`）的取值，改主题只改 `profile/brand.yaml`、不改本文。

**颜色：**
- 主色条：`#2F6F8F`（主题色 primary）
- 次色条/辅助条：`#B6D2DE`（浅主题色）
- 正文文字：`#2C2C2C`（深灰）
- 注释/副标题：`#666666`（中灰）
- 网格线：`#EEEEEE`（极浅灰）
- 禁用：matplotlib 默认蓝 `#1f77b4`、红 `#d62728`、橙 `#ff7f0e`

**字体（Windows / macOS / Linux 自动检测）：**
```python
def get_cn_font():
    import matplotlib.font_manager as fm
    for name in ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'PingFang SC']:
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            return name
    return 'DejaVu Sans'  # fallback（无中文）
plt.rcParams['font.family'] = get_cn_font()
plt.rcParams['axes.unicode_minus'] = False
```

**布局：**
- 背景：白色 `#FFFFFF`，无外框（保留左/下轴线，隐藏上/右）
- 标题：**左对齐**（`loc='left'`），字号 14-16，颜色 `#2C2C2C`
- 数据来源注释：标题下方或图下方，字号 9-10，颜色 `#666666`
- 刻度线：隐藏（`tick_params(length=0)`）
- 网格线：仅水平方向，虚线 `--`，颜色 `#EEEEEE`，`set_axisbelow(True)`

**尺寸与分辨率：**
- 横向条形图：`figsize=(10, n*0.55 + 1.5)`（n = 数据行数，动态计算）
- 折线图：`figsize=(10, 5)`
- 饼/环形图：`figsize=(7, 7)`
- 输出分辨率：`dpi=300`（正式）/ `dpi=150`（快速预览）

**横向条形图专项（本文最常用）：**
- 条高：`height=0.6`，条间距适当（不拥挤）
- 数值标注：条右侧 `bar.get_width() * 0.01 + max_val * 0.005` 处，字号 10，与条同色
- Y 轴倒序（`ax.invert_yaxis()`）：最大值在最上方，视觉从大到小
- 单位：写入标题括号内，如 `次/5h`、`元/月`

---

### 脚本产物要求

- **脚本路径**：`{文章目录}/素材/charts/chart_{NN}.py`（NN = 图编号，从 01 开始）
- **图片路径**：`{文章目录}/素材/charts/chart_{NN}.png`
- **脚本第一行注释**：`# 图NN：图表标题 | 数据截至 YYYY-MM-DD`
- **数据内嵌**：所有数值硬编码在脚本内（不依赖外部文件），便于复核
- **每个 `<!-- chart: ... -->` 标记对应一个独立 .py 脚本**

---

### boilerplate 模板（横向条形图）

每次写图表脚本时，复制此模板修改数据部分即可：

```python
# 图01：XXX对比 | 数据截至 2026-04-20
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# ── 品牌色（默认中性主题，改色改 profile/brand.yaml）──
PRIMARY   = '#2F6F8F'   # 主题色
PRIMARY_L = '#B6D2DE'   # 浅主题色
DARK_TEXT = '#2C2C2C'
MID_GRAY  = '#666666'
GRID      = '#EEEEEE'

# ⚠️ 中文字体 glyph 兼容性警告（踩过的坑）
# ──────────────────────────────────────
# SimHei / Microsoft YaHei 不包含以下符号的 glyph，渲染会出现空方框 □：
#   ¥ / ￥ （人民币符号）  →  用 "元" 替代，如 f'{val} 元'
#   ℃ / ℉             →  用 "度"，如 f'{val} 度'
#   ㎡ / ㎥            →  用 "平米" / "立方米"
#   § ¶ † ‡           →  用 ASCII 或 "节/段" 等中文
# Noto Sans CJK / PingFang SC 支持更全，但 Windows 默认没装，不能依赖。
# 兜底策略：数值标注一律用纯 ASCII + 中文字，避免跨机器字体差异。

# ── 字体检测 ────────────────────────────
def get_cn_font():
    for n in ['SimHei','Microsoft YaHei','Noto Sans CJK SC','PingFang SC']:
        if any(n.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            return n
    return 'DejaVu Sans'

plt.rcParams['font.family'] = get_cn_font()
plt.rcParams['axes.unicode_minus'] = False

# ── 数据（按从大到小排序）────────────────
labels = ['品牌A', '品牌B', '品牌C']
values = [6000, 1500, 400]
unit   = '次/5h'

# ── 绘图 ────────────────────────────────
n = len(labels)
fig, ax = plt.subplots(figsize=(10, n * 0.55 + 1.5))

bars = ax.barh(labels, values, color=PRIMARY, height=0.6)

# 数值标注
max_v = max(values)
for bar, val in zip(bars, values):
    ax.text(bar.get_width() + max_v * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f'{val:,}', va='center', ha='left',
            fontsize=10, color=PRIMARY)

# 样式清洁
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(False)
ax.tick_params(length=0)
ax.xaxis.grid(True, linestyle='--', color=GRID, alpha=0.8)
ax.set_axisbelow(True)
ax.invert_yaxis()
ax.set_xlim(0, max_v * 1.18)  # 右侧留标注空间

ax.set_title(f'图表标题（{unit}）', loc='left',
             fontsize=15, color=DARK_TEXT, pad=10)
ax.annotate('数据来源：官方文档 / 截至 2026-04-20',
            xy=(0, -0.06), xycoords='axes fraction',
            fontsize=9, color=MID_GRAY)

plt.tight_layout()
plt.savefig('素材/charts/chart_01.png', dpi=300,
            bbox_inches='tight', facecolor='white')
plt.close()
print('✅ 已保存 chart_01.png')
```
