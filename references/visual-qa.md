# 独立视觉 QA · 适配器与排障（L3 · 按需）

发布链上的位置、命令顺序与授权口径在 `release-runtime.md` §4，本文只讲**怎么接一个复核器**、
以及**这道闸失效时长什么样**。日常 SOP 不必读。

## 为什么必须是独立进程

图不能由生成它的模型自己审 —— `visual_qa.py::validate_qa_result` 会拿 `reviewer.model`
和 request 里所有 `generation.model` 求交集，撞上直接判不合格。

skill **不会替你自动指派复核器**：谁来看图必须由使用者在 `SANSHENG_WRITE_VISUAL_QA_COMMAND` 显式配置。自己指派一个复核器，
等于自己给自己发合格证。

## 接入契约

```text
<command> --request <_visual-qa-request.json> --output <candidate.json>
```

进程正常退出即可，「复核不通过」不要用非零退出码表达 —— 把结论写进 JSON，
交给 `visual_qa.py` 的校验器统一裁决，否则「进程炸了」和「图没过」两种语义会混在一起。

## 现成适配器：`visual_qa_claude.py`（推荐配置）/ `visual_qa_codex.py`

两个后端跑**同一套验收合同**（提示词、schema、逐项判据、信道自检全部从 codex 版复用），
只有「看图的独立进程」不同。配置写进仓根 `.env`（与 profile 指针、各家 key 同一个配置面，
换机复刻只拷一份）：

```
SANSHENG_WRITE_VISUAL_QA_COMMAND=["python3","-X","utf8","<绝对路径>/scripts/visual_qa_claude.py"]
```

- 🔴 **Claude Code 自己就能看图，只是不能生图**（2026-09-19 作者拍板「不用通过 codex 看图，
  Claude Code 自己看图就好」）。这道闸不依赖 Codex 额度：有一次实跑时 Codex 的
  usage limit 把复核卡了两小时，图早就渲好了，纯粹在等一个别家的看图进程。
- `visual_qa_claude.py` 每张图各起一个全新的 `claude -p --tools Read --add-dir <图目录>`
  无头进程（不带当前会话上下文，独立性与 codex 版同级）；默认模型 `claude-opus-5`，
  可用 `SANSHENG_WRITE_VISUAL_QA_MODEL` / `_JOBS`（默认 3）/ `_CLAUDE`（可执行文件）覆盖。
  实测 2 张图并发约 80 秒。
- `visual_qa_codex.py` 保留为备用后端（`SANSHENG_WRITE_VISUAL_QA_MODEL` 默认 `gpt-5.6-terra`、
  `_JOBS`、`_CODEX`）。⚠️ 走 ChatGPT 账号的 codex **不放行 `gpt-5.6-codex`**（服务端 400
  明确拒绝），别照抄历史文章 `_visual-qa.json` 里记的模型名。
- `visual_qa_openai.py` 是第三个后端：任意 OpenAI 兼容 `/chat/completions` 视觉模型（默认取
  `OPENAI_BASE_URL` / `OPENAI_API_KEY`，可用 `SANSHENG_WRITE_VISUAL_QA_BASE_URL` / `_API_KEY` 单独指定，
  模型默认 `gpt-5.6-terra`）。另一次实跑：Claude 与 Codex 都不方便时走中转，6 张图约 2 分钟，
  合同与判据同样全部复用 codex 版；`json_schema` 不被中转接受时自动退到 `json_object`。
- `-X utf8` **不能省**：子进程被 `capture_output` 管道接走后默认走 GBK，打中文直接崩。
- 复核模型必须与生图模型不同族；`visual_qa.py::validate_qa_result` 会拿两边 model 求交集。

## 🔴 三种静默失效（都不报错，只是悄悄失灵）

复核卡住时先怀疑这三条，再怀疑图。

### ① 提示词根本没送到复核模型

Windows 上 codex 的入口是 `codex.cmd`，批处理 shim 转发 `%*` 时会**吃掉多行参数**。
模型只收到图片、收不到任何要求，于是凭 `--output-schema` 编出一份格式合法、
checks 全 true 的结论 —— 闸门被架空却毫无征兆。

症状：`notes` 里写着「未提供目标文案或风格合同」，而 `checks` 照样全 true。

适配器已改走 stdin 完全绕开 shell 解析；另用「结论有没有复述 `required_visual_traits`」
做信道自检 —— 一条都对不上就报**进程失败**，而不是「复核未通过」（后者会让人去改图，
改到天亮也没用）。

### ② 糊字被脑补成通顺句子

生图模型偶尔会把中文字形画坏；看图模型又可能把看不清的字补成上下文里合理的词。
这只是 QA 必须严格逐字转写的理由，不是改用 SVG、确定性字体或后期叠字的理由。

实测：hero 图渲成「重置不是**祸利**，是**昀**家公司**付溻针**」，复核判 `text_match` 通过。

对策写在提示词的「转写纪律」里：逐字辨认 → 认不出写 `□` → 禁止补全 → **先转写再对白名单**
（顺序反了就会被白名单牵着走）。转写里只要出现 `□`，适配器一律判失败 ——
这不是替模型裁决，是执行它自己给出的信号。

### ③ 转写被打碎，好图被误杀

下游是把 `observed_text` 拼接后做子串匹配。两行标签被拆成
`['Codex', 'Claude', '主动补发 20 次', '事故赔偿 6 次']`（每张卡的第一行先写完、再写第二行）时，
拼接串里根本不存在「Codex 主动补发 20 次」，一张完全正常的图会被判成「这句话不在图上」。

提示词要求按「块」合并转写，并直接给了这个反例 —— 只讲规则时模型照样会拆。

## 原生文字路线不因错字风险改变

100+ 篇生产历史表明，当前生图模型的中文还原已经足以支撑一次性原生生图。独立 QA 的
职责是发现偶发事故并触发同 prompt 单张重渲，不是把文字从画面里拆出来。任何“为了防错字，
先出无字底图，再让模型写 SVG / HTML / Canvas 或用本地字体补字”的建议都违反正式合同，
因为它会破坏粘土字的材质、光照、色系和场景融入度。

## 改判定口径的纪律

- **适配器只转述，不裁决。** 模型判 false 就写 false，绝不「兜底修正」成 true，
  也绝不把模型没看见的文字塞进 `observed_text`。一旦开始兜底，它就退化成盖章机。
- 口径要改就改 `CHECK_DEFINITIONS`，并保证与 `visual_qa.py::validate_qa_result` 一致；
  两边不一致会出现「复核说不过、校验器说过」的分裂，人只能靠猜。
- 已固化的三条边界：白名单内的产品名与署名不算意外文字；脚本按固定 2% 内边距叠的
  署名不算裁切风险；色板只约束**设计元素**（标签条/箭头/高亮/图标），黏土人偶的肤色、
  木头纸张的自然土色是配方允许的。

## 排障

- **`_visual-qa.raw.json`**：无论通过与否都落盘。候选 JSON 校验不过会被上游删掉，
  raw 是事后查「哪张图哪一项没过」的唯一线索。
- **复核有抖动**：同一批字节可能这次过、下次卡在某条边界特征上（如封面徽章数量
  「两到三个」判成四个）。反复卡同一项时先看 `notes` 说的是不是事实，
  再决定重出图还是改契约，别机械重渲。
- **重渲之后必须重跑后处理**：`add_logo.js` + `compress_images.py`。压图脚本会把
  后处理造成的字节漂移补记进 `.gen-log.jsonl`，`render-visuals --only` 沿用未重渲的图
  时正是拿这条记录对账 —— 漏跑就会报「文件内容与历史记录对不上」。
