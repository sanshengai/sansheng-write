# 发布与沉淀

定稿后的可执行单一真源是 [release-runtime.md](release-runtime.md)。本文件只解释发布边界和状态。

## 两阶段发布

### 阶段一：自动到微信草稿箱

唯一入口：

```bash
python "$SKILL/scripts/pipeline.py" release-to-draft
```

该命令内联完成 release job 校验、发布预检、草稿创建、官方 `draft/get` 读回和状态落盘。任何一步失败都非零退出。

读回必须一致：

- title / digest / author
- `content_source_url`
- `need_open_comment` / `only_fans_can_comment`
- 规范化正文摘要与图片数量
- `thumb_media_id`

只拿到 `media_id` 不算成功；不得手工登记，不得拆开调用低层接口。

### 阶段二：作者人工正式发布

作者在微信后台处理预览、原创声明、赞赏设置和正式发布。公开 Skill 不尝试替作者完成这些高风险动作。

拿到永久链接后：

```bash
python "$SKILL/scripts/pipeline.py" finalize \
  "https://mp.weixin.qq.com/s/..."
```

固定顺序：

1. 永久链接写入 publish state。
2. 作品库归档及派生视图刷新。
3. archive 验证。
4. 执行 profile 中已配置的官网同步命令。
5. 生成 `_moments-copy.md`；实际朋友圈发布仍由作者完成。

`_moments-copy.md` 是可整段直接粘贴的纯文本，必须满足以下协议：

- 第一个字符就是首句 emoji；不得有标题、导语、引用符号、代码围栏或任何前导字符。
- 每个逻辑句是一段；段落之间恰好一个空行（两个 `\n`），句子内部不得插入换行。
- 每段首尾无普通空白、不可见零宽字符或 BOM；网址必须与所属句保持同一段。
- 文件末尾只保留一个换行。聊天交付必须从首句 emoji 开始，不添加 Markdown 包装。
- 🔴 **不放公众号文章链接行**（2026-07-30 sandy 拍板）：朋友圈从公众号文章点「分享」时，微信自动带文章卡片与链接，📖 文章 URL 行是冗余，不写。
- 🔴 **网站只出现一次**：引流尾巴一行同时承载品牌名与域名（`writing.moments_cta`，本身已含域名），不得再单独追加一行 🔗 裸网址。行结构 = 钩子 → 价值 → 引流尾巴（含域名），三行。
- 🔴 **聊天交付必须独占最终消息**：状态、解释和其他路径都在 commentary 里先说完；
  final 只逐字输出 `_moments-copy.md`，不得在它前后追加分隔线、播客状态或任何说明。
  禁止手敲复写，必须读取文件原文后原样发送。

## 之后：一稿多投

`finalize` 拿到永久链接后，同一篇可以派生到小红书 / 微博 / 播客——见 [distribute.md](distribute.md)。
分发是**独立的第二段链路**，不阻塞 finalize：生图、NotebookLM 与浏览器自动化都可能跑很久，
不该拖住归档与官网同步。

若 profile 已为播客显式配置 `auto_after_finalize: true`，`finalize` 完成核心收尾后会继续
生成音频并推送 RSS；失败会以非零退出明确暴露，但不会回滚已经完成的归档和官网同步。

## 凭证

- `_publish-ready.json`：调用微信前的本地包摘要。
- `_release-attempt.json`：草稿创建后的断点记录，防重试重复建稿。
- `_publish-receipt.json`：官方读回通过后的 v2 凭证。
- `_website-sync-receipt.json`：官网同步完成、失败或未配置记录。

本地 HTML、Hero、视觉凭证发生变化后，旧发布凭证失效，必须重跑 `release-to-draft`。

## 配置

- 微信密钥只从环境变量或 baoyu 标准 `.env` 位置读取，不写入文章目录或公开仓。
- `article-meta.yaml.source_url` 可填完整 URL、`default` 或 `treasure`。
- 默认阅读原文地址来自 profile 的 `publish.source_url_default`。
- 官网同步来自 profile 的 `publish.website_command`；相对路径命令应同时配置 `publish.website_cwd` 或 `SANSHENG_WRITE_WEBSITE_CWD`。
- 朋友圈尾巴来自 `writing.moments_cta` 和 `identity.site`。

缺微信凭证、远端读回失败或官网命令失败都应明确阻断；不存在“先发布、以后再补证据”的降级路径。
