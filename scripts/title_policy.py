"""Category-prefix policy, including evidence-bound exact author titles.

This verifies a recorded instruction, not the identity of its author. The caller
must quote the actual conversation; ordinary draft approval remains independent.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def title_prefix_errors(title: str, outward_category: str = "", *,
                        title_policy=None, article_dir=None) -> list[str]:
    try:
        from .works_registry import OUTWARD_CATEGORIES
    except ImportError:
        from works_registry import OUTWARD_CATEGORIES

    title = str(title or "").strip()
    if title_policy is not None:
        if not isinstance(title_policy, dict) or title_policy.get("mode") != "author-exact":
            return ["title_policy 必须是 mode: author-exact 的证据对象"]
        required = ("exact_title", "author_words", "evidence_file", "evidence_sha256")
        if any(not isinstance(title_policy.get(key), str) or not title_policy[key].strip()
               for key in required):
            return ["title_policy 缺非空 exact_title / author_words / evidence_file / evidence_sha256"]
        if not title or title_policy["exact_title"] != title:
            return ["title_policy.exact_title 与当前 title 不一致；旧标题证据失效"]
        words = title_policy["author_words"]
        if title not in words or "\n" in words or "\r" in words:
            return ["title_policy.author_words 必须逐字含完整标题，且为一行作者原话"]
        if article_dir is None:
            return ["title_policy 缺文章目录，无法验证作者原话证据"]
        root = Path(article_dir).resolve()
        rel = Path(title_policy["evidence_file"])
        path = (root / rel).resolve()
        if rel.is_absolute() or not path.is_relative_to(root):
            return ["title_policy.evidence_file 必须位于文章目录内，使用相对路径"]
        try:
            evidence = path.read_bytes()
            text = evidence.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            return [f"title_policy 作者原话证据不可读：{exc}"]
        if hashlib.sha256(evidence).hexdigest() != title_policy["evidence_sha256"]:
            return ["title_policy 作者原话证据 SHA256 已变化，旧证据失效"]
        if f"作者原话：{words}" not in text.splitlines():
            return ["title_policy 证据须有与 author_words 逐字一致的 作者原话： 行"]
        return []

    prefixes = ([f"{OUTWARD_CATEGORIES[outward_category]} | "]
                if outward_category in OUTWARD_CATEGORIES
                else [f"{tag} | " for tag in OUTWARD_CATEGORIES.values()])
    if any(title.startswith(prefix) for prefix in prefixes):
        return []
    expected = prefixes[0] if len(prefixes) == 1 else "标签 | "
    return [f"标题缺分类标签前缀（应为 {expected}）；作者指定原题须提供有效 title_policy 证据"]
