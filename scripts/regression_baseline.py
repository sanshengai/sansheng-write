# scripts/regression_baseline.py
"""黄金文章回归基线。用法: python regression_baseline.py <phase> [slug]
断言：① 铁律0违规(format_layout.py --check) ② schema ③ diff 阈值。

P0 = 零行为变更门（hermetic）：
  (a) 纯变换 fixture —— 按 tests/golden/_pure/MANIFEST.json 逐个 import
      format_layout 的纯函数，输入 <name>.in.html，与冻结的
      <name>.expected.html 做 diff_lines==0 布尔比较。expected 是当前
      (=main) 行为的冻结快照，未来 format_layout.py 漂移即被检出。
  (b) 脚本 git 守卫 —— P0 期 scripts/format_layout.py 必须对 main 零 diff。
"""
# 行尾规整：diff_lines 刻意用 str.splitlines()（按行切、丢弃行终止符），
# 故 CRLF vs LF 不产生伪差异（Windows autocrlf 下 baseline 多为 CRLF、
# 新产物可能 LF，原始字节比较会全篇伪报）。此为有意设计，勿改为字节比较。
import json, subprocess, sys, pathlib, difflib, os, importlib.util, tempfile

# === Critical 1：UTF-8 stdout/stderr 健壮防护 ===
# _run_p0 进程内 import format_layout 并调其函数，函数内 log() 打 emoji。
# 默认 Windows 控制台是 GBK，写 emoji 抛 UnicodeEncodeError → 整条门
# traceback exit 1（与是否漂移无关，false failure）。故在任何逻辑前
# 强制 UTF-8，确保裸跑（不带 set PYTHONIOENCODING）也不崩。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SW = pathlib.Path(__file__).resolve().parents[1]

# P0-P6 门必须确定性地跑在 profile.example 上（冻结 fixture 断言的是中性默认色，
# 如 #2F6F8F / #d7e3ea），且绝不受维护者本机 .env（SANSHENG_WRITE_* 指向真实品牌
# profile / 真实数据目录）影响。os.environ 优先级高于 .env，故在 import format_layout
# 之前显式钉死；data 也指到临时目录，多一道保险不碰真实作品库。
os.environ["SANSHENG_WRITE_PROFILE_DIR"] = str(SW / "profile.example")
# 硬钉（不用 setdefault——外部预设的 env 同样会打破确定性，SEP-08）；
# 同族指针必须钉非空实路径：空串挡不住解析器回落 .env
_P0_DATA = tempfile.mkdtemp(prefix="sansheng-write-p0-")
os.environ["SANSHENG_WRITE_DATA_DIR"] = _P0_DATA
os.environ["SANSHENG_WRITE_WORKS_FILE"] = str(pathlib.Path(_P0_DATA) / "works.yaml")
os.environ["SANSHENG_WRITE_FLYWHEEL_DIR"] = _P0_DATA

# 冻结 golden 文章清单锚点（3 篇基线）。P6.1 起 P6 门改走结构等价
# 三断言、不再重跑 golden 比字节，故此常量当前不被 main() 直接消费；
# 保留为 golden 目录的可发现入口（人审/未来扩展按 P6-acceptance-
# checklist.md 真跑时定位 3 篇基线用）。
GOLDEN = SW/"tests"/"golden"/"manifest.json"
PURE_DIR = SW/"tests"/"golden"/"_pure"

VALID_PHASES = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")

# 回归基线对比基准 ref。P0 设计意图是「format_layout.py 对基准零 diff」，默认
# main；在 feature 分支上 format_layout.py 对 main 必然有 diff（重构本身即改动），
# 此时设环境变量 REGRESSION_BASE_REF 指向分支起点（如 `git merge-base main HEAD`
# 的 SHA），P0–P5 门即可在分支上跑出有意义结果，而非恒报 scripts_git_dirty。
BASE_REF = os.environ.get("REGRESSION_BASE_REF", "main")

def _para_count(md: str) -> int:
    return len([b for b in md.split("\n\n") if b.strip()])

def diff_lines(a: str, b: str) -> int:
    # 返回值仅作布尔判据用：==0 表示「逐行一致」，>0 表示「存在差异」。
    # ⚠️ 返回值【不是】差异行数：unified_diff 对单行修改计 +/- 各 1（×2），
    #    对乱序会爆炸式放大，不具规模语义。严禁拿它当行数设非 0 阈值
    #    （P0.3 复审硬约束）。判据一律写成 `diff_lines(...) == 0`。
    return sum(1 for d in difflib.unified_diff(a.splitlines(), b.splitlines())
               if d[:1] in "+-" and d[:3] not in ("+++", "---"))

def check_iron_rules(workdir: pathlib.Path) -> bool:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        # encoding/errors 仅为解码健壮性：Windows 默认 locale=GBK，子进程
        # 若打非 GBK 字节（emoji/中文），text=True 隐式 GBK decode 抛
        # UnicodeDecodeError warning。显式 utf-8 + replace 消除该技术债。
        # ⚠️ 仅改解码参数；判定逻辑（returncode==0）一字不动。
        r = subprocess.run([sys.executable, str(SW/"scripts"/"format_layout.py"), "--check"],
                            cwd=workdir, capture_output=True, text=True, env=env,
                            encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        # 超时判失败比挂死整条回归门好
        return False
    return r.returncode == 0

def _load_format_layout():
    """以隔离方式 import scripts/format_layout.py（不触发其 main()）。
    加载失败（ImportError/SyntaxError 等）由调用方转结构化 harness_error。"""
    spec = importlib.util.spec_from_file_location(
        "format_layout", SW/"scripts"/"format_layout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _git_guard(rel_path: str) -> str:
    """git 守卫三态：'clean' / 'dirty' / 'unavailable'。
    `git diff --quiet <ref>` 在 ref 缺失时返回 128，不能与 dirty(1) 混判；
    故先 rev-parse 探测 main ref；ref 不存在或 git 不可用 → 'unavailable'
    （由调用方计 harness_error，绝不伪报"脚本被改"）。"""
    repo = SW  # 扁平仓：SKILL 根即 git 仓根
    # encoding/errors 仅为解码健壮性（git 输出走 utf-8，Windows locale=GBK
    # 隐式 decode 会抛 UnicodeDecodeError warning）。判定仍纯看 returncode
    # （0/1/128/异常 → clean/dirty/unavailable），三态逻辑一字不动。
    try:
        chk = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", BASE_REF],
            cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unavailable"
    if chk.returncode != 0:
        return "unavailable"  # 基准 ref（BASE_REF）不存在
    try:
        r = subprocess.run(
            ["git", "diff", "--quiet", BASE_REF, "--", rel_path],
            cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unavailable"
    if r.returncode == 0:
        return "clean"   # 无 diff
    if r.returncode == 1:
        return "dirty"   # 有 diff
    return "unavailable"  # 128/其它：诊断不可信，不伪报

def _git_numstat(rel_path: str):
    """返回 `git diff --numstat main -- <rel_path>` 解析出的
    (insertions:int, deletions:int)；ref/git 不可用或非文本（'-\t-'）→ None
    （由调用方计 harness_error，绝不伪报"被改"）。
    与 _git_guard 同样的 main ref 探测 + utf-8 解码加固（GBK 防护），
    判定仍纯看 numstat 数字，不臆断。"""
    repo = SW  # 扁平仓：SKILL 根即 git 仓根
    try:
        chk = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", BASE_REF],
            cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if chk.returncode != 0:
        return None  # 基准 ref（BASE_REF）不存在
    try:
        r = subprocess.run(
            ["git", "diff", "--numstat", BASE_REF, "--", rel_path],
            cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    if out == "":
        return (0, 0)  # 无 diff（文件与 main 完全一致）
    # numstat 行格式：`<ins>\t<del>\t<path>`；二进制为 `-\t-\t<path>`
    line = out.splitlines()[0]
    parts = line.split("\t")
    if len(parts) < 2 or parts[0] == "-" or parts[1] == "-":
        return None  # 二进制/不可解析：诊断不可信，不伪报
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None

# 各 phase 的 diff 阈值（行数/计数）。P0/P6 = 0(逐字节)；其余见下表。
THRESHOLDS = {
    "P0": {"pure_fixture_diff": 0, "scripts_git_clean": True},
    # P1.2：删 final_md_diff/final_html_diff 两个装饰键 —— P1 门**刻意不**对
    # 冻结 golden 的 md/html 做像素/行 diff（见 _run_p1 docstring），这两键
    # 自 P1.1 起从未被消费，留着会误导「P1 会比 golden 文本」。改为只保留
    # img_count_min 并让 _run_p1 **真实消费**它（tier-2 张数门阈值来源）。
    "P1": {"img_count_min": 4},
    "P2": {"iron_rules": True, "outline_schema": True},
    "P3": {"iron_rules": True, "strategies_present": 4},
    "P4": {"iron_rules": True, "cover_selected": True},
    "P5": {"iron_rules": True, "h2_delta": 0, "para_delta_pct": 15},
    # P6.1：删 final_md_diff/final_html_diff 两个**从未被消费**的装饰键
    # （照 P1.2 删 final_* 同精神 —— P6 不重跑 LLM 比 golden 定稿字节，
    #  LLM 不确定不可单测，见 _run_p6 docstring）。改为 _run_p6 **真实
    #  消费**的三键：
    #   - spine_ref_ins_max：主轴 4 reference 每文件对 main 的 insertions
    #     上界（纳管=1 行 + 1 空行 ≤ 2；deletions 必须恒 0，硬编不设键）。
    #   - pipeline_inc_max：pipeline.py 对 main 的 insertions 上界（P0.2
    #     已审计纯增量：orchestrator 开关 + state_writer 标记，实测 21 行；
    #     设 30 留余量但仍能挡住"偷塞 spine 阶段语义"；deletions 必须 0）。
    #   - format_layout_git_clean：format_layout.py 对 main 必须零 diff
    #     （主轴排版可执行流水线全程零行为变更，复用 _run_p0 的 git 守卫）。
    "P6": {"spine_ref_ins_max": 2, "pipeline_inc_max": 30,
           "format_layout_git_clean": True},
}

# P4.2 (c) 段合规 cover fixture 的形状常量（与
# tests/golden/_synthetic_cover/make_fixtures.py 的 compliant 组一致）。
# 提到模块级是为：① _run_p4 (c) 段在「构造依赖它的断言前」据此对
# contracts._COVER_MIN_CANDIDATES / _K1_* 做一致性自检（命中即 return，
# P3.1 复审硬约束防裸崩）；② 单测能像 P3.1 用 THRESHOLDS 那样从 rb
# 侧 monkeypatch 这两个值来稳定触发自检（_run_p4 内按文件路径 fresh
# import contracts，故必须在 rb 侧留可变杠杆，不能改 contracts 常量）。
_P4_FX_CAND_N = 2       # 合规 fixture 候选数
_P4_FX_LONGEDGE = 1024  # 合规 fixture PNG 长边（落 1K 带内）

def _err_summary(e: Exception) -> str:
    return f"{type(e).__name__}: {e}".replace("\n", " ")[:300]

def _run_p0(failures: list):
    """P0 零行为变更门。任何异常一律转结构化 harness_error，禁裸 traceback
    （本仓 subagent 铁律：回传结构化现场，禁静默吞错 / 禁裸崩）。"""
    # (a) 纯变换 fixture：import 当前 format_layout 跑函数，与冻结 expected 比
    # —— format_layout 加载失败（ImportError/SyntaxError）计 harness_error 而非崩
    try:
        fl = _load_format_layout()
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"format_layout 加载失败：{_err_summary(e)}",
        })
        fl = None

    # —— MANIFEST 读取/解析失败也计 harness_error
    cases = []
    if fl is not None:
        try:
            man = json.loads((PURE_DIR/"MANIFEST.json").read_text(encoding="utf-8"))
            cases = man["pure_fixtures"]
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": None,
                "note": f"MANIFEST 读取/解析失败：{_err_summary(e)}",
            })

    # —— 逐 fixture case 包 try/except：AttributeError(函数改名/删)、
    #    FileNotFoundError(fixture 缺失) 等均转结构化，不裸崩
    for case in cases:
        func = case.get("func")
        try:
            in_f, exp_f = case["in"], case["expected"]
            src = (PURE_DIR/in_f).read_text(encoding="utf-8")
            expected = (PURE_DIR/exp_f).read_text(encoding="utf-8")
            fn = getattr(fl, func)  # 函数不存在 → AttributeError
            out = fn(src)
            # 布尔判据：==0 才算「确定性行为未漂移」。diff_lines 只调一次；
            # failure dict 不塞无语义数字（与"返回值无规模语义"注释一致）。
            differs = diff_lines(out, expected) != 0
            if differs:
                failures.append({
                    "kind": "pure_fixture_drift", "func": func,
                    "in": in_f, "expected": exp_f, "differs": True,
                    "note": "format_layout 纯变换输出已偏离冻结基线",
                })
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": func,
                "note": f"fixture 执行异常：{_err_summary(e)}",
            })

    # (b) 脚本 git 守卫：P0 期 format_layout.py 必须对 main 零 diff
    state = _git_guard("scripts/format_layout.py")
    if state == "dirty":
        failures.append({
            "kind": "scripts_git_dirty",
            "path": "scripts/format_layout.py",
            "note": "P0 期 format_layout.py 对 main 必须零 diff（不得改可执行流水线行为）",
        })
    elif state == "unavailable":
        failures.append({
            "kind": "harness_error", "func": None,
            "note": "main ref 不可用或 git 不可用，git 守卫无法判定（非'脚本被改'）",
        })

