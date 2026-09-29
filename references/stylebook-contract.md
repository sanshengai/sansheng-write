# 画风手册文章合同（显式试用）

仅作者明确选择叁笙画风手册时使用。继续用本篇 `visual-plan.json`；无选择时旧 schema1 宝玉合同原样运行。画风手册 peer Skill 必须已安装，环境变量 `SANSHENG_STYLEBOOK_ROOT` 可指定实际本体。

## 当前可执行的步骤

同一任务单采用 `schema_version: 2`、`workflow: stylebook-v1`：

- `source.sha256`：`定稿.md` 的确切字节摘要；`source.author_content_sha256`：只去注册机器装配块后的作者正文摘要，使用 `assemble_release.author_content_sha256` 计算。
- `article_plan`：画风手册 v3/wxillus 的完整文章计划，`source.path` 指向当前 `定稿.md`。全文 coverage、原文引用和图意按画风手册验证，允许零张正文图。
- `group.style`：带修订号的样式，例如 `C31@r4`；与 `article_plan.style.code` 及封面一致。`group.palette` 与文章计划、封面一致；未调整时省略。逐图手动例外沿用画风手册原有显式规则。
- `cover`：独立的 `wechat-cover-head` 编译清单，绑定同一原文摘要，验收封面承担的主题与标题要求。
- `renderer.backend`：`host-imagegen` 或 `stylebook-service`。当前正式适配只会为前者创建待宿主执行的请求；后者明确报未实现，不自动换后端。

在本篇目录运行 `pipeline.py compile-visuals`。新路径输出 `素材/render-batch.json`、`素材/visual-compile-receipt.json` 和 `素材/stylebook-requests/<摘要>.json`；历史请求不可覆盖。保存完整编译词、参考图职责与实际文件摘要、制作清单、画风方法文件和适配器摘要。编译方言的 model 不充当实际调用模型。

接着运行 `pipeline.py render-visuals`：对当前原文、任务、方法、参考图和实际编译词重新核验，输出完整内置生图调用参数。`--only 01` 只准备指定图片。CLI 返回码 **3** 表示 `pending_host`，尚未生成成品；实际底层模型和费用保留 null。宿主不能将这一步当作生成成功或继续封存。

## 尚未完成的正式消费者

宿主实际调用的回收、最终制作与逐图 QA、装配、seal 及发布检查仍在实施。当前新路线的装配、旧宝玉 QA 和旧视觉凭证入口明确拒绝；旧预览、待生图请求与手工复制的历史样图不能进入正式 seal。默认路线尚未切换，写作正式可用不能由编译测试通过推断。

真实文章验收须继续完成：全文计划独立复核 → 实际生图及来源 → 最终排字/结构制作 → 绑定最终字节的 QA → 作者正文不变的装配 → seal → 整篇阅读候选。公众号提交只在另有对应授权及发布合同满足时执行。
