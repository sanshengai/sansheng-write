# 🤖 编排器状态机（Orchestrator State Machine）

> ✅ **2026-05-22 P1 已落地 + 混合方案定调**：fan-out 执行层就位。`orchestrator=on`（**默认**）下，主 Claude 按 [orchestration.md](orchestration.md) §编排器 fan-out 实操手册，在 4 个 fan-out 阶段（infographic / cover / research / review）一条消息发 N 个 `Agent` 真并行派发；**content_enhance 走主轴串行**（连贯性敏感、不并行）。`orchestrator=off` 走下方 §Legacy Fallback 全串行，两者产出字节级等价。

> **v4.0 起本 skill 引入「编排器（orchestrator）+ subagent」骨架。**
> 本文件顶部为编排器导言与阶段归属表（行为契约）；**下方 `## Legacy Fallback` 章节为原 v3.x 全自动驾驶舱原文，一字未改**，供 `orchestrator=off` 时回退使用。

## 编排器开关语义

- **`orchestrator=on`**（**默认**；`pipeline.py init` 写入，可用 `pipeline.py orchestrator off` 关闭）：走本章「编排器状态机」。可并行阶段接 `fan-out`（一条消息发 N 个 `Agent` 真并行），其余保持 `主轴`（编排器主线串行）。fan-out 范围见下方阶段归属表，执行手册见 [orchestration.md](orchestration.md) §编排器 fan-out 实操手册。
- **`orchestrator=off`**（回退）：直接走下方 `## Legacy Fallback（orchestrator=off 时走此路）` —— 即原 v3.x「全域自纠偏无感驾驶舱」，全程串行，逻辑与历史完全一致。
- 两条路产出**字节级等价**，任何时候可安全切换；中途切换不动 stage 状态。

## 阶段归属表（行为契约）

每个阶段标注其在 `orchestrator=on` 下的执行归属（`主轴` = 编排器主线串行；`fan-out` = 下放并发 subagent）。归属仅描述**执行拓扑**，不改变各阶段产出与规则；详细 subagent 行为契约见 [agent-contracts.md](agent-contracts.md)，编排状态机与状态写者唯一性见 [orchestration.md](orchestration.md)。

> 🔴 **fan-out 只发生在「单个阶段内部」** —— 把一个阶段里彼此独立的子任务（多张信息图 / 多种封面风格 / 多个调研桶 / 多个审稿角色）并发展开，跑完合并回该阶段。**阶段与阶段之间永远主轴串行有序**，由编排器主轴持有时序：并行不会打乱「选题→正文→…→发布」的先后次序。

| # | 阶段 | 归属 | 说明 |
|---|------|------|------|
| 1 | 选题 / 大纲 | 主轴 | 需贯穿上下文，串行。**阶段内** research 调研可 fan-out（多信源桶并行） |
| 2 | 正文起草 | 主轴 | 依赖大纲，串行。前置的「内容增强」4 策略走主轴**串行**（不并行，见 [content-enhance.md](content-enhance.md)） |
| 3 | 磨稿 / 反 AI 痕迹 | 主轴 | 依赖正文，串行。**阶段内** review 审稿可 fan-out（opt-in，多角色并行，需用户确认） |
| 4 | 排版预检门（.md 级 · `format_layout` preflight） | 主轴 | 仅扫 `定稿.md` 断言 prep / 冷读 / AI 腔，**不渲染 HTML**；真正的 MD→HTML 渲染在 step 8 | 
| 5 | 封面图 | 主轴（默认）| 🔴 **锁定 `montage-evidence`**（2026-05-22），默认单风格、不 fan-out；仅 `article-meta.yaml` 显式填其他 `cover_style` 时才退化为多候选 fan-out 选优 |
| 6 | 信息图 ≥4 张 | **fan-out** | 多图并发产出，主轴收齐验证 |
| 7 | BGM | 主轴 | `generate_article_bgm.py` 单写者（MiniMax 方法A）；**须在 MD→HTML 前**，先生成 mp3 + `bgm_cover.png` + 插 AUDIO-CARD 卡片 |
| 8 | MD → HTML | 主轴 | 确定性转换，单写者 |
| 9 | 加 logo | 主轴 | 批处理，单写者 |
| 10 | 推送草稿箱 | 主轴 | 终态，单写者 |

