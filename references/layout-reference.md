# 排版参考手册--底层机制、踩坑字典与表格规范

> **定位**：排版阶段的参考资料。**日常执行排版 SOP 时不需要加载此文件**--只在遇到样式异常、表格问题或微信过滤报错时按需查阅。
>
> 完整的微信兼容性规则数据库（标签白名单、CSS 过滤矩阵、图片规则等）见 [wechat-compat.md](wechat-compat.md)。
>
> 🎨 **所有颜色 / 圆角 / 边框 / 文字色的取值，以 [design-tokens.md](design-tokens.md) 为单一数据源**--改任何视觉值前先改那里。本文涉及的具体数值（主题色 #2F6F8F、圆角 6/8/10/12、浅色底等）都是 design-tokens 的落地，不要在这里另立新值。

---

## 微信渲染规则速查

**微信 = 去掉 CSS 层的纯 HTML。** 只有 `style=""` 里的硬编码值有效。

| 支持 ✅ | 不支持 ❌ |
|--------|---------|
| `<section>` + `style=""` | `<style>` 标签 |
| `float`、`display:inline-block` | `position: absolute/relative/fixed` |
| `border-*`、`border-radius`、`box-shadow` | `::before`/`::after` 伪元素 |
| `display:table` / `display:table-cell` / **`display:flex`** 🔴 | `display:grid`（未测，暂禁） |
| **`box-shadow`、`linear-gradient`（含渐变细线）** 🔴 | CSS 变量 `var(--xxx)` |
| **`overflow-x:auto/scroll` 横滑、`#ffffff`、`margin`** 🔴 | `@media`、`@keyframes` |

> 🔴 **API 路径实测校正**：标 🔴 的 `flex` / `box-shadow` / `linear-gradient` / 横滑 / `#ffffff` / `margin` 已在我方「API 直灌草稿箱」路径**真机实测可用**，推翻本表旧版「flex ❌ / 渐变不稳定」的经验教条。**权威依据与路径限定见 [wechat-compat.md §1.5](wechat-compat.md)**（「手动粘贴」是另一套净化器、不适用我方）。

**永远不要通过修改 CSS 文件影响微信显示。** 排版的本质是「检查和替换 HTML 属性值」。

---

## 踩坑字典（持续更新）

