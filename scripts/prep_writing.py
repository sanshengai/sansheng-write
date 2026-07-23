#!/usr/bin/env python3
"""
prep_writing.py -- 写作前把参考料主动聚合渲染成 _prep-context.md

脚本主动算出「该用什么」并落地为一个产物文件，取代「请 Claude 自己去 Read 一堆散
文件」的装饰引用 -- 只有真被聚合到一份文件里的料，才会进模型动笔时的 working memory。

所有语料都从 profile 覆盖层读（未配置 SANSHENG_WRITE_PROFILE_DIR 时回退仓内
profile.example/，这是正常路径）：
  - 风格手册  profile/corpus/authors/<name>.compact.md
  - 声纹样本  profile/corpus/voice-samples.md（无自备语料时的基础人味兜底）
  - 金句库    profile_config.py::golden_lines_file()（默认 profile/corpus/golden-lines.md，可由 env 直指）
  - 风格示例  profile/corpus/style-examples.md
  - 整篇范文  profile/corpus/samples/<name>/*.md（可选）
缺料一律优雅降级：在产出里留一行提示、不刷屏、不崩。

用法（在文章工作目录运行）：
    python <skill>/scripts/prep_writing.py
    python <skill>/scripts/prep_writing.py --dir <文章目录>

聚合渲染到工作目录的 _prep-context.md（🔴 2026-06-10 P0-2 执行层改造）：
    0. 本篇三件最高原则（seed 原话逐字渲染 + 句间引力四动作 + 终审门）——
       6/7 改造的三个新原则此前只在 writing.md 文档层，从未进过本文件，
       等于从未进过模型动笔时的 working memory。现在固定置顶。
    1. 对应 author compact（按 article-meta.yaml 的 style 字段解析）
    2. 反 AI 写作工具箱（跨作者通用 self-check，全文写完后统一扫）
    3. 金句库（写作声音锚点 + 金句锻造句式 + 按文章主题匹配的 1 个主题 section）
    4. 风格 few-shot 示例（风格示例库.md 中匹配本路由作者的最佳段落）
    5. AI 腔写作禁区（直接从 contracts._BLACKLIST_HARD 渲染——与写后 B-主门同源）

    （词汇温度池配额表不再注入——配额化选词是新的公式化，黑名单已由机器 grep
    兜底（B-主门）。）

下游：B-主门 verify_anti_ai_blacklist 会断言 _prep-context.md 存在且 mtime
早于 定稿.md。跳过本步直接写 = 排版阶段硬门 fail。

诚实边界：本脚本只保证「料被聚合喂到」，不保证「料被吸收」——后者是 Claude
写作时的事，无法机械验证。但比起过去「料根本没喂到」，这是实质前进。
"""

import argparse
import sys
from pathlib import Path

# Windows 控制台 GBK 兜底：强制 stdout/stderr UTF-8，避免 emoji 触发 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Windows GBK 控制台下 print 中文会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SKILL_DIR = Path(__file__).resolve().parent.parent          # 本 skill 根目录
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from profile_config import corpus_dir, authors_dir, author_compact  # noqa: E402

# 作者名单不再硬编码 -- 从 profile/corpus/authors/ 里现有的 *.compact.md 动态发现。
# 你想模仿哪些作者，就在那里自建手册（方法见 corpus/authors/README.md）；本脚本
# 会把 article-meta.yaml 的 style / modifier_style 字段跟这些手册名做匹配。


def available_authors() -> list:
    """从 profile/corpus/authors/ 发现已装的风格手册名（*.compact.md 的前缀）。"""
    d = authors_dir()
    if not d.is_dir():
        return []
    return sorted(p.name[:-len(".compact.md")] for p in d.glob("*.compact.md"))

# 金句库主题 section → 关键词（用于按文章主题匹配）
TOPIC_KEYWORDS = {
    "商业模式 · 行业结构": ["商业", "行业", "模式", "公司", "生意", "市场", "品牌"],
    "投资逻辑 · 周期": ["投资", "周期", "股", "基金", "回报", "估值"],
    "认知 · 思维方式": ["认知", "思维", "判断", "决策", "心智"],
    "AI · 技术变革": ["AI", "人工智能", "技术", "大模型", "Claude", "算法", "智能"],
    "智能家居 · 生活方式": ["家居", "智能家居", "生活方式", "装修", "居家"],
    "育儿 · 成长": ["育儿", "孩子", "教育", "成长", "父母", "小孩", "亲子", "学习"],
    "管理 · 团队": ["管理", "团队", "员工", "领导", "组织"],
    "时代 · 人生": ["时代", "人生", "人性", "命运"],
}


