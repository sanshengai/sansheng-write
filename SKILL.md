---
name: sansheng-write
description: Use when 用户要写、改、润色或排版中文长文和公众号文章，或明确要求把已发布文章转成小红书/微博图文、转成 X（Twitter）文章/发推特长文；触发对象为中文长文或公众号文章的创作、改稿、排版及按篇社媒分发（含 X 文章）；普通短回复、代码/规则文档修改不触发。社媒分发按篇显式触发，不因拿到正式链接自动执行。AI 课程使用 sandy-class，晨报使用 sandy-morning-cards，视频使用 sandy-video。
metadata:
  version: "3.0.0"          # 与 GitHub Release 共用同一 SemVer；由 release.py 自动同步
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, mcp__anysearch__search, mcp__doubao_search__web_search, mcp__tavily__tavily_search, mcp__datapro_search__dataPro_search, WebSearch, WebFetch, Agent, TodoWrite]
---

# 中文长文写作系统

给中文长文与公众号文章使用的写作、改稿和交付流程。运行要求 Python 3.10+；Markdown 排版、微信 API 已内置；生图默认调用同级 `sansheng-image`，保持作者配置的封面和正文风格。下文链接均指 `references/`。

## 先选本轮路径

| 用户本轮要什么 | 读取与终点 |
|---|---|
| 新文章、选题、大纲、正文 | [autopilot.md](references/autopilot.md)，按当前阶段读取写作资料；作者确认定稿后再进入制作 |
| 局部改文字、换图、调排版 | 只读取对应阶段；已有“交到草稿箱”授权时继续交付，否则止于指定修改 |
| 已有定稿，继续制作或交草稿 | [release-runtime.md](references/release-runtime.md)；先 `pipeline.py --dir <文章目录> status`，核对当前产物后从未完成处继续 |
| 已正式发表，提供永久链接 | `finalize <链接>`，依 [publish.md](references/publish.md) 完成已授权收尾；不自动触发新的社媒分发 |

“完整流程”指本篇已启用、已授权的内容全部完成，不等于把全部可选模块各跑一次。恢复时区分作者正文、图片、版式、音频和发布信息的变化；未改变的有效产物复用。`status` 的旧阶段标签不是当前文件已通过的证据，消费者验收才是准据。

## 必须保持的边界

- 作者拍板用 `approve blueprint|draft --words "<实际原话>"` 记录；`adopt-final` 接管定稿，不创造审批。已有授权持续有效，不重复询问；委托 Agent 完成交付不写成“作者已经看过当前新片”。
- 内容、来源、作者授权、最终文件和官方草稿读回必须真实。禁止手改状态或伪造通过记录。失败先修根因；相同输入、相同失败连续出现时先诊断，不机械重渲。
- 默认自动终点为微信草稿箱，唯一写入口 `release-to-draft`。公众号只走 API；浏览器操作需作者单独要求。API 不支持的原生组件交付文件和插入说明。正式发布、原创与赞赏由作者操作。
- 生图、排版或发布前读 [iron-rules.md](references/iron-rules.md)；实际制作路线从 [image-routing.md](references/image-routing.md) 进入。旧 schema1 仅用于历史文章或显式选择。
- 新文章主题曲按 [music.md](references/music.md) 交付 MiniMax 生成单，作者已给的音乐按真实来源复用。Lyria 自动通道暂停。启用公众号播客时，保持“导读 → 主题曲卡 → 播客卡 → 正文”，音频在交草稿前齐备。
- schema2 的已确认正文可先运行 `podcast-pregen`，与图片制作并行；按正文、标题、提示词及生成参数核对音频来源，图片装配变化不要求重新生成播客。同一篇的正文、选图、排版与发布写操作由一个控制者负责。
- 长任务报告实际阶段与剩余问题；工具返回“等待”不是失败，也不是完成。不要为了检查状态重复启动生成或发布。

## 按阶段读取

