#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profile_config.py -- 三层分离的解析层（本 skill 所有"私有值"的唯一入口）。

三层：
  ① skill 本体（本仓）      -- 方法论 + 引擎，不含任何私有内容
  ② profile 覆盖层（你的）  -- 品牌 token / 身份卡 / 人设 / 语料指针，**私有但非密**
  ③ secrets（.env）        -- API key，**只从 env 读，永不进仓、永不 print**

解析优先级（profile）：
  1. 环境变量 SANSHENG_WRITE_PROFILE_DIR 指向的目录 -- 有则用你的真值
  2. 回退仓内 profile.example/ -- 中性默认值，开箱即用（**这是正常路径，不是错误**）

解析优先级（数据目录，存放你的文章与作品库）：
  1. 环境变量 SANSHENG_WRITE_DATA_DIR
  2. 回退 <仓根>/data/

单键缺失时用 profile.example 的同名键兜底，不崩；整个目录指错才明确报错。
密钥永远不进 profile —— 那是 .env 的事（见 load_secret）。

用法：
    from profile_config import brand, profile_dir, data_dir, load_secret
    green = brand()["colors"]["primary"]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - 依赖缺失时给出可操作提示
    yaml = None

SKILL_DIR = Path(__file__).resolve().parent.parent
EXAMPLE_PROFILE = SKILL_DIR / "profile.example"

ENV_PROFILE = "SANSHENG_WRITE_PROFILE_DIR"
ENV_DATA = "SANSHENG_WRITE_DATA_DIR"

_cache: dict[str, Any] = {}


# ===== 【第 1 节】目录解析 =====

def profile_dir() -> Path:
    """返回生效的 profile 目录。未配置 env 时回退 profile.example（正常路径）。"""
    p = os.environ.get(ENV_PROFILE, "").strip()
    if p:
        d = Path(p).expanduser()
        if not d.is_dir():
            sys.exit(
                f"[profile] {ENV_PROFILE} 指向的目录不存在：{d}\n"
                f"          请修正该环境变量，或直接删掉它以回退到 {EXAMPLE_PROFILE.name}/"
            )
        return d
    return EXAMPLE_PROFILE


def using_example_profile() -> bool:
    """当前是否跑在示例 profile 上（产出物里会带示例品牌名，汇报时应提示一句）。"""
    return profile_dir() == EXAMPLE_PROFILE


def data_dir() -> Path:
    """文章与作品库所在目录。缺省 <仓根>/data/，首次使用自动创建。"""
    p = os.environ.get(ENV_DATA, "").strip()
    d = Path(p).expanduser() if p else SKILL_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def works_file() -> Path:
    """作品库（单一数据源）。"""
    return data_dir() / "works.yaml"


# ===== 【第 2 节】品牌 token（E-1：一处改完，全局换皮） =====

def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    if yaml is None:
        sys.exit("[profile] 需要 PyYAML：pip install pyyaml")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """override 覆盖 base；单键缺失自动用 base 兜底（不崩）。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def brand() -> dict:
    """品牌 token（颜色 / 圆角 / 署名 / 身份卡）。

    读取顺序：profile.example/brand.yaml（兜底基线）← 你的 profile/brand.yaml（覆盖）
    若 profile 里指定了 theme: <name>，再叠加 profile/themes/<name>.yaml。
    """
    if "brand" in _cache:
        return _cache["brand"]

    base = _read_yaml(EXAMPLE_PROFILE / "brand.yaml")
    pd = profile_dir()
    merged = base if pd == EXAMPLE_PROFILE else _deep_merge(base, _read_yaml(pd / "brand.yaml"))

    theme = (merged.get("theme") or "").strip()
    if theme:
        for cand in (pd / "themes" / f"{theme}.yaml", EXAMPLE_PROFILE / "themes" / f"{theme}.yaml"):
            if cand.is_file():
                merged = _deep_merge(merged, _read_yaml(cand))
                break
        else:
            print(f"[profile] ⚠ 主题 {theme!r} 未找到，沿用默认配色", file=sys.stderr)

    _cache["brand"] = merged
    return merged


def colors() -> dict:
    return brand().get("colors", {})


def identity() -> dict:
    """公众号/站点身份卡。示例 profile 里全是明显假值，**必须改成你自己的**。"""
    return brand().get("identity", {})


# ===== 【第 3 节】语料指针（BYO：自带语料才长出你的风格） =====

def corpus_dir() -> Path:
    return profile_dir() / "corpus"


def authors_dir() -> Path:
    """作者风格手册目录。公开仓只带一套虚构示例，请自建你要模仿的作者手册。"""
    return corpus_dir() / "authors"


def author_compact(name: str) -> Path | None:
    p = authors_dir() / f"{name}.compact.md"
    return p if p.is_file() else None


# ===== 【第 4 节】secrets（只从 env / .env 读，永不 print） =====

def _load_dotenv() -> dict:
    """只读本仓根目录的 .env。

    刻意不去读其他工具的 dotenv（如 ~/.xxx/.env）-- 偷读别人的配置目录
    是意外行为，也会让「我明明没配 key」的体检结果说谎。
    """
    if "dotenv" in _cache:
        return _cache["dotenv"]
    env: dict[str, str] = {}
    cand = SKILL_DIR / ".env"
    if cand.is_file():
        for line in cand.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    _cache["dotenv"] = env
    return env


def load_secret(name: str, *, required: bool = True, hint: str = "") -> str:
    """读密钥：shell env → 仓根 .env。

    读不到就明确报错并指路，**不静默降级、不硬编码兜底真值**。
    """
    val = os.environ.get(name, "").strip() or _load_dotenv().get(name, "").strip()
    if val:
        return val
    if not required:
        return ""
    tip = f"\n          {hint}" if hint else ""
    sys.exit(
        f"[secret] 缺少 {name}。\n"
        f"          请 cp .env.example .env 后填入，或 export {name}=...{tip}"
    )


def redact(text: str) -> str:
    """把可能出现在日志/报错里的 key 打码。"""
    import re
    text = re.sub(r"([?&]key=)[^&\s\"']+", r"\1***", text)
    text = re.sub(r"\b(AIza[0-9A-Za-z_-]{6})[0-9A-Za-z_-]+", r"\1***", text)
    text = re.sub(r"\b(AQ\.[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+", r"\1***", text)
    text = re.sub(r"\b(sk-[A-Za-z0-9]{6})[A-Za-z0-9]+", r"\1***", text)
    return text


def _reset_cache_for_tests() -> None:
    _cache.clear()


if __name__ == "__main__":
    print(f"profile   : {profile_dir()}{'  (示例，未配置 ' + ENV_PROFILE + ')' if using_example_profile() else ''}")
    print(f"data      : {data_dir()}")
    print(f"works     : {works_file()}")
    b = brand()
    print(f"brand     : {b.get('name')}  theme={b.get('theme') or '(default)'}")
    print(f"colors    : {colors()}")
    print(f"corpus    : {corpus_dir()}  authors={'有' if authors_dir().is_dir() else '无'}")