def load_article_meta(cwd: Path) -> dict:
    """读 article-meta.yaml；缺 PyYAML 时做最小手动解析。"""
    p = cwd / "article-meta.yaml"
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        # 最小回退：只抓顶层 key: value
        meta = {}
        for line in text.splitlines():
            if line.startswith((" ", "#", "-")) or ":" not in line:
                continue
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
        return meta


def resolve_author(style_field: str, authors=None) -> "str | None":
    """从 style 字段（如「沉思长谈体」「某作者宏观俯瞰」）解析出已装的 author 手册名。"""
    if not style_field:
        return None
    for a in (authors if authors is not None else available_authors()):
        if a in style_field:
            return a
    return None


def resolve_modifiers(meta: dict, authors=None) -> list:
    """从 article-meta.yaml 解析叠加路由 modifier 列表。

    支持两种位置:
      - meta['modifier_style']: 字符串(单 modifier)或 list(多 modifier)
      - meta['modifiers']: 同上的别名

    modifier 就是「拿来做局部染色」的另一本作者手册；返回命中已装 author 手册名的
    modifier 列表(去重保序)。
    """
    raw = meta.get("modifier_style") or meta.get("modifiers") or ""
    if not raw:
        return []
    pool = authors if authors is not None else available_authors()
    candidates = [raw] if isinstance(raw, str) else (raw or [])
    out = []
    seen = set()
    for c in candidates:
        s = str(c)
        for m in pool:
            if m in s and m not in seen:
                out.append(m)
                seen.add(m)
    return out


def extract_section(md_text: str, section_title: str) -> str:
    """从 markdown 提取 `## section_title` 到下一个 `## ` 之间的内容。"""
    lines = md_text.splitlines()
    out, capturing = [], False
    for line in lines:
        if line.startswith("## "):
            if capturing:
                break
            capturing = section_title in line
            if capturing:
                out.append(line)
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def extract_style_examples(md_text: str, author: str) -> str:
    """从风格示例库.md（按写作环节分区结构）抽取本路由 author 的全部 few-shot 段落。

    文件结构约定：
      - 一级分区是写作环节（`## 一、开篇钩子` / `## 二、类比与杀手锏比喻` ...）。
      - 每个示例段落以 `**N ｜ 标题**` 开头，紧跟一行 `风格：<作者名>`。
    抽取逻辑：遍历每个环节区，把「风格：{author}」的段落连同所在环节标题一起收集，
    跨环节聚合 —— 让 author 路由能拿到自己在所有环节的全部示例段落。
    """
    if not author:
        return ""
    lines = md_text.splitlines()

    # 切分出每个示例段落块：以 `**` 开头（如 `**1 ｜ ...**`）到下一个段落/环节标题前。
    out_sections: list[str] = []   # 当前环节已收集的段落块
    cur_env_title = ""             # 当前环节标题（`## 一、...`）
    cur_env_emitted = False        # 当前环节标题是否已写入 out
    out: list[str] = []

    block: list[str] = []          # 正在累积的段落块
    block_author: str | None = None

    def flush_block():
        nonlocal block, block_author, cur_env_emitted
        if block and block_author == author:
            if not cur_env_emitted and cur_env_title:
                out.append("")
                out.append(cur_env_title)
                cur_env_emitted = True
            out.append("")
            out.extend(s.rstrip() for s in block)
        block = []
        block_author = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            flush_block()
            cur_env_title = line.strip()
            cur_env_emitted = False
            i += 1
            continue
        # 段落块起点：加粗的示例标题行 `**N ｜ ...**`
        if line.startswith("**") and line.rstrip().endswith("**"):
            flush_block()
            block = [line]
            block_author = None
            i += 1
            continue
        if block:
            stripped = line.strip()
            if stripped.startswith("风格："):
                block_author = stripped.replace("风格：", "").strip()
            block.append(line)
        i += 1
    flush_block()

    return "\n".join(out).strip()


