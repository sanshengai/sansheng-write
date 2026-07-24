# 编排器规范

编排器是当前执行 Skill 的主控制器，与具体厂商或模型无关。`pipeline.py` 只维护状态和合同，不负责启动子任务。

## 职责

- 读取 `profile/context.md`、article meta、state 和当前阶段 reference。
- 把任务拆成互不覆盖的工作单元。
- 为每个单元提供最小上下文和明确输出路径。
- 收齐后运行机器验证；不以“子任务说完成了”代替验证。
- 只有编排器可以写 `.state.json` 或推进 stage。

## 可并行与不可并行

可并行：

- 多源调研。
- 独立事实复核与语义冷读。
- 多张已编译 canonical prompt 的像素渲染。

必须串行：

- 大纲批准 → 正文定稿。
- canonical prompt 编译 → 渲染 → 后处理 → 视觉 QA → seal。
- `release-to-draft` 整个事务。
- `finalize` 的归档 → 验证 → 官网 → 朋友圈文案。

定稿后的发布机械链不允许多个执行者同时写同一文章目录。

## 任务 bundle

每个并行单元至少含：

```yaml
run_id: 当前运行 ID
stage: 阶段
unit_id: 唯一单元 ID
inputs:
  - 只读输入路径与摘要
output:
  path: 唯一输出路径
constraints:
  - 不写 .state.json
  - 不调用发布接口
  - 不运行破坏性脚本
validation:
  - 返回结构化结果与失败原因
```

## 收齐与验证

1. 检查每个 unit ID 恰好返回一次。
2. 检查输出路径无覆盖冲突。
3. 运行对应 `contracts.py`/pytest/阶段 verify。
4. 任一单元失败就保留现场，最多按同一输入重试。
5. 全部通过后由编排器落盘并推进 state。

## 失败语义

- 子任务失败不能自行 `skip`。
- 连续三次同因失败就停，不扩大权限或换成未登记工具。
- 外部写操作必须由主流程授权；只读审计不得执行迁移、发布、覆盖或删除。
- 发布事务已拿到远端 ID 后，以 `_release-attempt.json` 为恢复锚，不重新创建。

`orchestrator=off` 只改变执行拓扑为串行，不改变输出合同和验证门。
