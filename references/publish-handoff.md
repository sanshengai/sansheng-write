# 把成品交给 sansheng-distribute

统一分发技能名称为`sansheng-distribute`。此处交接合同不变；按分发端已验收的平台能力执行，名称确定不代表全部平台已可用。

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

若文末往期推荐使用其他文章的本地封面，显式增加 `--image-dependencies /path/images.json`，格式为 `{"image_dependencies":[{"path":"/absolute/previous/cover.png","sha256":"实际64位小写SHA256"}]}`。仅接受正文实际引用的图片及逐字节哈希；空清单、未声明越界、哈希漂移和多余文件均拒绝。导出将这些图片复制进本篇过程目录并封存，不修改原稿；派生 HTML 去掉旧 `data-local-path`，上传器只使用封存后的 `src`。

锚点由 Write 放在最终 HTML 的实际插入处，必须唯一匹配。主题曲按 `_music-manifest.json` 正式记录、播客按 `dist/podcast/audio.mp3` 解析；仅在最终 HTML 有对应既有占位时自动关联。旧版动态占位文案可通过 media 显式声明，不模糊猜测。Markdown 声明了视频但 HTML 丢位置时拒绝导出，不把视频追加到文末。

导出到 `过程记录/publish/<版本指纹>/`，原定稿不修改。派生 HTML 将锚点换为可见 `【发布媒体:id】`，同时记录前后文；图片相对路径只在派生副本里调整。manifest 锁定原 Markdown/HTML、派生 HTML、所有本地图片和音视频的哈希。远程图片只锁定 URL，不声称校验了远端字节。

导出成功只代表生产端交接，不代表平台已支持/接受或作者授权发布。发布器须按当前账号实测选择全 API 或 API 建稿后编辑器补媒体；播放器保存后重新读回位置、顺序与内容。原生组件插好后禁止未经核对再用旧 HTML 覆盖草稿。外部回执通过下述 `import-publish` 回导，不直接改名成内置 `_publish-receipt.json`，也不能重新建稿补凭证。已有内置草稿继续原恢复入口，待发布器显式认领远端 ID 后才切换写入者。

默认微信导出遇到已有内置 `_release-attempt.json` 或 `_publish-receipt.json`（含空/坏记录）会拒绝，防止把已有远端稿重新创建。同一篇文章交给其他平台不受微信历史记录限制。

实验迁移入口：在上述生产命令加 `--existing-draft <旧回执中的草稿ID>`。必须有 schema2 已核验旧回执，源文件、正文、封面和元数据仍对应原版本；文章根和过程记录里的重复记录须一致。仅有提交尝试或坏回执时先只读恢复，不能新建补凭证。导出保留旧远端 ID、已上传图片身份及预期正文，作为交接包的封存依赖。发布器应先 `prepare` 再 `adopt`，只读核验同一草稿；禁止以新建稿执行该包。

已有媒体位置必须为唯一可见纯文字。导出同时保存 `legacy_anchor` 和标准槽位；编辑器核对旧文字与上下文，仅替换该位置。旧 HTML 注释、正文手改漂移或未知原生组件不猜位置，需先核对。已插播放器需发布器取得真实组件与源文件映射，不能仅凭旧回执认定已播放。旧草稿迁移仍仅通过离线合同测试。另有真实文章联调副本已完成新草稿的四个原生媒体槽、官方读回、回导及同 ID 续跑；不代表旧稿迁移、正式发表或手机客户端已验收。

若 Markdown 使用 `<!-- VIDEO: demo -->` 而旧 HTML 是可见占位文字，在同一 media 项显式写 `markdown_anchor: "<!-- VIDEO: demo -->"` 与 `anchor: "旧 HTML 中的实际占位文字"`，两处均须唯一匹配。无需修改已封存原稿；发布端只按 HTML 位置操作。

## 已核验草稿回导

```sh
python3 scripts/pipeline.py --dir /path/article import-publish --receipt /path/verified-write-receipt.json
```

发布器应先重新读回同一草稿，输出兼容 schema2 的凭证及不可变证据文件。Write 核对原稿/媒体哈希、当前生产封存、草稿与封面身份、官方正文摘要和原生媒体/排版观察后，写 `_external-publish-receipt.json` 并更新 publish 阶段。旧回执保留；相同草稿和素材的音频交接单不重写，已有音频核验不因重复导入失效。

存在外部凭证后，`release-to-draft` 转入同一导入核验，不再次上传建稿。缺证据、源稿漂移或不同草稿 ID 会拒绝。此入口的终点为草稿；它不授予发表/群发权限，不跳过正式链接与归档检查。含新视频槽的正式文章收尾尚待真实样本验证，不能以草稿回导通过宣称 finalize 全链已通过。

发布目标中的作者、摘要、封面、原文链接和留言设置应与本篇 Write 预期元数据一致，不能只传标题和账号。公众号不能保留普通外链时，由分发账号显式配置可见网址策略；派生结果单独留证，原稿保持不变。
