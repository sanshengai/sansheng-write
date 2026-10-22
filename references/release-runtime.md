# 定稿后的制作与草稿交付

作者已确认正文后进入本页。先运行 `pipeline.py --dir <文章目录> status`，结合当前文件和消费者校验确定从哪里续跑；不重写正文、不重新创作已确认的方案。下文命令在文章目录执行，`$SKILL` 指本 Skill 根。机器过程件由 `article_paths.process_file` 解析，新文章放 `过程记录/`，不手写完成状态。

## 本轮只走受影响的路径

| 本轮变化 | 执行范围 |
|---|---|
| 首次接管定稿 | 保存实际审批、`adopt-final`；确定视觉路线，主题曲交接与播客尽早启动 |
| 正文/配图含义变化 | 更新受影响计划、图片和阅读验收；音频按正文来源摘要判断是否失效 |
| 只换一张图或修字体 | 只制作和验收该候选；复用其他仍有效候选，重新选组装配与整篇阅读 |
| 只改外标题 | 走标题及来源核对；满足真实原正文与原参数复用条件才复用音频，不假称新生成 |
| 只调排版 | 重排与整篇阅读；源图不变不重新生图，已封存图片不就地后处理 |
| 同一候选已建草稿、读回失败 | 重跑 `release-to-draft`，凭有效 attempt 仅读回原 ID |
| 拿到正式链接 | 按 [publish.md](publish.md) 执行 `finalize`；不重新制作或自动分发社媒 |

## 1. 接管与并行

```bash
python3 "$SKILL/scripts/pipeline.py" approve draft --source-mode author-provided-final --words "<作者实际原话>"
python3 "$SKILL/scripts/pipeline.py" adopt-final --final 定稿.md --meta article-meta.yaml
```

只在首次接管或实际批准新正文时执行；已有有效审批持续有效。作者正文、审批 subject 与原话必须真实，不用“授权我交付”冒充作者看过最终成片。只有装配器和音频卡工具可写受控机器块。

接管后立即交付 [music.md](music.md) 的 MiniMax 主题曲生成单，作者生成音乐时继续配图。已有 MP3 先核来源并复用，不让作者重做。新文章 BGM 是硬门；Lyria 自动通道暂停。

schema2 接管后由主控按 `stylebook-contract.md` 预置标准音频卡；启用播客且参数齐备时，立即用宿主后台任务启动 `podcast-pregen`，保存任务 ID/日志，继续图片制作，不等待音乐 MP3。调度与写入边界见 [orchestration.md](orchestration.md)。图片装配不重做播客；正文、标题或生成参数变化按同源合同判断。播客必须在草稿前齐备，不能留到 finalize。正文、选图、排版和发布由一个控制者写入；独立模型负责规定的审核，不控制发布命令。

## 2. 只读取实际视觉路线

- **新文章 schema2**：按 [image-routing.md](image-routing.md) 选作者风格，再读 [stylebook-contract.md](stylebook-contract.md) 完成编译、出图、最终候选、独立审核、选组、装配、视觉封存与整篇阅读。正文图按内容规划为 0～多张；封面、正文、音乐和播客封面分别继承对应配置，不因换生图后端重选风格。`stylebook-service` CLI 直接生成并回收；只有 `host-imagegen` 返回 3 等宿主实际调用工具。
- **历史 schema1 或显式选择**：才读 [release-legacy.md](release-legacy.md)。其固定画风、张数、水印与后处理规则不能套到 schema2。
- **仅试验规划**：才读 [stylebook-preview.md](stylebook-preview.md)。已有正式 schema2 任务不再额外跑预览。
- **明确要求动态插图**：加读 [article-motion.md](article-motion.md)。先看动作能否解释内容及实际小样，再做交接；不能以移动选框冒充内容演绎。

