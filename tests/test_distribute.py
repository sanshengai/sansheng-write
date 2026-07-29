# -*- coding: utf-8 -*-
"""分发层（一稿多投）的闸门与状态机测试。

重点钉三件事：
  1. 渠道口径差异（小红书 #标签 / 微博 #话题#）真的被机器拦住，不靠人记
  2. 上游漂移后 verify **和** dispatch 双双阻断（曾经只在 verify 查，dispatch 能放过期文案出去）
  3. 未接线的自动派发明确失败，绝不写「发过了」的假状态
"""
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import distribute  # noqa: E402


# ===== fixtures =====

FINAL_TEXT = "# 测试文章\n\n正文内容，用来算 digest。\n"
WECHAT_URL = "https://example.invalid/s/TESTTESTTEST"


@pytest.fixture
def article(tmp_path: Path) -> Path:
    """最小可用的文章目录：定稿 + state（含 title_final 与永久链接）+ meta。"""
    d = tmp_path / "1-测试选题"
    (d / "素材").mkdir(parents=True)
    (d / "定稿.md").write_text(FINAL_TEXT, encoding="utf-8")
    (d / "article-meta.yaml").write_text(
        'title: "元数据里的旧标题"\n'
        'digest: "一句话摘要"\n'
        'tags: ["测试"]\n',
        encoding="utf-8",
    )
    (d / ".state.json").write_text(json.dumps({
        "schema_version": 2,
        "stages": {
            "writing": {"status": "done", "title_final": "定稿标题"},
            "publish": {"status": "done", "wechat_url": WECHAT_URL},
        },
    }, ensure_ascii=False), encoding="utf-8")
    for name in ("cover.png", "p1.png", "p2.png"):
        (d / "素材" / name).write_bytes(b"x")
    return d


@pytest.fixture
def all_enabled(monkeypatch):
    """把三个渠道都打开（profile.example 里默认是全注释的）。"""
    cfg = {
        "xhs": {"enabled": True, "title_max": 20, "body_max": 1000, "tag_min": 4},
        "weibo": {"enabled": True, "body_soft_max": 140, "tag_min": 2},
        "podcast": {"enabled": True, "shownotes_max": 800},
    }
    monkeypatch.setattr(distribute, "distribute_channel", lambda n: cfg.get(n, {}))
    return cfg


def _write_copy(article: Path, channel: str, text: str) -> None:
    p = distribute.channel_dir(article, channel) / "文案.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


GOOD_WEIBO = "一个完整的判断，配一个具体的数字：这套流程把分发成本压到了近乎零。\n\n#测试# #分发#"
GOOD_XHS = "五个字的标题\n\n正文写在这里，能独立成立。\n\n#测试 #分发 #写作 #效率"


# ===== 配置解析 =====

def test_未配置_profile_时所有渠道未启用(article):
    """profile.example 的 distribute 段是注释掉的——这是正常路径，不该崩。"""
    assert distribute.enabled_channels() == []
    assert distribute.cmd_plan(article) == 1   # 无渠道可规划，非 0 但也非崩溃


def test_渠道未启用时禁止派发(article, monkeypatch):
    monkeypatch.setattr(distribute, "distribute_channel", lambda n: {"enabled": False})
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 2


# ===== 上游读取 =====

def test_标题取_state_的_title_final_而非_meta(article):
    """meta 里的 title 可能滞后于 retitle，真源是 state。"""
    assert distribute.read_final_title(article) == "定稿标题"


def test_永久链接取_state_不取草稿箱凭证(article):
    """_publish-receipt.json 是**草稿箱**凭证，没有永久链接；
    读错地方会让每篇文章都显示「未发布」。"""
    (article / "_publish-receipt.json").write_text(
        json.dumps({"formal_publish": False, "draft_media_id": "abc"}), encoding="utf-8")
    assert distribute.read_wechat_url(article) == WECHAT_URL


def test_封面图排在素材列表最前(article):
    assert distribute.list_source_images(article)[0] == "cover.png"


# ===== plan =====

def test_plan_产出计划与待填槽(article, all_enabled):
    assert distribute.cmd_plan(article) == 0
    plan = json.loads((distribute.dist_dir(article) / distribute.PLAN_FILE).read_text(encoding="utf-8"))
    assert set(plan["channels"]) == {"xhs", "weibo", "podcast"}
    assert plan["channels"]["xhs"]["constraints"]["title_max"] == 20
    assert plan["channels"]["weibo"]["constraints"]["body_max"] == 140
    # 槽是空的：脚本不编内容
    assert plan["channels"]["xhs"]["fill"]["title"] == ""
    for ch in ("xhs", "weibo", "podcast"):
        assert distribute.get_status(article, ch) == "planned"


def test_plan_拒绝未知渠道(article, all_enabled):
    assert distribute.cmd_plan(article, only="douyin") == 2


