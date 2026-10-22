# 可选审稿团队合同

仅在明确启用此三角色审稿团队时读取；默认事实复核、语义冷读各用其专项合同，不另叠加本团队。

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
> 总纲」§bool/int 陷阱，见 [校验层级说明](agent-contracts-validation.md)。

### tier-2 语义门：`verify_review_set`（P5.2，仅对 opt-in 审稿 team fan-out 新产出强制）

> 与 tier-1 结构契约 `validate_output("review",...)` **分开**，与
> `verify_infographic_set` / `verify_research_set` /
> `verify_content_enhance_set` / `verify_cover_set` **并列同构**。**故意
> 不写进 `_OUTPUT_SCHEMA` / `validate_output`**（塞进去会污染契约且与
> [校验层级说明](agent-contracts-validation.md)自相矛盾——tier-1 只校验 verdicts[].role 非空
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
- [ ] 产物落盘 `素材/review/verdicts.json`；任一 `pass=false` 回流编排器走失败语义处置（确定性错误立即回报并修输入，瞬态外部错误才有限重试，恢复决策归主控，子任务不 skip）`(语义关/非 schema 强制)`。
