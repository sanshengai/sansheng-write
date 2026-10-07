# 画风库文章合同（schema2，新文章推荐路线）

新文章的配图默认走这条路线：`visual-plan.json` 写成 schema2，`renderer.backend` 用 `stylebook-service`（无人值守，经画风库调用 Codex 内置生图，走订阅额度）。旧 schema1 宝玉合同保留给历史文章和显式选择，原样运行。画风库 peer Skill 必须已安装，环境变量 `SANSHENG_IMAGE_ROOT` 可指定实际本体。

## 当前可执行的步骤

同一任务单采用 `schema_version: 2`、`workflow: stylebook-v1`：

- `source.sha256`：`定稿.md` 的确切字节摘要；`source.author_content_sha256`：只去注册机器装配块后的作者正文摘要，使用 `assemble_release.author_content_sha256` 计算。
- `article_plan`：画风库 v3/wxillus 的完整文章计划，`source.path` 指向当前 `定稿.md`。全文 coverage、原文引用和图意按画风库验证，允许零张正文图。
- `group.style`：带修订号的样式，例如 `C31@r4`；与 `article_plan.style.code` 及封面一致。`group.palette` 与文章计划、封面一致；未调整时省略。逐图手动例外沿用画风库原有显式规则。
- `cover`：独立的 `wechat-cover-head` 编译清单，绑定同一原文摘要，验收封面承担的主题与标题要求。
  封面可选的风格：画风库 v0.4.0 起新增封面向风格（C74 丝网印海报、C75 暖纸克制双色、C76 杂志编辑封面、C77 叁笙深空等），选择器里按「公众号封面」用途列出，样图是标题写在图上的真实封面；不改写作 Skill 的默认。
  封面单独选画风：默认封面与正文同一画风。要用只做封面的画风（如 C90 深色系列封面：深色底、左侧品牌名＋系列标签＋大标题、右侧主体，适合做成系列的连载）时，在 `cover` 里写 `"own_style": true` 并把 `cover.style` 锁到该画风修订（如 `C90@r1`）；编译时对照叁笙生图本体，只接受「封面」用途里的画风，正文仍锁 `group.style`，色调不随整组。C90 直接出 2.35:1，不走方形扩图；次条或转发要的方形版、发 X 用的 16:9（`x-image`）各单独出一张，做法见画风库 `references/recipes.md` 第 1 节。
- `renderer.backend`：`stylebook-service`（推荐）或 `host-imagegen`。前者由 `render-visuals` 直接调用画风库的 `raw-generate` 出图并按下面的规则回收，回执标 `source_strength: pipeline_invoked`；后者仍返回码 3 等待宿主自己调内置生图工具。两者不互相自动替换。

在本篇目录运行 `pipeline.py compile-visuals`。新路径输出 `素材/render-batch.json`、`素材/visual-compile-receipt.json` 和 `素材/stylebook-requests/<摘要>.json`；历史请求不可覆盖。保存完整编译词、参考图职责与实际文件摘要、制作清单、画风方法文件和适配器摘要；原文字节另存于不可变 `素材/stylebook-sources/<原文摘要>.md`。编译方言的 model 不充当实际调用模型。

接着运行 `pipeline.py render-visuals`：对当前原文、任务、方法、参考图和实际编译词重新核验。`stylebook-service` 后端会立刻出图并把原始底图收回（返回码 0，状态 `raw_collected_pending_production`，下一步 `produce-stylebook-candidate`）；`host-imagegen` 后端输出完整内置生图调用参数，`--only 01` 只准备指定图片，CLI 返回码 **3** 表示 `pending_host`，尚未生成成品，实际底层模型和费用保留 null，宿主不能把这一步当作生成成功或继续封存。

## 回收宿主原始输出

宿主按保存的 `call` 完整调用 `image_gen.imagegen` 后，将实际返回说明与输出文件保存为结果 JSON，再运行 `pipeline.py collect-stylebook-result --result <结果.json>`。结果字段为：`schema_version: 1`、`backend: image_gen.imagegen`、`invocation_status: succeeded`、`host_request_path`（本篇不可变请求路径）、`host_request_digest`（该 JSON 对象的 canonical SHA，调用 `stylebook_workflow.digest` 计算）、`request_id`、`id`、完整 `call`、非空 `tool_output`（实际返回说明）、`output: {path, sha256}`（PNG 原始输出；相对路径从结果 JSON 所在目录解析）。不能把旧样图或最终排字图填入原始输出。所有候选按字节摘要保存，重复回收同一结果幂等，不覆盖已有候选。

