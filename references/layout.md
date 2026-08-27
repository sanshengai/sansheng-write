# 排版流程

排版只负责把已确认的 Markdown 和已生成素材装配成微信兼容 HTML。视觉业务规则见 `image-routing.md`，草稿发布见 `release-runtime.md`。

## 输入

- `定稿.md`
- `article-meta.yaml`
- `素材/cover.png`
- `素材/hero.png`
- 至少 4 张 `素材/infographic-*.png`
- BGM MP3 与定稿中的 AUDIO-CARD
- 显式启用 `podcast.wechat_embed` 时：`dist/podcast/audio.mp3` 与 PODCAST-CARD

缺任一发布硬门产物就停，不用占位符先过排版。

## 1. Markdown 装配

固定顺序：

1. H1 标题。
2. `hero.png`。
3. 导读栏。
4. AUDIO-CARD「🎵 阅读配乐｜本文主题曲」。
5. PODCAST-CARD「🎧 音频版本｜本期播客」（显式启用时）。
6. 正文与信息图。
7. `DEEP READ / 继续往下读`：`endmatter.deep_read: true` 时必有，优先放 1 篇
   与本文直接相关的已发内容，再放 profile 的自有站点。
8. `SOURCES / 信息来源`：正文使用了外部案例、数据、视频或报告时必有。
9. 推荐阅读。
10. 关注卡片。

信息图按 `visual-plan.json` 的 opening/middle/closing 位置嵌入。素材存在但正文未引用会被发布预检拦截。

H2/H3 只保留纯标题；PART、时间线序号和样式由脚本生成。破折号使用 `--`。

## 2. Markdown → HTML

使用已安装的微信兼容 Markdown 转换器生成 HTML。随后运行：

```bash
python "$SKILL/scripts/format_layout.py" 定稿.html --all --check
```

`--all` 执行确定性清洗、组件注入和完整性检查；`--check` 单独使用不是完整发布凭证。

## 3. 组件

组件模板都在 `templates/`：

- `lead-section.html`
- `h2-header.html`
- `case-timeline.html`
- `key-takeaway.html`
- `quote-card.html`
- `link-card.html`
- `deep-read-section.html`
- `sources-section.html`
- `footer-recommended.html`

颜色、圆角、账号身份只从 profile 读取。禁止在文章里另存一套主题色。

### 选择原则

- 教程：步骤、注意事项、结果卡。
- 方法论清单：编号模块、对比块、关键结论。
- 深度文：导读、时间线、案例、金句。
- 单个外部链接：link card。
- 延伸阅读 / 自有阵地：deep-read section。
- 外部案例、报告、视频与数据出处：sources section。

金句卡不加装饰性引号；出处行使用发丝线和弱化右对齐。

### 文末双模块合同

- `DEEP READ` 与 `SOURCES` 是两件事，禁止合并：前者负责“读者接下来去哪”，后者负责
  “正文依据从哪来”。
- 两者都使用容器模块语言：主题浅底 + 主题边框 + 绿色小标 + 浅色 URL 内嵌框；
  颜色和圆角一律走 design tokens。
- 固定顺序：正文 → DEEP READ → SOURCES → 推荐阅读 → 关注卡片。
- 写入时必须保留模板标记 `SANSHENG-DEEP-READ` / `SANSHENG-SOURCES`。机器门据此
  判断是否真的用了标准组件，不能用一个普通 H2 或几行裸 URL 冒充。
- DEEP READ 最多放 1 篇强相关旧文 + 1 个自有阵地；找不到强相关旧文时只放自有阵地，
  不为了凑数塞弱相关内容。
- SOURCES 只列正文实际使用过的来源，按“来源主体 / 标题或用途 / URL”三层填写。

## 4. 图片后处理

```bash
node "$SKILL/scripts/add_logo.js" "素材/*.png"
python "$SKILL/scripts/compress_images.py" 素材
```

- Logo 与压缩必须在视觉 QA 前完成。
- 作者供图、二维码和脚本白名单资源不加 AI 图水印。
- 处理后不得继续修改图片；若修改，重新运行 QA 与 seal。

## 5. 发布前检查

```bash
python "$SKILL/scripts/pipeline.py" visual-qa
python "$SKILL/scripts/pipeline.py" seal visual
python "$SKILL/scripts/pipeline.py" release-to-draft
```

核心检查：

- 标题、导读、摘要一致。
- H2/H3 与 `article-meta.yaml` 数量一致。
- 无裸露不可点击 URL、无脚本/样式注入、无未替换占位符。
- Hero、双音频卡、文末双模块、推荐与关注组件位置正确；音频卡固定为主题曲 → 播客，均在导读后、正文前，同宽上下排列。
- 所有正文图已上传前可解析，且最终视觉凭证有效。

## 常见故障

- H2 数量不一致：修 `article-meta.yaml.part_subtitles` 或正文标题，不手改 HTML 结构。
  `信息来源` 不再写成 Markdown H2/H3，而是直接使用 `sources-section.html`，因此不计入
  `part_subtitles`。禁止 `[标题](链接)`；URL 放在模板的浅色可复制框里。
- 末节出现 800 字以上的纯文字连排：排版会提示字墙。找 2--4 个天然推进点拆 `###`
  H3，不要靠加空行硬断 —— H3 会自动转成时间线格式，本身就是视觉换气。
- 微信样式丢失：使用模板支持的行内样式，避免依赖外部 CSS/JS。
- 图片不显示：核对相对路径、文件扩展名及正文引用。
- QA 失效：图片后处理或 prompt 发生变化，重新 `visual-qa`、`seal visual`。
- 发布预检失败：按错误逐项修复，不调用低层发布命令。