def test_无定稿时_plan_失败(tmp_path, all_enabled):
    empty = tmp_path / "空目录"
    empty.mkdir()
    assert distribute.cmd_plan(empty) == 2


# ===== verify 硬门 =====

def test_微博超字数被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", "字" * 200 + "\n\n#测试# #分发#")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_微博标签缺尾井号被拦(article, all_enabled):
    """小红书格式误用到微博——最容易犯的错，机器必须拦住。"""
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", "短正文。\n\n#测试 #分发")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_小红书误用微博标签格式被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "xhs", "标题\n\n正文。\n\n#测试# #分发# #写作# #效率#")
    assert distribute.cmd_verify(article, "xhs") == 2


def test_小红书标题超长被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "xhs", "字" * 30 + "\n\n正文。\n\n#测试 #分发 #写作 #效率")
    assert distribute.cmd_verify(article, "xhs") == 2


def test_标签数量不足被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "xhs", "标题\n\n正文。\n\n#测试")
    assert distribute.cmd_verify(article, "xhs") == 2


def test_缺文案文件被拦(article, all_enabled):
    distribute.cmd_plan(article)
    assert distribute.cmd_verify(article, "weibo") == 2


def test_合规文案通过并置状态(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", GOOD_WEIBO)
    _write_copy(article, "xhs", GOOD_XHS)
    assert distribute.cmd_verify(article, "weibo") == 0
    assert distribute.cmd_verify(article, "xhs") == 0
    assert distribute.get_status(article, "weibo") == "verified"


def test_未先_plan_不能_verify(article, all_enabled):
    _write_copy(article, "weibo", GOOD_WEIBO)
    assert distribute.cmd_verify(article, "weibo") == 2


# ===== 上游漂移（关键防回归） =====

def test_定稿变更后_verify_阻断(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", GOOD_WEIBO)
    assert distribute.cmd_verify(article, "weibo") == 0
    (article / "定稿.md").write_text(FINAL_TEXT + "\n改了一句。\n", encoding="utf-8")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_定稿变更后_dispatch_也阻断(article, all_enabled):
    """🔴 防回归：曾经只在 verify 查 digest。
    `plan --only weibo` 之后小红书仍停在 verified，dispatch 光看状态
    就会把对应旧定稿的文案发出去。"""
    distribute.cmd_plan(article)
    _write_copy(article, "xhs", GOOD_XHS)
    _write_copy(article, "weibo", GOOD_WEIBO)
    assert distribute.cmd_verify(article, "xhs") == 0
    assert distribute.cmd_verify(article, "weibo") == 0

    (article / "定稿.md").write_text(FINAL_TEXT + "\n改了一句。\n", encoding="utf-8")
    distribute.cmd_plan(article, only="weibo")          # 只重做微博

    assert distribute.get_status(article, "xhs") == "verified"   # 状态没变
    assert distribute.cmd_dispatch(article, "xhs", confirm=True) == 2  # 但必须被拦


# ===== dispatch =====

def test_未_verify_不能_dispatch(article, all_enabled):
    distribute.cmd_plan(article)
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 2


def test_dry_run_不写凭证(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", GOOD_WEIBO)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=False) == 0
    assert not (distribute.channel_dir(article, "weibo") / distribute.RECEIPT_FILE).exists()
    assert distribute.get_status(article, "weibo") == "verified"


def test_未接线的自动派发明确失败(article, all_enabled):
    """🔴 宁可 exit 3，也不能写一条没发生过的发布记录。"""
    distribute.cmd_plan(article)
    _write_copy(article, "weibo", GOOD_WEIBO)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 3
    assert distribute.get_status(article, "weibo") == "verified"   # 状态不许前进
    assert not (distribute.channel_dir(article, "weibo") / distribute.RECEIPT_FILE).exists()


def test_手动渠道确认后写凭证(article, all_enabled):
    distribute.cmd_plan(article)
    _write_copy(article, "xhs", GOOD_XHS)
    distribute.cmd_verify(article, "xhs")
    assert distribute.cmd_dispatch(article, "xhs", confirm=True) == 0
    receipt = json.loads(
        (distribute.channel_dir(article, "xhs") / distribute.RECEIPT_FILE).read_text(encoding="utf-8"))
    assert receipt["mode"] == "manual"
    assert distribute.get_status(article, "xhs") == "dispatched"


# ===== 杂项 =====

def test_非法状态被拒(article):
    with pytest.raises(SystemExit):
        distribute.set_status(article, "weibo", "已发布")


def test_中文列宽按显示宽度算(article):
    assert distribute._display_width("微博") == 4
    assert distribute._display_width("weibo") == 5


def test_status_可在未配置时运行(article):
    assert distribute.cmd_status(article) == 0
