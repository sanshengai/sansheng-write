# 微信公众号排版兼容性规则

> **定位**：排版阶段专用参考。当文章涉及 HTML/CSS 调整、表格重构、卡片插入、图表排版时，**必须加载此文件**检查兼容性。
>
> **维护**：遇到新的被过滤/清洗案例，在对应章节末尾追加实测记录（含日期）。

---

## 1. 核心原则

微信公众号编辑器对 HTML 执行**白名单过滤**：不在白名单内的标签和属性会被**静默删除**，不报错、不提示。

| 原则 | 说明 |
|------|------|
| **纯内联样式** | 所有 CSS 必须写在 `style=""` 属性里；`<style>` 标签块会被整段删除 |
| **无 JS** | `<script>`、`onclick` 等事件属性一律被剥除 |
| **无外部资源** | 不支持外链 CSS/JS/字体文件；图片必须走微信素材库 CDN |
| **静态文档流** | 不支持定位布局，所有元素按文档流排列 |

---

## 1.5 🔴 2026-07-07 API 路径实测校正（覆盖下方部分历史结论）

> **背景**：本文档不少旧结论是 2026-04-09 经验值，来源含"编辑器粘贴"场景，从未在我方**实际投递路径**复验。我方投递 = `baoyu-post-to-wechat` 走 **draft/add API 把 HTML 直灌草稿箱**（非手动粘贴编辑器）。2026-07-07 用测试草稿在**真机逐项实测**，结论如下：

| CSS 能力 | 旧结论 | **API 路径实测（2026-07-07）** | 现行用法 |
|---|---|---|---|
| `display:flex` | ❌ 不支持，用 float/table 模拟 | ✅ **可用**（两栏 / 垂直居中 / 等分多列 / gap / 嵌套均正常渲染） | API 路径放心用；旧 float+table-cell 深嵌套模拟可逐步简化 |
| `box-shadow` | ⚠️ 可能被过滤 | ✅ **可用**（卡片投影正常） | 可用 |
| `linear-gradient`（背景 / 细线） | ⚠️ 不稳定 /"分隔线渐变不显示" | ✅ **可用**（渐变背景块 + 渐变细线分隔均显示） | 可用 |
| `border-collapse:collapse` | ❌ 禁用，改 `border-spacing:0` | ✅ **可用**（无错位、无空行） | 两者皆可；表格现行方案仍见 §4 |
| `overflow-x:auto/scroll` 横滑 | 未评估 | ✅ **可用**（横向滚动容器可滑） | 宽表格 / 多列矩阵用它（见 §4） |
| `#ffffff` 纯白背景 | ⚠️ 可能被过滤为透明 | ✅ **正常**（不被过滤） | `#fefefe` 不再必需，沿用亦无害 |
| `margin` | ⚠️ 慎用，优先 padding | ✅ **可靠**（间距正常） | 可正常用 margin |

> **🔑 路径限定（务必理解，别再把旧教条当公理）**：以上是**「API content 直灌草稿箱」路径**的结论。**「手动复制粘贴进公众号编辑器」是另一套净化器**（会剥掉无 `<span leaf>` 的文字样式、对 flex 行为也不同）--我方**不走**该路径，故不受其约束。根因：`span leaf` 是编辑器粘贴净化器的产物、`flex` 早年禁令源于服务端白名单经验值，两者根因不同轴，必须实测而非假设。若未来出现"发布后在后台手动粘贴微调"场景，需对该路径另行验证。
>
> **仍然禁用（未变）**：`<style>` / `<script>` / `<div>`、`class` / `id`、`position:fixed/absolute/sticky`、`display:grid`（未测，暂沿用禁用）、CSS 变量 `var(--x)`、`@media` / `@keyframes`、外部字体 / CSS。

---

## 2. HTML 标签白名单

### 2a. 安全标签（推荐使用）

| 类别 | 标签 |
|------|------|
| 容器 | `<section>`（首选）、`<div>`、`<p>` |
| 标题 | `<h1>` ~ `<h6>` |
| 文本 | `<span>`、`<strong>`/`<b>`、`<em>`/`<i>`、`<u>`、`<br>` |
| 列表 | `<ul>`、`<ol>`、`<li>` |
| 表格 | `<table>`、`<thead>`、`<tbody>`、`<tr>`、`<td>`、`<th>`、`<colgroup>`、`<col>` |
| 链接 | `<a>`（外链会触发安全提示弹窗） |
| 图片 | `<img>` |
| 引用 | `<blockquote>` |
| 分隔 | `<hr>` |
| SVG | `<svg>` 及子元素（有额外限制，见第6节） |
| 微信专属 | `<mpvoice>`、`<mpvideo>`、`<mp-common-profile>` |

