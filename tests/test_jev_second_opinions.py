# -*- coding: utf-8 -*-
"""Jev 第二意见四处接入（2026-09-22）：阈值边界反例、shadow 不改业务结果、enforce 才用、fail-open、不许直连。

全部离线：Jev 客户端用假对象替换，不打网络。真客户端只用来验「site 已登记 + 台账一行带 baseline/jev」。
接入层 `_ops/jev/` 不存在（公开仓 CI）时整个文件跳过——那种环境下四处调用点本来就走 import 失败即回退。
"""
import json
import sys
import time
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
REPO_JEV = SKILL.parent.parent / "_ops" / "jev"
sys.path.insert(0, str(SKILL / "scripts"))

if not (REPO_JEV / "client.py").is_file():  # pragma: no cover
    pytest.skip("接入层 _ops/jev 不存在，四处调用点走 import 失败即回退", allow_module_level=True)
sys.path.insert(0, str(REPO_JEV))
import client as jc  # noqa: E402
import contracts  # noqa: E402
import distribute  # noqa: E402
import evidence  # noqa: E402
from scripts import learn_edits as L  # noqa: E402

from tests.test_distribute import (  # noqa: E402,F401  复用分发层 fixture
    _write_images, _write_social, all_enabled, article,
)

SITES = {
    "anti_ai": "write.qc.anti_ai_second_opinion",
    "voice": "write.learn.voice_sample",
    "factcheck": "write.factcheck.adjudicate",
    "xhs": "write.distribute.xhs_risk",
}


class FakeJev:
    """假客户端：answers 由 scorer(state) 决定；记录 ask/log 调用。"""

    def __init__(self, scorer, mode="shadow", ok=True, raise_on_ask=False, delay=0.0):
        self.scorer, self.mode, self.ok = scorer, mode, ok
        self.raise_on_ask, self.delay = raise_on_ask, delay
        self.asks, self.rows = [], []

    enabled = True

    @property
    def enforce(self):
        return self.mode == "enforce"

    def ask(self, *, state, questions, meta=None, log=True, **_):
        self.asks.append({"state": state, "meta": meta})
        if self.raise_on_ask:
            raise RuntimeError("boom")
        if self.delay:
            time.sleep(self.delay)
        if not self.ok:
            return jc.JevResult(ok=False, mode=self.mode, error="URLError: down")
        return jc.JevResult(ok=True, mode=self.mode, answers=self.scorer(state), input_tokens=40)

    def log(self, r, meta=None):
        self.rows.append(meta or {})


# ===== 阈值边界（单一真源函数 + 反例） =====

@pytest.mark.parametrize("fn,val,expected", [
    (contracts.jev_ai_tone_is_hit, 0.50, True), (contracts.jev_ai_tone_is_hit, 0.49, False),
    (contracts.jev_ai_tone_is_hit, None, False),
    (L._jev_voice_is_rewrite, 0.50, True), (L._jev_voice_is_rewrite, 0.499, False),
    (L._jev_voice_is_rewrite, None, False),
    (distribute.xhs_divert_is_hit, 0.5, True), (distribute.xhs_divert_is_hit, 0.4999, False),
    (distribute.xhs_divert_is_hit, None, False),
])
def test_thresholds_boundaries(fn, val, expected):
    assert fn(val) is expected


# ===== 1. contracts.verify_anti_ai_blacklist：只报不拦 =====

AI_PARA = "在这个人工智能飞速发展的时代，我们每个人都应该拥抱变化，让我们一起迎接美好的未来吧，这是一个全新的篇章。"
HUMAN_PARA = "上周三早上七点十分，我在地铁十号线的车厢里数了数，十二个人里有九个在刷短视频，剩下三个在睡觉。"
ARTICLE = f"# 标题\n\n{AI_PARA}\n\n{HUMAN_PARA}\n\n- 列表项不问 Jev，够长够长够长够长够长够长够长够长够长够长\n"


