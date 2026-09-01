# skill 自省复核流程（skill-review）

> 本 skill 的「持续进化」机制 —— 每写一篇文章脚本自动留病历，
> 攒够了请旁观者会诊，动刀人工签字。
>
> **设计原则**：观察高频 / 便宜 / 确定性；修改低频 / 攒批 / 人工审。
> 「每篇都自省」不等于「每篇都自动动手术」—— 自动改一个高频生产工具会持续漂移。

## 触发

用户说「复核 write skill」「skill 自省」「skill 复盘」「skill 进化」时进入本流程。

**节奏由你定** —— 建议攒够 8-10 篇文章的 observation 再复核一次。攒太少
（1-2 篇）噪音淹没信号、抓不到模式；攒太多则问题积压。

## 数据源

观察日志路径由 `scripts/profile_config.py::observations_file()` 解析：配置 profile 时位于
`<profile>/flywheel/_skill-observations.jsonl`，未配置才回退仓根。每篇文章运行时，由
`contracts.py` / `format_layout.py` / `pipeline.py` 自动追加「门判定记录」。**禁止只看仓根同名旧文件**。
每行一个 v2 JSON，核心字段：`record_id/run_id/recorded_at/article_uid/stage/event/attempt/passed/severity/issue_codes/metrics/artifact_digest/source/workspace_root/workspace_uid`；同时保留 v1 的 `ts/article/verdict/detail` 兼容旧工具。pipeline 已绑定文章工作树时，`workspace_root` 记录解析后的绝对路径、`workspace_uid` 记录稳定短哈希；独立调用方尚未绑定时两者为空。

- `stage`：format_layout / verify_writing / archive
- `event`：门名或归档事件（verify_bold_density / verify_cjk_punctuation / registry_write / verify_closed_loop / copy_plan / copy_verify / source_cleanup / ...）
- `verdict`：该门这次的判定（ok / fail / warning / blocked / suspicious ...）
- `detail`：简短事实（命中几处、ratio 多少），**不含判断**

## 复核流程（5 步）

### 第 1 步 · 读 observation log 全文

调用 `observations_file()` 找到实际日志后读全文，禁止默认只看仓根旧文件。
若不存在或为空 → 告诉用户「还没攒够 observation，先写几篇文章再来」，结束。

### 第 2 步 · 统计模式

按 `stage + event`（阶段 + 门名）做**两套口径**：A. 原始 attempts（看恢复成本）；B. 每篇文章 `article_uid + stage + event` 只取最新一条（看最终失败率）。同名 event 若出现在不同 stage 必须分开统计，重跑不能在最终口径里重复计权。

| 阶段 / 门 | 原始尝试数 | 最新样本篇数 | 首次失败篇数 | 最终失败篇数 | 平均尝试次数 | 高频 issue_codes |
|---|---:|---:|---:|---:|---:|---|

重点找四类信号：
- **反复出问题的门**：某门在多篇最终 fail → skill 规则有缺陷，或写作总踩同一个坑
- **可恢复但昂贵的门**：首次常 fail、最终多 ok、平均 attempt 高 → 规则有效但前置指导不足
- **死门**：某门从来没拦下过任何东西 → 可能多余，该删或该改
- **疑似误判门**：某门几乎每篇 fail → 规则可能太严
- **字段不足**：observation 现有字段是否够支撑判断 → 要不要让脚本多记点
- **发布闭环异常**：`archive` 的 `registry_write` / `verify_closed_loop` 是否反复失败或重试 → 区分元数据问题、派生视图漂移与作品库写入故障
- **实体归档异常**：`copy_plan` / `copy_verify` / `source_cleanup` 是否失败 → 区分未配置永久根、目标冲突、复制期仍有写者、哈希复验失败与源目录清理失败；作品库登记成功不能证明文件已经移出 worktree

**🕸 织网两指标（数据源看各篇 `article-meta.yaml` + `profile/brand-net.md`）：**
- **织网执行率**：近 N 篇里 `weave:` 三问真答了几篇（含"不织:理由"也算答）；空着/没这字段 = 步骤 7.5 被跳，查原因
- **承诺兑现率**：brand-net.md §四台账里超过 1 个月仍 ⏳ 的愿有几条 → 列出排期或公开调整口径，**不许烂尾**

### 门的分类与放宽判据