独立审核绑定实际模型、文字、像素、来源和方法；失败先修实际问题，不修改凭证绕过。审核返回缺字段、格式错误或未完整结束时，先修审核调用并保留候选；不能把审核器故障当成图片设计失败而重新生图。具体视觉缺陷才修图，来源或计划变化按受影响输入处理。只读旧 done 标签不等于当前通过。数据图与精确拓扑用已核实内容的确定性路径，不让模型编造数值。

## 3. 音频、排版与阅读

1. 收到主题曲后创建并验证真实 `_music-manifest.json`，schema2 核对已预置的标准主题曲卡，历史 schema1 用 `audio_cards.py::upsert_card` 补入卡片；启用播客时保持“导读 → 主题曲卡 → 播客卡 → 正文”。两卡同级同宽，上下排列。
2. 用内置 `md_render.py` 生成微信 HTML，执行 `format_layout.py 定稿.html --all --check`。只读 [layout.md](layout.md) 当前所需步骤。
3. schema2 的品牌处理在候选验收前完成；装配后只安装品牌账本，不再覆盖、压缩已验收图片。静态正文使用 PNG/JPG，GIF 按动态合同上传。
4. 实际阅读完整文章及合同规定视口，确认字清楚、图意正确、无裁切。schema2 用 `accept-stylebook-reading` 保存真实观察，不用模型勾选替代看图。

封面或动图不满意属于候选问题，先修候选；不要一边更新制作方法一边验收同一个候选，避免方法摘要在长审核过程中改变。准备交草稿后冻结本次输入，发现变化先结束当前检查再重做受影响部分。

## 4. 一次命令交草稿

```bash
python3 "$SKILL/scripts/pipeline.py" release-to-draft
```

正常路径**不先跑 `release-check`、`verify publish --pre` 再跑上面命令**。它们保留为只诊断、不提交时的入口；`release-to-draft` 自己重绑定允许的机器装配、校验接管和全部发布前合同、封存发布包、创建草稿并官方读回。

- 只能 `scope=wechat-draft`、`formal_publish=false`；正式发布、原创与赞赏由作者操作。
- 默认只走公众号 API，浏览器操作须作者单独要求；API 不支持的原生组件交付文件和插入说明。
- 拿到 media_id 立即持久化。读回比对标题、摘要、作者、阅读原文、正文、图片、推广链接、封面和评论设置；全部一致才报草稿交付。
- 同一候选读回失败保留 attempt，重试不重建草稿；候选变了才开启新 attempt。官方读回不得缓存掉。
- 非零退出先修明确错误；禁止直调底层接口、手补状态或伪造通过。
- 运行 `handoff-assets` 补齐作者上传文件。已有音频封面复用，只生成缺失或明确要求修改的一张。交付路径用主仓镜像路径。
- 同一条交付消息附 [publish.md](publish.md) 规定的朋友圈文案；自动基线须改写，保留合适 emoji，不等正式链接再交。

## 5. 正式发表后的收尾

`finalize <永久链接>` 按 [publish.md](publish.md) 与 [release-runtime-appendix.md](release-runtime-appendix.md) 完成已授权收尾。正式文章双音频通过官方发布 API 验证；仅账号返回 48001 时按合同降级同一永久页，不声称验证了 API 看不到的音频字节。草稿已回收不是伪造凭证的理由。

把“微信已交草稿”“正式文章已发表”“官网正在排队”“官网已上线”分别报告。网站排队不影响已完成草稿的事实，也不重复制作文章；持久化 job ID 后按状态续查，退出码 0 或 queued 不等于上线。

## 排障按耗时定位

优先看本篇 observations 的 `pipeline.* / command_exit`，再看 `publish_preflight`、`draft_transaction` 与 `podcast_generation` 的子步骤（外部命令、轮询等待、下载重试等待）。父阶段包含子步骤，不能相加冒充总时间；人工等音乐、模型生成、本地检查、上传读回、网站排队分别统计。详细审计才读 [skill-review.md](skill-review.md)，不把复盘资料全部加载进日常发布。
