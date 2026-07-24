# sansheng-write · 中文长文写作引擎

> **把「选题 → 大纲 → 正文 → 改稿 → 排版 → 配图」跑完的 Claude Code skill。喂它你的语料，它长出你的声音。**

**中文** | [English](./README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/sandypoli-boop/sansheng-write?style=flat)](../../stargazers)
[![Last commit](https://img.shields.io/github/last-commit/sandypoli-boop/sansheng-write)](../../commits/main)

---

## 先看产出，再决定装不装

**↓ 20 秒手机实拍：一篇公众号长文从选题落定到成品排版，跑完整条链的样子。**

https://github.com/user-attachments/assets/7b5d8a8c-7caf-41e3-957e-5c2428859c79

一句「帮我写一篇关于 X 的文章」，它跑完这条链，最后给你一份**微信公众号能直接粘贴**的 HTML：

```
选题快评 → 大纲（含开篇策略分流）→ 正文 → 改稿（去 AI 味三层过滤）
   → 标题（内联锻造 5 个候选）→ 排版（10 个组件 + 契约门）→ 配图 / 封面
```

排版组件都在 `templates/`，配色跟着你的主题走：

| 组件 | 用途 |
|---|---|
| 导读栏 | 文首「一句话说清这篇讲什么」卡片 |
| PART 编号 H2 | 大标题 + 副标题，自动编号 |
| 时间线 H3 | 小标题竖线时间轴 |
| 要点卡 / 金句卡 | 左竖条 + 浅色底，轻盈不厚重 |
| 数字卡 / 步骤条 / 对比块 | 结构化信息，HTML 注释指令驱动 |
| 表格品牌化 | 主题色表头、列宽自动计算、手机端横滑 |
| 深读模块 / 链接卡 / 关注卡 | 文末转化 |

质量不靠自觉，靠**契约门**：作者审批绑定具体稿件摘要；baoyu 语义生产者与像素渲染器分别留痕；最终视觉、HTML 与微信草稿 media_id 用 receipt 逐层绑定。产出被改过，已完成下游会自动变成 `dirty`，不能拿旧绿灯继续发。

```console
$ python scripts/format_layout.py 定稿.html --all --check
  ✅ 成功将 3 个原生 H2 转换为 PART 格式
  ✅ 表格品牌化完成（主题色表头 / 行分隔线 / 交替行色 / 圆角容器）
  ✅ 成功将 3 处重点标记转换为主题色文字
  ⚠️  2 个警告（非阻塞），无错误
```

门里检查半角标点、加粗密度、词性比例、套话黑名单、信息图数量、封面比例……

---

## 这是什么

一套**中文长文的写作方法论 + 排版工程**，封装成 Claude Code 的 skill。

它**不是**「输入标题、输出文章」的一键生成器。它是一条有纪律的流水线：
每个阶段有它该读的规则，每个产出有它该过的门。你在里面的角色是主笔，不是甲方。

它也**不是**通用写作助手。它为「中文、长文、要发出去给人读」这个场景做了很多取舍：
排版针对微信公众号的 HTML 限制做了大量妥协，去 AI 味的规则针对中文的套话习惯。

### 它到底帮你做什么

| 阶段 | 它做什么 | 你做什么 |
|---|---|---|
| 选题 | 快评这个题值不值得写、从哪个角度切 | 拍板 |
| 大纲 | 按内容类型分流开篇策略（资讯直入 / 成果前置 / 故事钩子），搭骨架 | 改结构 |
| 正文 | 按你的风格手册写，注入你的金句库与声纹样本 | 挑开头（唯一法定停顿点） |
| 改稿 | 三层过滤去 AI 味 | 手改（它会从你的 diff 里学） |
| 标题 | 内联锻造 5 个候选并排序 | 选一个 |
| 排版 | 一键出微信 HTML，契约门把关 | 看一眼 |
| 配图 | 封面 / 信息图 / 数据图（数据图用 matplotlib 画，不让模型编数字） | 提意见 |

### 去 AI 味的六条核心

不是句式伪装，是内容层的要求：

1. **So What 兑现** -- 每个论点替读者问一句「所以呢」并答上
2. **类比落地** -- 抽象判断必须配一个读者的手能碰到的日常场景
3. **反常细节锚** -- 关键场景给一个反常到不像编的具体细节
4. **把自己写笨** -- 不立权威，讲教训不讲功绩
5. **段落具体领头** -- 每段第一句给具体的人 / 事 / 画面 / 数字
6. **句间引力** -- 上句尾留钩子，下句头接住

**诚实边界**：这六条只有「写前喂料 + 写后自觉」，**没有机器强制校验**。
`exit 2` 的硬门只拦正则抓得到的表层指纹（套话、半角标点、整句加粗计数）。
语义层的人味，正则测不出来，同一个模型自审也照不出来 -- 只能靠换个模型做语义差分。

---

## 开箱效果 vs 喂料后效果

**这一节比上面所有内容都重要。**

| | 你会得到 |
|---|---|
| **开箱**（不配 profile） | 完整的方法论引擎：结构、纪律、去 AI 味过滤、排版工程。产出干净、不像 AI 通稿 |
| **喂料后**（自建 `profile/corpus/`） | 上面全部，**加上你自己的声音** |

**不喂料时，产出接近通用 AI 写作 -- 这是设计，不是缺陷。**

风格是你的语料长出来的，不是提示词变出来的。这个仓库里**没有任何真实作者的风格手册**：
那类手册要从别人受版权的作品里蒸馏，不该由我打包分发给你；何况模仿谁本来就该你自己挑。

取而代之的是：

- 一份 [怎么自建作者风格手册](profile.example/corpus/authors/README.md) 的 HOW-TO（三步，含可直接用的蒸馏提示词）
- 一份虚构作者的 [示例手册](profile.example/corpus/authors/example-author.compact.md)，演示格式与颗粒度
- 一份 [原创的人味示例集](profile.example/corpus/voice-samples.md)，没自备语料时自动注入做基础兜底

顺带一提：**最该做的第一份手册是「你自己」的**。把你写得最满意的 20 篇丢进去蒸馏，
出来的手册会告诉你一些你没意识到的自己的习惯 -- 有些值得保留，有些该改。

---

## 三条使用路径

按你愿意装多少东西分三档。**每一档都能独立用；缺东西只降级那一个环节，不断整链。**

### ① 纯方法论（零门槛）

选题 / 大纲 / 正文 / 改稿 / 标题，全流程可用。

```bash
pip install pyyaml
python scripts/setup_check.py     # 体检：告诉你能跑到第几档
```

### ② + 排版出微信 HTML

加：一键排版、契约门、10 个组件模板。

```bash
# 再装：bun（跑 markdown→HTML 转换器）+ Node 18+
cd scripts && npm install         # jimp：给配图加水印
```

### ③ 全自动到发布

加：配图、封面、信息图、推送草稿箱。

```bash
cp .env.example .env              # 填你自己的 key
```

### 依赖矩阵

| 依赖 | 哪一档要 | 缺了会怎样 | 怎么装 |
|---|---|---|---|
| Python 3.10+ / PyYAML | ① | 全都跑不了 | `pip install pyyaml` |
| Pillow | ③ | 生图缩放、配图压缩不可用 | `pip install pillow` |
| bun | ② | markdown→HTML 转换跑不了 | [bun.sh](https://bun.sh) |
| Node 18+ / jimp | ② | 配图加不了 logo 水印 | `cd scripts && npm install` |
| **baoyu-skills 插件** | ② 起硬依赖 | md→HTML、像素渲染与微信 API 适配不可用 | 安装 `JimLiu/baoyu-skills`；provider 与微信 key 配在它自己的 `~/.baoyu-skills/` |
| 已配置的 image provider | ③ | `render-visuals` 非零退出 | 按 `baoyu-image-gen` 配置 provider/model；业务视觉规则仍由本 Skill 编译 |
| `MINIMAX_API_KEY` | ③ | BGM 硬门失败，不能推草稿 | MiniMax 国内站密钥 |
| 微信公众号 appid/secret | ③ | `release-to-draft` 无法创建并读回草稿 | 配在 baoyu 侧 `~/.baoyu-skills/.env`（**非本仓 .env**）；后台还需加 IP 白名单 |
| playwright / matplotlib | ③ 可选 | SVG 转 PNG、数据图画不了 | `pip install playwright matplotlib` |

低档能力可以独立使用；一旦进入“定稿→草稿箱”机械链，配图、BGM、视觉 QA、发布预检和官方读回都是硬门，任一失败都会非零退出，禁止静默降级。

---

## 安装

```bash
# 方式一：Claude Code 插件市场
claude plugin marketplace add sandypoli-boop/sansheng-write
claude plugin install sansheng-write

# 方式二：clone + 软链
git clone https://github.com/sandypoli-boop/sansheng-write.git
ln -s "$(pwd)/sansheng-write" ~/.claude/skills/sansheng-write
```

### 国内加速下载

GitHub 直连不畅时，给 clone 地址前面加一层公共镜像即可（下载源码 zip 同理）：

```bash
# 加速 clone（把 gh-proxy.com 换成 ghfast.top 即备用镜像）
git clone https://gh-proxy.com/https://github.com/sandypoli-boop/sansheng-write.git
```

插件市场方式暂无稳定国内镜像；网络不畅时用上面的加速 clone + 软链。

## 更新

升级到新版，取决于你当初怎么装的：

- **插件市场装的**：`claude plugin marketplace update` 刷新市场，再 `claude plugin update sansheng-write`
- **clone + 软链装的**：进本仓目录 `git pull`（软链即时生效，不必重装、不必重连）

**怎么知道有新版**：看本仓 [Releases](../../releases)；点仓库右上角 **Watch → Custom → Releases**，发新版时 GitHub 会通知你。每版改了什么见 [CHANGELOG](CHANGELOG.md)。

## 快速上手（从 clone 到第一篇）

```bash
python scripts/setup_check.py                       # 1. 体检：告诉你能跑到第几档、还缺什么
cp -r profile.example ~/my-writing-profile          # 2. 复制一份 profile
export SANSHENG_WRITE_PROFILE_DIR=~/my-writing-profile
export SANSHENG_WRITE_DATA_DIR=~/my-articles        # 3. 文章存哪
$EDITOR ~/my-writing-profile/context.md             # 4. 告诉它你是谁（写给谁、怎么说话）
$EDITOR ~/my-writing-profile/brand.yaml             # 5. 署名 + 主题 + 身份卡（发公众号才需要）

# 要出微信 HTML（②档）再补：装 bun + Node 18 + baoyu-skills 插件，然后
cd scripts && npm install                           # jimp 水印
# 要全自动配图/发布（③档）再补：
cp .env.example .env                                # 填生图 key；微信凭证配在 baoyu 侧（见依赖矩阵）
```

然后在 Claude Code 里说一句「帮我写一篇关于 X 的文章」。
每一步缺了什么，`setup_check.py` 都会指出来；缺件只降级对应环节，不断整链。

## 配置

三层分离 -- **代码在仓里，你的东西在你自己的目录里**：

| 层 | 放什么 | 在哪 |
|---|---|---|
| ① 仓库 | 代码 + 方法论 | 这里 |
| ② profile | 配色 / 署名 / 身份卡 / 语料（**私有但非密**） | `SANSHENG_WRITE_PROFILE_DIR` |
| ③ secrets | API key（**只从 env 读，永不打印，报错时打码**） | `.env`（gitignored） |

不配 profile 也能跑 -- 自动回退到仓内 `profile.example/`（中性配色 + 占位署名）。
这是正常路径，不是错误。

**换主题一行搞定**（`profile/brand.yaml`）：

```yaml
theme: "sage"      # slate 钢青（默认） | ink 近墨黑 | sage 草木绿 | jade 青玉绿 | amber 琥珀赭 | plum 梅子紫
```

模板里一个 hex 都不用改 -- 排版最后一步由 `process_theme()` 统一替换。

## 隐私

- 密钥只从 env / `.env` 读，**从不打印**，报错信息里自动打码。
- 运行观察日志（`_skill-observations.jsonl`）**只写本地、不联网**，
  文章名默认写哈希。整个日志可以关：`SANSHENG_WRITE_TELEMETRY=off`。
- 你的语料、草稿、密钥，不会被发送到任何地方。生图 / 发布是你显式调用时才打对应的 API。

---

## 配套文章 · Article

_（讲这个 skill 怎么用、以及怎么脱敏开源的公众号文章 -- 写好后补链接）_

---

## 关于作者 · About the author

<p align="center">
  <a href="https://sanshengai.top"><strong>🌐 网站 sanshengai.top</strong></a> ·
  <a href="https://namecard.xiaoyuzhoufm.com/nnl8x"><strong>🎧 小宇宙</strong></a> ·
  <a href="https://weibo.com/u/7546221967"><strong>微博</strong></a> ·
  <a href="https://www.xiaohongshu.com/user/profile/5c716b6d000000001000f5c4"><strong>小红书</strong></a> ·
  <a href="mailto:sandypoli@gmail.com"><strong>✉️ 邮箱</strong></a>
</p>

我是**叁笙**，一个用 AI 做内容、也用 AI 造工具的人。我做了个人站「[叁笙早安 AI](https://sanshengai.top)」--
每天清晨一份 AI 早报，加深度长文，还有一堆自己写来自己用的小东西：读书蒸馏、职业 AI 风险测评、
GitHub 宝藏精选、AI 羊毛铺……

这个仓里的 skill，就是我做这些内容时在真实工作流里一点点磨出来的。它写过的每一篇我都亲手改过，
改的地方又回头变成了它的规则。觉得好用，就清洗脱敏开源出来 -- 你可以直接用，也欢迎改成自己的。

如果这些东西对你有用，欢迎来[网站](https://sanshengai.top)逛逛，或**扫码关注公众号「叁笙早安AI」**
（公众号没有跳转链接，扫码最快）：

<p align="center">
  <img src="assets/qrcode-gongzhonghao.png" alt="微信公众号 叁笙早安AI" width="200">
  <br><sub>微信扫码关注 · 叁笙早安AI</sub>
</p>

---

## 致谢与依赖 · Credits & Dependencies

### 致谢（借鉴来源）

- **[baoyu-skills](https://github.com/JimLiu/baoyu-skills)** by [宝玉](https://github.com/JimLiu)（MIT）--
  排版链上游的 markdown→HTML 转换、信息图与发布工具链。本 skill 的排版后处理接在它的产出之后，
  skill 的组织方式也从中借鉴颇多。**不捆绑分发，请自行安装。**

- **[gzh-design-skill](https://github.com/isjiamu/gzh-design-skill)** by 甲木 × 摸鱼小李（AGPL-3.0）--
  排版层的重要方法论参照：「文章类型 → 组件配方表」、视觉层级与全文用色配额、封面文案策略
  （两层标题分离 / 五视角）、「模板源头 lint + 产物 HTML 校验」双关卡、待补素材居中占位约定，
  这些设计思想均借鉴自该项目。仅借鉴思路：本仓的组件 HTML 与校验脚本均为独立实现，
  不含其代码或模板。**不捆绑分发，两项目互不依赖。**

- **[WeWrite](https://github.com/oaker-io/wewrite)** by [oaker-io](https://github.com/oaker-io)（MIT）--
  「学习我的修改」闭环飞轮的整体设计（lessons → playbook 聚合、pattern 类型划分）、内容增强
  四策略框架（角度发现 / 密度强化 / 细节锚定 / 真实体感）与微信兼容微调思路源自该项目；
  脚本代码为独立实现。**不捆绑分发。**

- **[humanizer](https://github.com/blader/humanizer)** by [blader](https://github.com/blader)（MIT）--
  反 AI 味过滤器中「四种高频 AI 句式」的识别框架来自该项目。

### 运行依赖（不捆绑，请自行安装）

| 依赖 | 许可 | 用途 |
|---|---|---|
| [jimp](https://github.com/jimp-dev/jimp) | MIT | 给配图加 logo 水印 |
| [PyYAML](https://pyyaml.org/) | MIT | 配置与作品库读写 |
| [Pillow](https://python-pillow.org/) | MIT-CMU | 生图缩放、配图压缩 |
| [Playwright](https://playwright.dev/) | Apache-2.0 | SVG 转 PNG（可选） |
| [matplotlib](https://matplotlib.org/) | PSF-based（BSD 兼容） | 数据图（可选） |
| baoyu-skills | MIT | markdown→HTML / 信息图 / 发布 |

画中文数据图需要中文字体。建议用 OFL 许可的
[Noto Sans CJK](https://github.com/notofonts/noto-cjk) / 思源黑体，
而不是 Windows 自带的微软雅黑（专有字体）。

### License 兼容性

本仓以 **MIT** 分发。**仓内不捆绑任何第三方源码**（`scripts/node_modules/` 已 gitignore，
由你 `npm install` 生成）。上表均为**运行时依赖**，其许可与本仓分发无关，已逐个核对并标注。

---

## License

[MIT](LICENSE) © 2026 叁笙 (sansheng)