def _ai_scorer(state):
    p = state.get("paragraph", "")
    return {"ai_tone": {"noul": 0.9 if "拥抱变化" in p or "地铁" in p else 0.1}}


def test_anti_ai_paragraph_split_skips_headings_lists_and_short():
    paras = contracts.jev_ai_tone_paragraphs(contracts._strip_for_scan(ARTICLE))
    assert [p[:6] for _, p in paras] == [AI_PARA[:6], HUMAN_PARA[:6]]


def test_anti_ai_skips_endmatter_templates():
    raw = f"{HUMAN_PARA}\n\n<!-- SANSHENG-DEEP-READ -->\n\nDEEP READ\n继续往下读\n这篇讲的是一辆车怎么改写账本，更多请看示例站点。\n"
    paras = contracts.jev_ai_tone_paragraphs(contracts._strip_for_scan(contracts._cut_endmatter(raw)))
    assert [p[:4] for _, p in paras] == [HUMAN_PARA[:4]]
    assert contracts._cut_endmatter("无标记全文") == "无标记全文"


def test_anti_ai_shadow_leaves_regex_verdict_untouched(tmp_path, monkeypatch):
    md = tmp_path / "定稿.md"
    md.write_text(ARTICLE, encoding="utf-8")
    monkeypatch.setattr(contracts, "_jev_client", lambda site: None)
    off = contracts.verify_anti_ai_blacklist(str(md))
    fake = FakeJev(_ai_scorer, mode="shadow")
    monkeypatch.setattr(contracts, "_jev_client", lambda site: fake)
    shadow = contracts.verify_anti_ai_blacklist(str(md))
    # 正则结论一个字节不变
    for k in ("verdict", "errors", "warnings", "hard_hits", "soft_hits"):
        assert shadow[k] == off[k], k
    assert off["verdict"] == "fail" and off["jev"]["mode"] == "off"
    j = shadow["jev"]
    assert j["mode"] == "shadow" and j["scored"] == 2 and j["errors"] == 0
    assert j["baseline_hits"] == 1 and j["jev_hits"] == 2 and j["agree"] == 1
    assert [h["excerpt"][:4] for h in j["new_hits"]] == [HUMAN_PARA[:4]]  # Jev 命中而正则未命中
    # 台账 meta 带 baseline 与 jev 两个决策
    by_excerpt = {r["excerpt"][:4]: r for r in fake.rows}
    assert by_excerpt[AI_PARA[:4]]["baseline"] == "hit" and by_excerpt[AI_PARA[:4]]["jev"] == "hit"
    assert by_excerpt[HUMAN_PARA[:4]]["baseline"] == "clean" and by_excerpt[HUMAN_PARA[:4]]["jev"] == "hit"


def test_anti_ai_enforce_only_appends_warnings_never_blocks(tmp_path, monkeypatch):
    md = tmp_path / "定稿.md"
    md.write_text(f"# 标题\n\n{HUMAN_PARA}\n", encoding="utf-8")
    monkeypatch.setattr(contracts, "_jev_client", lambda site: FakeJev(_ai_scorer, mode="enforce"))
    r = contracts.verify_anti_ai_blacklist(str(md))
    assert r["verdict"] == "ok" and r["errors"] == [] and r["hard_hits"] == 0
    assert r["soft_hits"] == 0                      # 只数正则
    assert len(r["warnings"]) == 1 and "Jev 第二意见（只报不拦）" in r["warnings"][0]


