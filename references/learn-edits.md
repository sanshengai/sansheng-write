# 闭环学习飞轮 (Learn Edits)

> **触发条件**：用户说 "我改了，学习一下" 或 "学习我的修改"。
> **目标**：通过比对 AI 生成的草稿和用户手工修改的定稿，提取用户的写作偏好（Pattern），并聚合成规则库（Playbook），让下一次生成的初稿更接近用户的期望。

---

## 🔴 冷启动 SOP（主动 bootstrap，别等飞轮自然攒）

> **背景（"顺但没味道"诊断）：** 这套飞轮是整条写作链**唯一**能注入"你本人味道"的回路，但空仓时它**一直空转**——`playbook.rules: []`、`voice_corpus_index.count: 0`、`lessons.yaml` 的 `lessons: []` 全空。通用规则 + 他人样本只能逼近平均水准；**真正的"味道"必须来自你本人手改的正例**（研究印证：风格迁移"从样本学强、从名字学弱"，冷启动种子要个性化）。所以与其等飞轮被动攒满 30 段，不如**主动冷启动**。这是整套"去 AI 味"改造里成本最高、但长期杠杆最大的一项——把味道从"借来"变成"长出来"。

**🟡 为什么这一步无法全自动（必须你参与）：** 飞轮学的是「AI 初稿 → 你的终稿」的**句子级 diff**。要有 diff，就得有"改之前"和"改之后"两份。Claude 手里只有已发布的**终稿**，没有对应的 AI 初稿原件，**无法凭空造出 diff**。所以冷启动的"喂料"得你出。两条路：

- **路径 A（有原件，首选）：** 从近 5-8 篇你**亲自润色过**的已发布文章里，找出 AI 初稿原件——可能在文章目录的历史文件 / `.bak` / git 历史里。有原件就跑 `learn_edits.py diff --draft <初稿> --final 定稿.md`，Claude 读 diff 提炼 lessons。
- **路径 B（无原件，退而求其次）：** 你翻开一篇已发布文章，**逐段标出"这句不像我说的话 / 我当时改了什么 / 我会怎么说"**（语音口述转写也行）。Claude 把这些标注转成 lessons（type=expression / tone / word_sub…）。这等于让你直接告诉飞轮"我的味道长什么样"。

**冷启动步骤：**
1. 你选 5-8 篇最能代表自己味道的已发布文章。
2. 按路径 A/B 拿到每篇的 diff 或"哪句不像我"标注。
3. Claude 按下方「执行步骤 Step 3」提炼 Pattern，写进 `lessons.yaml`（每篇沉淀 1-2 条，**承接 / 选词 / 节奏类优先**）。
4. 跑 `learn_edits.py build` 编译进 `playbook.md` 的 `rules`，并往 `voice_corpus_index.count` / `profile/corpus/voice-samples.md` 攒正例段落。
5. 此后每写一篇新文，你若手改了，就顺手"学习我的修改"沉淀 1-2 条，飞轮转起来。

**🟡 交接给你（Claude 无法独立完成的部分）：** 回路（脚本 + lessons/playbook 结构 + 本 SOP）**Claude 已全部备好**；缺的只是"第一批喂料"。**只要你给出第一批 1-2 篇的 diff 或"哪句不像我"的标注，Claude 就能立刻跑通整条回路**，验证后再补全 5-8 篇。`rules` 设 confidence 阈值，低置信只作软参考，避免过拟合单篇。

---

## 执行步骤 (Agent 操作指南)

当用户要求"学习修改"时，Agent 必须严格按照以下步骤执行：

### Step 1: 获取草稿和定稿

1. 询问用户："请提供修改前的草稿文件路径，以及你修改后的定稿（可以直接把内容粘贴给我，或者给我文件路径）。"
   - *提示：如果当前工作目录下有 `.md` 文件，你可以主动帮用户找一找。*

2. 确保在工作目录下同时存有这两人份的内容，例如 `draft.md` 和 `final.md`。

### Step 2: 运行 Diff 分析

使用 `learn_edits.py` 脚本生成差异对比：

```bash
python "$SKILL/scripts/learn_edits.py" diff --draft <旧文件> --final <新文件>
```

### Step 3: 提取 Pattern 并追加到 lessons.yaml

1. 仔细阅读 Step 2 脚本输出的 Diff 结果。
2. 识别用户修改的**核心意图**（不要只看表面的字词替换，要看背后的逻辑）：
   - 是把段落切碎了？
   - 是去掉了某种特定的起承转合词？
   - 是把抽象概念具象化了？
   - 是改变了情绪的浓度？