> **⚠️ `<section>` 优先于 `<div>`**：实测 `<div>` 偶尔出现样式丢失，`<section>` 稳定性更高。

### 2b. 禁用标签（会被删除或导致错误）

`<script>`、`<iframe>`、`<object>`、`<embed>`、`<form>`、`<input>`、`<textarea>`、`<select>`、`<button>`、`<link>`、`<meta>`、`<video>`（用 `<mpvideo>` 替代）、`<audio>`（用 `<mpvoice>` 替代）

### 2c. 属性过滤

| 属性 | 状态 |
|------|------|
| `style` | ✅ 保留（核心样式通道） |
| `class` | ⚠️ 保留但无作用（无 `<style>` 块定义规则） |
| `id` | ❌ 被删除（页内锚点不可用） |
| `data-*` | ⚠️ 部分保留（微信组件专属 `data-*` 有效，自定义的可能被清理） |
| `onclick` 等事件 | ❌ 全部被剥除 |

---

## 3. CSS 属性支持矩阵

### 3a. 支持的属性

| 类别 | 属性 | 备注 |
|------|------|------|
| 字体 | `font-size`、`font-weight`、`font-style`、`font-family` | 自定义字体无效，始终回退系统字体（苹方/黑体/Arial） |
| 颜色 | `color`、`background-color` | `#ffffff` API 路径实测正常（见 §1.5）；`#fefefe` 沿用无害 |
| 行距 | `line-height`、`letter-spacing`、`word-spacing` | |
| 对齐 | `text-align`（但表格内需用 HTML `align` 属性） | |
| 内边距 | `padding` | **优先用 padding 控制间距**，比 margin 更稳定 |
| 外边距 | `margin` | 部分版本下被过滤或处理不当，慎用 |
| 边框 | `border`、`border-radius`、`border-bottom` 等 | 推荐 `solid` 实线，虚线/双线可能异常 |
| 阴影 | `box-shadow` | ✅ API 路径实测可用（2026-07-07，见 §1.5）；卡片投影正常 |
| 显示 | `display: block`、`inline-block`、`table`、`table-cell` | |
| 浮动 | `float: left/right` | 可用，但在隐藏/展开布局中容易脱离容器 |
| 透明 | `opacity` | |
| 文字装饰 | `text-decoration` | |
| 溢出 | `overflow: hidden` | 用于图片尺寸约束的关键属性 |
| 垂直对齐 | `vertical-align` | |
| 宽度 | `width`（px 或 %） | 表格列宽用 `<col style="width:X%">` 最稳 |
| 背景渐变 | `background: linear-gradient(...)` | ✅ API 路径实测可用（含渐变细线，2026-07-07，见 §1.5） |

### 3b. 被过滤/不支持的属性

| 属性 | 状态 | 替代方案 |
|------|------|---------|
| `position` (absolute/relative/fixed) | ❌ 被删除 | 用文档流或 `float` + `display:table` 布局 |
| `z-index` | ❌ 无定位则无意义 | -- |
| `display: flex` | ✅ **API 路径实测可用**（2026-07-07 校正，见 §1.5） | 旧 `float`/`table-cell` 深嵌套模拟可逐步简化；「粘贴」路径未验 |
| `display: grid` | ❌（未测，暂沿用禁用） | 用 `flex` 替代 |
| `transform` | ⚠️ 部分失效，iOS 上 `transform-origin` 无效 | 避免使用 |
| `@keyframes` / `animation` | ❌ | 用 GIF 或静态图替代 |
| `@media` | ❌ 无 `<style>` 块可写 | 用 `vw`/`vh` 做弹性适配 |
| `::before` / `::after` | ❌ 伪元素不支持 | 用真实 `<span>` 元素模拟 |
| `:hover` / `:focus` 等伪类 | ❌ | -- |
| CSS 变量 `var(--xxx)` | ❌ | 硬编码具体值 |
| `height`（img） | ⚠️ 微信不可靠 | 用容器 `width` + `overflow:hidden` 约束 |
| `max-width`（img） | ⚠️ 微信自动设 `max-width:100%`，自定义值可能冲突 | -- |
| 百分比高度/位移 | ⚠️ 如 `margin-top:-100%` 无效 | 用 `px` 或 `vw`/`vh` |

