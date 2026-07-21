# 发布与沉淀

> 定稿排版完成后的发布流程、图片管理规则和内容沉淀。

> 本阶段由编排器单线程执行；契约见 references/orchestration.md；正文逻辑不变（orchestrator=off 与既有完全一致）。

## ⚠️ 发布前置条件（强制检查）

**本阶段只能在以下条件全部满足时执行：**

1. ✅ **排版已完成**：工作目录存在 `定稿.html`，且已通过 layout.md 步骤 4 的全部检查（品牌色一致性、导读栏、H2 格式、表格样式、封面图、推荐阅读、关注卡片、信息图、水印、插图质量、系列一致性--共 11 项）
2. ✅ `定稿.html` 包含 **profile 生效主题色**（`colors.primary`，跑 `python scripts/profile_config.py` 可查；默认 slate 为 `#2F6F8F`）、组件模板、导读栏等

**如果工作目录中只有 `定稿.md`，还没有 `定稿.html`，说明 layout 步骤未完成。** 此时拒绝发布，提示用户先走排版流程。

> 排版完整性详细检查项在 [layout.md 步骤 4](layout.md) 中维护（11 项），此处不重复。

---

## 校对规范（定稿后、发布前）

### 允许保留的非标准用法（勿改）

| 用法 | 说明 |
|------|------|
| `--` 双连字符 | （**极度重要**）主理人固定标点风格，凡是代表破折号、副标题连接的，一律使用英文字符 `--`（双减号），绝对禁止出现中文的 `——`（长破折号）或 `—`（单一横），也不要被转码程序自动替换 |

### 校对只改以下类型

1. **错别字**：如"毋容置疑" → "毋庸置疑"（成语写错字）
2. **明显病句**：主谓不搭、逻辑断裂
3. **数字前后矛盾**：同一数据在文中出现两次值不同

写作/磨稿阶段的改稿规则见 [writing.md](writing.md)，这里只处理定稿后的最终校对。

---

## baoyu skills 调用

> **调用约定**：通过 Skill 工具调用时统一带 namespace 前缀 `baoyu-skills:<name>`（如 `baoyu-skills:baoyu-cover-image`）。下表的简短名是描述用，实际调用要带前缀。详见 memory `feedback_plugin_skill_namespace`。

| Skill | 用途 |
|-------|------|
| `baoyu-markdown-to-html` | MD → 微信排版 HTML |
| `baoyu-post-to-wechat` | 发布到微信公众号 |
| `baoyu-cover-image` | 生成封面图 |
| `baoyu-image-gen` | 通用 AI 生图（hero / bgm_cover 等小图） |
| `baoyu-article-illustrator` | 3c 概念解释配图 |
| `baoyu-infographic` | 3e 全文贯穿信息图（≥4 张） |
| `baoyu-diagram` | 3g 精确流程/时序/架构图（按需，需走 svg_to_png.py） |
| `baoyu-xhs-images` | 小红书图片 + 微信图文通用 |
| `baoyu-slide-deck` | 幻灯片 |

### 微信发文默认设置

- 主题色：`profile/brand.yaml` 的 `colors.primary`（默认 slate 为 `#2F6F8F`；换主题后以生效值为准）
- 作者：取自 `profile/brand.yaml` 的署名字段
- 发布方式：API 首选
- 评论：开启，所有人可评论
- **原文链接（「阅读原文」= `content_source_url`）**：走 profile，默认指向官网，见下节

### 「阅读原文」默认值（走 profile，不硬编码）

微信 `draft/add` API 的 `content_source_url` 就是读者点「阅读原文」后跳转的地址（`baoyu-post-to-wechat` 的 `--source-url` 直通此字段）。发布时按下面顺序解析出一个 URL，**显式带 `--source-url`**：

1. 该文 `article-meta.yaml` 若有 `source_url` 字段 → 用它（值可以是完整 URL，或关键字 `treasure` / `default`）；**工具 / 自研 skill / GitHub 仓库类**文章要把「阅读原文」指向宝藏页，就在这里显式写 `source_url: treasure`；
2. 否则一律取 `profile` 的 `publish.source_url_default`（官网首页，**默认**）——**文章内没特别说明就用官网首页，不再按文章类型自动走宝藏页**；
3. profile 对应值为空 → 不带 `--source-url`（保持微信默认，不报错）。

> 🔴 **赞赏（喜欢作者）无法在此固化**：微信 `draft/add` API **没有任何赞赏字段**，赞赏必须在公众号后台走「声明原创 → 选赞赏账户 → 勾选赞赏」的人工动作，API / 发布脚本都碰不到。发布档只负责把草稿推到草稿箱，赞赏由作者到后台手动开（账户微信编辑器会记住上次绑定的，无需每次重填）。

