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

路径配置支持 ``@workspace/...`` 占位符。流水线拿到文章目录后先调用
``bind_workspace(article_dir)``，占位符便会解析到**承载该文章的当前 Git
工作树**，而不是启动 Agent 时碰巧所在的主仓。

单键缺失时用 profile.example 的同名键兜底，不崩；整个目录指错才明确报错。
密钥永远不进 profile —— 那是 .env 的事（见 load_secret）。

用法：
    from profile_config import brand, profile_dir, data_dir, load_secret
    green = brand()["colors"]["primary"]
"""
from __future__ import annotations

import os
import sys
import copy
from pathlib import Path
from typing import Any, Callable

try:
    from .visual_contracts import signature_visual_profile
except ImportError:  # pragma: no cover - direct script execution
    from visual_contracts import signature_visual_profile

try:
    import yaml
except ImportError:  # pragma: no cover - 依赖缺失时给出可操作提示
    yaml = None

SKILL_DIR = Path(__file__).resolve().parent.parent
EXAMPLE_PROFILE = SKILL_DIR / "profile.example"

ENV_PROFILE = "SANSHENG_WRITE_PROFILE_DIR"
ENV_DATA = "SANSHENG_WRITE_DATA_DIR"
ENV_WORKS = "SANSHENG_WRITE_WORKS_FILE"
ENV_FLYWHEEL = "SANSHENG_WRITE_FLYWHEEL_DIR"
ENV_GOLDEN_LINES = "SANSHENG_WRITE_GOLDEN_LINES_FILE"
ENV_WORKSPACE = "SANSHENG_WRITE_WORKSPACE_DIR"
# 仅供当前 pipeline 及其子进程传播已经校验过的绑定；不从 .env 读取，也不作为
# 用户配置入口。ENV_WORKSPACE 负责“选哪棵树”，本键只负责“把选择传给子进程”。
ENV_ACTIVE_WORKSPACE = "SANSHENG_WRITE_ACTIVE_WORKSPACE"

_cache: dict[str, Any] = {}
_workspace: Path | None = None


# 历史上 pipeline 把 scripts/ 放进 sys.path 后按 ``profile_config`` 导入，pytest
# 和包式调用则按 ``scripts.profile_config`` 导入。两套名字若各加载一遍，会各有一份
# _workspace/_cache。尽早给当前实例登记别名；即使宿主已经先加载了两份实例，下面的
# active-workspace 同步仍会桥接它们的运行时状态。
_this_module = sys.modules[__name__]
if __name__ == "profile_config":
    sys.modules.setdefault("scripts.profile_config", _this_module)
elif __name__ == "scripts.profile_config":
    sys.modules.setdefault("profile_config", _this_module)


class WorkspaceBindingError(RuntimeError):
    """``@workspace`` 被使用但文章所在工作树尚未绑定。"""


def _nearest_git_root(start: Path) -> Path | None:
    """返回 ``start`` 所在的最近 Git 工作树根（兼容 .git 文件与目录）。"""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _validated_absolute_workspace(raw: str, *, setting: str) -> Path:
    """校验一个显式/继承的工作区根；相对路径不能随 cwd 漂移。"""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise WorkspaceBindingError(f"{setting} 必须是绝对路径：{raw!r}")
    root = candidate.resolve()
    if not root.is_dir():
        raise WorkspaceBindingError(f"{setting} 指向的目录不存在：{root}")
    return root


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _set_workspace(root: Path | None, *, propagate: bool) -> None:
    global _workspace
    if root != _workspace:
        _workspace = root
        _cache.clear()
    if propagate:
        if root is None:
            os.environ.pop(ENV_ACTIVE_WORKSPACE, None)
        else:
            os.environ[ENV_ACTIVE_WORKSPACE] = str(root)


def _sync_inherited_workspace() -> Path | None:
    """从父进程恢复已校验绑定，并同步可能并存的另一模块实例。"""
    raw = os.environ.get(ENV_ACTIVE_WORKSPACE, "").strip()
    if not raw:
        return _workspace
    root = _validated_absolute_workspace(raw, setting=ENV_ACTIVE_WORKSPACE)
    _set_workspace(root, propagate=False)
    return root


def bind_workspace(article_dir: str | os.PathLike[str]) -> Path | None:
    """把路径占位符绑定到承载 ``article_dir`` 的当前工作树。

    Git 仓内从文章目录向上找最近的 ``.git``；非 Git 数据目录可显式配置
    ``SANSHENG_WRITE_WORKSPACE_DIR``。找不到时不妄猜层级，绝对路径配置仍能
    正常使用，只有真正解析 ``@workspace`` 时才会给出可操作错误。

    重复绑定另一个工作树会清掉品牌等派生缓存，确保同一 Python 进程不把上
    一棵工作树的 profile 带进下一篇文章。
    """
    article = Path(article_dir).expanduser().resolve()
    explicit = _env_or_dotenv(ENV_WORKSPACE)
    if explicit:
        if explicit.lower().startswith("@workspace"):
            raise WorkspaceBindingError(
                f"{ENV_WORKSPACE} 不能引用自身 @workspace；请给绝对路径"
            )
        root = _validated_absolute_workspace(explicit, setting=ENV_WORKSPACE)
        if not _is_within(article, root):
            raise WorkspaceBindingError(
                f"{ENV_WORKSPACE} 必须包含当前文章目录：{article}；当前配置为 {root}"
            )
    else:
        root = _nearest_git_root(article)
    _set_workspace(root, propagate=True)
    return root


def workspace_root() -> Path | None:
    """返回当前已绑定工作树；未绑定或文章不在 Git 工作树时返回 ``None``。"""
    return _sync_inherited_workspace()


def resolve_config_path(value: str, *, setting: str = "路径配置") -> Path:
    """解析普通路径或 ``@workspace/...``，并拒绝 ``..`` 逃出工作树。"""
    raw = str(value or "").strip()
    is_workspace = raw == "@workspace" or raw.startswith(("@workspace/", "@workspace\\"))
    if raw.lower().startswith("@workspace") and not is_workspace:
        raise WorkspaceBindingError(
            f"{setting} 的 @workspace 占位符格式非法：{raw!r}；"
            "只允许 @workspace 或 @workspace/<相对路径>"
        )
    if not is_workspace:
        return Path(raw).expanduser()
    root = _sync_inherited_workspace()
    if root is None:
        raise WorkspaceBindingError(
            f"{setting} 使用了 {raw!r}，但尚未绑定文章工作树；"
            "请在文章目录确定后先调用 profile_config.bind_workspace(article_dir)"
        )
    suffix = raw[len("@workspace"):]
    if suffix:
        # 上面的合法性判断已保证第一字符是分隔符；只移除这一字符，保留后续
        # anchor/drive 供检查，避免 ``@workspace/C:/...`` 或 UNC 被悄悄重解释。
        suffix = suffix[1:]
    suffix_path = Path(suffix)
    if suffix_path.anchor:
        raise WorkspaceBindingError(
            f"{setting} 的 @workspace 后只能接相对路径：{raw!r}"
        )
    parts = [part for part in suffix.replace("\\", "/").split("/") if part]
    resolved = root.joinpath(*parts).resolve()
    if not _is_within(resolved, root):
        raise WorkspaceBindingError(
            f"{setting} 不能逃出当前工作树：{raw!r} → {resolved}"
        )
    return resolved


class DynamicPath(os.PathLike[str]):
    """兼容旧常量 API、但每次使用都重新求值的 PathLike 代理。

    ``WORKS_FILE`` 等公开名字曾是导入时冻结的 ``Path``。保留这些名字能避免
    破坏调用方，同时 ``Path(proxy)``、``open(proxy)``、``proxy.write_text()``
    都会读取当前 workspace 的真实路径。
    """

    def __init__(self, resolver: Callable[[], Path]):
        self._resolver = resolver

    def current(self) -> Path:
        return Path(self._resolver())

    def __fspath__(self) -> str:
        return os.fspath(self.current())

    def __str__(self) -> str:
        return str(self.current())

    def __repr__(self) -> str:
        return f"DynamicPath({self.current()!r})"

    def __getattr__(self, name: str) -> Any:
        return getattr(self.current(), name)

    def __truediv__(self, other: str | os.PathLike[str]) -> Path:
        return self.current() / other

    def __eq__(self, other: object) -> bool:
        try:
            return self.current() == Path(other)  # type: ignore[arg-type]
        except TypeError:
            return False


def dynamic_path(resolver: Callable[[], Path]) -> DynamicPath:
    """创建一个延迟求值的 PathLike；供兼容既有模块级路径名使用。"""
    return DynamicPath(resolver)


def _env_or_dotenv(name: str) -> str:
    """os 环境变量优先，其次 clone 根 .env。

    让**一个** .env 同时配 profile/data 指针与密钥（与 load_secret 同源），
    家里电脑复刻只需拷一份 .env，不必再另设系统级环境变量。
    """
    return os.environ.get(name, "").strip() or _load_dotenv().get(name, "").strip()


# ===== 【第 1 节】目录解析 =====

def profile_dir() -> Path:
    """返回生效的 profile 目录。未配置 env 时回退 profile.example（正常路径）。"""
    p = _env_or_dotenv(ENV_PROFILE)
    if p:
        d = resolve_config_path(p, setting=ENV_PROFILE)
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
    p = _env_or_dotenv(ENV_DATA)
    d = resolve_config_path(p, setting=ENV_DATA) if p else SKILL_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def works_file() -> Path:
    """作品库（单一数据源）。

    可用 SANSHENG_WRITE_WORKS_FILE 直指一个已存在的 yaml（比如你的作品库
    本来就叫别的名字）——比「另起硬链/软链对齐文件名」可靠：链接会被
    另一侧仓库的 git pull/checkout 替换文件时静默摘断，而 env 直指没有中间层。
    未配置则默认 <数据目录>/works.yaml。
    """
    p = _env_or_dotenv(ENV_WORKS)
    if p:
        return resolve_config_path(p, setting=ENV_WORKS)
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


def visual_profile(name: str = "") -> dict:
    """返回已解析的视觉配方。

    ``warm-light-clay`` 是产品签名视觉，由本仓 ``visual_contracts.py`` 固化，
    私有 profile 不得覆盖；否则账号主题色会静默改变黏土图的色调。其余配方仍可
    由 profile 提供。调用方会对返回值做稳定摘要并写进 canonical prompt 与日志。
    """
    visual = brand().get("visual") or {}
    selected = str(name or visual.get("default_profile") or "").strip()
    signature = signature_visual_profile(selected)
    if signature:
        signature["name"] = selected
        return signature
    profiles = visual.get("profiles") or {}
    raw = profiles.get(selected)
    if not selected or not isinstance(raw, dict):
        return {}
    recipe = copy.deepcopy(raw)
    if recipe.get("accent") == "brand-primary":
        recipe["accent"] = str(colors().get("primary") or "").upper()
    recipe["name"] = selected
    return recipe


def identity() -> dict:
    """公众号/站点身份卡。示例 profile 里全是明显假值，**必须改成你自己的**。"""
    return brand().get("identity", {})


def distribute_config() -> dict:
    """一稿多投的渠道配置（brand.yaml `distribute:`）。

    渠道账号、播客 feed 主机、节目 ID 这些都是**私有但非密**的值，跟品牌 token
    同层，所以放 profile 而不是 .env；公开仓的 profile.example 只留占位。
    未配置返回空字典 —— 由 distribute.py 解释成「所有渠道未启用」，而不是硬跑默认值。
    """
    return brand().get("distribute") or {}


def distribute_channel(name: str) -> dict:
    """单个渠道的配置。未声明 = 未启用（不做「缺键兜底成 enabled」的危险默认）。"""
    return (distribute_config().get("channels") or {}).get(name) or {}


def workflow_checkpoints() -> list:
    """profile 启用的人工检查点闸门（brand.yaml `workflow.checkpoints`）。

    合法值：
      - "blueprint"：大纲 + 5 标题候选 + 开头候选一包交付后硬停，等作者拍板
      - "draft"：定稿（磨稿 + 外审修复后）硬停，等作者审读
    未配置 = 全自动（唯一停顿 = 开头盲选，原默认行为不变）。
    """
    wf = brand().get("workflow") or {}
    cps = wf.get("checkpoints") or []
    if isinstance(cps, str):
        cps = [c.strip() for c in cps.split(",")]
    return [c for c in cps if c in ("blueprint", "draft")]


# ===== 【第 2.5 节】学习飞轮状态（playbook / lessons / observations） =====
#
# 飞轮文件是「越用越像你」攒出来的**个人数据**，不该写进公开仓的 git 跟踪文件里
# （公开仓只带空壳模板）。解析顺序：
#   1. SANSHENG_WRITE_FLYWHEEL_DIR 显式指定
#   2. 配置了自己的 profile → <profile>/flywheel/（个人数据跟着 profile 走，随你的
#      私有仓版本化备份——放仓根的话既无备份、又会被 git 操作误伤）
#   3. 未配置 profile（试用/开发态）→ 仓根（向后兼容，空壳文件就在那里）

def flywheel_dir() -> Path:
    p = _env_or_dotenv(ENV_FLYWHEEL)
    if p:
        d = resolve_config_path(p, setting=ENV_FLYWHEEL)
    elif not using_example_profile():
        d = profile_dir() / "flywheel"
    else:
        return SKILL_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def playbook_file() -> Path:
    """learn_edits 编译产物：带置信度的个性化写作规则（写作 Step 4 注入）。"""
    return flywheel_dir() / "playbook.md"


def lessons_file() -> Path:
    """learn_edits 原始 pattern 记录。"""
    return flywheel_dir() / "lessons.yaml"


def observations_file() -> Path:
    """运行观察日志（本地自省遥测）。"""
    return flywheel_dir() / "_skill-observations.jsonl"


# ===== 【第 3 节】语料指针（BYO：自带语料才长出你的风格） =====

def corpus_dir() -> Path:
    return profile_dir() / "corpus"


def golden_lines_file() -> Path:
    """金句库文件。

    默认使用 ``<profile>/corpus/golden-lines.md``；已有个人金句库位于别处时，
    用 SANSHENG_WRITE_GOLDEN_LINES_FILE 直指真源，避免复制出第二份库。
    """
    p = _env_or_dotenv(ENV_GOLDEN_LINES)
    if p:
        return resolve_config_path(p, setting=ENV_GOLDEN_LINES)
    return corpus_dir() / "golden-lines.md"


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
    global _workspace
    _cache.clear()
    _workspace = None
    os.environ.pop(ENV_ACTIVE_WORKSPACE, None)


if __name__ == "__main__":
    bind_workspace(Path.cwd())
    print(f"profile   : {profile_dir()}{'  (示例，未配置 ' + ENV_PROFILE + ')' if using_example_profile() else ''}")
    print(f"data      : {data_dir()}")
    print(f"works     : {works_file()}")
    print(f"golden    : {golden_lines_file()}")
    print(f"flywheel  : {flywheel_dir()}  (playbook / lessons / observations)")
    b = brand()
    print(f"brand     : {b.get('name')}  theme={b.get('theme') or '(default)'}")
    print(f"colors    : {colors()}")
    print(f"corpus    : {corpus_dir()}  authors={'有' if authors_dir().is_dir() else '无'}")
