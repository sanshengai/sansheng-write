# 📜 Fan-out 阶段契约（agent-contracts）

> 五个阶段（research / content_enhance / infographic / cover / review）的
> **进出契约**。编排器据此构造 bundle、subagent 据此产出、验证门据此校验。
>
> ⚠️ **2026-05-22 混合方案**：其中 **content_enhance 改走主轴串行**（不 fan-out，见
> [content-enhance.md](content-enhance.md)），其余 4 个为 fan-out 阶段。content_enhance
> 的进出契约（输出 schema + `verify_content_enhance_set`）**不变**——契约与执行拓扑无关，
> 4 策略无论串行还是并行产出，都过同一套校验。
>
> 机器可校验对齐源：`scripts/contracts.py` 的 `_OUTPUT_SCHEMA`。
> 每节「输出 schema」与对应 stage 的 `_OUTPUT_SCHEMA` 条目**字段逐一对齐**：
>
> ```python
> _OUTPUT_SCHEMA = {
>     "research":        {"findings": list, "sources": list},
>     "content_enhance": {"strategies": dict},          # {angle,density,detail,texture}
>     "infographic":     {"images": list},              # [{path,aspect,bytes}]
>     "cover":           {"candidates": list, "selected": str},
>     "review":          {"verdicts": list},            # [{role,issues,pass}]
> }
> ```
>
> 通用约束（所有阶段）：
> - 输入 bundle 恒为四键 —— 模板与每键含义详见 [orchestration.md](orchestration.md) §上下文 bundle 模板。
> - subagent 边界行为（只返回结构化产物 / 不碰 `.state.json` / 不 skip / 失败如实回传现场）—— 详见 [orchestration.md](orchestration.md) §派发协议 / §失败语义。
> - 类型不符 / 必需键缺失 → 验证门抛 `ContractError`，就地重派 —— 详见 [orchestration.md](orchestration.md) §失败语义。

---

## ⚠️ 校验层级总纲（先读，三层不可混）

本文件出现的所有 schema/字段约束分三层，**强制力不同，不要混排**：

1. **机器强制（`validate_output` 当前实测行为）** = **仅顶层键存在 + 顶层类型**。
   `scripts/contracts.py:validate_output` 现状只做 `_OUTPUT_SCHEMA[stage]` 的
   「顶层键齐全 + `isinstance(payload[key], typ)`」。除此之外**没有任何**机器强制。
   本文档中此类条目统一标注 **`(validate_output 强校验)`**。
   **（P1.1 起）infographic `images` 每项 `path`/`aspect` 非空 str、`bytes`
   严格 int（排除 bool）已升 tier-1**：由 `validate_output("infographic",...)`
   经 `_validate_infographic_items()` 机器强制（结构层）。
   **（P2.1 起）research `sources` 每项必须 dict 且含非空 str `url` 已升
   tier-1**：由 `validate_output("research",...)` 经
   `_validate_research_items()` 机器强制（结构层）。
   **（P3.1 起）content_enhance `strategies` 含且仅 4 键
   angle/density/detail/texture 且值非空 str 已升 tier-1**：由
   `validate_output("content_enhance",...)` 经 `_validate_content_enhance()`
   机器强制（结构层）。
   **（P4.1 起）cover `candidates` 每项必须 dict 且含非空 str `path`、
   `selected` 非空 str 已升 tier-1**：由 `validate_output("cover",...)` 经
   `_validate_cover()` 机器强制（结构层；**`selected ∈ candidates` 是跨字段
   = tier-2，不在结构契约**）。
   **（P5.1 起）review `verdicts` 每项必须 dict 且含非空 str `role`、list
   `issues`、严格 bool `pass`（排除 int —— 与 `infographic.bytes` 排除 bool
   互为镜像）已升 tier-1**：由 `validate_output("review",...)` 经
   `_validate_review_items()` 机器强制（结构层；**issues 质量 / role 合法性
   / 裁决一致性 / H2·段落 delta = tier-2，不在结构契约**）。此类条目标注
   **`(validate_output 强校验)`**。
2. **语义关 / 铁律关（验证门人为/编排器侧校验，非现状机器强制）** = 业务范围、
   跨字段、铁律合规约束。例：cover `selected ∈ candidates`、research 数字类
   finding 须有官网级 source。**infographic 的 `aspect` 取值集合
   (9:16/16:9/1:1)、张数 ≥4、压缩后 ≤2MB、开篇 9:16×1 + 中间 16:9×≥2 +
   结尾 9:16×1 构成**——这些是 tier-2 语义关，**仅由 P1.2 验证门对
   _新生成_ 信息图强制，不对历史冻结 baseline 追溯**（结构契约只管类型/非空，
   不塞枚举/计数/尺寸，否则污染契约且与本总纲自相矛盾）。这些**当前不由
   `_OUTPUT_SCHEMA` 自动校验**，由验证门铁律关 / 编排器侧逻辑把关，并按 plan
   后续 Phase **按需逐步**加进编排器校验代码。本文档中此类条目统一标注
   **`(语义关/非 schema 强制)`**。
3. **示例 JSON 中的字段名 = 建议契约**，不是机器约束。
   下文每节示例 JSON 里 `confidence`/`tier`/`style`/`diagnosis` 等字段名是
   subagent 产出建议形态；**任何把它升级为机器校验的改动，必须显式修改
   `scripts/contracts.py` 的 `_OUTPUT_SCHEMA`（或编排器校验代码）并同步更新本文档**，
   不允许「文档写了就当强制」。