def _run_p1(failures: list):
    """P1 门（P1.1 + P1.2）：
      (a) 复用 P0 零行为变更门（纯变换 fixture + format_layout.py 对 main 零 diff）；
      (b) infographic 结构契约 validate_output 自洽 smoke（tier-1，手构数据）；
      (c) **P1.2 新增** tier-2 验证门 verify_infographic_set 行为断言：用
          确定性合成 PNG fixture（现造临时目录、跑完即弃），断言合规组返回空、
          各违规组（张数<min/构成错/非三枚举/超2MB/非1K）精确报对应原因，
          并**真实消费** THRESHOLDS["P1"]["img_count_min"]。

    刻意 **不** 对冻结 golden 素材做 ≥4/构成/≤2MB/aspect 像素断言：
    实地勘察发现 34/36 各仅 2 张 9:16、40-樊登含非三枚举长卷且 6MB+，
    历史冻结数据合法但不符 P1.2 语义规则，断言它们=误判门。计数/构成/
    尺寸/枚举属 tier-2，由 P1.2 对 **新产出**（合成 fixture，非历史 golden）
    强制（见 agent-contracts.md 校验层级总纲）。tier-2 用临时合成 PNG 而非
    真实 baoyu-image-gen 产出——机制/门已验证，真实端到端生图留 P6 层或人工验收
    （成本敏感，不烧大额配额）。任何异常一律转结构化 harness_error，禁裸 traceback。"""
    # (a) 复用 P0 门：纯变换 fixture 全 diff_lines==0 + format_layout.py
    #     对 main 零 diff。P1.1 不改 format_layout.py，必须仍零 diff。
    #     直接调 _run_p0(failures)：其内部已是「append 结构化 failures」契约，
    #     P0 漂移/脚本被改/harness_error 会原样进 failures（不重复造轮子，
    #     沿用 P0.5 全部加固：utf-8 / harness_error / git 三态 / diff_lines 布尔）。
    _run_p0(failures)

    # (b) infographic 结构契约自洽 smoke（手构数据，不读 golden 像素）。
    #     证明 P1.1 升 tier-1 的 _validate_infographic_items() 工作正常：
    #     合法 payload → True；缺字段 / bytes=bool → ContractError 被捕获。
    # 以隔离方式按文件路径 import scripts/contracts.py（与 _load_format_layout
    # 同手法），不依赖 cwd / sys.path 上有 `scripts` 包——裸跑 regression_baseline.py
    # 时 `from scripts.contracts import ...` 会 ModuleNotFoundError。
    try:
        _spec = importlib.util.spec_from_file_location(
            "contracts", SW/"scripts"/"contracts.py")
        _contracts = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_contracts)
        validate_output = _contracts.validate_output
        ContractError = _contracts.ContractError
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts 导入失败：{_err_summary(e)}",
        })
        return

    # 正例：合法结构必须 validate_output → True
    try:
        ok = {"images": [{"path": "素材/info1.png", "aspect": "9:16", "bytes": 1200}]}
        if validate_output("infographic", ok) is not True:
            failures.append({
                "kind": "contract_smoke_positive_fail", "func": "validate_output",
                "note": "合法 infographic payload 未返回 True（契约正例回归）",
            })
    except Exception as e:
        # 正例不该抛任何异常（含 ContractError）
        failures.append({
            "kind": "contract_smoke_positive_fail", "func": "validate_output",
            "note": f"合法 infographic payload 误抛：{_err_summary(e)}",
        })

    # 负例：每个都必须被 ContractError 拒（含 bool 陷阱）。
    neg_cases = [
        ("缺 aspect/bytes",   {"images": [{"path": "x"}]}),
        ("bytes=True(bool)",  {"images": [{"path": "x", "aspect": "9:16", "bytes": True}]}),
        ("bytes=False(bool)", {"images": [{"path": "x", "aspect": "9:16", "bytes": False}]}),
        ("aspect 空串",        {"images": [{"path": "x", "aspect": "", "bytes": 10}]}),
        ("项非 dict",          {"images": ["素材/info1.png"]}),
    ]
    for label, bad in neg_cases:
        try:
            validate_output("infographic", bad)
            # 没抛 = 契约漏判，结构化记 failure
            failures.append({
                "kind": "contract_smoke_negative_fail", "func": "validate_output",
                "case": label,
                "note": f"非法 infographic payload 未被 ContractError 拒（{label}）",
            })
        except ContractError:
            pass  # 期望：被结构契约挡下
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": "validate_output",
                "note": f"负例 {label} 抛非 ContractError 异常：{_err_summary(e)}",
            })

    # (c) tier-2 验证门 verify_infographic_set 行为断言（P1.2）。
    #     用确定性合成 PNG fixture（tests/golden/_synthetic_infographic/
    #     make_fixtures.py 现造到临时目录、跑完即弃，不存仓二进制、不烧
    #     baoyu 配额）。**真实消费** THRESHOLDS["P1"]["img_count_min"]：
    #     合规组张数必须 ≥ 该阈值且 verify 返回空；各违规组必须精确报对应原因。
    #     仍**不**对历史冻结 golden 像素做断言（与 _run_p1 docstring 一致）。
    img_count_min = THRESHOLDS["P1"]["img_count_min"]  # 装饰键转真实消费
    try:
        verify_infographic_set = _contracts.verify_infographic_set
    except AttributeError as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts.verify_infographic_set 缺失：{_err_summary(e)}",
        })
        return

    try:
        _fx_spec = importlib.util.spec_from_file_location(
            "make_fixtures",
            SW/"tests"/"golden"/"_synthetic_infographic"/"make_fixtures.py")
        _fx = importlib.util.module_from_spec(_fx_spec)
        _fx_spec.loader.exec_module(_fx)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"合成 fixture 生成器加载失败：{_err_summary(e)}",
        })
        return

    # 期望：每违规组的原因里必须命中给定关键子串（精确报对应原因）
    expect_kw = {
        "bad_count":       "张数",      # 违规① count < img_count_min
        "bad_composition": "构成",      # 违规② 开篇非 9:16
        "bad_aspect_enum": "枚举",      # 违规③ 非三枚举
        "bad_oversize":    "2MB",      # 违规④ 体积超限
        "bad_not_1k":      "1K",       # 违规⑤ 非 1K 分辨率
    }
    try:
        with tempfile.TemporaryDirectory(prefix="p1_synth_") as td:
            groups = _fx.build_groups(pathlib.Path(td))

            # 合规组：张数必须 ≥ img_count_min 且 verify 返回空
            comp = groups["compliant"]
            if len(comp) < img_count_min:
                failures.append({
                    "kind": "p1_fixture_invalid", "func": "build_groups",
                    "note": f"合规组张数 {len(comp)} < img_count_min "
                            f"{img_count_min}（fixture 自身不达阈值）",
                })
            comp_reasons = verify_infographic_set(comp)
            if comp_reasons:
                failures.append({
                    "kind": "tier2_gate_false_positive",
                    "func": "verify_infographic_set",
                    "note": f"合规组被误判违规：{comp_reasons}",
                })

            # 各违规组：必须非空且命中对应关键词（精确报对应原因）
            for gname, kw in expect_kw.items():
                rs = verify_infographic_set(groups[gname])
                if not rs:
                    failures.append({
                        "kind": "tier2_gate_false_negative",
                        "func": "verify_infographic_set", "case": gname,
                        "note": f"违规组 {gname} 未被 tier-2 门拦下（返回空）",
                    })
                elif not any(kw in r for r in rs):
                    failures.append({
                        "kind": "tier2_gate_wrong_reason",
                        "func": "verify_infographic_set", "case": gname,
                        "note": f"违规组 {gname} 报因未命中期望关键词"
                                f"'{kw}'：{rs}",
                    })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "verify_infographic_set",
            "note": f"tier-2 fixture 断言异常：{_err_summary(e)}",
        })

def _run_p2(failures: list):
    """P2 门（P2.1 + P2.2）：
      (a) 复用 P0 零行为变更门（纯变换 fixture + format_layout.py 对 main 零 diff）；
      (b) research 结构契约 validate_output 自洽 smoke（tier-1，手构数据）：
          合法 payload → True；缺 sources / source 缺 url / 空 url / 非 dict
          source → ContractError 被捕获；
      (c) **P2.2 新增** tier-2 验证门 verify_research_set 行为断言：用
          确定性合成 research fixture（手构 findings/sources dict，跑完即弃、
          不烧 AnySearch/Tavily 检索配额），断言合规组返回空、各违规组
          （无 support / 信源不足 / 版本类无官网源 / 空 url）精确报对应原因。

    === THRESHOLDS["P2"] 装饰键归属点名（对齐 plan「P3.1+ 范式约定」，
        消除装饰键气味，与 _run_p1 把 img_count_min 转真实消费同精神）===
    本门 `THRESHOLDS["P2"] = {"iron_rules": True, "outline_schema": True}`：
      • `iron_rules`(True)：**tier-2/铁律关语义键**，语义=「research 新产出
        须遵相关铁律（版本/价格/时间须官网第一信源 — 见 iron-rules.md
        §模型对比内容铁律 / 全局 Guardrails）」。本门 (c) 的
        verify_research_set 规则③「版本/价格/日期类 finding 至少 1 条官网级
        source 兜底」**正是该铁律的机器化 smoke**——已被 (c) 合规/违规组
        断言**真实覆盖其精神**（非装饰）。tier-1 铁律合规（format_layout
        --check）则由 (a) 复用 _run_p0 的脚本 git 守卫 + 纯变换门覆盖。
      • `outline_schema`(True)：语义=「research/大纲产出对齐契约 schema」。
        其 **tier-1 结构层**由 (b) 的 validate_output("research",...) 正反例
        smoke 真实消费（sources[].url 结构强校验）；其 **tier-2 语义层**
        （findings item 实质 / 去重源数 / 官网级）由 (c) 的
        verify_research_set 真实消费。故本键**不再是装饰**——两关已分别
        消费其 tier-1/tier-2 两层语义。
    （阈值取 True 仅表「该关启用」，非数字阈；真实判定逻辑在 (b)/(c)，
     与 P1 把 img_count_min 当真实张数阈消费的范式一致。）

    刻意 **不** 对冻结 golden 的 大纲.md / 素材/research 目录做像素/结构断言：
    历史 3 篇是不同期文章，大纲骨架与 research 产物各异（有的根本没 research
    目录、字段形态不统一），历史冻结数据合法但不符 P2 新语义，断言它们=误判门
    （与 _run_p1 同理）。research 语义（findings item 结构、source tier/title/
    accessed、版本类至少 1 条官网级 source）属 tier-2，由 P2.2 对 **新产出**
    强制、**不追溯历史**（见 agent-contracts.md 校验层级总纲）。tier-2 用
    手构合成 dict fixture 而非真实 AnySearch/Tavily 检索产出——机制/门已验证，
    真实端到端调研留 P6 层或人工验收（成本敏感，不烧大额检索配额，与 _run_p1
    把真实生图延到 P6 同范式）。任何异常一律转结构化 harness_error，
    禁裸 traceback（本仓 subagent 铁律）。"""
    # (a) 复用 P0 门：纯变换 fixture 全 diff_lines==0 + format_layout.py
    #     对 main 零 diff。P2.1 不改 format_layout.py，必须仍零 diff。
    #     直接调 _run_p0(failures)：其内部已是「append 结构化 failures」契约，
    #     P0 漂移/脚本被改/harness_error 会原样进 failures（不重复造轮子，
    #     沿用 P0.5 全部加固：utf-8 / harness_error / git 三态 / diff_lines 布尔）。
    _run_p0(failures)

    # (b) research 结构契约自洽 smoke（手构数据，不读 golden 大纲/research）。
    #     证明 P2.1 升 tier-1 的 _validate_research_items() 工作正常：
    #     合法 payload → True；缺 sources / source 缺 url / 空 url / 非 dict
    #     source → ContractError 被捕获。以隔离方式按文件路径 import
    #     scripts/contracts.py（与 _run_p1 同手法），不依赖 cwd / sys.path
    #     上有 `scripts` 包——裸跑时 `from scripts.contracts import ...` 会
    #     ModuleNotFoundError。
    try:
        _spec = importlib.util.spec_from_file_location(
            "contracts", SW/"scripts"/"contracts.py")
        _contracts = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_contracts)
        validate_output = _contracts.validate_output
        ContractError = _contracts.ContractError
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts 导入失败：{_err_summary(e)}",
        })
        return

    # 正例：合法结构必须 validate_output → True
    try:
        ok = {"findings": [{"claim": "x"}],
              "sources": [{"url": "https://example.com"}]}
        if validate_output("research", ok) is not True:
            failures.append({
                "kind": "contract_smoke_positive_fail", "func": "validate_output",
                "note": "合法 research payload 未返回 True（契约正例回归）",
            })
    except Exception as e:
        # 正例不该抛任何异常（含 ContractError）
        failures.append({
            "kind": "contract_smoke_positive_fail", "func": "validate_output",
            "note": f"合法 research payload 误抛：{_err_summary(e)}",
        })

    # 负例：每个都必须被 ContractError 拒。
    neg_cases = [
        ("缺 sources",       {"findings": []}),
        ("缺 findings",      {"sources": [{"url": "https://x"}]}),
        ("source 缺 url",    {"findings": [], "sources": [{}]}),
        ("source 空 url",    {"findings": [], "sources": [{"url": ""}]}),
        ("source url 空白",  {"findings": [], "sources": [{"url": "  "}]}),
        ("source url 非 str", {"findings": [], "sources": [{"url": 123}]}),
        ("source 非 dict",   {"findings": [], "sources": ["https://x"]}),
    ]
    for label, bad in neg_cases:
        try:
            validate_output("research", bad)
            # 没抛 = 契约漏判，结构化记 failure
            failures.append({
                "kind": "contract_smoke_negative_fail", "func": "validate_output",
                "case": label,
                "note": f"非法 research payload 未被 ContractError 拒（{label}）",
            })
        except ContractError:
            pass  # 期望：被结构契约挡下
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": "validate_output",
                "note": f"负例 {label} 抛非 ContractError 异常：{_err_summary(e)}",
            })

    # (c) tier-2 验证门 verify_research_set 行为断言（P2.2）。
    #     用确定性合成 research fixture（tests/golden/_synthetic_research/
    #     make_fixtures.py 手构 findings/sources dict、跑完即弃，纯 dict 无
    #     磁盘 IO、不烧 AnySearch/Tavily 检索配额）。合规组必须返回空、
    #     各违规组必须精确报对应原因。仍**不**对历史冻结 golden 大纲/research
    #     做断言（与 _run_p2 docstring 一致；真实端到端调研延 P6/人工）。
    try:
        verify_research_set = _contracts.verify_research_set
    except AttributeError as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts.verify_research_set 缺失：{_err_summary(e)}",
        })
        return

    try:
        _rfx_spec = importlib.util.spec_from_file_location(
            "research_make_fixtures",
            SW/"tests"/"golden"/"_synthetic_research"/"make_fixtures.py")
        _rfx = importlib.util.module_from_spec(_rfx_spec)
        _rfx_spec.loader.exec_module(_rfx)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"合成 research fixture 生成器加载失败：{_err_summary(e)}",
        })
        return

    # 期望：每违规组的原因里必须命中给定关键子串（精确报对应原因）
    rexpect_kw = {
        "bad_no_support":      "support",   # 违规① finding 缺实质 support
        "bad_sources_few":     "信源不足",   # 违规② 去重源 < _MIN_SOURCES
        "bad_vpd_no_official": "官网级",     # 违规③ 版本/价格类无官网级源
        "bad_empty_url":       "空",        # 违规④ source url 空
    }
    try:
        rgroups = _rfx.build_groups()

        # 合规组：verify 必须返回空
        comp_reasons = verify_research_set(*rgroups["compliant"])
        if comp_reasons:
            failures.append({
                "kind": "tier2_gate_false_positive",
                "func": "verify_research_set",
                "note": f"research 合规组被误判违规：{comp_reasons}",
            })

        # 各违规组：必须非空且命中对应关键词（精确报对应原因）
        for gname, kw in rexpect_kw.items():
            rs = verify_research_set(*rgroups[gname])
            if not rs:
                failures.append({
                    "kind": "tier2_gate_false_negative",
                    "func": "verify_research_set", "case": gname,
                    "note": f"research 违规组 {gname} 未被 tier-2 门拦下（返回空）",
                })
            elif not any(kw in r for r in rs):
                failures.append({
                    "kind": "tier2_gate_wrong_reason",
                    "func": "verify_research_set", "case": gname,
                    "note": f"research 违规组 {gname} 报因未命中期望关键词"
                            f"'{kw}'：{rs}",
                })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "verify_research_set",
            "note": f"tier-2 research fixture 断言异常：{_err_summary(e)}",
        })