> 🔴 第 7 步「BGM」2026-06-18 复活（引擎 Lyria→MiniMax `music-2.6-free`），单写者主轴，**须在 MD→HTML 之前**执行（先插卡进 定稿.md，排版才渲染出音频卡片）。

> 🔴 **单一状态写者**：无论 on/off，`.state.json` 的唯一合法写者是编排器（或 Legacy 模式下的 `pipeline.py`）。subagent **永不**自行读写 `.state.json`、永不自行 `pipeline.py skip`，失败只回传结构化现场，恢复决策归编排器（详见 [iron-rules.md](iron-rules.md) subagent 铁律）。

---

## 🖼️ 信息图阶段（orchestrator=on · 第 6 步 · fan-out 并行派发）

> 本节**仅在 `orchestrator=on` 时生效**，替代下方 Legacy 第 6 步的串行执行。`orchestrator=off` 一律走 Legacy（下方原文一字未改，下界限）。封面图（第 5 步）默认锁定 `montage-evidence` 单风格、不 fan-out；仅 `article-meta.yaml` 显式填其他 `cover_style` 时才退化为多候选 fan-out（与信息图同批并发）。本节以信息图为例。
>
> 🛠 **2026-05-22 P1 落地**：所有 fan-out 阶段（infographic / cover / research / review）的**通用执行序列 7 步 + subagent prompt 模板 + 4 阶段特化表 + 真并行技术关键**见 [orchestration.md](orchestration.md) §编排器 fan-out 实操手册（content_enhance 走主轴串行，不在 fan-out 之列）。本节是 infographic 的特化展开，与实操手册完全一致。

编排器（= 主 agent，单线程）按下列**确定性流程**驱动信息图 fan-out，全程不把状态写权下放：

1. **定 N 与每张规格**：编排器按 [image-routing.md](image-routing.md) 路由决定信息图张数 N（**≥4**）与每张的 `aspect` + prompt + 数据表——构成必须是「开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1」。**所有 baoyu-* 生图统一 1K（长边 ≈1024px，达标带 [900,1200]），宽高比按上述路由不变**（详见 [iron-rules.md](iron-rules.md) §生图分辨率铁律 / [image-routing.md](image-routing.md) §1K 横切规范）；数据型图表走本地 `matplotlib`/`pyecharts` 脚本、不受 1K 限制。
2. **逐张构造上下文 bundle**：对**每一张**图，编排器按 [orchestration.md](orchestration.md) §上下文 bundle 模板组装四键 `dict`：
   - `sansheng_context`：品牌视觉调性摘要（从 profile 读取，不转储全文）；
   - `iron_rules`：**配图相关铁律子集**（生图后端铁律、生图分辨率 1K 铁律、信息图风格 `--style claymation` 或 `morandi-journal` 二选一、严禁 Agent 原生 `generate_image`/`imagine`、数据图防幻觉）——只下发与本阶段相关的若干条，不下发全集；
   - `article_meta`：`article-meta.yaml` 原样字典；
   - `stage_input`：**该张**已确认的 prompt + 目标 `aspect` + 1K 规格 + 数据表（如为数据图）。
   编排器派发前对每个 bundle 调 `scripts/contracts.py:validate_bundle` 自校验，不通过先补齐，**禁止带病派发**。
3. **并行派发 N 个 subagent**：在**一条消息内**发起 N 个 Agent 调用（一图一 subagent），真正并发 fan-out。subagent 是无状态执行单元：只产出对齐 `_OUTPUT_SCHEMA["infographic"]` 的结构化产物（`{"images":[{path,aspect,bytes}]}`），**不碰 `.state.json`、不调 `pipeline.py`、不自行 `skip`、不静默吞错**（违反即判不合规，详见 [iron-rules.md](iron-rules.md) subagent 协作铁律）。
4. **收齐 → 过验证门**：编排器等 N 个 subagent 全部返回（含失败回传）后，先逐单元过 tier-1 结构契约 `validate_output("infographic", payload)`，再对**合并后的新产出集合**过 tier-2 语义门 `verify_infographic_set(images)`——后者按真实像素校验 ≥4 张 / 9:16+16:9+9:16 构成 / aspect 三枚举 / ≤2MB / 1K。`verify_infographic_set` 返回非空 = 有违规。
   > tier-2 门**只对本次 fan-out 新产出强制，不追溯历史冻结 golden**（历史文章合法但不符新规）。
