---
name: sansheng-write
description: Use when 用户要写、改、润色或排版中文长文和公众号文章，包含选题、标题、封面或图文化需求；触发词：写文章、帮我写、改稿、定稿、公众号文章。AI 课程使用 sandy-class，晨报使用 sandy-morning-cards，视频使用 sandy-video。
metadata:
  version: "0.8.4"          # 与 GitHub Release 共用同一 SemVer；由 release.py 自动同步
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Agent, TodoWrite]
---

# 中文长文写作系统

运行要求：Python 3.10+、Node.js 18+ 与 baoyu-skills；BGM/各 renderer 的凭证按 `music.md` / `image-routing.md` 配置，只从环境变量读取。

**主入口**：只承载「路由 + 触发边界 + 全局元指令 + 高频铁律」，各阶段细则一律 lazy-load 对应 reference。**下文裸写的 `xxx.md` 一律指 `references/xxx.md`**（`profile/corpus/authors/` 与 `profile/` 下的文件已标全路径）。

> 🔴 **默认 = 全自动一路到草稿箱**：新文章按 autopilot.md；作者已给确认定稿时直接按 release-runtime.md。失败只在当前命令修复，不 skip、不伪造状态。自动链止于微信草稿箱；原创、赞赏与正式发布由作者人工完成。

## 🟢 启动前必读（元指令，先于任何阶段）

进任一阶段**第一件事按序读两份共享上下文**，读完不再问已知信息（主题色/账号名/创作者背景），只追问本任务才变的参数（风格/受众/字数）：

1. **品牌上下文** `profile/context.md`（品牌身份/人设/风格路由/对话约定）；未配置 profile 时回退仓内 `profile.example/context.md`（中性默认，正常路径不是错误）；皆无则兜底本文件「品牌身份 fallback」节。
2. **品牌织网（可选）** `profile/brand-net.md`（阵地地图/伏笔池/承诺台账）。存在时大纲阶段**步骤 7.5 织网三问必答**（联动已发文/推自有阵地/埋伏笔），答案落 `article-meta.yaml` 的 `weave:`（细则进 outline.md 步骤 7.5）；归档把本篇许的愿登进 brand-net.md §四。**文件不存在则跳过织网环节，不报错**（织网是可选玩法）。

> profile 目录由环境变量 `SANSHENG_WRITE_PROFILE_DIR` 指定（未配置则回退仓内 `profile.example/`），解析入口 `scripts/profile_config.py`。多阶段任务：完成一阶段再读下一个，勿一次性全读。

## 🔁 恢复协议（元指令）

进任何 `{数据目录}/{N}-{选题名}/` 目录**第一件事**跑 `python "$SKILL/scripts/pipeline.py" status`。state v2 保留 `first_completed_at`、更新 `last_verified_at/attempt_count/artifact_digest`；已完成上游产物发生变化时，当前与已完成下游自动标成 `dirty`，必须从最早 dirty 阶段重验。内容配置唯一真源是 `article-meta.yaml`，`.state.json` 只记流程状态。

## 快速路由（🔴 = 进该阶段前必读）

