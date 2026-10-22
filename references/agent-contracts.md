# 子任务合同索引

通用调度、输入冻结与文件所有权只读 [orchestration.md](orchestration.md)。不要一次加载所有阶段合同。

| 本轮任务 | 只读此合同 |
|---|---|
| 独立事实复核 | [fact-check.md](fact-check.md) |
| 独立语义冷读 | [semantic-review.md](semantic-review.md) |
| schema2 图片生成/审核 | [stylebook-contract.md](stylebook-contract.md)，以及实际步骤引用的合同 |
| research 结构化调研 | [agent-contracts-research.md](agent-contracts-research.md) |
| 明确启用三角色审稿团队 | [agent-contracts-review.md](agent-contracts-review.md)；不与默认双复核自动叠加 |
| 历史 schema1 / 旧结构化四策略实验 | [agent-contracts-legacy.md](agent-contracts-legacy.md) |

## research

按 research schema 交回 `findings` 与 `sources`；字段与验证见上表对应文件。搜索服从当前宿主规则；一个问题先用一个合适引擎，结果不足再降级，不同问题才并行。

## review

只有显式采用三角色 team 时才走上述完整旧团队合同；不能为了“完整流程”增加第三轮审核。

## 校验层级

机器合同检查字段、摘要和来源；语义审核检查含义与读者体验，两者不能互相冒充。旧结构化新产物按对应合同校验，不追溯改写历史。旧结构化校验细节见 [校验层级说明](agent-contracts-validation.md)，仅使用对应合同才读取。输出字段的实现真源是 `scripts/contracts.py`；主控收齐后验收，不直接相信子任务的“已通过”。
