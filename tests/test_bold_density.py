"""verify_bold_density 行为契约。

背景：这个门能 exit 2 阻断发布，但在 2026-08-14 之前**一条测试都没有** ——
所以 2026-08-14 放宽阈值时，458 项存量测试全绿，等于没有任何回归保护。
本文件补上，钉住放宽后的行为，防止阈值被无意改回硬门。

2026-08-14 放宽（sandy 拍板）的两条设计意图：
  ① 上限按字数**线性折算**，不再阶跃分档 —— 多写两句话不该让上限突然跳一档；
  ② **软硬双阈值** —— 略超只提示（soft_over，不阻断），真刷屏才拦。
  ③ 整句加粗留 2 处名额给金句，超出才违规。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from contracts import verify_bold_density  # noqa: E402

# pipeline.py 的调用方约定：只有这三个 verdict 阻断
BLOCKING_VERDICTS = {"bold_over", "integral_bold_violation", "both_violations"}


def _doc(zh_filler: int, n_bold: int = 0, n_integral: int = 0) -> str:
    """构造测试正文。

    🔴 每个加粗块之间必须夹普通文字：连续拼接 `**词**` 会产出 `**词****词**`，
       四连星号会被粗斜体正则 `\\*\\*\\*[^*]+\\*\\*\\*` 误匹配，测出来的
       italic_bold_count 是假的（第一版测试就踩了这个坑）。
    """
    parts = ["字" * zh_filler]
    parts += [f"前文**词{i}**后文" for i in range(n_bold)]
    parts += [
        f"前文**这是一句超过二十个中文字符的整句加粗用于做金句节拍器{i}**后文"
        for i in range(n_integral)
    ]
    return "，".join(parts)


# --- ① 上限随字数线性增长，不阶跃 ---

def test_limit_scales_linearly_with_word_count():
    small = verify_bold_density("字" * 4000)
    large = verify_bold_density("字" * 8000)
    assert large["bold_limit"] > small["bold_limit"], "字数翻倍，上限应随之提高"
    # 线性折算：每千字 10 处
    assert large["bold_limit"] == 80
    assert small["bold_limit"] == 40


def test_no_cliff_at_old_tier_boundary():
    """旧实现在 5000 字处从 35 跳到 45；线性折算后跨界不应出现跳变。"""
    before = verify_bold_density("字" * 4990)["bold_limit"]
    after = verify_bold_density("字" * 5010)["bold_limit"]
    assert abs(after - before) <= 1, f"5000 字边界仍有阶跃：{before} -> {after}"


def test_short_article_gets_floor():
    """短文有保底，不至于被压到没有标识可用。"""
    assert verify_bold_density("字" * 500)["bold_limit"] == 30


def test_hard_limit_is_above_soft_limit():
    r = verify_bold_density("字" * 4000)
    assert r["bold_hard_limit"] > r["bold_limit"]


# --- ② 软硬双阈值 ---

def test_within_soft_limit_is_ok():
    r = verify_bold_density(_doc(4000, n_bold=30))
    assert r["verdict"] == "ok"
    assert r["verdict"] not in BLOCKING_VERDICTS


def test_slightly_over_soft_limit_warns_but_does_not_block():
    """核心诉求：「稍微超就超一点」—— 不能再判死。"""
    r = verify_bold_density(_doc(4000, n_bold=45))
    assert r["verdict"] == "soft_over"
    assert r["verdict"] not in BLOCKING_VERDICTS, "略超软上限不得阻断发布"


def test_way_over_hard_limit_blocks():
    """放宽不等于取消：真·刷屏仍然要拦。"""
    r = verify_bold_density(_doc(4000, n_bold=100))
    assert r["verdict"] == "bold_over"
    assert r["verdict"] in BLOCKING_VERDICTS


# --- ③ 整句加粗留名额给金句 ---

def test_two_integral_bolds_allowed_for_golden_lines():
    r = verify_bold_density(_doc(4000, n_integral=2))
    assert r["verdict"] == "ok"
    assert r["integral_bold_allowance"] == 2


def test_three_integral_bolds_violates():
    r = verify_bold_density(_doc(4000, n_integral=3))
    assert r["verdict"] == "integral_bold_violation"
    assert r["verdict"] in BLOCKING_VERDICTS


def test_integral_threshold_raised_to_20_chars():
    """15~19 中文字的加粗不再算「整句」（阈值从 15 放宽到 20）。"""
    body = "字" * 4000 + "，前文**十六个中文字符的加粗短语啊啊**后文"
    r = verify_bold_density(body)
    assert r["integral_bold_count"] == 0


def test_both_violations_when_flooded_and_integral_over():
    r = verify_bold_density(_doc(4000, n_bold=100, n_integral=3))
    assert r["verdict"] == "both_violations"
    assert r["verdict"] in BLOCKING_VERDICTS


# --- 回归保护：不许悄悄改回硬门 ---

def test_soft_over_verdict_must_exist():
    """若有人删掉 soft_over 分支，本用例先红，而不是等作者被闸门卡住才发现。"""
    r = verify_bold_density(_doc(4000, n_bold=45))
    assert r["verdict"] == "soft_over", (
        "soft_over 是 2026-08-14 放宽的核心机制，不得移除；"
        "移除会让「略超即判死」的老问题复活"
    )


def test_invalid_input_guard():
    assert verify_bold_density("")["verdict"] == "invalid_input"
    assert verify_bold_density(None)["verdict"] == "invalid_input"
