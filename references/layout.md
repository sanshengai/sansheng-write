# 排版流程

排版只负责把已确认的 Markdown 和已生成素材装配成微信兼容 HTML。视觉业务规则见 `image-routing.md`，草稿发布见 `release-runtime.md`。

## 输入

- `定稿.md`
- `article-meta.yaml`
- `素材/cover.png`
- `素材/hero.png`
- 至少 4 张 `素材/infographic-*.png`
- BGM MP3 与定稿中的 AUDIO-CARD

缺任一发布硬门产物就停，不用占位符先过排版。

## 1. Markdown 装配

固定顺序：

1. H1 标题。
2. `hero.png`。
3. 导读栏。
4. AUDIO-CARD。
5. 正文与信息图。
6. 推荐阅读。
7. 关注卡片。

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
- `footer-recommended.html`

颜色、圆角、账号身份只从 profile 读取。禁止在文章里另存一套主题色。

### 选择原则

- 教程：步骤、注意事项、结果卡。
- 方法论清单：编号模块、对比块、关键结论。
- 深度文：导读、时间线、案例、金句。
- 单个外部链接：link card。
- 多个来源或延伸阅读：deep-read section。

金句卡不加装饰性引号；出处行使用发丝线和弱化右对齐。

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
- Hero、AUDIO-CARD、推荐与关注组件位置正确。
- 所有正文图已上传前可解析，且最终视觉凭证有效。

## 常见故障

- H2 数量不一致：修 `article-meta.yaml.part_subtitles` 或正文标题，不手改 HTML 结构。
- 微信样式丢失：使用模板支持的行内样式，避免依赖外部 CSS/JS。
- 图片不显示：核对相对路径、文件扩展名及正文引用。
- QA 失效：图片后处理或 prompt 发生变化，重新 `visual-qa`、`seal visual`。
- 发布预检失败：按错误逐项修复，不调用低层发布命令。