| 意图（含该行必要约束） | 读 |
|---|---|
| 新选题 / 写篇文章 / 聊方向 | outline.md |
| 展开正文 / 继续写 / 改稿（写前先跑 `prep_writing.py` 聚合 `_prep-context.md` 再走 7 步准备） | writing.md + style-routes.md 对应章 + profile/corpus/authors/{X}.compact.md |
| 给几版开头盲选 / 挑开头 / 换开头（2-3 版钩子 A/B/C 盲选不给理由，**autopilot 唯一法定停顿点**） | writing.md §开头候选盲选 |
| 内容增强 / 素材不够尖（4 套策略，**大纲后写作前**） | content-enhance.md |
| 想标题（内联出 5 候选+排序） | title.md |
| 写作技法 / 开篇结尾 / 金句 | craft-techniques.md |
| 文体专属（教程/方法论清单/技术解读，仅这三类加载；文体三选一的**选定**在 outline Step 3） | writing-genres.md |
| 去 AI 味 / 磨稿 | anti-ai-filter.md |
| 冷读外审（磨稿后排版前派**不同模型族** subagent，产 `_stutter-list.md`，与事实复核同窗口并行） | semantic-review.md |
| 事实复核 / 数据版本价格核验（磨稿后排版前派**无上下文** subagent，产 `_fact-check.md`，preflight 硬断言 exit 2） | fact-check.md |
| 排版 / 转HTML / 导读栏 | layout.md |
| 排版兼容 / 表格 / 卡片 / 平台过滤 | wechat-compat.md |
| 排版踩坑 / 样式异常（**按需，日常 SOP 不读**） | layout-reference.md |
| 🔴 改任何颜色/圆角前必读（视觉 SSOT，改一处全局生效） | design-tokens.md |
| 🔴 任何生图前必读；真人真事主动搜真实新闻照按 16:9 截取、**禁 AI 生成人物肖像**（新闻人物/重大事件同此） | image-routing.md |
| 🔴 生成封面 / 选风格（锁定 `montage-evidence`，自动选择/近3篇回避已失效；余 4 种仅 meta 显式 `cover_style` 激活） | cover-styles.md |
| 生成音乐 / BGM / 主题曲（MiniMax `music-2.6-free`） | music.md |
| 🔴 已有定稿 / 配图排版 / 发草稿 / 发布后收尾（唯一机械链） | release-runtime.md |
| 发布状态、凭证与人工边界说明 | publish.md |
| 转图文 / 拆图文 | xhs-storyboard.md |
| 全流程自动驾驶（并行只用于独立工作单元；定稿后的机械链串行） | autopilot.md + orchestration.md + agent-contracts.md |
| 🔴 查铁律 / 确认约束（**进入发布/排版/生图前必读**） | iron-rules.md |
| 学某文排版（Agent 抓 URL 分析→排版参考库） | — |
| 我改了 / 学习我的修改（draft vs final diff 提 pattern 写 playbook.md） | learn-edits.md |
| 复核 skill / skill 自省进化 | skill-review.md |

**子命令快捷入口：** `写 选题`/`写 大纲`→outline ｜ `写 正文`/`写 展开`→writing ｜ `写 开头候选`/`盲选开头`/`挑开头`→writing §开头候选盲选 ｜ `写 标题`→title ｜ `写 音乐`/`写 BGM`→music ｜ `写 排版`→layout ｜ `写 发布`→publish ｜ `写 图文`/`转图文`→xhs-storyboard ｜ `写 状态`/`写 进度`→`pipeline.py status` ｜ `全流程`/`走一遍流程`→autopilot ｜ `复核 skill`/`skill 自省`/`skill 复盘`/`skill 进化`→skill-review

## ✍️ 写作核心六条（语义层正向规则 — 六个章节指针的**目录**，唯一 single-source）

> 🔴 本节只是指针目录、**非可单独执行的「够用版」**--摘要在场模型会跳过正文（已知失败模式）。写作期真正内化 `_prep-context.md`（`prep_writing.py` 渲染，§〇 三原则置顶），磨稿期按每条指针**进对应章节逐条打卡**，别只看目录。
> 🟡 诚实边界：六条只有「写前喂料 + 写后自觉」、无机器写后校验；`exit 2` 硬门只拦正则/计数抓得到的表层指纹（套话黑名单、半角标点、整句加粗计数），语义人味正则无法强制、同模型自审照不出，唯靠换模型语义差分（semantic-review.md），别当已机器落地。

1. **So What 兑现**（论点替读者问"所以呢"并答）→ anti-ai-filter.md §8.1
2. **类比落地**（抽象判断配日常类比）→ anti-ai-filter.md
3. **反常细节锚**（关键场景给反常到不像编的具体细节）→ anti-ai-filter.md §2.3.5
4. **把自己写笨**（不立权威，自嘲换信任）→ anti-ai-filter.md §6.1
5. **段落具体领头（BLOT）**（每段第一句给具体的人/事/画面/数字）→ writing.md §密度法则 9
6. **句间引力**（上句尾留钩子、下句头接住；顶真 + 旧信息在前新信息在后）→ **单一来源** writing.md §句间引力

