# 定稿后的唯一发布运行时

适用场景：作者已经确认 `定稿.md`，后续只做配图、BGM、排版、微信草稿和发布后收尾。此阶段不重写正文，不重跑写作前半程。

## 不可变边界

- 自动化终点是微信草稿箱：`scope=wechat-draft`、`formal_publish=false`。
- 正式发布、原创声明、赞赏设置由作者在微信后台完成。
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

`adopt-final` 只绑定作者确认的文件字节和元数据，不伪造事实复核或审稿记录。之后定稿、meta 或 state 变化都会令 `_release-job.json` 失效。

## 1. 生成受限视觉任务单

根据定稿写 `visual-plan.json`。只允许以下结构：

- 封面：`2.35:1`，`montage-evidence`。
- Hero：`1:1`。
- 信息图至少 4 张：首张 `9:16`、末张 `9:16`、中间全部 `16:9`。
- 每张信息图必须含 `id`、`position`、`aspect_ratio`、`title`、`layout`、`expected_text`、`facts`。
- AI 产品/模型主轴用 `claymation + warm-light-clay`；现象/商业/人文主轴用 `morandi-journal`。

```bash
python "$SKILL/scripts/pipeline.py" compile-visuals
```

编译器生成 canonical prompts 和 `素材/render-batch.json`。业务生产者固定为 `sansheng-write.visual-planner`。

## 2. 调用外部像素渲染器

```bash
python "$SKILL/scripts/pipeline.py" render-visuals
```

当前适配器调用 `baoyu-image-gen` CLI。它只负责像素，不决定版式、风格、文字或比例。运行前会探测 batch 能力；仅按 `renderer-policy.json` 的顺序降级，并保持同一 prompt、比例和输出目标。未配置 policy 时使用已安装渲染器的默认 provider。

每张图必须记录：

- `producer=sansheng-write.visual-planner`
- `renderer=baoyu-image-gen`
- 实际 provider、model、renderer revision、attempt
- prompt/output SHA-256

全部已配置 renderer 都失败时非零退出，不调用宿主内置生图工具绕过。

## 3. 后处理、BGM 与排版

1. 将信息图按任务单位置嵌入 `定稿.md`。
2. 运行 `generate_article_bgm.py`，生成 MP3 并插入 AUDIO-CARD。
3. 用外部 Markdown→WeChat HTML 转换器生成原始 HTML。
4. 运行：

```bash
python "$SKILL/scripts/format_layout.py" 定稿.html --all --check
node "$SKILL/scripts/add_logo.js" 素材
python "$SKILL/scripts/compress_images.py" 素材
```

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

授权源是 `_visual-qa.json`，不是 Markdown 勾选框。合同逐图检查预期文字、意外杂字、裁切安全、主次层级、风格一致性，并绑定最终后处理图片字节。`_visual-qa.md` 只是派生的人读摘要。

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
- 图片或 prompt 改动：重新 `visual-qa`、`seal visual`、`release-to-draft`。
- 草稿已创建但读回失败：不得删除 attempt，不得手工登记 media ID。
- 需要换 provider：只改 `renderer-policy.json`，不得改 canonical prompt 或图片比例。
