"""Baoyu 视觉能力的**可验证**依赖锚点。

背景（2026-08-02 复核结论）
---------------------------
在此之前，`producer_chain` 里的 `baoyu-infographic` / `baoyu-article-illustrator`
是代码无条件写进去的字符串常量，而校验方又只检查"这个字符串在不在"——
写入方与校验方是同一处代码，**这道门永远通过**，无法证明真的经过了 Baoyu 方法论。

更根本的是：这几个 Baoyu 视觉能力只有 `SKILL.md` + `references/`，没有可执行脚本，
它们是给模型读的方法论文档，不存在可被记录的"调用事件"。所以靠"记录调用"无解。

本模块换一个可验证对象：**锚定产物特征与文档字节**。

- `layout_type` 必须取自 Baoyu `baoyu-infographic` 的 Layout Gallery 枚举（21 种），
  枚举从磁盘上的 SKILL.md **实时解析**，不在本仓硬编码；
- 同时记录被解析文档的 `sha256`，写进 render batch 与 receipt；
- 校验侧重新解析并比对 sha256。

于是形成真实依赖：Baoyu 能力缺失 / 被换版本 / layout 写了枚举外的值，
都会在编译期或发布期硬失败，而不是靠一个自说自话的字符串放行。
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

INFOGRAPHIC_SKILL = "baoyu-infographic"
ARTICLE_SKILL = "baoyu-article-illustrator"


class BaoyuContractError(RuntimeError):
    """Baoyu 依赖缺失或不可解析——属于硬失败，不允许降级放行。"""


#: 测试与离线环境用：指向一个包含 baoyu-* 子目录的根，优先于真实查找顺序。
#: 公开仓 CI 没有 Baoyu 能力，靠它注入最小 fixture；生产环境不要设置。
SKILL_ROOT_ENV = "SANSHENG_WRITE_BAOYU_SKILL_ROOT"


def _search_roots() -> list[Path]:
    """与 render_visuals._candidate_renderer_dirs 保持同一优先级：

    四端共享入口优先，插件缓存只作末级兼容回退（缓存不进 git、易随插件升级漂移）。
    """
    roots: list[Path] = []
    override = os.environ.get(SKILL_ROOT_ENV, "").strip()
    if override:
        roots.append(Path(override))
    home = Path.home()
    roots.extend(
        [
            home / ".codex" / "skills",
            home / ".claude" / "skills",
            home / ".gemini" / "config" / "skills",
            home / "Cowork" / "skills",
        ]
    )
    return roots


def _cache_globs(name: str) -> list[str]:
    return [
        f".codex/plugins/cache/baoyu-skills/**/skills/{name}",
        f".claude/plugins/cache/baoyu-skills/**/skills/{name}",
    ]


def resolve_skill_dir(name: str) -> Path:
    """定位 Baoyu 能力目录；找不到即硬失败。"""
    for root in _search_roots():
        candidate = root / name
        if (candidate / "SKILL.md").is_file():
            return candidate
    home = Path.home()
    for pattern in _cache_globs(name):
        for candidate in sorted(home.glob(pattern)):
            if (candidate / "SKILL.md").is_file():
                return candidate
    raise BaoyuContractError(
        f"未找到 Baoyu 能力 {name}：视觉链要求它真实可读。"
        f"请确认它已进入共享真源（如 ~/Cowork/skills/{name}）并完成四端接线。"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_LAYOUT_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|", re.MULTILINE)


def infographic_layout_gallery() -> tuple[frozenset[str], str]:
    """解析 baoyu-infographic 的 Layout Gallery 枚举。

    :return: (合法 layout_type 集合, SKILL.md 的 sha256)
    """
    skill_md = resolve_skill_dir(INFOGRAPHIC_SKILL) / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    # 标题实际写法是 `## Layout Gallery (21)`，括号里的计数是 Baoyu 文档自带的自校验锚。
    heading = re.search(
        r"^##\s+Layout Gallery(?:\s*\((\d+)\))?\s*$", text, re.MULTILINE
    )
    if not heading:
        raise BaoyuContractError(
            f"{skill_md} 里找不到 `## Layout Gallery` 段落——"
            "Baoyu 文档结构可能已变更，需同步本契约的解析规则。"
        )
    tail = text[heading.end():]
    body = re.split(r"^##\s+", tail, maxsplit=1, flags=re.MULTILINE)[0]
    layouts = frozenset(_LAYOUT_ROW.findall(body))
    declared = int(heading.group(1)) if heading.group(1) else 0
    if declared and len(layouts) != declared:
        raise BaoyuContractError(
            f"{skill_md} 标题声明 {declared} 个 layout，实际解析出 {len(layouts)} 个——"
            "解析规则与 Baoyu 文档结构脱节，拒绝以不完整枚举放行。"
        )
    if len(layouts) < 10:
        raise BaoyuContractError(
            f"从 {skill_md} 只解析出 {len(layouts)} 个 layout，明显偏少，"
            "疑似解析规则与文档结构脱节，拒绝以不完整枚举放行。"
        )
    return layouts, _sha256(skill_md)


def article_illustrator_digest() -> str:
    """Hero / 叙事插图侧的锚点：article-illustrator 的 SKILL.md 字节摘要。"""
    return _sha256(resolve_skill_dir(ARTICLE_SKILL) / "SKILL.md")


def build_anchors() -> dict[str, str]:
    """生成写进 render batch / receipt 的 Baoyu 依赖锚点。"""
    layouts, infographic_sha = infographic_layout_gallery()
    return {
        "baoyu_infographic_sha256": infographic_sha,
        "baoyu_infographic_layout_count": str(len(layouts)),
        "baoyu_article_illustrator_sha256": article_illustrator_digest(),
    }


def verify_anchors(recorded: dict[str, object]) -> list[str]:
    """校验侧：重新解析当前磁盘上的 Baoyu 文档并与记录比对。

    :param recorded: receipt / batch 里记录的锚点字典
    :return: 错误列表（空表示通过）
    """
    errors: list[str] = []
    try:
        current = build_anchors()
    except BaoyuContractError as exc:
        return [str(exc)]

    for key in ("baoyu_infographic_sha256", "baoyu_article_illustrator_sha256"):
        want = current[key]
        got = str(recorded.get(key) or "").strip()
        if not got:
            errors.append(
                f"缺 {key}：无法证明视觉链真的经过了 Baoyu 方法论"
                "（旧版只记 producer_chain 字符串，属于自说自话，已废止）"
            )
        elif got != want:
            errors.append(
                f"{key} 不一致：记录={got[:12]}… 当前={want[:12]}…；"
                "Baoyu 能力已变更，需重新编译视觉任务单后再发布"
            )
    return errors


def validate_layout_types(layout_types: list[str]) -> list[str]:
    """校验 visual-plan 里的 layout_type 全部取自 Baoyu Layout Gallery。"""
    try:
        gallery, _ = infographic_layout_gallery()
    except BaoyuContractError as exc:
        return [str(exc)]
    errors = []
    for value in layout_types:
        if value not in gallery:
            errors.append(
                f"layout_type={value!r} 不在 baoyu-infographic 的 Layout Gallery 内；"
                f"合法值共 {len(gallery)} 个，例如："
                f"{', '.join(sorted(gallery)[:6])} …"
            )
    return errors