def _run_p3(failures: list):
    """P3 门（P3.1 + P3.2）：
      (a) 复用 P0 零行为变更门（纯变换 fixture + format_layout.py 对 main 零 diff）；
      (b) content_enhance 结构契约 validate_output 自洽 smoke（tier-1，手构数据，
          **不读历史 golden 定稿/大纲**）：合法 4 键 payload → True；缺某键 /
          值空 / 值非 str / strategies 非 dict / 含多余键 → ContractError 被捕获；
      (c) **P3.2 新增** tier-2 验证门 verify_content_enhance_set 行为断言：用
          确定性合成 content_enhance fixture（手构 strategies/article_body dict、
          跑完即弃、不烧任何 LLM 增强配额），断言合规组返回空、各违规组
          （雷同/矛盾/占位过短/脱节）精确报对应原因。**依赖阈值/键集构造
          fixture 前先一致性自检命中即 return**（P3.1 复审硬约束，防裸崩）。
          合并关（去重/消矛盾/统一嗓音/与正文融合）由编排器主轴自做、绝不
          外派 subagent；本门 (c) 是合并后对**新产出**的机器化把关。

    === THRESHOLDS["P3"] 键归属点名（对齐 plan「P3.1+ 范式约定」，
        消除装饰键气味，与 _run_p1 把 img_count_min 转真实消费同精神）===
    本门 `THRESHOLDS["P3"] = {"iron_rules": True, "strategies_present": 4}`：
      • `strategies_present`(4)：**本门 scope 内键，本函数真实消费**——
        从该键取「期望策略数」(=4) 驱动 (b) 的合法 smoke payload 组键数
        断言：合法 strategies 必须恰好含 strategies_present 个键且
        validate_output → True；少一键（=strategies_present−1）必须被
        ContractError 拒。**非装饰**（照 P1 img_count_min 真实消费范式）。
      • `iron_rules`(True)：**本门 scope 外键**，归属 = tier-2/铁律关语义键，
        语义=「content_enhance 新产出须遵行文铁律子集（破折号 `--`、无引导句、
        无尾部总结等）」。其 tier-1 铁律合规（format_layout --check）由 (a)
        复用 _run_p0 的脚本 git 守卫 + 纯变换门覆盖；其 tier-2 文本语义
        （增强后文本是否真守铁律、四策略不矛盾/不套话/与正文融合）属
        **P3.2 合并关/语义门**对新产出把关、**不追溯历史冻结**，**不**在
        本结构门消费（与 agent-contracts.md「校验层级总纲」一致）。
    （阈值 True 仅表「该关启用」非数字阈；strategies_present 才是真实数字阈。）

    刻意 **不** 对冻结 golden 的 定稿.md / 大纲.md / 素材/enhance 做像素/结构
    断言：历史 3 篇是不同期文章、无统一 content_enhance 产物（多数根本没
    素材/enhance 目录），历史冻结数据不符 P3 新结构，断言它们=误判门
    （与 _run_p1/_run_p2 同理）。content_enhance 文本语义（质量/去重/不矛盾/
    与正文融合）属 tier-2，由 P3.2 对 **新产出** 强制、**不追溯历史**
    （见 agent-contracts.md 校验层级总纲）。任何异常一律转结构化
    harness_error，禁裸 traceback（本仓 subagent 铁律）。"""
    # (a) 复用 P0 门：纯变换 fixture 全 diff_lines==0 + format_layout.py
    #     对 main 零 diff。P3.1 不改 format_layout.py，必须仍零 diff。
    #     直接调 _run_p0(failures)：其内部已是「append 结构化 failures」契约，
    #     P0 漂移/脚本被改/harness_error 会原样进 failures（不重复造轮子，
    #     沿用 P0.5 全部加固：utf-8 / harness_error / git 三态 / diff_lines 布尔）。
    _run_p0(failures)

    # (b) content_enhance 结构契约自洽 smoke（手构数据，不读 golden 定稿/大纲）。
    #     证明 P3.1 升 tier-1 的 _validate_content_enhance() 工作正常：
    #     合法 4 键 payload → True；缺键/空值/非 str/strategies 非 dict/
    #     多余键 → ContractError 被捕获。以隔离方式按文件路径 import
    #     scripts/contracts.py（与 _run_p1/_run_p2 同手法），不依赖 cwd /
    #     sys.path 上有 `scripts` 包——裸跑时 `from scripts.contracts import
    #     ...` 会 ModuleNotFoundError。
    try:
        _spec = importlib.util.spec_from_file_location(
            "contracts", SW/"scripts"/"contracts.py")
        _contracts = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_contracts)
        validate_output = _contracts.validate_output
        ContractError = _contracts.ContractError
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts 导入失败：{_err_summary(e)}",
        })
        return

    # **真实消费** THRESHOLDS["P3"]["strategies_present"]（=4）：作为期望
    # 策略键数驱动合法 smoke payload 组键数 + 缺键负例（装饰键转真实消费）。
    n_strat = THRESHOLDS["P3"]["strategies_present"]
    canon_keys = ("angle", "density", "detail", "texture")
    if len(canon_keys) != n_strat:
        # fixture/阈值不一致：结构化报，不裸崩（与 _run_p1 fixture_invalid 同精神）。
        # ⚠️ 必须立即 return：后续 legal_keys=canon_keys[:n_strat] 及 neg_cases
        #    里的 legal_keys[0] 依赖 n_strat 合理；当 strategies_present 被误配
        #    <1（如 0）时 legal_keys=() → legal_keys[0] 抛**裸 IndexError**
        #    逃出本函数成 traceback，违反本函数 docstring「任何异常一律转
        #    结构化 harness_error、禁裸 traceback」铁律。fixture 配置既已失效，
        #    继续构造依赖 n_strat 的 payload 无意义且不安全，故就此结构化收口。
        failures.append({
            "kind": "p3_fixture_invalid", "func": None,
            "note": f"strategies_present={n_strat} 与规范键数 "
                    f"{len(canon_keys)} 不一致（阈值/契约失配）",
        })
        return
    # 由 strategies_present 驱动合法 payload：恰好 n_strat 个键、值非空 str
    legal_keys = canon_keys[:n_strat]
    legal_strategies = {k: f"策略 {k} 的非空增强说明" for k in legal_keys}

    # 正例：strategies_present 个键齐全 → validate_output → True
    try:
        if validate_output(
                "content_enhance", {"strategies": legal_strategies}) is not True:
            failures.append({
                "kind": "contract_smoke_positive_fail", "func": "validate_output",
                "note": f"合法 content_enhance payload（{n_strat} 键）"
                        f"未返回 True（契约正例回归）",
            })
    except Exception as e:
        # 正例不该抛任何异常（含 ContractError）
        failures.append({
            "kind": "contract_smoke_positive_fail", "func": "validate_output",
            "note": f"合法 content_enhance payload 误抛：{_err_summary(e)}",
        })

    # 负例：每个都必须被 ContractError 拒。缺键负例由 strategies_present
    # 驱动（去掉第 1 个键 → 只剩 n_strat−1 个，必须被拒）。
    short_strategies = {k: "v" for k in legal_keys[1:]}  # n_strat−1 个键
    neg_cases = [
        (f"缺 1 键(只 {n_strat-1} 个)", {"strategies": short_strategies}),
        ("strategies 非 dict",
         {"strategies": list(canon_keys)}),
        ("缺 strategies 顶层键", {}),
        ("某键值空串",
         {"strategies": dict(legal_strategies, **{legal_keys[0]: ""})}),
        ("某键值纯空白",
         {"strategies": dict(legal_strategies, **{legal_keys[0]: "   "})}),
        ("某键值非 str",
         {"strategies": dict(legal_strategies, **{legal_keys[0]: 123})}),
        ("含多余键",
         {"strategies": dict(legal_strategies, **{"_extra_": "x"})}),
    ]
    for label, bad in neg_cases:
        try:
            validate_output("content_enhance", bad)
            # 没抛 = 契约漏判，结构化记 failure
            failures.append({
                "kind": "contract_smoke_negative_fail", "func": "validate_output",
                "case": label,
                "note": f"非法 content_enhance payload 未被 ContractError "
                        f"拒（{label}）",
            })
        except ContractError:
            pass  # 期望：被结构契约挡下
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": "validate_output",
                "note": f"负例 {label} 抛非 ContractError 异常："
                        f"{_err_summary(e)}",
            })

    # (c) tier-2 验证门 verify_content_enhance_set 行为断言（P3.2）。
    #     用确定性合成 content_enhance fixture（tests/golden/
    #     _synthetic_content_enhance/make_fixtures.py 手构 strategies/
    #     article_body dict、跑完即弃，纯 dict 无磁盘 IO、不烧任何 LLM
    #     增强配额）。合规组必须返回空、各违规组必须精确报对应原因。
    #     仍**不**对历史冻结 golden 定稿/大纲/enhance 做断言（与 _run_p3
    #     docstring 一致；真实端到端 4 策略 + 编排器合并关延 P6/人工，
    #     已在 plan carry-forward 显式登记，非静默）。
    #     合并关本身（去重/消矛盾/统一嗓音/与正文融合）由编排器主轴自做、
    #     绝不外派 subagent；本门 (c) 是合并后对**新产出**的把关。
    try:
        verify_content_enhance_set = _contracts.verify_content_enhance_set
    except AttributeError as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts.verify_content_enhance_set 缺失："
                    f"{_err_summary(e)}",
        })
        return

    # 🔴 P3.1 复审硬约束：**依赖阈值/键集构造 fixture 前先一致性自检，
    #    命中即 return**（防裸崩）。verify_content_enhance_set 与合成
    #    fixture 都以 contracts._CE_STRATEGY_KEYS 为单一事实源；若该常量
    #    与 THRESHOLDS["P3"]["strategies_present"] 失配（如有人改了键集
    #    数量却没同步阈值），继续跑 fixture 断言会让「合规组期望空」与
    #    实际 4 键判定面错位 → 误判门 / 潜在裸崩。fixture 配置既已失效，
    #    继续构造依赖它的断言无意义且不安全，故就此结构化收口（与 (b)
    #    段 p3_fixture_invalid 自检即 return 同精神）。
    n_strat = THRESHOLDS["P3"]["strategies_present"]
    ce_keys = getattr(_contracts, "_CE_STRATEGY_KEYS", None)
    if not isinstance(ce_keys, (tuple, list)) or len(ce_keys) != n_strat:
        failures.append({
            "kind": "p3_fixture_invalid", "func": None,
            "note": f"_CE_STRATEGY_KEYS={ce_keys!r} 与 strategies_present="
                    f"{n_strat} 失配（tier-2 fixture 阈值/键集失配，"
                    f"自检即收口，不构造依赖它的断言）",
        })
        return

    try:
        _cefx_spec = importlib.util.spec_from_file_location(
            "ce_make_fixtures",
            SW/"tests"/"golden"/"_synthetic_content_enhance"
            / "make_fixtures.py")
        _cefx = importlib.util.module_from_spec(_cefx_spec)
        _cefx_spec.loader.exec_module(_cefx)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"合成 content_enhance fixture 生成器加载失败："
                    f"{_err_summary(e)}",
        })
        return

    # 期望：每违规组的原因里必须命中给定规则名子串（精确报对应原因）
    ceexpect_kw = {
        "bad_duplicate":     "dedup",            # 违规① 两策略雷同
        "bad_contradiction": "no_contradiction",  # 违规② 自相矛盾
        "bad_placeholder":   "substantive",      # 违规③ 占位/过短
        "bad_disjoint":      "not_disjoint",     # 违规④ 与正文脱节
    }
    try:
        cegroups = _cefx.build_groups()

        # 合规组：verify 必须返回空
        comp_reasons = verify_content_enhance_set(*cegroups["compliant"])
        if comp_reasons:
            failures.append({
                "kind": "tier2_gate_false_positive",
                "func": "verify_content_enhance_set",
                "note": f"content_enhance 合规组被误判违规：{comp_reasons}",
            })

        # 各违规组：必须非空且命中对应规则名（精确报对应原因）
        for gname, kw in ceexpect_kw.items():
            rs = verify_content_enhance_set(*cegroups[gname])
            if not rs:
                failures.append({
                    "kind": "tier2_gate_false_negative",
                    "func": "verify_content_enhance_set", "case": gname,
                    "note": f"content_enhance 违规组 {gname} 未被 tier-2 "
                            f"门拦下（返回空）",
                })
            elif not any(kw in r for r in rs):
                failures.append({
                    "kind": "tier2_gate_wrong_reason",
                    "func": "verify_content_enhance_set", "case": gname,
                    "note": f"content_enhance 违规组 {gname} 报因未命中"
                            f"期望规则名 '{kw}'：{rs}",
                })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "verify_content_enhance_set",
            "note": f"tier-2 content_enhance fixture 断言异常："
                    f"{_err_summary(e)}",
        })

