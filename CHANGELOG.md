# Changelog

本项目的变更记录。版本号遵循 [semver](https://semver.org/lang/zh-CN/)。

## [未发布]

## [0.2.0] -- 2026-07-11

### 新增

- **人工检查点闸门（`workflow.checkpoints`）**：profile 的 `brand.yaml` 可配
  `workflow: { checkpoints: [blueprint, draft] }` --
  **blueprint 蓝图闸**（大纲 + **5 套「外标题 + 封面文案」配套视觉方案**（每套 = 标题候选 + 配套封面 L1/L2 文案，
  成套呈现成套选定、不拆分交付）+ 开头候选一包交付，硬停等作者拍板，开头盲选并入此闸）；
  **draft 定稿闸**（磨稿 + 双外审修复后硬停等审读，过闸后配图→BGM→排版→草稿箱照旧零停顿）。
  `pipeline.py verify outline/writing` 硬查 `_blueprint-approval.md` / `_draft-approval.md` 锚点，
  闸上不在场 = 等（不自动续跑）；作者明说「免检」单次跳闸。**未配置 = 原全自动行为不变**。

### 修复

- **推荐阅读卡 cover 路径三兼容解析**（`<数据目录>/` 占位符 / 相对数据目录 / 旧库父目录基准）--
  修复历史作品库条目被判「无封面」导致文末推荐位 + 关注卡整体静默跳过
- **导读栏 logo 自动补齐**：`素材/logo-white.png` 缺失时排版自动从 `profile/brand/logo.png` 拷贝
  （lead 模板硬引用该文件，此前每篇导读栏 logo 均裂图）
- **`***粗斜体***` 降级为禁用**：md 转换器会把 CJK 粗斜体吃成空 `<em>`、标记文字整个消失（实战实证），
  重点标绿一律用 `<mark>` 标签（writing.md / layout.md 已同步）

## [0.1.2] -- 2026-07-11

发布后的第一轮全面复核（5 维度审计 + 逐条对抗校验，39 项发现全部修复/处置）。

### 新增

- **三套新预置主题**：`jade`（青玉绿）/ `amber`（琥珀赭）/ `plum`（梅子紫），预置主题增至六套
- **OpenAI 兼容生图兜底实装**：`gen_img.py --provider openai -m <模型>`（此前文档承诺但未实现）；
  新增 `--dry-run` 打印请求摘要；`setup_check` 对兜底做真实探测，不再发假绿灯
- **快速上手一页化** + 依赖矩阵点名 baoyu-skills（安装命令、双 `.env` 体系、微信凭证正确位置）
- **缺微信凭证的落盘降级路径**写入 publish.md（含 IP 白名单提醒）

### 修复

- **换肤零残留**：`_THEME_DEFAULTS` 11 → 17 条（补 surface / text_strong + 4 个主色衍生 alpha），
  两段式替换防误染；ink/sage 等非默认主题不再混出钢青蓝
- **BGM**：key 读取接通仓根 `.env`（此前只读 shell env，正确实现是死代码）；无 key 时按承诺
  「跳过并明说」而非硬报错；docstring 凭证位置纠正
- **logo 水印**：`add_logo.js` 支持从仓根 `.env` 读 profile 指针；缺 logo 打印说明后跳过不再崩溃
- **`svg_to_png --check-brand`**：白名单从 profile 生效令牌动态生成（此前写死默认色，
  自定义主题下拒真放假；且大小写不一致连默认主色都匹配不上）
- **学习飞轮归位 profile 层**：playbook / lessons / observations 迁至 `<profile>/flywheel/`
  （个人数据不再写进 git 跟踪文件）；个性化规则由 prep_writing 解析注入，模型不再读固定路径
- **推荐阅读产物落数据目录**（含身份卡的个人数据不再写进仓库工作树）
- **作品库可 env 直指**：`SANSHENG_WRITE_WORKS_FILE` 支持指向你既有的 yaml
- `lint_templates` 调色板基线钉规范默认值（私有主题机上不再报满屏伪 WARN）；
  遥测 detail 字段在匿名态下同步打码文章名；biz_id/headimg 获取指引纠正
- cover-styles 残留的两处旧色值令牌化；封面/信息图不随主题自动换色已在文档明示

### 合规

- 两个校验脚本中与 gzh-design-skill（AGPL-3.0）近似的正则常量块**独立重写**
- 致谢补齐：gzh-design-skill、WeWrite、humanizer（此前只有 baoyu-skills）
- 一处真实文章引文按「逐字引文换原创例句」纪律改写为虚构等效例句

## [0.1.1] -- 2026-07-11

### 新增

- **发布后·朋友圈文案**（`references/publish.md`）：发布链路的最后一拍 --
  拿到正式链接、归档、部署后自动产出一条 3-4 行朋友圈文案（钩子 → 价值 → 固定引流尾巴）。
  尾巴走 profile（`identity.site` + `writing.moments_cta`），仓库里不含任何具体品牌 / 域名。
- **一份 `.env` 配齐**：`profile_config` 现在也能从仓根 `.env` 读 `SANSHENG_WRITE_PROFILE_DIR` /
  `SANSHENG_WRITE_DATA_DIR` 指针（`os` 环境变量仍优先）。换机器只需拷一份 `.env`。

### 修复

- `setup_check.py` 在 GBK 控制台（Windows 默认）打 emoji 会崩，补 UTF-8 stdout 兜底。

### 测试

- `conftest.py` 与 `regression_baseline.py` 显式把测试钉死在 `profile.example` + 临时数据目录，
  与本机 `.env` 隔离，保证冻结 fixture（断言中性默认色）的确定性，且任何测试都不碰真实数据。

## [0.1.0] -- 2026-07-11

首次公开发布。这个 skill 在作者的真实写作流里跑了半年多，现在脱敏开源。

### 有什么

- **写作方法论全链路**：选题快评 → 大纲（含开篇策略分流）→ 正文 → 改稿 → 标题锻造
- **反 AI 味三层过滤**：套话黑名单 / 换模型语义差分外审 / 写作核心六条
  （So What 兑现、类比落地、反常细节锚、把自己写笨、段落具体领头、句间引力）
- **排版工程**：一键把 markdown 转成微信公众号能吃的 HTML，10 个组件模板；
  契约门（`scripts/contracts.py`）在产出不合规时直接 `exit 2`，不让你发出去
- **三套预置主题**：`slate`（默认，钢青）/ `ink`（近墨黑）/ `sage`（草木绿）。
  改一行 `theme:` 整套换皮，模板里不用动一个 hex
- **BYO 语料**：自己蒸馏想模仿的作者手册放进 `profile/corpus/authors/`；
  改稿飞轮（`scripts/learn_edits.py`）从你的手改 diff 里提炼规则，越用越像你
- **三层分离**：代码在仓里，品牌 / 身份 / 语料在你的 `profile/`，密钥在 `.env`。
  仓库里没有任何人的私密内容
- **提交前护栏**：`.githooks/pre-commit` 拦下形似密钥的内容与个人路径

### 设计上的诚实声明

不喂料时，产出接近通用 AI 写作 -- **这是设计，不是缺陷**。
风格是你的语料长出来的，不是提示词变出来的。仓内自带的
`profile.example/corpus/voice-samples.md`（本项目原创撰写）只提供基础的去 AI 味兜底。

### 不含什么

- **不含任何真实作者的风格手册或作品节选**。版权是一层原因；更重要的是，
  模仿谁该由你自己挑。取而代之的是一份「怎么自建手册」的 HOW-TO 和一份虚构作者的示例
- **不含任何真实文章作为测试夹具**。所有 golden 都是合成的（`tests/golden/_synthetic_*/`）
- **不捆绑任何第三方源码**。`jimp`（MIT）等运行依赖由你 `npm install` / `pip install`

[0.1.2]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.2
[0.1.1]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.1
[0.1.0]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.0
