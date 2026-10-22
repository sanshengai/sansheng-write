# 画风库规划试验（非正式制作必经步骤）

文章希望试用 `sansheng-image` 时，可先按该 Skill 的 v3 规则独立规划正文配图，保存计划，然后在**当前文章目录**运行：

```bash
python "$SKILL/scripts/pipeline.py" compile-stylebook-preview \
  --plan stylebook-plan.json --image-skill-root /已安装的/sansheng-image
```

该入口检查 `source.path` 必须指向本篇 `定稿.md`、原文字节 SHA-256、全文 `coverage` 和逐张编译合同，输出 `素材/stylebook-preview-<计划摘要>.json`：每张的完整编译词、清单、实际画风库文件摘要及真实 `producer` 均在其中。0 张新增图也能得到明确预览证据。预览的 `renderer=null`、`plan_review=not_run` 是实际状态；须另按画风库规则执行独立 `plan-review` 和实际图片核对。旧预览不会被不同本体静默覆盖。

这个预览入口只验证内容规划与画风编译的消费者输入，**不**生成图片，不写 `visual-plan.json`、`render-batch.json` 或发布封存回执；不能代替 schema2 的实际制作与验收，也不能凭预览回执进入微信草稿。schema2 允许正文图 0～多张，按自己的来源、文字、装配和封存合同验收，不能把新图记为宝玉出图。下述 schema1 主链保留给历史文章和显式选择。

