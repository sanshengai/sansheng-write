# 旧结构化产物合同

仅历史 schema1 或显式旧 fan-out 实验使用。新 schema2 不使用这里的候选数、图片数与画风要求；content_enhance 默认按缺口选择，不调用四策略齐备校验。这里保留旧消费者迁移所需字段。

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
> `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与[校验层级说明](agent-contracts-validation.md)自相矛盾——tier-1 只校验 strategies 4 键齐全/仅认/值非空
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
> —— `bytes=True`/`False` 会被判 ContractError。详见[校验层级说明](agent-contracts-validation.md)
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
> `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与[校验层级说明](agent-contracts-validation.md)自相矛盾——tier-1 只校验 candidates[].path 非空 str +
> selected 非空 str，见 `_validate_cover`；`selected ∈ candidates` /
> 磁盘 IO / 像素属 tier-2）。由编排器在 cover fan-out **收齐之后**、对
> **新产出**单独调
> `scripts/contracts.py:verify_cover_set(candidates, selected, recent_covers=None)`
> 把关；返回 `list[str]`（每条带定位 `candidates[i]` / `selected` +
> 规则名），空 list = 通过。纯函数：只读入参 + 磁盘 PNG 像素（IO），
> 不碰网络/状态，异常转结构化原因不裸崩。1K 口径**复用**
> `verify_infographic_set` 的模块级 `_K1_MIN/_K1_MAX`（=`[900,1200]`，
> 单一事实源在 `contracts.py` 本体，**不重复造规则**，文档只存索引）；
> 2.35:1 依据 [iron-rules.md](iron-rules.md) §视觉 第 2 条
> （封面 `2.35:1`；Hero `1:1`；信息图首尾 `9:16`、中间至少两张 `16:9`）。

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