@pytest.mark.parametrize("fake_kwargs", [
    {"ok": False},                # 接口返回失败
    {"raise_on_ask": True},       # 客户端抛异常
])
def test_anti_ai_fail_open(tmp_path, monkeypatch, fake_kwargs):
    md = tmp_path / "定稿.md"
    md.write_text(ARTICLE, encoding="utf-8")
    monkeypatch.setattr(contracts, "_jev_client", lambda site: None)
    off = contracts.verify_anti_ai_blacklist(str(md))
    monkeypatch.setattr(contracts, "_jev_client", lambda site: FakeJev(_ai_scorer, **fake_kwargs))
    r = contracts.verify_anti_ai_blacklist(str(md))
    assert r["verdict"] == "fail" and (r["hard_hits"], r["soft_hits"], r["errors"]) == (
        off["hard_hits"], off["soft_hits"], off["errors"])
    assert r["jev"]["new_hits"] == [] and r["jev"]["scored"] == 0


def test_anti_ai_deadline_is_hard(tmp_path, monkeypatch):
    md = tmp_path / "定稿.md"
    md.write_text("\n\n".join([HUMAN_PARA + str(i) for i in range(6)]), encoding="utf-8")
    monkeypatch.setenv("SANSHENG_WRITE_JEV_DEADLINE", "0.3")
    monkeypatch.setattr(contracts, "_jev_client", lambda site: FakeJev(_ai_scorer, delay=2.0))
    t0 = time.time()
    r = contracts.verify_anti_ai_blacklist(str(md))
    assert r["verdict"] == "ok" and r["jev"]["scored"] == 0 and r["jev"]["errors"] == 6


def test_anti_ai_client_missing_means_mode_off(tmp_path, monkeypatch):
    """接入层缺失 / mode=off / 无 key：JevClient 拿不到 → 'jev'.mode=off，其余与从前一致。"""
    md = tmp_path / "定稿.md"
    md.write_text(ARTICLE, encoding="utf-8")
    monkeypatch.setenv("JEV_ENABLED", "0")
    r = contracts.verify_anti_ai_blacklist(str(md))
    assert r["jev"]["mode"] == "off" and r["verdict"] == "fail"


# ===== 2. learn_edits._select_voice_candidates：shadow 不改入选，enforce 才用 =====

DRAFT_P = "这是一段会被作者大改的话，原本写得很书面很套路，充满了潜移默化和从根本上这类副词补丁，读起来像机器写的。"
TYPO_P = "这是一段会被作者大改的话，原本写得很书面很套路，充满了潜移默化和从根本上这类副词补丁，读起来像机器写的！"
REWRITE_P = "这段我重写了：别整那些虚的，就是机器现在能干活了，你昨天还在手搓的事今天它十分钟给你交差，差距就这么实在。"
NEW_P = "我后来又补了一整段全新的话，纯粹是我自己想说的——技术这东西，不落到你具体某天省下的两小时上，吹得再高也是别人的故事。"


def _voice_scorer(state):
    f = state["final"]
    # Jev：只改标点的不算实质改写；重写 / 全新算
    return {"substantive_rewrite": {"noul": 0.05 if f == TYPO_P else 0.95}}


def test_voice_shadow_keeps_difflib_selection(monkeypatch):
    draft = f"{DRAFT_P}\n\n{DRAFT_P}"
    final = f"{TYPO_P}\n\n{REWRITE_P}\n\n{NEW_P}"
    monkeypatch.setattr(L, "_jev_voice_client", lambda: None)
    base = L._select_voice_candidates(draft, final)
    fake = FakeJev(_voice_scorer, mode="shadow")
    monkeypatch.setattr(L, "_jev_voice_client", lambda: fake)
    assert L._select_voice_candidates(draft, final) == base
    assert base == [REWRITE_P, NEW_P]  # difflib：只改标点的相似度 ≥0.92 → 不收
    assert len(fake.rows) == 3
    rows = {r["excerpt"][:6]: r for r in fake.rows}
    assert rows[TYPO_P[:6]]["baseline"] == "skip" and rows[TYPO_P[:6]]["jev"] == "skip"
    assert rows[REWRITE_P[:6]]["baseline"] == "select" and rows[REWRITE_P[:6]]["jev"] == "select"
    assert "difflib" in rows[NEW_P[:6]]


