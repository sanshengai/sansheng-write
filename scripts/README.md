# scripts/ 结构索引

两个引擎文件各 ~120KB、2400+ 行，是本 skill 的排版与质量门核心。本文件是它们的导航图。
**2026-07-10 建档（F-4）**：源码内已插入分节锚点，只插注释行、未改任何代码行（AST 等价性已证）。

## 怎么导航

```bash
grep -n "# ===== 【第" scripts/format_layout.py   # 一次性得到完整目录
grep -n "# ===== 【第" scripts/contracts.py
```

`【第` 是全库唯一 token，不与既有 `# ====` 装饰横幅冲突。
**行号会随编辑漂移**，下表行号为 2026-07-10 基线；定位请用 `grep "def 函数名"` 或节锚点，别死记行号。

---

## format_layout.py -- 排版引擎（2434 行 / 20 节）

把 baoyu-markdown-to-html 的原始 HTML，清洗为满足 `references/layout.md` 规范的最终发布版。确定性、幂等。
入口：`main()`（CLI）→ `run()`（编排各 `process_*` 阶段）。

| 节 | 区块 | 说明 |
|---|---|---|
| 1 | Design Tokens 品牌色令牌 | SSOT，被 `lint_templates.py` import 当调色板 |
| 2-3 | log / article-meta 读取 | meta 值覆盖 argparse 命名空间 |
| 4 | 模块10 预发布自检 `--check` | 铁律0 / 品牌色 / 组件完整性 |
| 5 | 模块1 H2/H3 转换 | H2→PART 编号、H3→时间线 |
| 6 | 模块2 表格品牌化 | 绿头 / 列宽计算 / 横滑 / 术语卡 |
| 7 | 模块3 导读栏注入 | purge 旧导读 + 孤儿 hero + body h1 后注入 |
| 8 | 模块4 底部推荐+名片 | |
| 9 | 模块5 品牌色全局替换 | legacy 蓝/红/灰 → 品牌绿 |
| 10 | 模块6 清 AI 生图提示词 | |
| 11 | 模块6.5 列表重排版 | 无序→绿箭头、有序→圆形编号徽章 |
| 12 | 模块7 主题色重点文字 | `<mark>` / `***粗斜体***` → 品牌绿 |
| 13 | 模块8 划重点卡片 | |
| 14 | 模块8.5 结构组件 | stat 数字卡 / steps 步骤条 / compare 对比块 |
| 15-16 | 模块9 导读引用块 / 模块11 微信兼容 | 图片圆角、`<p>` 强制 color |
| 17 | 主流程 preflight | 排版前扫定稿致命缺陷、修图片路径反斜杠 |
| 18 | 模块8.6 交付附件 | 生成 `_layout-decision.md` |
| 19 | `run()` 主编排 | 契约门链（preflight + contracts 各 verify_*）→ 顺序调 process_* |
| 20 | `main()` CLI | argparse；无 flag 默认 `--all` |

### 函数索引

| 节 | 行 | 函数 | 可见性 |
|---|---|---|---|
| 2 | 85 | `log` | 公开 |
| 3 | 93 / 110 | `load_article_meta` / `apply_meta_to_args` | 公开 |
| 4 | 139 / 265 | `check_all` / `print_check_results` | 公开 |
| 5 | 290-371 | `_clean_h2_text` `_auto_split_h2_subtitle` `_build_part_h2` `_revert_part_h2` | 私有 |
| 5 | 417 / 488 | `process_h2` / `process_h3` | 阶段 |
| 6 | 610-710 | `_char_weight` `_compute_column_widths` `_scroll_col_px` `_is_term_table` `_render_term_cards` | 私有 |
| 6 | 736 | `process_table` | 阶段 |
| 7 | 1014-1085 | `_purge_existing_lead` `_purge_orphan_hero_in_body` `_strip_body_h1` | 私有 |
| 7 | 1099 | `process_lead` | 阶段 |
| 8-13 | 1182 / 1246 / 1312 / 1353 / 1415 / 1485 | `process_footer` `process_colors` `process_prompts` `process_lists` `process_highlights` `process_takeaway` | 阶段 |
| 14 | 1591 / 1626 / 1653 | `process_stat` / `process_steps` / `process_compare` | 阶段 |
| 15-16 | 1692 / 1735 | `process_lead_quote` / `process_wechat_compat` | 阶段 |
| 17 | 1795 / 1921 | `preflight_markdown` / `normalize_img_local_paths` | 公开 |
| 18 | 1961-1996 | `_scan_md_structure` `_render_layout_facts` `write_layout_decision` | 混合 |
| 19-20 | 2034 / 2367 | `run` / `main` | 入口 |

> 所有 `process_*` 会被 `regression_baseline.py` 隔离 import 后逐一调用做纯变换比对 → 视为公开 API 表面，签名不得随意改。

---

## contracts.py -- 契约门引擎（2264 行 / 17 节）

各阶段的入场/出场校验与质量硬门。**不含任何 hex 色值**（已核实为 0）。

