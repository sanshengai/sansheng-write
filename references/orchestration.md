# 🧭 编排器规范（orchestration）

> ✅ **2026-05-22 P1 已落地 + 混合方案定调**：fan-out 执行层就位。`orchestrator=on`（**默认**）按下方 §编排器 fan-out 实操手册执行 —— 其中 **infographic / research / review 3 个阶段并行 fan-out**（**cover 已锁定 montage-evidence 单风格、不再 fan-out**），**content_enhance 走主轴串行**（连贯性敏感、不并行，见 [content-enhance.md](content-enhance.md)）。`orchestrator=off` 走 [autopilot.md](autopilot.md) §Legacy Fallback 全串行，两者产出字节级等价。
>
> 📌 「pipeline.py 零 Agent 调用」不是缺陷 —— `pipeline.py` 是 Python 脚本本就不该有 `Agent` 调用；fan-out 的执行者是**主 Claude**，pipeline.py 只做状态记账 + verify。

> 本 skill fan-out 重构的**单一编排权威**。本文件定义主 agent（编排器）如何对
> research / infographic / review 三个 fan-out 阶段构造上下文、并行派发
> subagent、收齐验证、失败自纠偏与留痕（cover 锁定 montage-evidence 单风格不 fan-out；
> content_enhance 走主轴串行，见 [content-enhance.md](content-enhance.md)）。
>
> 机器可校验对齐源：`scripts/contracts.py`
> （`_BUNDLE_REQUIRED` ← 本文「上下文 bundle 模板」；
>  `_OUTPUT_SCHEMA` ← 配套 [agent-contracts.md](agent-contracts.md)）。
> 失败语义对齐源：[autopilot.md](autopilot.md) §失败恢复 SOP、[iron-rules.md](iron-rules.md)。

---

## 编排器职责

编排器 = **主 agent，单线程**。以下职责**唯一归属编排器**，subagent 一律不得染指：

| 职责 | 说明 | 排他性 |
|---|---|---|
| 持有主轴顺序 | 选题→大纲→正文→改稿→排版→配图封面→BGM→发布 的阶段时序由编排器掌控（🔴 此处「排版」含 **.md 预检（早跑，仅扫 `定稿.md` 不渲染）**；真正的 MD→HTML 渲染在末段 layout 阶段，**配图封面 / BGM 先于该渲染**——以 `pipeline.py` STAGE_ORDER = outline→writing→cover→infographic→bgm→layout→logo→publish→archive 为准） | subagent 不感知全局时序，只做被派发的单元 |
| 持有铁律 | [iron-rules.md](iron-rules.md) 全集的解释权与裁剪权（向 subagent 下发**子集**） | subagent 不读全集，只收 bundle 内 `iron_rules` 子集 |
| 持有 sansheng-context | 品牌身份/人设/风格路由摘要的唯一来源（从 profile 读取） | subagent 不自行重建品牌设定，只用 bundle 内 `sansheng_context` |
| 单一状态写者 | **唯一读写** `pipeline.py` / `.state.json` | subagent **绝不**触碰 `.state.json`，也不调 `pipeline.py` |
| 失败自纠偏循环 | 唯一拥有「按错误建议恢复 → 就地重派 → 连错 3 次回报」的控制循环 | subagent 失败如实回传现场，**不自行 skip、不自行重试到放弃** |
| 验证门 | 收齐 subagent 产物后调 `scripts/contracts.py:validate_output` 校验 + 落盘留痕 | subagent 不自校验 schema，由编排器统一把关 |

**铁律**：状态机（`.state.json`）有且只有一个写者。任何 fan-out 设计若让 subagent 写状态，
即违反本规范，直接判不合规。

---

## 上下文 bundle 模板

编排器对每个 fan-out 阶段构造一个「上下文 bundle」字典，**四键缺一不可**，
与 `scripts/contracts.py` 的 `_BUNDLE_REQUIRED` **逐字一致**：

```python
_BUNDLE_REQUIRED = ("sansheng_context", "iron_rules", "article_meta", "stage_input")
```

模板（YAML 形态，便于人读；运行期以 `dict` 传递）：

