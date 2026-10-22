# 历史 schema1 视觉制作

仅历史文章或作者明确选择 schema1 时读取。新文章走 [stylebook-contract.md](stylebook-contract.md)。共用接管、音频、排版、草稿和收尾回到 [release-runtime.md](release-runtime.md)。

schema1（历史文章与显式选择）根据定稿写 `visual-plan.json`，只允许以下结构；schema2 使用上面链接的画风库合同：

- 封面：`2.35:1`，`montage-evidence`。
- Hero：`1:1`。
- 信息图至少 4 张：首张 `9:16`、末张 `9:16`、中间全部 `16:9`。例外：`article-meta.yaml` 声明 `infographic_mode: author-shots`（作者截图模式）时 `infographics` 必须为 `[]`，视觉切分由正文引用的 ≥4 张作者供图兑现（`素材/作者素材/` 或 `shot-` 前缀，文件必须存在）；`verify infographic` / `release-check` 改验这一条，`assemble-release` 不插图。
- 每张信息图必须含 `id`、`position`、`aspect_ratio`、`title`、`layout_type`、`layout`、`anchor`、`expected_text`、`facts`。`layout_type` 必须是已登记的 Baoyu 布局类型。
- `anchor` 是定稿作者正文中唯一命中的原文片段；装配器把该图插在锚句之后，找不到或命中多次即失败，禁止再按 H2 数量猜图位。
- 编译器会拦截明显的相邻双重复字；文字 QA 的“逐字一致”只证明渲染忠实，
  不等于任务单文案本身正确。
- 信息图与 Hero 一律 `claymation + warm-light-clay`，全站统一，不按题材分流。

```bash
python "$SKILL/scripts/pipeline.py" compile-visuals
```

编译器生成 canonical prompts 和 `素材/render-batch.json`。业务生产者固定为
`sansheng-write.visual-planner`，`producer_chain` 只允许这个真实执行者。Hero / 信息图必须
分别记录 `baoyu-article-illustrator` / `baoyu-infographic` 的 `method_sources` 与 SKILL 字节锚点；
封面只走本仓 `montage-evidence`。缺方法锚点、伪造 producer chain 或视觉合同不完整都不得发布。

## 2. 调用外部像素渲染器

> 本节「只可调用 `baoyu-image-gen`」等 renderer 规则适用于 **schema1**（历史文章与显式选择）。schema2 的出图路线见上文「画风库路径」与 [stylebook-contract.md](stylebook-contract.md)，不受本节 renderer 限制。

```bash
python "$SKILL/scripts/pipeline.py" render-visuals
```

需要比较同一张图的多种生成结果时，用候选闭环，而不是反复覆盖最终文件：

```bash
python "$SKILL/scripts/pipeline.py" render-visuals --candidates 3
python "$SKILL/scripts/pipeline.py" select-visuals \
  cover=2 hero=1 infographic-01=3 infographic-02=1 infographic-03=2 infographic-04=1
```

候选只保存在 `素材/candidates/`；未执行 `select-visuals` 时视觉 QA 会硬拦。系统绝不把最后一张随机生成图冒充为“最佳图”。
请求多候选但因 429 等原因只生成出一张时，选择命令必须失败，禁止把残留单图标成“已选择”。

schema1 的适配器只可调用 `baoyu-image-gen` CLI。
外部渲染器只负责像素，不决定版式、风格、文字或比例。图中全部内容文字必须由生成模型与
画面在同一次请求里原生生成，并共享对应的粘土材质、灯光与色板；不允许 SVG / HTML /
Canvas / CSS / 本地模板 / Pillow / Jimp / Sharp / ImageMagick 绘制或后期叠字，也不允许
模型另写 SVG 再转 PNG。错字只走同一 canonical prompt 的单张重渲，不拆分文字层。运行前会探测 batch
能力；仅在 `baoyu-image-gen` 内按 `renderer-policy.json` 的顺序降级，并保持同一 prompt、
比例和输出目标。未配置 policy 时直接使用 `baoyu-image-gen` 默认 provider。`sansheng-google`
等本仓原生 provider 会绕开 Baoyu，现已无条件拒绝；不存在“写理由放行”。

