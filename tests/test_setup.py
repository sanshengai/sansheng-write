# -*- coding: utf-8 -*-
"""交互式配置引导的行为测试（发布规约 optional-features.md「验收」四段）。

钉住的是「可选模块契约」的可执行部分：
  1. 全关状态可用，且主线流程零提及可选模块
  2. 引导可跑（含非交互降级、拒绝写示例 profile）
  3. 单模块启用不牵连其他
  4. 重复运行识别已配项，而不是从头再问一遍
"""
import sys
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import profile_config as pc  # noqa: E402
import setup  # noqa: E402
import distribute  # noqa: E402


@pytest.fixture
def my_profile(tmp_path, monkeypatch):
    """一份属于「用户自己」的 profile（不是仓内 example），可写。"""
    d = tmp_path / "my-profile"
    d.mkdir()
    (d / "brand.yaml").write_text(
        "# 我的注释，必须活下来\nname: 我的专栏\n", encoding="utf-8")
    monkeypatch.setattr(pc, "profile_dir", lambda: d)
    monkeypatch.setattr(pc, "using_example_profile", lambda: False)
    monkeypatch.setattr(setup.pc, "profile_dir", lambda: d)
    monkeypatch.setattr(setup.pc, "using_example_profile", lambda: False)
    return d / "brand.yaml"


def _fake_io(monkeypatch, answers):
    """喂一串答案给 input()，并让脚本认为自己在交互终端里。"""
    seq = list(answers)
    monkeypatch.setattr(setup, "_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: seq.pop(0) if seq else "")
    return seq


def _load(target: Path) -> dict:
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


# ===== 验收 1：全关可用 + 零提及 =====

def test_未启用任何模块时体检不提可选模块(capsys, monkeypatch):
    monkeypatch.setattr(distribute, "distribute_channel", lambda n: {})
    import setup_check
    setup_check._check_optional_distribute()
    out = capsys.readouterr().out
    assert out == "", f"未启用却打印了：{out!r}"


def test_启用后体检才列出该模块(capsys, monkeypatch):
    monkeypatch.setattr(distribute, "distribute_channel",
                        lambda n: {"enabled": True} if n == "weibo" else {})
    monkeypatch.setattr(distribute, "resolve_post_script", lambda ch, cfg: Path("x.ts"))
    monkeypatch.setattr(distribute, "_find_bun", lambda: "bun")
    import setup_check
    setup_check._check_optional_distribute()
    out = capsys.readouterr().out
    assert "微博" in out
    assert "小红书" not in out          # 单模块启用不牵连其他
    assert "播客" not in out


# ===== 验收 2：引导可跑 =====

def test_非交互环境不阻塞而是打印清单(capsys, monkeypatch, my_profile):
    monkeypatch.setattr(setup, "_interactive", lambda: False)
    assert setup.main() == 0
    out = capsys.readouterr().out
    assert "非交互环境" in out
    assert "小红书图文" in out


def test_拒绝写入仓内示例_profile(capsys, monkeypatch):
    monkeypatch.setattr(setup.pc, "using_example_profile", lambda: True)
    assert setup.main() == 2
    out = capsys.readouterr().out
    assert "不能往里写个人配置" in out
    assert "cp -r profile.example" in out      # 报错必须清晰指路（§4.4）


def test_全部跳过则三个模块都是关闭(monkeypatch, my_profile):
    _fake_io(monkeypatch, ["n", "n", "n", "y"])   # 三问皆否 + 确认写入
    assert setup.main() == 0
    chans = _load(my_profile)["distribute"]["channels"]
    assert all(not chans[k].get("enabled") for k in ("xhs", "weibo", "podcast"))


def test_取消写入则不改动文件(monkeypatch, my_profile):
    before = my_profile.read_bytes()
    _fake_io(monkeypatch, ["n", "n", "n", "n"])   # 最后一问：不确认
    assert setup.main() == 0
    assert my_profile.read_bytes() == before


# ===== 验收 3：单模块启用 =====

def test_只启用微博不牵连其他(monkeypatch, my_profile):
    _fake_io(monkeypatch, ["n", "y", "", "n", "y"])
    #                      xhs 否 / weibo 是 / post_script 留空 / podcast 否 / 确认
    assert setup.main() == 0
    chans = _load(my_profile)["distribute"]["channels"]
    assert chans["weibo"]["enabled"] is True
    assert chans["xhs"]["enabled"] is False
    assert chans["podcast"]["enabled"] is False


def test_必填项缺失则该模块记为未启用(monkeypatch, my_profile):
    """小红书的 post_script 是必填，留空不能算启用——否则跑起来才发现缺。"""
    _fake_io(monkeypatch, ["y", "", "n", "n", "y"])
    assert setup.main() == 0
    chans = _load(my_profile)["distribute"]["channels"]
    assert chans["xhs"]["enabled"] is False


def test_填入的字段被写进_profile(monkeypatch, my_profile):
    _fake_io(monkeypatch, ["y", "/tmp/xhs-post.ts", "n", "n", "y"])
    assert setup.main() == 0
    xhs = _load(my_profile)["distribute"]["channels"]["xhs"]
    assert xhs["enabled"] is True
    assert xhs["post_script"] == "/tmp/xhs-post.ts"


# ===== 验收 4：重复运行 =====

def test_重复运行识别已配项(monkeypatch, my_profile):
    """第二次跑是「改配置」，默认值应等于当前状态，直接回车即保留。"""
    _fake_io(monkeypatch, ["y", "/tmp/a.ts", "n", "n", "y"])
    setup.main()

    # 让 setup 看到第一次写入的结果
    saved = _load(my_profile)["distribute"]["channels"]
    monkeypatch.setattr(setup.pc, "distribute_channel", lambda n: saved.get(n, {}))

    # 第二次全部直接回车（沿用默认）
    _fake_io(monkeypatch, ["", "", "", "", ""])
    assert setup.main() == 0
    after = _load(my_profile)["distribute"]["channels"]
    assert after["xhs"]["enabled"] is True             # 默认沿用「已启用」
    assert after["xhs"]["post_script"] == "/tmp/a.ts"  # 回车保留原值


# ===== 不破坏用户文件 =====

def test_没有ruamel时不写盘只打印片段(capsys, monkeypatch, my_profile):
    """🔴 PyYAML 重排会抹掉 profile 里的全部注释——那些往往是决策记录。
    宁可不写，也不能默默毁掉用户的文件。"""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def no_ruamel(name, *a, **k):
        if name.startswith("ruamel"):
            raise ImportError("simulated: no ruamel")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", no_ruamel)
    before = my_profile.read_bytes()
    _fake_io(monkeypatch, ["y", "/tmp/a.ts", "n", "n", "y"])
    setup.main()
    assert my_profile.read_bytes() == before          # 一个字节都没动
    out = capsys.readouterr().out
    assert "不写盘" in out and "ruamel" in out


def test_写入保留原有注释与其他段(monkeypatch, my_profile):
    pytest.importorskip("ruamel.yaml")
    _fake_io(monkeypatch, ["n", "n", "n", "y"])
    setup.main()
    text = my_profile.read_text(encoding="utf-8")
    assert "我的注释，必须活下来" in text
    assert "我的专栏" in text