```yaml
sansheng_context:        # 品牌身份 / 人设 / 风格路由摘要（摘要，非全文转储；从 profile/context.md + profile/brand.yaml 读取）
  brand: "<你的品牌名>"
  persona: "<你的人设，如：理性又有温度的主笔>"
  style_route: "深度安利文 / 转发文 / 教学文 中本阶段命中的那一路摘要"
  voice_dna: ["破折号用 --", "不写引导句", "表格优先于散文", "…该阶段相关的风格约束"]

iron_rules:              # 该阶段相关铁律【子集】，非空 list（contracts 强校验）
  - "生图后端铁律：严禁 Agent 原生 generate_image / imagine"
  - "H2 只写纯标题铁律：禁止手写 PART NN｜ 前缀"
  - "…仅裁剪与本阶段相关的若干条，不下发全集"

article_meta:            # article-meta.yaml 的内容（原样字典）
  title: "文章定标题"
  slug: "42-anysearch"
  dir: "<数据目录>/42-anysearch"
  part_subtitles: ["…", "…"]
  # …article-meta.yaml 其余字段原样带入

stage_input:             # 该阶段输入产物（随 stage 不同而不同）
  # research:        大纲 / 调研 query 列表
  # content_enhance: 初稿正文 / 待增强片段
  # infographic:     已确认的配图 prompt + 数据表
  # cover:           标题 + 风格路由 + 封面文案要点
  # review:          定稿全文 + 审稿维度清单
  ...
```

四键含义（**与 `validate_bundle` 的语义对齐**）：

| 键 | 含义 | contracts 强约束 |
|---|---|---|
| `sansheng_context` | 品牌身份/人设/风格路由摘要。让 subagent 不脱离品牌调性 | 必须存在（缺键 → `bundle missing keys`） |
| `iron_rules` | 该阶段相关铁律子集，**非空 list** | 缺键或非 list 或空 list → `ContractError: iron_rules must be non-empty list` |
| `article_meta` | `article-meta.yaml` 内容（原样带入，subagent 据此定位文章目录与元信息） | 必须存在 |
| `stage_input` | 该阶段输入产物（大纲/定稿片段/配图 prompt/审稿维度等） | 必须存在 |

> `validate_bundle(bundle)` 在派发前由编排器调用；任一键缺失或 `iron_rules` 空 → 抛
> `ContractError`，**禁止带病派发**，先补齐 bundle 再派。

---

## 派发协议

编排器与 fan-out subagent 的交互**严格单向收敛**：

1. **构造**：编排器对该 fan-out 阶段组装上述四键 bundle。
2. **自校验**：调 `validate_bundle(bundle)` —— 不通过即停，先补 bundle，不带病派发。
3. **并行派发**：把 bundle 派发给一个或多个 subagent（同阶段多单元可并行，如 infographic 多张图、review 多审稿角色）。
4. **subagent 边界约束**（硬规则，违反即判不合规）：
   - 只返回**结构化产物**（对齐 [agent-contracts.md](agent-contracts.md) 各阶段「输出 schema」）。
   - **不碰 `.state.json`**、不调 `pipeline.py`。
   - **不自行 skip**、不把失败吞掉。
   - 失败时**如实回传现场**：错误原因 + 已执行到哪一步 + 可复现的输入快照，交回编排器决策。
5. **收齐**：编排器等待该阶段全部派发单元返回（含失败回传），再进入验证门。

subagent 是**无状态执行器**：它不知道全局主轴，不知道前后阶段，只对「这个 bundle」负责产出「这个 schema」。

---

## 🛠 编排器 fan-out 实操手册（P1 落地）

> 2026-05-22 P1 落地。上方「派发协议」是**抽象契约**，本节是**主 Claude 照着做的具体操作序列**。
>
> 🔴 **认知前提**：本 skill 的「编排器」就是**执行 skill 的主 Claude 自己**。fan-out 不是 `pipeline.py` 写调度代码（Python 脚本无法 spawn Claude subagent），而是**主 Claude 用 `Agent` 工具并行派发**。`pipeline.py` 的角色始终只是状态记账 + verify，不变。

### 真并行的唯一技术关键

**N 个 `Agent` 工具调用必须放在同一条消息里一次性发出。** 分多条消息发 = 串行，等于没并行。这跟「同一消息里发多个独立工具调用」是同一个机制。

### 通用 fan-out 执行序列（7 步，所有 fan-out 阶段通用）