| 坑 | 错误做法 | 正确做法 |
|----|---------|---------| 
| 颜色变蓝 | CSS `var(--xxx)` | 硬编码 `#2F6F8F` |
| H3 圆点不显示 | `::before` + `position:absolute` | 真实 `<span>` 模拟 |
| H3 时间线内容缩进异常 | 时间线 `</section>` 漏写 | **确保开闭标签完整匹配** |
| 导读栏换行 | 标题 22px 过大 | 缩小到 18px，每行 ≤8 字 |
| 封面图在正文 | cover 嵌入 body | 删除 img 标签，后台设封面 |
| div 样式丢失 | `<div>` 做容器 | 改用 `<section>` |
| ~~flex 布局异常~~（作废） | -- | `display:flex` 已实测 API 路径可用，见 wechat-compat §1.5；旧 float/table-cell 模拟可逐步简化 |
| 图片无法被发布脚本识别/上传 | 仅写入相对路径 | 使用 API 脚本上传时需配合：`<img src="相对路径" data-local-path="绝对路径">` |
| Logo/图片绝对路径 src | `src="/abs/path/logo.png"` | 复制到素材目录，用相对路径 |
| Logo 用 height/max-width 撑大 | `<img style="height:16px">` | 用容器 width + `overflow:hidden` |
| 发布 47001 超限 | 直接发布 baoyu 输出 | 先压缩 HR 等冗余，控制 ≤19,000 字符。若文章极长（如>5万字），必须拆分为上下篇再做排版推送。 |
| 表格列不对齐 / 手机端挤成一坨 | 只在表头设宽度 | `--table` 自动处理：≥3 列缩 11px+放不下横滑、2 列术语转卡（2026-07-07，见「表格设计规范·分三路」）。仍宜精简单元格短语 |
| 推荐阅读历史封面长宽不齐 | HTML使用 auto / contain 适应原始尺寸 | 直接将卡片封面 HTML 定死宽屏规格并强制裁切。例如：`width:140px; height:79px; object-fit:cover;`。|
| 图表(非生图)或信息图未转换成图片 | 写 `<section><img>` 预留空 | Markdown中直接保留 `![图释](相对路径)` 的标准语法让 `baoyu-markdown-to-html` 自然解析即可。 |
| 序号圆点错位 | `::before` 伪元素 | `<span>` 做圆点，`vertical-align:middle` |
| ~~渐变分隔线不显示~~（作废） | -- | 渐变（含细线）已实测 API 路径可用，见 wechat-compat §1.5 |
| 自造不存在的 `--theme` 名报错 | baoyu 无此主题 | 用 `--theme default --color "#2F6F8F"` |
| 图片间白缝 | img 默认 inline | 所有 `<img>` 加 `display:block` |
| 关注卡片 API 报"信息错误" | `data-id` 少一个 `=` padding / 缺少外层 class 包裹 / 缺少组件 class 和 data-pluginname | **三要素缺一不可**：① `data-id="QWJjRGVmR2g=="` 双等号 ② `<section class="mp_profile_iframe_wrp custom_select_card_wrp">` 包裹 ③ `class="mpprofile js_uneditable..."` + `data-pluginname="mpprofile"` |
| 推荐阅读卡片在编辑器中变形 | `<a>` 包裹块级元素后进入编辑模式 | 方案A（`<a>` 包裹整卡）发布后正常但**不能在编辑器内二次编辑**；方案B（`<table>` + 分散式 `<a>`）更稳 |
| 排版阶段字符数"虚警" | 直接对排版 HTML 做字符数检查，含 `data-local-path` 绝对路径导致 57000 字符 | 发布脚本会替换为 CDN 短 URL 并删除 `data-local-path`，上传后约 16000 字符。日常**跳过检查**，仅超长文（>5万字纯文本）才做拆分 |
| `--takeaway` 正则吃掉多个 blockquote | `[\s\S]*?` 懒惰匹配跨越 blockquote/H2 边界 | 改用 `(?:(?!<blockquote\|<h[12])[\s\S])*?` 否定前瞻锚定边界；`<strong>` 改 `<strong[^>]*>` 兼容带 style |
| H2 纯数字起手标题（如"4 月涨价"）被剥离数字 | 排版脚本正则 `^\d+\s+` 过于贪婪误伤单数字 | 将正则收紧为 `^\d{2,}\s+`，只剥离明确的 `01 ` 等多位裸编号 |
| 封面图需要精确定制字体和高亮文字 | 让 renderer 自行决定字号与构图 | 在 `visual-plan.json` 明确文字、事实与禁用项，再由 `compile-visuals` 编译受限 prompt |

> **提示**：如果 Markdown 流程转换后发现自己需要插入 `导读栏`(lead-section) 和 `推荐阅读`(footer-recommended)，一定要把它们插入到 `<div id="output">` 这个主包裹体内。千万别直接扔在 `</body>` 的下面，否则会被微信直接丢弃！

---

## 微信公众号表格设计规范（固化标准）

微信公众号所有表格遵循以下规范，不得随意改变：

### 一、列数与宽度

🔴 **表格按列数/内容自动分三路，不再有「最多 2 列」硬禁（草稿箱实测锁定）**。`--table` 自动判定，作者不必手动改写：

| 列数/内容 | 自动呈现 | 字号 | 说明 |
|------|------|------|------|
| **≥3 列** | **11px 横滑表** | 表头 12px / 内容 11px | 列 px 总和 ≤~345px（≈3 列短内容）→ `width:100%` 铺满不滚；放不下（≥4 列或含长列）→ 外层 `overflow-x:auto` 横滑。多维度对比矩阵（N 模型 × M 能力）现为一等公民，不再禁 |
| **2 列「术语\|释义」型** | **术语卡**（左竖条） | 术语 15px 加粗 / 释义 14px | 左列短术语(≤11 CJK)、右列长释义(≥15 CJK 且显著更长)时自动转卡，绕开窄表挤压 |
| **2 列对称数据** | **12px 改良表** | 表头 13px / 内容 12px | 右列也短（如 季度\|营收）时保留表格 |