def test_voice_enforce_uses_jev_and_falls_back_per_item(monkeypatch):
    draft = f"{DRAFT_P}"
    # 反例：difflib 会把「只改了几个字但相似度 0.85」的段当实质改写收进去；Jev 判 skip 才能拦住
    near = "这是一段会被作者改动的话，原先写得偏书面偏套路，满是潜移默化、从根本上这类副词补丁，读来像机器出品。"  # 与 draft 相似度 0.82
    final = f"{near}\n\n{NEW_P}"
    monkeypatch.setattr(L, "_jev_voice_client", lambda: None)
    assert L._select_voice_candidates(draft, final) == [near, NEW_P]

    def scorer(state):
        return {"substantive_rewrite": {"noul": 0.2 if state["final"] == near else 0.9}}
    monkeypatch.setattr(L, "_jev_voice_client", lambda: FakeJev(scorer, mode="enforce"))
    assert L._select_voice_candidates(draft, final) == [NEW_P]
    # enforce 下 Jev 失败 → 该条回退 difflib
    monkeypatch.setattr(L, "_jev_voice_client", lambda: FakeJev(scorer, mode="enforce", ok=False))
    assert L._select_voice_candidates(draft, final) == [near, NEW_P]


def test_voice_fail_open_on_exception(monkeypatch):
    monkeypatch.setattr(L, "_jev_voice_client", lambda: FakeJev(_voice_scorer, raise_on_ask=True))
    assert L._select_voice_candidates(DRAFT_P, f"{TYPO_P}\n\n{NEW_P}") == [NEW_P]


# ===== 3. evidence：事实裁决四选一对照 =====

FACT_MD = """# 事实复核清单

复核模型：x
条目数：5
结论：1 条待改

## 逐条
- [✓] 上下文 50 万，知识截止 2026 年 5 月。文档表写 context 500,000，knowledge cutoff May 2026。
- [△] 版本号少了「.2」 -- 模型页写的现行名称是 v4.3.2，正文写成 v4.3。
- [✗] 训练那句把对象写错了。发布页原文是 Grok Bot harness，正文写成 Grok Build。
- [⚠️ 待核实] 使用者帖的浏览次数 -- 搜不到独立信源。
- [L] 这行是来源清单，不是裁决 -- 应归 unknown
1. [✓] 编号列表也要认。 [证据](https://example.invalid/x)
"""


def test_parse_fact_check_items_marks_and_split():
    items = evidence.parse_fact_check_items(FACT_MD)
    assert [i["mark"] for i in items] == ["correct", "attributed", "wrong", "need_verify", "unknown", "correct"]
    assert items[0]["claim"] == "上下文 50 万，知识截止 2026 年 5 月。" and items[0]["evidence"].startswith("文档表")
    assert items[1]["claim"] == "版本号少了「.2」" and items[1]["evidence"].startswith("模型页")
    assert items[5]["evidence"].startswith("[证据]")


def test_parse_fact_check_items_warns_on_nonconforming_but_never_raises():
    """B4：不合格条目只报 warning；合格条目 warning=None。degraded 只标没用 ` -- ` 分写的。"""
    items = evidence.parse_fact_check_items(FACT_MD)
    assert items[1]["warning"] is None and items[1]["degraded"] is None            # 标准写法
    assert items[3]["warning"] is None                                              # ⚠️ 待核实 + ` -- ` 也合格
    assert items[0]["degraded"] == "claim_evidence_unsplit" and "` -- `" in items[0]["warning"]
    assert items[2]["degraded"] == "claim_evidence_unsplit"
    assert "标记 [L]" in items[4]["warning"]
    assert items[5]["degraded"] == "claim_evidence_unsplit"
    warns = evidence.fact_check_format_warnings(FACT_MD)
    assert len(warns) == 4 and warns[0].startswith("第 1 条：")
    # 反例：全部合格 → 空列表；证据为空也要报
    good = "- [✓] A -- 对上官网\n- [△] B -- 当事方自述\n- [✗] C -- 实际应为 D\n- [⚠️ 待核实] E -- 搜不到\n"
    assert evidence.fact_check_format_warnings(good) == []
    assert "证据为空" in evidence.fact_check_format_warnings("- [✓] 只有 claim -- \n")[0]