---

## 4. 表格规则（手机端关键）

> 手机端微信图文区域宽约 **360px**，表格是最常被清洗的元素。

### 4a. 列数限制

- **最多 2 列**：3 列及以上在手机端严重挤压变形
- **超过 2 列** → 必须改写为列表、分段卡片或纵向排列

### 4b. 列宽控制（🔴 2026-06-26 现行方案：写进首行单元格，非 colgroup）

微信编辑器进入编辑模式时会自动注入 `table-layout: fixed`，导致所有列被强制等宽。

**现行根治方案**：把列宽 `width` **直接写进首行单元格** + table 设 `table-layout:fixed`--fixed 布局本就按首行单元格宽度定列，微信注入的 fixed 反成助力，**列宽稳定生效且不被格式清算**。`format_layout.py --table` 自动完成，无需手写。

> ⚠️ 旧 `<colgroup>` 方案已弃用：实跑发现微信会把 `<colgroup>` 渲染成**表头上方一行空虚线格子**（空行 bug）。下面代码块仅留作历史参考。

```html
<!-- 现行：宽度写进首行 th（脚本自动） -->
<table style="width:100%; table-layout:fixed;">
  <thead><tr>
    <th style="width:38%; ...">列A</th>
    <th style="width:62%; ...">列B</th>
  </tr></thead>
  <!-- ... -->
</table>
```

列宽**值的来源**：优先用大模型按内容测算、填进 `article-meta.yaml` 的 `table_widths`（更协调）；无则脚本 sqrt 启发式兜底。详见 [layout-reference.md §一、列数与宽度](layout-reference.md)。

### 4c. 表格样式规范

| 要素 | 规则 |
|------|------|
| 表头 | 主题色 `#2F6F8F` 背景 + 白色文字 + **13px 加粗**（比内容大一号） |
| 表格内容 | **12px**（比表头小一号），每格 ≤20-22 字，须大模型精炼 |
| 交替行色 | 奇数行白色，偶数行 `rgba(47, 111, 143,0.03)` |
| 外边框 | `border-radius:8px; overflow:hidden; border:1px solid #eef0f2` |
| 行分隔线 | `border-bottom:1px solid #f0f0f0`（末行不加） |
| 边框合并 | 现行默认 `border-spacing:0`；`border-collapse:collapse` 亦实测可用（§1.5），二选一 |
| 对齐 | `align`/`valign` 用原生 HTML 属性，CSS `text-align` 在 `<td>` 中可能被过滤 |

---

## 5. 图片规则

| 规则 | 说明 |
|------|------|
| **必须用微信素材库** | 本地路径和外链均无法显示；发布时由脚本上传获取 CDN URL |
| **微信自动加 `max-width:100%`** | 不要依赖自定义 `max-width` |
| **固定尺寸用容器约束** | `<section style="width:Npx; overflow:hidden;"><img style="width:Npx; display:block;">` |
| **禁止用 `height` 控制** | 微信对 `height` 属性支持不可靠 |
| **加 `display:block`** | 消除图片间白缝（inline 默认有基线间隙） |
| **Base64 不支持** | SVG 中的 `<image>` 也必须用素材库 URL |
| **推荐阅读封面** | 定死 `width:140px; height:79px; object-fit:cover;` |

---

## 6. SVG 规则

微信支持内联 SVG 用于点击交互效果，但有严格限制：

| 规则 | 说明 |
|------|------|
| 必须内联 | 不支持外部 `.svg` 文件引用 |
| `<image>` 标签 | 必须写 `width` 和 `height` 属性（iOS 必需） |
| 图片源 | 只能用微信素材库 CDN URL，不支持外链或 Base64 |
| CSS 限制 | SVG 内部同样不支持 `position`、`@keyframes` |
| `<style>` | SVG 内部的 `<style>` 在部分客户端可能被保留，但**不可靠**，建议内联 |

---

## 7. 颜色与深色模式

