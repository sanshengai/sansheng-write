# 生图路由

本文件只定义业务视觉规则。像素厂商与模型属于 renderer 配置，不属于文章规则。

## 先判断是否应当生图

- 真人、新闻人物、重大事件：优先使用可授权的真实新闻照，禁止生成相似人物肖像。
- 厂商产品界面、Logo、硬件外观：优先官方素材或作者截图。
- 作者供图：保留原图，使用 `shot-` 前缀；默认不加 AI 图水印。
- 概念、结构、流程、抽象关系：进入视觉规划器。

## 三层合同

| 层 | 责任 | 唯一事实 |
|---|---|---|
| producer | 读定稿、选图位、定版式/风格/比例/文字、编译 prompt | `sansheng-write.visual-planner` |
| method source | 提供内容分析、结构化与布局方法；以版本字节和枚举锚定 | Hero=`baoyu-article-illustrator`；信息图=`baoyu-infographic` |
| renderer | 按 canonical prompt 生成像素 | 固定 `baoyu-image-gen`；只能在其内部选择 provider/model |

method source 与 renderer 都不得修改 `expected_text`、比例、style 或 visual profile，
也不得在日志中冒充 producer。

**Hero 与信息图**的 `method_sources` 必须分别包含 `baoyu-article-illustrator` 与
`baoyu-infographic`。前者的方法用于正文插图的 Type × Style × Palette 分析，后者的方法
用于命名布局 × 风格、内容结构化与 prompt 合成；真实 `producer_chain` 始终只能记录
`sansheng-write.visual-planner`，禁止用一串 Skill 名冒充执行证据。

🔴 **封面不接 `baoyu-cover-image`**（2026-08-02 拍板）：`montage-evidence` 是自建
签名视觉（英文 ghost 叠加），只反哺方法论、不走外部五维配方。声明一个明确不使用的
依赖，只会让 producer chain 退化成不可验证的空标签。

🔴 **method source 的名字是声明，不是证据。** 这几个 Baoyu 能力只有 `SKILL.md` 与
`references/`，没有可执行脚本，不存在可记录的"调用事件"——写一串名字进日志证明不了
任何事（历史上写入方与校验方就是同一处代码，那道门永远通过）。真正的证据是
`scripts/baoyu_contract.py` 产出的**字节锚点**：

- 本仓的信息图版式语言（`INFOGRAPHIC_LAYOUTS`）必须整体取自 `baoyu-infographic`
  的 Layout Gallery 枚举，枚举在编译期从磁盘 **实时解析**、不在本仓硬编码；
- 解析结果与标题声明的数量必须一致，否则判为解析规则与 Baoyu 文档脱节并拒绝放行；
- `baoyu_infographic_sha256` / `baoyu_article_illustrator_sha256` 写入
  `render-batch.json`，发布期重新解析比对，不一致即拒绝发布。

于是 Baoyu 能力缺失、被换版本、或本地版式语言偏离枚举，都会在编译期或发布期硬失败。
测试与离线环境可用 `SANSHENG_WRITE_BAOYU_SKILL_ROOT` 指向 fixture 根，生产环境不要设置。
图中文字必须由本次生成模型与画面一起原生生成；禁止用本地模板、Pillow 或后期文字叠加来替代。
`layout` 是构图合同而非模板 ID：它约束层级和关系，但不把题材锁死在过去某篇文章的插画元素里。

`visual-planner` 是唯一执行者，它必须按已安装 Baoyu method source 的当前文档完成分析、
结构化和布局选择，再收口为 canonical prompt。编译器会实时读取并锚定对应 SKILL 字节，
输出 `analysis.md` / `structured-content.md`，同时把 `method_sources` 与 SHA-256 写入凭证；
Skill 缺失、版本变化、枚举解析失败或凭证不一致时必须停下，禁止只补名称或手写假 receipt。

本流程内置的是经人工筛选的品牌视觉合同，用来约束 Baoyu 方法产物的最终边界：

