# 独立发布器交接

Write 保留创作、排版与媒体位置的责任。独立发布器接收中性交接包，负责账号、上传、原生组件插入、草稿/发表与读回。此入口可选；现有 `release-to-draft` 和公开用户的默认配置不变，不要求安装任何私有 Skill。`pipeline.py export-publish` 复用内置路线的接管校验、发布预检和封存；底层 `export_handoff()` 只做合同转换，不能替代生产预检。

```sh
python3 scripts/pipeline.py --dir /path/article export-publish --targets /path/targets.json --media /path/media.json
```

targets.json 示例（账号、标题与终点必须使用实际选择，不默认升级公开）：

```json
{"targets":[{"id":"wechat-main","platform":"wechat","account":"main","content_type":"article","endpoint":"draft","title":"文章标题"}]}
```

media.json 示例：

```json
{"media":[{"id":"demo-video","kind":"video","path":"素材/demo.mp4","anchor":"<!-- VIDEO: demo -->","role":"product-demo"}]}
```

锚点由 Write 放在最终 HTML 的实际插入处，必须唯一匹配。主题曲按 `_music-manifest.json` 正式记录、播客按 `dist/podcast/audio.mp3` 解析；仅在最终 HTML 有对应既有占位时自动关联。旧版动态占位文案可通过 media 显式声明，不模糊猜测。Markdown 声明了视频但 HTML 丢位置时拒绝导出，不把视频追加到文末。

导出到 `过程记录/publish/<版本指纹>/`，原定稿不修改。派生 HTML 将锚点换为可见 `【发布媒体:id】`，同时记录前后文；图片相对路径只在派生副本里调整。manifest 锁定原 Markdown/HTML、派生 HTML、所有本地图片和音视频的哈希。远程图片只锁定 URL，不声称校验了远端字节。

导出成功只代表生产端交接，不代表平台已支持/接受或作者授权发布。发布器须按当前账号实测选择全 API 或 API 建稿后编辑器补媒体；播放器保存后重新读回位置、顺序与内容。原生组件插好后禁止未经核对再用旧 HTML 覆盖草稿。外部回执不能直接改名成内置 `_publish-receipt.json`；回导适配未验收前，外部草稿与原 finalize 不能宣称闭环，也不能重新运行内置建稿补凭证。已有内置草稿继续原恢复入口，待发布器显式认领远端 ID 后才切换写入者。

默认微信导出遇到已有内置 `_release-attempt.json` 或 `_publish-receipt.json`（含空/坏记录）会拒绝，防止把已有远端稿重新创建。同一篇文章交给其他平台不受微信历史记录限制。

实验迁移入口：在上述生产命令加 `--existing-draft <旧回执中的草稿ID>`。必须有 schema2 已核验旧回执，源文件、正文、封面和元数据仍对应原版本；文章根和过程记录里的重复记录须一致。仅有提交尝试或坏回执时先只读恢复，不能新建补凭证。导出保留旧远端 ID、已上传图片身份及预期正文，作为交接包的封存依赖。发布器应先 `prepare` 再 `adopt`，只读核验同一草稿；禁止以新建稿执行该包。

已有媒体位置必须为唯一可见纯文字。导出同时保存 `legacy_anchor` 和标准槽位；编辑器核对旧文字与上下文，仅替换该位置。旧 HTML 注释、正文手改漂移或未知原生组件不猜位置，需先核对。已插播放器需发布器取得真实组件与源文件映射，不能仅凭旧回执认定已播放。此迁移仅通过离线合同测试，真实编辑器和回执回导仍未验收。

若 Markdown 使用 `<!-- VIDEO: demo -->` 而旧 HTML 是可见占位文字，在同一 media 项显式写 `markdown_anchor: "<!-- VIDEO: demo -->"` 与 `anchor: "旧 HTML 中的实际占位文字"`，两处均须唯一匹配。无需修改已封存原稿；发布端只按 HTML 位置操作。
