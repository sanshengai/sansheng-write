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


GOOD_XHS_TITLE = "五个字的标题"
GOOD_XHS_BODY = "正文写在这里，能独立成立。\n\n#测试 #分发 #写作 #效率"
GOOD_WEIBO_BODY = "一个完整的判断，配一个具体的数字：这套流程把分发成本压到近乎零。\n\n#测试# #分发#"


def _write_social(article: Path, xhs_title=GOOD_XHS_TITLE, xhs_body=GOOD_XHS_BODY,
                  weibo_body=GOOD_WEIBO_BODY) -> None:
    """写 dist/社媒文案.txt（与晨报同款双段格式）。"""
    text = (
        "════════════ 小红书 ════════════\n\n"
        f"# 标题\n\n{xhs_title}\n\n"
        f"# 正文\n\n{xhs_body}\n\n\n"
        "════════════ 微博 ════════════\n\n"
        f"# 正文\n\n{weibo_body}\n"
    )
    p = distribute.dist_dir(article) / distribute.SOCIAL_COPY_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_images(article: Path, n: int = 6) -> None:
    """小红书是图文，verify 会查图。"""
    d = distribute.channel_dir(article, "xhs") / "images"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"{i + 1:02d}-p.png").write_bytes(b"x")


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
    _write_social(article, weibo_body="字" * 200 + "\n\n#测试# #分发#")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_微博标签缺尾井号被拦(article, all_enabled):
    """小红书格式误用到微博——最容易犯的错，机器必须拦住。"""
    distribute.cmd_plan(article)
    _write_social(article, weibo_body="短正文。\n\n#测试 #分发")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_小红书误用微博标签格式被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_social(article, xhs_body="正文。\n\n#测试# #分发# #写作# #效率#")
    _write_images(article)
    assert distribute.cmd_verify(article, "xhs") == 2


def test_小红书标题超长被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_social(article, xhs_title="字" * 30)
    _write_images(article)
    assert distribute.cmd_verify(article, "xhs") == 2


def test_标签数量不足被拦(article, all_enabled):
    distribute.cmd_plan(article)
    _write_social(article, xhs_body="正文。\n\n#测试")
    _write_images(article)
    assert distribute.cmd_verify(article, "xhs") == 2


def test_缺文案文件被拦(article, all_enabled):
    distribute.cmd_plan(article)
    assert distribute.cmd_verify(article, "weibo") == 2


def test_合规文案通过并置状态(article, all_enabled):
    distribute.cmd_plan(article)
    _write_social(article)
    _write_images(article)
    assert distribute.cmd_verify(article, "weibo") == 0
    assert distribute.cmd_verify(article, "xhs") == 0
    assert distribute.get_status(article, "weibo") == "verified"


def test_未先_plan_不能_verify(article, all_enabled):
    _write_social(article)
    assert distribute.cmd_verify(article, "weibo") == 2


# ===== 上游漂移（关键防回归） =====

def test_定稿变更后_verify_阻断(article, all_enabled):
    distribute.cmd_plan(article)
    _write_social(article)
    assert distribute.cmd_verify(article, "weibo") == 0
    (article / "定稿.md").write_text(FINAL_TEXT + "\n改了一句。\n", encoding="utf-8")
    assert distribute.cmd_verify(article, "weibo") == 2


def test_定稿变更后_dispatch_也阻断(article, all_enabled):
    """🔴 防回归：曾经只在 verify 查 digest。
    `plan --only weibo` 之后小红书仍停在 verified，dispatch 光看状态
    就会把对应旧定稿的文案发出去。"""
    distribute.cmd_plan(article)
    _write_social(article)
    _write_images(article)
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
    _write_social(article)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=False) == 0
    assert not (distribute.channel_dir(article, "weibo") / distribute.RECEIPT_FILE).exists()
    assert distribute.get_status(article, "weibo") == "verified"


@pytest.fixture
def fake_browser(monkeypatch, tmp_path):
    """拦掉真实的 Chrome 启动。

    🔴 dispatch 会打开浏览器并填入内容，测试里绝不能真跑——既慢又会
    在维护者机器上弹窗，CI 上还没有登录态。这里替换掉脚本解析、bun 查找
    与子进程调用，只验证「传了什么参数、写没写凭证」。
    """
    script = tmp_path / "fake-post.ts"
    script.write_text("// fake", encoding="utf-8")
    calls = []

    def fake_call(argv):
        calls.append(argv)
        return fake_call.rc

    fake_call.rc = 0
    monkeypatch.setattr(distribute, "resolve_post_script", lambda ch, cfg: script)
    monkeypatch.setattr(distribute, "_find_bun", lambda: "bun")
    monkeypatch.setattr(distribute.subprocess, "call", fake_call)
    return fake_call, calls


def test_找不到发布脚本时失败且不写凭证(article, all_enabled, monkeypatch):
    """🔴 宁可失败，也不能写一条没发生过的发布记录。"""
    monkeypatch.setattr(distribute, "resolve_post_script", lambda ch, cfg: None)
    distribute.cmd_plan(article)
    _write_social(article)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 2
    assert distribute.get_status(article, "weibo") == "verified"   # 状态不许前进
    assert not (distribute.channel_dir(article, "weibo") / distribute.RECEIPT_FILE).exists()


def test_填充失败不写凭证(article, all_enabled, fake_browser):
    """脚本非零退出（比如没登录）时，状态必须停在 verified。"""
    fake_call, _ = fake_browser
    fake_call.rc = 1
    distribute.cmd_plan(article)
    _write_social(article)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 2
    assert distribute.get_status(article, "weibo") == "verified"
    assert not (distribute.channel_dir(article, "weibo") / distribute.RECEIPT_FILE).exists()


