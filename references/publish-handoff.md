# 独立发布器交接

Write 保留创作、排版与媒体位置的责任。独立发布器接收中性交接包，负责账号、上传、原生组件插入、草稿/发表与读回。此入口可选；现有 `release-to-draft` 和公开用户的默认配置不变，不要求安装任何私有 Skill。

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

导出成功只代表生产端交接，不代表平台已支持/接受或作者授权发布。发布器须按当前账号实测选择全 API 或 API 建稿后编辑器补媒体；播放器保存后重新读回位置、顺序与内容。原生组件插好后禁止未经核对再用旧 HTML 覆盖草稿。收到草稿回执后仍复用本 Skill 的官方核验与后续归档链，不能手工伪造现役发布凭证。