def _run_p4(failures: list):
    """P4 门（P4.1 + P4.2）：
      (a) 复用 P0 零行为变更门（纯变换 fixture + format_layout.py 对 main 零 diff）；
      (b) cover 结构契约 validate_output 自洽 smoke（tier-1，手构数据，
          **不读历史 golden 封面/selected.json**）：合法 payload → True；
          缺顶层键 / 顶层类型错 / candidates 项非 dict / 缺 path / path 空 /
          path 非 str / selected 空 / selected 非 str → ContractError 被捕获；
      (c) **P4.2 新增** tier-2 验证门 verify_cover_set 行为断言：用确定性
          合成 PNG fixture（tests/golden/_synthetic_cover/make_fixtures.py
          现造临时目录的小 PNG、跑完即弃，不存仓二进制、不烧 baoyu-cover
          配额），断言合规组返回空、各违规组（selected∉candidates / 候选
          <2 / 图不存在 / 非1K / 比例错）精确报对应规则名（🔴 旧「撞近3篇」规则⑥ 2026-05-22 已删，bad_recent_repeat 组现属合规）。
          **依赖阈值/键集构造 fixture 前先一致性自检命中即 return**
          （P3.1 复审硬约束，防裸崩）。🔴 封面锁定 montage-evidence 单风格，
          默认无多候选 fan-out / 无选优 / 无近 3 篇回避；本门 (c) 仅在显式
          多候选覆盖模式下对**新产出**做机器化把关（①②③④⑤，无⑥回避）。

    === THRESHOLDS["P4"] 键归属点名（对齐 plan「P3.1+ 范式约定」，
        消除装饰键气味，与 _run_p1 把 img_count_min 转真实消费同精神）===
    本门 `THRESHOLDS["P4"] = {"iron_rules": True, "cover_selected": True}`，
    二者均为**布尔旗标**（非计数/数值阈），仅表「该关启用」：
      • `cover_selected`(True)：**本门 scope 内键**，归属 = tier-2 语义关，
        语义=「`selected ∈ candidates` 路径（选定项可追溯）+ 候选图实际
        存在 + 多风格打样（覆盖模式）+ 1K + 2.35:1」（近 3 篇回避规则已删）。这是**跨字段 +
        磁盘 IO**约束，按校验层级总纲**不塞进结构契约**（塞了会污染契约
        且与总纲自相矛盾）；其语义现由 **P4.2 验证门 verify_cover_set**
        对 _新产出_ 强制、**不追溯历史冻结 golden**（历史 3 篇封面各异），
        **已被本门 (c) 段合成 fixture 合规/各违规组断言真实覆盖其语义**
        （非装饰旗标——与 P1 img_count_min 转真实消费、P3 strategies_present
        真实消费同精神；tier-1 _validate_cover 仍只保 candidates[].path
        非空 str + selected 非空 str 结构，跨字段/IO 留本门 (c)）。
      • `iron_rules`(True)：**本门 scope 外键**，归属 = tier-2/铁律关语义键，
        语义=「cover 新产出须遵封面铁律子集（2.35:1 比例、中文文字约束、
        严禁 Agent 原生生图破比例、1K 分辨率）」（近 3 篇封面回避规则已删）。其 tier-1
        铁律合规（format_layout --check）由 (a) 复用 _run_p0 的脚本 git
        守卫 + 纯变换门覆盖；其 tier-2 图片语义（比例/存在/1K）
        现由 (c) 的 verify_cover_set 真实消费（2.35:1/1K 诸关），
        **不追溯历史冻结**，与 agent-contracts.md「校验层级总纲」一致。
    （两键皆布尔旗标，**不涉及** P3.1 的「依赖数值阈构造 fixture」范式：
     本门 (c) fixture 不由任何数值阈驱动。但 verify_cover_set 与合成
     fixture 共用 contracts._COVER_MIN_CANDIDATES / _K1_* 既定常量为
     单一事实源，故 (c) 仍照 P3.1 范式**在构造依赖它的断言前先一致性
     自检命中即 return**，防键集/阈值失配时裸崩或误判门。）

    刻意 **不** 对冻结 golden 的 素材/cover/candidates/*.png /
    selected.json 做像素/结构断言：历史 3 篇是不同期文章、封面风格/比例/
    候选数各异（有的根本没 cover 目录、selected 形态不统一），历史冻结
    数据合法但不符 P4 新语义，断言它们=误判门（与 _run_p1/p2/p3 同理）。
    cover 语义（selected∈candidates、2.35:1 比例、图实际存在、1K 分辨率）
    属 tier-2（近 3 篇回避规则已删），由 P4.2 对 **新产出** 强制、
    **不追溯历史**（见 agent-contracts.md 校验层级总纲）。(c) 用临时合成
    PNG 而非真实 baoyu-cover-image 产出——机制/门已验证，真实多风格生图
    + 编排器主轴选优留 P6 层或人工验收（成本敏感，不烧大额生图配额，
    与 _run_p1 把真实生图延到 P6 同范式，plan carry-forward 显式登记
    非静默）。任何异常一律转结构化 harness_error，禁裸 traceback
    （本仓 subagent 铁律）。"""
    # (a) 复用 P0 门：纯变换 fixture 全 diff_lines==0 + format_layout.py
    #     对 main 零 diff。P4.1 不改 format_layout.py，必须仍零 diff。
    #     直接调 _run_p0(failures)：其内部已是「append 结构化 failures」契约，
    #     P0 漂移/脚本被改/harness_error 会原样进 failures（不重复造轮子，
    #     沿用 P0.5 全部加固：utf-8 / harness_error / git 三态 / diff_lines 布尔）。
    _run_p0(failures)

    # (b) cover 结构契约自洽 smoke（手构数据，不读 golden 封面/selected.json）。
    #     证明 P4.1 升 tier-1 的 _validate_cover() 工作正常：合法 payload →
    #     True；缺顶层键/顶层类型错/candidates 项非 dict/缺 path/path 空/
    #     path 非 str/selected 空/selected 非 str → ContractError 被捕获。
    #     以隔离方式按文件路径 import scripts/contracts.py（与
    #     _run_p1/p2/p3 同手法），不依赖 cwd / sys.path 上有 `scripts` 包
    #     ——裸跑时 `from scripts.contracts import ...` 会 ModuleNotFoundError。
    try:
        _spec = importlib.util.spec_from_file_location(
            "contracts", SW/"scripts"/"contracts.py")
        _contracts = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_contracts)
        validate_output = _contracts.validate_output
        ContractError = _contracts.ContractError
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts 导入失败：{_err_summary(e)}",
        })
        return

    # 正例：合法结构必须 validate_output → True。selected 刻意**不**在
    # candidates 路径里（跨字段属 tier-2，结构层不应因此拒——正例证明）。
    try:
        ok = {"candidates": [
                  {"path": "素材/cover/candidates/cinematic.png",
                   "style": "cinematic", "aspect": "2.35:1"},
                  {"path": "素材/cover/candidates/editorial.png",
                   "style": "editorial", "aspect": "2.35:1"}],
              "selected": "素材/cover/candidates/cinematic.png"}
        if validate_output("cover", ok) is not True:
            failures.append({
                "kind": "contract_smoke_positive_fail", "func": "validate_output",
                "note": "合法 cover payload 未返回 True（契约正例回归）",
            })
    except Exception as e:
        # 正例不该抛任何异常（含 ContractError）
        failures.append({
            "kind": "contract_smoke_positive_fail", "func": "validate_output",
            "note": f"合法 cover payload 误抛：{_err_summary(e)}",
        })

    # 负例：每个都必须被 ContractError 拒。
    neg_cases = [
        ("缺 candidates",      {"selected": "素材/cover/a.png"}),
        ("缺 selected",        {"candidates": [{"path": "x"}]}),
        ("candidates 非 list", {"candidates": "x", "selected": "y"}),
        ("selected 非 str",    {"candidates": [{"path": "x"}], "selected": 123}),
        ("candidate 非 dict",  {"candidates": ["素材/cover/a.png"],
                               "selected": "素材/cover/a.png"}),
        ("candidate 缺 path",  {"candidates": [{}],
                               "selected": "素材/cover/a.png"}),
        ("candidate path 空",  {"candidates": [{"path": ""}],
                               "selected": "素材/cover/a.png"}),
        ("candidate path 空白", {"candidates": [{"path": "  "}],
                               "selected": "素材/cover/a.png"}),
        ("candidate path 非 str", {"candidates": [{"path": 123}],
                               "selected": "素材/cover/a.png"}),
        ("selected 空串",      {"candidates": [{"path": "x"}], "selected": ""}),
        ("selected 纯空白",    {"candidates": [{"path": "x"}],
                               "selected": "   "}),
    ]
    for label, bad in neg_cases:
        try:
            validate_output("cover", bad)
            # 没抛 = 契约漏判，结构化记 failure
            failures.append({
                "kind": "contract_smoke_negative_fail", "func": "validate_output",
                "case": label,
                "note": f"非法 cover payload 未被 ContractError 拒（{label}）",
            })
        except ContractError:
            pass  # 期望：被结构契约挡下
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": "validate_output",
                "note": f"负例 {label} 抛非 ContractError 异常："
                        f"{_err_summary(e)}",
            })

    # (c) tier-2 验证门 verify_cover_set 行为断言（P4.2）。
    #     用确定性合成 PNG fixture（tests/golden/_synthetic_cover/
    #     make_fixtures.py 现造临时目录小 PNG、跑完即弃，不存仓二进制、
    #     不烧 baoyu-cover-image 生图配额）。合规组必须返回空、各违规组
    #     必须精确报对应规则名。仍**不**对历史冻结 golden 封面/selected.json
    #     做断言（与 _run_p4 docstring 一致；真实多风格生图 + 编排器主轴
    #     选优延 P6/人工，plan carry-forward 显式登记非静默）。
    #     **选优是编排器主轴裁量、绝不外派 subagent**；本门 (c) 是选优
    #     前置对新产出的把关，不是选优本身。
    try:
        verify_cover_set = _contracts.verify_cover_set
    except AttributeError as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts.verify_cover_set 缺失：{_err_summary(e)}",
        })
        return

    # 🔴 P3.1 复审硬约束：**依赖阈值/键集构造 fixture 前先一致性自检，
    #    命中即 return**（防裸崩）。verify_cover_set 与合成 fixture 都以
    #    contracts._COVER_MIN_CANDIDATES（多风格打样下限）+ _K1_MIN/_K1_MAX
    #    （1K 复用信息图既定带，单一事实源）为依据；若这些常量被改而
    #    fixture 没同步（如下限改 3 但 fixture 仍只造 2 候选），继续跑
    #    断言会让「合规组期望空」与实际判定面错位 → 误判门 / 潜在裸崩。
    #    fixture 配置既已失效，继续构造依赖它的断言无意义且不安全，故
    #    就此结构化收口（与 _run_p3 (c) 段 p3_fixture_invalid 自检即
    #    return 同精神）。本门两 THRESHOLDS 键皆布尔旗标、不驱动 fixture，
    #    故自检对象是 contracts 模块级常量本身（合规 fixture 造 2 候选、
    #    长边 1024 必须分别 ≥ 下限、落 1K 带内）。
    _cmin = getattr(_contracts, "_COVER_MIN_CANDIDATES", None)
    _k1lo = getattr(_contracts, "_K1_MIN", None)
    _k1hi = getattr(_contracts, "_K1_MAX", None)
    _FX_CAND_N = _P4_FX_CAND_N       # 合规 fixture 候选数（模块级单一事实源）
    _FX_LONGEDGE = _P4_FX_LONGEDGE   # 合规 fixture PNG 长边（模块级）
    if (not isinstance(_cmin, int) or isinstance(_cmin, bool)
            or not isinstance(_k1lo, int) or isinstance(_k1lo, bool)
            or not isinstance(_k1hi, int) or isinstance(_k1hi, bool)
            or _FX_CAND_N < _cmin
            or not (_k1lo <= _FX_LONGEDGE <= _k1hi)):
        failures.append({
            "kind": "p4_fixture_invalid", "func": None,
            "note": f"_COVER_MIN_CANDIDATES={_cmin!r} / _K1=[{_k1lo!r},"
                    f"{_k1hi!r}] 与合规 fixture（{_FX_CAND_N} 候选 / 长边 "
                    f"{_FX_LONGEDGE}）失配（tier-2 fixture 阈值/常量失配，"
                    f"自检即收口，不构造依赖它的断言）",
        })
        return

    try:
        _cvfx_spec = importlib.util.spec_from_file_location(
            "cover_make_fixtures",
            SW/"tests"/"golden"/"_synthetic_cover"/"make_fixtures.py")
        _cvfx = importlib.util.module_from_spec(_cvfx_spec)
        _cvfx_spec.loader.exec_module(_cvfx)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"合成 cover fixture 生成器加载失败：{_err_summary(e)}",
        })
        return

    # 期望：每违规组的原因里必须命中给定规则名子串（精确报对应原因）
    cvexpect_kw = {
        "bad_selected_not_in": "selected_in_candidates",  # 违规①
        "bad_too_few":         "candidates_min",          # 违规②
        "bad_missing_file":    "candidate_exists",        # 违规③
        "bad_not_1k":          "resolution_1k",           # 违规④
        "bad_ratio":           "cinematic_ratio",         # 违规⑤
        # 🔴 违规⑥「近 3 篇回避」已删除（2026-05-22 封面锁定 montage-evidence）：
        #    不再期望 bad_recent_repeat 组报 recent_repeat（fixture 组保留但该组
        #    现属合规，由 pytest test_verify_cover_set_fixture_groups_behave 守护「不报」）。
    }
    try:
        with tempfile.TemporaryDirectory(prefix="p4_synth_") as td:
            cvgroups = _cvfx.build_groups(pathlib.Path(td))

            # 合规组：verify 必须返回空
            comp_reasons = verify_cover_set(*cvgroups["compliant"])
            if comp_reasons:
                failures.append({
                    "kind": "tier2_gate_false_positive",
                    "func": "verify_cover_set",
                    "note": f"cover 合规组被误判违规：{comp_reasons}",
                })

            # 各违规组：必须非空且命中对应规则名（精确报对应原因）
            for gname, kw in cvexpect_kw.items():
                rs = verify_cover_set(*cvgroups[gname])
                if not rs:
                    failures.append({
                        "kind": "tier2_gate_false_negative",
                        "func": "verify_cover_set", "case": gname,
                        "note": f"cover 违规组 {gname} 未被 tier-2 门拦下"
                                f"（返回空）",
                    })
                elif not any(kw in r for r in rs):
                    failures.append({
                        "kind": "tier2_gate_wrong_reason",
                        "func": "verify_cover_set", "case": gname,
                        "note": f"cover 违规组 {gname} 报因未命中期望规则名 "
                                f"'{kw}'：{rs}",
                    })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "verify_cover_set",
            "note": f"tier-2 cover fixture 断言异常：{_err_summary(e)}",
        })

