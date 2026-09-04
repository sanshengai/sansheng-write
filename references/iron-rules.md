# 铁律清单

原则：能由代码判断的规则只在代码中执行，本文只给人类一页索引。遇到冲突，以 `pipeline.py`、`contracts.py`、`visual_workflow.py`、`visual_qa.py` 的非零退出为准。

## 发布主链

1. 新文章必须经过 pipeline；不得手改 `.state.json`。
2. 作者定稿进入机械链时先有真实 `_draft-approval.md`（`审批结论：通过`），再跑
   `adopt-final`；接管只读并绑定审批 SHA/subject，禁止代签、覆写审批或伪造前半程审稿文件。
3. BGM 是发布硬门；缺 MP3、AUDIO-CARD 或 `_music-manifest.json` 就没完成，`skip bgm` 被拒绝。硬门校验文件与真实来源，不绑定厂商；旧歌换播放通道时不得伪造其 provider/model 出身。
4. `podcast.wechat_embed: true` 时，播客 MP3、PODCAST-CARD、同源生成摘要与人工插入后的官方读回凭证同为发布硬门；正常路径认 `draft/get` 草稿凭证。仅当文章已正式发布且草稿被回收时，才可用永久链接生成独立正式文章补验凭证：优先 `freepublish/batchget` + `freepublish/getarticle`；只有已发表内容 API 返回 `48001` 才可改用同一微信官方公开页 + 原官方草稿回执的显式证据链。两条路径都必须绑定双播放器身份、本地音频哈希与人工首尾试听，缺一项不得 `finalize`，也不得拿正式文章凭证冒充草稿凭证。
5. writing、cover、infographic、bgm、layout、publish 不可 skip；不存在 `--force`、`--legacy` 或作者授权例外。
6. 草稿箱唯一入口是 `release-to-draft`；非零退出时禁止直调发布接口。
7. 正式发布、原创和赞赏由作者人工完成；永久链接用 `finalize` 收尾。
8. 公众号首屏固定为「导读 → 主题曲卡 → 播客卡 → 正文」；两卡是同级选项、同宽上下排，不互相从属，也不做左右双栏。
9. `weave` 声明“开篇与文末”的地址必须以可复制明文各出现一次，且 `draft/get` 回读仍为两次。
10. 控制器是机械链唯一命令写者；模型只交付任务单候选与视觉 QA，不运行、重试或并发启动长命令。

## 视觉

1. 语义 producer 固定为 `sansheng-write.visual-planner`；`baoyu-image-gen` 只是 renderer。
2. 封面 `2.35:1`；Hero `1:1`；信息图首尾 `9:16`、中间至少两张 `16:9`。
3. 信息图与 Hero 一律 `claymation + warm-light-clay`，全站统一粘土风，不按题材分流。
   该签名配方只由 `scripts/visual_contracts.py` 定义；Baoyu 负责内容分析和布局，无权覆盖
   色板、材质、字形与明暗阈值，私有 profile 也不得覆盖。
4. 真人真事优先真实授权图片，禁止生成相似人物肖像，也禁止把真人照片喂给生图模型重绘成风格化肖像。
   封面需要真脸时走 `portrait-bleed`：renderer 只出底板、右区留空场，真实肖像由
   `scripts/cover_portrait.py` 确定性合成（与 `add_logo` / 压缩同属既有后处理层，按 `stage` 记账）。
   该层只许贴可追溯的真实人物照片、只许贴在右区照片位；贴文字、标签、logo 或图表一律禁止，
   封面上的字仍必须由生图模型原生生成。`cover_portrait` 缺 `source` 或 `license` 即拒绝合成。
5. 精确数字图、精确拓扑图走独立本地确定性代码路径，不得冒充封面 / Hero / 信息图，也不得进入其最终图证据集。
6. renderer fallback 只能按配置执行，prompt 和比例不可改变。
7. 最终图后处理后必须独立 `visual-qa` 并 `seal visual`；Markdown 勾选不算证据。
8. 信息图引用只由 `assemble-release` 写入带 marker 的机器块；正文变化仍会令 release job 失效。
9. `style_consistent` 不能代替目标风格验收；QA 必须通过 `style_contract_match`、
   `brand_palette_match`，封面另过 `composition_contract_match`。
10. 所有正文视觉均须由登记的生成式 renderer 原生生成；图中文字必须随画面一起生成，
    禁止以 `template_id`、SVG、HTML、Canvas、Pillow、本地模板或任何后期叠字替代，
    也禁止让模型另写 SVG 再转 PNG。生成失败只能按 policy 切换另一生成式 renderer，
    不能降级为确定性模板或拆分文字层。
11. 看图模型不是视觉发布的唯一授权者；没有实际对象、数量、位置和版式观察的
    布尔式 QA 不得放行。
12. `text_match`、`no_unexpected_text`、`style_contract_match` 不得从发布硬门移除；
    `required_text` 每条恰好出现一次。Hero 与最终 HTML 实际引用的所有生成图必须送审。
13. 同一发布任务中不得修改 QA 规则迁就现图；编译后 QA 代码发生变化时凭证失效。
14. Hero 与信息图必须分别留下 `baoyu-article-illustrator` / `baoyu-infographic`
    `method_sources` 与对应 SKILL 字节锚点；真实 `producer_chain` 只能是本仓 planner。
    封面走本仓 `montage-evidence`；把方法来源伪装成已执行 producer 同样拒绝发布。
