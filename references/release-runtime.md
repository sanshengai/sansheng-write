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

当前适配器只可调用 `baoyu-image-gen` CLI。
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
- 实际 renderer（必须为 `baoyu-image-gen`）
- 实际 provider、model、renderer revision、attempt
- prompt/output SHA-256

全部已配置 renderer 都失败时非零退出，不调用宿主内置生图工具绕过。

## 3. 后处理、BGM 与排版

1. 由确定性装配器按任务单位置嵌入信息图：

```bash
python "$SKILL/scripts/pipeline.py" assemble-release
```

2. 运行 `generate_article_bgm.py`，生成 MP3 并插入 AUDIO-CARD。
3. 用外部 Markdown→WeChat HTML 转换器生成原始 HTML。
4. 运行：

```bash
python "$SKILL/scripts/format_layout.py" 定稿.html --all --check
node "$SKILL/scripts/add_logo.js" "素材/*.png"
python "$SKILL/scripts/compress_images.py" 素材
```

🔴 **微信只收 jpg / png**，webp/avif/heic/bmp/tiff 一律 `40005`，且上传器会**吞掉**
这个失败、把本地 `src` 原样留在正文里（草稿一片坏图，而 `image_count` 数量对得上、
校验全绿——2026-07-28 连推三版才发现）。三道防线已内建，不必手动记：
`compress_images.py` 收图前自动转 PNG 并改写引用；`build_expected_draft` 推送前硬拦；
`_compare_readback` 回读后兜底。

数据图与精确拓扑图只允许根据已核实内容走独立本地确定性代码路径；两者都不得让生成模型编造数值，也不得冒充封面 / Hero / 信息图进入最终图证据集。

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
🔴 **别凭印象判断哪张渲多了** —— 第 89 篇那句「45 次渲染、6 张图、浪费 39 次」
是事后手工数出来的，这个命令就是来替掉那个活的。
四条成因按实测收益排序（frontmatter 泄漏 → SCENE 缺具体物象 → 文字共享 ≥2 字 →
自带文字的物件），第 2-4 条 `compile-visuals` 就会拦；渲到一半才发现，
先怀疑是不是手工改过 prompt 绕开了编译期。完整实验见
`_ops/生图首过率改造-实验与结论-20260816.md`。

授权源是结构门与 `_visual-qa.json` 的共同结果，不是 Markdown 勾选框。
QA request 会逐图携带目标 style、配方摘要、
必备视觉特征、禁用视觉特征与所需 checks；审阅必须检查预期文字、意外杂字、裁切安全、主次层级、
目标风格、品牌色板和同篇一致性，封面另验固定构图。模型审阅必须给出实际对象、数量、
位置和版式观察；只返回布尔勾选不得放行。`_visual-qa.md` 只是派生的人读摘要。
QA 资产集合从最终 HTML 与 Markdown 的实际引用共同计算；Hero 即使只由排版器写入 HTML，也必须送审。
`text_match`、`no_unexpected_text`、`style_contract_match` 是不可移除的发布硬门；
每条 `required_text` 必须在整图恰好出现一次。视觉编译后若 QA 代码字节变化，旧凭证立即失效。

仓内自带一个 Codex CLI 后端的适配器 `scripts/visual_qa_codex.py`，配置与三种静默失效
（提示词没送达 / 糊字被脑补成通顺句 / 转写被打碎误杀好图）见 `visual-qa.md`。

## 5. 唯一草稿箱事务

```bash
python "$SKILL/scripts/pipeline.py" release-check
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

固定顺序：登记永久链接 → 归档作品库 → 验证归档 → **生成 `_moments-copy.md`** → 自动播客 → 执行已配置官网同步。官网命令未配置时记录 skipped。🔴 **朋友圈文案前移到归档验证之后**：它只需要标题、摘要和永久链接，不依赖播客音频与官网；压在链尾会让作者等一个 10-30 分钟的音频才拿到文案，而首发那几小时最需要它。**播客或官网失败不得阻断、也不得回滚它。** 内容要求见 publish.md「朋友圈内容协议」。

- 播客配置 `auto_after_finalize: true` 时必须继续 `generate → publish --confirm` 到 receipt；同源 receipt 幂等跳过。**NotebookLM 登录失效时 `podcast_episode.py` 会自动拉起 `nlm login` 弹浏览器授权（2026-07-30 起），探测恢复后继续原流程**；只有自动登录失败才提示人工 `nlm login`（无人值守环境用 `SANSHENG_NLM_NO_AUTOLOGIN=1` 关回纯提示）。不得误说成“音频只能手动生成”。
- **播客音频同时上官网「听全文」（2026-07-30 拍板规则）**：`finalize` 必须先执行自动播客的 `generate → publish --confirm`，确认 `dist/podcast/audio.mp3` 与 RSS receipt 都存在之后，才能同步官网；不得先部署一个只有主题曲的版本。把该音频随文章目录一起 commit，官网构建时 `prepare-songs.py` 自动复制为 `public/song-assets/{code}/podcast.mp3`，文章页主题曲卡下出现「🎧 听全文 · 播客版」播放器（全站单例播放器，天然互斥暂停），文章列表标题旁出现「🎧 有音频」标记。部署走 `publish-to-website.sh {code}`（`-ArticleCodesCsv` 放行 song-assets）。设计口径：主题曲=配乐读、播客=代替读，两卡并存不做选择 UI；列表只放标记不放播放按钮。
- 朋友圈状态先放 commentary；final 只逐字输出 `_moments-copy.md`，首字符为 emoji，前后不得混入解释。

## 失败处理

- 非零退出：修复明确报错后重跑同一命令。
- 长命令尚未退出：每 60 秒以内报告一次存活进度，等待当前单写者返回；禁止另开终端、直调 renderer 或重复启动同一命令。
- 图片或 prompt 改动：重新 `visual-qa`、`seal visual`、`release-to-draft`。
- 草稿已创建但读回失败：不得删除 attempt，不得手工登记 media ID。
- 需要换 provider：只改 `renderer-policy.json`，不得改 canonical prompt 或图片比例。
