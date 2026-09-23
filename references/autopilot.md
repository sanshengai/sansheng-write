# 全流程自动驾驶

适用于完整新文章的自动主链：从选题到微信草稿箱连续推进。先服从本轮约定终点；仅要大纲、正文、局部改稿或排版时，完成该产物即止，不为满足流水线创建后续阶段。主题曲使用手动交接：定稿接管后先交付生成单，等待作者提供 MP3 期间继续不依赖音频的工作。

## 默认路径：创作在对话里推进，作者拍板后接管定稿

前半程（选题 → 大纲 → 正文 → 磨稿 → 双复核）按下面 1–4 的 reference 在对话里推进，产物落在文章目录，**不启用大纲 / 正文的状态机阶段**；作者每次拍板都用 `approve --words` 把原话逐字落盘（不手写审批文件），定稿拍板后 `adopt-final` 接管，进入 release-runtime.md 的机械链。这是实际在用的主路径；给大纲、正文阶段也记状态的完整模式见文末附录，可选。

## 启动

```bash
python "$SKILL/scripts/pipeline.py" status
```

先读 profile 上下文。已接管的文章从最早 pending/dirty 阶段恢复；还没接管的，从下面对应步骤继续。不要重做已通过且摘要未变化的阶段。

## 主流程

1. **选题与大纲**
   - 读取 `outline.md`、近三篇作品和必要信源。
   - 先建目录：`pipeline.py new "<选题名>" --genre news|tutorial|deep|promo`（资讯快讯 / 教程 / 深度 / 推广）。
     它按文体从 `templates/article-meta.template.yaml` 与 profile 生成 `article-meta.yaml`（带受控词表注释，
     文体相关字段预填、标题摘要等留空），**不复制上一篇的任何文件**——照抄上一篇会把旧值、渲染策略和
     社媒风格一起继承下来。编号取数据目录、归档目录与作品库的最大序号加一。
   - 写 `大纲.md`，按大纲逐项填 `article-meta.yaml`。
   - 「大纲 + 5 套标题/封面方案 + 开头候选」一包交作者拍板。作者选定后：

     ```bash
     python "$SKILL/scripts/pipeline.py" approve blueprint --source-mode new-draft \
       --words "<作者原话>" --title "<选定标题>" --opening "<开头选择>" \
       --outline "<大纲要点>" --cover-style montage-evidence
     ```

     命令按作者原话生成 `_blueprint-approval.md` 并封存；缺标题 / 开头 / 大纲 / 封面风格任一项直接拒绝。
     作者明说免检时改用 `--source-mode checkpoint-waived`。
2. **内容增强**
   - 按 `content-enhance.md` 补充案例、反例、类比和可验证事实。
3. **正文**
   - 资讯快讯、教程先读对应执行卡（`执行卡-资讯快讯.md` / `执行卡-教程.md`，每张 ≤10 KB、每条注明出处），
     大文档只在拿不准时按出处查；其他文体照常读 `writing.md`。
   - 运行 `prep_writing.py`，按执行卡或 `writing.md` 与选定风格手册写 `定稿.md`。
   - 生成标题候选并确定最终标题。
   - 🔎 **写完立刻跑 `pipeline.py preflight`**，把静态问题一次清完再往下走。
     它不花配额、几秒返回，覆盖：闸门锚点文件、H2/`part_subtitles` 对齐、
     加粗密度、开篇重点标识、文末 DEEP READ / SOURCES、金句库来源标记、
     `visual-plan.json` 合法性。
     （一次实跑教训：这些检查此前散落在排版与 finalize 阶段，
     开篇标识迟 3 个阶段才报、金句库来源标记迟 5 个阶段，
     导致 `verify_layout` 反复 6 轮、`verify_publish` 反复 8 轮。）
4. **磨稿与双复核**
   - 运行反 AI 磨稿：读出声 → [polish-whitelist.md](polish-whitelist.md) 白名单减法 → `pipeline.py verify writing` + `audit_quant_signals` → anti-ai-filter 语义层 → 冷读/事实复核。不为像人加料。
   - 事实复核与语义冷读使用独立上下文，产出结构化记录。
   - 定稿交作者审读；作者说通过后：

     ```bash
     python "$SKILL/scripts/pipeline.py" approve draft --source-mode author-provided-final \
       --words "<作者原话>"
     ```
5. **接管定稿**

   ```bash
   python "$SKILL/scripts/pipeline.py" adopt-final --final 定稿.md --meta article-meta.yaml
   ```

   显式进入 `release-from-final` 模式，不是伪造写作历史。🔴 `adopt-final` **没有作者审批权**：
   运行前必须已有 `审批结论：通过` 的 `_draft-approval.md`；缺失、拒绝或尚未确认都会原子失败，
   不写 state、release job 或 checkpoint receipt。接管只读取并绑定审批文件 SHA 与定稿 subject，
   绝不改写审批文件。接管成功就交付主题曲生成单（见下一步）。