- 封面：`montage-evidence` 的深炭品牌构图。
- 信息图与 Hero：`warm-light-clay` 粘土配方（全站唯一正文风格）。

`warm-light-clay` 的“黏土”同时约束物体和文字：白名单中文必须是立体挤出的圆润厚实
黏土字，并与场景使用同一哑光材质；不得退化为平面商务黑体、手写马克笔、毛笔/书法字，
标题与至少一半标签必须无底板、以自由立体字直接嵌入场景，不得让大多数文字都落进
底板、方框、条幅或卡片。编译器会拒绝冲突短语，独立视觉 QA 还会逐条核对
材质、字形、嵌入方式与排版层级；`required_visual_traits` 或
`forbidden_visual_traits` 为空时禁止发布。

`warm-light-clay` 不再放在可覆盖的私有 profile：它由本仓
`scripts/visual_contracts.py` 作为签名视觉固定，编译后把 owner、revision、摘要和色值写入
prompt frontmatter 与生成日志。Baoyu 仍负责内容分析、结构化与布局选择，但无权改色板、
材质、字形或明暗阈值；与签名合同冲突时由本合同收口。这样既保留 Baoyu 的结构能力，
又不会因插件更新或账号主题色变化而静默换画风。

## 固定视觉集合

- `素材/cover.png`：`2.35:1`。
- `素材/hero.png`：`1:1`，浅底，不承担第二张封面职责。
- `素材/infographic-01.png`：开篇 `9:16`。
- 中间信息图：至少 2 张，全部 `16:9`。
- 最后一张信息图：结尾 `9:16`。

信息图总数至少 4 张；同篇统一风格。

## 正文风格：全站统一粘土风，没有路由

信息图与 Hero 一律 `claymation` + `warm-light-clay`。不按题材分流，不需要判断，
`article-meta.yaml` 里这两个字段是固定值。

**为什么砍掉路由**：旧版让 `infographic_subject`（"具名 AI 产品是不是信息架构主轴"）
这个主观判断去决定视觉。三处校验都只查 subject 与 style 配不配套，从不查 subject
本身填得对不对 —— 填错之后整条链完全自洽：六层一致性门全绿、独立 QA 逐项通过、
字节封存成功。作者来回退了四五轮，没有任何一道闸门报过警。风险源就是这条路由本身。

`morandi-journal` 配方仍封存在 profile 的 `visual.profiles` 里，只是不再被路由到；
将来要切回去，改 `visual_workflow.py` 的 `INFOGRAPHIC_STYLE` 一处即可。

正文配方的色值、材质、灯光、必备特征和禁用特征只从
`scripts/visual_contracts.py` 读取；profile 只保留身份、排版主题与非签名视觉配置。

## 🔴 layout 不许写中文散文

`layout` 会**原样进入 prompt** 的 `COMPOSITION GUIDANCE` 段。那段带着「绝不可渲染为
可见文字」的禁令，但禁令压得住短标签，压不住整段中文 —— 模型看见中文就想画。

编译器强制中文 ≤ 24 字（`LAYOUT_CJK_MAX`）。构图细节请写英文，英文长描述实测无害。

同一篇文章、同一条流水线、同一份配方、同一个模型下的实测：

| layout 中文字数 | 结果 |
|---|---|
| 0（英文 538 字） | 一次成功 |
| 0 | 一次成功 |
| 108 | 连废 4 版：标签错位 / 多画「训练与比赛」/ 标题重复两次 / 乱码「50对选中，牵」 |
| 158 | 乱码「实近仆禽人粒」 |
| 181 | 多画白名单外的「污染」 |

「训练与比赛」的来源就是 layout 里那句「经由少年选拔、训练和比赛时间」。

稳定跑完 100+ 篇的历史文章，layout 中文都在 11–20 字这种短标签量级。这不是模型变差，
是 prompt 被灌进了模型会照着画的中文。

## 封面背景不再生成 ghost 文字

`cover_keywords` 只用于语义检索和视觉概念选择，不再被编译为可见英文水印。
封面背景只允许抽象线条与低对比图形；所有可见文字都必须进入明确白名单，
并由视觉质检逐项核对。