3. 对于每个有价值的意图，提炼为一个 Pattern。
4. 先定位飞轮文件：跑 `python $SKILL/scripts/profile_config.py` 看输出的 `flywheel` 行（配置了 profile 时在 `<profile>/flywheel/`，未配置即仓根）。查看该目录下 `lessons.yaml` 现有的 Pattern，如果本次的意图和已有的某个 key 是一回事，**必须复用现有的 key**。
5. 将新的 Pattern 追加到上一步定位的 `lessons.yaml` 的 `lessons` 列表中。

**Pattern 数据结构要求**：
- `key`: 简短的英文标识（如 `shorter_paragraphs`, `avoid_jiangzhen`）
- `type`: `word_sub` (词汇替换) / `para_delete` (段落删除) / `para_add` (段落新增) / `structure` (结构调整) / `tone` (语气改变) / `expression` (表达习惯) / **`reference_preference` (元偏好，如"倾向引 KOL 而非研究报告")** / **`discourse` (篇章级——文章谈论自己/复述自己/金句节拍这类跨段模式)** / **`weave` (品牌织网——你手动补进稿子的 联动已发文章/推自有阵地/埋伏笔 动作)**
- `rule`: 能够直接作为 Prompt 指令的**祈使句**（例如："不要使用'讲真'，用'坦白说'代替"）
- `description`: 对本次修改的简要描述

**🔴 分层指引（实证：词句级规则被执行了但病根往往在篇章层）：**
蒸馏每个 diff 时先问：「这改的是**一句话**（→ word_sub/expression/tone），还是**文章组织自己的方式**（→ discourse/structure）？」篇章级信号举例：删掉整段复盘、把"还记得前面"改成原样重复意象、把段首加粗口号移到段尾。**优先沉淀篇章级**——词句级规则通常覆盖较全，篇章级偏少，是飞轮下一阶段的主要缺口。

**🕸 织网信号（实证：织网动作常靠人工补，值得让飞轮学会）：**
diff 里发现你**手动加**了「已发文章链接 / 官网阵地引流 / 未来内容预告」这类动作 → 沉淀为 `weave` 类 Pattern，并回查该篇 `article-meta.yaml` 的 `weave:` 字段——若字段里没有这条决策，说明大纲步骤 7.5 漏答或答浅了，把具体场景（什么话题该联动什么资产）补进 `profile/brand-net.md` 对应区块，让下一篇的候选清单更准。

**RED 基线 backlog（待跑，token 重）：** 对 confidence ≥5 的核心规则逐条做对照验证——同一选题「有/无该规则」各跑一版初稿 diff，**无可观察差异的规则删除**（NO RULE WITHOUT A FAILING TEST）。排期：等改造后第一篇真实文章读感验证通过后，随下一次「复核 skill」一起跑，只对 6-8 条核心做。

---

## v5 playbook schema 升级

`playbook.md` 现在是**四段结构**，由 `learn_edits.py` build 模式以 **merge 模式**维护（不覆盖手动维护字段）：

| 段 | 内容 | 维护方式 |
|---|---|---|
| `rules:` | 字词/句式硬规则（≥5.0 硬执行 / <5.0 软参考） | learn_edits.py 自动 |
| **`reference_preferences:`** v5 新增 | 你反复手改呈现的高层风格倾向（如"倾向引 KOL 而非研究报告"） | learn_edits.py 自动（从 type=reference_preference 的 lessons 聚合） |
| **`voice_corpus_index:`** v5 新增 | 你的声音样本累计计数（threshold=3） | learn_edits.py 自动维护计数 dict；**自动灌库开闸**：`diff` 模式默认把你实质改写/新写的散文段自动提进 `profile/corpus/voice-samples.md`（`--no-promote-voice` 可关；`add-paragraph` 为手动精选补充）。prep §一·声 注入 gate = corpus 内容 >200 字（≈2-3 段即触发） |
| **`noise_filter_rules:`** v5 新增 | 训练语料排除规则（排除混入的软广 / 风格污染样本） | **你手动维护** |

**关键**：`learn_edits.py _write_playbook()` 已升级为 merge 模式，build 前先读现有 playbook，保留 `reference_preferences / voice_corpus_index / noise_filter_rules` 三个字段，只更新 `rules:`。**手动维护的 `noise_filter_rules` 不会被覆盖**。

**写作时如何使用 v5 schema**（writing.md Step 4 加载）：
- `rules` confidence ≥ 5.0 → 硬性约束
- `reference_preferences` → style-routes 检索时的第二信号（第一信号是大纲 `[目标风格 X]`）
- `noise_filter_rules` → 加载 author compact 前过滤训练语料（防训练语料污染导致的风格沉默漂移）

### Step 4: 编译生成 Playbook

更新完 `lessons.yaml` 后，必须执行以下命令，让系统重新计算每个规则的置信度，并更新到 `playbook.md`：

```bash
python "$SKILL/scripts/learn_edits.py" build
```

脚本输出 `✅ playbook.md 更新完成` 后，向用户汇报学习成果（列出提取了哪些新规则，以及哪些老规则得到了强化）。
