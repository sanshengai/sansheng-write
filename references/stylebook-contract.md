# 画风手册文章合同（显式试用）

仅作者明确选择叁笙画风手册时使用。继续用本篇 `visual-plan.json`；无选择时旧 schema1 宝玉合同原样运行。画风手册 peer Skill 必须已安装，环境变量 `SANSHENG_STYLEBOOK_ROOT` 可指定实际本体。

## 当前可执行的步骤

同一任务单采用 `schema_version: 2`、`workflow: stylebook-v1`：

- `source.sha256`：`定稿.md` 的确切字节摘要；`source.author_content_sha256`：只去注册机器装配块后的作者正文摘要，使用 `assemble_release.author_content_sha256` 计算。
- `article_plan`：画风手册 v3/wxillus 的完整文章计划，`source.path` 指向当前 `定稿.md`。全文 coverage、原文引用和图意按画风手册验证，允许零张正文图。
- `group.style`：带修订号的样式，例如 `C31@r4`；与 `article_plan.style.code` 及封面一致。`group.palette` 与文章计划、封面一致；未调整时省略。逐图手动例外沿用画风手册原有显式规则。
- `cover`：独立的 `wechat-cover-head` 编译清单，绑定同一原文摘要，验收封面承担的主题与标题要求。
- `renderer.backend`：`host-imagegen` 或 `stylebook-service`。当前正式适配只会为前者创建待宿主执行的请求；后者明确报未实现，不自动换后端。

在本篇目录运行 `pipeline.py compile-visuals`。新路径输出 `素材/render-batch.json`、`素材/visual-compile-receipt.json` 和 `素材/stylebook-requests/<摘要>.json`；历史请求不可覆盖。保存完整编译词、参考图职责与实际文件摘要、制作清单、画风方法文件和适配器摘要；原文字节另存于不可变 `素材/stylebook-sources/<原文摘要>.md`。编译方言的 model 不充当实际调用模型。

接着运行 `pipeline.py render-visuals`：对当前原文、任务、方法、参考图和实际编译词重新核验，输出完整内置生图调用参数。`--only 01` 只准备指定图片。CLI 返回码 **3** 表示 `pending_host`，尚未生成成品；实际底层模型和费用保留 null。宿主不能将这一步当作生成成功或继续封存。

## 回收宿主原始输出

宿主按保存的 `call` 完整调用 `image_gen.imagegen` 后，将实际返回说明与输出文件保存为结果 JSON，再运行 `pipeline.py collect-stylebook-result --result <结果.json>`。结果字段为：`schema_version: 1`、`backend: image_gen.imagegen`、`invocation_status: succeeded`、`host_request_path`（本篇不可变请求路径）、`host_request_digest`（该 JSON 对象的 canonical SHA，调用 `stylebook_workflow.digest` 计算）、`request_id`、`id`、完整 `call`、非空 `tool_output`（实际返回说明）、`output: {path, sha256}`（PNG 原始输出；相对路径从结果 JSON 所在目录解析）。不能把旧样图或最终排字图填入原始输出。所有候选按字节摘要保存，重复回收同一结果幂等，不覆盖已有候选。

CLI 能核对请求、原文、方法、参考图与输出字节，但无法独立证明宿主工具曾执行，因此记录 `source_strength: host_attested`、`independent_invocation_verified: false`。回收只达到 `raw_collected_pending_production`；不生成最终成品或通过 QA 的凭证。

## 最终候选与正式消费者

回收后运行 `pipeline.py produce-stylebook-candidate --raw-receipt <不可变回收凭证.json>`。它核对当前原文、计划、完整请求和原始图片，使用画风手册实际导出与排字器，输出版本化的最终候选及 `production.json`。凭证绑定实际字体文件、图层、制作代码和输出字节；输入在制作期间改变时拒绝交付。重复制作同一输入幂等；已保存候选被改坏时拒绝覆盖。此时状态仍是 `produced_pending_qa`，不会填充正式 `素材/cover.png` 或装配文章。

接着运行 `pipeline.py review-stylebook-candidate --production <production.json>`。它独立调用画风手册当前配置的看图后端，核对画风、逐字文字、内容要点、最终方形裁切（适用时）及文字碰线、多余软件标记。返回码 0 为通过、1 为真实验收不通过且已保存报告、2 为无法完成验收。失败报告同样不可覆盖。验收前后绑定最终图片、全部制作依赖、实际合同、预览及验收代码；`stylebook_review.verify_candidate_review` 是后续消费者复核旧报告的入口，任何绑定输入变化都须重新验收。