| 列宽规则 | 说明 |
|------|------|
| **列宽跟内容走（脚本按像素需求分配）** | `--table` 先估每列「单行排开」需要的像素宽（汉字=字号、ASCII≈0.6 字号、含 padding，表头按加粗算）：**放得下**就按需求比例铺满 100%；**放不下**先给每列保底（自身需求 / 3 个汉字宽 / 表头单行宽取合适的小值），剩余宽度按「超出保底的部分」比例分给长列——一字列（停/留、3、437 MB）只拿它需要的那点，长文列均摊折行，不会再出现「短列占 1/3、长列拉成十几行」。2026-09-15 起取代旧 sqrt 阻尼 + [15%,52%] 夹断。 |
| **`table_widths` 手动覆盖** | 觉得脚本分得不协调时，由大模型扫一眼每列最长内容填一组固定百分比进 `article-meta.yaml`（见下），覆盖优先于脚本估算。 |

> 多维度对比现直接用多列表（横滑兜底）；单元格仍尽量精简短语，横滑是防挤压兜底而非纵容长句。唯「术语｜整句释义」交给术语卡承接长文。

#### `table_widths`：大模型测算的固定列宽（article-meta.yaml）

```yaml
# 每个内容表一组列宽，按表在文中出现顺序对齐；数字会自动归一化到和为 100
table_widths:
  - [38, 62]        # 第 1 个表（两列）
  - [26, 46, 28]    # 第 2 个表（三列）
```

- `format_layout.py --table` / `--all` 自动读取，把宽度写进 **section 版格子**（`display:table-cell; width:X%`，见「微信兼容表格写法」一节——写在 `<td>` 上会被微信清掉）。
- 某个表不填、或组数/列数对不上 → 该表静默回退脚本的内容需求估算，不报错。
- 改了表的列数后记得同步改对应那组数字。

### 二、字体大小

| 区域 | 字号 | 说明 |
|------|------|------|
| 正文 | 15-16px（baoyu默认） | 基准字号 |
| **表头** | 2 列表 **13px 加粗** / ≥3 列横滑表 **12px** | 比内容大一号，作视觉锚（≥3 列横滑整体降一档见上「分三路」表） |
| **表格内容** | 2 列表 **12px** / ≥3 列横滑表 **11px** | 比表头小一号，压住换行、提手机端容量 |
| **内容精简** | -- | 🔴 单元格文字须**大模型精炼**（保留信息、非机械删词），目标每格 ≤20-22 字；`--check` 会对 >22 字的单元格出告警 |

### 三、视觉规则

| 规则 | 说明 |
|------|------|
| **表头** | 主题色 `#2F6F8F` 背景，白色文字，13px 加粗 |
| **第一列/首行** | 纯文字，**不加 emoji/图标**（图标只用在内容单元格里） |
| **重点内容** | 可在内容单元格中加 emoji（🥇✅❌等）或品牌色 `color:#2F6F8F` 加粗高亮 |
| **交替行色** | 奇数行白色 `#FFFFFF`，偶数行极浅色 `rgba(47, 111, 143,0.03)` |
| **外边框** | `border-radius:8px; overflow:hidden; border:1px solid #eef0f2` |
| **行分隔线** | `border-bottom:1px solid #f0f0f0`（最后一行不加） |

### 四、内容原则

- 每格文字尽量简短，目标 ≤ 20 字
- 关键结论用 `color:#2F6F8F; font-weight:bold` 标主题色
- 金额/百分比等数字用 `<span style="color:#2F6F8F; font-weight:bold">` 突出
- 「术语｜整句释义」型 2 列表交给「术语卡」（`--table` 自动转），不必硬压短语；其余长内容仍宜改「要点列表」而非塞表格
- **能力/对比表用星级时，标度取 1-5 星（✘ = 不支持），不要用 1-3 星** -- 3 星太粗，多数格会挤在满级、拉不开主体间差距；1-5 星能把「招牌强项 ★★★★★」和「能用 ★★★」分开，对比才有信息量（3 星版大家都满星、没意义）

---

## 微信兼容表格写法