def test_factcheck_degraded_items_carry_marker_into_ledger(tmp_path):
    """A3：条目没按 ` -- ` 分写 → 台账 meta 带 degraded；合格条目不带。"""
    (tmp_path / "_fact-check.md").write_text(FACT_MD, encoding="utf-8")
    fake = FakeJev(_fact_scorer, mode="shadow")
    evidence.jev_factcheck_second_opinion(tmp_path, jev=fake)
    by_claim = {r["claim"]: r for r in fake.rows}
    assert by_claim["上下文 50 万，知识截止 2026 年 5 月。"]["degraded"] == "claim_evidence_unsplit"
    assert "degraded" not in by_claim["版本号少了「.2」"]
    assert "degraded" not in by_claim["使用者帖的浏览次数"]


def _fact_scorer(state):
    ev = state["evidence"]
    if "写错" in ev or "写成 Grok Build" in ev:
        return {"verdict": {"choice": "wrong"}}
    if "搜不到" in ev:
        return {"verdict": {"choice": "need_verify"}}
    return {"verdict": {"choice": "correct"}}   # 故意把 △ 判成 correct → 1 条分歧


def test_factcheck_shadow_logs_baseline_and_jev(tmp_path):
    (tmp_path / "_fact-check.md").write_text(FACT_MD, encoding="utf-8")
    fake = FakeJev(_fact_scorer, mode="shadow")
    s = evidence.jev_factcheck_second_opinion(tmp_path, jev=fake)
    assert s["mode"] == "shadow" and s["total"] == 5 and s["scored"] == 5   # unknown 不喂
    assert s["agree"] == 4 and s["disagreements"] == [
        {"claim": "版本号少了「.2」", "baseline": "attributed", "jev": "correct"}]
    assert all({"baseline", "jev", "claim"} <= set(r) for r in fake.rows)