15. 封面文字只认 `lead.line1/line2/accent/tag1/tag2`：五项必填，accent 必须是 L2 结尾，
    tag1/tag2 恰好两项。`lead.subtitle` 是文章导读，不得冒充封面标签。
16. 人物、品牌或作品为主题时填写 `cover_identity`，并把它写入 L1/L2；小标签不算显著出现。
16. renderer 必须经过 `baoyu-image-gen`；本仓原生 provider、任意命令覆盖与“写理由放行”均禁止。
17. `cover.png`、`hero.png`、`infographic-*.png` 必须是 `baoyu-image-gen` 直接返回的 PNG
    像素文件；SVG 转换器只服务独立精确图表，不得占用这些正式生成图槽位。

## 社媒分发

1. 小红书与微博按篇显式触发；正式链接生成或 profile 已启用，不等于自动授权社媒分发。
2. 图片也是文章：每套先确定一个传播命题，再编排页序；禁止把全文按段落切片或用空泛卖点凑页。
3. 小红书使用 `dist/xhs/images/` 的 3:4 专属图；微博使用 `dist/weibo/images/` 的 1:1
   专属图。两套不得互相复用、裁切、加边或回落公众号素材。
4. 文字、画面与可选 logo 必须由 `baoyu-image-gen` 在同一次请求中原生生成；禁止无字底图
   + SVG / HTML / Canvas / Pillow / 第二模型补字。
5. 先单张试片；总图数 ≥4 且 provider 支持时用 batch。错字或版式失败必须修 prompt 后整张重渲。
6. 小红书禁止 URL、二维码与站外行动指令；可在不含网址和行动动词时中性说明项目已在
   GitHub / 官网公开。微博可在正文直接放链接。
7. 微博的 140 字是首屏预算，不是全文硬上限；首段须独立成立，完整正文与九宫格共同交付信息。
8. 浏览器只预填标题、正文与图片；小红书「发布」和微博「发送」必须由作者点击。

## 排版

1. H2/H3 只写纯标题，不手写 PART、序号或装饰。
2. 破折号统一 `--`，避免全角破折号进入成稿。
3. 金句卡禁装饰引号；出处行使用弱化右对齐样式。
4. `hero.png` 只放标题后、导读前；音乐卡放导读后、正文前。
5. 正文图片必须实际嵌入 Markdown/HTML，素材目录存在不等于已发布。
6. 验收必须运行 `format_layout.py 定稿.html --all --check`；只跑 `--check` 不代表完整门通过。
7. 发布前图片必须加 Logo并压缩，作者供图和二维码按脚本白名单处理。
8. 文末固定顺序为“正文 → DEEP READ → SOURCES → 推荐阅读 → 关注卡片”。DEEP READ
   放强相关旧文与自有阵地；SOURCES 放正文实际使用的外部依据。启用项必须使用标准模板
   标记，普通 H2、裸 URL 或自画卡片均不得冒充。

## 内容与归档

1. 标题只走 title.md 的唯一公式：`分类标签 | 关键词锚点：一句由正文主干兑现的话`；冒号后四选一（原话型 > 具象型 > 处境型 > 定位型，后者配额制）。出候选必须同时给出锚点与兑现处。禁揭穿式反差整个句式家族、悬念卖关子、内部结构编号（N 章 / 第 N 期 / v 号）与标题党词。
2. 正文守 writing.md §三条直球守则：简洁、不延迟揭示到文末是不可豁免核（任何风格路由不豁免）；结论先行按开篇策略 + compact opt-out（资讯/成果第一句必须是判断；深度随笔可 opt-out 第一句，核心判断须在第一个 H2 之前）。冲突裁决 → writing.md §规则冲突优先级。磨稿减法 → polish-whitelist.md。
3. 版本、价格、时间、模型参数必须核实；不确定就标注，不编造。
4. 敏感议题避免煽动性和绝对化表述。
5. 作品库是单一真源；`articles.md`、dashboard、推荐卡不得手改。
6. archive 的元数据、词表或金句来源标记未通过时不得写盘。
7. 官网同步只执行 profile 明确配置的命令；朋友圈只生成文案，不自动发布。
8. 只要已有文章的朋友圈文案时走秒级快路，不启动 finalize、归档、官网、搜索或生图。
9. `archive` 只指作品库登记；永久目录搬运只走 `physical-archive`。永久根必须是独立绝对路径，`HANDOFF_DIR` 只做人工上传临时包，二者禁止混用。
10. 实体归档只能在所有文章写者退出后执行；目标冲突、复制期源文件变化或最终 SHA-256 复验失败时必须保留源目录。没有显式 `--delete-source` 不得删除，复验成功后也不在过程根与永久根长期保留两份同名成品。

## 失败语义

- 修复当前错误后重跑同一命令，不跳阶段。
- 同一阶段连续失败三次，停止扩展动作并报告现场。
- 草稿 ID 已生成但读回失败时保留 `_release-attempt.json`，重试不得重复创建草稿。
- 任何 prompt、图片、HTML 或 meta 漂移都会使相应 receipt 失效。