实际底图留白与计划文字区不一致时，可运行 `pipeline.py refit-stylebook-candidate --raw-receipt <原始回收凭证.json> --layout <布局.json>`，调整现有排字。布局格式为 `{"version":1,"items":[{"box":[0.1,0.2,0.8,0.15]}]}`，items 与原文字项数量及顺序相同，每项仅允许 `box`、`font_px`、`min_px`、`align`；box 使用画布比例，字号使用像素。不得改变文案、画风、字体或降低原计划的最小字号。入口保留原始调用与底图，冻结布局及实际制作方法，生成新的制作 ID；旧失败记录不改写，新图须重新独立验收。原始底图无法容纳必要文字时仍会拒绝制作，不能以缩小到最低字号以下通过。

模型通过与实际候选可用分别判断。看图发现模型漏判时，运行 `pipeline.py reject-stylebook-candidate --production <production.json> --reason <实际问题>`，绑定本张最终字节登记不可变异议，保留原模型报告。后续选图、装配与 seal 应调用 `stylebook_acceptance.verify_acceptable_candidate`，它同时检查独立报告及已知问题；有异议或异议文件损坏时拒绝。当前尚无撤回异议的入口，修图会形成新的制作 ID，旧失败候选继续保留。候选可用也不等于整组、全文计划或发布验收通过。

运行 `pipeline.py review-stylebook-plan` 会独立完整阅读定稿，逐张复核配图位置、内容忠实度、形式和阅读价值，并另行检查封面主题与额外承诺。正文图允许为零；任何一项不通过或遗漏需配图的内容时，全文复核不能通过。报告绑定原文、完整计划、参考图、制作请求与复核代码；当前仅复核文字上下文，不宣称已经看过文章中的原始截图或照片。

运行 `pipeline.py select-stylebook-group --plan-review <全文报告.json> --report cover=<封面报告.json> --report 01=<正文图报告.json>` 选择完整组。`--report` 可重复；必须恰好覆盖本篇全部图片 ID。入口重新检查全文报告、每张最终图的独立 QA、已知异议及是否属于同一当前制作请求，保留不可变选图快照，并写入当前 `素材/stylebook-selection.json`。原文、计划、成品、报告、方法或实际问题改变后，`stylebook_group.verify_group` 会拒绝旧选择。选中整组状态仍是 `group_selected_pending_assembly`，不代表装配或发布通过。

运行 `pipeline.py assemble-release` 会先重新核对完整选图，再将选定封面与正文图放到正式引用路径，并按每张图的确切位置引用插入机器图片块。冻结原文保持原字节；定稿中的作者字符保留顺序，不移动原始照片、截图或音频块。引用必须唯一命中段首或段末；含糊位置拒绝装配。装配结果、当前选图及最终图片摘要写入不可变 `素材/stylebook-assemblies/<摘要>.json`，当前凭证为 `素材/stylebook-assembly.json`，状态仍是 `assembled_pending_release_review`。

`stylebook_assembly.verify_assembly` 重新复核全文及逐图验收、当前选择、冻结原文和实际成品，要求定稿逐字等于从冻结原文重建的装配结果。正文摘要相同但替换了图片引用、多插了机器块、改变了正文或成品字节时均拒绝。各图 QA 与全文报告绑定冻结来源，合法插图不会使其失效；原文改稿须重新制定计划、编译并验收。旧请求没有冻结来源时明确失效，不自动补造历史凭证。

装配后运行 `pipeline.py visual-qa`，会重新核对全文计划、每张图的独立报告、已知异议和确切装配，生成 schema2 汇总。该步骤没有新增模型调用，明确记录 `additional_independent_review: false`，保留实际逐图及全文复核来源；不宣称完成整篇阅读验收。零张正文图同样须有合格封面及全文计划，不能以空资产清单通过。

随后运行 `pipeline.py seal visual`，封存上述汇总及最终字节，保存不可变 `素材/stylebook-visual-seals/<摘要>.json` 和当前视觉凭证。`evidence.verify_visual_receipt` 在消费者入口重新验证整个来源链；修改正文、正式图片、验收报告、选图、装配或新增真实异议后，旧封存会失效。状态为 `visual_sealed_pending_reading_review`；仍须实际整篇阅读验收。旧预览、待生图请求与手工复制的历史样图不能进入正式 seal。

正式发布检查与整篇阅读凭证仍在实施，默认路线尚未切换。现有 schema1 宝玉路径继续按原合同独立验收；不能因为新路径编译或单图通过就声称写作正式发布已经可用。

真实文章验收须继续完成：全文计划独立复核 → 实际生图及来源 → 最终排字/结构制作 → 绑定最终字节的 QA → 作者正文不变的装配 → seal → 整篇阅读候选。公众号提交只在另有对应授权及发布合同满足时执行。
