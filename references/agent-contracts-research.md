# 调研结构化合同

仅在按 research schema 回传时读取。执行拓扑见 [orchestration.md](orchestration.md)。

搜索首先服从当前宿主的引擎优先规则；下方旧路由表仅在宿主未另行规定时参考。

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
> `validate_output`**（塞进去会污染契约且与[校验层级说明](agent-contracts-validation.md)自相矛盾——
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