> 🔴 **2026-09-15 现行方案：section 版 CSS 表，不再输出 `<table>`。** `format_layout.py --table` 自动完成，作者照常写 Markdown 表即可。
>
> **为什么**：微信编辑器保存 / 发布时会把 `<td>` / `<th>` 上的 `width`（inline style 和 `width` 属性一样）整个清掉，再配上它注入的 `table-layout:fixed`，结果永远等宽。证据：2026-09-15 抓四篇已发布文章，线上 `<td>/<th>` 里 **0 个** 还留着 width（本地发布稿有 12 个）；`draft/add → draft/get` 回读时 width 都还在，说明清洗发生在编辑器保存那一步，不在 API。同一批文章里推荐阅读卡的 `<section style="display:table-cell; width:64%">` 原样存活——列宽只有写在 section 上才到得了读者手机。
>
> 历史：2026-04 的 `<colgroup>` 方案会在表头上方渲染出一行空虚线格（空行 bug）；2026-06-26 的「宽度写进首行单元格 + table-layout:fixed」在草稿箱预览正常，但发布后被清洗，一直没人回头核对线上页。

```html
<!-- 每一行是一张 100% 宽的 display:table，各行列宽相同 → 视觉上是一张对齐的表 -->
<section style="border-radius: 10px; overflow: hidden; border: 1px solid #d7e3ea; margin: 0 8px 0.8em; font-size: 12px; line-height: 1.4;">
  <section style="display: table; width: 100%; table-layout: fixed; border-collapse: collapse; box-sizing: border-box;">
    <section style="display: table-cell; vertical-align: middle; box-sizing: border-box; word-wrap: break-word; overflow-wrap: anywhere; width: 38%; padding: 8px 6px; background-color: #2F6F8F; color: #fff; font-size: 13px; text-align: center; font-weight: bold;">列A</section>
    <section style="display: table-cell; vertical-align: middle; box-sizing: border-box; word-wrap: break-word; overflow-wrap: anywhere; width: 62%; padding: 8px 6px; background-color: #2F6F8F; color: #fff; font-size: 13px; text-align: center; font-weight: bold;">列B</section>
  </section>
  <section style="display: table; width: 100%; table-layout: fixed; border-collapse: collapse; box-sizing: border-box;">
    <section style="display: table-cell; vertical-align: top; box-sizing: border-box; word-wrap: break-word; overflow-wrap: anywhere; width: 38%; padding: 8px 6px; border-bottom: 1px solid #eef0f2; color: #333333; font-size: 12px; text-align: left;">内容A</section>
    <section style="display: table-cell; vertical-align: top; box-sizing: border-box; word-wrap: break-word; overflow-wrap: anywhere; width: 62%; padding: 8px 6px; border-bottom: 1px solid #eef0f2; color: #333333; font-size: 12px; text-align: left;">内容B</section>
  </section>
</section>
```

**关键规则**：

- 行用 `display:table`、格用 `display:table-cell`——这两个 display 值在线上有存活证据；`display:table-row` 没有，所以不用行容器，每行各自成表。
- `width` **每一行的每个格子都写**（各行独立成表，只写首行对不齐）；百分比保留一位小数，和为 100。
- 横滑表（≥4 列且放不下）：每行 `width` 为固定 px（列宽夹在 72–150px），外层 `overflow-x:auto`。
- `overflow-wrap: anywhere` 让长 ASCII（命令、URL 片段）在格内折行而不撑宽列；禁止 `word-break: keep-all`（中日韩文字不断行、单元格无限撑宽）。
- 空格子填 `&nbsp;` 占位，否则该格塌陷。
- 格子样式顺序里 `display: table-cell;` 后面不能紧跟 `width:`——`display: table-cell; width: 64%` 是导读栏检测的签名。

### 多列表格列宽分配参考（≥3 列，供 `table_widths` 填值参考；横滑模式会按比例转 px）

| 表格类型 | 列宽分配 | 说明 |
|---------|---------|------|
| 3列（名称+短+长） | 20% / 20% / 60% | 长描述列占大半 |
| 4列（名称+2短+1长描述） | 18% / 15% / 14% / 53% | 最后一列长文字给足空间 |
| 4列（4个均等描述列） | 18% / 18% / 18% / 46% | 最后一列多留余量 |
| 6列均分型 | 18% / 14% / 14% / 16% / 14% / 14% | 第一列名称多留2% |