5. **不过的单张就地重派**：验证门报某张违规（如比例不符 / 非 1K / 超 2MB），编排器**只重派那一张**（不是整阶段重来），按错误建议自纠偏（换 prompt / 调 aspect / 重压缩）。**同一张连错 3 次才回报用户**，回报带三要素（阶段名 / 失败原因含验证门哪关挂 / 已尝试恢复方式）。恢复决策权完全归编排器，subagent 无权放弃或 skip。
6. **全过才推进**：N 张全部过双门后，编排器把产物清单按 [orchestration.md](orchestration.md) §留痕路径约定落盘（`素材/*.png` + `素材/infographic/*.json`，数据图 `.py` 留文章目录），再写 `.state.json` 推进到下一阶段（先 BGM，再 MD→HTML）。

> 与 Legacy 的关系：本节只改**执行拓扑**（串行 → 并行 fan-out + 双验证门），**不改产出规则与构成要求**——信息图仍是 ≥4 张、开篇/结尾 9:16、中间 16:9、走 `baoyu-skills:baoyu-infographic`、`--style claymation` 或 `morandi-journal` 二选一。`orchestrator=off` 时下方 Legacy 串行路径**原文不变**继续生效。

---

## Legacy Fallback（orchestrator=off 时走此路）

> 以下为原 v3.x「全域自纠偏无感驾驶舱」原文，`orchestrator=off` 时按此路执行；`orchestrator=on` 的 P0 阶段各阶段行为亦与此完全等同。

# 🤖 全域自纠偏无感驾驶舱 (Agent Autonomous State Machine)

当用户抛出想法、要求生成文章或触发流水线时，你必须进入**全自动隐式闭环模式**。不再扮演"事事请示的副驾"，而是"大包大揽的顶级主控"。