def test_factcheck_receipt_bytes_unchanged_and_fail_open(tmp_path, monkeypatch):
    """draft 审批封存：Jev 抛异常 / 失败 / 关闭，receipt 内容完全一致。"""
    for name, text in {
        "定稿.md": "# 标题\n\n正文。\n", "_fact-check.md": FACT_MD, "_stutter-list.md": "无",
        "_draft-qc.md": "ok", "_draft-approval.md": "审批结论：通过\n",
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(evidence, "_jev_factcheck_client", lambda: None)
    rec_off, err = evidence.write_checkpoint_receipt(tmp_path, "draft", "new-draft")
    assert not err
    monkeypatch.setattr(evidence, "_jev_factcheck_client", lambda: FakeJev(_fact_scorer, raise_on_ask=True))
    rec_boom, err = evidence.write_checkpoint_receipt(tmp_path, "draft", "new-draft")
    assert not err
    for k in ("artifact", "artifact_digest", "decision", "source_mode"):
        assert rec_boom[k] == rec_off[k]
    s = evidence.jev_factcheck_second_opinion(tmp_path, jev=FakeJev(_fact_scorer, raise_on_ask=True))
    assert s["scored"] == 0 and s["errors"] == 5 and s["disagreements"] == []
    assert evidence.jev_factcheck_second_opinion(tmp_path / "nope")["total"] == 0


# ===== 4. distribute：小红书导流第二意见只报不拦 =====

def _xhs_scorer(state):
    return {"divert": {"noul": 0.85 if "详情戳我" in state["copy"] else 0.05}}


def test_xhs_second_opinion_rows_and_new_hit():
    fake = FakeJev(_xhs_scorer)
    soft = "想要完整清单的，详情戳我，你懂的"          # 关键词漏、Jev 命中
    r = distribute.xhs_divert_second_opinion(soft, distribute.xhs_divert_hits(soft), jev=fake)
    assert r["new_hit"] is True and r["baseline_hit"] is False
    hard = "公众号搜「某某」看全文"
    r2 = distribute.xhs_divert_second_opinion(hard, distribute.xhs_divert_hits(hard), jev=fake)
    assert r2["baseline_hit"] is True and r2["hit"] is False and r2["new_hit"] is False
    assert [(x["baseline"], x["jev"]) for x in fake.rows] == [("clean", "hit"), ("hit", "clean")]
    assert distribute.xhs_divert_second_opinion(soft, [], jev=FakeJev(_xhs_scorer, ok=False)) is None
    assert distribute.xhs_divert_second_opinion(soft, [], jev=FakeJev(_xhs_scorer, raise_on_ask=True)) is None


@pytest.mark.parametrize("mode,expect_note", [("shadow", False), ("enforce", True)])
def test_xhs_verify_never_blocks_on_jev(article, all_enabled, monkeypatch, capsys, mode, expect_note):
    distribute.cmd_plan(article)
    _write_social(article, xhs_body="正文。\n\n想要完整清单的，详情戳我，你懂的\n\n#测试 #分发 #写作 #效率")
    _write_images(article)
    fake = FakeJev(_xhs_scorer, mode=mode)
    monkeypatch.setattr(distribute, "_jev_xhs_client", lambda: fake)
    assert distribute.cmd_verify(article, "xhs") == 0          # 只报不拦
    assert ("Jev 第二意见" in capsys.readouterr().err) is expect_note
    assert fake.rows and fake.rows[0]["baseline"] == "clean" and fake.rows[0]["jev"] == "hit"
    # 关键词硬门本身不受影响
    _write_social(article, xhs_body="正文。\n\n公众号搜「某某」看全文\n\n#测试 #分发 #写作 #效率")
    assert distribute.cmd_verify(article, "xhs") == 2


# ===== 共同约束：站点已登记 + 真客户端台账行格式 + 不许直连 =====

@pytest.mark.parametrize("site", list(SITES.values()))
def test_sites_registered_and_ledger_row_has_both_decisions(site, tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_ENABLED", "1")
    monkeypatch.setenv("JEV_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("JEV_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    jev = jc.JevClient(site)
    assert jev.mode == "shadow" and jev.enabled
    monkeypatch.setattr(jev, "ask", lambda **kw: jc.JevResult(ok=True, mode="shadow", answers={
        "ai_tone": {"noul": 0.9}, "substantive_rewrite": {"noul": 0.9},
        "verdict": {"choice": "correct"}, "divert": {"noul": 0.9}}, input_tokens=10))
    if site == SITES["anti_ai"]:
        contracts._jev_anti_ai_second_opinion(HUMAN_PARA, set(), jev=jev)
    elif site == SITES["voice"]:
        L._jev_voice_second_opinion([(NEW_P, DRAFT_P, 0.3, True)], jev=jev)
    elif site == SITES["factcheck"]:
        (tmp_path / "_fact-check.md").write_text(FACT_MD, encoding="utf-8")
        evidence.jev_factcheck_second_opinion(tmp_path, jev=jev)
    else:
        distribute.xhs_divert_second_opinion("详情戳我", [], jev=jev)
    rows = [json.loads(l) for l in next((tmp_path / "ledger").glob(f"*/{site}.jsonl")).read_text().splitlines()]
    assert rows and all(r["site"] == site and {"baseline", "jev"} <= set(r["meta"]) for r in rows)


def test_no_direct_api_calls_outside_client():
    """四个业务文件不许绕过接入层直连 Jev。"""
    for name in ("contracts.py", "learn_edits.py", "evidence.py", "distribute.py"):
        src = (SKILL / "scripts" / name).read_text(encoding="utf-8")
        assert "typesafe.ai" not in src and "urllib" not in src, name