> ✅ 2026-07-07 起 ≥3 列由 `--table` 自动缩 11px + 放不下横滑，常规文章可正常用多列对比表（不再限「最多 2 列」）；横滑虽比不上纵向铺满，但一屏可读，多维度对比不必再拆表。

---

## 列表 / H4 子级排版

> 由 `format_layout.py` 的 `process_lists()` 在 `--all` 时**自动**把 baoyu 生成的 `<ul class="ul">` / `<ol class="ol">` 重排。核心诉求：**marker 独占左列 + 内容悬挂缩进**（第 2/3 行不顶格、全部对齐在内容列左缘），主次分明；并给有序编号一个介于 H3(时间线) 与正文之间的「H4」级设计格式。

| 列表类型 | marker | 设计 |
|---------|--------|------|
| **无序列表** | 主题色 **箭头 ➤**（U+27A4 黑右箭头 glyph 染主题色；取代默认 `•` 与旧实心 ▸） | `display:table` 两列：marker 列 `width:1.7em` + 内容列悬挂缩进 |
| **有序列表 = H4 子级** | 主题色 **圆形编号徽章**（`20px` / `border-radius:50%`，比 H3 的圆角方块 `24px` 略小） | `display:table` 两列：徽章列 `width:2.2em` + 内容列悬挂缩进 |

- 🔴 **层次系统（方圆对调后）**：H2=PART 大编号块 ｜ **H3=主题色【圆角方块】编号(24px) + 竖线时间线** ｜ **H4=主题色【圆形】编号徽章(20px) + 悬挂缩进列表**（无竖线）｜ 无序点=主题色箭头 ➤。四级视觉拉开、不混。**方=H3(大)、圆=H4(小)**，靠"方/圆 + 大/小"双重信号一眼分级（方=H3 大、圆=H4 小，旧版相反已对调）。
- 🔺 **无序 marker（点 5）**：主题色 **➤**（U+27A4 黑右箭头 glyph，15px 染 `#2F6F8F`）。后背微凹、比旧实心 `▸` 更大更有设计感；dingbat 区字体覆盖好、不依赖 CSS 叠层（曾试 CSS 缺口三角，观感不佳，改用 ➤ glyph）。
- **悬挂缩进**靠 `display:table` / `display:table-cell` 实现（微信稳定支持，比 `text-indent` 负值可靠）；marker 列 `vertical-align:top` 对齐首行。
- **禁止**默认 `<li>• 一句话` 顶格排版（第二行回到最左、主次糊成一团，明确不要）。
- 幂等：转换后不再是 `<ul class="ul">`，重复跑 `--all` 不会二次处理。
- 🔴 **覆盖范围不止正文**：悬挂缩进是**列表通用规则**，不分正文 H3/H4 还是卡片内嵌列表。「划重点」要点卡片（`process_takeaway()` / `key-takeaway.html`）此前用 `margin-right` 兼容写法、无悬挂缩进，第二行顶格露馅（截图实证）；已同步改为同一套 `display:table` 两列约定。未来任何新增卡片组件（要点/案例/框栏等）只要内部出现有序或无序列表，一律套用本节的 marker 独占左列 + 内容悬挂缩进模式，不得各自发明新写法。

### 链接卡 + 文末「深读入口 / 引流框」（固化成独立模块，禁手敲）

**两个模板，配套使用：**

| 用途 | 模板 | 关键点 |
|------|------|--------|
| 正文里**单条**可复制链接（文档 / GitHub / 在线页） | [templates/link-card.html](../templates/link-card.html) | 分类标题 + 「复制到浏览器打开」+ URL 左对齐浅色框 |
| 文末**独立成块**的深读栏 / 附加框栏（1-N 个去向） | [templates/deep-read-section.html](../templates/deep-read-section.html) | DEEP READ 小标 + 大标题 + 引导语 + 多张资源卡（缩略图/图标 + 名 + 可复制 URL） |

