# 文章动态插图（可选）

默认仍生成静态图。作者明确要动态插图时，先读上下文，选一两处值得演绎的过程、对比或关系；每支片只承担一个解释任务。只接受 AI 插图，不把截图当作动态素材。先决定为什么动、什么动、前后状态说明什么，再补素材；主体缺失、物理关系错误或只有缩放时回到构图，不能靠多加动效补救。

写作端负责原文、位置与最终文章；`sansheng-image` 沿用已选画风色板，完成素材、导演稿、制作与实际连续审片。无声插图沿用 image 的动态入口；扩展为剪辑、配音或完整视频时再交接 `sansheng-video`。历史文章试验使用独立候选副本，保留已发布原文与图片。

## 先做可否成立的小样

正式装配前先验证一个完整动作周期：开头是什么状态，哪个物件因为什么发生变化，最后读者看懂了什么。暂时遮住解释字幕再看一遍：若只能看到方框换位置、标签换字或整图缩放，画面没有承担解释，返回动作设计。过程图应能辨认同一内容载体的变化；用途对比应能看见主体、标题和信息层次重新安排。小样先检查手机显示宽度、完整边缘、承接顺序和首尾衔接，再做全尺寸编码与来源交接。

更换动作不要求重写已确认的文章，也不要求重做无关截图、音乐或封面；只重验受影响文件与最终消费者。若原素材无法承担动作，应补完整部件并如实记录来源，不能把新生成部件写成从原图抠出。

## 接收与采用

先按 [画风库文章合同](stylebook-contract.md) 完成 schema2 静态计划、独立复核与整组选图。动态替换的是本篇已选中的正文图，不能替换封面。将本批 `素材/stylebook-sources/<摘要>.md` 作为 image 动态工程的 `--article`，原图使用选组中的确切最终图；不能把相似图片或仅作者正文摘要相同的另一个文件冒充来源。

在本篇运行 `pipeline.py request-article-motion --id 01 --purpose "这支图的具体解释任务"`。它输出冻结原文、选中原图的确切路径和摘要，以及可由 image 正常编译的 `brief_path`；需求本身不代表已制作。使用输出路径运行 image 的 `sb.py animate wake init <image> --brief <brief_path> --item 01 --out <新工程> --purpose "同一解释任务"`，由原有导演与备料流程继续制作。

image 制作审片通过后，用其 `animate wake handoff` 导出 `article-media.json`。合同为 `sansheng.article-motion/1`，状态 `reviewed_pending_user_adoption`，绑定原文及静态图摘要、精确引用句、画风色板、GIF 时序、实际渲染候选和审片，附 MP4、静态备用图、联系表及署名。

在本篇目录运行（脚本路径按实际安装位置填写）：

```sh
python3 "$WRITE/scripts/pipeline.py" prepare-article-motion --id 01 --handoff /path/to/handoff/article-media.json
```

这一步只接收候选，核对实际多帧 GIF、至少两轮审片、原文和当前选图，再使用与微信上传相同的准备函数生成最终 GIF 与首帧备用图。只复制合同声明的文件；结果保存在本篇 `素材/motion-candidates/<摘要>/prepared.json`。此时不修改正文，也不表示作者采用。

给作者看这份实际候选。只有作者明确采用后，按实际原话记录：

```sh
python3 "$WRITE/scripts/pipeline.py" adopt-article-motion --candidate 素材/motion-candidates/<摘要>/prepared.json --by "作者" --words "作者明确采用这支候选的实际原话"
python3 "$WRITE/scripts/pipeline.py" assemble-release
```

Agent 审片通过、一般性的“继续”或对旧片的认可，不能冒充作者看过当前候选。作者已明确委托 Agent 修好本篇并交草稿时，可在该范围内选择候选；`--by` 写实际选择者，`--words` 写委托原话与候选依据，保留“代理采用、待作者草稿审阅”的状态说明，不填写虚构的作者观片意见。没有这类委托时仍需当前候选采用。多张旧候选因制作方法变化失效时，用多个 `--candidate` 一次替换本轮整组；新候选全部验真、旧采用快照保持完整、未替换的项目仍须有效。不能手工删指针绕过。采用记录保存在不可变快照，当前指针为 `素材/article-motion-selection.json`。没有记录时使用静态图；空记录或损坏记录不能绕过为静态成功。

装配将选中的正文图引用为 `素材/infographic-01.gif`，同时保留 `素材/infographic-01.png` 作为该 GIF 的静态备用图。冻结原文和原始静态选图仍保留。当前版本不会根据平台自动切换备用图；需要静态交付时明确制作对应候选，不能在封存后手改引用。

随后照常运行 `visual-qa`、`seal visual`、排版及整篇阅读。动态候选、采用、实际 GIF 和备用图均进入装配及封存。原文、锚点、选图、时序、文件、准备方法或采用记录改变后，旧证据失效。升级导致方法指纹变化的待发布批次，须从冻结原文重建当前批次并复核；已发表文章不会被自动修改。

## 手机阅读与微信上传

整篇 HTML 必须引用同一份已采用 GIF。实际浏览器阅读时，除既有三个视口外，逐支连续看至少两轮，确认正文宽度下的文字、节奏、主体与首尾循环；放大预览清楚不代表手机正文清楚。将对应文件的播放观察保留在本篇过程记录，不能从旧样片继承通过结论。

整篇阅读 observation 增加 `motion_playback` 数组，顺序与封存 manifest 中的动图一致。每项记录实际 GIF 的绝对 `path`、`sha256`、手机视口 `width`（390 或 430）、实际 `cycles`（至少 2）和具体 `method`；`checks` 逐项确认 `all_states_readable`、`meaning_matches_context`、`loop_continuous`。`evidence` 至少两个不同状态的实际手机 PNG，每项为本篇相对 `path`、`sha256`、本轮片内 `at_ms`。程序核对文件与时间范围，画面含义仍由实际阅读者判断；只有首帧加载或重复静止截图不能通过。

微信的 [正文图片接口](https://developers.weixin.qq.com/doc/service/api/notify/message/api_uploadimage.html)只列出 JPG/PNG；[永久素材接口](https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html)明确列出 GIF。代码让 GIF 使用 `material/add_material?type=image`，静态 JPG/PNG 继续使用 `media/uploadimg`；本地 GIF 预算为 10 MiB。超出预算只尝试保留画面状态、停留时间和循环的 GIF 压缩，失败明确报错，不转成静态首帧。动画 WebP/APNG 需先导出 GIF。

永久素材上传成功仍不等于该 GIF 在公众号正文和手机预览可用。每份新文件的 `platform_playback` 初始为 `unverified`；按既有发布授权上传草稿后，回读 URL，再做本文件对应的手机播放与文字验收，另存平台证据。本地假服务测试通过不能填写平台已测试。

动态运行时及输出署名继续遵守 image 的上游许可记录，本合同不改变该许可。