| 节 | 门 | 说明 |
|---|---|---|
| 1 | tier-1 入场/出场校验 | `validate_bundle` / `validate_output` + 5 个 `_validate_*` |
| 2 | 信息图集合门 P1.2 | 张数 / 构成 / 宽高比 / 体积 |
| 3 | 调研集合门 P2.2 | url 归一 + 官方源判定 |
| 4 | 内容增强集合门 P3.2 | 文本相似度阈值 |
| 5 | 封面集合门 P4.2 | 候选数 / 比例容差 |
| 6 | 审稿集合门 P5.2 | 最小角色数 |
| 7 | 词性比例门 I31 | 形/副 vs 名/动 |
| 8 | 加粗密度门 | |
| 9 | 发布素材门 | |
| 10 | 导读 lead 块门 | |
| 11 | B-主门 AI 腔黑名单 | `_BLACKLIST_HARD` 被 `prep_writing.py` import |
| 12 | B-软门 风格信号 | |
| 13-15 | 半角标点门 / 产物 HTML 门 / H2 副标题对齐门 | |
| 16 | 量化体检报告 | |
| 17 | skill 自省日志 | `log_observation` -- 唯一「写盘」例外 |

### 函数索引

`class ContractError`(3) · `validate_bundle`(18) · `validate_output`(185) · `verify_infographic_set`(288) ·
`verify_research_set`(542) · `verify_content_enhance_set`(773) · `verify_cover_set`(962) · `verify_review_set`(1126) ·
`verify_pos_ratio`(1221) · `verify_bold_density`(1320) · `verify_publish_assets`(1415) · `verify_article_meta_lead`(1608) ·
`verify_anti_ai_blacklist`(1801) · `audit_style_signals`(1888) · `verify_cjk_punctuation`(1982) · `verify_final_html`(2026) ·
`verify_h2_subtitle_align`(2085) · `audit_quant_signals`(2160) · `log_observation`(2232)

私有辅助：`_validate_*`(26-140) `_classify_aspect`(270) `_norm_url`(472) `_url_host`(489) `_host_matches`(499)
`_is_official_source`(508) `_ce_norm`(708) `_longest_common_substr_len`(725) `_ce_tokens`(749) `_strip_for_scan`(1717)

---

## scan_polish_signals.py -- 只读扫描软/硬门命中

对 `文稿成品/` 或单篇文章目录里的每篇 `定稿.md` 跑 `verify_anti_ai_blacklist`，打印 hard/soft 计数与最多 20 条抽样。不写盘、不改定稿。

```bash
python scripts/scan_polish_signals.py --dir 文稿成品
```

## 跨脚本契约（改动前必看）

| 依赖 | 说明 |
|---|---|
| `lint_templates.py` → `import format_layout as F` | 复用 Design Tokens 常量作调色板 SSOT。**改令牌名会连带断 lint_templates** |
| `prep_writing.py` → `from contracts import _BLACKLIST_HARD` | 私有常量实为跨脚本契约，改名要同步 |
| `regression_baseline.py` P0 门 | `_git_guard("scripts/format_layout.py")` 断言工作树对 `BASE_REF`（默认 `main`）**零 diff**。改动 format_layout.py 后必须提交进 main，回归门才会恢复通过；重构分支上把 `REGRESSION_BASE_REF` 钉在分支起点 |
| `format_layout.py` → `contracts` | try/except 双回退 import（含 sys.path.insert），两文件存在运行时软耦合 |
| `validate_bundle` | 无生产调用者，但被 `tests/test_contracts.py` import，且属对外契约 -- **不是死代码，勿删** |

## 品牌色台账（为 Phase 2 的 E-1 token 配置化预建档，本轮不改）

`contracts.py`：0 处 hex，无需处理。

`format_layout.py`（行号为 2026-07-10 基线）：

| 类别 | 位置 | 处置 |
|---|---|---|
| **令牌常量（SSOT）** | 45 `BRAND_GREEN #2F6F8F`、48 `BRAND_GREEN_2 #7FB0C4`，及圆角/浅绿底/边框/文字五类令牌 | E-1 抽为机器可读 token 源 |
| **legacy 检测/替换串（勿动）** | 198-204、1251、1256、1262、1266-1268（`#0F4C81` 蓝 / `#d14` 红 / `#f7f7f7` 灰） | 这些是**被清洗的目标值**，不是品牌值。tokenize 会破坏清洗逻辑 |
| **内联漏网品牌绿（rgba 形式）** | 358、360 `rgba(47, 111, 143,…)`；1256 替换目标 `rgba(47, 111, 143,0.05)` | E-1 应改为由令牌派生 |
| **中性色内联** | 365 `#333333`、550 `#ffffff`、778/788/1388/1639 `#fff`、1704/1718 `#666666`、1033 `#eef0f2`、1281 `rgba(0,0,0,0.1)` | E-1 纳入中性色令牌 |
| **docstring 内提及（非可执行）** | 1419-1420 说明文字里的 `#7FB0C4` / `#2F6F8F` | 随文档更新即可，无行为影响 |

> ⚠ E-1 的难点不在这里：品牌色还写死在 `templates/*.html` 静态模板、`generate_article_bgm.py` 的 AUDIO-CARD 串、以及发布命令的 `--color` 参数里。静态模板读不了 Python 常量，必须靠渲染期替换。详见开源改造执行计划 E-1。
