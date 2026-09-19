#!/usr/bin/env python3
"""只读扫描 polish 软/硬门命中。不写盘、不改定稿。

用法：
    python scripts/scan_polish_signals.py
    python scripts/scan_polish_signals.py --dir 文稿成品
    python scripts/scan_polish_signals.py --dir path/to/一篇文章

对每篇定稿.md 跑 verify_anti_ai_blacklist，打印 hard/soft 计数与最多 20 条抽样。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from contracts import verify_anti_ai_blacklist  # noqa: E402


def _find_finals(root: Path) -> list[Path]:
    if (root / "定稿.md").is_file():
        return [root / "定稿.md"]
    return sorted(root.rglob("定稿.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description="只读扫描 polish 软/硬门命中")
    parser.add_argument(
        "--dir",
        default="文稿成品",
        help="文章根目录或文稿成品/（默认：文稿成品）",
    )
    parser.add_argument("--sample", type=int, default=20, help="抽样条数上限")
    args = parser.parse_args()
    root = Path(args.dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    if not root.exists():
        print(f"路径不存在：{root}", file=sys.stderr)
        return 2

    finals = _find_finals(root)
    if not finals:
        print(f"未找到 定稿.md：{root}")
        return 0

    hard_n = soft_n = 0
    samples: list[str] = []
    per_file = []
    for path in finals:
        r = verify_anti_ai_blacklist(str(path))
        hard_n += r.get("hard_hits") or 0
        soft_n += r.get("soft_hits") or 0
        rel = path
        try:
            rel = path.relative_to(root)
        except ValueError:
            pass
        per_file.append((str(rel), r.get("hard_hits") or 0, r.get("soft_hits") or 0))
        for item in (r.get("errors") or []) + (r.get("warnings") or []):
            if len(samples) < args.sample:
                samples.append(f"{rel}  {item}")

    print(f"扫描 {len(finals)} 篇定稿  hard={hard_n}  soft={soft_n}")
    print("—— 按篇 ——")
    for rel, h, s in per_file:
        if h or s:
            print(f"  {rel}  hard={h}  soft={s}")
    print(f"—— 抽样 {len(samples)}/{args.sample} ——")
    for line in samples:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