## 特殊约定（每轮解析对话都用）

- **「」批注：** 「」内是批注非正文--指令类直接执行，参考类作上下文。**「素材」标记：** 归入素材分拣表。**「入囊」标记：** 自动沉淀 profile 的选题储备文件对应分类作选题储备。
- **素材自动读取：** 对话开始检查工作目录 `素材/`，有内容一并读。**事实验证：** 需核实的事实/数据直接搜，不问创作者。
- **🔴 破折号统一 `--`：** 给读者的文字里所有破折号用两个英文连字符 `--`，禁全角。
- **🔴 铁律总纲 iron-rules.md：** 集中所有硬约束（排版→发布序列/**金句卡禁装饰引号**/开篇策略分流/生图后端/组件小图/数据图防幻觉/信息来源格式/AUDIO-CARD 位置/知识图位置/时间线 H3/文章导读/敏感议题用词防下架/**不可 skip 的 stage**/发布完整性）。**进入发布/排版/生图前必读。**

## 🔄 skill 自省机制

`contracts.py`/`format_layout.py`/`pipeline.py` 把 v2 观察记录追加到 `scripts/profile_config.py::observations_file()` 解析出的 `<profile>/flywheel/_skill-observations.jsonl`（未配 profile 才回退仓根）。复核时同时统计原始尝试与每篇最新结果，避免重跑放大失败率；旁观者只诊断，改动由用户拍板。

## 排版模板 / 配置 / 发布脚本

- **HTML 组件模板**（导读栏/H2-PART/H3 时间线/Case/要点/金句卡/链接卡/深读/推荐/关注卡）在 `templates/`；**排版进 layout.md** 看工作流与组件清单、从 `templates/` 读代码。🔴 金句卡禁用 `&ldquo;`（部分平台渲乱码），出处行=发丝线 + 淡化右对齐。
- **`article-meta.yaml`：** 每篇目录持久化参数（导读文案/H2 风格/封面关键词/`weave`/`modifier_style`，模板 `templates/article-meta.template.yaml`），`format_layout.py` 自动读、CLI 参数优先。
- **定稿后运行时**统一见 release-runtime.md。关键入口为 `adopt-final`、`compile-visuals`、`render-visuals`、`visual-qa`、`seal visual`、`release-to-draft`、`finalize`。`release-to-draft` 是唯一草稿创建入口；拿到永久链接后 `finalize` 按“归档→验证→官网→朋友圈文案”收尾。archive 校验失败不得写盘；🔴 **禁手改 `articles.md` / `works-dashboard.html`**。

## 运行时数据文件（语料池，勿整段复制进上下文）

- **统一作品库 SSOT：** 实际路径只认 `scripts/profile_config.py::works_file()`（默认 `{数据目录}/works.yaml`，可由 `SANSHENG_WRITE_WORKS_FILE` 重命名）；文章+视频每篇一条。写作/配图前**先读近 3 篇**做维度/收尾/风格去重；发布后 `archive` 写入。`articles.md` 与 `works-dashboard.html` 是自动渲染视图（🔴 禁手改）；命令输出必须打印解析后的真实绝对路径，旧 `history.yaml` 已冻结。
- **`prep_writing.py` 写作前自动聚合进 `_prep-context.md`（不必手翻）：** profile 语料池的 风格示例库 / 金句库（按主题）/ 反例对照库 / voice 语料（gate：>200 字≈2-3 段即注入）+ `profile/corpus/authors/{X}.compact.md`（用户自备的作者风格手册；无自备手册时注入仓内原创的 `profile/corpus/voice-samples.md` 做基础人味兜底）。金句库路径只认 `profile_config.py::golden_lines_file()`；已有库在别处时用 `SANSHENG_WRITE_GOLDEN_LINES_FILE` 直指，禁止复制第二份。
- **按主题人工挑读（非自动）：** 若 profile 自带精选样本库 `profile/corpus/samples/{作者}/`，写作前可按当前风格路由抽读 2-3 篇（无对应作者回退 `profile/corpus/voice-samples.md`）。按需查 profile 里的品牌规范 / 选题储备文件。

