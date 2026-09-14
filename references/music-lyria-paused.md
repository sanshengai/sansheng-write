# Lyria 自动生成通道（暂停维护参考）

当前默认是 MiniMax 网页手动生成。只有作者明确要求恢复或排查 Lyria 时才读取和执行本页；缺 MP3、缺 ADC 或已授权“完整流程”均不等于授权恢复。以下为历史实现记录，不证明当前服务可用，恢复时须重新核实端点、模型和实际权限。

## 自动生成通道（Lyria 3）

> 🔴 **提炼环节不调任何模型**：由 **Claude 在 BGM 阶段按下面《Claude 提炼标准》提炼**，作为参数传给脚本；脚本是纯执行器（拼 V2 空灵 prompt → Lyria 3 写词生成）。
> （生成环节本身走 Google Vertex；这与「提炼不调模型」不冲突，别再沿用旧文档里"不碰 Google"的说法。）

```bash
python "$SKILL/scripts/generate_article_bgm.py" "<文章目录>" \
    --theme-brief "虚无缥缈的诗意主旨叙事（一句，方法A 据此自动写词）" \
    --imagery "柔美画面词,逗号分隔,如 薄雾,潮汐,微光" \
    --song-name "既诗意又点题文章主题的短歌名" \
    --style ambient_piano --gender male

# 参数优先级：CLI > article-meta.yaml music 块 > 规则兜底
#   --theme-brief  不传则用 frontmatter digest/description 兜底（音色不如诗意提炼空灵，会警告）
#   --style  ethereal_folk|ambient_vocal|ambient_piano|cinematic_vocal|shanghai_jazz_soul（默认 ethereal_folk）
#   --gender 默认按序号奇偶交替（奇女偶男）；shanghai_jazz_soul 例外默认女声
#   --model 默认 lyria-3-pro-preview
```


## API 调用要点（Vertex Lyria 3 · interactions）

| 项 | 值 |
|----|----|
| 端点 | `POST https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/global/interactions` |
| 鉴权 | `Authorization: Bearer $(gcloud auth application-default print-access-token)` |
| 模型 | `lyria-3-pro-preview` — 本管线**固定用这一个**，不要换 |
| 入参 | `{"model": "...", "input": "<自然语言描述，含风格/人声/配器/主旨/简体中文歌词要求>"}` |
| 返回 | 同步；`outputs[]` 含 `type=audio`（**内联 base64 mp3**，无链接过期问题）、`type=text`×2（歌词 / caption） |
| 计费 | $0.08/首（Clip $0.04）。走 `aiplatform.googleapis.com` = Cloud 计费，**$300 赠金覆盖** |

### 🔴 三个坑（错任一个都报错，且报错措辞会把人带偏）

| 现象 | 真正原因 |
|------|----------|
| **404** `not found or your project does not have access` | 用了 `publishers/google/models/{M}:predict`——那是旧版音乐模型的端点形态，对 Lyria 3 必然 404。**不是**没白名单（public preview 无需 allowlist），社区里大批人卡在这个误判上，本管线 2026-05 也栽在这里 |
| **401** `API keys are not supported by this API` | interactions 只认 OAuth2。`.env` 里那把 `AQ.` 开头的 Vertex Express key 用不了（它是给 `gen_img.py` 的） |
| **403** `Permission 'aiplatform.interactions.create' denied` | project 选错。必须用**当前 ADC 账号自己有权限**的 project，别拿 `.env` 里的 `GOOGLE_VERTEX_PROJECT` |

> 🔴 **歌词默认出繁体**——prompt 必须显式写「Simplified Chinese（简体中文，NOT traditional）」，
> `build_music_prompt()` 已内置该约束，改 prompt 时不要删掉。
> 🔴 **只用 `lyria-3-pro-preview`**。Google 还有别的音乐模型，但要么纯器乐没人声、要么只出 30 秒片段，都顶不了主题曲——本管线不提供切换选项，避免选错。

---
