# Changelog

本项目的变更记录。版本号遵循 [semver](https://semver.org/lang/zh-CN/)。

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

[0.1.0]: https://github.com/sandypoli-boop/sansheng-write/releases/tag/v0.1.0