### 发文前必要操作

调用 baoyu-post-to-wechat 或 baoyu-markdown-to-html 前，先将自定义 CSS 覆盖到主题目录。详见 `~/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md`。

---

## 缺微信凭证时的降级路径（G-4）

没配公众号 appid/secret（在 **baoyu 侧** `~/.baoyu-skills/.env` 的 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`，
不是本仓 `.env`）时，发布档降级为**落盘交付**，链路不断：

1. 排版照常跑完，产物就是文章目录里的 `定稿.html`；
2. 打开微信公众号后台 → 新建图文 → 把 `定稿.html` 的正文区（`<div id="output">` 内）整体复制粘贴进编辑器；
3. 封面图手动上传 `素材/cover.png`；
4. 核对推荐阅读卡片与关注卡片渲染正常后存草稿。

⚠️ 配好凭证走 API 推送时，公众号后台还需把本机出口 IP 加入「IP 白名单」（后台 → 设置与开发 →
基本配置），否则 40164 报错。

## 发布执行

### 发布前脚本（必须按顺序执行）

脚本用法详见 layout.md 步骤2a（format_layout.py）和步骤3（add_logo.js）。

1. **`format_layout.py --all`** -- 一键后处理（H2格式、表格品牌化、导读栏、推荐阅读、品牌色清洗）
2. **`add_logo.js`** -- 给 AI 配图加水印（**排除** hero.png 和 bgm_cover.png--尺寸太小，打水印影响观感）
3. **`baoyu-post-to-wechat`** -- 发布到微信草稿箱

```bash
# 发的是已排版的 定稿.html（无 frontmatter）→ 必须显式 --cover，否则封面取不到
# --source-url 按上节「阅读原文默认值」解析出的 URL 显式带上（默认官网；要走宝藏页在该文 article-meta.yaml 显式写 source_url: treasure）
baoyu-post-to-wechat 定稿.html --cover 素材/cover.png --source-url "<按上节解析出的 URL：默认走 profile.publish.source_url_default>"
```

🔴 **发 html 必须显式 `--cover 素材/cover.png`**：wechat-api 的封面 fallback 链是「CLI `--cover` → frontmatter `coverImage` → `imgs/cover.png` → 首张正文图」。但发布的 `定稿.html` 是 markdown→html 转换后的产物、**没有 frontmatter**，且封面在 `素材/cover.png` 不在 `imgs/`，所以不传 `--cover` 会直接报 `No cover image` 中断。

| 发布方式 | 封面图处理 |
|---------|-----------|
| API 方式（发 .md）| 脚本读取 frontmatter `coverImage` 字段自动上传 |
| API 方式（发 .html）| **必须显式 `--cover 素材/cover.png`**（html 无 frontmatter，本次实战路径） |
| 浏览器方式 | **不支持**自动设置封面，必须在微信后台手动上传 |

🔴 **改稿重推 = 新增草稿，不覆盖旧草稿（2026-07-21 实战固化）**：wechat-api 每次推送都在草稿箱新建一条，不会替换同标题旧稿。改稿重推后**必须去微信后台删掉旧版草稿**，否则两篇并存容易发错。建议推完新稿后顺手把 media_id 记进 `pipeline.py done publish draft_media_id=...`（会覆盖 state 里的旧值）。

---

## 完整发布流程（排版→发布→更新库）

1. 确认 `定稿.md` 正文已定稿（封面图 + 信息图已生成）
2. **MD→HTML 转换** -- `baoyu-markdown-to-html 定稿.md`
3. **执行 `format_layout.py --all`** -- 一键后处理（导读栏、H2、表格、推荐阅读、品牌色）
4. **执行 `add_logo.js`** -- 给配图添加水印
5. 调用 `/baoyu-post-to-wechat` -- 发布到微信草稿箱
6. **归档入库** -- 运行 `pipeline.py archive`：写一条记录进 `<数据目录>/works.yaml`（按 category 自动分配 code），并自动刷新 `articles.md` + `作品库看板.html`（旧的「手动覆写 articles.md」「add_published_article.py」均已废弃）
7. **沉淀内容** -- 更新金句库和风格库

---

## 图片管理规则

- 所有 AI 生成的图片统一存到 `<文章目录>/素材/`（即 `<数据目录>/{N}-{选题名}/素材/`）
- 文件名有意义：`cover.png`、`section_1.png`、`infographic-01.png`
- 定稿.md 中引用图片使用相对路径 `素材/xxx.png`
- 不能散落在其他位置

### 手机边框规则

- 9:16 竖版截图 → 加 `profile/brand/phone-frame.png` 边框
- 16:9 横版插图 → 不加边框

---

## 发布前 Checklist

> **重要规则：任何对 `定稿.md` 的修改，都必须重新走完 layout 步骤，再发布 HTML。绝不能直接用 MD 发布或跳过后处理步骤。**

### 第一步：自动化预检（强制后台执行）

```bash
python $SKILL/scripts/format_layout.py 定稿.html --all --check
```

> **系统自律要求**：AI 将隐式执行此命令自动检查品牌色、组件完整性、关注卡片 padding、图片属性。
> 🔴 **必须带 `--all`**：preflight 契约门（`verify_publish_assets`/反 AI 腔/半角/prep/冷读外审）只在 `--all`（或 `--h2`）路径触发--**裸 `--check` 只跑品牌色/组件/加粗自检，不等于过了发布契约门**（与 SKILL.md「发布工具脚本」表口径一致）。
> ❌ 如果输出红色的 Error 报错，AI 将**自行中断发布进程**，并调用底层读写工具自动修复 `定稿.html` 直至通过。绝不抛出错误让用户去手动排查。

### 第二步：内容质量安全巡检（AI 自审名单）

AI 在推往草稿箱前，必须自行建立质检线程打卡：
- [x] 正文确实无禁用词和 AI 翻译腔痕迹？
- [x] 所有引用的硬核数据已配有合法来源？
- [x] 图片生成没有遗漏打上 `add_logo.js` 的水印？

### 第三步：配套物料确认

- ☐ 封面图已生成（`素材/cover.png`）

---

## 定稿验收：主旨反推自适应断路器 (Fail-Safe)

发布前系统必须执行"闭卷反向校验"：

1. **反推主旨**：AI 在看不到大纲的情况下，对当下的成品 `定稿.md` 反向提取出 50 个字的核心观点。
2. **阻断标准**：
   - ✅ 提取出来的观点具有强认知红利和信息增量 → 允许放行。
   - ❌ 提取出来的只是一通百搭的真理废话（如"AI 很重要"）→ 触发断路器！AI **自动终止发布**，退回重写逻辑，并且不得提示用户“您要我重写吗”，直接进行底层改造重塑。

---

## 发布后沉淀

### 1. 归档入库（`pipeline.py archive`）

**时机：** 拿到最终微信永久链接、且 `pipeline.py done publish wechat_url=...` 已写入后。

> 🔴 旧流程（AI 手动覆写 `articles.md`）已废弃。现在 **`<数据目录>/works.yaml` 是唯一数据源**，`articles.md` 是它的自动生成视图，**禁止手改 articles.md**。

**操作步骤：**
1. 确认 `article-meta.yaml` 已填 `category`（分类代码，见 profile 的分类体系）/ `tags` / `digest`
2. 在文章目录运行：`pipeline.py archive`
   - 自动写一条记录进 `<数据目录>/works.yaml`（按 category 分配 code，如 `AIT-08`，分类内独立计数、发布即冻结）
   - **自动刷新** `articles.md` + `作品库看板.html`
3. `pipeline.py verify archive`（按 code 校验已入库）
4. 同步在 `profile/corpus/金句库.md` 注入本次的高光段落

---

### 2. 自动生成推荐文章 HTML

**时机：** `articles.md` 覆写完成后，调用 `generate_recommend_html.py` 重生成 `<数据目录>/recommend_articles.html`（个人数据落数据目录，不进仓）。

**自动执行步骤：**
1. ✅ 从 `<数据目录>/works.yaml` 按「一三五」规则取已发布第 1 / 3 / 5 篇（按发布日倒序，跳过第 2、4 篇，**需 ≥5 篇「有封面」的已发布文章**；缺封面顺延就近、不足则该区块静默跳过）

> ⏱ **时序说明**：footer/推荐卡片在**排版阶段**注入（读 `works.yaml`），而本篇要到**发布后 `pipeline.py archive`** 才入库--所以推荐卡片读到的是「上一批已入库文章」，**本篇自身不会出现在自己的推荐里，这是设计而非 bug**。
2. ✅ 提取标题、摘要、封面、链接
3. ✅ 按照微信排版样式生成 HTML
4. ✅ 输出到 `<数据目录>/recommend_articles.html`，可直接粘贴到 `定稿.html`

**生成的 HTML 样式：**
```html
<!-- 推荐阅读 -->
<section style="margin: 48px 8px 0;">
  <section style="text-align: center; margin-bottom: 20px;">
    <section style="display: inline-block; font-size: 17px; font-weight: bold; color: #333333; letter-spacing: 2px;">推荐阅读</section>
    <section style="width: 56px; height: 4px; background: #2F6F8F; border-radius: 2px; margin: 8px auto 0;"></section>
  </section>
  <!-- 三篇推荐卡片自动生成（纯封面版）：每篇 = 一张全宽封面长条 -->
  <!-- 结构 <section><a href><img width:100%></a></section>，整图可点击跳转，无右侧文字 -->
