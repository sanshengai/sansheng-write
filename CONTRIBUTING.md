# 参与贡献 · Contributing

欢迎 PR。这个仓库很小，规矩也少。

## 开工前先做一件事

```bash
git config core.hooksPath .githooks
```

这会打开提交前的密钥护栏。它会拦下形似 API key 的内容和 Windows 个人路径。
**不要用 `--no-verify` 绕过它** -- 它拦你的时候，通常真的有东西不该提交。

## 本地跑起来

```bash
pip install pyyaml pillow            # 最小依赖
python scripts/setup_check.py        # 体检：看你能跑到第几档
python -m pytest -q                  # 全绿才提 PR
```

## PR 前的自检清单

- [ ] `python -m pytest -q` 全绿（看完整 summary 行，别用管道 `| tail` 判成败 -- 管道退出码会骗你）
- [ ] 没有把配色 / 署名 / 身份卡写死进代码或模板 -- 那些属于 `profile/brand.yaml`
- [ ] 没有新增硬编码的 hex 色值。要加就先加进 `profile.example/brand.yaml` 的令牌表，
      再在 `format_layout.py` 的 `_THEME_DEFAULTS` 里登记映射；`scripts/lint_templates.py` 会检查
- [ ] 没有引入任何真实文章 / 真实语料作为测试夹具。测试一律用 `tests/golden/_synthetic_*/` 下的合成件
- [ ] 改了 `scripts/format_layout.py` 或 `scripts/contracts.py`？先读 `scripts/README.md` 的
      「跨脚本契约」一节 -- 那两个文件有别的脚本 import 它们的常量

## 改什么最有价值

| 方向 | 说明 |
|---|---|
| 更多排版组件 | `templates/` 下加一个组件 + `format_layout.py` 里加一个 `process_*` 阶段 |
| 更多主题 | `profile.example/themes/` 下加一套完整调色板（**必须给全套键，只写一半会换皮换一半**） |
| 平台适配 | 目前排版针对微信公众号的 HTML 限制做了很多妥协；欢迎适配别的平台 |
| 写作规则 | `references/` 下的方法论，欢迎带着你的实证来讨论 |

## 不接受什么

- 把某位真实作者的文章 / 风格手册塞进仓库（版权问题，也不该由我替你选模仿对象）
- 用某个具体品牌的配色 / 署名替换中性默认值
- 为了让测试变绿而放宽契约门（`scripts/contracts.py` 里的硬门是有意设计的）

### 关于「文档里为什么还有人名」

`references/` 里会出现奥威尔、阿西莫夫、朱光潜这类名字，那是**方法论出处的署名引用**
（六规则、透明玻璃、与读者的四种关系）。这和「打包分发某人的风格手册」是两回事：

| | 处理 |
|---|---|
| 引用某人提出的**方法 / 规则**，注明出处 | **保留署名**。删掉署名却留着规则，那叫剽窃 |
| 从某人的**受版权作品**里蒸馏风格手册、摘录原句 | **不发**。改成教你怎么自建（`profile/corpus/authors/README.md`） |
| 把某位在世作者当作「我要写成他那样」的声音目标 | **不发**。那是个人品味，写进你自己的 `profile/context.md` |

提 PR 时请照这个分界线来。

## 提交信息

用中文或英文都行，说清「改了什么 + 为什么」。不需要 conventional commits。
