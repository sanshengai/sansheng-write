# 全流程自动驾驶

默认目标：从选题到微信草稿箱连续推进；方向不确定或用户配置了检查点时才停。状态以 `.state.json` 为准。

## 启动

```bash
python "$SKILL/scripts/pipeline.py" status
```

先读 profile 上下文，再从最早 pending/dirty 阶段恢复。不要重做已通过且摘要未变化的阶段。

## 主流程

1. **选题与大纲**
   - 读取 `outline.md`、近三篇作品和必要信源。
   - 写 `大纲.md` 与 `article-meta.yaml`。**`article-meta.yaml` 从
     `templates/article-meta.template.yaml` 复制再改**，不要手写 —— 模板里带着
     `infographic_subject` / `visual_profile` / `tags` 受控词表这些必填项的注释，
     手写极易漏，而它们要到 `adopt-final` 才报错。
   - 配置 blueprint 检查点时等待作者确认并执行 `approve blueprint`。

   🔴 **blueprint 锚点文件必须同时含下面六项**，缺一 `verify outline` 就拦
   （作者明说免检时写「作者免检授权」整体放行）：

   | 锚点 | 判据 |
   |---|---|
   | 5 套标题+封面文案 | 文中出现 `方案 1` ~ `方案 5`；或写明「作者指定标题」 |
   | 开头选择 | 含「开头」 |
   | 大纲结论 | 含「大纲」 |
   | 封面风格 | 含「封面风格」 |

   （信息图主题/风格不再进闸门：全站固定 `claymation + warm-light-clay`，没有可选项。
   旧版要求在这里声明视觉路由，而那个判断填错时全链无人校验 —— 路由已整体砍掉。）

   审批结论另需单独一行 `审批结论：通过`（或「作者免检授权：免检」），且全文不得
   出现「不通过 / 未通过 / 拒绝 / 驳回 / 不同意 / 尚未确认 / 待确认」——
   出现任一即判 rejected。
2. **内容增强**
   - 按 `content-enhance.md` 补充案例、反例、类比和可验证事实。
3. **正文**
   - 运行 `prep_writing.py`，按 `writing.md` 与选定风格手册写 `定稿.md`。
   - 生成标题候选并确定最终标题。
4. **磨稿与双复核**
   - 运行反 AI 磨稿。
   - 事实复核与语义冷读使用独立上下文，产出结构化记录。
   - 配置 draft 检查点时等待作者确认并执行 `approve draft`。
5. **定稿后的机械链**
   - 只读 [release-runtime.md](release-runtime.md) 并按命令顺序执行。
   - 视觉业务规划在本 Skill 内完成；外部 `baoyu-image-gen` 只渲染像素。
   - BGM 是发布硬门。
   - 草稿创建只运行 `release-to-draft`。

作者直接提供已确认定稿时，跳过 1--4，使用：

```bash
python "$SKILL/scripts/pipeline.py" adopt-final \
  --final 定稿.md --meta article-meta.yaml
```

这不是伪造写作历史，而是显式进入 `release-from-final` 模式。

⚠️ **`adopt-final` 会把 `_draft-approval.md` 覆写成机器接管块**（绑定定稿 SHA）。
作者拍板时说的话、以及当时定下的取舍，要写在**另一个文件**里（如
`_draft-decisions.md`），否则接管一跑就没了。

## 合同门要求 subagent，但当前运行时不给 subagent 时

事实复核（`fact-check.md`）与语义冷读（`semantic-review.md`）都要求独立上下文，
视觉 QA 还要求独立看图进程。**当宿主运行时不允许派 subagent 时，这不是跳过的理由，
而是降级执行**：由主 agent 就地完成，但必须在产出文件顶部**显式写明执行方式与
诚实边界**（哪些是机器可定位的、哪些是同模型自审照不出的盲区）。

伪造成「已派独立评审」是不允许的；直接 `skip` 也是不允许的。

## 合法停顿

- 用户明确要求逐步确认。
- blueprint/draft 检查点。
- 缺凭证、权限、输入文件或外部服务不可用。
- 非零合同门经同因重试三次仍失败。

除此之外不因“下一步可能费时”停顿，也不把失败 stage 标成 done。

## 并行

默认可并行独立调研、事实复核和语义冷读；具体合同见 `orchestration.md`。对同一文章目录有写入的发布机械链必须串行。

## 恢复

- `status` 显示 dirty：从最早 dirty 阶段重验。
- renderer 失败：按同一 prompt 和比例走已配置 fallback。
- 图片后处理后变化：重新 `visual-qa`、`seal visual`。
- 微信草稿已创建但读回失败：复用 `_release-attempt.json`，不得重复建稿。
- 正式发布后取得永久链接：运行 `finalize`，不要分别手工归档和同步官网。

## 自动化边界

自动流程止于微信草稿箱。原创声明、赞赏、正式发布和朋友圈实际发送由作者完成；拿到永久链接后，归档、官网同步和朋友圈文案生成可自动完成。