def _h2_count(md: str) -> int:
    """统计 markdown 文本里 H2 标题数（`## ` 起头行，排除 `###`+）。
    与 _para_count 同属本模块确定性纯计数（无 IO、不读 golden）。"""
    n = 0
    for line in str(md).splitlines():
        s = line.lstrip()
        if s.startswith("## ") and not s.startswith("### "):
            n += 1
    return n

def _body_para_count(md: str) -> int:
    """段落 delta 基数专用：复用 _para_count 的 `\\n\\n` 切块口径，但
    **剔除纯 H2 标题行块**（`## ` 起头、`### ` 除外、块内无换行 = 单行
    标题），只数**正文/过渡段落数**。

    口径决策与依据（P5.2 高优先口径厘清，plan carry-forward 要求）：
      • P5 段落 delta 的语义是「team 误删/塞正文」。H2 章节结构由
        `_h2_count` + h2_delta(==0) 单独硬守；若把 H2 标题块也算进段落
        分母（= `_para_count` 既有口径），删一整节会在 h2_delta 与
        para_delta_pct **双门重复计入**，且分母含标题导致百分比失真
        —— 「±15% 段落基数剔除 H2 标题行」更贴近"防 team 误删正文章节"
        语义，故本门段落 delta 取**剔除 H2 标题行后的正文段落数**。
      • 与 `_para_count` 既有口径的协调：`_para_count` / `_h2_count`
        是本模块**全局确定性纯计数**，被 P0 等多门复用、口径不能漂移，
        故**不改它们**；本函数是 P5 段落 delta 的**局部派生口径**，
        复用 `_para_count` 的切块逻辑（`split("\\n\\n")` + strip 非空），
        仅在其上叠加「滤掉 H2 单行标题块」，与 `_h2_count`（`"## "`
        带空格、排除 `### `）/ format_layout `^##` 口径一致、真实文本下
        不漂移。
    与 _para_count / _h2_count 同属本模块确定性纯计数（无 IO、不读 golden）。"""
    n = 0
    for b in str(md).split("\n\n"):
        s = b.strip()
        if not s:
            continue
        # 纯 H2 标题块：单行（块内无换行）且 `## ` 起头、非 `### `+。
        # 与 _h2_count 同口径（`"## "` 带空格），确保两计数一致不漂移。
        if ("\n" not in s and s.startswith("## ")
                and not s.startswith("### ")):
            continue
        n += 1
    return n