**为什么固化（修旧版毛病）：** 旧深读入口是「手动加粗、字号与正文一样、不换行、不成块」，周边框还用浅蓝/浅灰 + 嵌黑块，浅色模式下既刺眼又不像独立模块、配色也不入主题色系。新模板统一解决。

**硬约定：**

- 🔴 **正文里任何一个完整 URL（含 `https://` 全写、或 `域名/路径` 形态如 `example.com/tools/xxx`）一律走模板**：单条 → `link-card.html`，文末 / 多条 → `deep-read-section.html`。**严禁**把完整 URL 裸放在正文段落、划重点要点、表格单元格或任何普通文本块里。
  - **根因（2026-07-11 实测坐实）**：微信对「含一个放不下的长 token（URL）」的行做**两端对齐**，把该行前面的中文字撑成大字间距（截图里「GitHub 打 不 开 就 走」那种分散对齐）；同时被拉散的 URL 读者**长按选不中、没法复制**。只有模板里的 `text-align:left + word-break:break-all` 浅色框能同时压住这两件事。裸贴 = 必然翻车。
  - **网址放不下就让模板换行**，不要硬塞一行、更不要为了塞下去改成两端对齐。
  - 🔴 **文末「地址再放一遍 / 引流」段落 = 必须走 `deep-read-section.html`，禁止手敲成正文段**（这次翻车的就是手敲文末：无绿标题、无浅框、URL 分散对齐）。发布硬门 `verify_no_bare_url` 会拦下漏网的裸 URL（见 scripts/contracts.py）。
- 🔴 **URL 必须左对齐 + `word-break:break-all` + 装进浅色框**（`#eaf1f5` 底 + 圆角）。绝不能裸贴长 URL--微信会两端对齐把它拉成大字间距。
- 🔴 **引流链接直接给出可复制的完整 URL**（`https://...` 全写），不要只写「点左下角阅读原文」（读者找不到、无法复制）。多个去向 = **各列各的独立资源卡**，不要合并成一句。
- 🔴 **「单击即可复制」在微信正文做不到**（正文外链是纯文本、不可点、不能挂 JS——普通订阅号外链能力已被微信回收）。能做到的最佳态 = **URL 保持一整串干净纯文本装进浅框**，读者**长按 → 复制 / 浏览器打开**；框上标一句「复制到浏览器打开 ▾」提示。若要一个**可点击**的主入口，用「阅读原文」（`content_source_url`）承载（见 publish.md），正文纯文本 URL 作长按复制的兜底。
- 🔴 **入口标签作标题类元素**：`GitHub` / `国内直达` / `在线解析` 这类入口名 = 品牌绿加粗小标题（link-card 的 `🔗 分类名` 13px/bold 绿 或 deep-read 的资源名 15px/800），**不能跟正文一样字号、靠手动加粗充数**。
- 🔴 **整模块走主题色系浅底**（深读模块 `#f2f7f9`、链接卡 `#fafcfb`），**不嵌黑块、不出现浅蓝/浅灰杂色**，浅色阅读环境友好。
- **标题主次靠字号/字重拉开**：模块大标题（18px/800）> 资源名（15px/800）> 说明（12px/normal）> URL（13px/600）> 提示与免责（12px 浅灰）。
- 缩略图：有封面用 A 型卡（`<img>` + `data-local-path` 走发布脚本上传）；无封面用 B 型卡（emoji 图标兜底：📄 PDF / 📦 GitHub / 📝 表单 / 🔗 通用）。
- 阅读原文作为**兜底次级**入口保留即可，不作主引导。

---

### 后处理脚本说明

> 实际执行逻辑在 `scripts/format_layout.py` 的 `process_table()` 函数，以下为处理要点：