🔴 **模型 ID 不要带 `-preview`。** 模型转正后 preview ID 可能下线返回 404；
429 则通常是速率配额，应该退避重试并降低并发，不要混入另一条绕过 Baoyu 的原生链。
`sansheng-template-safe`、`sansheng-google-text-safe`、`sansheng-google` 均被运行时拒绝。

每张图必须记录：

- `producer=sansheng-write.visual-planner`
- 实际 renderer（schema1 必须为 `baoyu-image-gen`；schema2 记录 `backend` 与来源强度，见 stylebook-contract.md）
- 实际 provider、model、renderer revision、attempt
- prompt/output SHA-256

全部已配置 renderer 都失败时非零退出，不调用宿主内置生图工具绕过。


## 装配正文

```bash
python3 "$SKILL/scripts/pipeline.py" assemble-release
```

按唯一锚点确定性插入封面、Hero 与信息图；不手改正文插图。装配完成回主运行时处理音频和排版，再完成下面的旧路线后处理与独立验收。

## 旧路线后处理

只在 schema1 执行水印和压缩，完成后再进行下述独立视觉 QA。schema2 不使用这些命令。

```bash
node "$SKILL/scripts/add_logo.js" "素材/*.png"
python3 "$SKILL/scripts/compress_images.py" 素材
```

## 4. 独立视觉 QA 与封存

`SANSHENG_WRITE_VISUAL_QA_COMMAND` 必须指向一个独立看图进程，接受：

```text
<command> --request <_visual-qa-request.json> --output <candidate.json>
```

然后执行：

```bash
python "$SKILL/scripts/pipeline.py" visual-qa
python "$SKILL/scripts/pipeline.py" seal visual
```

**觉得重渲多了就跑 `pipeline.py render-stats`**（只读不改状态）：按图打印渲染次数、
QA 打回次数、产出过几张不同的图，并算出浪费量与排查顺序。
🔴 **别凭印象判断哪张渲多了** —— 曾经那句「45 次渲染、6 张图、浪费 39 次」
是事后手工数出来的，这个命令就是来替掉那个活的。
四条成因按实测收益排序（frontmatter 泄漏 → SCENE 缺具体物象 → 文字共享 ≥2 字 →
自带文字的物件），第 2-4 条 `compile-visuals` 就会拦；渲到一半才发现，
先怀疑是不是手工改过 prompt 绕开了编译期。完整实验见
`_ops/records/2026-08/生图首过率改造-实验与结论-20260816.md`。

授权源是结构门与 `_visual-qa.json` 的共同结果，不是 Markdown 勾选框。
QA request 会逐图携带目标 style、配方摘要、
必备视觉特征、禁用视觉特征与所需 checks；审阅必须检查预期文字、意外杂字、裁切安全、主次层级、
目标风格、品牌色板和同篇一致性，封面另验固定构图。模型审阅必须给出实际对象、数量、
位置和版式观察；只返回布尔勾选不得放行。`_visual-qa.md` 只是派生的人读摘要。
QA 资产集合从最终 HTML 与 Markdown 的实际引用共同计算；Hero 即使只由排版器写入 HTML，也必须送审。
`text_match`、`no_unexpected_text`、`style_contract_match` 是不可移除的发布硬门；
每条 `required_text` 必须在整图恰好出现一次。视觉编译后若 QA 代码字节变化，旧凭证立即失效。

仓内自带两个同合同的看图适配器：默认 `scripts/visual_qa_claude.py`（Claude 无头进程自己看图，不依赖 Codex 额度）与备用
`scripts/visual_qa_codex.py`；配置与三种静默失效（提示词没送达 / 糊字被脑补成通顺句 / 转写被打碎误杀好图）见 `visual-qa.md`。