def match_topic(meta: dict, jujul_text: str) -> str:
    """按 title/digest/tags/topic_keywords 关键词匹配金句库的 1 个主题 section。

    🔴 2026-06-20 D-1 修：原 haystack 读 project/selected_title/core_thesis/audience
    四个键，但真实 article-meta.yaml 根本没有这几个字段（死键），haystack 实际
    坍缩成只剩 title 单字段弱命中。改读真实存在的多字段，并扁平化 list 型字段。
    （topic_keywords 是给标题/摘要无主题明词的文章手填的命中兜底字段。）
    """
    def _flat(v) -> str:
        # tags / topic_keywords 是 list，扁平化避免 str(list) 把方括号引号也带进 haystack
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return str(v) if v else ""
    haystack = " ".join(_flat(meta.get(k)) for k in
                        ("title", "digest", "tags", "topic_keywords", "style"))
    best, best_hits = None, 0
    for section, kws in TOPIC_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in haystack)
        if hits > best_hits:
            best, best_hits = section, hits
    if not best:
        return ""
    return extract_section(jujul_text, best)


def _clean_gold_sample(text: str) -> str:
    """整篇范文注入前的机械清洗（🔴 2026-06-10 P1-8 前置护栏）。

    范文是「更近的信号」，若携带与 iron-rules 冲突的格式（全角破折号等），
    会以示范之名盖过红线——注入前必须清洗，这不是美化是护栏。
    """
    import re
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)        # 图片
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)    # 链接留文字
    text = re.sub(r'<[^>]+>', '', text)                     # HTML 标签
    text = text.replace('——', '--').replace('—', '-')       # 破折号铁律
    # 网页剪藏噪声：CSS 巨行（≥3 个 '{'）/ setext 下划线 / 原文地址引用行
    kept = []
    for ln in text.split('\n'):
        if ln.count('{') >= 3:
            continue
        if re.fullmatch(r'=+|-{4,}', ln.strip()):
            continue
        if ln.lstrip().startswith('>') and '原文地址' in ln:
            continue
        kept.append(ln)
    text = '\n'.join(kept)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def select_gold_sample(author: str) -> "tuple[str, str] | None":
    """从 profile/corpus/samples/<author>/ 选 1 篇完整金标范文（可选特性）。

    为什么注入整篇而非金句摘录：AI 腔是预训练分布偏置，规则描述压不动、
    剂量级范文压得动（真人片段逐字种入是最强人味放大器；把样本压缩成招式/句式
    公式正是「失味」路径）。整篇 = 完整语流示范。

    选样确定性：候选取 1200-8000 字、标题无商业推广/投稿痕迹的 .md，
    取字数最接近 3000 的一篇（典型单篇长度，避开合集/一览/超长）。
    未自备整篇范文时目录不存在——返回 None，优雅降级（这是可选料，不影响写作）。
    """
    if not author:
        return None
    sample_dir = corpus_dir() / "samples" / author
    files = list(sample_dir.glob("*.md")) if sample_dir.is_dir() else []
    if not files:
        return None
    skip_title = ("推荐", "报名", "扫码", "一览", "合作伙伴", "活动预告", "投稿")
    scored = []
    for f in files:
        if any(k in f.stem for k in skip_title):
            continue
        try:
            text = _clean_gold_sample(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        n = len(text)  # 清洗后净文字长度（剪藏 CSS/链接噪声已剔除）
        if 1200 <= n <= 8000:
            scored.append((abs(n - 3000), f.stem, text))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]))
    _, title, text = scored[0]
    return title, text