> **🪤 bool/int 陷阱（防 P1.1 踩坑）**：Python `isinstance(True, int) == True`
> ——`bool` 是 `int` 子类。`infographic.bytes`(int) 与 `review` 每项 `pass`(bool)
> 并排，极易诱导出「统一一套 `isinstance(v,int)`」的偷懒写法，导致 `pass=True`
> 被误判为合法 int、或 `bytes=False` 蒙混过关。**后续给 `contracts.py` 加任何
> item 级 int 校验时，必须显式排除 bool**，写成
> `isinstance(v, int) and not isinstance(v, bool)`；校验 bool 字段时也不要复用 int 分支。

---

## research

大纲调研：为大纲/正文补事实、信源、数据支撑。

**选引擎：一个 query 只走一个引擎，不同题并行撒网**（三家搜同一题返回高度重复，只烧上下文）。

| 调研意图 | 引擎 | 备注 |
| --- | --- | --- |
| 选题背景、人物、公司、财经社会类 | AnySearch | 中文相关性最好 |
| 要可引用的原文段落 / 大段素材 | `doubao_search` | 直接返网页正文，**`Count` 压到 3–5**（10 条≈2 万字） |
| 技术选型、GitHub、英文技术 | Tavily | 此类 AnySearch 会退化成代码检索 |
| 工商、股权、实缴、财务、司法风险 | `datapro_search` | **须给工商全称或统一社会信用代码**；字段缺失 ≠ 0 |
| 已知 URL 的公众号正文 | `baoyu-url-to-markdown` | 其他工具会撞反爬假页面 |

一篇文章典型 3–6 次搜索足够；调研完先与用户对一轮角度再动笔（见 [autopilot.md](autopilot.md) blueprint 闸门）。

### 输入 bundle

- `sansheng_context`：品牌调性 + 命中风格路由摘要（决定调研深度与角度取向）。
- `iron_rules`：信源相关铁律子集（如「模型版本号/价格/时间必须官网第一信源 + 权威媒体交叉核对」「不确定标注待核实」）。
- `article_meta`：`article-meta.yaml` 内容（定位文章目录、标题、slug）。
- `stage_input`：大纲骨架 + 待调研 query 列表 / 论点清单。

### 输出 schema

对齐 `_OUTPUT_SCHEMA["research"] = {"findings": list, "sources": list}`：

```json
{
  "findings": [
    {"claim": "论点/事实陈述", "support": "证据摘要", "confidence": "high|need_verify"}
  ],
  "sources": [
    {"title": "信源标题", "url": "https://…", "tier": "官网|权威媒体|学术|社区", "accessed": "2026-05-19"}
  ]
}
```

- `findings`：**list**（`validate_output` 强校验）。每项一条调研结论；**finding item 结构（`claim`/`support`/`confidence`）属 tier-2 语义关**，由 P2.2 验证门对新产出强制，**不入结构契约**（裸 str / 缺 claim 的项契约层放行）`(语义关/非 schema 强制)`。无法确认的显式标 `need_verify` `(语义关/非 schema 强制)`。
- `sources`：**list**（`validate_output` 强校验）。**（P2.1 起）每项 item 级
  必须 dict 且含非空 str `url` = tier-1 结构强校验**，由
  `validate_output("research",...)` → `_validate_research_items()` 机器强制
  `(validate_output 强校验)`。每条的 `title` / `tier` 分级 / `accessed`、
  「数字/版本/价格类 finding 必须含官网级信源对应」= **tier-2 语义关**，
  由 P2.2 验证门对 _新产出_ 强制，**不对历史冻结 golden 追溯**
  （结构契约只校验 `url` 存在且非空，不查 tier/title/accessed/官网级语义）
  `(语义关/非 schema 强制)`。

### tier-2 语义门：`verify_research_set`（P2.2，仅对 fan-out 新产出强制）

> 与 tier-1 结构契约 `validate_output("research",...)` **分开**，与
> `verify_infographic_set` **并列同构**。**故意不写进 `_OUTPUT_SCHEMA` /
> `validate_output`**（塞进去会污染契约且与本文件「校验层级总纲」自相矛盾——
> tier-1 只校验 `sources[].url` 结构）。由编排器在 research fan-out 收齐后、
> 对**合并后的新产出集合**单独调 `scripts/contracts.py:verify_research_set(findings, sources)`
> 把关；返回 `list[str]`（每条带定位 `findings[i]`/`sources[i]` + 规则名），
> 空 list = 通过。纯函数：只读入参 dict，不读磁盘/网络/状态，异常转结构化原因不裸崩。

**规则清单（与上方验证清单 tier-2 项一一对应）：**

| # | 规则 | 判据 |
|---|------|------|
| ① | `findings` 非空且每条有实质 `support` | 每项须 dict，`claim`/`support` 均非空 str（裸 str / 缺 claim / 空 support 判违规） |
| ② | `sources` 去重后 ≥ **3** | 去重按 url 归一化（去协议/末尾斜杠/查询锚点/小写 host）防换 http·加 `?` 凑数。**N=3 依据**：步骤 5 要求多渠道（行业报告/科技媒体/学术/竞品/官方），全局铁律要求官网第一信源 + 权威媒体交叉核对（≥2 档），取 3 = 官网 + 权威媒体 + 第三方交叉的最小可信三角 |
| ③ | 版本/价格/日期类 finding 至少 1 条**官网级** source 兜底 | finding 文本命中版本/价格/日期触发词时，全集须含 ≥1 官网级 source。**官网级启发式**：`tier == "官网"`，或 url host 带官方前缀（`docs./developer./blog./help.`）/ 路径含 `/blog\|/news\|/release\|/pricing\|/changelog` 等，且 host **不属**社媒/UGC 聚合域（zhihu/weibo/xiaohongshu/csdn/36kr/medium 等二手转述不算官网级）。判不准倾向报违规（让编排器补官网源），不放水——呼应铁律「版本/价格/时间须官网第一信源核实、无法确认标待核实」 |
| ④ | `sources` 每条 url 非空 + 域名基本合法 | tier-1 已保底 url 存在非空，tier-2 复检 + 要求能解析出含点的合法 host |

