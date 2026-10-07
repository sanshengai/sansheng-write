"""守门：写作 Skill 对宝玉（baoyu）的引用只减不增。

2026-09-30 起新代码不得新增 baoyu 调用；旧路径（schema1 合同、显式回退开关）的存量冻结在下表。
某文件引用数下降就把这里的数字同步调低（棘轮）；新增文件或超出上限即失败。
"""
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BASELINE = {
    "audio_covers.py": 8,
    "baoyu_contract.py": 38,
    "baoyu_locator.py": 8,
    "compress_images.py": 2,
    "contracts.py": 6,
    "distribute.py": 7,
    "evidence.py": 15,
    "format_layout.py": 27,
    "generate_article_bgm.py": 1,
    "md_render.py": 11,
    "md_render_compare.py": 1,
    "pipeline.py": 15,
    "regression_baseline.py": 5,
    "release_to_draft.py": 18,
    "render_visuals.py": 34,
    "setup.py": 1,
    "setup_check.py": 12,
    "stylebook_reading.py": 1,
    "stylebook_workflow.py": 1,
    "svg_to_png.py": 3,
    "visual_contracts.py": 1,
    "visual_qa.py": 5,
    "visual_workflow.py": 35,
    "wechat_api.py": 1,
    "x_article.py": 3
}


def _count(p: Path) -> int:
    return len(re.findall(r"baoyu|宝玉", p.read_text(encoding="utf-8"), re.I))


def test_no_new_baoyu_references():
    over = {}
    for p in SCRIPTS.glob("*.py"):
        n = _count(p)
        if n > BASELINE.get(p.name, 0):
            over[p.name] = (n, BASELINE.get(p.name, 0))
    assert not over, f"新增了宝玉引用（现有, 上限）：{over}；新代码走叁笙生图与内置模块"


def test_guard_rejects_a_new_reference(tmp_path):
    """反例：临时文件写入一次 baoyu 调用，判据必须判为超限。"""
    f = tmp_path / "new_mod.py"
    f.write_text("run('baoyu-image-gen')\n", encoding="utf-8")
    assert _count(f) > BASELINE.get(f.name, 0)


def test_vendored_weibo_is_self_contained():
    d = SCRIPTS / "_vendor" / "weibo"
    assert (d / "weibo-post.ts").is_file() and (d / "chrome-cdp.ts").is_file() and (d / "LICENSE").is_file()
    assert "baoyu-chrome-cdp" not in (d / "weibo-utils.ts").read_text(encoding="utf-8")