def render_top_principles(meta: dict) -> str:
    """渲染『本篇三件最高原则』置顶块（🔴 2026-06-10 P0-2）。

    为什么置顶：_prep-context.md 是 skill 明文指定「写作时真正要内化的这一份」，
    是唯一可靠进 working memory 的通道。种子/句间引力/终审门写在 writing.md
    里两次被实证不生效——必须渲染在模型动笔前读的第一屏。
    """
    seed = str(meta.get("seed") or "").strip()
    # 第一人称原话判据：seed 里至少有一句带「我」的句子，才算采到人味种子
    has_first_person = any("我" in s for s in seed.replace("\n", "。").split("。") if s.strip())

    lines = ["## 〇、本篇四件最高原则（先读这个，其余一切服从它）", ""]

    # 本篇开篇策略（🔴 2026-07-02 C8：outline 步骤 3.5 判定后写入 article-meta.yaml 的
    # opening_strategy 字段，带下来直接渲染，替代"每个下游各自重判"）
    opening = str(meta.get("opening_strategy") or "").strip()
    if not opening:
        # 缺字段时按 style 兜底推断：资讯直入路由默认直入
        _style = str(meta.get("style", ""))
        if "资讯直入" in _style:
            opening = "直入"
    if opening:
        _opening_hint = {
            "直入": "🔴 **资讯 / 时效类直入**：第一句直接说「发生了什么 / 它是什么」，不设故事钩子、不做概念铺垫、不先讲个人经历。",
            "成果前置": "🔴 **成果 / 实作类成果前置**：第一句亮成果（「我做了个 X」+ 能干什么），第一屏内给入口（网址 / 下载）+ 一个真实产出示例；「为什么做 / 制作背景 / 焦虑数据」降级到成果之后当动机、不当钩子。",
            "可钩子": "深度启发类：可用故事钩子（真实亲历优先，虚构慎用），走开头候选盲选。",
        }.get(opening, f"开篇策略：{opening}")
        lines.append("### 0. 本篇开篇策略（按 outline 步骤 3.5 分流，已定）")
        lines.append("")
        lines.append(_opening_hint)
        lines.append("")

    # 开篇标识配方（🔴 2026-07-02 D3：把"开篇每处该标什么"写进 working memory，不再靠事后
    # preflight 退回——实证 63 号开篇专名全裸、零标识仍过审，根因就是写作时脑子里没这根弦）
    lines.append("### 0-标. 开篇主题色标识配方（读者一眼扫核心，写开篇时就标，别留到磨稿）")
    lines.append("")
    lines.append("- **密度**：开篇区（正文开头 → 第一个 H2）每 ~120 字至少 1 处主题色标识（`**词**` 或 "
                 "`<mark>词</mark>`），每个 ≥40 字的段至少 1 处。排版 preflight 有硬门（不够 exit 2）。")
    lines.append("- **信息锚点六型，出现即标**：① 专名首现（产品/公司/网站名第一次出现）② 关键数字短语"
                 "（价格/倍数/评分连量词）③ 时间窗口（截止/生效日）④ 对比/转折结论 ⑤ 入口/行动锚"
                 "（网址/下载/操作/CTA，成果类第一屏必标）⑥ 落差/量级对比（个把小时/省 61%/从 X 到 Y）。")
    lines.append("- 🔴 **事实型优先**：①②⑤⑥ 是读者滑动时最先抓的事实，**先标全再看观点**；别把标识额度"
                 "全花在 ④ 观点/整句上（实测多篇标反——堆观点、漏事实）。")
    lines.append("- **≤15 字词组、不是整句**：整句加粗口号全篇 ≤2（金句节拍器）；标识是词组级视觉落点，不是把句子刷绿。")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("### 1. 种子 —— 本篇的人味起点")
    lines.append("")
    if seed and has_first_person:
        lines.append("> " + seed.replace("\n", "\n> "))
        lines.append("")
        lines.append("这是你（作者）本人的原话，**逐字保留区**：正文从这个种子长出来，原话所在句原样进正文，"
                     "磨稿阶段不许把它润色成通用书面语。全文的声音以这段话的说话方式为准。")
    elif seed:
        lines.append("> " + seed.replace("\n", "\n> "))
        lines.append("")
        lines.append("⚠️ **本篇种子不含第一人称原话**（没有一句带「我」的句子）——这是策划简报，不是人味种子。"
                     "建议回 outline 步骤 1.5 让作者说一句真话再动笔；硬写则心里有数：声音是空的。")
    else:
        lines.append("⚠️ **本篇无人味种子**（article-meta.yaml 的 seed 为空）。"
                     "建议回 outline 步骤 1.5 采集；硬写 = 纯通用生成，别假装有味道。")
    lines.append("")

    lines.append("### 2. 句间引力 —— 写每一句时唯一要持有的技法")
    lines.append("")
    lines.append("- **旧信息在前，新信息在后**：每句开头接住上句已出现的词/概念，句尾才抛新东西（given-new）")
    lines.append("- **顶真**：上句尾词可原样搬到下句开头（…传输比特。比特，那就是流量费）")
    lines.append("- **重点词落句尾**：每句最想强调的词放在句号前，别卡在句中")
    lines.append("- **段尾回看**：写完一段扫一眼——每句开头能否在上句结尾找到承接点？找不到 = 断点，移词或补半句")
    lines.append("")

    lines.append("### 3. 终审门 —— 凌驾一切量化指标")
    lines.append("")
    lines.append("- **读出声**：你会这样跟一个聪明朋友说话吗？不会 → 重写该句")
    lines.append("- **想读下一句**：读完第一句想读第二句吗？不想 → 治首句张力或句间承接，不是去刷指标")
    lines.append("- 写的时候只管把话顺着说完；下面各节的招式/禁区是参考，**伤语流时一律让位**")
    lines.append("")

    lines.append("### 4. 论断-证据契约 —— 干货密度的底线（🔴 2026-07-02 C8）")
    lines.append("")
    lines.append("- 每个**判断性 claim**（评价 / 趋势 / 对比 / 预测）必须配：具体数据 / 一手案例 / KOL 原话（标利益立场）/ 交叉验证，**四选一**。")
    lines.append("- **缺支撑就现场补搜**（AnySearch / Tavily / WebSearch）——搜索是 AI 相对人类作者的独有优势，别急着把论断软化或删掉；补搜 1-2 轮仍无才降强度或删。")
    lines.append("- 去 AI 味的本体是**内容精炼、干货充足、不绕弯子**：句式再像人、没干货也是 AI 文。每段自问「删掉它读者损失什么」，答不上来就删。")
    return "\n".join(lines)