1. **判 orchestrator 开关**：读 `.state.json` 的 `orchestrator` 字段。`on`（默认）→ 继续本手册。`off` → 走 [autopilot.md](autopilot.md) §Legacy Fallback 全串行，不执行本手册。
2. **构造 bundle**：按上文「上下文 bundle 模板」组装四键（`sansheng_context` / `iron_rules` / `article_meta` / `stage_input`）。`iron_rules` 只裁本阶段相关子集。
3. **自校验 bundle**：
   ```bash
   python -c "import sys; sys.path.insert(0,'<skill>/scripts'); import contracts; contracts.validate_bundle(BUNDLE_DICT)"
   ```
   抛 `ContractError` → 先补 bundle，不带病派发。
4. **拆分派发单元**：把 `stage_input` 按本阶段特化规则（见下表）拆成 N 个独立单元。
5. **🔴 一条消息发 N 个 `Agent`**：在**单条回复**里写 N 个 `Agent` 工具调用，`subagent_type` 见特化表，每个 prompt 用下方模板填入「bundle 四键 + 该单元的 stage_input 分片」。N 个 Agent 并行跑。
6. **收齐 + 验证门（🔴 不可省的硬步骤）**：等所有 subagent 返回（含失败回传），逐单元过验证门（见下方「验证门」章节：`validate_output` + 铁律 + 落盘），整集再调 `verify_<stage>_set`。**这两道门不由 `pipeline.py` 自动触发，纯靠主 Claude 自觉**——`research` / `review` / `content_enhance` 三阶段更连 `pipeline.py verify` 子命令都没有，漏调即裸奔，所以本步是写死的硬纪律、绝不可跳。
7. **失败重派**：任一单元不过 → 按「失败语义」就地重派该单元（不是整阶段重来），连错 3 次才回报用户。

### subagent prompt 模板

每个 fan-out subagent 的 prompt 必须自包含（subagent 无主轴上下文）：

```
你是本 skill 编排器派发的 <stage> fan-out 单元。只产出结构化结果，不碰 .state.json、不调 pipeline.py、不自行 skip。

## 品牌上下文（sansheng_context）
<bundle.sansheng_context 摘要>

## 本阶段铁律（iron_rules，必须全部遵守）
<bundle.iron_rules 子集逐条>

## 文章元信息（article_meta）
<bundle.article_meta>

## 你这个单元的任务（stage_input 分片）
<该单元分到的具体输入：1 张图的 prompt / 1 个调研 query / 1 种封面风格 ...>

## 产出要求
严格按 agent-contracts.md §<stage>「输出 schema」返回结构化结果。
失败不要吞错——如实回传：错误原因 + 执行到哪步 + 可复现输入。
```

### 4 阶段特化表（fan-out 阶段；content_enhance 不在内 —— 走主轴串行，见表下注）

| 阶段 | 拆分单元 | subagent_type | 并行数 | 主轴自做的步骤（绝不外派） |
|---|---|---|---|---|
| **infographic** | 每张图 1 个单元（按 `素材/infographic/batch.json` 的 N 个 prompt） | general-purpose | N（≥4） | 无(收齐验证即可) |
| **cover** | 🔴 **封面锁定 `montage-evidence`**：单风格生成，**不 fan-out、不自动选优**。**「每风格 1 单元 + 近 3 篇回避选优」机制已删除。** 仅 `article-meta.yaml` 显式填其他 `cover_style` 时改生成那一种**指定**风格（仍单张、无回避）。详见 [cover-styles.md](cover-styles.md) 顶部 override 段 / [iron-rules.md](iron-rules.md) 封面风格固化铁律 | general-purpose | 1（锁定单风格） | 无（按 montage-evidence 直接生成） |
| **research** | 按信源类型/query 分桶，每桶 1 个单元 | general-purpose（可用 Explore 做纯检索） | 桶数 | 无 |
| **review** | 每审稿角色 1 个单元（风格审/铁律审/事实核查） | general-purpose | 3 | **汇总裁决**：合并 issues / 消冲突 / 应用 fixes |
| **冷读外审**（🔴 2026-06-10 新增，**非 opt-in，每篇必跑**） | 固定 1 个单元：首读读者冷读 定稿.md → `_stutter-list.md`（排版前置硬门）。🔴 **上下文隔离铁律**：bundle **只含定稿正文**——不给大纲/seed/_prep-context/会话历史，隔离即价值（带上下文 = 自审 = 盲目自信）。契约见 [writing.md §磨 第 6 步](writing.md) | general-purpose | 1 | **修复应用**：按 _stutter-list 逐处修复（语流第一），subagent 只标注不改稿 |