**核心操作规范**：
1. **一镜到底，拒绝中断**：无论是大纲定核心、正文生文字、还是后台生图发布。所有步骤均被折叠进后台思维链。你不准做完"找核"就停下来问用户，你必须**自行向体内的自查器要授权**！
   - 🔴 **唯一例外**：开头候选盲选（步骤 2.5）是 autopilot **唯一允许的法定停顿**——初稿写完后停一次，给用户 2-3 版开头编号挑一个，用户回一个字母即续跑。除此之外一切照旧闭门，选完之后继续一镜到底跑到草稿箱，中途不再有第二次停顿。这一停不违反"跑到草稿箱才算结束"——它在磨稿之前、极简（一个字母）、选完直奔草稿箱。
   - 🔴🔴 **检查点闸门模式（profile 可配，配了就优先于上一条）**：`profile/brand.yaml` 的 `workflow.checkpoints` 含 `blueprint` / `draft` 时，法定停顿改为两道**硬闸**（设计动机：前期出错会导致正文/配图/音乐/排版全链返工，停顿的价值 = 拦截概率 × 下游返工成本）：
     - **blueprint 蓝图闸（outline 末）**：把「大纲 + **5 套『外标题 + 封面文案』配套方案** + 2-3 版开头候选（盲选格式）」**一包交付**，硬停等作者拍板——一条回复搞定三项（"方案 2 / 开头 B / 大纲第三节改 X"）。**配套方案 = 标题候选（按 title.md 锻造并排序、标推荐）+ 与之配套的封面文案（cover-styles.md 的 L1 主视觉大字 + L2 副行，风格含英文 ghost 层的一并给 3 词）**——标题卖"为什么点开"、封面卖"里面讲什么"，两者按封面文案四招分工互不复述；**成套呈现、成套选定，不把标题和封面拆成两次确认**。作者若改大纲方向，开头候选重出一轮再收口，仍算同一道闸。确认后把结论落 `_blueprint-approval.md`（选定标题 / 开头字母 + 首句 / 大纲改动 / 时间），开头选定照旧同步写 `_opening-choice.md`（恢复链路兼容）。`pipeline.py verify outline` 硬查锚点，缺失不放行。**开头盲选并入本闸，写作前只停这一次。**
     - **draft 定稿闸（writing 末）**：磨稿 + 冷读外审 + 事实复核修复**全部完成后**，硬停把 `定稿.md` 交作者审读；作者回「过 / 改 X」，结论落 `_draft-approval.md`，`verify writing` 硬查。通过后 封面 → 信息图 → BGM → 排版 → 草稿箱 照旧**零停顿一路到底**（后端零停顿铁律不变，只是起跑线从"开头选定"改为"定稿过闸"）。
     - **闸上不在场 = 等，不取默认续跑**（这与开头盲选的"不在场取默认"相反——闸的目的就是防返工，自动续跑等于没闸）。恢复协议：新会话进目录跑 `pipeline.py status`，verify 报 checkpoint 未过即知停在哪道闸。
     - **单次免检**：作者明说「免检 / 一路到底不用确认 / 直接跑完」→ 两闸自动通过，锚点写『作者免检授权 + 时间』留痕。
     - 未配置 checkpoints（公开仓默认）不受影响：仍是原「唯一停顿 = 开头盲选」全自动。
     - **后端（配图/BGM/排版/推送）永不设闸**：错误可局部重跑、成本低，且草稿箱本身就是最终人工预览位。
   - 🔴🔴 **后端零停顿铁律**：本 skill 的初衷=**前期文字稿（大纲 / 开头盲选 / 定稿 / 标题）确认后，进入完整流程就一路跑到草稿箱**。所以**文字一旦确认 + 用户给任意推进信号**（"继续 / 好 / go / 发吧 / 行"——不限于"全流程"这种触发词），就从封面 → hero → 信息图 → BGM → 排版 → 发布**一路做完，禁止在后端再插入任何确认 / 选择 / "要不要继续"**。具体禁止：
     - ❌ "封面出来要不要换 / A 还是 B"——封面锁死 montage-evidence，**本就无需选择**，生成即用、不预审
     - ❌ "信息图要不要做 / 要几张 / 这篇豁免吗"——≥4 张是铁律、无豁免，**直接做满**，别问
     - ❌ "现在继续把剩下做完吗 / 留到下一程吗"——文字已确认就是已授权，**别把后端工作重新拿出来请示**
     - ✅ 后端**唯一**可中断的两种情形：① 某步连错 3 次自纠偏无效（按 [autopilot 失败不 skip 铁律](#)，回报现场）；② 涉敏用词扫描命中需用户确认防下架。除此之外一律闭门跑完，**最终一次性交付草稿箱**。
     - 教训：曾在封面阶段又停下来给 A/B 选择 + 问 scope——文字早确认了，这是把"已授权的后端"重新请示，正是本铁律要根除的。
2. **后台多步拆分，前台一次交付**：如果你担忧长文生成导致 LLM 质量衰退，在后台私下分块自评重写，但对人类曝光的始终是一个不被打扰的流线，直到给出完美排查版本。
3. **每次回复时同步进度卡**：在你的最终输出或者中间关键节点，把进度打卡表打印出来。已完成标 `[x]`。
4. **原生无缝生图**：自动读取 `baoyu-skills:baoyu-cover-image` 对应的配置规则，按照系统指令自行画完不再挂起。

---

## 触发词清单

任何以下关键词（同义词组）出现在用户消息里都进 autopilot，**必须跑到 `baoyu-skills:baoyu-post-to-wechat` 草稿箱推送成功才算结束**，禁止停在排版/封面/BGM 阶段：

- 完整流程 / 全流程 / 一气呵成
- 走一遍流程 / 走一遍 / 走完
- 一镜到底 / 一条龙
- 从头到尾 / 全自动 / autopilot

---

## 流程顺序（不可跳跃）

> 🔴 **阶段时序唯一权威 = `scripts/pipeline.py` STAGE_ORDER = outline → writing → cover → infographic → bgm → layout → logo → publish → archive**（配图 / BGM 先于排版渲染，图先于 HTML）。本文件下方任何叙述（编号列表 / 状态看板 / 行内顺序）与之冲突，一律以 STAGE_ORDER 为准。下方各处已据此统一，留此声明供后续维护者校准。

> ⚠️ **顺序硬约束**：BGM 必须在 MD→HTML 排版**之前**执行——先生成 mp3 + 把 AUDIO-CARD 插入 `定稿.md`，排版才会渲染出音频卡片。MiniMax 引擎**不依赖图片输入**（与旧 Lyria 不同），放在配图之后、排版之前即可。

1. **选题 / 大纲** — outline.md
1.5. **🔴 开头候选盲选（autopilot 唯一法定停顿点）**：大纲定稿后、动笔写正文**之前**，**停一次**——按 [writing.md §开头候选盲选](writing.md) 基于大纲+种子给出 2-3 版不同钩子类型的开头候选（编号 A/B/C，只给版本不给推荐理由）。等用户回一个字母（或"换个角度"）即续跑；**选定的开头定下全文调子，顺着它闭门一气呵成**写完初稿→磨稿→冷读外审→封面→信息图→BGM→layout(MD→HTML)→发布，中途不再停（磨稿期若开头和全文不咬合，自动微调那一版，不再打扰）。结尾盲选默认关（除非用户显式要）。为什么放在动笔前：开头没定，后面内容朝哪写都没依据。
   - 🔴 **盲选锚点产物**：用户回字母选定后、**标 `done writing` 之前**，必须在工作目录产出一个轻量 `_opening-choice.md`，记录选定开头（字母 A/B/C + 首句原文 + 选定时间），作为这个「唯一法定停顿点」的**可恢复锚点**。理由：开头盲选是纯 prose 停顿、无 state 无脚本门，跨会话恢复时若无此文件痕迹，新会话见 `writing=done` 会直奔 cover、**静默跳过盲选**。有了 `_opening-choice.md`，pipeline 可对它做存在性 **WARNING** 提示（仅提示、不 exit 硬拦，兼容历史文章无此文件），杜绝静默漏盲选。
2. **正文起草** — writing.md
   - 🔴 **前置必跑**：`prep_writing.py` 聚合 compact/vocab/金句/AI 腔禁区 → 工作目录 `_prep-context.md`，写作时内化它。排版阶段 A 层前置门会断言此文件存在，跳过则 `exit 2`
3. **磨稿 / 反 AI 痕迹** — anti-ai-filter.md
   - 🔴 **磨稿收尾必跑冷读外审 / 换模型语义评审**：派一个**不带写作上下文**的全新 subagent 冷读 定稿.md（只给正文，不给大纲/seed/_prep-context），以首读读者身份逐段标卡顿 + 做语义差分。**高价值篇换不同模型族**（如 Sonnet，同模型自审照不出语义 AI 味）。产出工作目录 `_stutter-list.md`（**带 semantic-review-signature 签名**：评审模型/写作模型/段数）。**完整契约见 [semantic-review.md](semantic-review.md)**（派发/换模型/语义靶子 10 类/签名 schema）。写作 agent 不得自审代替。排版 preflight 断言此文件存在，缺失 `exit 2`；签名缺失或评审模型==写作模型只 WARNING 不阻断
   - 🔴 **磨稿收尾同窗口跑事实复核**：与冷读外审**并行**，派一个**不带写作上下文**的全新 subagent 从定稿提取数字/日期/价格/版本号/专名/引语，逐条对 `素材/research/*.json` 或现场搜索核实，产出 `_fact-check.md`（带签名：复核模型/条目数/结论）。冷读抓内部读感与前后矛盾，事实复核抓外部真伪，两者划界。发现事实错写作 agent 修正后复跑；`need_verify` 项改模糊表述或删（零停顿，待核实清单最终一并汇报）。完整契约见 [fact-check.md](fact-check.md)。排版 preflight 断言 `_fact-check.md` 存在，缺失 `exit 2`
4. **排版前 MD 预检（format_layout 的 preflight 门）**（layout.md）— **仅扫 `定稿.md`、不渲染 HTML**：含 A 层断言（`_prep-context.md` 存在）+ 冷读外审门（`_stutter-list.md` 存在）+ 事实复核门（`_fact-check.md` 存在）+ B-主门 AI 腔黑名单与导游腔元话语（命中 `exit 2` 逼补 prep / 冷读 / 事实复核）+ B-软门
   - 🔴 **本步只做 .md 级断言门、不产出 HTML**：真正的 MD→HTML + `format_layout.py --all` 渲染在后面的 step 8（layout 阶段）。此处早跑预检，是为了在磨稿后立即把缺 prep / 缺冷读外审 / AI 腔等问题逼出来，而非提前渲染。
5. **封面图** → `baoyu-skills:baoyu-cover-image`
   - 🔴 **MUST 先读 [cover-styles.md](cover-styles.md) 顶部 override 段**（H1 后第一段）
   - 默认走 `montage-evidence`（三件套：英文 GHOST-WATERMARK + 中文 L1/L2 关键词主题色 + 3 个 quiet-pill 胶囊 + 右侧拼贴区 black-fill 信息徽章 + 虚线箭头）
   - **严禁套用历史文章已封存的 conceptual / focus 风格 cover.md 模板**
   - 同步 [iron-rules.md 流水线隔离铁律](iron-rules.md) + [iron-rules.md 封面图文字样式铁律 第 5 条](iron-rules.md)
6. **信息图 ≥4 张** → `baoyu-skills:baoyu-infographic`（**唯一允许入口**）
   - 🔴 **信息图 = 内容总结，不是装饰插画**：每张图必须先**分析该段内容 → 选一个信息版式（清单/对比/流程/矩阵）→ 把原文的真实要点·数字·标签当图内中文文字排进去**。prompt 三件套 = 真实内容 + 版式骨架 + 官方 style。只画"物件/场景、没一句原文要点"的 = 打回重写（踩坑教训：手写黏土场景风格对但零信息，一眼被看穿）。中文要点多→Gemini 偶尔糊字须逐张核验重生，宁糊字重生也不退回零信息好看场景。详见 [image-routing.md §③](image-routing.md)
   - 🔴 **严禁直接调 `baoyu-skills:baoyu-image-gen` batch 跑信息图**（会跳过 baoyu-infographic 的 style 处理）
   - 🔴 **style 二选一**（详见 [image-routing.md §信息图 style 选择铁律](image-routing.md)）：
     - AI 工具教程 / 产品评测 / 功能解读 → **`--style claymation` 暖米黄轻盈版**（默认）
     - 行业趋势 / 商业评论 / 人文反思 → **`--style morandi-journal`**（莫兰迪杂志风）
     - 其他 20 种 style **全部封存**，新文章不再选用
   - 🔴 **单篇文章所有信息图（≥4 张）必须风格统一**，禁止 claymation + morandi 混用
   - 一句话判定：「解释工具/产品怎么用」→ claymation；「评现象/趋势/价值观」→ morandi-journal
   - **踩坑教训**：craft-handmade 单薄、claymation 深色版厚重；claymation 暖米黄定调轻盈耐看
   - 构成铁律：开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1
   - 例外：精确数据图（雷达/折线/柱状/饼/跑分）走本地 `matplotlib`/`pyecharts`，不走 baoyu-infographic
   - 例外：精确架构图 / 时序图 / 数据流图（≥5 节点 + 拓扑核心）走 `baoyu-skills:baoyu-diagram`
   - 同步 [image-routing.md](image-routing.md) 路由表 + [iron-rules.md 流水线隔离铁律](iron-rules.md)
7. **BGM** → 🔴 Claude 先按 [music.md](music.md) §Claude 提炼标准 提炼诗意 theme_brief/imagery/点题歌名/选风格，再传参调 `generate_article_bgm.py --theme-brief ... --imagery ... --song-name ... --style ...` → MiniMax 自动写词生成 + `bgm_cover.png` + 插 AUDIO-CARD；不依赖图片/Gemini，须在排版前跑
   - 🔴 **完成后必须跑 `pipeline.py verify bgm`（硬查 mp3 + 「本文主题曲」卡片），未过不得进入 step 8 layout（MD→HTML）**——`verify_publish_assets` 对 BGM 缺失视为正常放行，这道 verify 是进 layout 前的唯一硬关卡
8. **MD → HTML** → `baoyu-skills:baoyu-markdown-to-html` + `format_layout.py --all`
9. **加 logo** → `add_logo.js`（**排除** hero.png 和 bgm_cover.png 等组件小图）
10. **推送到草稿箱** → `baoyu-skills:baoyu-post-to-wechat`

---

## 失败恢复 SOP（硬规则）

- 任何阶段失败时，**禁止用 `pipeline.py skip` 绕过**
- 按脚本错误信息给的建议恢复：重试 / 换风格 / 修文件 / 调参数
- **同一阶段连错 3 次才回报用户**，期间自主决策恢复路径
- 回报时要带：阶段名 / 失败原因 / 已尝试的恢复方式

---

## skill 调用必须带 namespace 前缀

通过 Skill 工具调用 baoyu plugin 的 skill 时使用 `baoyu-skills:<name>` 全名，裸名会失败。常用映射：

| 描述名 | 真名 |
|--------|------|
| baoyu-cover-image | `baoyu-skills:baoyu-cover-image` |
| baoyu-infographic | `baoyu-skills:baoyu-infographic` |
| baoyu-diagram | `baoyu-skills:baoyu-diagram` |
| baoyu-image-gen | `baoyu-skills:baoyu-image-gen` |
| baoyu-xhs-images | `baoyu-skills:baoyu-xhs-images`（小红书 + 微信图文通用） |
| baoyu-markdown-to-html | `baoyu-skills:baoyu-markdown-to-html` |
| baoyu-post-to-wechat | `baoyu-skills:baoyu-post-to-wechat` |

详见 memory `feedback_plugin_skill_namespace`（裸名失败时先看 system reminder 真名 + 重启，不要反向工程 settings/plugin/symlink）。

---

## 发布阶段状态看板（示例模板，一气呵成）

```text
全自动发行流水线：
- [x] 第一步 🖼️ 核心大图：结合 `baoyu-skills:baoyu-cover-image` 规约生成 `cover.png`，及 `baoyu-skills:baoyu-infographic` × **≥ 4** 生成全文贯穿信息图：开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1（详见 [layout.md 3e](layout.md)）。**必须通过 Skill 工具调用 `baoyu-skills:baoyu-infographic`，禁直接调底层 `baoyu-skills:baoyu-image-gen`**。
- [x] 第二步 🧩 组件小图：调用 `baoyu-skills:baoyu-image-gen` 强制 `--ar 1:1 --quality normal` 生成 `hero.png`（科技感导读图）。`bgm_cover.png`（主题曲封面）由 BGM 阶段 `generate_article_bgm.py` 自动生成、不在此步。这些图尺寸很小，`add_logo.js` 已内置跳过清单，不会误打水印。
- [x] 第三步 📊 数据图表：文中如果有雷达图、折线图、跑分图等需要**完全数据精确**的对比，**严禁用生图模型画**（防维度幻觉）。必须用 Python 代码（如 `matplotlib`）精确渲染出图存入 `素材/`。
- [x] 第三步 b 🎵 BGM：🔴 Claude 按 [music.md](music.md) §Claude 提炼标准 提炼诗意 theme_brief/imagery/点题歌名/选风格，传参执行 `generate_article_bgm.py --theme-brief ... --imagery ... --song-name ... --style ...`（MiniMax 自动写词 → 中文人声主题曲 + `bgm_cover.png` + 插 AUDIO-CARD；不依赖图片/Gemini）。🔴 **完成后必须跑 `pipeline.py verify bgm`（硬查 mp3 + 「本文主题曲」卡片已插入 `定稿.md`），未过不得进入第六步洗绿 / layout（MD→HTML）**——`verify_publish_assets` 把 BGM 缺失当正常放行，不会替你拦，所以这一道 verify 是 BGM 进 layout 前的唯一硬关卡。
- [x] 第四步 🖼️ 插图嵌入：将 `cover.png`（仅 frontmatter `coverImage`）+ ≥4 张 `infographic*.png`（贯穿正文：2×9:16 + ≥2×16:9）写入 `定稿.md`（BGM 卡片占位已由上一步自动插入）。**严禁手动写 `![导读图](素材/hero.png)` 或 `![](素材/bgm_cover.png)`**——hero 由导读栏自动注入、bgm_cover 由音频卡片自动注入，手动嵌会重复展示。详见 `iron-rules.md` 中 hero 唯一位置铁律。
- [x] 第五步 📄 HTML：命令行执行 `baoyu-skills:baoyu-markdown-to-html` 转化标签。
- [x] 第五步前置校验 ✋：进入第六步前必须确认 `article-meta.yaml` 的 `part_subtitles` 长度 == 文中 H2 数量。`grep -c "^## " 定稿.md` 数 H2 数，对比 yaml 配置；不匹配立即补齐 yaml 再继续。详见 [iron-rules.md · H2 副标题预填铁律](iron-rules.md)。
- [x] 第六步 🎨 洗绿：执行 `format_layout.py --all` 处理全部微信定制组件（含音乐栏自动前置——把 AUDIO-CARD 上移到导读栏下方渲染）。
- [x] 第七步 🏷️ 水印：自动批量执行 `add_logo.js 素材/*.png 截图/*.png`（**排除** hero.png 和 bgm_cover.png 等组件小图——这些尺寸太小，打水印反而影响观感）。
- [x] 第七步 b ⚖️ 压缩：执行 `python "$SKILL/scripts/compress_images.py" 素材/ --max-mb 2` 把所有 PNG 压到 ≤ 2MB（Pillow 实现、中文路径友好，保持 PNG 不转 JPEG，hero 等组件小图自动跳过）。详见 [layout.md 3h](layout.md)。
- [x] 第八步 🚀 API 发布草稿箱：调用 `baoyu-skills:baoyu-post-to-wechat` 的 wechat-api.ts，把 `定稿.html` 推送到微信公众号草稿箱（**必须显式 `--cover 素材/cover.png`** —— html 无 frontmatter，不传会报 `No cover image` 中断；作者/留言开关从 EXTEND.md 读取），返回 `media_id` 后执行 `pipeline.py done publish draft_media_id=<media_id>`（草稿箱已推送 = autopilot 终态；verify publish 认 draft_media_id 为阶段通过，正式发布后再补 wechat_url）。**禁止止步于排版** —— 排版完成不等于发布完成。
- [x] 第九步 📚 归档入库：用户手动预览 + 发布、拿到 `wechat_url` 后，执行 `pipeline.py done publish wechat_url=...`，再跑 `pipeline.py archive` 把本文写入 `<数据目录>/works.yaml`（SSOT，自动按 category 分配 code + 刷新 articles.md/看板）。**禁止止步于草稿推送** —— 草稿推送不等于发布完成、更不等于已入库。
```

---

## 交付附 `_layout-decision.md` 语义决策说明（可事后审计非事前问）

autopilot 后端零停顿，用户拿到草稿箱成品时对"为什么这么判 / 这么排"是黑盒，只能重跑、不能按点改。故 **layout 阶段（step 8 排版）结束后、交付前，在工作目录生成 `_layout-decision.md`**，把 autopilot 做过的**语义判断**记下来供事后审计：

- **文体判定**（深度 / 清单 / 教程 / 混合）→ 影响配方表选组件、配图通道、H2 切分；
- **自拟标题 / 封面主标题**及其理由（若与外标题视角错开的取舍）；
- **配图通道仲裁结果**（哪几张走 3c / 3e / 3g，为什么）；
- **要点卡 / 金句卡的落位**与数量（对照视觉层级配额）。

> **只记"模型做过语义判断"的项，确定性脚本行为（如 `--h2` 编号、洗绿）不记**，避免噪音文件。用户拿到后可**按点改**（"文体判错了、按清单文重排""封面复述了外标题、换个角度"），不必整篇重跑。契合决策看板 / 可审计偏好。
>
> ⚙️ **生成 hook 已接**：`format_layout.py --all` 末尾自动调 `write_layout_decision(cwd, meta)`，在工作目录写 `_layout-decision.md`：
> - **「一、机械事实」段**由脚本扫 `定稿.md` 自动填（H2/H3 数、要点卡数、数字卡/步骤条/对比块用量、表格数、配图数），用 `<!-- AUTO-FACTS-START/END -->` 标记包住——`--all` 多次跑只刷新此段。
> - **「二、语义决策」段**是 TODO 骨架（文体判定/自拟标题/配图仲裁/要点卡落位/组件选用理由），**由 autopilot 编排器把上面 4 项语义判断填进去**（脚本不碰、多次跑保留已填内容）。
> 即：脚本给确定性骨架 + 机械事实，autopilot 补语义理由。用户拿到后可按点改。

---

## ⚠️ 草稿推送后还有 2 件手动操作（autopilot 无法 API 化）

草稿箱推送成功只是 autopilot 的终点，**不是文章上线**。必须明确告知用户：

1. **预览 + 发布**：检查排版无误，手动点发布。
2. **归档入库**：发布完成拿到 `wechat_url` 后，执行 `pipeline.py done publish wechat_url=...`，再跑 `pipeline.py archive` 把本文写入 `<数据目录>/works.yaml`（SSOT，自动按 category 分配 code + 刷新 articles.md/看板）。

autopilot 的最后一次回复**必须**把这 2 步作为"交付清单"明确打印给用户，不能让用户以为草稿推送就完事。