def render_blacklist() -> str:
    """从 contracts._BLACKLIST_HARD 渲染人类可读的「写作禁区清单」。
    与写后 B-主门 verify_anti_ai_blacklist 同源——写前提示 + 写后检查闭环。
    """
    try:
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        from contracts import _BLACKLIST_HARD
    except Exception as e:
        return f"（无法加载 contracts._BLACKLIST_HARD：{e}）"
    lines = ["以下固定套话**写了会被排版阶段 B-主门硬拦**（exit 2），写作时直接绕开：", ""]
    for _pattern, label, fix in _BLACKLIST_HARD:
        lines.append(f"- ❌ {label} → ✅ {fix}")
    return "\n".join(lines)


def render_fact_sheet(cwd: Path) -> tuple[list[str], str | None]:
    """渲染『一·据、事实数据清单』节（🔴 2026-07-02 C9）。

    数据源 = cwd/素材/research/*.json（research fan-out 产物，schema:
    {"findings":[{"claim","support","confidence"}], "sources":[{"title","tier",...}]}）。
    正文引用数据以本清单为准；清单外新增数字须现场搜索核实。
    历史文章多无此产物——文件缺失时优雅降级（返回提示，不阻塞）。
    返回 (要 append 的行列表, 缺料提示或 None)。
    """
    import json
    research_dir = cwd / "素材" / "research"
    jsons = sorted(research_dir.glob("*.json")) if research_dir.exists() else []
    if not jsons:
        return [], ("无 素材/research/*.json 事实清单（research fan-out 未落盘或本篇未调研）——"
                    "若正文有数据/版本/价格类 claim，写作时须现场补搜核实（见 §〇 第 4 原则）")
    lines = ["## 一·据、事实数据清单（带信源，正文数据以此为准）", ""]
    lines.append("> 🔴 **正文引用的数据 / 版本 / 价格 / 时间以本清单为准**；清单**外**新增的数字须现场搜索核实，"
                 "`need_verify` 项不得写成确定语气（见 §〇 第 4 原则 论断-证据契约）。")
    lines.append("")
    total = 0
    for jf in jsons:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            lines.append(f"- ⚠️ 无法解析 {jf.name}：{e}")
            continue
        findings = data.get("findings") or []
        srcs = data.get("sources") or []
        src_map = "；".join(
            f"{s.get('title', '?')}（{s.get('tier', '?')}）"
            for s in srcs if isinstance(s, dict)
        )
        for f in findings:
            if not isinstance(f, dict):
                continue
            claim = str(f.get("claim", "")).strip()
            if not claim:
                continue
            conf = f.get("confidence", "?")
            support = str(f.get("support", "")).strip()
            flag = "⚠️ 待核实" if conf == "need_verify" else "✓"
            lines.append(f"- [{flag}] {claim} —— {support}")
            total += 1
        if src_map:
            lines.append(f"  - 信源：{src_map}")
    if total == 0:
        return [], "素材/research/*.json 存在但无有效 findings（结构异常）——正文数据须现场核实"
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines, None


