# 定稿后的唯一发布运行时

适用场景：作者已经确认 `定稿.md`，后续只做配图、BGM、排版、微信草稿和发布后收尾。此阶段不重写正文，不重跑写作前半程。

## 不可变边界

- 自动化终点是微信草稿箱：`scope=wechat-draft`、`formal_publish=false`。
- 正式发布、原创声明、赞赏设置由作者在微信后台完成。
- 模型只产出 `visual-plan.json` 候选与独立视觉 QA；控制器单写者串行执行 pipeline、renderer、BGM、排版和微信事务。模型不得拥有长命令或发布命令。
- 微信草稿只允许通过 `pipeline.py release-to-draft` 创建。不得拆开预检、推送、登记 ID。
- 任一命令非零退出就停在当前步骤修复；禁止手工补状态、伪造凭证或调用低层发布脚本绕过。
- BGM 是发布硬门；新文章不可 `skip bgm`。

下文命令均在文章目录执行，`$SKILL` 指本 Skill 根目录。

## 0. 接管作者定稿

```bash
python "$SKILL/scripts/pipeline.py" adopt-final \
  --final 定稿.md --meta article-meta.yaml
python "$SKILL/scripts/pipeline.py" verify-release-job
```

`adopt-final` 同时绑定原始文件字节与作者正文摘要，不伪造事实复核或审稿记录。之后只允许 `assemble-release` 和 BGM 脚本写入有明确 marker 的机器装配块；作者正文、meta 或 state 漂移仍会令 `_release-job.json` 失效。

## 1. 生成受限视觉任务单

根据定稿写 `visual-plan.json`。只允许以下结构：

- 封面：`2.35:1`，`montage-evidence`。
- Hero：`1:1`。
- 信息图至少 4 张：首张 `9:16`、末张 `9:16`、中间全部 `16:9`。
- 每张信息图必须含 `id`、`position`、`aspect_ratio`、`title`、`layout`、`template_id`、`expected_text`、`facts`。
- `template_id` 只能选已审核模板：开篇 `curve-convergence`；中段
  `service-map` / `tiered-network`；收尾 `experience-loop`。模型不得自创版式。
- 编译器会拦截明显的相邻双重复字；文字 QA 的“逐字一致”只证明渲染忠实，
  不等于任务单文案本身正确。
- AI 产品/模型主轴用 `claymation + warm-light-clay`；现象/商业/人文主轴用 `morandi-journal`。

```bash
python "$SKILL/scripts/pipeline.py" compile-visuals
```

编译器生成 canonical prompts 和 `素材/render-batch.json`。业务生产者固定为 `sansheng-write.visual-planner`。

## 2. 调用外部像素渲染器

```bash
python "$SKILL/scripts/pipeline.py" render-visuals
```

当前适配器可调用 `baoyu-image-gen` CLI，也可使用本 Skill 的已审核模板渲染器。
外部渲染器只负责像素，不决定版式、风格、文字或比例。运行前会探测 batch
能力；仅按 `renderer-policy.json` 的顺序降级，并保持同一 prompt、比例和输出目标。
未配置 policy 时使用已安装渲染器的默认 provider。

**默认走 `provider: sansheng-google`**（模板 `templates/renderer-policy.template.json`
已按此预置）。该路径由本 Skill 自带的 `gen_img.py` 渲染，按 key 前缀自动分流
AI Studio / Vertex Express 端点，并记录实际 fallback 后的模型 ID。

🔴 **模型 ID 不要带 `-preview`。** 这些模型转正后 preview 的 ID 会下线返回 404，
而降级链会先撞一次 404 再发真请求 —— 等于每张图多打一发空枪，一批 6 张变 12 次
调用，突发速率翻倍后触发按分钟计的配额（429）。典型症状是「一批总有两三张失败，
重跑又换成另外几张失败」。`gen_img.py` 检测到这一支会打印 `[🔴 请改配置]`，
看到就去改 `renderer-policy.json`，别当噪音。

🔴 **429 不是「模型不可用」，换模型没有用。** 它按分钟配额触发，处置是退避重试
（`gen_img.py` 内建）+ 降并发（`render_visuals.py` 的 `_DEFAULT_JOBS`）。
把它和 404 混在同一条降级链里，会拿好模型去撞已经满的配额，还把真因掩盖成
「模型不行」。

⚠️ **`provider: sansheng-template-safe` 是例外路径，不是默认。** 它用
`render_text_safe_visual.py` 按 `template_id` 渲染，中文字形与坐标绝对稳定、
数字零幻觉；代价是**每套模板的插画元素是随某一篇文章的题材做出来的**（房子、
人群、社区节点这类），换个题材就会画出与内容完全无关的东西，而且改任务单没用。
只在「文字极密 + 数字绝不容错 + 题材恰好匹配某套模板」时手动切过去，
**切之前先渲一张看看再决定**。每张图同时生成同名 `.design.json`，绑定模板、
文字框、安全区、视觉元素与渲染前图片摘要。缺清单、越界或模板不兼容都会在视觉
QA 前硬失败。`sansheng-google-text-safe` 仅保留为兼容旧策略的路径。