| 当前工作 | 参考 |
|---|---|
| 选题、大纲、文体选择 | [outline.md](references/outline.md) |
| 正文、开头候选、展开 | [writing.md](references/writing.md)；需要时再读 craft-techniques.md、writing-genres.md |
| 标题 | [title.md](references/title.md) |
| 口述、录音转文字 | [transcribe.md](references/transcribe.md)，先转写与口述梳理 |
| 磨稿、去 AI 味 | [polish-whitelist.md](references/polish-whitelist.md)、[anti-ai-filter.md](references/anti-ai-filter.md) |
| 事实复核、冷读 | [fact-check.md](references/fact-check.md)、[semantic-review.md](references/semantic-review.md)；独立上下文，实际执行方式如实记录 |
| 封面与静态配图 | [image-routing.md](references/image-routing.md)、[cover-styles.md](references/cover-styles.md)；schema2 的具体合同见 stylebook-contract.md |
| 明确要求动态插图 | [article-motion.md](references/article-motion.md)，先确定动作的解释价值与小样，再做正式交接 |
| 音乐、音频封面 | [music.md](references/music.md) |
| 排版、导读、文末卡片 | [layout.md](references/layout.md)；改颜色或圆角前读 design-tokens.md；平台问题读 wechat-compat.md |
| 制作、恢复、微信草稿 | [release-runtime.md](references/release-runtime.md)、[publish.md](references/publish.md) |
| 已发表文章搬进永久目录 | [physical-archive.md](references/physical-archive.md)，所有写者退出后执行 |
| 小红书、微博图文 | [xhs-storyboard.md](references/xhs-storyboard.md)、[distribute.md](references/distribute.md)，按篇显式触发 |
| X 文章、推特长文 | [x-article.md](references/x-article.md)，说明文字见 x-caption.md |
| 学习作者改稿 | [learn-edits.md](references/learn-edits.md) |
| 完整复核本 Skill | [skill-review.md](references/skill-review.md)，按真实记录区分执行问题与规则问题 |

## 共享上下文与预检

创作或改变品牌表达时，读取配置 profile 的 `context.md`；有 `brand-net.md` 时按 outline 的织网三问执行。局部校字、换单图或机械排版不重读整套创作资料。profile 由 `profile_config.py` 解析；未配置时使用 `profile.example/`，不复制个人资料。模板默认身份、色板和风格按 profile 与 style-routes.md，不从旧会话猜。

新文章用 `prep_writing.py` 聚合品牌与语料；创作或新配图方案只读近三篇相关摘要去重。金句库、作品库位置从 profile 解析，不能硬编码第二份。子任务需要并行合同才读 orchestration.md / agent-contracts.md；排障才读 visual-qa.md / layout-reference.md。

正文完成先运行 `pipeline.py preflight`，一次发现纯静态问题。不要等生图、音频都完成后才检查标题、章节、加粗、来源块和计划合法性。检查实现是唯一判据，入口不再复制完整检查清单。

## 交付与收尾

- 产物保存在当前文章目录，机器过程件放 `过程记录/`；`handoff-assets` 把需要手动上传的音频、封面放在文章第一层。
- 草稿交付必须有当前版本的官方读回凭证；同一候选创建成功、读回失败时重试读回，不重复建草稿。
- 报告草稿交付时附可复制朋友圈文案，按 publish.md 改写自动基线。用户只要朋友圈文案时直接写，不启动整篇流程。
- `archive` 只是作品库登记；实体搬运用 `physical-archive`，不手动改 articles.md、作品看板等派生视图。
- 正式发表后的完整任务以 `finalize` 和 `closeout-check` 为准；仅交草稿不冒称正式发表或官网已更新。

中文正文使用 `--` 代替全角破折号；`「」` 中的作者批注按上下文执行，不能直接混入正文。「入囊」仅沉淀选题。普通短回复、代码文档、晨报、视频制作不启动本流程。