## 成品输出目录

```
{数据目录}/{N}-{选题名}/
  ├── 大纲.md ← 大纲   ├── 定稿.md ← 写作   ├── 定稿.html ← 排版   └── 素材/ ← 所有 AI 生成图片
```
编号按 `{数据目录}/` 下已有最大序号递增。

## 品牌身份（fallback 兜底 — 正常优先读 `profile/context.md`）

> ⚠️ 仅当 `profile/context.md` 与回退 `profile.example/context.md` 均不存在时以本节为准。

- **品牌名 / 账号名：** 由 profile 提供（示例见 `profile.example/context.md`）｜ **主题色（primary）：** `#2F6F8F`（中性 slate，改样式见 design-tokens.md；六套预置主题 slate/ink/sage/jade/amber/plum 见 `profile/brand.yaml`）
- **风格路由：** 主路由为 profile 自备的作者风格手册（`profile/corpus/authors/*.compact.md`）**单选其一**；可叠加 modifier 手册 0-1 个组合（**不当主路由用**）；文体三选一（深度文/教程文/方法论清单文，细则 outline Step 3）。**完整清单与叠加机制见 style-routes.md**（modifier 由 `prep_writing.py` 自动叠进 _prep-context）。无自备手册时回退 `profile/corpus/voice-samples.md`。
- **品牌规范 / 创作者人设：** `profile/context.md`（中性示例见 `profile.example/`）。

## When NOT to Use（反向路由：交别的工具 / 不触发）

| 用户意图 | 应该用 | 不要用本 skill |
|---|---|---|
| 先把话题/背景查清、看各方怎么说（再决定写不写） | **你惯用的调研工具**（多源+交叉验证+归纳）| 调研交调研工具；"值不值得写"由本 skill「写 选题」阶段做 |
| 单独打磨/锻造一个标题（无正文） | 本 skill「写 标题」（title.md） | 纯标题打磨归本 skill 内联锻造 |
| 已发布文章 数据复盘/涨粉/阅读量诊断 | **你的数据分析工具** | 本 skill 不处理已发布数据 |
| 已写好文章 转短视频口播/分镜 | **你的视频 skill** | 本 skill 出文章不出视频脚本；定稿后转视频交视频工具，不越界写口播 |
| 通用中文写作（不需要品牌约束）| 原生写作即可 | 品牌约束会污染通用写作 |
| 英文内容 / 纯代码 / Git 同步 / 环境配置 | 默认流程 | 本 skill 专为中文长文设计 |

**衔接规则 · 选题/找素材调研分流：** **轻素材**（核一事实/补一数字/查一名词/确认时间价格）→ 自己 WebSearch **直接搜**，不起调研工具；**深素材**（有争议/多平台口碑/交叉验证去伪/国内外都看/成体系背景时间线，或用户说"查清楚/各方怎么说/是不是真的/交叉验证"）→ **委派你惯用的调研工具**，写时手动引其事实底座与信源--**不自动注入**素材、不预填 meta。拿不准默认轻素材自己搜。

## references 三级分层（按加载时机分层）

- **L1 · 启动必读：** 新文章读 autopilot；作者定稿后的机械工作只读 release-runtime；进入排版/生图/发布前读一页 iron-rules。真正每次开局无条件读的是 `profile/context.md` + 可选 `profile/brand-net.md`。
- **L2 · 阶段按需（路由触发时加载）：** 主流程各 reference（即上「快速路由」表所列）+ `profile/corpus/authors/*.compact.md`（用户自备，数量不定，prep_writing.py 自动聚合）。
- **L3 · 排障备查（低频/进阶/历史，日常不读）：** layout-reference / visual-qa（接复核器 + 视觉闸三种静默失效）/ orchestration / agent-contracts / learn-edits / skill-review / `_archive/候补技法池.md`（技法池候补备料，craft-techniques 主池不够时才翻）。