复核时先判断门保护的是什么，不能只看“它拦了几次”：

- **内容真实性 / 权利 / 作者拍板 / 正式发布回读**：属于不可替代证据，继续硬拦；服务商暂时不可用也不能改写旧资产出身，作者检查点也不能由机器代签。
- **作者在场检查点**：证据缺失时状态应是 `waiting_author`，不是内容 `failed`，不累计失败次数；这是等待态建模，不是放宽审批。
- **服务商与执行通道**：门校验“最终文件 + 真实来源 manifest”，不绑定某一家厂商。Google、网页手工生成或复用既有成品都可通过同一合同。
- **路径、缓存、派生视图等运行环境**：应自动绑定当前工作区、给出可恢复错误；不得因为主仓路径被导入时冻结而制造假失败。
- **候选的放宽条件**：只有跨篇数据显示高误判、被拦样本经独立复核均合格，且放宽后仍有等价证据时才改。单篇觉得麻烦、第三方冻结或处理耗时都不是放宽理由。

复盘报告必须把结论写成“保留 / 改状态语义 / 改证据合同 / 删除”四类之一，避免把所有不顺畅都笼统归因于“闸门太严”。

### 第 3 步 · 派旁观者 agent 找模式 + 给建议

用 Agent 工具派一个 general-purpose subagent。**它看的是「跨 N 篇的模式」，
不是单篇质量**（与写文章时的单篇旁观者不同）。喂给它：① observation log 全文
② 第 2 步统计表 ③ skill 关键文件清单（contracts.py / format_layout.py /
pipeline.py / writing.md / outline.md / SKILL.md）。

旁观者职责：
- 哪个门反复出问题 → 是 skill 规则缺陷，还是写作习惯问题？
- 哪个门形同虚设 / 疑似误判 → 该删 / 该改 / 该放宽？
- observation 字段够不够？要不要脚本多记什么？
- skill 有没有「文档说了但实战从不触发」的装饰性设定？

旁观者**只产建议报告（按 P0/P1/P2 排序），不改任何文件**。

### 第 4 步 · 人工决定

把旁观者报告给用户。用户逐条拍板「改 / 不改 / 以后再说」。
**这一步不可省** —— 旁观者会犯错（它的判断也是 LLM 输出，有 variance），
人工闸门是防止错误建议被固化进生产工具的唯一保险。

### 第 5 步 · 归档滚动

用户拍板、改动落地后：
- 已复核的记录从 `_skill-observations.jsonl` 移到 `_skill-observations.archive.jsonl`
- 主 log 清空

这样下一轮复核只看「上次复核之后的新记录」，不重复看旧的。

```bash
# 归档（在 skill 根目录）
cat _skill-observations.jsonl >> _skill-observations.archive.jsonl
: > _skill-observations.jsonl
```

## 旁观者 agent prompt 模板

```
你是本 skill 的「自省复核 agent」。职责：跨 N 篇文章的运行记录里
找模式，复核 skill 本身的健康度。你看的是「模式」，不是单篇文章质量。

## 数据：observation log（N 篇文章的门判定记录）
<贴入 _skill-observations.jsonl 全文>

## 已做的统计
<贴入第 2 步统计表>

## skill 关键文件（自己打开读）
contracts.py / format_layout.py / pipeline.py / references/{writing,outline}.md / SKILL.md

## 你要回答
1. 哪个门反复出问题？是 skill 规则缺陷还是写作习惯？
2. 哪个门形同虚设（从不触发）/ 疑似误判（几乎每篇 fail）？该删/改/放宽？
3. observation 记录的字段够不够支撑判断？要不要脚本多记什么？
4. skill 有没有「文档写了但实战从不触发」的装饰性设定（参考 verify_compact_strokes 的教训）？

## 交付
≤1000 字报告，建议按 P0/P1/P2 排。只诊断不改文件。
独立判断 —— observation log 是事实，你负责从事实里读出 skill 的病。
```

## 铁律

- 旁观者**永不自动改 skill** —— 它只诊断，动刀由你签字。
- observation 只记**事实**不记判断；判断在复核时由旁观者一次性做。
- 单篇的偶发噪音不处理 —— 只有「跨多篇反复出现」的才算真问题。
- 旁观者自己也会犯错（它是 LLM）—— 第 4 步人工闸门不可省。
