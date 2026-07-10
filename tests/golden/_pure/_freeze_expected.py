# -*- coding: utf-8 -*-
"""一次性 freeze 脚本：以当前 (=main, P0 未改 format_layout.py) 实跑各纯变换函数，
把输出冻结为 <name>.expected.html，并写 MANIFEST.json。
仅在 fixture 首次建立 / 经评审确认行为变更时手动重跑。回归断言不调本脚本。"""
import importlib.util, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"
spec = importlib.util.spec_from_file_location("format_layout", SCRIPTS / "format_layout.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)

# 仅纳入已逐函数核验为「字符串入→字符串出、无文件IO、不依赖 cwd/article-meta、
# 不调外部工具」的确定性纯变换。process_lead/footer/wechat_compat 因含文件IO或
# cwd 依赖被剔除（见报告）。
CASES = [
    {"func": "process_colors",     "in": "process_colors.in.html"},
    {"func": "process_h2",         "in": "process_h2.in.html"},
    {"func": "process_table",      "in": "process_table.in.html"},
    {"func": "process_takeaway",   "in": "process_takeaway.in.html"},
    {"func": "process_highlights", "in": "process_highlights.in.html"},
]

manifest = []
for c in CASES:
    src = (HERE / c["in"]).read_text(encoding="utf-8")
    out = getattr(fl, c["func"])(src)
    exp_name = c["in"].replace(".in.html", ".expected.html")
    (HERE / exp_name).write_text(out, encoding="utf-8", newline="")
    manifest.append({"func": c["func"], "in": c["in"], "expected": exp_name})

(HERE / "MANIFEST.json").write_text(
    json.dumps({"pure_fixtures": manifest}, ensure_ascii=False, indent=1),
    encoding="utf-8", newline="",
)
print("frozen:", [m["func"] for m in manifest])
