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
弱模型只能在 `visual-plan.json` 选择已审核 `template_id`，不能自由设计最终布局：

- `opening` → `curve-convergence`
- `middle` → `service-map` 或 `tiered-network`
- `closing` → `experience-loop`

确定性模板渲染必须生成同名 `.design.json`；视觉 QA 先校验模板、图片摘要、
安全区和文字框，再要求看图模型提供像素级观察证据。

`visual-planner` 内置的是经过筛选的稳定视觉合同，不在运行时跨 Skill 临时读取规则：

- 封面：`montage-evidence` 的深炭品牌构图。
- AI 主轴：`warm-light-clay`。
- 现象主轴：宝玉 `morandi-journal` 的配色、doodle、washi tape、bullet-journal 与 Avoid 清单。

这些配方集中在 profile 的 `visual.profiles`，编译后写入 prompt frontmatter 和摘要。上游
baoyu Skill 可以独立更新；只有人工审阅后的配方变更才同步进本合同，避免插件升级静默改变成图。

## 固定视觉集合

- `素材/cover.png`：`2.35:1`。
- `素材/hero.png`：`1:1`，浅底，不承担第二张封面职责。
- `素材/infographic-01.png`：开篇 `9:16`。
- 中间信息图：至少 2 张，全部 `16:9`。
- 最后一张信息图：结尾 `9:16`。

信息图总数至少 4 张；同篇统一风格。

## 风格路由

- 具名 AI 产品、模型、工具或功能是信息架构主轴：`claymation`，必须绑定 `warm-light-clay`。
- 现象、商业、人文判断是主轴，产品只是案例：`morandi-journal`。
- 混合题材按信息架构主轴判定；产品/模型轴优先于趋势结论。

两种正文风格与封面配方的色值、材质、灯光、必备特征和禁用特征只从 profile 的
`visual.profiles` 读取，编译时写入 prompt 摘要，避免文档与代码各存一份。

## 确定性图表

- 数字柱图、折线、饼图、雷达图：已核实数据 + 本地 `matplotlib`/等价确定性代码。
- 精确节点与拓扑：`baoyu-diagram`，转 PNG 后进入同一最终 QA。
- 生成模型只可做装饰性视觉，不得推断、补齐或改写数字。

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

- 每张确定性模板图的 `.design.json` 结构证据。
- `_visual-qa.json`：独立视觉审阅结果。
- `_visual-receipt.json`：QA、prompt、日志和最终图片字节的封存。

QA 必须逐图确认 `style_contract_match` 与 `brand_palette_match`；封面另需
`composition_contract_match`。`style_consistent` 只表示同批一致，不能证明符合目标风格。
看图模型只作辅助语义审阅；没有实际对象、数量、位置和版式观察的布尔式“全通过”
一律拒绝。

Markdown QA 清单不具发布授权效力。