</section>
```

**使用流程：**
```
pipeline.py archive（写 works.yaml + 自动刷新 articles.md/看板）
  ↓
执行 generate_recommend_html.py（读 works.yaml）
  ↓
recommend_articles.html 重生成 ✅
  ↓
打开 定稿.html → 替换 <!-- 推荐阅读 --> 区块 → 完成 ✨
```

---

### 3. 沉淀内容素材

1. 将好句子追加到 `profile/corpus/金句库.md`
2. 如有新风格发现，更新 `profile/corpus/风格示例库.md`
3. 系列文章确认下期预告和发布节奏

---

## 发布后交付

**用户需要的信息：**

1. **正式发布链接** -- 作品库 (`works.yaml`) 中对应作品的微信永久链接
2. **入库确认** -- 已写入 `<数据目录>/works.yaml`（自动分配 code，如 `AIT-08`），并刷新 `articles.md`/看板
3. **推荐卡片状态** -- 最新三篇文章列表（用于后续推荐卡片更新）

**交付格式：**
```
📰 发布完成

文章：[标题]
链接：[微信链接]
发布时间：[时间]

📋 已入库：<数据目录>/works.yaml（已自动刷新 articles.md + 作品库看板.html）
推荐卡片当前 TOP 3：[最新三篇文章列表]
```

---

## 发布后·朋友圈文案

发布链路的最后一拍：拿到正式链接、归档入库、部署完成之后，**自动产出一条朋友圈文案**
供作者复制（只出文案文本，不自动发朋友圈 -- 朋友圈没有开放发布 API）。跟 `publish` / `archive`
共用「你发正式链接」这一个触发词，一口气跑完，无需额外指令。

**为什么带它：** 朋友圈是把已发文章推向私域的顺手一步，跟发布同一条生命周期；产物是 3-4 行轻文案，
与小红书的多图轮播分镜形态差别很大，所以归本节、不进小红书拆图流程。

### 文案标准

| 要素 | 规则 |
|---|---|
| **版本数** | 🔴 **只出一版**，直接给终稿；不提供候选 / 备选 / 多版钩子让作者挑（朋友圈不同于开头盲选） |
| **篇幅** | 正文 **2-3 个短句** + 1 行固定尾巴；一句一行，句子都要短 |
| **结构** | 首句钩子（数字反差 / 成果 / 反常问句）→ 1-2 句价值（谁能用上、解决什么）→ 末行固定引流尾巴 |
| **固定尾巴** | profile 的 slogan CTA（引读者去自有阵地，不甩公众号链接）。取值见下方「尾巴取值」 |
| **emoji** | 🔴 **每句句首各带 1 个 emoji**（含尾巴行），一句一个；只放句首、不夹在词中间、句中不再加 |
| **语气** | 口语真人感，不用营销号腔（延续去 AI 味）；破折号统一 `--` |

### 尾巴取值（走 profile，不硬编码）

固定引流尾巴由 profile 提供，**公开仓不含任何具体品牌 / 域名**：

- 官网地址 = `profile` 的 `identity.site`
- 引流那句话 = `profile` 的 `writing.moments_cta`

两者任一为空则该行省略。示例（中性）见 `profile.example/brand.yaml`；填成你自己的官网 + CTA 即生效。

### 产出格式

```
[emoji] 钩子句：一句话把最抓人的成果 / 数字 / 反常点抛出来
[emoji] 价值句：这东西谁能用上、解决什么，说人话（1-2 句，凑够 2-3 句正文）

[emoji] {writing.moments_cta}
```

- 每句句首各 1 个 emoji（含尾巴行），emoji 按当句语义现挑、不写死；正文 2-3 句、只一版。
- 末行只发 `writing.moments_cta` 一行（前面补 emoji）；若它**未**包含官网地址，才补一行 `identity.site`
  （避免同一域名出现两次）。两者都为空则不带尾巴。