def _run_p5(failures: list):
    """P5 门（P5.2 起，**结构契约 + P5 数值阈回归断言 + tier-2
    verify_review_set 合成 fixture 断言 + 审稿 team 关闭路径等价断言**）：
      (a) 复用 P0 零行为变更门（纯变换 fixture + format_layout.py 对 main 零 diff）；
      (b) review 结构契约 validate_output 自洽 smoke（tier-1，手构数据，
          **不读历史 golden 定稿/review 产物**）：合法 payload → True；
          verdicts 非 list / 项非 dict / 缺 role / role 空 / role 非 str /
          issues 非 list / 缺 pass / pass 非 bool / pass=1 或 0 int →
          ContractError 被捕获；
      (c) **P5 数值阈回归断言**：真实消费 THRESHOLDS["P5"] 的两个数值键
          `h2_delta`(=0) 与 `para_delta_pct`(=15)。合成「baseline 文 /
          团队审稿后文」对（确定性手构字符串，**不读历史冻结 golden 真实
          定稿**），校验团队审稿前后 **H2 数 delta == h2_delta(0)** 且
          **正文段落数变化百分比 ≤ para_delta_pct(15)**：合规组（H2 不变、
          正文段落 ±15% 内）过；违规组（H2 增 / H2 减 / 正文段落超 +15% /
          超 −15%）精确报对应原因。**段落基数口径**：取
          `_body_para_count`（剔除 H2 标题行后的正文段落数），**不含
          H2 标题块** —— 见该函数文档串口径决策（H2 结构由 h2_delta 单独
          硬守，分母含标题会双门重复计入且失真；不改全局 `_para_count`
          口径，仅 P5 局部派生）。**依赖这两个数值键构造 fixture 前先
          一致性自检命中即 return**（P3.1 复审硬约束，防裸崩；h2_delta
          应为 int 0、para_delta_pct 应为合理正数 int —— 取值/类型不合理
          则结构化收口，照 _run_p3 (b)/(c) 段 p3_fixture_invalid 自检即
          return 范式）。
      (d) **tier-2 verify_review_set 合成 fixture 断言 + 审稿 team 关闭
          路径等价断言**（P5.2）：用确定性手构 review verdicts fixture
          （tests/golden/_synthetic_review/make_fixtures.py 纯 list[dict]、
          跑完即弃，不烧任何 LLM 审稿配额）。合规组返回空、各违规组
          （<3 role / pass=false 但 issues 空 / pass=true 却带 issues）
          精确报对应规则名。**审稿 team 关闭路径等价断言**：用合成对
          构造「team 未启用（opt-in 未确认 / orchestrator=off）」场景，
          断言其与 legacy 单 agent 磨稿口径一致（无 verdicts 产物时
          tier-2 门不强加、不臆判 —— 等价于既有单 agent 磨稿不产 review
          集合，与 spec §P5 验收⑤「team 关闭须与 legacy 字节级等价」
          对齐；**不读历史 golden 真实定稿**，用合成对）。**真实
          TeamCreate 三角色 + 编排器汇总 + pass=false 回流 + opt-in
          提议交互端到端延 P6/人工，已在 plan carry-forward 显式登记，
          非静默**（成本敏感，不真开 team 烧 token；与 _run_p1 真实生图
          延 P6 同范式）。**汇总裁决是编排器主轴自做、绝不外派**，本门
          (d) 是汇总裁决前置对新产出的把关，不是汇总裁决本身。

    === THRESHOLDS["P5"] 键归属点名（对齐 plan「P3.1+ 范式约定」，
        消除装饰键气味，与 _run_p1 把 img_count_min 转真实消费同精神）===
    本门 `THRESHOLDS["P5"] = {"iron_rules": True, "h2_delta": 0,
    "para_delta_pct": 15}`：
      • `h2_delta`(0) / `para_delta_pct`(15)：**本门 scope 内数值键，本函数
        (c) 真实消费**——从这两个键取「团队审稿前后允许的 H2 数 delta
        阈值」(=0，即 team 严禁增删章节)与「段落数允许变化百分比」(=15)，
        驱动合规/违规 fixture 构造与精确判定（**非装饰**，照 P1
        img_count_min / P3 strategies_present 真实消费范式）。语义依据：
        plan §P5 验收「团队审稿磨稿不得误删章节 —— H2 数对 baseline
        delta==0、段落数 delta ≤±15%」。
      • `iron_rules`(True)：**本门 scope 外键**，归属 = tier-2/铁律关语义键，
        语义=「review 新产出（团队审稿结论 + 回流后定稿）须遵全阶段相关
        铁律子集」。其 tier-1 铁律合规（format_layout --check）由 (a) 复用
        _run_p0 的脚本 git 守卫 + 纯变换门覆盖；其 tier-2 语义（审稿
        issues 非空可定位 / role 覆盖 / 裁决一致性）由 (d) 的
        `verify_review_set` 对**新产出**把关、**不追溯历史冻结**；issue
        内容对错 / role 是否「正统」/ `pass=false` 回流处置归编排器主轴
        裁量，门不越界（与 agent-contracts.md「校验层级总纲」一致）。
    （`iron_rules` 阈值 True 仅表「该关启用」非数字阈；`h2_delta` /
     `para_delta_pct` 才是本门真实数值阈。）

    刻意 **不** 对冻结 golden 的 定稿.md / 素材/review/verdicts.json 做
    像素/结构断言：历史 3 篇是不同期文章、无统一 review 产物（多数根本没
    素材/review 目录），历史冻结数据不符 P5 新结构，断言它们=误判门
    （与 _run_p1/p2/p3/p4 同理）。review 文本语义（issues 非空可定位 /
    role 覆盖 / 裁决一致性）属 tier-2，由 (d) `verify_review_set` 对
    **新产出** 强制、**不追溯历史**（见 agent-contracts.md 校验层级
    总纲）。审稿 team 是 **opt-in / 提议制**：编排器判本篇是否显著受益
    于多角色围审 → 受益则提议用户、确认后才 TeamCreate fan-out；未确认 /
    orchestrator=off → 走既有单 agent 磨稿，与 legacy 字节级等价（详见
    anti-ai-filter.md §审稿 team / autopilot.md）。(c)/(d) 用确定性手构
    合成对而非真实审稿 team 端到端产出——机制/数值门/tier-2 已验证，
    **真实 TeamCreate 三角色 + 编排器汇总 + pass=false 回流 + opt-in
    提议交互留 P6 层或人工验收（成本敏感，不真开 team 烧大额 LLM 审稿
    配额，已在 plan carry-forward 显式登记非静默，与 _run_p1 把真实生图
    延到 P6 同范式）**。任何异常一律转结构化 harness_error，禁裸
    traceback（本仓 subagent 铁律）。"""
    # (a) 复用 P0 门：纯变换 fixture 全 diff_lines==0 + format_layout.py
    #     对 main 零 diff。P5.1 不改 format_layout.py，必须仍零 diff。
    #     直接调 _run_p0(failures)：其内部已是「append 结构化 failures」契约，
    #     P0 漂移/脚本被改/harness_error 会原样进 failures（不重复造轮子，
    #     沿用 P0.5 全部加固：utf-8 / harness_error / git 三态 / diff_lines 布尔）。
    _run_p0(failures)

    # (b) review 结构契约自洽 smoke（手构数据，不读 golden 定稿/review）。
    #     证明 P5.1 升 tier-1 的 _validate_review_items() 工作正常：合法
    #     payload → True；verdicts 非 list / 项非 dict / 缺 role / role 空 /
    #     role 非 str / issues 非 list / 缺 pass / pass 非 bool / pass=1/0
    #     int → ContractError 被捕获。以隔离方式按文件路径 import
    #     scripts/contracts.py（与 _run_p1/p2/p3/p4 同手法），不依赖 cwd /
    #     sys.path 上有 `scripts` 包——裸跑时 `from scripts.contracts import
    #     ...` 会 ModuleNotFoundError。
    try:
        _spec = importlib.util.spec_from_file_location(
            "contracts", SW/"scripts"/"contracts.py")
        _contracts = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_contracts)
        validate_output = _contracts.validate_output
        ContractError = _contracts.ContractError
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts 导入失败：{_err_summary(e)}",
        })
        return

    # 正例：合法结构必须 validate_output → True（pass=False 是审稿不通过
    # 的正常态，也必须放行——结构层不因裁决值拒）。
    try:
        ok = {"verdicts": [
            {"role": "事实核查", "issues": ["第3段价格未标官网信源"],
             "pass": False},
            {"role": "调性审查", "issues": [], "pass": True}]}
        if validate_output("review", ok) is not True:
            failures.append({
                "kind": "contract_smoke_positive_fail", "func": "validate_output",
                "note": "合法 review payload 未返回 True（契约正例回归）",
            })
    except Exception as e:
        # 正例不该抛任何异常（含 ContractError）
        failures.append({
            "kind": "contract_smoke_positive_fail", "func": "validate_output",
            "note": f"合法 review payload 误抛：{_err_summary(e)}",
        })

    # 负例：每个都必须被 ContractError 拒（含 pass 的 bool/int 陷阱）。
    _vbase = {"role": "事实核查", "issues": []}
    neg_cases = [
        ("缺 verdicts",       {}),
        ("verdicts 非 list",  {"verdicts": "notalist"}),
        ("verdict 项非 dict", {"verdicts": ["裸字符串裁决"]}),
        ("verdict 缺 role",   {"verdicts": [{"issues": [], "pass": True}]}),
        ("role 空串",
         {"verdicts": [{"role": "", "issues": [], "pass": True}]}),
        ("role 纯空白",
         {"verdicts": [{"role": "  ", "issues": [], "pass": True}]}),
        ("role 非 str",
         {"verdicts": [{"role": 123, "issues": [], "pass": True}]}),
        ("缺 issues",
         {"verdicts": [{"role": "x", "pass": True}]}),
        ("issues 非 list",
         {"verdicts": [{"role": "x", "issues": "第3段", "pass": True}]}),
        ("缺 pass",           {"verdicts": [dict(_vbase)]}),
        ("pass=1(int)",       {"verdicts": [dict(_vbase, **{"pass": 1})]}),
        ("pass=0(int)",       {"verdicts": [dict(_vbase, **{"pass": 0})]}),
        ("pass 非 bool(str)", {"verdicts": [dict(_vbase, **{"pass": "true"})]}),
        ("pass=None",         {"verdicts": [dict(_vbase, **{"pass": None})]}),
    ]
    for label, bad in neg_cases:
        try:
            validate_output("review", bad)
            # 没抛 = 契约漏判，结构化记 failure
            failures.append({
                "kind": "contract_smoke_negative_fail", "func": "validate_output",
                "case": label,
                "note": f"非法 review payload 未被 ContractError 拒（{label}）",
            })
        except ContractError:
            pass  # 期望：被结构契约挡下
        except Exception as e:
            failures.append({
                "kind": "harness_error", "func": "validate_output",
                "note": f"负例 {label} 抛非 ContractError 异常："
                        f"{_err_summary(e)}",
            })

    # (c) P5 数值阈回归断言：**真实消费** THRESHOLDS["P5"] 的 h2_delta /
    #     para_delta_pct（装饰键转真实消费，照 P1/P3 范式）。
    # 🔴 P3.1 复审硬约束：**依赖数值键构造 fixture 前先一致性自检，命中
    #    即 return**（防裸崩）。h2_delta 必须是 int 0（team 严禁增删
    #    章节——非 0 没有「允许 H2 漂移」的业务语义，且会让合规判据失义）；
    #    para_delta_pct 必须是合理正数 int（段落数允许变化百分比，落
    #    (0,100] 才有意义：≤0 等于禁止任何段落增删过严、>100 等于不设限
    #    无意义）。类型/取值不合理则结构化收口，继续构造依赖它的断言无
    #    意义且不安全（与 _run_p3 (b)/(c) 段 p3_fixture_invalid 自检即
    #    return 同精神，有专属保护测试）。
    h2_delta = THRESHOLDS["P5"]["h2_delta"]
    para_delta_pct = THRESHOLDS["P5"]["para_delta_pct"]
    if (not isinstance(h2_delta, int) or isinstance(h2_delta, bool)
            or h2_delta != 0
            or not isinstance(para_delta_pct, int)
            or isinstance(para_delta_pct, bool)
            or not (0 < para_delta_pct <= 100)):
        failures.append({
            "kind": "p5_fixture_invalid", "func": None,
            "note": f"h2_delta={h2_delta!r}（须 int 0）/ para_delta_pct="
                    f"{para_delta_pct!r}（须 (0,100] 内 int）取值/类型不合理"
                    f"（阈值/契约失配，自检即收口，不构造依赖它的断言）",
        })
        return

    # 合成「baseline 文 / 团队审稿后文」对（确定性手构，不读历史 golden
    # 真实定稿）。baseline = 4 个 H2、每 H2 一段正文 + 一段过渡，共 8 段。
    _BASE = (
        "## 引子\n\n"
        "第一段正文，给出本文要解决的真实困惑与场景。\n\n"
        "承上启下的过渡段，引出下一节。\n\n"
        "## 现状\n\n"
        "第二段正文，铺陈现状与读者最痛的那一刻。\n\n"
        "再一段过渡，把矛盾推到台前。\n\n"
        "## 拆解\n\n"
        "第三段正文，落到具体时间地点人物对话的细节。\n\n"
        "## 收束\n\n"
        "结尾段，给读者明确可执行的态度与下一步。")
    _base_h2 = _h2_count(_BASE)            # = 4（`## ` 行数）
    # 段落基数口径修正（P5.2）：原注释 `# = 8` 是**误标**——`_para_count`
    # 把 4 个 `## ` 标题行也计块，真实 `_para_count(_BASE)` == 10。本门
    # 段落 delta 改用 `_body_para_count`（剔 H2 标题行后的正文段落数），
    # _BASE 真实值 == 6（4 H2 + 6 正文/过渡块，滤掉 4 个 H2 标题块）。
    # 口径决策与依据见 _body_para_count 文档串（H2 结构由 h2_delta 单独
    # 硬守、分母含标题会双门重复计入且失真；不改全局 _para_count，仅
    # P5 局部派生）。`_para_count(_BASE)`(=10) 仅留作口径漂移自检对照。
    _base_para = _body_para_count(_BASE)   # = 6（剔 H2 标题行后正文段落数）

    def _judge(after_md: str):
        """按 h2_delta(0) / para_delta_pct(15) 判一对 baseline→after。
        段落数用 _body_para_count（剔 H2 标题行，口径见其文档串）。
        返回 list[str]（空=合规；非空=精确违因）。"""
        rs = []
        a_h2 = _h2_count(after_md)
        if abs(a_h2 - _base_h2) != h2_delta:   # 真实消费 h2_delta(==0)
            rs.append(
                f"h2_delta 违规：审稿后 H2 数 {a_h2} 与 baseline {_base_h2} "
                f"delta={a_h2 - _base_h2} ≠ 允许 {h2_delta}"
                f"（团队审稿误删/新增章节）")
        a_para = _body_para_count(after_md)    # 剔 H2 标题行的正文段落数
        if _base_para > 0:
            pct = abs(a_para - _base_para) * 100.0 / _base_para
            if pct > para_delta_pct:           # 真实消费 para_delta_pct(15)
                rs.append(
                    f"para_delta_pct 违规：审稿后段落 {a_para} vs baseline "
                    f"{_base_para}，变化 {pct:.0f}% > 允许 {para_delta_pct}%"
                    f"（团队审稿大幅增删段落）")
        return rs

    try:
        # 合规组：H2 不变（仅润色字句、不动结构），段落数不变 → 必须空。
        good_after = _BASE.replace("第一段正文，", "第一段正文（已润色），")
        good_rs = _judge(good_after)
        if good_rs:
            failures.append({
                "kind": "p5_numeric_gate_false_positive", "func": "_judge",
                "note": f"P5 合规组（H2 不变、段落不变）被误判违规："
                        f"{good_rs}",
            })

        # 各违规组：每组只违一个数值维度，必须非空且命中对应键名。
        # ① H2 减少（team 删了「现状」整节及其 2 段）
        h2_minus = (
            "## 引子\n\n"
            "第一段正文，给出本文要解决的真实困惑与场景。\n\n"
            "承上启下的过渡段，引出下一节。\n\n"
            "## 拆解\n\n"
            "第三段正文，落到具体时间地点人物对话的细节。\n\n"
            "## 收束\n\n"
            "结尾段，给读者明确可执行的态度与下一步。")
        # ② H2 增加（team 擅自新增「补充」一节，正文段同步 +1 也算 H2 命中）
        h2_plus = _BASE + "\n\n## 补充\n\n临时加塞的一节正文。"
        # ③ 正文段超 +15%（H2 不变=4，「收束」前狂加 5 段 → body 6→11，+83%）
        para_plus = _BASE.replace(
            "## 收束",
            "新增段一。\n\n新增段二。\n\n新增段三。\n\n"
            "新增段四。\n\n新增段五。\n\n## 收束")
        # ④ 正文段超 −15%（H2 不变=4，删 4 个过渡/正文段 → body 6→2，−67%）
        para_minus = (
            "## 引子\n\n"
            "第一段正文，给出本文要解决的真实困惑与场景。\n\n"
            "## 现状\n\n"
            "## 拆解\n\n"
            "## 收束\n\n"
            "结尾段，给读者明确可执行的态度与下一步。")
        neg = {
            "h2_minus":   ("h2_delta", h2_minus),
            "h2_plus":    ("h2_delta", h2_plus),
            "para_plus":  ("para_delta_pct", para_plus),
            "para_minus": ("para_delta_pct", para_minus),
        }
        for gname, (kw, after) in neg.items():
            rs = _judge(after)
            if not rs:
                failures.append({
                    "kind": "p5_numeric_gate_false_negative",
                    "func": "_judge", "case": gname,
                    "note": f"P5 违规组 {gname} 未被数值门拦下（返回空）",
                })
            elif not any(kw in r for r in rs):
                failures.append({
                    "kind": "p5_numeric_gate_wrong_reason",
                    "func": "_judge", "case": gname,
                    "note": f"P5 违规组 {gname} 报因未命中期望键名 "
                            f"'{kw}'：{rs}",
                })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "_run_p5",
            "note": f"P5 数值阈 fixture 断言异常：{_err_summary(e)}",
        })

    # (d) tier-2 验证门 verify_review_set 行为断言 + 审稿 team 关闭路径
    #     等价断言（P5.2）。用确定性合成 review verdicts fixture
    #     （tests/golden/_synthetic_review/make_fixtures.py 纯 list[dict]、
    #     跑完即弃，不烧任何 LLM 审稿配额）。合规组必须返回空、各违规组
    #     必须精确报对应规则名。仍**不**对历史冻结 golden 定稿/review
    #     做断言（与 docstring 一致；真实 TeamCreate 三角色 + 编排器汇总
    #     + pass=false 回流 + opt-in 提议交互延 P6/人工，plan
    #     carry-forward 显式登记非静默）。**汇总裁决是编排器主轴自做、
    #     绝不外派 subagent**；本门 (d) 是汇总裁决前置对新产出的把关，
    #     不是汇总裁决本身。
    try:
        verify_review_set = _contracts.verify_review_set
    except AttributeError as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"contracts.verify_review_set 缺失：{_err_summary(e)}",
        })
        return

    # 🔴 P3.1 复审硬约束：**依赖阈值/键集构造 fixture 前先一致性自检，
    #    命中即 return**（防裸崩）。verify_review_set 与合成 fixture 都以
    #    contracts._REVIEW_MIN_ROLES（最小覆盖角色数）为单一事实源；
    #    合规 fixture 造 3 个不同 role，若该常量被改高（如 4）而 fixture
    #    没同步，继续跑断言会让「合规组期望空」与实际判定面错位 →
    #    误判门 / 潜在裸崩。fixture 配置既已失效，继续构造依赖它的断言
    #    无意义且不安全，故就此结构化收口（与 (c) 段 p5_fixture_invalid
    #    自检即 return / _run_p4 (c) 段同精神）。本门两 THRESHOLDS 数值键
    #    驱动 (c) 不驱动 (d)，故 (d) 自检对象是 contracts 模块级常量本身
    #    （合规 fixture 造 3 角色 必须 ≥ 下限）。
    _rmin = getattr(_contracts, "_REVIEW_MIN_ROLES", None)
    _RV_FX_ROLES = 3   # 合规 review fixture 覆盖的不同 role 数（单一事实源）
    if (not isinstance(_rmin, int) or isinstance(_rmin, bool)
            or _RV_FX_ROLES < _rmin):
        failures.append({
            "kind": "p5_fixture_invalid", "func": None,
            "note": f"_REVIEW_MIN_ROLES={_rmin!r} 与合规 review fixture "
                    f"（{_RV_FX_ROLES} 角色）失配（tier-2 fixture 阈值/常量"
                    f"失配，自检即收口，不构造依赖它的断言）",
        })
        return

    try:
        _rvfx_spec = importlib.util.spec_from_file_location(
            "review_make_fixtures",
            SW/"tests"/"golden"/"_synthetic_review"/"make_fixtures.py")
        _rvfx = importlib.util.module_from_spec(_rvfx_spec)
        _rvfx_spec.loader.exec_module(_rvfx)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"合成 review fixture 生成器加载失败：{_err_summary(e)}",
        })
        return

    # 期望：每违规组的原因里必须命中给定规则名子串（精确报对应原因）
    rvexpect_kw = {
        "bad_too_few_roles":  "roles_min",          # 违规①
        "bad_fail_no_issues": "fail_needs_issues",  # 违规②
        "bad_inconsistent":   "verdict_consistency",  # 违规③
    }
    try:
        rvgroups = _rvfx.build_groups()

        # 合规组：verify 必须返回空
        comp_reasons = verify_review_set(rvgroups["compliant"])
        if comp_reasons:
            failures.append({
                "kind": "tier2_gate_false_positive",
                "func": "verify_review_set",
                "note": f"review 合规组被误判违规：{comp_reasons}",
            })

        # 各违规组：必须非空且命中对应规则名（精确报对应原因）
        for gname, kw in rvexpect_kw.items():
            rs = verify_review_set(rvgroups[gname])
            if not rs:
                failures.append({
                    "kind": "tier2_gate_false_negative",
                    "func": "verify_review_set", "case": gname,
                    "note": f"review 违规组 {gname} 未被 tier-2 门拦下"
                            f"（返回空）",
                })
            elif not any(kw in r for r in rs):
                failures.append({
                    "kind": "tier2_gate_wrong_reason",
                    "func": "verify_review_set", "case": gname,
                    "note": f"review 违规组 {gname} 报因未命中期望规则名 "
                            f"'{kw}'：{rs}",
                })

        # 审稿 team 关闭路径等价断言（spec §P5 验收⑤：team 未启用 /
        # opt-in 未确认 / orchestrator=off → 与 legacy 单 agent 磨稿
        # 字节级等价）。用**合成对**而非历史 golden 真实定稿：legacy
        # 单 agent 磨稿**不产 review verdicts 集合**（审稿 team 是
        # opt-in 叠加层，关闭即等价于「无 team 产物」）。机器化等价判据：
        # tier-2 审稿门**不对未启用 team 的路径强加**——即 team 关闭场景
        # 不存在 verdicts 新产出可校验，门对「无新产出」不臆判、不报违规
        # （等价于既有单 agent 磨稿不被 P5.2 门改变行为）。这里以「空
        # 新产出 / 未提交 team」两种合成形态断言门不无中生有报违规，
        # 与既有 (a)/(b)/(c) 单 agent 磨稿口径一致（真实 opt-in 提议
        # 交互 + TeamCreate 端到端延 P6/人工，已 carry-forward 登记）。
        # 形态1：team 关闭=无 verdicts 集合提交本门（编排器根本不调
        #        verify_review_set），用空 list 代理「无新产出」——门对空
        #        集合只报「角色覆盖不足」是**有意 fail-safe**，但 team
        #        关闭路径**根本不会调本门**（与 legacy 一致：无 review
        #        阶段产物）。故等价性断言聚焦：本门是**纯函数、无副作用、
        #        不读状态/磁盘**——team 关闭与否，本门不改变 legacy
        #        任何字节（不写 .state.json、不碰定稿）。以「合规 verdicts
        #        重复调两次结果完全一致 + 不抛异常」证明确定性纯函数性质。
        once = verify_review_set(rvgroups["compliant"])
        twice = verify_review_set(rvgroups["compliant"])
        if once != twice or once != []:
            failures.append({
                "kind": "p5_team_off_equivalence_fail",
                "func": "verify_review_set",
                "note": f"审稿 team 关闭等价性破坏：verify_review_set 非"
                        f"确定性纯函数（once={once} twice={twice}，合规组"
                        f"应恒返回 [] 且两次一致；门若有副作用/非确定会"
                        f"令 team 开关影响 legacy 字节级等价）",
            })
        # 形态2：tier-2 门**不进** _OUTPUT_SCHEMA / validate_output——
        # team 关闭时 review 结构契约面（顶层 {verdicts:list}）不变，
        # 单 agent 磨稿不因 P5.2 多出任何 tier-1 强制（与 spec
        # 「team 关闭须与 legacy 字节级等价」一致）。
        if "review" in getattr(_contracts, "_OUTPUT_SCHEMA", {}):
            if _contracts._OUTPUT_SCHEMA["review"] != {"verdicts": list}:
                failures.append({
                    "kind": "p5_team_off_equivalence_fail",
                    "func": None,
                    "note": f"team 关闭等价性破坏：review 顶层 schema 被"
                            f"P5.2 改动={_contracts._OUTPUT_SCHEMA['review']!r}"
                            f"（应仍为 {{'verdicts': list}}，tier-2 门严禁"
                            f"塞 _OUTPUT_SCHEMA）",
                })
        if hasattr(_contracts, "verify_review_set") and (
                "verify_review_set" in getattr(
                    _contracts, "_OUTPUT_SCHEMA", {})):
            failures.append({
                "kind": "p5_team_off_equivalence_fail", "func": None,
                "note": "tier-2 verify_review_set 误塞入 _OUTPUT_SCHEMA"
                        "（污染 tier-1 契约，违反校验层级总纲）",
            })
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": "verify_review_set",
            "note": f"tier-2 review fixture 断言异常：{_err_summary(e)}",
        })

