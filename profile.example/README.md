# profile.example/ -- 把它复制一份，改成你自己的

这个目录是**三层分离**的第二层：装「私有但非密」的东西 -- 配色、署名、身份卡、语料。
API key 不在这里（那是 `.env` 的事）。

## 30 秒上手

```bash
cp -r profile.example ~/my-writing-profile
export SANSHENG_WRITE_PROFILE_DIR=~/my-writing-profile      # Windows: setx
python scripts/profile_config.py                            # 确认读到了你的 profile
```

**不配置也能跑** -- 会自动回退到本目录（中性示例值）。这是正常路径，不是错误。
只是产出物会带 `Your Column` 这类占位署名，提醒你还没配。

## 文件一览

| 文件 | 干什么 | 必改？ |
|---|---|---|
| `brand.yaml` | 品牌 token：配色 / 圆角 / 署名 / 身份卡 | **是**（身份卡里全是假值） |
| `themes/*.yaml` | 三套预置配色：`slate` 钢青 / `ink` 近墨 / `sage` 草木 | 否（在 brand.yaml 里填 `theme:` 即可整套换皮） |
| `context.md` | 品牌身份 / 人设 / 对话约定，写作时全程生效 | **是**（这是"你是谁"） |
| `corpus/voice-samples.md` | 原创的人味示例集，没自备语料时兜底注入 | 否 |
| `corpus/authors/README.md` | 教你怎么自建作者风格手册 | 否（读一遍） |
| `corpus/authors/example-author.compact.md` | 一份虚构作者的示例手册 | 换成你自己做的 |
| `corpus/raw/` | 放你的原始语料（gitignored，不会被提交） | 你自己决定 |

## 换皮：一处改完，全局生效

`brand.yaml` 的 `colors` 是排版引擎的唯一色源。改它，下面这些**同时**跟着变：

- `templates/*.html` 的 10 个组件（渲染期替换，不用手改模板）
- `scripts/format_layout.py` 的排版输出
- 发布命令的 `--color` / `--author`

想整套换配色，别逐个改 hex，填一行就行：

```yaml
theme: "sage"   # slate | ink | sage
```

## 开箱效果 vs 喂料后效果

| | 你会得到 |
|---|---|
| **开箱**（不配 profile） | 完整的方法论引擎：选题 / 大纲 / 写作纪律 / 反 AI 味过滤 / 排版工程。产出干净、不像 AI 通稿 |
| **喂料后**（自建 `corpus/authors/` + `context.md`） | 上面全部，**加上你自己的声音** |

不喂料时产出接近通用 AI 写作 -- **这是设计，不是缺陷**。
风格是你的语料长出来的，不是提示词变出来的。
