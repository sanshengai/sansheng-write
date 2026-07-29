# 铁律清单

原则：能由代码判断的规则只在代码中执行，本文只给人类一页索引。遇到冲突，以 `pipeline.py`、`contracts.py`、`visual_workflow.py`、`visual_qa.py` 的非零退出为准。

## 发布主链

1. 新文章必须经过 pipeline；不得手改 `.state.json`。
2. 作者定稿进入机械链时先 `adopt-final`，不得伪造前半程审稿文件。
3. BGM 是发布硬门；缺 MP3 或 AUDIO-CARD 就没完成，`skip bgm` 被拒绝。
4. writing、cover、infographic、bgm、layout、publish 不可 skip；历史迁移只有显式 `--force`/`--legacy` 例外。
5. 草稿箱唯一入口是 `release-to-draft`；非零退出时禁止直调发布接口。
6. 正式发布、原创和赞赏由作者人工完成；永久链接用 `finalize` 收尾。
7. 控制器是机械链唯一命令写者；模型只交付任务单候选与视觉 QA，不运行、重试或并发启动长命令。

## 视觉

1. 语义 producer 固定为 `sansheng-write.visual-planner`；`baoyu-image-gen` 只是 renderer。
2. 封面 `2.35:1`；Hero `1:1`；信息图首尾 `9:16`、中间至少两张 `16:9`。
3. 信息图与 Hero 一律 `claymation + warm-light-clay`，全站统一粘土风，不按题材分流。
4. 真人真事优先真实授权图片，禁止生成相似人物肖像。
5. 精确数字图走本地确定性代码；精确拓扑可走 `baoyu-diagram`。
6. renderer fallback 只能按配置执行，prompt 和比例不可改变。
7. 最终图后处理后必须独立 `visual-qa` 并 `seal visual`；Markdown 勾选不算证据。
8. 信息图引用只由 `assemble-release` 写入带 marker 的机器块；正文变化仍会令 release job 失效。
9. `style_consistent` 不能代替目标风格验收；QA 必须通过 `style_contract_match`、
   `brand_palette_match`，封面另过 `composition_contract_match`。
10. 所有正文视觉均须由登记的生成式 renderer 原生生成；图中文字必须随画面一起生成，
    禁止以 `template_id`、Pillow、本地模板或后期叠字替代。生成失败只能按 policy
    切换另一生成式 renderer，不能降级为确定性模板。
11. 看图模型不是视觉发布的唯一授权者；没有实际对象、数量、位置和版式观察的
    布尔式 QA 不得放行。
12. `text_match`、`no_unexpected_text`、`style_contract_match` 不得从发布硬门移除；
    `required_text` 每条恰好出现一次。Hero 与最终 HTML 实际引用的所有生成图必须送审。
13. 同一发布任务中不得修改 QA 规则迁就现图；编译后 QA 代码发生变化时凭证失效。
14. 封面与信息图必须分别留下 `baoyu-cover-image` / `baoyu-infographic` producer chain；
    只调用 `baoyu-image-gen` renderer 不等于执行了完整 Baoyu 视觉工作流。

## 排版

1. H2/H3 只写纯标题，不手写 PART、序号或装饰。
2. 破折号统一 `--`，避免全角破折号进入成稿。
3. 金句卡禁装饰引号；出处行使用弱化右对齐样式。
4. `hero.png` 只放标题后、导读前；音乐卡放导读后、正文前。
5. 正文图片必须实际嵌入 Markdown/HTML，素材目录存在不等于已发布。
6. 验收必须运行 `format_layout.py 定稿.html --all --check`；只跑 `--check` 不代表完整门通过。
7. 发布前图片必须加 Logo并压缩，作者供图和二维码按脚本白名单处理。

## 内容与归档

1. 版本、价格、时间、模型参数必须核实；不确定就标注，不编造。
2. 敏感议题避免煽动性和绝对化表述。
3. 作品库是单一真源；`articles.md`、dashboard、推荐卡不得手改。
4. archive 的元数据、词表或金句来源标记未通过时不得写盘。
5. 官网同步只执行 profile 明确配置的命令；朋友圈只生成文案，不自动发布。

## 失败语义

- 修复当前错误后重跑同一命令，不跳阶段。
- 同一阶段连续失败三次，停止扩展动作并报告现场。
- 草稿 ID 已生成但读回失败时保留 `_release-attempt.json`，重试不得重复创建草稿。
- 任何 prompt、图片、HTML 或 meta 漂移都会使相应 receipt 失效。