> **content_enhance 不并行**（2026-05-22 混合方案）：4 套增强策略由编排器主轴**依次串行**执行，不拆 subagent。理由 —— 4 策略需互相呼应、共用一套嗓音，拆散再 merge 有连贯性折损风险。详见 [content-enhance.md](content-enhance.md)。`verify_content_enhance_set` 仍对串行产出的 4 策略集合做 tier-2 校验。

> 🔴 **主轴自做步骤的铁律**：cover 选优 / content_enhance 合并 / review 汇总裁决，**编排器主轴自己做，绝不外派 subagent**——这三件事需要全局视野与最终裁量权，外派会丢上下文且违反单一状态写者精神。详见 [agent-contracts.md](agent-contracts.md) 对应章节。
>
> 🔴 **review 是 opt-in**：审稿 team 默认不强开，编排器判本篇显著受益 → 提议用户 → 确认后才 fan-out（遵守 memory `feedback_agent_teams_propose`）。

### 与 Legacy 串行的等价保证

`orchestrator=off` 时**完全不执行本手册**，走 [autopilot.md](autopilot.md) §Legacy Fallback——每个 fan-out 阶段由主 Claude 自己串行做（自己一张张画图、自己写四策略）。产出与 `orchestrator=on` 字节级等价，只是没有并行加速。两条路任何时候都可切换。

---

## 验证门

> 🔴 **验证门不是 `pipeline.py` 自动触发的硬门**：`verify_<stage>_set` / `validate_output` / `validate_bundle` 这些函数**不由 `pipeline.py` 在阶段推进时自动调用** —— 它们是**主 Claude（编排器）按本手册手动调用**的纪律门。`pipeline.py` 只做 `.state.json` 记账与各 `verify <stage>` 子命令的产物文件断言；唯一机器化的回归保障是 `pytest tests/test_contracts.py` 与 `regression_baseline.py` 对合成 fixture 的断言。别误以为这些 verify 门会像 `pipeline.py verify writing` 那样被自动跑。

> 🔴 **fan-out 收齐后必调 `verify_<stage>_set` 是不可省的硬纪律（非 `pipeline.py` 自动触发，纯靠主 Claude 自觉，所以更要写死在执行序列里）**：`research` / `review` / `content_enhance` 三个 fan-out 语义阶段**不在 STAGE_ORDER 内**（STAGE_ORDER 只有 outline/writing/cover/infographic/bgm/layout/logo/publish/archive 九阶段有 `pipeline.py verify` 子命令），因此它们**没有任何 `pipeline.py` 机器兜底** —— 一旦主 Claude 漏调 `verify_<stage>_set` / `validate_output`，劣质产物（调研信源不足 / 审稿没真跑 / 增强策略缺失）会**无机器告警地静默并入主轴**。所以收齐后过双门（逐单元 `validate_output` + 整集 `verify_<stage>_set`）是**执行序列里写死的硬步骤，不是可选优化**，下方通用 fan-out 执行序列第 6 步与特化表均据此标注。

### MD→HTML 前的强制纪律门清单（layout 阶段前必过）

> 🔴 进入 layout（MD→HTML + `format_layout.py --all` 渲染）**之前**，编排器必须逐项过下列纪律门——它们同样**不由 `pipeline.py` 自动触发**，靠编排器自觉，因此集中列死在此：

| 门 | 命令 / 校验 | 不过的后果 |
|---|---|---|
| **BGM 硬存在门** | `pipeline.py verify bgm`（硬查 mp3 + 「本文主题曲」AUDIO-CARD 已插入 `定稿.md`） | `verify_publish_assets` 把 BGM 缺失视为正常放行、不会替你拦；漏跑此门 = 主题曲卡片可能整篇缺失却照样进 layout / 发布 |
| **fan-out 集合门** | 各 fan-out 阶段收齐后的 `verify_<stage>_set`（infographic 构成/张数、research/review/content_enhance 产物完整性） | 漏调即劣质产物静默并入主轴（见上方红字） |
| **事实复核门**（🔴 2026-07-02 C13） | 排版 preflight 断言 `_fact-check.md` 存在（与冷读外审门同构，缺失 `exit 2`） | 无此门则定稿的数字/版本/价格/时间错误无对外核验兜底、直接滑到草稿箱（冷读只查内部一致性、不核外部真伪；契约见 [fact-check.md](fact-check.md)） |