**强制范围**：**仅对 P2.2 fan-out 新产出强制，不追溯历史冻结 golden**
（历史 3 篇大纲/research 各异、字段形态不统一，有的根本没 research 目录——
追溯它们=误判门，与 `verify_infographic_set` 同理）。一致性等价 **exit 0**：
机制由 `regression_baseline.py` P2 门 (c) 段 + `pytest tests/test_contracts.py`
共用同一套合成 fixture（`tests/golden/_synthetic_research/make_fixtures.py`）
断言——合规组返回空、各违规组精确报对应规则，单一事实源、hermetic、
不烧 AnySearch/Tavily 检索配额（真实端到端调研延 P6/人工）。

### 验证清单

- [ ] `findings` / `sources` 均为 list（`validate_output` 强校验）。
- [ ] `sources` 每项是 dict 且 `url` 为非空 str `(validate_output 强校验：P2.1 起 _validate_research_items() 机器强制)`。
- [ ] `findings` 非空、每项含 `claim`/`support`/`confidence` `(语义关/非 schema 强制：P2.2 verify_research_set 规则① 对新产出把关，不追溯历史 baseline)`。
- [ ] 涉及版本号/价格/时间的 finding 至少 1 条官网级 source 对应、source 带 `tier`/`title`/`accessed` `(语义关/非 schema 强制：P2.2 verify_research_set 规则③，不追溯历史冻结)`。
- [ ] `sources` 去重后 ≥3 条（多渠道交叉，非单点臆断）`(语义关/非 schema 强制：P2.2 verify_research_set 规则②)`。
- [ ] 无法确认项已标 `need_verify`，未硬给数字 `(语义关/非 schema 强制；铁律：信息无法确认显式标注待核实)`。
- [ ] 🔴 产物落盘 `素材/research/*.json`（**2026-07-02 升格为必做**：`prep_writing.py` 的「一·据 事实数据清单」节直接读它注入 `_prep-context.md`，不落盘 = 写作 agent 拿不到带信源的事实底座、只能凭大纲转述）`([orchestration.md](orchestration.md) §留痕路径约定)`。

---

## content_enhance

内容增强：对初稿做四策略加工（角度 / 密度 / 细节 / 质感）。

> 🔧 **执行拓扑：主轴串行（不 fan-out）**。2026-05-22 混合方案定调——4 策略由编排器
> 主轴依次串行执行，不拆 subagent（4 策略需互相呼应、共用嗓音，拆散再 merge 有连贯性
> 折损风险）。本节描述的「输入 bundle / 输出 schema / `verify_content_enhance_set`」
> **全部不变**：契约与拓扑无关。下文凡出现「fan-out 收齐」字样，按「主轴串行产出」理解。

### 输入 bundle

- `sansheng_context`：人设 voice DNA + 风格路由（决定增强方向不脱品牌调性）。
- `iron_rules`：行文铁律子集（破折号用 `--`、不写引导句、表格优先、无尾部总结等）。
- `article_meta`：文章元信息。
- `stage_input`：初稿正文 / 待增强片段 + 增强目标说明。

### 输出 schema

对齐 `_OUTPUT_SCHEMA["content_enhance"] = {"strategies": dict}`，
`strategies` **dict 必含四键** `angle / density / detail / texture`：

```json
{
  "strategies": {
    "angle":   {"diagnosis": "原稿角度问题", "rewrite": "调整后角度/切入"},
    "density":  {"diagnosis": "信息密度问题", "rewrite": "增删后的密度处理"},
    "detail":  {"diagnosis": "细节缺失点",   "rewrite": "补入的具体细节"},
    "texture": {"diagnosis": "语言质感问题", "rewrite": "质感打磨后的文本"}
  }
}
```

- `strategies`：**dict**（`validate_output` 强校验）。**（P3.1 起）dict
  必含且仅含四键 `angle`/`density`/`detail`/`texture`，每个值为非空 str
  = tier-1 结构强校验**，由 `validate_output("content_enhance",...)` →
  `_validate_content_enhance()` 机器强制 `(validate_output 强校验)`。
- 各策略文本的**质量 / 去重 / 不矛盾 / 与正文融合**、是否套话、长度是否
  合理 = **tier-2 语义关**，**由 P3.2 合并关/语义门对 _新产出_ 强制，不对
  历史冻结 baseline 追溯**（历史文章无统一 content_enhance 产物；结构契约
  不塞文本质量/语义判定）`(语义关/非 schema 强制)`。

### tier-2 语义门：`verify_content_enhance_set`（P3.2，仅对新产出强制）