CLI 能核对请求、原文、方法、参考图与输出字节，但无法独立证明宿主工具曾执行，因此记录 `source_strength: host_attested`、`independent_invocation_verified: false`。回收只达到 `raw_collected_pending_production`；不生成最终成品或通过 QA 的凭证。

## 最终候选与正式消费者

改稿后先重新编译当前计划。仅当保存的完整调用及参考图字节均相同，才可用 `pipeline.py reuse-stylebook-raw --raw-receipt <历史宿主回收凭证.json> --id <当前图片ID>` 复用底图。入口保留原始宿主回执、历史编译请求和原文快照，明确记录 `source_strength: host_attested_reused` 与 `reuse.new_invocation: false`，不虚构新生图。复用只得到当前版本的待制作凭证；仍须全文计划复核、最终制作与新的独立看图验收。提示词或参考图变化时拒绝复用；历史来源变化会令后续验收失效。

回收后运行 `pipeline.py produce-stylebook-candidate --raw-receipt <不可变回收凭证.json>`。它核对当前原文、计划、完整请求和原始图片，使用画风库实际导出与排字器，输出版本化的最终候选及 `production.json`。凭证绑定实际字体文件、图层、制作代码和输出字节；输入在制作期间改变时拒绝交付。重复制作同一输入幂等；已保存候选被改坏时拒绝覆盖。此时状态仍是 `produced_pending_qa`，不会填充正式 `素材/cover.png` 或装配文章。

接着运行 `pipeline.py review-stylebook-candidate --production <production.json>`。它独立调用画风库当前配置的看图后端，核对画风、逐字文字、内容要点、最终方形裁切（适用时）及文字碰线、多余软件标记。返回码 0 为通过、1 为真实验收不通过且已保存报告、2 为无法完成验收。失败报告同样不可覆盖。验收前后绑定最终图片、全部制作依赖、实际合同、预览及验收代码；`stylebook_review.verify_candidate_review` 是后续消费者复核旧报告的入口，任何绑定输入变化都须重新验收。

实际底图留白与计划文字区不一致时，可运行 `pipeline.py refit-stylebook-candidate --raw-receipt <原始回收凭证.json> --layout <布局.json>`，调整现有排字。布局格式为 `{"version":1,"items":[{"box":[0.1,0.2,0.8,0.15]}]}`，items 与原文字项数量及顺序相同，每项仅允许 `box`、`font_px`、`min_px`、`align`；box 使用画布比例，字号使用像素。不得改变文案、画风、字体或降低原计划的最小字号。入口保留原始调用与底图，冻结布局及实际制作方法，生成新的制作 ID；旧失败记录不改写，新图须重新独立验收。原始底图无法容纳必要文字时仍会拒绝制作，不能以缩小到最低字号以下通过。

模型通过与实际候选可用分别判断。看图发现模型漏判时，运行 `pipeline.py reject-stylebook-candidate --production <production.json> --reason <实际问题>`，绑定本张最终字节登记不可变异议，保留原模型报告。后续选图、装配与 seal 应调用 `stylebook_acceptance.verify_acceptable_candidate`，它同时检查独立报告及已知问题；有异议或异议文件损坏时拒绝。当前尚无撤回异议的入口，修图会形成新的制作 ID，旧失败候选继续保留。候选可用也不等于整组、全文计划或发布验收通过。

运行 `pipeline.py review-stylebook-plan` 会独立完整阅读定稿，逐张复核配图位置、内容忠实度、形式和阅读价值，并另行检查封面主题与额外承诺。正文图允许为零；任何一项不通过或遗漏需配图的内容时，全文复核不能通过。报告绑定原文、完整计划、参考图、制作请求与复核代码；当前仅复核文字上下文，不宣称已经看过文章中的原始截图或照片。

运行 `pipeline.py select-stylebook-group --plan-review <全文报告.json> --report cover=<封面报告.json> --report 01=<正文图报告.json>` 选择完整组。`--report` 可重复；必须恰好覆盖本篇全部图片 ID。入口重新检查全文报告、每张最终图的独立 QA、已知异议及是否属于同一当前制作请求，保留不可变选图快照，并写入当前 `素材/stylebook-selection.json`。原文、计划、成品、报告、方法或实际问题改变后，`stylebook_group.verify_group` 会拒绝旧选择。选中整组状态仍是 `group_selected_pending_assembly`，不代表装配或发布通过。

