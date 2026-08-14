"""prompt 精简的安全网：必需短语契约 + 不许再膨胀回去。

2026-08-15 精简 prompt 时当场踩到：把 "dimensional rounded clay text" 改成
"dimensional, rounded, chunky"，语义完全没变，但 visual_route 是**逐字子串比对**，
门直接过不了。那次是靠一条现成测试抓到的，属于运气 —— 这里把它变成契约级断言：
直接遍历 visual_contracts 声明的必需短语，任何一组缺失都当场红。

同时钉一个**上限**。prompt 从 78 篇的 1400 字符一路膨胀到 89 篇的 5000 字符、
否定式从 3 条涨到 29 条，机理是「改一段比加一段贵」：visual_route 逐字比对 +
prompt_sha256 硬校验，让每次出问题时加一条禁令成了最省事的选择，从不删。
上限断言让下一次膨胀在 CI 里就被看见。
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import visual_contracts  # noqa: E402
import visual_workflow as vw  # noqa: E402


ITEM = {
    "id": "01", "title": "一个月，八次更新", "layout_type": "linear-progression",
    "layout": ("A tall clay ribbon runs down the centre. Five small clay robots "
               "stand in a column to its left, three more to its right."),
    "expected_text": ["中国五个", "美国三个"], "facts": ["已核实事实"],
    "aspect_ratio": "9:16", "position": "opening", "anchor": "锚句",
}


def _prompt():
    return vw._infographic_prompt(ITEM, "claymation", {})


def _body(text):
    return text.split("---", 2)[-1] if text.startswith("---") else text


CLAY = visual_contracts.SIGNATURE_VISUAL_PROFILES["warm-light-clay"]
REQUIRED_GROUPS = CLAY["required_prompt_groups"]


def test_contract_actually_declares_groups():
    """先确认取得到契约本身 —— 否则下面的参数化会静默跑零条（已踩过一次）。"""
    assert len(REQUIRED_GROUPS) >= 7, f"必需短语组只有 {len(REQUIRED_GROUPS)} 组"


@pytest.mark.parametrize("group", REQUIRED_GROUPS,
                         ids=[g[0] for g in REQUIRED_GROUPS])
def test_every_required_phrase_group_survives_trimming(group):
    """每一组必需短语至少要有一个变体**原样**出现在 prompt 里。

    visual_route 是逐字子串比对，同义改写过不了门 —— 实测把
    "dimensional rounded clay text" 写成 "dimensional, rounded, chunky"
    语义没变，门直接拦下整批渲染。
    """
    text = _prompt()
    assert any(phrase in text for phrase in group), (
        f"必需短语组 {group} 一个变体都没出现 —— visual_route 逐字门会拦下整批渲染"
    )


def test_forbidden_terms_stay_out_of_prompt():
    text = _prompt().lower()
    for term in CLAY.get("forbidden_prompt_terms", []):
        assert term.lower() not in text, f"prompt 出现禁用词：{term}"


# ── 防再膨胀 ──────────────────────────────────────────────────────────────
# 2026-08-15 精简后实测 2150 字符 / 1 条否定式 / 0 个色号。
# 阈值留了余量，但不该再回到四位数后段。
_MAX_CHARS = 2600
_MAX_NEGATIONS = 4
_NEG = re.compile(
    r"\b(never|not|without|avoid|forbidden|must not|do not|don't|nothing else)\b",
    re.IGNORECASE)
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")


def test_prompt_does_not_balloon_again():
    body = _body(_prompt())
    assert len(body) <= _MAX_CHARS, (
        f"prompt 正文 {len(body)} 字符，超过上限 {_MAX_CHARS}。"
        f"改造前是 4855 字符 —— 那是一路加禁令加出来的。加之前先想想能不能改。"
    )


def test_negations_stay_near_zero():
    """扩散模型对否定式基本不敏感；写了不管用，还挤占注意力。"""
    body = _body(_prompt())
    hits = _NEG.findall(body)
    assert len(hits) <= _MAX_NEGATIONS, (
        f"prompt 有 {len(hits)} 条否定式（{hits}），超过上限 {_MAX_NEGATIONS}。"
        f"改造前是 29 条。要什么就正面描述什么 —— 唯一例外是 logo 合规那条。"
    )


def test_hex_colours_never_reach_the_model():
    """色号进 prompt 会被渲进画面（实测抓到一次整条色卡带）。

    色值仍由 visual_contracts 持有并用于像素级 QA，那才是它该待的地方。
    frontmatter 是结构化元数据，不算给模型的正文指令。
    """
    body = _body(_prompt())
    assert _HEX.findall(body) == [], "prompt 正文出现 hex 色号"


def test_layout_reaches_the_prompt_verbatim():
    """精简不能把 SCENE 弄丢 —— 它是唯一在讲『画什么』的部分。"""
    assert ITEM["layout"] in _prompt()


def test_allowlist_reaches_the_prompt():
    text = _prompt()
    assert ITEM["title"] in text
    for line in ITEM["expected_text"]:
        assert line in text


def test_facts_never_reach_the_prompt():
    """facts 是给人看的核实依据，泄漏进 prompt 会被渲成图上文字。"""
    assert "已核实事实" not in _prompt()