6. **定稿后的机械链**
   - 只读 [release-runtime.md](release-runtime.md) 并按命令顺序执行。
   - 视觉业务规划在本 Skill 内完成；外部 `baoyu-image-gen` 只渲染像素。
   - BGM 是发布硬门。默认按 `music.md` 交付 `MiniMax-主题曲生成单.md`（歌名、主题、风格提示词、完整歌词、导出要求），**定稿接管成功就交付，不等配图做完**，作者生成音乐和配图并行；收到 MP3 后接入。Lyria 暂停，不自动调用或要求配置 Google Cloud。
   - ⏱ **BGM 注入 AUDIO-CARD 后，启用了 `podcast.wechat_embed: true` 就立刻跑 `pipeline.py podcast-pregen`**。它先写入同级 PODCAST-CARD，再生成音频；随后才允许排版与草稿。未显式开启嵌入时，仍可预生成 RSS，但公众号保持单卡。
   - 固定首屏顺序是「导读 → 主题曲卡 → 播客卡 → 正文」；两卡同宽上下排列。
   - 草稿创建只运行 `release-to-draft`；作者人工插入两份微信原生音频后可直接正式发布，`finalize <永久链接>` 会先自动做正式文章双音频补验（发布前自检 `wechat-audio-check` 可选）。

作者直接交来已确认的定稿时，跳过 1–4，从 `approve draft` 开始。

## 合同门要求 subagent，但当前运行时不给 subagent 时

事实复核（`fact-check.md`）与语义冷读（`semantic-review.md`）都要求独立上下文，
视觉 QA 还要求独立看图进程。**当宿主运行时不允许派 subagent 时，这不是跳过的理由，
而是降级执行**：由主 agent 就地完成，但必须在产出文件顶部**显式写明执行方式与
诚实边界**（哪些是机器可定位的、哪些是同模型自审照不出的盲区）。

伪造成「已派独立评审」是不允许的；直接 `skip` 也是不允许的。

## 合法停顿

- 用户明确要求逐步确认。
- 等作者拍板大纲 / 定稿（blueprint / draft 检查点）。
- 已交付完整 MiniMax 主题曲生成单，等待作者提供 MP3；这是人工素材交接，不是定稿重审或生成失败，不能把生成单算成已完成 BGM。
- 缺凭证、权限、输入文件或外部服务不可用。
- 非零合同门经同因重试三次仍失败。

除此之外不因“下一步可能费时”停顿，也不把失败 stage 标成 done。

## 并行

默认可并行独立调研、事实复核和语义冷读；具体合同见 `orchestration.md`。对同一文章目录有写入的发布机械链必须串行。

## 恢复

- `status` 显示 dirty：从最早 dirty 阶段重验。
- renderer 失败：按同一 prompt 和比例走已配置 fallback。
- 图片后处理后变化：重新 `visual-qa`、`seal visual`。
- 微信草稿已创建但读回失败：复用 `_release-attempt.json`，不得重复建稿。
- 正式发布后取得永久链接：运行 `finalize`，不要分别手工归档和同步官网。

## 自动化边界

自动流程止于微信草稿箱。原创声明、赞赏、正式发布和朋友圈实际发送由作者完成；拿到永久链接后，归档、官网同步和朋友圈文案生成可自动完成。

## 附录：完整状态机模式（可选）

需要给大纲、正文阶段也记状态时才用：`pipeline.py init` 建 state，大纲写完 `verify outline`、正文写完
`done writing title_final='…'` 与 `verify writing`，拍板照样用上面的 `approve` 命令（`--source-mode new-draft`
时定稿审批还要求 `_fact-check.md`、`_stutter-list.md`、`_draft-qc.md` 已就位）。profile 启用
`workflow.checkpoints` 后，`verify outline` 要求蓝图锚点同时含下面四项（作者免检授权整体放行）：

| 锚点 | 判据 |
|---|---|
| 5 套标题+封面文案 | 文中出现 `方案 1` ~ `方案 5`；或写明「作者指定标题」 |
| 开头选择 | 含「开头」 |
| 大纲结论 | 含「大纲」 |
| 封面风格 | 含「封面风格」 |

审批结论只看结论行（`审批结论：` / `作者免检授权：`）：结论行出现「不通过 / 未通过 / 拒绝 / 驳回 /
不同意 / 尚未确认 / 待确认」即判 rejected；`approve --words` 生成的文件把作者原话放在引用块里，不参与判定。
检查点是唯一错误时，pipeline 记为 `waiting_author`（⏸），不记 `failed`、不累计 `fail_count`；
`status` / `next` 会直接显示所需作者动作，拍板凭证通过后自动转为 `done`。
