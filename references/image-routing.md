# 生图路由

本文件只定义业务视觉规则。像素厂商与模型属于 renderer 配置，不属于文章规则。

## 先判断是否应当生图

- 真人、新闻人物、重大事件：优先使用可授权的真实新闻照，禁止生成相似人物肖像。
- 厂商产品界面、Logo、硬件外观：优先官方素材或作者截图。
- 作者供图：保留原图，使用 `shot-` 前缀；默认不加 AI 图水印。
- 概念、结构、流程、抽象关系：进入视觉规划器。

## 两层合同

| 层 | 责任 | 唯一事实 |
|---|---|---|
| producer | 读定稿、选图位、定版式/风格/比例/文字、编译 prompt | `sansheng-write.visual-planner` |
| renderer | 按 canonical prompt 生成像素 | 当前适配 `baoyu-image-gen`，可按配置替换 |

renderer 不得修改 `expected_text`、比例、style 或 visual profile，不得在日志中冒充 producer。
封面和信息图的 producer chain 还必须分别包含 `baoyu-cover-image` 与 `baoyu-infographic`；
前者完成五维封面设计，后者完成命名布局×风格、内容结构化与 prompt 合成。
仅复制一段风格描述、随后调用 `baoyu-image-gen`，不算完整执行 Baoyu 工作流。
图中文字必须由本次生成模型与画面一起原生生成；禁止用本地模板、Pillow 或后期文字叠加来替代。
`layout` 是构图合同而非模板 ID：它约束层级和关系，但不把题材锁死在过去某篇文章的插画元素里。

`visual-planner` 是编排器，不是 Baoyu Skill 的替身。进入封面或信息图阶段时，Agent
必须实际调用已安装的 `baoyu-cover-image` / `baoyu-infographic`，读取对应 `SKILL.md`
与当前生效的 `EXTEND.md`，完成它们各自的内容分析、结构化、布局×风格选择和 prompt
合成；然后再由本流程把结果收口为 canonical prompt。Skill 不可用时必须停下修复接线，
禁止自己仿写 `analysis.md`、`structured-content.md` 或只在 receipt 里补一个 producer 名称。

本流程内置的是经人工筛选的品牌视觉合同，用来约束 Baoyu 输出的最终边界，而不是跳过
Baoyu 的理由：

- 封面：`montage-evidence` 的深炭品牌构图。
- 信息图与 Hero：`warm-light-clay` 粘土配方（全站唯一正文风格）。

这些配方集中在 profile 的 `visual.profiles`，编译后写入 prompt frontmatter 和摘要。上游
Baoyu Skill 可以独立更新；若它的建议与品牌合同冲突，以品牌合同收口，但仍须保留并实际
执行其内容分析、结构化和 prompt 设计步骤。只有人工审阅后的配方变更才同步进本合同，
避免插件升级静默改变成图。

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

配方的色值、材质、灯光、必备特征和禁用特征只从 profile 的 `visual.profiles` 读取，
编译时写入 prompt 摘要，避免文档与代码各存一份。

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
- 精确节点与拓扑：`baoyu-diagram`，转 PNG 后进入同一最终 QA。
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
