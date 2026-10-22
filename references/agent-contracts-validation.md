# 旧结构化合同的校验分层

仅在实际使用 `validate_output` 等结构化合同实现或对应旧实验时按需读取。

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