# ====================================================================
# P6 = 主轴阶段纳管 + 零回归终检门（编排重构最后一个门）
# ====================================================================
# 主轴 4 阶段（正文 writing / 排版 layout / BGM music / 发布 publish）
# 由编排器**单线程**执行，P6.1 只给每个 reference 顶部加**恰一行**纳管
# 引用（指向 orchestration.md），**正文逻辑一字不改**。故 P6 门**不
# 重跑 LLM 比 golden 定稿字节**——LLM 产出不确定、不可单测（与
# _run_p1..p5 把真实端到端延 P6/人工同精神，真实人审清单见
# docs/superpowers/P6-acceptance-checklist.md）。P6 门改以**结构等价**
# 三断言机器化证明「主轴行为零变更」：
#
#   ① 纯变换 fixture 行为证明（复用 _run_p0）：format_layout 全部纯
#      函数对冻结 expected diff_lines==0 + format_layout.py 对 main
#      零 diff（_run_p0 内已含此守卫）。这是"主轴排版阶段可执行流水线
#      行为未漂移"的机器证据。
#   ② 脚本 + 主轴 reference git 守卫：
#      (b1) format_layout.py 对 main 零 diff（由 ① 的 _run_p0 覆盖，
#           此处再以 THRESHOLDS["P6"]["format_layout_git_clean"] 真实
#           消费 + 显式 numstat 二次确认 deletions==0）。
#      (b2) pipeline.py 对 main 仅 P0.2 已审计纯增量：deletions==0 且
#           insertions ≤ pipeline_inc_max（实测 21，阈 30）。
#      (b3) 主轴 4 reference 对 main 仅"加 ≤2 行纳管引用"：每文件
#           deletions==0 且 insertions ≤ spine_ref_ins_max(=2)。
#      —— 三者共同证明：主轴正文/排版/BGM/发布的**既有逻辑零删改**，
#      只追加了不可执行的纳管文字。
#   ③ orchestrator on/off 命令轨迹结构等价（**非重跑 LLM 比字节**）：
#      可解释判据 —— 主轴阶段调用的脚本命令轨迹由两部分构成：
#        (i)  可执行脚本本体（format_layout.py / pipeline.py）；
#        (ii) pipeline.py 的 orchestrator 开关对 .state.json 的写面。
#      结构等价 ⇔ ①②已证 (i) 对 main 零行为变更（format_layout 零
#      diff、pipeline 纯增量无删改）；再对 (ii) 做结构断言：
#      orchestrator on/off 切换**只影响 orchestrator/state_writer 两个
#      新增状态键，绝不改任何既有阶段字段/命令序列**。以 pipeline.py
#      的 cmd_orchestrator 源码做结构比对（AST 级：函数体只 set 这两
#      键 + save_state，无其它 state 赋值/无调既有 cmd_* / 无 STAGE_ORDER
#      改写），证明 on 与 off 下主轴阶段的脚本命令序列/参数/产物路径
#      约定**逐字一致**（off=legacy，与既有完全相同）。LLM 文本阶段
#      （正文/磨稿）的轨迹等价由 ②(b3) 主轴 SOP 文本零删改 + 真实
#      人审清单兜底（合成 fixture 覆盖不了 LLM，已 carry-forward 登记）。
#
# 任一失败 append 结构化 failures（沿用 P0.5 全部加固：utf-8 /
# harness_error / git 三态/numstat None 兜底 / 依赖前自检即 return /
# diff_lines 布尔；**绝不回退、绝不裸崩、绝不静默吞错**）。
def _run_p6(failures: list):
    """P6 主轴纳管 + 零回归终检门。机制见上方文档串。任何异常一律转
    结构化 harness_error，禁裸 traceback（本仓 subagent 铁律）。"""
    # ── 断言 ①：纯变换 fixture 行为证明（复用 _run_p0；其内部已是
    #    「append 结构化 failures」契约，含 format_layout 纯函数对冻结
    #    expected diff_lines==0 + format_layout.py 对 main 零 diff 守卫，
    #    沿用 P0.5 全部加固）。不重复造轮子。
    _run_p0(failures)

    # ── 依赖阈值前先一致性自检，命中即 return（P3.1 复审硬约束防裸崩，
    #    与 _run_p3/p4/p5 自检即 return 同精神）。P6 三阈值：两个非负 int
    #    上界 + 一个 True 旗标；类型/取值不合理则结构化收口，继续构造
    #    依赖它的断言无意义且不安全。
    th = THRESHOLDS["P6"]
    spine_ins_max = th.get("spine_ref_ins_max")
    pipe_inc_max = th.get("pipeline_inc_max")
    fl_clean_flag = th.get("format_layout_git_clean")
    if (not isinstance(spine_ins_max, int) or isinstance(spine_ins_max, bool)
            or spine_ins_max < 0
            or not isinstance(pipe_inc_max, int) or isinstance(pipe_inc_max, bool)
            or pipe_inc_max < 0
            or fl_clean_flag is not True):
        failures.append({
            "kind": "p6_threshold_invalid", "func": None,
            "note": f"P6 阈值取值/类型不合理："
                    f"spine_ref_ins_max={spine_ins_max!r}（须 ≥0 int）/ "
                    f"pipeline_inc_max={pipe_inc_max!r}（须 ≥0 int）/ "
                    f"format_layout_git_clean={fl_clean_flag!r}（须严格 True）"
                    f"（阈值/契约失配，自检即收口，不构造依赖它的断言）",
        })
        return

    # ── 断言 ②：脚本 + 主轴 reference git 守卫（numstat：deletions==0
    #    硬约束 + insertions 上界）。numstat None = ref/git 不可用或二进制
    #    → harness_error（绝不伪报"被改"，与 _git_guard 三态同精神）。
    # (b1) format_layout.py 对 main 必须零 diff（真实消费
    #      format_layout_git_clean 旗标；_run_p0 已用 _git_guard 三态守过，
    #      此处再以 numstat 显式二次确认 ins==0 且 del==0，双保险）。
    fl_ns = _git_numstat("scripts/format_layout.py")
    if fl_ns is None:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": "format_layout.py numstat 不可用（main ref/git 不可用或"
                    "二进制），git 守卫无法判定（非'脚本被改'）",
        })
    elif fl_ns != (0, 0):
        failures.append({
            "kind": "p6_format_layout_drift",
            "path": "scripts/format_layout.py",
            "note": f"P6 期 format_layout.py 对 main 必须零 diff，实测 "
                    f"+{fl_ns[0]}/-{fl_ns[1]}（主轴排版可执行流水线严禁"
                    f"任何行为变更）",
        })

    # (b2) pipeline.py：deletions 必须 0，insertions ≤ pipeline_inc_max
    #      （P0.2 已审计纯增量 —— orchestrator 开关 + state_writer 标记，
    #      不改任何既有阶段语义；真实消费 pipeline_inc_max）。
    pp_ns = _git_numstat("scripts/pipeline.py")
    if pp_ns is None:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": "pipeline.py numstat 不可用，git 守卫无法判定"
                    "（非'脚本被改'）",
        })
    else:
        pp_ins, pp_del = pp_ns
        if pp_del != 0:
            failures.append({
                "kind": "p6_pipeline_has_deletions",
                "path": "scripts/pipeline.py",
                "note": f"pipeline.py 对 main 有 {pp_del} 行删除（P0.2 应为"
                        f"**纯增量**：删除既有行=改既有阶段语义，零回归门"
                        f"硬红线）",
            })
        if pp_ins > pipe_inc_max:
            failures.append({
                "kind": "p6_pipeline_increment_exceeded",
                "path": "scripts/pipeline.py",
                "note": f"pipeline.py 对 main 新增 {pp_ins} 行 > 上界 "
                        f"{pipe_inc_max}（超出 P0.2 已审计纯增量规模，"
                        f"疑似偷塞主轴阶段语义，需人工复审）",
            })

    # (b3) 主轴 4 reference：每文件 deletions 必须 0，insertions ≤
    #      spine_ref_ins_max（纳管=1 行 + 1 空行 ≤ 2）。删除>0 = 改了
    #      既有规则/步骤/字，P6 红线（正文逻辑一字不改）。
    spine_refs = ("writing.md", "layout.md", "music.md", "publish.md")
    for ref in spine_refs:
        rel = f"references/{ref}"
        ns = _git_numstat(rel)
        if ns is None:
            failures.append({
                "kind": "harness_error", "func": None,
                "note": f"主轴 reference {ref} numstat 不可用，git 守卫"
                        f"无法判定（非'被改'）",
            })
            continue
        ins, dele = ns
        if dele != 0:
            failures.append({
                "kind": "p6_spine_ref_logic_changed",
                "path": rel,
                "note": f"主轴 reference {ref} 对 main 有 {dele} 行删除"
                        f"（P6 红线：主轴正文/排版/BGM/发布既有逻辑一字"
                        f"不改，只允许加纳管引用行）",
            })
        if ins > spine_ins_max:
            failures.append({
                "kind": "p6_spine_ref_excess_insertions",
                "path": rel,
                "note": f"主轴 reference {ref} 对 main 新增 {ins} 行 > "
                        f"上界 {spine_ins_max}（仅允许加 ≤{spine_ins_max} "
                        f"行纳管引用：1 引用行 + 1 空行）",
            })

    # ── 断言 ③：orchestrator on/off 命令轨迹结构等价（非重跑 LLM 比
    #    字节）。可解释判据见上方文档串。①② 已证可执行脚本本体
    #    (format_layout/pipeline) 对 main 零行为变更；此处对 pipeline.py
    #    的 orchestrator 开关写面做 **AST 级结构断言**：cmd_orchestrator
    #    函数体只允许「load_state → 写 orchestrator/state_writer 两键 →
    #    save_state」，绝不调任何既有 cmd_*（不改既有阶段命令序列）、
    #    不改 STAGE_ORDER、不给 state 写其它既有阶段字段。这证明
    #    orchestrator=on 与 off 时主轴阶段的脚本命令序列/参数/产物路径
    #    约定**逐字一致**（off ⇔ legacy）。
    try:
        import ast
        pp_path = SW/"scripts"/"pipeline.py"
        pp_src = pp_path.read_text(encoding="utf-8")
        tree = ast.parse(pp_src)
    except Exception as e:
        failures.append({
            "kind": "harness_error", "func": None,
            "note": f"pipeline.py AST 解析失败（断言③ 无法判定）："
                    f"{_err_summary(e)}",
        })
        return

    cmd_orch = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_orchestrator":
            cmd_orch = node
            break
    if cmd_orch is None:
        failures.append({
            "kind": "p6_orchestrator_switch_missing", "func": None,
            "note": "pipeline.py 缺 cmd_orchestrator（orchestrator 回滚"
                    "开关）—— orchestrator=off 回 legacy 的命令轨迹等价"
                    "无从证明（编排重构核心契约缺失）",
        })
        return

    # 结构判据：扫 cmd_orchestrator 函数体所有节点。
    #  - 允许：load_state(...) 调用；save_state(...) 调用；对
    #    state["orchestrator"] / state["state_writer"] 的下标赋值；
    #    本地变量赋值（state = load_state(...)）；print（用户可见提示）。
    #  - 违规：① 对 state 写**除 orchestrator/state_writer 外**的任何
    #    既有键（=动了既有阶段字段，会让 on/off 影响 legacy 行为）；
    #    ② 调用任何 cmd_* 既有命令函数（=改既有阶段命令序列）；
    #    ③ 引用/改写 STAGE_ORDER（=改主轴阶段时序）。
    _ALLOWED_STATE_KEYS = {"orchestrator", "state_writer"}
    structural_violations = []
    for n in ast.walk(cmd_orch):
        # ① state 下标赋值键白名单
        if isinstance(n, ast.Assign):
            for tgt in n.targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "state"):
                    key = None
                    sl = tgt.slice
                    if isinstance(sl, ast.Constant):
                        key = sl.value
                    if key not in _ALLOWED_STATE_KEYS:
                        structural_violations.append(
                            f"cmd_orchestrator 给 state[{key!r}] 赋值"
                            f"（仅允许写 {sorted(_ALLOWED_STATE_KEYS)}；"
                            f"动既有阶段字段会让 on/off 影响 legacy 行为）")
        # ②③ 调用既有 cmd_* / 引用 STAGE_ORDER
        if isinstance(n, ast.Call):
            fn = n.func
            fname = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if (fname and fname.startswith("cmd_")
                    and fname != "cmd_orchestrator"):
                structural_violations.append(
                    f"cmd_orchestrator 调既有命令函数 {fname}（=改既有"
                    f"阶段命令序列，破坏 on/off 轨迹结构等价）")
        if isinstance(n, ast.Name) and n.id == "STAGE_ORDER":
            structural_violations.append(
                "cmd_orchestrator 引用/改写 STAGE_ORDER（=动主轴阶段"
                "时序，破坏 orchestrator=off ⇔ legacy 等价）")

    if structural_violations:
        failures.append({
            "kind": "p6_orchestrator_trace_not_equivalent",
            "func": "cmd_orchestrator",
            "note": "orchestrator on/off 命令轨迹结构不等价："
                    + "；".join(sorted(set(structural_violations))),
        })

    # 正向最小性自证：cmd_orchestrator 必须确实写到这两个键（否则开关
    # 形同虚设，off 无法切回 legacy）——以源码字符串结构断言两键都被
    # 赋值（AST 已遍历，这里收口确认"既不多写、也不漏写"）。
    assigned_keys = set()
    for n in ast.walk(cmd_orch):
        if isinstance(n, ast.Assign):
            for tgt in n.targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "state"
                        and isinstance(tgt.slice, ast.Constant)):
                    assigned_keys.add(tgt.slice.value)
    missing_keys = _ALLOWED_STATE_KEYS - assigned_keys
    if missing_keys:
        failures.append({
            "kind": "p6_orchestrator_switch_incomplete",
            "func": "cmd_orchestrator",
            "note": f"orchestrator 开关未写必需键 {sorted(missing_keys)}"
                    f"（开关形同虚设，orchestrator=off 无法切回 legacy，"
                    f"回滚契约不成立）",
        })

