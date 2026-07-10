#!/usr/bin/env python3
"""
🗜️ 图片压缩工具（PIL 实现，中文路径友好）
========================================================
替代 baoyu-compress-image 在 Windows + 中文路径下的 ImageMagick `convert` 崩溃问题
。

策略：
  1. ≤ target_max_mb 的文件 → 仅 optimize=True 重写（轻量瘦身，体积通常省 15-30%）
  2. > target_max_mb 的文件 → 等比缩长边到 1024px（1K 横切规范）+ optimize=True
  3. 内置跳过清单：hero.png / bgm_cover.png / music_cover.png（组件小图，无需压缩）

用法：
  python compress_images.py 素材/             # 压缩目录下所有 PNG
  python compress_images.py 素材/cover.png    # 压缩单个文件
  python compress_images.py 素材/ --max-mb 2  # 自定义阈值

集成位置：autopilot.md 第八步 b。
"""

import argparse
import os
import sys
from pathlib import Path

# Windows GBK 控制台/管道下 print 中文会 UnicodeEncodeError，强制 UTF-8
# （与 prep_writing.py / learn_edits.py / regression_baseline.py 同源防护）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow 未安装。请：pip install Pillow", file=sys.stderr)
    sys.exit(1)


# 跟 add_logo.js 内置跳过清单保持一致（layout.md "Logo 水印例外" 同源）
SKIP_NAMES = {"hero.png", "bgm_cover.png", "music_cover.png"}

# 1K 横切规范长边（image-routing.md "1K 分辨率横切规范"）
TARGET_LONG_EDGE = 1024


def compress_one(path: Path, target_max_mb: float, verbose: bool = True) -> tuple[float, float, str]:
    """压缩单个 PNG，返回 (原大小 MB, 压缩后 MB, 状态)"""
    if path.suffix.lower() != ".png":
        return (0, 0, "SKIP_NOT_PNG")
    if path.name in SKIP_NAMES:
        size_mb = path.stat().st_size / 1024 / 1024
        if verbose:
            print(f"SKIP  {path.name:30s} ({size_mb:.2f}MB) -- 组件小图跳过清单")
        return (size_mb, size_mb, "SKIP_COMPONENT")

    orig_mb = path.stat().st_size / 1024 / 1024
    try:
        img = Image.open(path)
    except Exception as e:
        if verbose:
            print(f"FAIL  {path.name:30s} 无法读取：{e}")
        return (orig_mb, orig_mb, f"FAIL_READ:{e}")

    w, h = img.size
    long_side = max(w, h)
    resized = False

    if orig_mb > target_max_mb and long_side > TARGET_LONG_EDGE:
        scale = TARGET_LONG_EDGE / long_side
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        resized = True

    try:
        img.save(path, "PNG", optimize=True)
    except Exception as e:
        if verbose:
            print(f"FAIL  {path.name:30s} 写入失败：{e}")
        return (orig_mb, orig_mb, f"FAIL_WRITE:{e}")

    new_mb = path.stat().st_size / 1024 / 1024
    tag = "RESIZE" if resized else "OPT   "
    if verbose:
        action = f"{tag} {path.name:30s} {orig_mb:.2f}MB -> {new_mb:.2f}MB ({(1-new_mb/orig_mb)*100:.0f}% saved)"
        print(action)
    return (orig_mb, new_mb, tag.strip())


def main():
    parser = argparse.ArgumentParser(
        description="图片压缩（PIL 实现，中文路径友好）"
    )
    parser.add_argument("input", help="文件或目录路径")
    parser.add_argument(
        "--max-mb",
        type=float,
        default=2.0,
        help="目标最大体积（MB），超过则缩长边到 1K（默认 2.0）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，仅输出总结",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: 路径不存在 {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.is_file():
        targets = [input_path]
    else:
        targets = sorted(input_path.glob("*.png"))

    if not targets:
        print(f"WARN: {input_path} 下无 PNG 文件")
        sys.exit(0)

    verbose = not args.quiet
    total_orig = 0.0
    total_new = 0.0
    skipped = 0
    processed = 0

    for p in targets:
        orig, new, status = compress_one(p, args.max_mb, verbose=verbose)
        total_orig += orig
        total_new += new
        if status.startswith("SKIP"):
            skipped += 1
        elif status in ("OPT", "RESIZE"):
            processed += 1

    print()
    print(
        f"Done: {processed} 张压缩 / {skipped} 张跳过，"
        f"总大小 {total_orig:.2f}MB -> {total_new:.2f}MB "
        f"({(1 - total_new/total_orig)*100 if total_orig > 0 else 0:.0f}% saved)"
    )


if __name__ == "__main__":
    main()