> 与 tier-1 结构契约 `validate_output("content_enhance",...)` **分开**，与
> `verify_infographic_set` / `verify_research_set` **并列同构**。**故意不写进
> `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与本文件
> 「校验层级总纲」自相矛盾——tier-1 只校验 strategies 4 键齐全/仅认/值非空
> str，见 `_validate_content_enhance`）。由编排器在 content_enhance 主轴串行
> **产出 + 合并关之后**、对**合并后的新产出**单独调
> `scripts/contracts.py:verify_content_enhance_set(strategies, article_body=None)`
> 把关；返回 `list[str]`（每条带定位 `[strategy 名]` + 规则名），空 list =
> 通过。纯函数：只读入参（不读磁盘/网络/状态），异常转结构化原因不裸崩。
> 校验面以模块级 `_CE_STRATEGY_KEYS`（`angle/density/detail/texture`）为
> **单一事实源**，不重抄 4 键硬编码（与 SOP 派发列表同源，防双写漂移）。

> 🔴 **合并关由编排器主轴自做、绝不外派 subagent**：四策略主轴串行产出后，
> 编排器**主轴自己**完成「两两去重 / 消矛盾 / 统一嗓音 / 与正文融合」的
> 合并（plan 须明确「此步主轴自做不外派」），**不派任何 subagent 做合并**
> （合并需要全局视野与最终裁量权，属编排器主轴职责，外派会丢上下文且违反
> 单一状态写者精神）。`verify_content_enhance_set` 是合并**之后**对合并产物
> 的机器化把关，不是合并本身。

**规则清单（与下方验证清单 tier-2 项一一对应）：**

| # | 规则 | 判据 |
|---|------|------|
| ① | 四策略文本两两**去重**（无大段雷同/复制粘贴） | 归一化（去空白/标点/小写）后：两文「归一化全等」或「最长公共连续子串 ÷ 较短文本长度 ≥ **0.65**」即判雷同。**0.65 依据**：四策略各司其职（角度/密度/细节/质感），增强说明常共享选题名/术语等公共片段，0.5 会误判正常用词重叠，0.65 要求「大段连续雷同」才报——宁严勿松但不误杀 |
| ② | 无显著**自相矛盾** | 同一策略文本内对冲词对同现（应该/不应该、保留/删除、增加/减少、加长/缩短、强化/弱化、更口语/更书面、keep/remove 等）视为对冲。这些词单独看未必矛盾，**判不准倾向报违规**（让编排器复核），与全门 fail-safe 取向一致 |
| ③ | 每策略**实质性**（非占位/套话/过短） | strip 后长度 < **12** 即报实质性不足；若同时命中占位/套话词（todo/tbd/待补/待定/占位/略/xxx/暂无/同上/见上 等）报更强信号。**12 依据**：低于 ~12 字符（≈中文 6 字）不可能承载一条可执行增强意见，必是占位残片；取 12 偏松只挡明显占位，不误杀「精炼但有效」短指引 |
| ④ | 与正文**非完全脱节**（给 `article_body` 时） | 策略与正文连 1 个长度≥2 的公共 token（英文/数字词 + 中文 2-gram）都没有 → 判该策略与本文无关（跑错题/套模板）。**只要 ≥1 即放行**（增强说明用元语言描述「怎么改」，未必复述正文原词，过严会误杀合规增强）。`article_body` 为 None / 空白时**本关整体跳过**（无正文可比，不臆断） |

**强制范围**：**仅对 P3.2 新产出强制，不追溯历史冻结 golden**
（历史 3 篇文章无统一 content_enhance 产物、多数根本没 `素材/enhance`
目录——追溯它们=误判门，与 `verify_infographic_set` /
`verify_research_set` 同理）。一致性等价 **exit 0**：`_OUTPUT_SCHEMA`
顶层 `content_enhance` 仍为 `{strategies: dict}` **不变**（本门不改 tier-1
契约面）；机制由 `regression_baseline.py` P3 门 (c) 段 +
`pytest tests/test_contracts.py` 共用同一套合成 fixture
（`tests/golden/_synthetic_content_enhance/make_fixtures.py`）断言——合规组
返回空、各违规组精确报对应规则，单一事实源、hermetic、不烧任何 LLM
增强配额（真实端到端 4 策略 + 编排器合并关延 P6/人工，plan carry-forward
显式登记非静默）。**依赖阈值/键集构造 fixture 前先一致性自检命中即
return**（P3.1 复审硬约束，防裸崩）。

### 验证清单

- [ ] `strategies` 是 dict（`validate_output` 强校验）。
- [ ] 四键 `angle / density / detail / texture` 全部存在（且无多余键）、每键值为非空 str `(validate_output 强校验：P3.1 起 _validate_content_enhance() 机器强制)`。
- [ ] 四策略文本两两去重，无大段雷同/复制粘贴 `(语义关/非 schema 强制：P3.2 verify_content_enhance_set 规则① dedup，对新产出把关，不追溯历史冻结)`。
- [ ] 每策略内部无显著自相矛盾（对冲措辞同现）`(语义关/非 schema 强制：P3.2 verify_content_enhance_set 规则② no_contradiction)`。
- [ ] 每键内容有实质（非占位/套话/过短），与正文有效融合不脱节 `(语义关/非 schema 强制：P3.2 verify_content_enhance_set 规则③ substantive / 规则④ not_disjoint，对新产出把关，不追溯历史冻结)`。
- [ ] 合并（去重/消矛盾/统一嗓音/与正文融合）由编排器**主轴自做、绝不外派 subagent**，`verify_content_enhance_set` 是合并后对新产出的机器化把关 `(语义关/非 schema 强制：P3.2 合并关由主轴执行)`。
- [ ] 增强后文本符合 `iron_rules` 子集（破折号 `--`、无引导句、无尾部总结）`(语义关/非 schema 强制：P3.2 合并关/语义门)`。
- [ ] 产物落盘 `素材/enhance/strategies.json` `(语义关/非 schema 强制)`。

---

## infographic

信息图：≥4 张配图打样（含数值型图表）。

### 输入 bundle

- `sansheng_context`：品牌视觉调性摘要；`claymation` 同时带 `warm-light-clay` 配方名、背景、当前主题主色与配方摘要。
- `iron_rules`：生图后端铁律子集（**严禁 Agent 原生 generate_image/imagine**；数值型图表必须 `matplotlib`/`pyecharts` 本地脚本渲染，.py 留文章目录供复核 —— 见 [image-routing.md](image-routing.md)）。
- `article_meta`：文章元信息。
- `stage_input`：已确认的配图 prompt + 数据表 / 图表规格；`claymation` 每张信息图与 Hero prompt 必须带 `pipeline.py visual-contract` 输出的四字段。

### 输出 schema

对齐 `_OUTPUT_SCHEMA["infographic"] = {"images": list}`，
`images` 每项 `{path, aspect, bytes}`：

```json
{
  "images": [
    {"path": "素材/infographic-01.png", "aspect": "16:9",  "bytes": 184320},
    {"path": "素材/chart-radar.png",    "aspect": "1:1",   "bytes": 96512}
  ]
}
```

- `images`：**list**（`validate_output` 强校验）。**（P1.1 起）每项 item 级
  `path`/`aspect` 非空 str、`bytes` 严格 int（排除 bool）= tier-1 结构强校验**，
  由 `validate_output("infographic",...)` → `_validate_infographic_items()`
  机器强制 `(validate_output 强校验)`。
- `aspect` 取值集合 (9:16 / 16:9 / 1:1)、**≥4 张**、压缩后 ≤2MB、开篇 9:16×1 +
  中间 16:9×≥2 + 结尾 9:16×1 构成 = **tier-2 语义关**，**由 P1.2 验证门对
  _新生成_ 信息图强制，不对历史冻结 baseline 追溯**（结构契约不塞枚举/计数/尺寸）
  `(语义关/非 schema 强制)`。

> **🪤 bytes 字段 bool/int 陷阱**：每项 `bytes` 是**严格整数字节数**。Python
> `isinstance(True, int) == True`（`bool` 是 `int` 子类）。P1.1 已给
> `contracts.py:_validate_infographic_items()` 加 item 级 `bytes` int 校验，
> **已显式排除 bool**，写成 `isinstance(v, int) and not isinstance(v, bool)`
> —— `bytes=True`/`False` 会被判 ContractError。详见顶部「校验层级总纲」
> §bool/int 陷阱。

### 验证清单

- [ ] `images` 是 list（`validate_output` 强校验）。
- [ ] 每项是 dict，`path`/`aspect` 非空 str、`bytes` 严格 int（排除 bool）`(validate_output 强校验：P1.1 起 _validate_infographic_items() 机器强制)`。
- [ ] `images` ≥4 项 `(语义关/非 schema 强制：P1.2 新产出验证门把关，不追溯历史 baseline)`。
- [ ] 每项 `path` 指向文章目录内真实文件、`bytes` 与磁盘实际大小一致、`aspect` ∈ {9:16,16:9,1:1} 且与图实际比例一致、压缩后 ≤2MB `(语义关/非 schema 强制：P1.2 新产出强制，不追溯历史 baseline)`。
- [ ] 数值型图表（雷达/折线/柱状/饼）均由本地脚本渲染，对应 `.py` 已留在文章目录 `(语义关/非 schema 强制；铁律，禁大模型生图)`。
- [ ] 未调用任何 Agent 原生生图（generate_image / internal_image_gen / imagine）`(语义关/非 schema 强制；铁律)`。
- [ ] `claymation` 已显式绑定 `visual_profile: warm-light-clay`；canonical prompt、gen-log、最终像素和 Hero 通过同一配方门，未混入深色/金属/高反差主视觉 `(语义关：pipeline.py _visual_route_errors 强制)`。
- [ ] 产物 + 清单落盘 `素材/*.png` 与 `素材/infographic/*.json`，渲染脚本留 `素材/*.py` `(语义关/非 schema 强制)`。

---

## cover

> 🔴 **2026-05-22 封面锁定 `montage-evidence` 单风格**：默认路径**只生成单张** `素材/cover.png`，
> 无多候选打样、无选优、无近 3 篇回避。下方多风格打样 `candidates/selected` 契约 + `verify_cover_set`
> 仅在 `article-meta.yaml` 显式填非 montage-evidence 的 `cover_style`（多候选覆盖模式）时才适用。

封面（多候选覆盖模式）：多风格打样并选定。

### 输入 bundle

- `sansheng_context`：品牌视觉调性 + 命中风格路由（决定封面风格集）。
- `iron_rules`：封面铁律子集（**2.35:1 比例**、中文文字约束、严禁 Agent 原生生图破比例 —— 见 [cover-styles.md](cover-styles.md)、[image-routing.md](image-routing.md)）。
- `article_meta`：标题等元信息。
- `stage_input`：标题 + 封面文案要点 + 候选风格清单。

### 输出 schema

对齐 `_OUTPUT_SCHEMA["cover"] = {"candidates": list, "selected": str}`：

```json
{
  "candidates": [
    {"path": "素材/cover/candidates/cinematic.png", "style": "cinematic", "aspect": "2.35:1"},
    {"path": "素材/cover/candidates/editorial.png", "style": "editorial", "aspect": "2.35:1"}
  ],
  "selected": "素材/cover/candidates/cinematic.png"
}
```

- `candidates`：**list**（`validate_output` 强校验）。**（P4.1 起）每项 item 级
  `path` 非空 str = tier-1 结构强校验**，由 `validate_output("cover",...)` →
  `_validate_cover()` 机器强制（结构层）`(validate_output 强校验)`。多风格打样
  全留、≥2 风格 = **tier-2 语义关**，由 P4.2 验证门对 _新产出_ 强制、不追溯
  历史冻结 `(语义关/非 schema 强制)`。
- `selected`：**str**（`validate_output` 强校验）。**（P4.1 起）`selected` 非空
  str = tier-1 结构强校验**，由 `validate_output("cover",...)` →
  `_validate_cover()` 机器强制（结构层）`(validate_output 强校验)`。其值须为
  某个 candidate 的 path = **跨字段 tier-2**：当前 `_OUTPUT_SCHEMA` /
  `_validate_cover()` **只**校验 selected 是非空 str，**不查是否 ∈
  candidates**（跨字段约束塞进结构契约会污染契约且与校验层级总纲自相矛盾），
  由 P4.2 验证门对 _新产出_ 强制、不追溯历史冻结 `(语义关/非 schema 强制)`。

### tier-2 语义门：`verify_cover_set`（P4.2，仅对 fan-out 新产出强制）

> 与 tier-1 结构契约 `validate_output("cover",...)` **分开**，与
> `verify_infographic_set` / `verify_research_set` /
> `verify_content_enhance_set` **并列同构**。**故意不写进
> `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与本文件
> 「校验层级总纲」自相矛盾——tier-1 只校验 candidates[].path 非空 str +
> selected 非空 str，见 `_validate_cover`；`selected ∈ candidates` /
> 磁盘 IO / 像素属 tier-2）。由编排器在 cover fan-out **收齐之后**、对
> **新产出**单独调
> `scripts/contracts.py:verify_cover_set(candidates, selected, recent_covers=None)`
> 把关；返回 `list[str]`（每条带定位 `candidates[i]` / `selected` +
> 规则名），空 list = 通过。纯函数：只读入参 + 磁盘 PNG 像素（IO），
> 不碰网络/状态，异常转结构化原因不裸崩。1K 口径**复用**
> `verify_infographic_set` 的模块级 `_K1_MIN/_K1_MAX`（=`[900,1200]`，
> 单一事实源，**不重复造规则**，见 [image-routing.md](image-routing.md)
> §1K 分辨率横切规范 / [iron-rules.md](iron-rules.md) §生图分辨率铁律）；
> 2.35:1 依据 [cover-styles.md](cover-styles.md)「不变的底层铁律」第一条
> （briefing/noir + montage 3 亚型全共享 `2.35:1`）。

> 🔴 **2026-05-22 封面锁定 `montage-evidence`：多风格 fan-out 选优 +「近 3 篇
> 回避」已废止/删除。** 默认路径只按 montage-evidence 生成单张 `素材/cover.png`，
> 无候选集合、无选优、无风格回避。`verify_cover_set` 仅在显式多候选覆盖模式下
> 才被调用（候选集合机器化把关：①selected 可追溯 ②候选≥2 ③图存在 ④1K
> ⑤2.35:1）；**规则⑥「近 3 篇回避 / montage 同源家族回避」已从代码删除**
> （见 `contracts.py:verify_cover_set`，`recent_covers` 参数降级为废弃 no-op）。

**规则清单（与下方验证清单 tier-2 项一一对应）：**

| # | 规则 | 判据 |
|---|------|------|
| ① | `selected ∈ candidates` 的 path 集合（选定项可追溯，**跨字段**） | selected 必须精确等于某个 candidate 的 `path`；不在集合内 = 选定项不可追溯（规则名 `selected_in_candidates`） |
| ② | `candidates` ≥ **2**（多风格并行打样） | 少于 2 个候选 = 没真正并行打样（单张无从「选优」）。下限取模块级 `_COVER_MIN_CANDIDATES`（规则名 `candidates_min`） |
| ③ | 每候选图**实际存在**（磁盘 IO） | 用 Pillow 打开 path：`FileNotFoundError` → `candidate_exists`；其它解码异常 → `candidate_readable`（绝不裸抛） |
| ④ | **1K 分辨率**：长边 ∈ `[900,1200]` | 用 Pillow 读真实像素，长边落带外即报。**复用 `verify_infographic_set` 既定 `_K1_MIN/_K1_MAX`（单一事实源，不双写漂移）**，依据见该函数文档串「1K 容差带的依据」（规则名 `resolution_1k`） |
| ⑤ | 封面比例 **2.35:1**（cinematic） | 封面恒横图（w>h），按高推理想宽，实际宽偏差 ≤ **±4px** 即命中（容差略宽于信息图 ±2px：封面比例更扁、按高推宽杠杆更大，长边宽 ~1024px 量级、与 1K 约束 [900,1200] 自洽，同等相对取整误差对应更大绝对像素）。**2.35:1 是 cover-styles.md 底层铁律第一条，briefing/noir + montage 3 亚型全共享**（规则名 `cinematic_ratio`） |
| ⑥ | ~~给 `recent_covers` 时 selected 风格与近 3 篇不重复~~ **🔴 已删除（2026-05-22 封面锁定 montage-evidence）** | 「近 3 篇回避 / montage 同源家族回避」规则已从 `verify_cover_set` 删除，`recent_covers` 参数降级为废弃 no-op、完全忽略，不再产生 `recent_repeat` 违规。封面单风格锁定，无风格轮换 |

**强制范围**：**仅对 P4.2 fan-out 新产出强制，不追溯历史冻结 golden**
（历史 3 篇封面各异：风格/比例形态不统一，有的根本没 `素材/cover`
目录——追溯它们=误判门，与 `verify_infographic_set` /
`verify_research_set` / `verify_content_enhance_set` 同理）。一致性等价
**exit 0**：`_OUTPUT_SCHEMA` 顶层 `cover` 仍为
`{candidates: list, selected: str}` **不变**（本门不改 tier-1 契约面）；
机制由 `regression_baseline.py` P4 门 (c) 段 +
`pytest tests/test_contracts.py` 共用同一套合成 PNG fixture
（`tests/golden/_synthetic_cover/make_fixtures.py`）断言——合规组返回
空、各违规组精确报对应规则名，单一事实源、hermetic、不烧 baoyu-cover
生图配额（真实多风格生图 + 编排器主轴选优延 P6/人工，plan
carry-forward 显式登记非静默）。**依赖阈值/键集构造 fixture 前先
一致性自检命中即 return**（P3.1 复审硬约束，防裸崩）。

### 验证清单

- [ ] `candidates` 是 list、`selected` 是 str（`validate_output` 强校验）。
- [ ] 每项是 dict、`path` 非空 str；`selected` 非空 str `(validate_output 强校验：P4.1 起 _validate_cover() 机器强制)`。
- [ ] `selected` 取值必须等于某个 candidate 的 path（选定项可追溯，**跨字段**）`(语义关/非 schema 强制：P4.2 verify_cover_set 规则① selected_in_candidates，对新产出把关，不追溯历史 baseline)`。
- [ ] `candidates` ≥2（多风格并行打样）`(语义关/非 schema 强制：P4.2 verify_cover_set 规则② candidates_min)`。
- [ ] 所有 candidate 图片实际存在、**1K 分辨率**（复用信息图 [900,1200] 既定带）、比例为 **2.35:1**（cinematic）`(语义关/非 schema 强制：P4.2 verify_cover_set 规则③ candidate_exists / 规则④ resolution_1k / 规则⑤ cinematic_ratio，对新产出把关，不追溯历史 baseline；铁律)`。
- [ ] ~~给 `recent_covers` 时 selected 风格与近 3 篇不重复~~ **🔴 规则⑥已删除（2026-05-22 封面锁定 montage-evidence）**：不再做风格回避，`recent_covers` 为废弃 no-op。仍校：未用 Agent 原生生图破 2.35:1。
- [ ] **封面锁定 montage-evidence 单风格**：默认无多候选 fan-out / 无选优 / 无近 3 篇回避，直接生成单张 `素材/cover.png`。仅显式覆盖 `cover_style` 时才生成指定单风格。

---

## review

磨稿审稿 team（**opt-in / 提议制**：默认不强开，由编排器提议、用户确认后才 fan-out）。

### 输入 bundle

- `sansheng_context`：人设 + 风格路由（审稿据此判调性是否走样）。
- `iron_rules`：全阶段相关铁律子集（审稿角色据此查违规）。
- `article_meta`：文章元信息。
- `stage_input`：定稿全文 + 审稿维度清单（每维度对应一个 role）。

### 输出 schema

对齐 `_OUTPUT_SCHEMA["review"] = {"verdicts": list}`，
`verdicts` 每项 `{role, issues, pass}`：

```json
{
  "verdicts": [
    {"role": "事实核查",   "issues": ["第3段价格未标官网信源"], "pass": false},
    {"role": "调性审查",   "issues": [],                       "pass": true},
    {"role": "铁律合规",   "issues": ["出现尾部总结句"],        "pass": false}
  ]
}
```

- `verdicts`：**list**（`validate_output` 强校验）。**（P5.1 起）每项 item 级
  必须 dict 且含非空 str `role`、list `issues`、**严格 bool** `pass`（排除
  int）= tier-1 结构强校验**，由 `validate_output("review",...)` →
  `_validate_review_items()` 机器强制（结构层）`(validate_output 强校验)`。
  issues 内容质量 / role 是否合法审稿角色 / 裁决与正文一致性 / `pass=false`
  时 issues 是否非空可定位 / H2·段落 delta = **tier-2 语义关**，由 P5.2
  审稿 team 对 _新产出_ 强制、不追溯历史冻结（历史无统一 review 产物）
  `(语义关/非 schema 强制)`。

> **🪤 pass 字段 bool/int 陷阱**：每项 `pass` 是严格 `bool`。**（P5.1 起）
> `_validate_review_items()` 已机器强制 `pass` 严格 bool**：用
> `isinstance(v, bool)` 直判，**不复用 `int` 分支**（`isinstance(True,
> int)==True`，反向亦不可拿 int 校验冒充 bool —— `pass=1`/`0` int 会被判
> ContractError）。`pass` 是 Python 关键字，取值用 `item["pass"]` 下标
> （不写属性名）。与 infographic `bytes`(int) 并排时切勿统一一套 isinstance
> ——二者互为镜像（bytes 排除 bool / pass 要真 bool）；详见顶部「校验层级
> 总纲」§bool/int 陷阱。

### tier-2 语义门：`verify_review_set`（P5.2，仅对 opt-in 审稿 team fan-out 新产出强制）

> 与 tier-1 结构契约 `validate_output("review",...)` **分开**，与
> `verify_infographic_set` / `verify_research_set` /
> `verify_content_enhance_set` / `verify_cover_set` **并列同构**。**故意
> 不写进 `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与
> 本文件「校验层级总纲」自相矛盾——tier-1 只校验 verdicts[].role 非空
> str + issues 是 list + pass 严格 bool，见 `_validate_review_items`；
> issues 内容质量 / role 合法性 / 裁决一致性属 tier-2）。由编排器在
> **审稿 team fan-out 收齐之后**、对**新产出 verdicts 集合**单独调
> `scripts/contracts.py:verify_review_set(verdicts, recent_or_ctx=None)`
> 把关；返回 `list[str]`（每条带定位 `verdicts[i]` / `role` + 规则名），
> 空 list = 通过。纯函数：只读入参（不读磁盘/网络/状态），异常转结构化
> 原因不裸崩。第二参 `recent_or_ctx` 仅为与其它 verify_* 同构预留位，
> P5.2 规则①②③ **不消费**（review 不追溯历史冻结，无历史/上下文输入）。

> 🔴 **team 为 opt-in / 提议制**：审稿 team **默认不强开**。磨稿阶段
> 编排器判本篇是否显著受益于多角色围审 → 受益则**明确提议用户、等
> 确认后才 TeamCreate fan-out**（遵守 memory `feedback_agent_teams_propose`：
> team 不自动触发，Claude 提议 + 用户确认后才发起）。未确认 / 用户拒绝 /
> `orchestrator=off` / 提议交互不可用 → **走既有单 agent 磨稿，与 legacy
> 字节级等价**（不开 team、不调本门、不产 verdicts 集合）。提议判定 /
> 话术 / 三角色分工 / 短时即散见 [anti-ai-filter.md](anti-ai-filter.md)
> §九 审稿 team / [autopilot.md](autopilot.md)。

> 🔴 **汇总裁决由编排器主轴自做、绝不外派 subagent**：双门通过后，
> 编排器**主轴自己**汇总三角色 issues、去重消冲突、形成统一处置清单、
> 按前八节规则**自己应用 fixes**（plan 须明确「此步主轴自做不外派」），
> **不派任何 subagent 做汇总/裁决/改稿**（汇总需要全局视野与最终裁量
> 权，属编排器主轴职责，外派会丢上下文且违反单一状态写者精神，与
> `verify_content_enhance_set` 合并关 / `verify_cover_set` 选优由主轴
> 自做同精神）。`verify_review_set` 是汇总裁决**前置**对 verdicts 集合
> 的机器化把关（校验角色覆盖 + 裁决有效性），**不是汇总裁决本身**
> ——它不替编排器裁决该不该回流、也不判 issue 内容对错。

**规则清单（与下方验证清单 tier-2 项一一对应）：**

| # | 规则 | 判据 |
|---|------|------|
| ① | role 覆盖：去重后 ≥ **3** 个不同 role | 三角色 = 风格审 / 铁律审 / 事实核查，三维度齐才构成一轮有效围审。去重计数防「同一 role 报两条 verdict 凑数」绕过 ≥3。**门不内置「合法 role 白名单」**（白名单会随审稿维度增删漂移、且越界替编排器做「这个 role 算不算正经审稿角色」的语义裁量）——只数去重后不同 role 个数够不够，不判每个 role 叫什么是否「正统」（与 `verify_cover_set` 不内置「当前可用风格白名单」同精神，规则名 `roles_min`） |
| ② | `pass=false` 的 verdict 其 `issues` 必须非空 | 判失败却无具体可定位 issue = 无效裁决，编排器无从回流处置（规则名 `fail_needs_issues`） |
| ③ | 裁决一致性轻量启发式 | 某 verdict `pass=true` 却携带非空 `issues` = 弱不一致警示项（要么 issue 是噪声、要么不该 pass）。**判不准倾向报违规**（让编排器主轴复核裁决是否自相矛盾），与全门 fail-safe 取向一致（规则名 `verdict_consistency`） |

**强制范围**：**仅对 P5.2 opt-in 审稿 team fan-out 新产出强制，不追溯
历史冻结 golden**（历史 3 篇文章无统一 review 产物、多数根本没
`素材/review` 目录——追溯它们=误判门，与 `verify_infographic_set` /
`verify_research_set` / `verify_content_enhance_set` / `verify_cover_set`
同理）。一致性等价 **exit 0**：`_OUTPUT_SCHEMA` 顶层 `review` 仍为
`{verdicts: list}` **不变**（本门不改 tier-1 契约面）；机制由
`regression_baseline.py` P5 门 (d) 段 + `pytest tests/test_contracts.py`
共用同一套合成 fixture
（`tests/golden/_synthetic_review/make_fixtures.py`）断言——合规组返回
空、各违规组精确报对应规则名，单一事实源、hermetic、不烧任何 LLM
审稿配额（**真实 TeamCreate 三角色 + 编排器汇总 + `pass=false` 回流 +
opt-in 提议交互延 P6/人工，plan carry-forward 显式登记非静默**）。
**依赖阈值/常量构造 fixture 前先一致性自检命中即 return**（P3.1 复审
硬约束，防裸崩）。

### 验证清单

- [ ] `verdicts` 是 list（`validate_output` 强校验）。
- [ ] **（P5.1 起机器强制）每项 dict 且含非空 str `role` / list `issues` /
      严格 bool `pass`（排除 int）** = tier-1 结构强校验
      `(validate_output 强校验)`。
- [ ] `verdicts` 覆盖 stage_input 列出的全部审稿维度（去重后 ≥3 不同 role：风格审/铁律审/事实核查）`(语义关/非 schema 强制：P5.2 verify_review_set 规则① roles_min，对新产出把关，不追溯历史冻结)`。
- [ ] `pass=false` 的 verdict 其 `issues` 非空且可定位 `(语义关/非 schema 强制：P5.2 verify_review_set 规则② fail_needs_issues)`。
- [ ] 无 `pass=true` 却携带非空 `issues` 的裁决不一致（弱提示，判不准倾向报）`(语义关/非 schema 强制：P5.2 verify_review_set 规则③ verdict_consistency)`。
- [ ] `issues` 内容质量 / `role` 是否「正统」审稿角色 / 裁决与正文一致性 / 团队审稿前后 H2 数 delta == 0 且正文段落数变化 ≤±15% = **tier-2 语义关/编排器主轴裁量**，由 P5.2 审稿 team 对 _新产出_ 强制、不追溯历史冻结；门**不越界**判 issue 内容对错与 role 合法性 `(语义关/非 schema 强制)`。
- [ ] review 为 **opt-in / 提议制**：编排器判显著受益 → 提议用户 → 确认后才 fan-out；未确认 / 拒绝 / `orchestrator=off` → 走 legacy 单 agent 磨稿、字节级等价 `(语义关/非 schema 强制；提议制)`。
- [ ] **汇总裁决（合并 issues / 消冲突 / 应用 fixes / 按失败语义回流）由编排器主轴自做、绝不外派 subagent**，`verify_review_set` 是汇总裁决前置对新产出的机器化把关，不是汇总裁决本身 `(语义关/非 schema 强制：P5.2 汇总裁决由主轴执行)`。
- [ ] 审稿 team 是**短时单元**：围审一轮 + 主轴汇总应用 fixes 后立即 TeamDelete 解散，不常驻/不跨阶段复用 `(语义关/非 schema 强制；短时即散)`。
- [ ] 产物落盘 `素材/review/verdicts.json`；任一 `pass=false` 回流编排器走失败语义处置（连错 3 次才回报，恢复决策归编排器，subagent 不 skip）`(语义关/非 schema 强制)`。