def test_小红书填充成功后写凭证(article, all_enabled, fake_browser):
    _, calls = fake_browser
    distribute.cmd_plan(article)
    _write_social(article)
    _write_images(article)
    distribute.cmd_verify(article, "xhs")
    assert distribute.cmd_dispatch(article, "xhs", confirm=True) == 0

    argv = calls[0]
    assert "--title" in argv and GOOD_XHS_TITLE in argv
    assert "--content" in argv
    assert argv.count("--image") == 6          # 六张轮播图都传了

    receipt = json.loads(
        (distribute.channel_dir(article, "xhs") / distribute.RECEIPT_FILE).read_text(encoding="utf-8"))
    assert receipt["mode"] == "assisted"
    assert distribute.get_status(article, "xhs") == "dispatched"


def test_微博文案走位置参数而非_content(article, all_enabled, fake_browser):
    """两个脚本的调用约定不同：weibo-post.ts 的文案是位置参数。"""
    _, calls = fake_browser
    distribute.cmd_plan(article)
    _write_social(article)
    _write_images(article)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 0

    argv = calls[0]
    assert "--content" not in argv
    assert argv[2].startswith("一个完整的判断")


def test_微博限图数量(article, all_enabled, fake_browser, monkeypatch):
    """微博最多 4 张自动排九宫格，不能把 16 张轮播图全丢过去。"""
    cfg = {"enabled": True, "body_soft_max": 140, "tag_min": 2, "image_max": 4}
    monkeypatch.setattr(distribute, "distribute_channel",
                        lambda n: cfg if n == "weibo" else {"enabled": True, "tag_min": 4})
    _, calls = fake_browser
    distribute.cmd_plan(article, only="weibo")
    _write_social(article)
    _write_images(article, n=16)
    distribute.cmd_verify(article, "weibo")
    assert distribute.cmd_dispatch(article, "weibo", confirm=True) == 0
    assert calls[0].count("--image") == 4


# ===== 小红书字数算法 =====

def test_小红书字数算法(article):
    """🔴 中文/emoji/标点=1，英文数字=0.5，空格不计。
    用 len() 会和平台自己的计数对不上，把合规标题误判超长（晨报 2026-07-08 踩过）。"""
    assert distribute.xhs_char_count("中文五个字啊") == 6
    assert distribute.xhs_char_count("abcd") == 2.0
    assert distribute.xhs_char_count("a b c d") == 2.0       # 空格不计
    assert distribute.xhs_char_count("AI 早安 07/29") == pytest.approx(2 + 1 + 2.5)


def test_英文标题不会被误判超长(article, all_enabled):
    """40 个英文字符按官方算法只有 20 字，正好卡线——用 len() 会误拦。"""
    distribute.cmd_plan(article)
    _write_social(article, xhs_title="a" * 40)
    _write_images(article)
    assert distribute.cmd_verify(article, "xhs") == 0


# ===== 杂项 =====

def test_非法状态被拒(article):
    with pytest.raises(SystemExit):
        distribute.set_status(article, "weibo", "已发布")


def test_中文列宽按显示宽度算(article):
    assert distribute._display_width("微博") == 4
    assert distribute._display_width("weibo") == 5


def test_status_可在未配置时运行(article):
    assert distribute.cmd_status(article) == 0


# ===== 小红书站外导流硬门（2026-06 平台把间接导流也纳入处罚） =====

@pytest.mark.parametrize("text,label", [
    ("公众号搜「某某」看全文", "引导站外搜账号"),
    ("详见主页简介", "主页引导"),
    ("想了解更多看我主页", "夹字的主页引导"),
    ("全文见 https://example.com/a", "站外链接"),
    ("私信我发你完整版", "私信引导"),
    ("加V领取资料", "联系方式变体"),
    ("进群一起聊", "私域引导"),
    ("扫码关注", "二维码引导"),
])
def test_小红书导流违禁词被识别(text, label):
    assert distribute.xhs_divert_hits(text), f"漏判：{label} — {text}"


@pytest.mark.parametrize("text", [
    "五本书拆穿了同一个错觉。你怎么看，评论区聊聊。",
    "条件塑造结果，判断可能误读结果。",
    "从《引爆点》到《逆转》，作者反复提醒一件事。",
])
def test_正常文案不被误拦(text):
    assert not distribute.xhs_divert_hits(text), f"误伤：{text}"


def test_小红书文案含导流时_verify_阻断(article, all_enabled):
    """🔴 硬门：命中即拦。平台扣分累计不清零，一次侥幸换来的是账号长期降权。"""
    distribute.cmd_plan(article)
    _write_social(article, xhs_body="正文。\n\n公众号搜「某某」看全文\n\n#测试 #分发 #写作 #效率")
    _write_images(article)
    assert distribute.cmd_verify(article, "xhs") == 2


def test_微博含链接不被拦(article, all_enabled):
    """微博是唯一能直给链接的渠道，不能套用小红书的规则。"""
    distribute.cmd_plan(article)
    _write_social(article, weibo_body="一个判断加一个数字。\n\n🔗 全文：https://example.invalid/s/X\n\n#测试# #分发#")
    _write_images(article)
    assert distribute.cmd_verify(article, "weibo") == 0


def test_计划里给出各渠道的引流口径(article, all_enabled):
    distribute.cmd_plan(article)
    plan = json.loads((distribute.dist_dir(article) / distribute.PLAN_FILE).read_text(encoding="utf-8"))
    assert "零引流" in plan["channels"]["xhs"]["divert_policy"]
    assert plan["channels"]["weibo"]["divert_url"] == WECHAT_URL