编排器收齐某 fan-out 阶段全部产物后，逐单元过验证门：

```python
import scripts.contracts as c
c.validate_output(stage, payload)   # stage ∈ research/content_enhance/infographic/cover/review
```

验证门三关，全过才算该单元合格：

1. **schema 校验**：`validate_output(stage, payload)` —— 必需键齐全 + 类型匹配
   （键缺失 → `[stage] output missing key: …`；类型错 → `[stage] key X expected …`）。
   各 stage 期望键见 [agent-contracts.md](agent-contracts.md)，与 `_OUTPUT_SCHEMA` 逐字对齐。
2. **铁律合规**：产物是否违反本阶段下发的 `iron_rules` 子集
   （如 cover 必须 2.35:1、infographic 数值图必须本地脚本渲染而非大模型生图 —— 见 [iron-rules.md](iron-rules.md)）。
3. **落盘留痕**：把该边界产物写入「留痕路径约定」规定的可追溯位置。

**任一关不通过 → 就地重派该单元**（不是整阶段重来，是失败的那个单元），
进入下方「失败语义」的自纠偏循环。

---

## 失败语义（连错3次/禁止skip）

完全对齐 [autopilot.md](autopilot.md) §失败恢复 SOP（硬规则）与
[iron-rules.md](iron-rules.md)：

- **禁止用 `pipeline.py skip` 绕过**任何 fan-out 单元的失败。
- 按错误信息给的建议**自主恢复**：重试 / 换风格 / 修文件 / 调参数
  （例：cover 比例错 → 按 montage-evidence 重生图；infographic 数值图被大模型生图 → 改本地 matplotlib 脚本重渲；research 信源不足 → 扩 query 重调研）。
- **同一阶段（同一单元）连错 3 次才回报用户**，期间编排器自主决策恢复路径，不打断用户。
- 回报时**必须带三要素**：① 阶段名 ② 失败原因（含验证门是哪一关挂的）③ 已尝试的恢复方式（逐次列出）。
- subagent 端：失败**不自行 skip、不静默吞错**，如实回传现场给编排器，由编排器的自纠偏循环统一处置（subagent 无权决定放弃）。

计数口径：连错计数按「同一 stage 的同一派发单元」累计；换了恢复策略重派仍计入同一计数，第 3 次仍挂才回报。

---

## 留痕路径约定

每个 fan-out 边界产物**落盘到文章目录下可追溯位置**，便于失败现场复盘
（参照 AnySearch 基准 `bench/` 全量留档同种做法：每次边界产出都留档，不只留最终态）。

文章目录根 = `article_meta.dir`（如 `<数据目录>/42-anysearch/`）。约定：

| 阶段 | 留痕路径（相对文章目录） | 形态 |
|---|---|---|
| research | `素材/research/*.json` | 每次调研一份 JSON（含 findings + sources）。🔴 **必落（2026-07-02）**：prep_writing.py「一·据」节消费它注入写作上下文，不落盘写作 agent 拿不到带信源事实底座 |
| content_enhance | `素材/enhance/strategies.json` | 四策略产物（angle/density/detail/texture） |
| infographic | `素材/*.png` + `素材/infographic/*.json` + 数值图 `素材/*.py` | 图本体 + 产物清单 JSON + 可复核渲染脚本 |
| cover | `素材/cover.png`（锁定 montage-evidence 单张） | 单风格直接生成，无多候选打样 |
| review | `素材/review/verdicts.json` | 各审稿角色 verdict 汇总 |

通用规则：

- **边界产物全留**，不只留最终选定的那一份（打样的废稿、被否的策略也留，供复盘）。
- 失败单元的现场（出错输入快照 + 错误原因）一并落盘到对应阶段目录，便于回报与回放。
- 留痕由**编排器在验证门第 3 关统一写入**，subagent 不直接写文章目录状态相关文件（仅产出产物交回）。