| 规则 | 说明 |
|------|------|
| 纯白背景 | ✅ `#ffffff` API 路径实测正常（2026-07-07，见 §1.5）；`#fefefe` 不再必需、沿用无害 |
| 深色模式 | 微信会自动反转颜色，硬编码的白色背景在深色模式下变黑 |
| 渐变 | ✅ `linear-gradient` API 路径实测可用（含渐变细线分隔，2026-07-07，见 §1.5） |
| 品牌色 | 必须硬编码 `#2F6F8F`，不能用 CSS 变量 |

---

## 8. 链接规则

| 规则 | 说明 |
|------|------|
| 外链 | 触发"即将离开微信"安全提示；仅白名单域名可免提示 |
| `<a>` 包裹块级 | 支持但不稳定，偶发编辑器"系统错误" → 推荐 `<a>` 只包裹行内文本 |
| 未群发图文链接 | 不可插入，会报"请勿插入未群发的图文消息链接" |

---

## 9. 字符与内容限制

| 限制 | 值 |
|------|-----|
| `content` 字段上限 | **20,000 字符**（超出返回 47001 错误） |
| 公众号名 | 4-30 字符（1 汉字 = 2 字符），不支持特殊符号和空格 |
| 系统字体 | 苹方（iOS）、黑体/思源黑体（Android）、Arial/Segoe UI（Web） |

---

## 10. 常见被清洗场景 & 解决方案速查

| # | 场景 | 被清洗原因 | 解决方案 |
|---|------|-----------|---------|
| 1 | 颜色变蓝/丢失 | 用了 `var(--xxx)` | 硬编码颜色值 |
| 2 | 圆点/序号消失 | 用了 `::before` 伪元素 | 真实 `<span>` 模拟 |
| 3 | 布局错乱 | `display:grid`（flex 已实测可用，见 §1.5） | grid 改 `display:table`；flex 可直接用 |
| 4 | 元素飘到错误位置 | 用了 `position:absolute` | 去掉定位，用文档流 |
| 5 | ~~白色背景消失~~ | `#ffffff` 已实测正常（见 §1.5，本条作废） | 无需改 `#fefefe` |
| 6 | 表格列等宽 | 编辑器注入 `table-layout:fixed` | 列宽**写进首行单元格** + `table-layout:fixed`（脚本自动；旧 colgroup 会出空行 bug） |
| 7 | 多列表格挤成一团 | 手机宽仅 360px | 改写为 ≤2 列或纵向列表 |
| 8 | 图片间有白缝 | `<img>` 默认 inline | 加 `display:block` |
| 9 | Logo/图标过大 | 用了 `height`/`max-width` | 容器 `width` + `overflow:hidden` 约束 |
| 10 | ~~分隔线渐变不显示~~ | 已实测可用（见 §1.5，本条作废） | 渐变细线 API 路径正常显示 |
| 11 | 动画不动 | `@keyframes` 被删除 | 改用 GIF |
| 12 | `<div>` 样式丢失 | `<div>` 偶尔不稳 | 改用 `<section>` |
| 13 | 推荐卡片在编辑器变形 | `<a>` 包裹块级后二次编辑 | 用分散式 `<a>` 方案 |
| 14 | 关注卡片报"信息错误" | `data-id` padding 不完整 / 缺 class | 三要素缺一不可（见 layout.md 详细说明） |
| 15 | 47001 超限 | `content` > 20,000 字符 | 压缩冗余 HTML，或拆分上下篇 |

---

## 11. 排版前检查清单

排版 HTML 调整前，逐项检查：

- [ ] 无 `<style>` 标签块，所有样式已内联
- [ ] 无 `position`、`display:grid`、CSS 变量（flex 已实测可用，见 §1.5，不再禁）
- [ ] 无 `::before`/`::after` 伪元素
- [ ] 表格 ≤ 2 列，列宽写进首行单元格 + `table-layout:fixed`（脚本自动；优先 `table_widths`）
- [ ] 白色背景 `#ffffff` / `#fefefe` 皆可（§1.5 实测 `#ffffff` 正常）
- [ ] 图片有 `display:block`，无 `height` 属性控制
- [ ] 固定尺寸图片用容器 `width` + `overflow:hidden`
- [ ] `<section>` 优先于 `<div>`
- [ ] `content` 字符数 < 19,000（留余量）
  > 仅极长文 >5 万字纯文本时启用；日常公众号文章跳过此检查。

---

*最后更新：2026-04-09 · 数据来源：实战踩坑记录 + axtonliu.ai HTML/CSS 支持解析 + 微信开放社区 + 多源交叉验证*
