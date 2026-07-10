#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
learn_edits.py — 写作闭环学习飞轮
========================================

用途：
1. diff 模式：对比定稿前后的差异，输出给 Agent 进行 Pattern 分析；**并自动灌库声纹**
   ——把作者实质改写 / 新写的散文段提进 profile/corpus/voice-samples.md。
2. build 模式：汇总 lessons.yaml 中的历史记录，生成带置信度(confidence)的 playbook.md。
3. add-paragraph 模式：手动精选一段作者亲笔改稿追加进 voice-samples.md（自动通道的补充）。

声纹达 threshold=3 后，prep_writing.py §一·声 注入写作上下文（决定「是谁在说话」）。

用法:
  python learn_edits.py diff --draft <旧文件> --final <新文件>           # 默认自动灌库
  python learn_edits.py diff --draft <旧> --final <新> --no-promote-voice  # 仅 diff 不灌库
  python learn_edits.py build
  python learn_edits.py add-paragraph --text "<作者亲笔段落>"
  python learn_edits.py add-paragraph --file <段落文件路径>
"""

import argparse
import datetime
import difflib
import sys
import os
from pathlib import Path

# v5: Windows GBK stdout 默认无法 print emoji，强制 UTF-8 避免崩溃
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import yaml
except ImportError:
    print("❌ 缺少 PyYAML 库，请执行: pip install pyyaml")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
LESSONS_FILE = SKILL_DIR / "lessons.yaml"
PLAYBOOK_FILE = SKILL_DIR / "playbook.md"
sys.path.insert(0, str(SCRIPT_DIR))
from profile_config import corpus_dir  # noqa: E402
# 声纹库落盘走 profile 覆盖层（未配置 SANSHENG_WRITE_PROFILE_DIR 时回退
# profile.example/corpus/voice-samples.md）。prep_writing.py §一·声 读同一个文件，
# 确保写=读同一处。
VOICE_CORPUS_FILE = corpus_dir() / "voice-samples.md"

_VOICE_HEADER = (
    "# 作者声纹样本库\n"
    "\n"
    "> 作者亲笔/亲改的段落集合。prep_writing.py 检测到内容（>200 字）即注入写作"
    "上下文 §一·声，优先级高于他人范文——决定「是谁在说话」。\n"
    "> 收录标准：作者亲笔改动多、AI 代笔痕迹轻；代笔痕迹重的不收（会教坏声纹）。\n"
    "> 灌库方式：① 飞轮 `diff` 自动灌库（挑出被实质改写/新写的散文段）；"
    "② 手动 `add-paragraph` 精选补充。\n"
)

# ── 自动灌库：从作者改稿里提取声音样本 ─────────────────────
# 设计：作者实质改写过 / 新写的散文段 = 已是他的声音（AI 没改的高相似段被上界排除，
#       天然规避「教坏声纹」）。纯函数挑选与文件写入分离，便于回归测试。
_VOICE_PROMOTE_HI = 0.92   # 与某 draft 段相似度 ≥ 此值 = 基本没改（AI 原段）→ 不收
_VOICE_MIN_CHARS = 50      # 太短的段不够承载声音特征（按中文校准：~50 字≈完整一两句，更短多是碎片/口号）


def _split_paragraphs(text):
    """按空行切段，去首尾空白，返回非空段列表。"""
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        b = block.strip()
        if b:
            out.append(b)
    return out


def _is_voice_sample(para):
    """是否够格当声纹样本：实质散文，排除 标题/列表/表格/代码/引用/图片标记。"""
    if len(para) < _VOICE_MIN_CHARS:
        return False
    head = para.lstrip()
    if head[:1] in ("#", "-", "*", ">", "|", "`") or head.startswith("!["):
        return False
    lines = [l for l in para.split("\n") if l.strip()]
    listy = sum(
        1 for l in lines
        if l.lstrip()[:2] in ("- ", "* ")
        or (l.lstrip()[:1].isdigit() and ". " in l.lstrip()[:4])
    )
    if lines and listy / len(lines) > 0.5:   # 过半是列表行 → 当列表，不当散文
        return False
    return True


def _select_voice_candidates(draft_text, final_text, hi=_VOICE_PROMOTE_HI):
    """纯函数：从 draft→final 挑出作者实质改写 / 新写的散文段（声纹候选）。
    对每个 final 散文段，取它与所有 draft 段的最高相似度 best：
      best ≥ hi → 基本没动（AI 原段，作者没改）→ 不收，避免教坏声纹；
      best < hi → 改写过 / 全新（draft 找不到近似）→ 收（final 已是作者的声音）。"""
    draft_paras = _split_paragraphs(draft_text)
    out = []
    for fp in _split_paragraphs(final_text):
        if not _is_voice_sample(fp):
            continue
        best = 0.0
        for dp in draft_paras:
            r = difflib.SequenceMatcher(None, dp, fp).ratio()
            if r > best:
                best = r
                if best >= hi:
                    break
        if best < hi:
            out.append(fp)
    return out


def _append_voice_paragraphs(paras, source_label, today):
    """把若干段追加进 voice-samples.md（去重 vs 现有内容），bump 计数，返回实际追加段数。"""
    paras = [p for p in paras if p and p.strip()]
    if not paras:
        return 0
    if not VOICE_CORPUS_FILE.exists():
        VOICE_CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VOICE_CORPUS_FILE.write_text(_VOICE_HEADER, encoding="utf-8")
        print(f"📄 已新建声纹库文件: {VOICE_CORPUS_FILE}")
    existing_paras = _split_paragraphs(VOICE_CORPUS_FILE.read_text(encoding="utf-8"))
    added = 0
    with open(VOICE_CORPUS_FILE, "a", encoding="utf-8") as f:
        for para in paras:
            # 去重：与现有任一段高度相似（>0.9）则跳过，避免重复灌
            if any(difflib.SequenceMatcher(None, ep, para).ratio() > 0.9 for ep in existing_paras):
                continue
            f.write(f"\n## {today} · {source_label}\n\n{para}\n")
            existing_paras.append(para)
            added += 1
    if added:
        print(f"✅ 已追加 {added} 段作者声音样本到 {VOICE_CORPUS_FILE}")
        _bump_voice_corpus_index(today, delta=added)
    return added


def diff_files(draft_path, final_path, promote_voice=True):
    p_draft = Path(draft_path)
    p_final = Path(final_path)

    if not p_draft.exists():
        print(f"❌ 找不到草稿文件: {draft_path}")
        return
    if not p_final.exists():
        print(f"❌ 找不到定稿文件: {final_path}")
        return
    
    with open(p_draft, 'r', encoding='utf-8') as f:
        draft_lines = f.readlines()
    with open(p_final, 'r', encoding='utf-8') as f:
        final_lines = f.readlines()

    diff = difflib.unified_diff(
        draft_lines, final_lines,
        fromfile='Draft', tofile='Final',
        n=1
    )
    
    diff_output = "".join(diff)
    if not diff_output.strip():
        print("✅ 两个文件没有差异。")
        return
        
    print("=== 📝 DIFF 分析结果 ===")
    print(diff_output)
    print("\n=== 🤖 给 Agent 的操作指令 ===")
    print("1. 阅读上述 Diff，理解用户修改的意图（删减、替换、句式调整、结构变动）。")
    print(f"2. 将有价值的修改模式追加到 {LESSONS_FILE}。")
    print("   每个 pattern 包括：key, "
          "type(word_sub/para_delete/para_add/structure/tone/expression/discourse/reference_preference), "
          "rule(祈使句), description。")
    print("   🔴 归档时显式区分层级：词句级(word_sub/expression/tone) vs 篇章级(discourse/structure)。")
    print("   实证：playbook 词句级规则被执行了但病根在篇章层——蒸馏时优先问")
    print("   「这个 diff 改的是一句话，还是文章谈论自己/复述自己/打金句拍子的方式？」")
    print("   注：如果是已有的偏好，请使用相同的 key。")
    print("3. 追加完成后，执行 `python scripts/learn_edits.py build` 更新 Playbook。")

    # 自动灌库：把作者实质改写 / 新写的散文段提进声纹库。
    # 与上面「Claude 蒸馏词句/篇章规则」并行——规则进 lessons.yaml，声音样本进 voice-samples.md。
    if promote_voice:
        source = Path(final_path).parent.name or "diff"
        cands = _select_voice_candidates("".join(draft_lines), "".join(final_lines))
        if cands:
            print("\n=== 🎙️ 自动灌库（声纹）===")
            _append_voice_paragraphs(cands, source, datetime.date.today().isoformat())
        else:
            print("\nℹ️ 自动灌库：本次未发现够格的作者声音样本（实质改写的散文段）。")

def build_playbook():
    if not LESSONS_FILE.exists():
        print(f"⚠️ 找不到 {LESSONS_FILE}，新建空文件...")
        LESSONS_FILE.write_text("lessons: []\n", encoding="utf-8")
        
    with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
        
    lessons = data.get("lessons", [])
    if not lessons:
        print("⏭️ lessons.yaml 为空，无需更新。")
        # 即使为空也写入空的 playbook
        _write_playbook([])
        return

    # 按 key 聚合规则
    rules_dict = {}
    
    for lesson in lessons:
        date = lesson.get("date", "2000-01-01")
        patterns = lesson.get("patterns", [])
        for p in patterns:
            key = p.get("key")
            if not key: continue
            
            if key not in rules_dict:
                rules_dict[key] = {
                    "key": key,
                    "type": p.get("type", "expression"),
                    "rule": p.get("rule", ""),
                    "occurrences": 0,
                    "last_seen": date
                }
            # 更新为最新的规则表达
            rules_dict[key]["rule"] = p.get("rule", rules_dict[key]["rule"])
            rules_dict[key]["type"] = p.get("type", rules_dict[key]["type"])
            # 更新最后可见时间
            if date > rules_dict[key]["last_seen"]:
                rules_dict[key]["last_seen"] = date
            
            rules_dict[key]["occurrences"] += 1
            # pinned = 作者置顶的规则（lessons.yaml pattern 带 pinned: true）。
            # 置顶规则不走飞轮慢速积分——出现 1 次就该硬执行，否则会被降权成软参考
            # （实证：置顶规则当天 confidence 2.0 < 5.0 硬执行阈值，形同没置顶）。
            if p.get("pinned"):
                rules_dict[key]["pinned"] = True

    # 计算 confidence 和过滤
    final_rules = []
    for key, info in rules_dict.items():
        occ = info["occurrences"]
        # 简单算法：每次出现 +2.0 分；pinned（作者置顶）锚到硬执行档（≥5.0）
        confidence = float(occ * 2.0)
        if info.get("pinned"):
            confidence = max(confidence, 5.0)
        info["confidence"] = confidence
        
        # 只有 confidence >= 2.0 (即至少出现1次，因为1次就2.0) 才进入 Playbook
        if confidence >= 2.0:
            final_rules.append(info)

    # 按 confidence 降序
    final_rules.sort(key=lambda x: x["confidence"], reverse=True)
    
    _write_playbook(final_rules)

def _write_playbook(rules):
    # v5: merge 模式 — 保留 reference_preferences / voice_corpus_index / noise_filter_rules
    # 防止覆盖作者手动维护的 noise-filter 规则和 v5 schema 新增字段
    existing = {}
    if PLAYBOOK_FILE.exists():
        try:
            text = PLAYBOOK_FILE.read_text(encoding="utf-8")
            # 剥掉 markdown 代码块围栏
            yaml_body = text.replace("```yaml", "").replace("```", "").strip()
            existing = yaml.safe_load(yaml_body) or {}
        except Exception as e:
            print(f"⚠️ 解析现有 playbook 失败（将以默认 v5 schema 重建）：{e}")
            existing = {}

    playbook_content = {
        "rules": rules,
        "reference_preferences": existing.get("reference_preferences", []),
        "voice_corpus_index": existing.get("voice_corpus_index", {
            "count": 0,
            # 阈值 30→3：与 playbook.md/SKILL.md/header 注释统一口径
            #（原 30 等于永不启动；作者挑 3-5 篇亲笔改稿即启动声纹）
            "threshold": 3,
            "corpus_path": "profile/corpus/voice-samples.md",
            "last_updated": "",
        }),
        "noise_filter_rules": existing.get("noise_filter_rules", []),
    }
    yaml_str = yaml.dump(playbook_content, allow_unicode=True, sort_keys=False, default_flow_style=False)

    header = (
        "```yaml\n"
        "# 写作 Playbook — 从用户编辑中学习的写作规则\n"
        "# v5: rules / reference_preferences / voice_corpus_index 由 learn_edits.py merge 模式自动维护\n"
        "#     noise_filter_rules 由作者手动维护（发现的训练语料污染规则）\n"
        "# \n"
        "# 【使用规范】在写作 Step 4 时读取：\n"
        "# - rules confidence >= 5.0：硬性约束\n"
        "# - rules confidence <  5.0：软性参考\n"
        "# - reference_preferences：style-routes 检索的第二信号\n"
        "# - voice_corpus_index：达 threshold（=3，作者挑 3-5 篇亲笔改稿即启动）后注入声纹\n"
        "# - noise_filter_rules：author compact 加载前过滤训练语料\n\n"
    )

    with open(PLAYBOOK_FILE, 'w', encoding='utf-8') as f:
        f.write(header + yaml_str + "```\n")

    print(f"✅ playbook.md 更新完成，共聚合生成 {len(rules)} 条规则（v5 字段已保留）。")


def _bump_voice_corpus_index(today, delta=1):
    """声纹库追加 delta 段后：voice_corpus_index.count += delta、last_updated 写为 today。
    复用 _write_playbook 的 existing 解析逻辑（merge 模式，不动 rules / 其他 v5 字段）。
    playbook 不存在时不强建——声纹追加不该顺带初始化飞轮，交给 build。"""
    if not PLAYBOOK_FILE.exists():
        print("⚠️ playbook.md 不存在，跳过 voice_corpus_index 更新（请先跑一次 build 初始化）。")
        return
    try:
        text = PLAYBOOK_FILE.read_text(encoding="utf-8")
        yaml_body = text.replace("```yaml", "").replace("```", "").strip()
        existing = yaml.safe_load(yaml_body) or {}
    except Exception as e:
        print(f"⚠️ 解析现有 playbook 失败，跳过 voice_corpus_index 更新：{e}")
        return

    # 取现有 rules（已计算好的成品）原样回写，避免重新 build 改动飞轮积分
    rules = existing.get("rules", []) or []
    vci = existing.get("voice_corpus_index", {
        "count": 0,
        "threshold": 3,
        "corpus_path": "profile/corpus/voice-samples.md",
        "last_updated": "",
    })
    vci["count"] = int(vci.get("count", 0)) + delta
    vci["last_updated"] = today
    # 把更新后的 index 暂存回 existing，再借 _write_playbook 落盘其余字段
    # （_write_playbook 自己会从 existing 读 voice_corpus_index，这里直接改文件里的值）
    existing["voice_corpus_index"] = vci

    playbook_content = {
        "rules": rules,
        "reference_preferences": existing.get("reference_preferences", []),
        "voice_corpus_index": vci,
        "noise_filter_rules": existing.get("noise_filter_rules", []),
    }
    yaml_str = yaml.dump(playbook_content, allow_unicode=True, sort_keys=False, default_flow_style=False)
    header = (
        "```yaml\n"
        "# 写作 Playbook — 从用户编辑中学习的写作规则\n"
        "# v5: rules / reference_preferences / voice_corpus_index 由 learn_edits.py merge 模式自动维护\n"
        "#     noise_filter_rules 由作者手动维护（发现的训练语料污染规则）\n"
        "# \n"
        "# 【使用规范】在写作 Step 4 时读取：\n"
        "# - rules confidence >= 5.0：硬性约束\n"
        "# - rules confidence <  5.0：软性参考\n"
        "# - reference_preferences：style-routes 检索的第二信号\n"
        "# - voice_corpus_index：达 threshold（=3，作者挑 3-5 篇亲笔改稿即启动）后注入声纹\n"
        "# - noise_filter_rules：author compact 加载前过滤训练语料\n\n"
    )
    with open(PLAYBOOK_FILE, 'w', encoding='utf-8') as f:
        f.write(header + yaml_str + "```\n")
    print(f"✅ voice_corpus_index 已更新：count={vci['count']}（threshold={vci.get('threshold', 3)}），"
          f"last_updated={today}。")


def add_voice_paragraph(text=None, file_path=None):
    """add-paragraph 子命令：把一段作者亲笔改稿文本手动追加进 voice-samples.md
    （精选补充通道；自动通道见 diff 模式的「自动灌库」）。复用 _append_voice_paragraphs：
    文件不存在则创建、去重、count += 实际追加段数、last_updated 更新写回 playbook。"""
    # 取段落正文：--file 优先，其次 --text
    if file_path:
        p = Path(file_path)
        if not p.exists():
            print(f"❌ 找不到段落文件: {file_path}")
            return
        body = p.read_text(encoding="utf-8").strip()
    else:
        body = (text or "").strip()

    if not body:
        print("❌ 段落内容为空（请用 --text \"...\" 或 --file <路径> 提供作者亲笔改稿文本）。")
        return

    today = datetime.date.today().isoformat()
    added = _append_voice_paragraphs([body], "作者亲笔段落", today)
    if added == 0:
        print("ℹ️ 该段与现有声纹库高度重复（>0.9），未重复追加。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="写作闭环学习飞轮")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # diff
    diff_parser = subparsers.add_parser("diff", help="比对草稿和定稿（含自动灌库声纹）")
    diff_parser.add_argument("--draft", required=True, help="修改前的草稿文件")
    diff_parser.add_argument("--final", required=True, help="修改后的定稿文件")
    diff_parser.add_argument("--no-promote-voice", dest="promote_voice", action="store_false",
                             help="关闭自动灌库（默认开：把作者实质改写/新写的散文段提进声纹库）")
    
    # build
    build_parser = subparsers.add_parser("build", help="从 lessons.yaml 重新编译 playbook.md")

    # add-paragraph：把一段作者亲笔改稿追加进声纹库，并 +1 计数（手动激活特性，不自动灌库）
    ap_parser = subparsers.add_parser(
        "add-paragraph",
        help="追加一段作者亲笔改稿到 voice-samples.md（达 threshold=3 后 prep 注入声纹）",
    )
    ap_group = ap_parser.add_mutually_exclusive_group(required=True)
    ap_group.add_argument("--text", help="直接传入段落正文（注意 shell 引号转义）")
    ap_group.add_argument("--file", help="从文件读取段落正文（整文件内容作为一段）")

    args = parser.parse_args()

    if args.command == "diff":
        diff_files(args.draft, args.final, promote_voice=args.promote_voice)
    elif args.command == "build":
        build_playbook()
    elif args.command == "add-paragraph":
        add_voice_paragraph(text=args.text, file_path=args.file)