⚠️ **`expected_text` 每张信息图恰好 4 条**（标题另算，走 `title` 字段）。
确定性模板会硬断言这一点；生成式路径虽不断言，但超过 4 条会显著提高重复与
增殖的概率。

每张图必须记录：

- `producer=sansheng-write.visual-planner`
- 实际 renderer（如 `baoyu-image-gen` 或 `deterministic-template-compositor`）
- 实际 provider、model、renderer revision、attempt
- prompt/output SHA-256

全部已配置 renderer 都失败时非零退出，不调用宿主内置生图工具绕过。

## 3. 后处理、BGM 与排版

1. 由确定性装配器按任务单位置嵌入信息图：

```bash
python "$SKILL/scripts/pipeline.py" assemble-release
python "$SKILL/scripts/pipeline.py" verify-release-job
```

2. 运行 `generate_article_bgm.py`，生成 MP3 并插入 AUDIO-CARD。
3. 用外部 Markdown→WeChat HTML 转换器生成原始 HTML。
4. 运行：

```bash
python "$SKILL/scripts/format_layout.py" 定稿.html --all --check
node "$SKILL/scripts/add_logo.js" "素材/*.png"
python "$SKILL/scripts/compress_images.py" 素材
```

🔴 **微信只收 jpg / png。** 截图工具常默认存 `.webp`（体积小），而
`media/uploadimg` 对 webp/avif/heic/bmp/tiff 一律返回 `40005 invalid file type`，
**且 baoyu-post-to-wechat 把上传异常 catch 掉只打一行 stderr、img 标签原样保留本地
`src`** —— 结果是草稿里一片坏图，而 `image_count` 数量对得上、全部校验显示通过
（2026-07-28 六张截图连推三版才发现）。两道防线都已内建，不必手动记：

- `compress_images.py` 收图前**自动**把不支持的格式转成 PNG，并改写 `定稿.md` /
  `定稿.html` 里的引用、删掉原文件；
- `build_expected_draft` 在推送前**硬拦**任何仍指向这些后缀的引用，
  `_compare_readback` 再在回读后兜一层（仍是本地路径的 img 一律判失败）。

数据图只允许根据已核实数字用本地确定性图表代码渲染；精确拓扑图可走 `baoyu-diagram`。两者都不得让生成模型编造数值。

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

授权源是结构门、设计清单与 `_visual-qa.json` 的共同结果，不是 Markdown 勾选框。
QA request 会逐图携带目标 style、配方摘要、
必备视觉特征、禁用视觉特征与所需 checks；审阅必须检查预期文字、意外杂字、裁切安全、主次层级、
目标风格、品牌色板和同篇一致性，封面另验固定构图。模型审阅必须给出实际对象、数量、
位置和版式观察；只返回布尔勾选不得放行。`_visual-qa.md` 只是派生的人读摘要。

仓内自带一个 Codex CLI 后端的适配器 `scripts/visual_qa_codex.py`，配置与三种静默失效
（提示词没送达 / 糊字被脑补成通顺句 / 转写被打碎误杀好图）见 `visual-qa.md`。

## 5. 唯一草稿箱事务

```bash
python "$SKILL/scripts/pipeline.py" release-to-draft
```

该命令不可拆分：

1. 验证 release job。
2. 执行全部发布前硬门并写 `_publish-ready.json`。
3. 创建微信草稿；拿到 `media_id` 后立即写 `_release-attempt.json`。
4. 调微信官方 `draft/get` 读回。
5. 比对标题、摘要、作者、阅读原文、评论设置、正文规范化摘要、图片数量、封面 media ID。
6. 全部一致才写 v2 `_publish-receipt.json` 并把 publish 标为 done。

读回失败时保留 attempt；同一 ready digest 重试只读回原草稿，不重复创建。产物发生变化后才会开启新 attempt。

## 6. 人工正式发布与自动收尾

作者在微信后台人工处理预览、原创、赞赏和正式发布。拿到永久链接后运行：

```bash
python "$SKILL/scripts/pipeline.py" finalize \
  "https://mp.weixin.qq.com/s/..."
```

固定顺序：登记永久链接 → 归档作品库 → 验证归档 → 执行已配置官网同步 → 生成 `_moments-copy.md`。官网命令未配置时记录 skipped；配置后执行失败会阻断朋友圈文案生成。

## 失败处理

- 非零退出：修复明确报错后重跑同一命令。
- 长命令尚未退出：等待当前单写者返回；禁止另开终端、直调 renderer 或重复启动同一命令。
- 图片或 prompt 改动：重新 `visual-qa`、`seal visual`、`release-to-draft`。
- 草稿已创建但读回失败：不得删除 attempt，不得手工登记 media ID。
- 需要换 provider：只改 `renderer-policy.json`，不得改 canonical prompt 或图片比例。