0. **解析**：`_parse_table_rows` 把 `<thead><th>…</th></thead>`（无 tr）/ `<thead><tr>…` / 无 thead 但首行全 th 三种形态统一拆成表头 + 数据行，格子保留 inner HTML（`<strong>` / `<code>` / `<br>`）。
1. **路由分派**（2026-07-07）：**2 列且 `_is_term_table`**（左短术语/右长释义，无 `table_widths` 覆盖时）走 `_render_term_cards` 出术语卡；**≥3 列** 用 11px / 表头 12px、padding `6px 7px`；**其余 2 列** 用 12px / 表头 13px、padding `8px 6px`。
2. **列宽**（2026-09-15）：`table_widths` 优先；否则 `_column_needs_px` 估每列单行所需像素（汉字=字号、ASCII≈0.6 字号、表头加粗 +5%、含 padding、各留 4px 余量），`_fit_widths_px` 压进 `_TABLE_BODY_PX`=345：放得下按比例铺满；放不下先给保底（自身需求 / 3 汉字宽 / 表头单行宽），余量按超出保底的部分分给长列。**≥4 列且放不下** → 每列夹 [72,150]px、每行固定 px 宽 + 外层 `overflow-x:auto` 横滑。
3. **渲染**：`_render_section_table` 输出 section 版 CSS 表——每行 `display:table; width:100%|Npx; table-layout:fixed`，每格 `display:table-cell` 带 `width`；表头 主题色底 + 白字 + 居中加粗 + `vertical-align:middle`，数据格 只有 `border-bottom` 分隔线 + `vertical-align:top`，偶数行格子追加 `background-color: rgba(47, 111, 143,0.03)`；空格子填 `&nbsp;`。
4. **外层圆角容器**：`<section class="sw-table" style="border-radius: 10px; overflow: hidden|overflow-x: auto; border: 1px solid #d7e3ea; margin: 0 8px 0.8em;">`。
5. **空行修复**：移除 baoyu 生成的多余 wrapper section（其 `line-height: 1.75` + 空白字符会渲染出空行）。输出里不再有 `<table>`，重复跑天然幂等。
6. **术语卡**（2 列术语｜释义）：`_render_term_cards` 出「左竖条 + 加粗术语(15px) + 全宽释义(14px)」，仅用 design-tokens，theme-ready。

### 已知问题备忘

| 问题 | 原因 | 解决 |
|------|------|------|
| 发布后列等宽 | 编辑器清掉 td/th 的 width 再注入 table-layout: fixed | 不输出 `<table>`，列宽写在 `display:table-cell` 的 section 上（2026-09-15） |
| 编辑模式下文字变大 | 微信重置 font-size 为 16px | 每个 td/th 强制 font-size: 13px |
| 编辑模式下推荐阅读变蓝 | `<a>` 标签被微信还原为默认蓝色 | 显式 `color: #333333` |
| 关注卡片变窄 | 编辑器假预览中有额外 padding | 非编辑模式和手机端正常，不影响最终效果 |
| 表格上方多空白行 | baoyu 的 wrapper section 含 line-height:1.75 + 空白字符 | process_table 移除该 wrapper |
| 表格外多一圈边框 | td/th 用 border:1px solid（四边框）叠加成外框 | th 无边框、td 只用 border-bottom |
| word-break: keep-all 撑爆 | 中日韩文字禁止断行导致列无限宽 | 全局清除此属性 |

---

## 导读栏底栏 Logo

底栏（主题色背景 `#2F6F8F`）左侧用白色 Logo：

```html
<section style="width: 110px; height: 30px; overflow: hidden;">
  <img src="素材/logo-white.png" data-local-path="{{ARTICLE_DIR}}/素材/logo-white.png" style="width: 110px; display: block;">
</section>
```

使用前须将 logo 复制到文章素材目录（跨平台正斜杠；Windows `copy`/Unix `cp` 均可）：
```
cp brand/logo-white.png <数据目录>/{N}-{选题名}/素材/logo-white.png
```

---

## 分隔线样式参考

```html
<!-- 品牌色短线（模块间） -->
<section style="text-align:center; margin:30px 0;">
  <section style="display:inline-block; width:40px; height:3px; background:#2F6F8F; border-radius:2px;"></section>
</section>

<!-- 三点式（段落组之间） -->
<section style="text-align:center; color:#ccc; letter-spacing:12px; margin:25px 0; font-size:14px;">···</section>

<!-- 细灰线（脚注前） -->
<section style="border-top:1px solid #eee; margin:30px auto; width:60%;"></section>
```

---

*提取自 layout.md 参考资料部分 · 2026-04-11*