def build_prep_context(cwd: Path) -> tuple[str, list]:
    """聚合 4 类料，返回 (_prep-context.md 全文, 缺失项列表)。"""
    meta = load_article_meta(cwd)
    style = str(meta.get("style", ""))
    author = resolve_author(style)
    missing = []

    parts = []
    parts.append("# _prep-context.md -- 本篇写作配方")
    parts.append("")
    parts.append("> 🟢 由 prep_writing.py 自动聚合生成。**写作时内化这一份即可**，")
    parts.append("> 不必再去翻 compact / vocab-pool / 金句库等散落源文件。")
    parts.append("")
    parts.append(f"- 文章：{meta.get('project') or meta.get('selected_title') or cwd.name}")
    parts.append(f"- 风格标签：{style or '（article-meta.yaml 未填 style）'}")
    parts.append(f"- 解析出的 author 路由：{author or '（未匹配到已知 author）'}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 0. 本篇三件最高原则（🔴 2026-06-10 P0-2：置顶，先于一切招式）
    parts.append(render_top_principles(meta))
    parts.append("")
    parts.append("---")
    parts.append("")

    # 1. compact
    parts.append("## 一、作者执行手册（compact）")
    parts.append("")
    parts.append("> 🟢 **写作时第一步**：翻到下文 §段落实例库 抄节奏，**不要先用 DNA/招式/句式公式生造句子**（那会写成营销号配方+知识分子腔的拼贴）。")
    parts.append("> 🟢 **compact 上半部（DNA/招式/句式公式）= 磨稿对照表**（🔴 2026-06-10 降级）：磨稿期回头打勾用，**不是写作期执行约束**——写作期只用 §〇 三原则 + 下文整篇范文 + §段落实例库。")
    parts.append("> 🟢 **写的时候只管把话顺着说完**（句间承接，见 §〇 三原则）。**初稿全文完成后**再对照 §朴实简洁的小动作 统一扫一遍——")
    parts.append("> 🔴 **禁止边写边逐段打钩**：那会让每句话的首要目标变成「过本段检查」而不是「接住上一句」，正是「句子各自合规、连起来生涩」的来源。")
    parts.append("")
    if author:
        cf = author_compact(author)
        if cf is not None:
            parts.append(cf.read_text(encoding="utf-8").strip())
        else:
            missing.append(f"compact 文件不存在：profile/corpus/authors/{author}.compact.md")
            parts.append(f"⚠️ 未找到 {author} 的风格手册（profile/corpus/authors/{author}.compact.md）")
    else:
        missing.append("article-meta.yaml 的 style 未能解析出已装的 author 手册")
        parts.append(f"⚠️ style 字段未匹配到 profile/corpus/authors/ 里的任何 author 手册"
                     f"（现有：{available_authors() or '无——请先自建手册，见 corpus/authors/README.md'}），本篇无 compact 路由。")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 1-声. 作者声纹样本（优先级在他人范文之上——他人范文管「顺」的底色，
    # 作者自己的语料管「是谁在说」）。无自备语料时这份 voice-samples.md 就是
    # 仓内原创的基础人味兜底。
    vc = corpus_dir() / "voice-samples.md"
    vc_text = vc.read_text(encoding="utf-8").strip() if vc.exists() else ""
    if len(vc_text) > 200:  # 有实质内容才注入（空壳/占位文件跳过）
        parts.append("## 一·声、作者声纹样本（谁在说话——优先级高于下文一切他人范文）")
        parts.append("")
        parts.append("> 🟢 这是作者本人的文字。**全文的「我」以这里的说话方式为准**；")
        parts.append("> 他人范文只管句子顺不顺，声音的归属听这里。")
        parts.append("")
        parts.append(vc_text[:6000])
        parts.append("")
        parts.append("---")
        parts.append("")

    # 1-样. 整篇金标范文（🔴 2026-06-10 P1-8：范文-规则配比反转）
    parts.append("## 一·样、整篇金标范文（写前通读，校准耳朵）")
    parts.append("")
    parts.append("> 🟢 **用法：写初稿前从头到尾通读一遍，让耳朵先校准到「人在说话」的频率。**")
    parts.append("> 这是一整篇真文章的完整语流——句子怎么接句子、段落怎么呼吸、哪里密哪里松，")
    parts.append("> 比任何规则描述都管用（AI 腔是分布偏置，规则压不动，剂量范文压得动）。")
    parts.append("> 🔴 **抄声音不抄内容**：范文内容与本篇无关，不许搬观点/句子/比喻进正文；")
    parts.append("> 读完合上，用它的「说话方式」写你自己的内容。")
    parts.append("")
    gold = select_gold_sample(author) if author else None
    if gold:
        gtitle, gtext = gold
        parts.append(f"### 《{gtitle}》（{author}，已机械清洗：破折号→--、去图链）")
        parts.append("")
        parts.append(gtext)
    else:
        missing.append(f"整篇金标范文未注入（profile/corpus/samples/{author or '?'}/ 不存在或无合适篇目——这是可选料，缺省不影响写作）")
        parts.append(f"⚠️ 未找到 {author or '（无路由）'} 的整篇范文（可选特性：把范文放进 profile/corpus/samples/{author or '<author>'}/ 即可启用）")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 1-α. 叠加路由 modifier (2026-05-27 双层加载机制)
    # article-meta.yaml 可填 modifier_style: <某作者手册名>（也支持 list）；
    # 命中已装 author 手册名的 modifier compact 在此处叠加进 _prep-context.md。
    modifiers = resolve_modifiers(meta)
    if modifiers:
        parts.append("## 一·α、叠加路由 modifier（跟主路由 compact 组合使用）")
        parts.append("")
        parts.append(
            "> 🟢 **modifier 用法**：主路由 compact 决定文章主调性（整篇底色），"
            "modifier 在主调性基础上叠加风格修饰（如小说式开场 / 教程类钩子）。"
            "**不要把 modifier 的招式当主路由用**——它们是局部染色，不是整篇底色。"
        )
        parts.append("")
        for m in modifiers:
            mf = author_compact(m)
            if mf is not None:
                parts.append(f"### Modifier · {m}")
                parts.append("")
                parts.append(mf.read_text(encoding="utf-8").strip())
                parts.append("")
            else:
                missing.append(f"modifier compact 文件不存在：profile/corpus/authors/{m}.compact.md")
                parts.append(f"⚠️ 未找到 modifier {m}（profile/corpus/authors/{m}.compact.md）")
                parts.append("")
        parts.append("---")
        parts.append("")

    # 1-bis. 反 AI 写作工具箱（A/B/C 三层 self-check 配方，跨作者通用）
    parts.append("## 一·补、反 AI 写作工具箱（跨作者通用 self-check）")
    parts.append("")
    parts.append("> 🟢 **本节是 self-check 的「第一层」**：先扫 A 层 3 条无条件铁律 → 段落属性触发 B 层 → 整篇定稿后看 C 层激活。")
    parts.append("> 与上面作者 compact 的「作者特有招式」**互不掩盖**，避免「同条规则跨作者砸 3 次」的虚假高分幻觉。")
    parts.append("")
    tf = SKILL_DIR / "references" / "反 AI 写作工具箱.md"
    if tf.exists():
        parts.append(tf.read_text(encoding="utf-8").strip())
    else:
        missing.append(f"反 AI 写作工具箱 不存在：{tf}")
        parts.append(f"⚠️ 未找到 {tf}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 1-规. 个性化写作规则（learn_edits 飞轮产物 playbook —— 路径经 profile_config
    # 解析：profile 配置时在 <profile>/flywheel/，未配置回退仓根空壳。复核 B-4：
    # 之前 writing.md 让模型读固定路径 $SKILL/playbook.md，飞轮迁 profile 后固定路径
    # 只剩空壳——改为在这里解析并注入，模型不再需要自己找文件）
    from profile_config import playbook_file
    pb = playbook_file()
    pb_text = pb.read_text(encoding="utf-8").strip() if pb.exists() else ""
    parts.append("## 一·规、个性化写作规则（learn_edits 飞轮产物）")
    parts.append("")
    # 判别「编译产物」vs「仓根空壳说明文」：空壳刻意演示了完整规则形态（含示例
    # confidence），内容形状分不开——用路径判别：飞轮解析到 profile（≠仓根）才是
    # 用户真产物。边缘：example-profile 用户直接在仓根攒规则会被标成「尚无沉淀」，
    # 但 README 本就引导先建 profile，接受这一边缘。
    if pb_text and pb.parent.resolve() != SKILL_DIR.resolve():
        parts.append("> 🟢 用法：`rules` 中 confidence >= 5.0 的**硬执行**、< 5.0 软参考；")
        parts.append("> `reference_preferences` 作 style-routes 检索的第二信号；")
        parts.append("> `noise_filter_rules` 在加载 author compact 前过滤训练语料污染。")
        parts.append("")
        parts.append(pb_text)
    else:
        parts.append("（playbook 尚无沉淀规则——直接用上文通用规则写作，不停等。攒法见 learn-edits.md）")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 1-据. 事实数据清单（🔴 2026-07-02 C9：research fan-out 产物注入，正文数据以此为准）
    fact_lines, fact_missing = render_fact_sheet(cwd)
    parts.extend(fact_lines)
    if fact_missing:
        missing.append(fact_missing)

    # （已移除原 §二 词汇温度池注入：配额表 + 替换规则是写作期最大的单块注意力
    #   占用之一，且配额化选词 = 新的公式化。黑名单兜底已由机器层接管
    #   （B-主门 verify_anti_ai_blacklist / B-软门 audit_style_signals）。）

    # 3. 金句库
    parts.append("## 二、金句库（声音锚点 + 锻造句式 + 本篇主题金句）")
    parts.append("")
    from profile_config import golden_lines_file
    jf = golden_lines_file()
    if jf.exists():
        jtext = jf.read_text(encoding="utf-8")
        anchor = extract_section(jtext, "写作声音锚点")
        forge = extract_section(jtext, "金句锻造句式")
        topic = match_topic(meta, jtext)
        if not topic:
            # 🔴 2026-06-20 D-1：把静默降级变可见信号——本篇标题/摘要/标签无主题明词，
            #   拿不到主题金句 section（只剩通用锚点+锻造句式），提醒可手填 topic_keywords 兜底。
            missing.append("本篇未匹配到主题金句 section（标题/摘要无主题明词，"
                           "可在 article-meta.yaml 手填 topic_keywords 命中兜底）")
        for blk in (anchor, topic, forge):
            if blk:
                parts.append(blk)
                parts.append("")
    else:
        missing.append(f"金句库不存在：{jf}（可选料，缺省不影响）")
        parts.append(f"⚠️ 未找到金句库：{jf}（可用 SANSHENG_WRITE_GOLDEN_LINES_FILE 指向现有真源）")
    parts.append("---")
    parts.append("")

    # 4. 风格 few-shot 示例（与 compact 配套，语感锚定）
    parts.append("## 三、风格 few-shot 示例（最佳段落语感锚）")
    parts.append("")
    sf = corpus_dir() / "style-examples.md"
    if not sf.exists():
        missing.append("风格示例库不存在：profile/corpus/style-examples.md（可选料，缺省不影响）")
        parts.append("⚠️ 未找到 profile/corpus/style-examples.md（可选：自建后此处按 author 注入 few-shot 段落）")
    elif not author:
        parts.append("（未解析出 author 路由，跳过 few-shot 示例。）")
    else:
        examples = extract_style_examples(sf.read_text(encoding="utf-8"), author)
        if examples:
            parts.append(examples)
        else:
            parts.append(f"（style-examples.md 暂无「{author}」路由的 few-shot 示例，"
                         "该路由以 compact 手册为准。）")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 5. AI 腔写作禁区（与 B-主门同源）
    parts.append("## 四、AI 腔写作禁区（与写后 B-主门同源）")
    parts.append("")
    parts.append(render_blacklist())
    parts.append("")

    return "\n".join(parts), missing


def main():
    parser = argparse.ArgumentParser(description="写作前聚合参考料 → _prep-context.md")
    parser.add_argument("--dir", "-d", default=".", help="文章工作目录（默认当前目录）")
    args = parser.parse_args()

    cwd = Path(args.dir).resolve()
    if not cwd.is_dir():
        print(f"ERROR: 目录不存在：{cwd}", file=sys.stderr)
        sys.exit(1)

    content, missing = build_prep_context(cwd)
    out = cwd / "_prep-context.md"
    out.write_text(content, encoding="utf-8")

    print(f"✅ 已生成 {out}（{len(content)} 字符）")
    if missing:
        print("⚠️ 部分料缺失（不阻塞，但建议补齐）：")
        for m in missing:
            print(f"   • {m}")
    print()
    print("下一步：写作时内化 _prep-context.md。写完跑排版，B-主门会断言此文件存在。")


if __name__ == "__main__":
    main()
