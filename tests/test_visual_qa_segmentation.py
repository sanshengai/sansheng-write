"""`_fully_segmented_by_allowed` 的分隔符容错契约。

2026-08-14 第 89 篇实测暴露：封面底栏把 tag1 与 tag2 排成「选型 / 盘点」，
中间的斜杠由版式渲染、不属于任何一条 expected_text。OCR 有时把两个胶囊读成
一项（"选型 / 盘点"），有时读成两项 —— 前者被判「白名单外文字」发布失败，
后者放行。**同一张完全合规的封面，成败取决于转写员当次怎么断句**，这是随机
性泄漏进硬门，不是图的问题。

修法：只放行纯分隔符，模型真编出来的字仍须照抓 —— 下面两组用例分别钉住这两侧。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from visual_qa import _fully_segmented_by_allowed  # noqa: E402

COVER_TAGS = {"十分钟补齐", "一个月的模型全在这", "选型", "盘点"}


# --- 该放行的：模板分隔符把两条白名单文字粘成一块 ---

def test_slash_joined_cover_tags_pass():
    """封面底栏的真实形态，2026-08-14 实测卡住发布的那一条。"""
    assert _fully_segmented_by_allowed("选型/盘点", COVER_TAGS)


def test_various_template_separators_pass():
    for joined in ("选型·盘点", "选型、盘点", "选型|盘点", "选型-盘点", "选型：盘点"):
        assert _fully_segmented_by_allowed(joined, COVER_TAGS), joined


def test_leading_and_trailing_separators_pass():
    """信息图标签外圈常被转写出装饰性顿号，如 "、新底座三个、"。"""
    allowed = {"新底座三个", "旧底座五个"}
    assert _fully_segmented_by_allowed("、新底座三个、", allowed)
    assert _fully_segmented_by_allowed("、旧底座五个、", allowed)


def test_plain_concatenation_still_passes():
    assert _fully_segmented_by_allowed("选型盘点", COVER_TAGS)


def test_single_allowed_token_passes():
    assert _fully_segmented_by_allowed("十分钟补齐", COVER_TAGS)


def test_empty_passes():
    assert _fully_segmented_by_allowed("", COVER_TAGS)


# --- 该拦截的：模型真编出来的字 ---

def test_fabricated_text_still_blocked():
    """放宽分隔符不得放过编造内容。"""
    assert not _fully_segmented_by_allowed("限时特惠", COVER_TAGS)


def test_allowed_token_plus_fabricated_tail_blocked():
    assert not _fully_segmented_by_allowed("选型/盘点/立即购买", COVER_TAGS)


def test_partial_token_blocked():
    assert not _fully_segmented_by_allowed("选型/盘", COVER_TAGS)


def test_english_junk_blocked():
    """01 初版曾渲染出意外的 "new feature"。"""
    assert not _fully_segmented_by_allowed("newfeature", COVER_TAGS)


def test_separators_only_is_not_a_free_pass_for_content():
    """纯分隔符块本身可放行，但不得因此放行夹带的实义字。"""
    assert _fully_segmented_by_allowed("//", COVER_TAGS)
    assert not _fully_segmented_by_allowed("//促销", COVER_TAGS)
