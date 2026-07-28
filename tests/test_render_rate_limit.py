# -*- coding: utf-8 -*-
"""限流与 prompt 文字约束的回归测试。

这些用例全部来自一次真实事故：一批 6 张图反复「总有两三张失败，重跑又换成
另外几张失败」，最后查出两个独立原因叠加 ——

1. renderer-policy 里写的模型 ID 带 `-preview`，而那些模型已转正、preview ID 下线，
   于是每张图都先撞一次 404 再发真请求，整批请求数翻倍，自己把自己限流；
2. 429 被混进 404 的降级链，被当成「模型不可用」处理 —— 换模型对配额毫无帮助，
   还把真正的原因（打太快）掩盖成了「模型不行」。

外加一条图面事故：中文的 layout 排布说明被直接嵌进 prompt 正文，模型把整句
排布说明当标题画进了图里。
"""
import json
from pathlib import Path

from scripts import gen_img, visual_workflow


# ── 429 vs 404：处置完全相反，必须分得开 ──────────────────────────────

def test_识别限流的多种写法():
    for text in (
        '{"code": 429, "message": "Resource has been exhausted"}',
        '{"status": "RESOURCE_EXHAUSTED"}',
        "Rate limit exceeded",
    ):
        assert gen_img._is_rate_limited(text) is True, text


def test_模型不存在不得被当成限流():
    """🔴 这两类必须分开：404 要换模型，429 要等。
    早期版本把 429 塞进 404 的降级链，结果是拿好模型去撞已经满的配额。"""
    assert gen_img._is_rate_limited(
        '{"code": 404, "message": "Publisher model not found"}') is False
    assert gen_img._is_rate_limited("") is False
    assert gen_img._is_rate_limited(None) is False


def test_退避参数足够覆盖一分钟配额窗口():
    """图像模型配额按每分钟算。退避总时长必须跨过一个窗口，否则重试等于白试。"""
    delays, d = [], gen_img._RETRY_BASE_SECONDS
    for _ in range(gen_img._RETRY_MAX_ATTEMPTS - 1):
        delays.append(d)
        d *= 2
    assert sum(delays) >= 25, f"退避总时长仅 {sum(delays)}s，跨不过一分钟级配额窗口"


# ── 并发：gen_img 的串行保护在多进程下失效，必须在编排层限流 ───────────

def test_默认并发不得回到会打满配额的档位():
    """gen_img 自己是串行设计，但 render_visuals 每张图起一个独立进程，
    那份保护绕不过来。默认并发实测 4 会打满、2 能一次跑完。"""
    from scripts import render_visuals
    assert render_visuals._DEFAULT_JOBS <= 2


# ── prompt 文字约束 ──────────────────────────────────────────────────

def _prompt(**over) -> str:
    item = {
        "id": "01",
        "position": "opening",
        "aspect_ratio": "9:16",
        "title": "重置的间隔正在收窄",
        "layout_type": "linear-progression",
        "layout": "四级台阶横向递进，每级一个日期与用户数标签",
        "template_id": "tiered-network",
        "expected_text": ["7月14日 700万", "7月15日 800万", "7月16日 900万", "7月22日 1000万"],
        "facts": ["f1"],
    }
    item.update(over)
    return visual_workflow._infographic_prompt(item, "claymation", {})


def test_中文排布说明必须显式标为不可渲染():
    """🔴 实测事故：整句中文排布说明被模型当标题画进了图里。
    只把它放进 prompt 而不声明用途，等于和下面的白名单指令自相矛盾。"""
    text = _prompt()
    assert "COMPOSITION GUIDANCE" in text
    guidance_at = text.index("COMPOSITION GUIDANCE")
    layout_at = text.index("四级台阶横向递进")
    assert guidance_at < layout_at, "排布说明必须落在不可渲染声明之后"
    assert "Never render this guidance" in text


def test_必须明令每条文字只出现一次():
    """实测事故：四个并列的里程碑标签被同时画成徽章和台阶脚注，每条重复两遍。"""
    text = _prompt()
    assert "EXACTLY ONCE" in text
    assert "never repeat" in text.lower()


def test_必须明令禁画真实logo():
    """实测事故：讲两家产品对比的图里，模型把某家的真实 logo 画了出来。"""
    text = _prompt()
    assert "logo" in text.lower()
    assert "Never draw any real company or product logo" in text


# ── 默认渲染策略 ─────────────────────────────────────────────────────

def _policy() -> dict:
    p = Path(visual_workflow.__file__).resolve().parents[1] / "templates" / "renderer-policy.template.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_默认策略走生成式渲染器():
    """🔴 默认曾是确定性模板渲染器，而那些模板的插画元素是随某一篇文章的题材
    做出来的（房子、人群、社区节点）。任何新题材照默认建 policy，都会继承
    那套与内容无关的视觉语汇 —— 事故就是这么来的。"""
    renderers = _policy()["renderers"]
    assert renderers, "默认策略不得为空"
    assert renderers[0]["provider"] == "sansheng-google"
    assert all(r["provider"] != "sansheng-template-safe" for r in renderers)


def test_默认模型ID不得带preview后缀():
    """🔴 preview ID 下线后，降级链会先撞一次 404 再发真请求，
    整批请求数翻倍 —— 这是自造 429 的头号原因。"""
    for r in _policy()["renderers"]:
        assert not r["model"].endswith("-preview"), (
            f"{r['model']} 带 -preview；模型转正后该 ID 会 404，每张图白打一发空枪"
        )