## 确定性图表

- 数字柱图、折线、饼图、雷达图：已核实数据 + 本地 `matplotlib`/等价确定性代码。
- 精确节点与拓扑：走独立本地确定性代码路径，不得冒充封面 / Hero / 信息图，也不得进入其最终图证据集。
- 生成模型只可做装饰性视觉，不得推断、补齐或改写数字。

## 生成式渲染的三类文字事故（都已在 prompt 层加约束，但仍要在 QA 复核）

1. **排布说明被当标题画出来**：`layout` 是中文的构图描述。它只能出现在
   `COMPOSITION GUIDANCE` 段、且带「绝不可渲染为可见文字」的禁令，**不进
   frontmatter** —— 渲染器把整份 prompt 文件连 frontmatter 一起发给模型，
   frontmatter 里的中文一样会被画出来。
2. **同一条文字重复两遍**：多个高度雷同的并列标签（几个只差数字的里程碑）最容易
   触发，模型会同时画成徽章和脚注。缓解办法是**让每条标签自带唯一前缀**
   （加日期、加主体），而不是只改 prompt。
3. **画出真实公司 / 产品 logo**：讲厂商对比时高发。prompt 已明令禁止，但仍要在
   视觉 QA 逐张看。

⚠️ 选渲染器前先读 [release-runtime.md](release-runtime.md) 的渲染器一节：
当前只允许生成式 renderer；错字或构图不合格时走独立 QA + 单张重渲，不降级成本地模板。

## 执行

```bash
python "$SKILL/scripts/pipeline.py" compile-visuals
python "$SKILL/scripts/pipeline.py" render-visuals
node "$SKILL/scripts/add_logo.js" "素材/*.png"
python "$SKILL/scripts/compress_images.py" 素材
python "$SKILL/scripts/pipeline.py" visual-qa
python "$SKILL/scripts/pipeline.py" seal visual
```

渲染器 fallback 只能来自 `renderer-policy.json`；每次尝试必须复用同一 canonical prompt 与比例。全部失败就停，不调用未登记的宿主生图能力。

🔴 **多数文章不需要 `renderer-policy.json`，删掉它才是正确配置。** 该文件不存在时自动走
`baoyu-image-gen`（Baoyu 视觉链默认渲染器）；它的语义是**覆盖默认**而非**确认默认**，
凭空建一份就是在改行为。实证（2026-08-02）：照模板复制一份（模板曾预置
`provider: sansheng-google`）就把渲染器静默换成 `gen_img.py`，封面从 1584×672 降到
1024×436，而所有发布门照常放行。现已收紧：`sansheng-google` 等本仓原生 provider
无条件拒绝，不接受理由放行；只允许 `baoyu-image-gen` 自身支持的 provider/model，
只想调尺寸时填 `quality` / `imageSize` 即可。

⚠️ **切回 Google 路径时的已知依赖**：`baoyu-image-gen` 的 `providers/google.ts` 需要
Vertex Express 端点补丁（`base.includes("/publishers/google")` 直接返回，不再拼
`/v1beta/`），否则 Banana 模型一律 404，且症状酷似"项目没开通模型权限"。该补丁已随
共享本体版本化，不再随插件缓存升级丢失。

## 证据

`.gen-log.jsonl` 必须逐图记录 producer、renderer、provider、model、renderer revision、attempt、prompt/output 摘要。日志只能证明“谁生成了什么”，不能代替视觉正确性。

最终授权只认：

- `_visual-qa.json`：独立视觉审阅结果。
- `_visual-receipt.json`：QA、prompt、日志和最终图片字节的封存。

QA 必须逐图确认 `style_contract_match` 与 `brand_palette_match`；封面另需
`composition_contract_match`。`style_consistent` 只表示同批一致，不能证明符合目标风格。
看图模型只作辅助语义审阅；没有实际对象、数量、位置和版式观察的布尔式“全通过”
一律拒绝。

Markdown QA 清单不具发布授权效力。
