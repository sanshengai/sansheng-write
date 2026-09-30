# 发布运行时附录

`release-runtime.md` 保持短小；这里放收尾阶段的完整细则，规则内容与原文一致。

## 人工发布后的自动收尾

作者再人工处理预览、原创、赞赏和正式发布。拿到永久链接后运行：

```bash
python "$SKILL/scripts/pipeline.py" finalize \
  "https://mp.weixin.qq.com/s/..."
```

固定顺序：前置检查（含双音频正式文章补验）→ 登记永久链接 → 归档作品库 → 验证归档 → **生成 `_moments-copy.md`** → 已获长期授权的自动播客 → 执行已配置官网同步。官网命令未配置时记录 skipped。🔴 **朋友圈文案自 2026-09-23 起在 `release-to-draft` 成功时就已交付**（见 §5），这里通常只是保留终稿；草稿阶段漏交付时才在此补。它排在归档验证之后、播客与官网之前：它只需要标题、摘要和永久链接，不依赖播客音频与官网；压在链尾会让作者等一个 10-30 分钟的音频才拿到文案，而首发那几小时最需要它。**播客或官网失败不得阻断、也不得回滚它。** 内容要求见 publish.md「朋友圈内容协议」。

`finalize` 在任何写盘前还会再次读回远端证据源：正常路径读草稿，恢复路径读绑定永久链接的正式文章；本地音频、远端播放器身份、正文或交接哈希任一变化，旧凭证立即失效。公众号、官网与 RSS 复用同一个 `dist/podcast/audio.mp3`，禁止各自重生成一份。新生成音频另有 `dist/podcast/audio.manifest.json` 绑定语义输入、生成参数、字节哈希、编码与时长；存量无 manifest 的音频继续兼容，但下次重生成会自动升级。

- 播客配置 `auto_after_finalize: true` 时必须继续 `generate → publish --confirm` 到 receipt；同源 receipt 幂等跳过。**NotebookLM 登录失效时 `podcast_episode.py` 会自动拉起 `nlm login` 弹浏览器授权（2026-07-30 起），探测恢复后继续原流程**；只有自动登录失败才提示人工 `nlm login`（无人值守环境用 `SANSHENG_NLM_NO_AUTOLOGIN=1` 关回纯提示）。不得误说成“音频只能手动生成”。
- 小红书与微博不随 `finalize` 自动规划。用户明确点名某篇要「转小红书 / 发微博」后，才运行 `distribute.py plan --only ...`，分别制作 3:4 与 1:1 专属图片并预填发布页。所有会继续写文章目录的任务结束后，再按 `physical-archive.md` 做永久文件交付；它不属于 `finalize`、作品库 `archive` 或人工上传 handoff。
- **播客音频同时上官网「听全文」（2026-07-30 拍板规则）**：`finalize` 必须先执行自动播客的 `generate → publish --confirm`，确认 `dist/podcast/audio.mp3` 与 RSS receipt 都存在之后，才能同步官网；不得先部署一个只有主题曲的版本。把该音频随文章目录一起 commit，官网构建时 `prepare-songs.py` 自动复制为 `public/song-assets/{code}/podcast.mp3`，文章页主题曲卡下出现「🎧 听全文 · 播客版」播放器（全站单例播放器，天然互斥暂停），文章列表标题旁出现「🎧 有音频」标记。部署走 `publish-to-website.sh {code}`（`-ArticleCodesCsv` 放行 song-assets）。设计口径：主题曲=配乐读、播客=代替读，两卡并存不做选择 UI；列表只放标记不放播放按钮。
- 朋友圈状态先放 commentary；final 只逐字输出 `_moments-copy.md`，首字符为 emoji，前后不得混入解释。


## 素材计划与当前交付状态（2026-09-30）

`adopt-final` 后先检查自动生成的 `_asset-plan.json` 和 `_delivery-snapshot.json`，把正文来源模式、主封面、Hero、主题曲生成单/音频/封面、播客音频/封面以及视频逐项定下来。新闻正文不用额外生图，不意味着取消主封面或音频封面；已明确的作者选择直接录入计划。接管默认只生成待核对的角色计划，不伪造验收或来源。

当前快照记录本篇正文引用文件、SHA、位置、实际音乐 manifest、播客文件与网站视频清单；`present_unverified` 只代表文件存在。来源和适用渠道等编辑信息写入计划，关键发布判断继续读取原有权威 manifest/回执。主题曲生成单仍在配图前交作者，同步作曲。

接管、`handoff-assets` 和 `finalize` 收尾刷新 `交付状态.md`，统一给真实可点击 Markdown 文件链接；路径有空格用 `<绝对路径>`。回复还须包含已有的草稿/正式链接和剩余人工操作。不要用旧手写“候选/未发布”清单报告当前完成状态。

Writer 负责精确本篇媒体交接，Website 负责受管上传、R2/Cloudflare CDN、正式站发布和状态查询。profile `publish.website_command` 保持兼容，并支持 `{media_manifest}` 指向当前快照；不在公开 Writer 写死私有桶、凭证或另造全站发布器。声明的视频通过 `_website-media.json` 交接，使用网站自己的 HTML `<video>` 播放器。

官网命令 exit 0 只代表命令正常结束；输出 `JOB_STATE=queued|running` 时回执为 pending，不结清 finalize、不重复发起任务。Agent 用 Website 状态入口查询同一任务后，以真实状态更新本篇回执并续跑（不要求作者手工操作）；成功后仍验当前正文及正式文章入口和本篇声明的正文图片、主题曲、播客、视频。部署 state、正文/图片/音频/视频验收分别报告，不能以封面可访问代替歌曲可播放。无官网 profile 仍记录 skipped，不影响通用 Skill。

官网完成记录绑定当前正文及媒体输入哈希。同名图片、音频或视频内容变化后，必须重新同步验收；旧记录缺少绑定也不能直接跳过。待处理任务的 job ID 在前置检查失败时仍须保留。

## 失败处理

- 非零退出：修复明确报错后重跑同一命令。
- 长命令尚未退出：每 60 秒以内报告一次存活进度，等待当前单写者返回；禁止另开终端、直调 renderer 或重复启动同一命令。
- 图片或 prompt 改动：重新 `visual-qa`、`seal visual`、`release-to-draft`；标题、正文、播客提示词或生成参数改动还必须重跑 `podcast-pregen`。
- 草稿已创建但读回失败：不得删除 attempt，不得手工登记 media ID。
- 需要换 provider：只改 `renderer-policy.json`，不得改 canonical prompt 或图片比例。