运行 `pipeline.py assemble-release` 会先重新核对完整选图，再将选定封面与正文图放到正式引用路径，并按每张图的确切位置引用插入机器图片块。冻结原文保持原字节；定稿中的作者字符保留顺序，不移动原始照片、截图或音频块。引用必须唯一命中段首或段末；含糊位置拒绝装配。装配结果、当前选图及最终图片摘要写入不可变 `素材/stylebook-assemblies/<摘要>.json`，当前凭证为 `素材/stylebook-assembly.json`，状态仍是 `assembled_pending_release_review`。

`stylebook_assembly.verify_assembly` 重新复核全文及逐图验收、当前选择、冻结原文和实际成品，要求定稿逐字等于从冻结原文重建的装配结果。正文摘要相同但替换了图片引用、多插了机器块、改变了正文或成品字节时均拒绝。各图 QA 与全文报告绑定冻结来源，合法插图不会使其失效；原文改稿须重新制定计划、编译并验收。旧请求没有冻结来源时明确失效，不自动补造历史凭证。

装配后运行 `pipeline.py visual-qa`，会重新核对全文计划、每张图的独立报告、已知异议和确切装配，生成 schema2 汇总。该步骤没有新增模型调用，明确记录 `additional_independent_review: false`，保留实际逐图及全文复核来源；不宣称完成整篇阅读验收。零张正文图同样须有合格封面及全文计划，不能以空资产清单通过。

随后运行 `pipeline.py seal visual`，封存上述汇总及最终字节，保存不可变 `素材/stylebook-visual-seals/<摘要>.json` 和当前视觉凭证。`evidence.verify_visual_receipt` 在消费者入口重新验证整个来源链；修改正文、正式图片、验收报告、选图、装配或新增真实异议后，旧封存会失效。状态为 `visual_sealed_pending_reading_review`；仍须实际整篇阅读验收。旧预览、待生图请求与手工复制的历史样图不能进入正式 seal。

整篇阅读通过后运行 `pipeline.py accept-stylebook-reading --observation <真实阅读记录.json>`。记录使用 `schema_version: 1`，绑定 `html_sha256`，来源为 `host_attested_browser_and_native_reading`，`additional_independent_review: false`；这不是一次新的独立模型复核。`native_checks` 必须逐项确认 `whole_article_read`、`required_text_readable`、`no_clipping`、`consistent_style`、`cover_crops_checked`。没有看过或仍有问题时不得填 true。

`views` 保存 390、430、900 三个实际视口，分别记录 `width`、`viewport_height`、`document_width`、`document_height`；`images` 按 HTML 图片顺序保存实际本地绝对 `path`、`sha256`、`loaded`、`natural_width`、`display_width`；`screenshot` 为本篇目录内完整页面 PNG 的 `path` 和 `sha256`。程序检查加载、溢出、当前图像字节和截图尺寸；文字、裁切与风格结论仍由宿主实际阅读提供，不将截图存在误说成语义自动验收。

阅读入口绑定当前视觉 seal、整篇 HTML、全部本地图片、实际截图及阅读方法。它用 Python Markdown（`python3 -m pip install Markdown`）解析定稿，检查作者文字在 HTML 中完整且顺序保留，并绑定解析器版本；缺依赖时明确失败。发布前会重新核验 `素材/stylebook-reading-review.json`；缺记录、坏图、横向溢出、必要文字不清或任一绑定输入改变都拒绝。默认路线尚未切换，现有 schema1 宝玉路径继续按原合同独立验收；单图通过仍不能代表正式文章发布可用。

封面、正文图阶段及发布前视觉路由在显式 schema2 任务中调用当前完整计划的验收链，不再套用 schema1 的粘土风或至少四张图规则。正式目录中的 `infographic*.png` 必须恰好等于当前计划选中的正文图，零张正文图也必须有合格封面和全文复核；混入额外未验收图、缺图、旧报告或待生成请求均拒绝。导读小图、音频、HTML、上游审稿及归档等发布要求继续独立检查。

真实文章验收须继续完成：全文计划独立复核 → 实际生图及来源 → 最终排字/结构制作 → 绑定最终字节的 QA → 作者正文不变的装配 → seal → 整篇阅读候选。公众号提交只在另有对应授权及发布合同满足时执行。
