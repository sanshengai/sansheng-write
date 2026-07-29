# Changelog

本项目的变更记录。版本号遵循 [semver](https://semver.org/lang/zh-CN/)。

## [未发布]

### 修复

- `podcast_episode.py` 的 `--dir` 现在放在子命令前后都认。之前只能写在子命令**前面**，
  写在后面直接报 `unrecognized arguments` -- 而文件顶部的用法说明恰好写的是后面那种，
  照着文档敲必然失败。（子命令那份用 `SUPPRESS` 兜底：用普通默认值会让
  `--dir X generate` 里的 X 被子命令的默认值悄悄覆盖，参数被无声吃掉，
  然后在当前目录找不到定稿，报的错还指不到真原因。）
- `distribute plan` 打印的播客命令改用脚本绝对路径。那条命令是在**文章目录**里执行的，
  原先的 `scripts/podcast_episode.py` 相对路径在那儿并不存在，复制粘贴必然失败。
- 单集标题不再出现两道竖线。文章标题若自带分类前缀（「洞察 | 正文标题」），套上单集前缀
  后会变成「深聊 | 洞察 | 正文标题」，在播客 App 的列表里又长又难看。新增可选的
  `episode_title_strip_prefixes`：**只去掉你显式列出的分类词**，不做模式猜测 --
  试过「吃掉分隔符前若干字」的启发式，它当场把「这届年轻人 | 到底在焦虑什么」
  切成了「到底在焦虑什么」。不配置则完全不改标题。
- 重新生成时，已存在且内容不一致的 `shownotes.md` 会明确报警。它仍然不被覆盖
  （手写的 shownotes 比自动生成的值钱），但过期得让人看见 -- shownotes 是读者在播客
  App 里真正看到的那段文字，悄悄留着旧标题比覆盖更糟。

## [0.9.2] -- 2026-07-29

### 修复

- `distribute plan` 的「下一步」提示不再写死。之前无论启用了哪些渠道，它都让你去写
  社媒文案、再跑 `verify xhs` / `verify weibo`；如果你只开了播客，这行提示指向的是
  一件不存在的活儿，照着做会以为流程坏了。现在提示按实际启用的渠道推导，只开播客时
  直接给出生成音频的命令。

## [0.9.1] -- 2026-07-29

### 新增

- **各渠道引流策略分治**。三个平台对"把读者引去站外"的容忍度天差地别，同一套文案照搬会让
  账号出事，因此拆成三套口径写进 `references/distribute.md`：
  - **小红书 = 零引流**。不只是"正文别放链接"：平台 2026-06 起把**间接导流**一并纳入处罚
    ——「看主页」「私信我」、主页简介放联系方式、图片水印含联系方式、谐音变体、引导去站外
    搜账号，全部违规，且扣分累计不清零。新增机器闸门 `xhs_divert_hits()`，`verify` 命中即
    非零退出。回流改为靠账号同名沉淀，结尾用站内互动收口。
  - **微博 = 唯一能直给链接的渠道**，链接写进正文（不放评论区）；短链占约 25 字符且计入
    140 字，正文实际可用约 90-100 字。
  - **播客 = 口播 + shownotes 双落点**。音频里只说主阵地名字不念网址（听众记不住也难听），
    完整链接放 shownotes。

### 修复

- ⚠ **纠正一条会导致账号被罚的旧约定**：此前文档写小红书「原文入口靠主页简介或评论区」，
  在平台把间接导流纳入处罚后这两条本身即违规。已作废并改写。

## [0.9.0] -- 2026-07-29

新增一组**可选的**一稿多投模块（小红书 / 微博 / 播客），把已发布的文章派生到其他平台。
默认全部关闭，不启用时不会出现在任何命令的输出里 -- 只想写文章的话，这一版对你没有任何变化。

### 新增

- **分发层：一稿多投**。`scripts/distribute.py` 与 `references/distribute.md`，把正式发布之后
  的多渠道派生做成第二段链路：`plan`（产约束与待填槽）→ `verify`（机器闸门）→ `dispatch`
  （默认 dry-run）。沿用本 Skill 一贯的分工 -- **脚本做闸门，agent 做内容**。
  - 渠道口径差异由机器拦，不靠人记：小红书 `#标签` 与微博 `#话题#` 写反、微博正文超长
    （会被平台折叠）、小红书标题超限，`verify` 一律非零退出。
  - 小红书标题按**平台自己的字数算法**校验（中文 / emoji / 中文标点算 1 字，英文数字算
    0.5 字，空格不计）。用字符串长度会把合规标题误判超长 -- 40 个英文字符按平台算法只有 20 字。
  - **上游漂移即失效**：定稿一变，对应渠道的文案标记过期，`verify` 与 `dispatch` 双双阻断。
    只在 `verify` 查是不够的：单独重做某一个渠道后，其余渠道仍停在已校验状态，
    光看状态就会把对应旧定稿的文案发出去。
  - 派发**永远不替你点最后那下发布**：脚本把内容填进平台的发布框就停手。填错还能改，
    发出去收不回来。
- **播客单集流水线**（`scripts/podcast_episode.py`）：把定稿做成双主持音频，推到你自己的
  feed 主机。生成与上线分两步，生成耗时较长可丢后台。
  - 音频在**本机**生成而非服务器：这类服务的登录态只有真实浏览器能维持，无头服务器上的
    静态凭证快照会被很快判废。
- **交互式配置引导**（`scripts/setup.py`）：问清你要哪些可选模块，**只收集那些模块需要的**
  配置。已配好的不重复问，第二次运行是「改配置」而不是从头再来；非交互环境（CI、管道）
  只打印清单不阻塞。装有 `ruamel.yaml` 时就地改写并**保留你 profile 里的注释**，没装则
  不写盘、改为打印片段 -- 不会默默抹掉你的注释。

### 改进

- **可选模块默认关闭、未启用即静默**：未启用的模块不报错、不提示、不在体检报告里出现，
  也不在发布收尾时附带它的操作指引。判据是：只用主线功能的用户跑完全流程，不应该知道
  这些模块存在。README 新增「可选功能」章，每个模块写清「能做什么 / 需要你提供什么 /
  **不启用会怎样** / 怎么启用」。
- `setup_check` 的检查面收敛为「已启用模块 + 主线依赖」，不再体检你用不到的东西。
- 正式发布收尾（`finalize`）在启用了分发模块时，会顺带生成一份分发计划并打印下一步；
  未启用则完全不提。计划生成是纯本地的快操作，浏览器填充与音频生成都不塞进这一步 --
  否则一条几秒的收尾命令会变成漫长的阻塞等待。

### 修复

- 读取正式发布链接的位置修正：真源是流程状态文件，而非草稿箱凭证 -- 后者在正式发布前
  始终标记为未发布，据此判断会让每篇文章都显示「未发布」。

## [0.8.4] -- 2026-07-24

### 修复

- **朋友圈段落格式固定**：段落之间保留一个空行，清除零宽字符与 BOM，禁止句内换行、标题包装和任何前导空白；生成结果可直接整段粘贴。

## [0.8.3] -- 2026-07-24

### 修复

- **朋友圈文案可整段直接粘贴**：输出文件从第一个正文 emoji 开始，
  不再附带 Markdown 标题、前置空行或行首空白，复制到朋友圈不会产生首行缩进。

## [0.8.2] -- 2026-07-24

### 修复

- **文字安全不再等于通用卡片**：用 4 个按图位审核的
  `morandi-journal` 模板替换忽略任务布局的统一卡片渲染；弱模型只能选择
  `template_id`，不能自由生成或降级版式。
- **封面恢复明确主副层级**：主标题、副标题与 descriptor 采用三级字阶，
  禁止两行等字号堆在画面中央。
- **确定性图也必须证明设计正确**：新增 `.design.json`，绑定模板、图片摘要、
  安全区、文字框和视觉元素；缺失或不一致在发布前非零退出。
- **视觉 QA 拒绝橡皮图章**：看图结果必须写出实际对象、数量、位置与观察到的
  版式，只有布尔勾选不能签发视觉合格。
- **任务单先拦明显重复字**：图内文字出现相邻双重复字簇时在编译前失败，
  避免“与错误任务单逐字一致”被误判为文字正确。

## [0.8.1] -- 2026-07-24

### 修复

- **视觉合同不再丢失**：恢复深色 `montage-evidence` 品牌封面，并把完整的
  `morandi-journal` 配色、手绘元素与禁用项编译进 canonical prompt，避免只传风格名导致照片拼贴或旧纸水彩偏移。
- **视觉 QA 验目标而非只验一致**：每张图携带可复验的目标风格与品牌色板合同；
  封面额外检查固定构图，错误但内部一致的一批图不能再进入发布链。
- **断点续跑绑定 Prompt**：运行器会同时核对图片和 canonical prompt 摘要；
  规则更新后不会误复用旧图。
- **中文不再交给生图模型猜**：canonical prompt 使用可见文字白名单且不再把原始事实句喂给渲染器；
  文字密集图可切到 `deterministic-compositor`，由本地字体精确写入中文，杜绝漏字、改字和把英文风格指令画进图。
- **Vertex 快速路由可直接使用**：`renderer-policy.json` 可选 `sansheng-google`，
  由 Skill 自带客户端识别 AI Studio / Vertex key、执行模型 ID fallback，并按任务并发出图，不再被外部插件的 Base URL 拼接方式卡住。
- **合法 Logo 纳入 OCR 白名单**：视觉 QA 会把 profile 中的账号名视为后处理合法文字，并按封面与正文各自的目标风格检查一致性。

## [0.8.0] -- 2026-07-23

### 新增

- **定稿到微信草稿箱的确定性机械链**：新增 `release-job.json`、内部视觉编译器、批量渲染适配器、独立视觉 QA、发布事务与官方 `draft/get` 读回校验；发布成功以 v2 `_publish-receipt.json` 为唯一凭据。
- **可恢复的草稿事务**：拿到 `media_id` 后立即写入 `_release-attempt.json`；重跑会优先读回既有草稿，避免弱模型或中断场景重复创建。
- **弱模型压力评估**：新增 7 类故障场景数据集，覆盖预检失败、渲染失败、QA 不通过、草稿读回不一致与恢复执行。

### 改进

- **视觉语义规则内聚**：封面、Hero、正文信息图的数量、比例、视觉路线与 canonical prompt 由本 Skill 自己编译；外部图像能力只负责像素渲染，不再要求宿主 Agent 在多个语义 Skill 间切换。
- **发布文档减重**：以 `references/release-runtime.md` 作为定稿后机械链单一真源，合并并大幅压缩重复的自动化、编排、生图、排版、发布和铁律文档。
- **正式发布边界明确**：自动链只到微信公众号草稿箱；正式群发、原创与赞赏保持人工操作。获得永久链接后，`finalize` 才执行归档、网站同步与朋友圈文案生成。

### 修复

- **禁止绕过契约门**：草稿创建与发布预检置于同一事务，任何图片证据、独立 QA、BGM、元数据或读回结果不合格都会非零退出，手工补写“已发布”状态不能放行。
- **视觉证据绑定最终字节**：QA 请求、结构化结果与 seal receipt 均绑定最终图片哈希；人工编辑 Markdown 清单不再具备授权能力。
- **降级策略可审计**：只有 `renderer-policy.json` 声明的 provider/model 顺序允许降级，且 prompt、比例和输出目标保持不变；所有尝试写入生成日志。

## [0.7.2] -- 2026-07-23

### 修复

- `prep_writing.py` 现在会跳过 RRF 等合法但不符合 `{"findings": ...}` 契约的检索 JSON，不再因顶层为列表而中断写作前事实清单聚合；新增回归测试覆盖混合研究目录。

## [0.7.1] -- 2026-07-23

### 修复

- **浅色黏土不再随宿主 Agent / 渲染器漂移**：新增 `warm-light-clay` 视觉配方，将暖米黄背景、当前主题主色、浅色阈值、哑光材质与柔光约束绑定到 canonical prompt、生成日志和最终像素；钢蓝/砖红/金属黑底等深色方案在登记证据前即被阻断。
- **Hero 不再成为暗色例外**：`claymation` 文章的 Hero 与四张信息图共用配方、prompt、日志和色调门，避免正文浅色而导读图突然切成暗黑科技风。
- **视觉 QA 不再只看“已勾选”**：浅色配方要求显式核验背景、主色、禁用色、材质、写实感与 Hero 一致性，总勾选项不少于 12 条。

### 新增

- `pipeline.py visual-contract` 打印当前 profile 对应的配方名、内容摘要、背景色与主题主色，供信息图和 Hero prompt 原样复用。
- 生图日志新增 `visual_profile(_sha256)`、`host_agent`、`orchestrator_skill` 与可选 `extend_sha256`，视觉 receipt 同步封存，便于区分模型、宿主与 EXTEND 配置差异。

### 改进

- **固定视觉合同而非武断固定渲染器**：同 Prompt A/B 中 Gemini 与 GPT Image 都通过浅色门；保留后端可替换性，只有同规格重复越线才考虑 pin renderer。

## [0.7.0] -- 2026-07-22

### 改进

- **公开版本统一**：`SKILL.md metadata.version` 不再维护独立“范式版本”，与插件清单、CHANGELOG、git tag 和 GitHub Release 共用同一 SemVer。
- **正式发布一键闭环**：新增 `pipeline.py finalize <wechat_url>`，串起永久链接登记、作品库归档、`articles.md` / `works-dashboard.html` / 推荐卡刷新与闭环验证；微信公众号完成态与可选的网站/朋友圈外部收尾分开表述。
- **发布元数据前置校验**：标签、分类、摘要、最终标题前缀与微信永久链接在写盘前统一校验；正式标题以 `article-meta.yaml` 为单一真源，发布、作品库、网站/RSS 不再二次拼接。
- **归档可观测性**：观察日志新增 `archive/registry_write` 与 `archive/verify_closed_loop` 事件，自省复核可识别元数据、写入和派生视图故障。

### 修复

- **归档失败不再残留脏数据**：候选作品库先在内存中完成全量校验，再统一写盘；重复归档保留原发布日期、合并关系、视频与系列等已有字段。
- **闭环验证不再假绿**：`verify archive` 除了检查 seq/code，还会核对当前元数据、正式链接、作品库全量契约、派生视图与金句文章标记。
- **路径与私有配置解耦**：作品库与金句库统一走 resolver，命令打印实际绝对路径；个人网站同步命令移入 profile，不再硬编码在公开 skill。
- **推荐脚本消除帮助副作用**：`generate_recommend_html.py --help` 只显示帮助，不再把 `--help` 当输出路径写文件；归档流程直接调用纯函数生成推荐卡，不依赖剪贴板。

## [0.6.0] -- 2026-07-22

### 新增

- **视觉与发布 receipt**：`pipeline.py seal visual` 将 logo/压缩后的最终封面、信息图、canonical prompt 和 QA 记录绑定为 SHA-256 清单；`done publish draft_media_id=...` 再把 HTML、hero 与视觉清单绑定到微信草稿 media_id。
- **审批对象摘要**：`pipeline.py approve blueprint|draft --source-mode ...` 将作者确认绑定到具体大纲/meta 或语义定稿/双外审/QC，改稿后旧批准自动失效。
- **生图证据 v2**：最终视觉日志分开记录 baoyu producer 与像素 renderer，并保存 model、prompt/output 摘要与 record id。
- **观察日志 v2**：新增 run/record id、attempt、passed、severity、issue_codes、metrics 与 artifact digest；复核同时看原始重试成本和每篇最终结果。

### 改进

- **发布两阶段门**：`verify publish --pre` 在调微信前写 publish-ready，`done publish` 在拿到 media_id 后复验并写最终 receipt；`--force` 也不能绕过。
- **状态自动失效**：state v2 保留首次完成时间，重复验证只更新最后验证时间和尝试次数；上游摘要变化时自动把已完成下游标为 `dirty`。
- **内容配置 SSOT**：`.state.json` 不再复制 style/lead 参数，内容配置统一以 `article-meta.yaml` 为准。
- **baoyu 路由统一**：文档明确 `baoyu-cover-image` / `baoyu-infographic` 负责分析、版式与风格，`imagegen` / `gen_img` 只负责渲染；最终 prompt 统一放 `素材/prompts/final/`。

### 修复

- **门禁失败可被脚本识别**：`verify` / `done` 的正常失败统一返回非零退出码，上游失败会立即污染已完成下游；status 同时检测 canonical prompt、最终视觉 QA 与 receipt 漂移。
- **发布状态原子化**：仅凭 `wechat_url` 不再绕过新流程 receipt；失败的发布尝试不会覆盖可信 `draft_media_id`、`wechat_url` 或 receipt，合法草稿态也不再误报缺正式链接。
- **审批结论防伪**：checkpoint receipt 同时绑定审批锚点文件、SHA-256 与 `approved/waived` 结论；锚点写成拒绝或后来被改动都会失效。

### 迁移

- ⚠ 破坏性：新文章的最终封面/信息图日志需补 `--prompt --renderer --model`，并在发布前执行 `pipeline.py seal visual`；启用检查点的 profile 需在作者确认后执行 `pipeline.py approve`。历史文章可继续用 `--legacy` 做只读迁移。

## [0.5.0] -- 2026-07-22

这一版把视觉路由从“写在文档里的建议”升级为可追溯、可阻断的发布契约，防止混合题材选错画风后一路发布。

### 新增

- **视觉路由 SSOT 与六层一致性门**：新文章须显式填写 `infographic_subject`（`ai-product` / `phenomenon`）和 `infographic_style`；模型/产品承担信息架构主轴时固定使用暖米黄 `claymation`。流水线会核对 meta、分析稿、结构稿、prompt、最新生成日志与最终图组。
- **发布前视觉 QA 凭证**：封面和信息图生成后必须逐张看图，将标题占比、裁切、杂字、统一画风和文字核对记录到 `_visual-qa.md`；缺失时发布前门禁阻断。
- **批量生图串行执行**：`gen_img.py` 现在真正支持帮助文档承诺的多组输入，并按输入顺序串行请求，避免并发请求触发上游限流。

### 改进

- **混合题材优先级明确**：具名 AI 模型、工具、产品或功能承担卡片/对比轴时，产品/模型轴优先于外层的趋势结论；仅在产品只是论据时使用 `morandi-journal`。
- **蓝图闸结构校验**：启用 blueprint checkpoint 时，锚点必须包含标题、开头、大纲、封面风格与信息图主题/风格，不再只检查文件是否存在。
- **封面字级收紧**：`montage-evidence` 的中文标题块改为画布高度 18--22%，并禁止在 prompt 中使用会诱发海报大字的 `largest` / `extra-black`。
- **自省日志路径对齐**：文档改为读取 profile flywheel 的观察日志 SSOT，不再误读仓根的陈旧同名文件。

### 修复

- 修正对外分类新增 `share` 后测试仍断言六分类的陈旧用例。

### 迁移

- ⚠ 破坏性：新文章需在 `article-meta.yaml` 增加 `infographic_subject`，并在发布前生成 `_visual-qa.md`。历史文章如只做归档兼容，可继续使用流水线的 `--legacy` 模式。

## [0.4.1] -- 2026-07-17

### 修复

- **生图白名单与文档脱节**：`scripts/pipeline.py` 的 `IMAGE_TOOL_WHITELIST` 仍停在 baoyu-* 时代，
  而 `image-routing.md` 路由表与 `pipeline.py status` 提示早已把封面/信息图的实际执行入口迁到
  `gen_img.py`；按本 skill 自己的文档正确执行反被判「不在白名单」，现补入 `gen_img`（旧 baoyu-*
  名保留作历史文章向后兼容）。

### 新增

- **厂商官方产品截图通道**：`image-routing.md` 新增「第零分支之二」完整 SOP——评测/对比类文章展示
  软件真实界面时，AI 生图画不出真实 UI（一眼假、且等于伪造产品外观），改走抓官方素材（GitHub
  仓库 raw > 官方页 img/og:image > 无头截图），`vendor-` 前缀落盘协议（`add_logo.js` 同 `news-`
  一样跳过水印，非本号产物不冒认版权）。

## [0.4.0] -- 2026-07-13

### 新增

- **磨稿「四层自检地图」+ draft 闸《质检报告》**：`writing.md §四磨` 开头新增一张四层金字塔速查表
  （L1 硬规则 / L2 风格一致 / L3 内容质量 / L4 活人感），把原本散在多个文件的自检机制归并成一张
  心智图（借鉴软件测试金字塔框架，纯指针、不新增检查）；`draft` 定稿闸交付时附一张四层《质检报告》
  `_draft-qc.md`，把 `_stutter-list.md` / `_fact-check.md` / 机器门结果汇总成一屏，作者不必翻多个文件
  即知稿件过了哪些关、还剩什么待定。
- **正文叙事插图方法论**：`image-routing.md` 新增「正文叙事插图」节——原创隐喻三步法（抽象概念 →
  物理动作 → 低科技实物，让主体去执行该动作）、单图单概念 + 每篇不复用旧构图、叙事插图 QA 门
  （失败信号 + 交付判断双层）；并明确叙事插图画风**并入本篇 `infographic_style`**（与信息图同一视觉
  系统，不另立第三套画风）。
- **全生图「图内文字护栏」**：任何 AI 生图图内文字出错，一律改 prompt 重新生成，**禁止** PS / 工具在
  成图上覆盖修字、**禁止** SVG/HTML 假冒栅格图（`image-routing.md`）。
- **`profile.example/corpus/` 补开箱占位语料**：新增原创、版权干净的 `反例对照库.md`（6 组 AI 腔 → 人话
  对照 + tag 召回方法）与可选 `vocab-pool.md`，让 `anti-ai-filter.md §七` 的「反例对照库召回」步骤在默认
  profile 下也能跑通、有样例可循（此前引用的语料文件不在示例 profile 里）。

## [0.3.0] -- 2026-07-11

### 新增

- **裸 URL 发布硬门（`verify_no_bare_url`）**：正文里的完整 URL（≥18 字符、带 `/路径`）
  必须装进 `link-card.html`（单条）/ `deep-read-section.html`（文末·多条）的
  `word-break:break-all` 浅框；裸放在正文段落 / 划重点 / **文末手敲网址段** → `pipeline.py
  verify layout` 阶段 **硬 fail**。根因：微信对含长 URL 的行做两端对齐，把中文撑成大字间距
  （分散对齐），且被拉散的 URL 读者长按选不中、无法复制。规则原只在 `layout-reference.md`
  被绕过（手敲文末引流段），故升格为硬门（`scripts/contracts.py` + `tests/test_no_bare_url.py` 12 例）。
- **「阅读原文」默认值走 profile（`publish.source_url_*`）**：`profile/brand.yaml` 新增
  `publish.source_url_default`（默认官网）/ `source_url_treasure`（自研 skill / 工具类文的宝藏页）；
  发布时按「article-meta `source_url` → 文章类型 → 默认」解析出 URL，显式带 `baoyu-post-to-wechat
  --source-url`（映射微信 `content_source_url`）。`publish.md` 记明流程；`profile.example` 带中性占位。
  ⚠️ 微信 `draft/add` API 无任何赞赏字段，「赞赏」只能后台手动开，无法在此固化（`publish.md` 已注明）。

### 修复

- **划重点要点行分散对齐**：`process_takeaway()` 生成的要点内容单元格补
  `text-align:left; word-break:break-all;`，防要点里混入 URL / 长英文时被微信两端对齐撑成
  大字间距（截图实证）；`key-takeaway.html` 模板同步 + 注明「完整 URL 应走 link-card」。
- **文末 / 正文 URL 排版规范固化**：`layout-reference.md` 补硬规则--正文任何完整 URL 一律走
  模板、入口名作品牌绿小标题、URL 左对齐浅框长按复制（「单击复制」在微信正文做不到，已注明
  平台约束 + 可用「阅读原文」承载可点击主入口）；`layout.md` 步骤4 自动检查项 + 巡航清单各加一项。
- **导读栏 logo 自动补齐路径崩溃**：`format_layout.py process_lead` 里 `cwd`/`profile_dir()`
  为 `str` 时 `cwd / "素材"` 抛 `TypeError`，导致 `--all` 排版在导读栏阶段整体失败；
  改为 `Path(cwd)` / `Path(profile_dir())` 兜底（实战复现并修复）

## [0.2.0] -- 2026-07-11

### 新增

- **人工检查点闸门（`workflow.checkpoints`）**：profile 的 `brand.yaml` 可配
  `workflow: { checkpoints: [blueprint, draft] }` --
  **blueprint 蓝图闸**（大纲 + **5 套「外标题 + 封面文案」配套视觉方案**（每套 = 标题候选 + 配套封面 L1/L2 文案，
  成套呈现成套选定、不拆分交付）+ 开头候选一包交付，硬停等作者拍板，开头盲选并入此闸）；
  **draft 定稿闸**（磨稿 + 双外审修复后硬停等审读，过闸后配图→BGM→排版→草稿箱照旧零停顿）。
  `pipeline.py verify outline/writing` 硬查 `_blueprint-approval.md` / `_draft-approval.md` 锚点，
  闸上不在场 = 等（不自动续跑）；作者明说「免检」单次跳闸。**未配置 = 原全自动行为不变**。

### 修复

- **推荐阅读卡 cover 路径三兼容解析**（`<数据目录>/` 占位符 / 相对数据目录 / 旧库父目录基准）--
  修复历史作品库条目被判「无封面」导致文末推荐位 + 关注卡整体静默跳过
- **导读栏 logo 自动补齐**：`素材/logo-white.png` 缺失时排版自动从 `profile/brand/logo.png` 拷贝
  （lead 模板硬引用该文件，此前每篇导读栏 logo 均裂图）
- **`***粗斜体***` 降级为禁用**：md 转换器会把 CJK 粗斜体吃成空 `<em>`、标记文字整个消失（实战实证），
  重点标绿一律用 `<mark>` 标签（writing.md / layout.md 已同步）

## [0.1.2] -- 2026-07-11

发布后的第一轮全面复核（5 维度审计 + 逐条对抗校验，39 项发现全部修复/处置）。

### 新增

- **三套新预置主题**：`jade`（青玉绿）/ `amber`（琥珀赭）/ `plum`（梅子紫），预置主题增至六套
- **OpenAI 兼容生图兜底实装**：`gen_img.py --provider openai -m <模型>`（此前文档承诺但未实现）；
  新增 `--dry-run` 打印请求摘要；`setup_check` 对兜底做真实探测，不再发假绿灯
- **快速上手一页化** + 依赖矩阵点名 baoyu-skills（安装命令、双 `.env` 体系、微信凭证正确位置）
- **缺微信凭证的落盘降级路径**写入 publish.md（含 IP 白名单提醒）

### 修复

- **换肤零残留**：`_THEME_DEFAULTS` 11 → 17 条（补 surface / text_strong + 4 个主色衍生 alpha），
  两段式替换防误染；ink/sage 等非默认主题不再混出钢青蓝
- **BGM**：key 读取接通仓根 `.env`（此前只读 shell env，正确实现是死代码）；无 key 时按承诺
  「跳过并明说」而非硬报错；docstring 凭证位置纠正
- **logo 水印**：`add_logo.js` 支持从仓根 `.env` 读 profile 指针；缺 logo 打印说明后跳过不再崩溃
- **`svg_to_png --check-brand`**：白名单从 profile 生效令牌动态生成（此前写死默认色，
  自定义主题下拒真放假；且大小写不一致连默认主色都匹配不上）
- **学习飞轮归位 profile 层**：playbook / lessons / observations 迁至 `<profile>/flywheel/`
  （个人数据不再写进 git 跟踪文件）；个性化规则由 prep_writing 解析注入，模型不再读固定路径
- **推荐阅读产物落数据目录**（含身份卡的个人数据不再写进仓库工作树）
- **作品库可 env 直指**：`SANSHENG_WRITE_WORKS_FILE` 支持指向你既有的 yaml
- `lint_templates` 调色板基线钉规范默认值（私有主题机上不再报满屏伪 WARN）；
  遥测 detail 字段在匿名态下同步打码文章名；biz_id/headimg 获取指引纠正
- cover-styles 残留的两处旧色值令牌化；封面/信息图不随主题自动换色已在文档明示

### 合规

- 两个校验脚本中与 gzh-design-skill（AGPL-3.0）近似的正则常量块**独立重写**
- 致谢补齐：gzh-design-skill、WeWrite、humanizer（此前只有 baoyu-skills）
- 一处真实文章引文按「逐字引文换原创例句」纪律改写为虚构等效例句

## [0.1.1] -- 2026-07-11

### 新增

- **发布后·朋友圈文案**（`references/publish.md`）：发布链路的最后一拍 --
  拿到正式链接、归档、部署后自动产出一条 3-4 行朋友圈文案（钩子 → 价值 → 固定引流尾巴）。
  尾巴走 profile（`identity.site` + `writing.moments_cta`），仓库里不含任何具体品牌 / 域名。
- **一份 `.env` 配齐**：`profile_config` 现在也能从仓根 `.env` 读 `SANSHENG_WRITE_PROFILE_DIR` /
  `SANSHENG_WRITE_DATA_DIR` 指针（`os` 环境变量仍优先）。换机器只需拷一份 `.env`。

### 修复

- `setup_check.py` 在 GBK 控制台（Windows 默认）打 emoji 会崩，补 UTF-8 stdout 兜底。

### 测试

- `conftest.py` 与 `regression_baseline.py` 显式把测试钉死在 `profile.example` + 临时数据目录，
  与本机 `.env` 隔离，保证冻结 fixture（断言中性默认色）的确定性，且任何测试都不碰真实数据。

## [0.1.0] -- 2026-07-11

首次公开发布。这个 skill 在作者的真实写作流里跑了半年多，现在脱敏开源。

### 有什么

- **写作方法论全链路**：选题快评 → 大纲（含开篇策略分流）→ 正文 → 改稿 → 标题锻造
- **反 AI 味三层过滤**：套话黑名单 / 换模型语义差分外审 / 写作核心六条
  （So What 兑现、类比落地、反常细节锚、把自己写笨、段落具体领头、句间引力）
- **排版工程**：一键把 markdown 转成微信公众号能吃的 HTML，10 个组件模板；
  契约门（`scripts/contracts.py`）在产出不合规时直接 `exit 2`，不让你发出去
- **三套预置主题**：`slate`（默认，钢青）/ `ink`（近墨黑）/ `sage`（草木绿）。
  改一行 `theme:` 整套换皮，模板里不用动一个 hex
- **BYO 语料**：自己蒸馏想模仿的作者手册放进 `profile/corpus/authors/`；
  改稿飞轮（`scripts/learn_edits.py`）从你的手改 diff 里提炼规则，越用越像你
- **三层分离**：代码在仓里，品牌 / 身份 / 语料在你的 `profile/`，密钥在 `.env`。
  仓库里没有任何人的私密内容
- **提交前护栏**：`.githooks/pre-commit` 拦下形似密钥的内容与个人路径

### 设计上的诚实声明

不喂料时，产出接近通用 AI 写作 -- **这是设计，不是缺陷**。
风格是你的语料长出来的，不是提示词变出来的。仓内自带的
`profile.example/corpus/voice-samples.md`（本项目原创撰写）只提供基础的去 AI 味兜底。

### 不含什么

- **不含任何真实作者的风格手册或作品节选**。版权是一层原因；更重要的是，
  模仿谁该由你自己挑。取而代之的是一份「怎么自建手册」的 HOW-TO 和一份虚构作者的示例
- **不含任何真实文章作为测试夹具**。所有 golden 都是合成的（`tests/golden/_synthetic_*/`）
- **不捆绑任何第三方源码**。`jimp`（MIT）等运行依赖由你 `npm install` / `pip install`

[0.1.2]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.2
[0.1.1]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.1
[0.1.0]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.0