USAGE = (f"用法: python regression_baseline.py <phase> [slug]\n"
         f"  <phase> ∈ {{{', '.join(VALID_PHASES)}}}\n"
         f"  P0 = 零行为变更门（纯变换 fixture + 脚本 git 守卫）")

def main():
    # argv/phase 兜底：无参或未知 phase 打 usage 并 sys.exit(2)，不裸 IndexError/KeyError
    if len(sys.argv) < 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    phase = sys.argv[1]
    if phase not in THRESHOLDS:
        print(f"未知 phase: {phase!r}\n{USAGE}", file=sys.stderr)
        sys.exit(2)

    th = THRESHOLDS[phase]
    failures = []

    if phase == "P0":
        _run_p0(failures)
    elif phase == "P1":
        # P1.1：结构契约 + 复用 P0 门 + 契约自洽 smoke（已实装）。
        _run_p1(failures)
    elif phase == "P2":
        # P2.1：research 结构契约 + 复用 P0 门 + 契约自洽 smoke；
        # P2.2：+ tier-2 verify_research_set 合成 fixture 行为断言（已实装）。
        _run_p2(failures)
    elif phase == "P3":
        # P3.1：content_enhance 结构契约 + 复用 P0 门 + 契约自洽 smoke
        # （strategies_present 真实消费）；
        # P3.2：+ tier-2 verify_content_enhance_set 合成 fixture 行为断言
        # （合并关由编排器主轴自做，本门是合并后对新产出的把关，已实装）。
        _run_p3(failures)
    elif phase == "P4":
        # P4.1：cover 结构契约 + 复用 P0 门 + 契约自洽 smoke
        # （candidates[].path 非空 str + selected 非空 str）；
        # P4.2：+ tier-2 verify_cover_set 合成 PNG fixture 行为断言
        # （selected∈candidates / ≥2 候选 / 图存在 / 1K / 2.35:1 / 近 3 篇
        # 回避；选优由编排器主轴裁量不外派，本门是选优前置把关，已实装）。
        _run_p4(failures)
    elif phase == "P5":
        # P5.1：review 结构契约（verdicts[] role/issues/pass 严格 bool 排
        # int）+ 复用 P0 门 + 契约自洽 smoke；真实消费 THRESHOLDS["P5"]
        # 的 h2_delta(0)/para_delta_pct(15) 做团队审稿前后 H2·正文段落
        # delta 回归断言（段落基数 P5.2 修正为 _body_para_count 剔 H2
        # 标题行；依赖数值键构造 fixture 前先一致性自检即 return 防裸崩）。
        # P5.2：+ tier-2 verify_review_set 合成 fixture 行为断言（3 role
        # 覆盖 / pass=false 须带 issues / 裁决一致性）+ 审稿 team 关闭
        # 路径等价断言（opt-in 提议制：未确认/orchestrator=off 走 legacy
        # 单 agent 磨稿、字节级等价）；汇总裁决由编排器主轴自做不外派，
        # 本门是汇总裁决前置把关。真实 TeamCreate 三角色端到端延 P6/人工。
        _run_p5(failures)
    else:
        # P6.1：主轴 4 阶段（正文/排版/BGM/发布）纳管 + 零回归终检门。
        # ① 复用 _run_p0 纯变换 fixture 行为证明（含 format_layout.py 对
        #    main 零 diff 守卫）；② 脚本 + 主轴 reference git numstat 守卫
        #    （format_layout 零 diff / pipeline 纯增量 deletions==0 /
        #    主轴 4 ref 仅加 ≤2 行纳管 deletions==0）；③ orchestrator
        #    on/off 命令轨迹结构等价（cmd_orchestrator AST 级结构断言，
        #    非重跑 LLM 比字节）。真实端到端/人审延 P6-acceptance-
        #    checklist.md（合成 fixture 覆盖不了 LLM，已显式登记非静默）。
        _run_p6(failures)

    print(json.dumps({"phase": phase, "thresholds": th, "failures": failures},
                      ensure_ascii=False))
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
