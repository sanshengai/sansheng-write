# 社媒预填交接验收

本合同覆盖脚本、手工与 CUA，防止执行通道切换时把产物缩水。微博图文与 X Articles 的原有制作规则仍分别在 distribute.md、x-article.md。

## 执行顺序

1. 从用户本次请求列出渠道与产物：微博默认独立方图＋文案；X 默认完整 Articles＋封面＋原位正文图＋推荐说明。未明确改成纯文字时，不自行降级。
2. 批量制作前先检查指定浏览器的登录与编辑器可用性，缺登录尽早告知，继续独立的本地工作；本地素材校验通过后再预填。本地计划数与浏览器实际上传数分别记录。
3. 对真实 UI 回读文字、图片数量、顺序/位置、封面、预览、说明框和发送按钮。没观察到记 false/null，不推断成功；上传中、工具中断均属未完成。
4. 按下列合同写观察回执并运行：

```bash
python3 scripts/social_handoff.py <文章目录> --only weibo,x
```

只请求一个渠道就只列一个。exit 2 表示不可交接为「准备完成」。用户明确另要纯文字时沿该任务单独记录，不伪造本合同通过。

## 观察回执

位置：`过程记录/_social-browser-handoff.json`。根字段 `observed_at`（ISO/UTC）、`method`（实际观察工具）、`channels`。每个渠道有：

- `product`：微博 `image_text`，X `article`；`url` 为当前预填页，X 必须 `/compose/articles/edit/<数字>`（可带 `/focus`）。
- `assets`：实际使用文件的 `{path: 相对文章目录路径, sha256: 内容哈希, role: copy/image/cover/body_image/caption}` 列表，至少含文案、图片；X 含适配稿、封面、正文图和 caption.txt。文件变化后必须重新回读。
- `text_readback_verified`、`media_order_verified`、`send_button_enabled`、`send_clicked`：前三项只有实际核对后可 true，最后必须 false。
- 微博：`images_expected`、`images_uploaded`（实际值，4–9 张，且与计划相等）。
- X：`cover_verified`、`body_images_expected`、`body_images_uploaded`、`body_structure_verified`、`placeholders_remaining`、`preview_verified`、`caption_prefilled`、`caption_readback_verified`。正文图片数量来自本篇块计划，不把封面算入正文。说明必须在长文发布确认弹层预填，普通短帖编辑框不算。

可附 `observations` 保存 AX 摘要、实际图片 URL、预览位置等观察证据。不记录账号密码或会话凭证。检查器验证字段完整性与本地哈希，不能独立证明 Agent 所填观察真实；禁止用计划数填实际数、没核对就填 true。

## 拒绝与恢复

本次事故反例：微博 `images_uploaded=0`，X `url=https://x.com/compose/post`，即使文字正确、按钮可用，也必须拒绝交接。

缺图补图；缺短说明先补说明；浏览器不可操作时保存候选、记录剩余项，不写 ready。作者手动发出后，凭真实 URL 另登记已发布；「预填就绪」不自动升级为已发布。
