"""fan-out 阶段进/出契约校验。纯函数，无副作用，不碰状态文件。"""

class ContractError(Exception):
    pass

_BUNDLE_REQUIRED = ("sansheng_context", "iron_rules", "article_meta", "stage_input")

# 每个 fan-out 阶段输出 schema：必需键 -> 类型
_OUTPUT_SCHEMA = {
    "research":        {"findings": list, "sources": list},  # (P2.1) sources[] 每项 dict 且非空 str url 升 tier-1（_validate_research_items）；findings item / source 其它字段属 tier-2
    "content_enhance": {"strategies": dict},          # (P3.1) strategies 含且仅 4 键 angle/density/detail/texture 且值非空 str 升 tier-1（_validate_content_enhance）；各策略文本质量/去重/不矛盾/与正文融合属 tier-2（P3.2）
    "infographic":     {"images": list},              # [{path,aspect,bytes}]
    "cover":           {"candidates": list, "selected": str},
    "review":          {"verdicts": list},            # (P5.1) verdicts[] 每项 dict 且含非空 str role / list issues / 严格 bool pass 升 tier-1（_validate_review_items；pass 排除 int，与 bytes 排除 bool 镜像）；issues 质量/role 合法性/裁决一致性/H2·段落 delta 属 tier-2（P5.2 审稿 team）
}

# ===== 【第 1 节】tier-1 入场/出场校验 =====
def validate_bundle(bundle: dict) -> bool:
    missing = [k for k in _BUNDLE_REQUIRED if k not in bundle]
    if missing:
        raise ContractError(f"bundle missing keys: {missing}")
    if not isinstance(bundle["iron_rules"], list) or not bundle["iron_rules"]:
        raise ContractError("iron_rules must be non-empty list")
    return True

def _validate_infographic_items(images: list) -> None:
    """infographic item 级 tier-1 **结构**强校验（P1.1）。
    只管结构：每项 dict，`path`/`aspect` 非空 str，`bytes` 严格 int。
    ⚠️ 按「校验层级总纲」，aspect 枚举(9:16/16:9/1:1)、张数≥4、
       压缩后 ≤2MB、开篇/中间/结尾构成属 **tier-2 语义关**，由 P1.2
       新产出验证门强制，**不塞进结构契约**（塞了会污染契约且与总纲自相矛盾）。
    🪤 bool/int 陷阱：isinstance(True, int) == True（bool 是 int 子类），
       故 bytes 用 `isinstance(v, int) and not isinstance(v, bool)`，
       bytes=True/False 必须判非法。"""
    for i, item in enumerate(images):
        if not isinstance(item, dict):
            raise ContractError(
                f"[infographic] images[{i}] expected dict, got {type(item).__name__}")
        for f in ("path", "aspect"):
            if f not in item:
                raise ContractError(f"[infographic] images[{i}] missing key: {f}")
            v = item[f]
            if not isinstance(v, str) or not v.strip():
                raise ContractError(
                    f"[infographic] images[{i}].{f} expected non-empty str, "
                    f"got {type(v).__name__!s}={v!r}")
        if "bytes" not in item:
            raise ContractError(f"[infographic] images[{i}] missing key: bytes")
        b = item["bytes"]
        # 显式排除 bool：必须严格 int（isinstance(True,int)==True 陷阱）
        if not (isinstance(b, int) and not isinstance(b, bool)):
            raise ContractError(
                f"[infographic] images[{i}].bytes expected strict int "
                f"(bool excluded), got {type(b).__name__!s}={b!r}")

_CE_STRATEGY_KEYS = ("angle", "density", "detail", "texture")

def _validate_content_enhance(strategies: dict) -> None:
    """content_enhance item 级 tier-1 **结构**强校验（P3.1）。
    只管结构：`strategies` 是 dict（顶层 schema 已保证），且**含且仅认**
    这 4 键 angle/density/detail/texture，每个值为**非空 str**（strip 后非空）。
    缺任一键 raise、有多余键 raise、值空/非 str raise。
    ⚠️ 按「校验层级总纲」，各策略文本的质量/去重/不矛盾/与正文融合、
       是否套话、长度是否合理属 **tier-2 语义关**，由 P3.2 合并关/语义门
       对 **新产出** 强制、**不追溯历史冻结 golden**（历史文章无统一
       content_enhance 产物），**不塞进结构契约**（塞了会污染契约且与
       总纲自相矛盾）。故本函数**只**校验 4 键齐全 + 值非空 str 结构。"""
    keys = set(strategies.keys())
    want = set(_CE_STRATEGY_KEYS)
    missing = want - keys
    if missing:
        raise ContractError(
            f"[content_enhance] strategies missing keys: "
            f"{sorted(missing)}（须含且仅 {list(_CE_STRATEGY_KEYS)}）")
    extra = keys - want
    if extra:
        raise ContractError(
            f"[content_enhance] strategies has unknown keys: "
            f"{sorted(extra)}（仅认 {list(_CE_STRATEGY_KEYS)}）")
    for k in _CE_STRATEGY_KEYS:
        v = strategies[k]
        if not isinstance(v, str) or not v.strip():
            raise ContractError(
                f"[content_enhance] strategies.{k} expected non-empty str, "
                f"got {type(v).__name__!s}={v!r}")

def _validate_research_items(sources: list) -> None:
    """research item 级 tier-1 **结构**强校验（P2.1）。
    只管结构：`sources` 每项 dict 且含非空 str `url`。
    ⚠️ 按「校验层级总纲」，findings item 结构（claim/support/confidence）、
       source 的 title/tier/accessed、「版本/价格/时间类 finding 至少 1 条
       官网级 source」属 **tier-2 语义关**，由 P2.2 验证门对 **新产出**
       强制、**不追溯历史冻结 golden**，**不塞进结构契约**（塞了会污染
       契约且与总纲自相矛盾）。故本函数**只**校验 sources[].url 结构，
       **不**碰 findings item、**不**碰 source 其它字段。"""
    for i, item in enumerate(sources):
        if not isinstance(item, dict):
            raise ContractError(
                f"[research] sources[{i}] expected dict, got {type(item).__name__}")
        if "url" not in item:
            raise ContractError(f"[research] sources[{i}] missing key: url")
        u = item["url"]
        if not isinstance(u, str) or not u.strip():
            raise ContractError(
                f"[research] sources[{i}].url expected non-empty str, "
                f"got {type(u).__name__!s}={u!r}")

def _validate_cover(payload: dict) -> None:
    """cover item 级 tier-1 **结构**强校验（P4.1）。
    只管结构：`candidates` 每项 dict 且含非空 str `path`；`selected`
    为**非空 str**（strip 后非空）。
    ⚠️ 按「校验层级总纲」，`selected ∈ candidates 路径`是**跨字段**约束、
       图片实际存在/尺寸/风格/**1K 分辨率**/近 3 篇封面回避属 **tier-2
       语义关**，由 P4.2 验证门对 **新产出** 强制、**不追溯历史冻结
       golden**（历史 3 篇封面各异、风格/比例形态不统一），**不塞进结构
       契约**（塞了会污染契约且与总纲自相矛盾）。故本函数**只**校验
       candidates[].path 结构 + selected 非空 str，**不**做跨字段比对、
       **不**碰磁盘/图片。"""
    candidates = payload["candidates"]
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise ContractError(
                f"[cover] candidates[{i}] expected dict, "
                f"got {type(item).__name__}")
        if "path" not in item:
            raise ContractError(f"[cover] candidates[{i}] missing key: path")
        p = item["path"]
        if not isinstance(p, str) or not p.strip():
            raise ContractError(
                f"[cover] candidates[{i}].path expected non-empty str, "
                f"got {type(p).__name__!s}={p!r}")
    sel = payload["selected"]
    # 顶层 schema 已保证 selected 是 str；这里 tier-1 再要求**非空**
    # （空串/纯空白 selected 无意义，结构层即拒；是否 ∈ candidates 属 tier-2）。
    if not isinstance(sel, str) or not sel.strip():
        raise ContractError(
            f"[cover] selected expected non-empty str, "
            f"got {type(sel).__name__!s}={sel!r}")

def _validate_review_items(verdicts: list) -> None:
    """review item 级 tier-1 **结构**强校验（P5.1）。
    只管结构：`verdicts` 每项 dict，含非空 str `role`、list `issues`、
    **严格 bool** `pass`。缺项 / 类型错 / role 空 / pass 非 bool /
    issues 非 list 一律 raise。
    🪤 bool/int 陷阱：isinstance(True, int) == True（bool 是 int 子类），
       故 `pass` 用 `isinstance(b, bool)` 直判，**不复用 int 分支**——
       与 infographic.bytes 严格 int 是镜像关系：bytes 要排除 bool，
       pass 要的就是真 bool（int 1/0 必须判非法）。`pass` 是 Python
       关键字，取值统一用 `item["pass"]`（绝不写 `item.pass` 属性名）。
    ⚠️ 按「校验层级总纲」，issues 内容质量 / role 是否合法审稿角色 /
       裁决与正文一致性 / pass=false 时 issues 是否非空可定位 / H2·段落
       delta 属 **tier-2 语义关**，由 P5.2 审稿 team 对 **新产出** 强制、
       **不追溯历史冻结 golden**（历史无统一 review 产物），**不塞进结构
       契约**（塞了会污染契约且与总纲自相矛盾）。故本函数**只**校验
       role 非空 str + issues 是 list + pass 严格 bool 结构。"""
    for i, item in enumerate(verdicts):
        if not isinstance(item, dict):
            raise ContractError(
                f"[review] verdicts[{i}] expected dict, "
                f"got {type(item).__name__}")
        if "role" not in item:
            raise ContractError(f"[review] verdicts[{i}] missing key: role")
        r = item["role"]
        if not isinstance(r, str) or not r.strip():
            raise ContractError(
                f"[review] verdicts[{i}].role expected non-empty str, "
                f"got {type(r).__name__!s}={r!r}")
        if "issues" not in item:
            raise ContractError(f"[review] verdicts[{i}] missing key: issues")
        iss = item["issues"]
        if not isinstance(iss, list):
            raise ContractError(
                f"[review] verdicts[{i}].issues expected list, "
                f"got {type(iss).__name__!s}={iss!r}")
        if "pass" not in item:
            raise ContractError(f"[review] verdicts[{i}] missing key: pass")
        # `pass` 关键字用下标取值（非属性名）。严格 bool：显式 isinstance
        # bool（int 1/0/True-int 全判非法——与 bytes 排除 bool 互为镜像）。
        p = item["pass"]
        if not isinstance(p, bool):
            raise ContractError(
                f"[review] verdicts[{i}].pass expected strict bool "
                f"(int excluded), got {type(p).__name__!s}={p!r}")

def validate_output(stage: str, payload: dict) -> bool:
    if stage not in _OUTPUT_SCHEMA:
        raise ContractError(f"unknown stage: {stage}")
    for key, typ in _OUTPUT_SCHEMA[stage].items():
        if key not in payload:
            raise ContractError(f"[{stage}] output missing key: {key}")
        if not isinstance(payload[key], typ):
            raise ContractError(f"[{stage}] key {key} expected {typ.__name__}")
    # infographic：images 顶层已校验是 list（上方循环），再做 item 级结构强校验。
    # 其它 stage 的 item 级校验保持不变（仍属语义关，未升 tier-1）。
    if stage == "infographic":
        _validate_infographic_items(payload["images"])
    # research：sources 顶层已校验是 list（上方循环），再做 item 级结构强校验
    # （仅 sources[].url；findings item / source 其它字段属 tier-2，不在此校验）。
    if stage == "research":
        _validate_research_items(payload["sources"])
    # content_enhance：strategies 顶层已校验是 dict（上方循环），再做 item 级
    # 结构强校验（4 键 angle/density/detail/texture 齐全且仅认、值非空 str；
    # 文本质量/去重/不矛盾/与正文融合属 tier-2，不在此校验）。
    if stage == "content_enhance":
        _validate_content_enhance(payload["strategies"])
    # cover：candidates 顶层已校验是 list、selected 是 str（上方循环），
    # 再做 item 级结构强校验（candidates[].path 非空 str + selected 非空 str；
    # selected∈candidates / 图存在 / 1K / 风格属 tier-2，不在此校验）。
    if stage == "cover":
        _validate_cover(payload)
    # review：verdicts 顶层已校验是 list（上方循环），再做 item 级结构强
    # 校验（role 非空 str + issues 是 list + pass 严格 bool；issues 内容
    # 质量 / role 合法性 / 裁决一致性 / H2·段落 delta 属 tier-2，不在此校验）。
    if stage == "review":
        _validate_review_items(payload["verdicts"])
    return True


# ===== 【第 2 节】信息图集合门 P1.2 =====
# ====================================================================
# tier-2 信息图集合验证门（P1.2）—— 对 **新生成** 信息图强制，
# **不追溯历史冻结 golden**（34/36/40-樊登 历史合法但不符新规）。
#
# ⚠️ 这是 tier-2 **语义关**，与 tier-1 结构契约 validate_output 分开：
#   - 故意 **不** 写进 `_OUTPUT_SCHEMA` / `validate_output`
#     （塞进去会污染契约且与 agent-contracts.md「校验层级总纲」自相矛盾）。
#   - 由编排器在 fan-out 收齐后、对 **新产出** 单独调本函数把关。
#
# 纯函数：只读磁盘 PNG 像素 + 入参 bytes，无写副作用、不碰 .state.json。
# 返回 list[str]：每条一个违规原因；空 list = 通过。任何 IO/解码异常
# 都转成结构化原因字符串（绝不裸抛），契合本仓 subagent「禁裸崩」铁律。
#
# === 判定规则（与 agent-contracts.md / image-routing.md 对齐）===
# ① 张数 ≥4
# ② 构成 = 开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1
#    （位置语义：images[0]/images[-1] 必须 9:16；中间段 ≥2 张 16:9）
# ③ 每张 aspect ∈ {9:16, 16:9, 1:1}（由**实际像素**判，非入参声明）
# ④ 压缩后 bytes ≤ 2_000_000
# ⑤ 1K 分辨率：长边落在 [900, 1200]
#
# === aspect 像素判定与 ±2px 容差 ===
# 不信任入参 `aspect` 字段（可能与磁盘实际不符——历史踩坑）；用 Pillow
# 读真实 (w,h)，对三个目标比例分别算「按短边推出的理想长边」，
# 若实际长边与理想长边偏差 ≤ 2px 即判定命中该比例。2px 容差吸收
# baoyu/压缩链路的取整误差（如 9:16 在 1024 高下理想宽 576，得到 577/578
# 仍应判 9:16），同时仍能把 3:4(768×1024) 这类非三枚举挡下。
#
# === 1K 容差带 [900, 1200] 的依据 ===
# 「1K」标称 = 1024px 长边。横切规范要求所有 baoyu-* 生图统一长边≈1024。
# 真实生成器极少恰好 1024：常见落点 960/1000/1024/1080/1152。下界 900
# （≈1024−12%）排掉缩略图级小图；上界 1200（≈1024+17%）既容纳 1080/1152，
# 又能把历史 2k 长卷（40-樊登 长边 ≥1500）这类「非 1K」产物挡在门外。
# matplotlib 数据图表（dpi=300）不走本门——它们由 image-routing 数据图
# 防幻觉铁律单独约束，编排器对数据图单元不调 verify_infographic_set。
# ====================================================================

# name -> (w_ratio, h_ratio)。**含朝向**：9:16 是竖图(h>w)、16:9 是横图(w>h)，
# 二者长短边比例同为 16:9，仅靠「长/短边比」无法区分朝向 —— 必须用
# (w,h) 原始朝向判定，否则 1024x576 会被先匹配到 9:16（dict 序）误判。
_ASPECT_RATIOS = {
    "9:16": (9, 16),       # 竖图：宽:高 = 9:16
    "16:9": (16, 9),       # 横图：宽:高 = 16:9
    "1:1":  (1, 1),
}
_ASPECT_TOL_PX = 2        # 长边容差（吸收取整/压缩误差）
_K1_MIN, _K1_MAX = 900, 1200   # 1K 长边容差带（依据见上）
_MAX_BYTES = 2_000_000         # 压缩后单张上限


def _classify_aspect(w: int, h: int):
    """按实际像素把 (w,h) 归到三枚举之一；不命中返回 None。
    判据：对每个候选比例，由短边推理想长边，实际长边偏差 ≤ ±2px 即命中。"""
    # 含朝向判定：用 (rw,rh) 原始宽高比，由**较大边**定基推另一边理想值，
    # 与实际比 ±2px（取大边定基避免误差放大）。9:16(竖) 与 16:9(横)
    # 因此被正确区分：1024x576 只命中 16:9，576x1024 只命中 9:16。
    for name, (rw, rh) in _ASPECT_RATIOS.items():
        if rw >= rh:                       # 该比例为横/方：宽 ≥ 高
            ideal_h = w * rh / rw
            if abs(h - ideal_h) <= _ASPECT_TOL_PX and w >= h - _ASPECT_TOL_PX:
                return name
        else:                              # 该比例为竖：高 > 宽
            ideal_w = h * rw / rh
            if abs(w - ideal_w) <= _ASPECT_TOL_PX and h >= w - _ASPECT_TOL_PX:
                return name
    return None


def verify_infographic_set(images: list) -> list:
    """tier-2：校验**新生成**信息图集合。返回违规原因 list（空=通过）。
    入参 images：[{path, aspect, bytes}, ...]（与 _OUTPUT_SCHEMA infographic 同形）。
    path 指向磁盘真实 PNG；本函数按真实像素判 aspect/1K，按入参 bytes 判 ≤2MB。"""
    reasons = []

    if not isinstance(images, list):
        return [f"images 必须是 list，收到 {type(images).__name__}"]

    # ① 张数 ≥4
    n = len(images)
    if n < 4:
        reasons.append(f"张数不足：需 ≥4 张，实际 {n} 张（tier-2 count_min）")

    # 逐张读像素 + 判 aspect / 1K / bytes
    per_aspect = []   # 与 images 等长；读不到的位置填 None
    for i, item in enumerate(images):
        if not isinstance(item, dict):
            reasons.append(f"images[{i}] 不是 dict，无法校验")
            per_aspect.append(None)
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            reasons.append(f"images[{i}].path 缺失或非法")
            per_aspect.append(None)
            continue

        # 读真实像素（IO/解码异常一律转结构化原因，绝不裸抛）
        try:
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
        except FileNotFoundError:
            reasons.append(f"images[{i}] 文件不存在/缺失：{path}")
            per_aspect.append(None)
            continue
        except Exception as e:
            reasons.append(
                f"images[{i}] 读取失败（{type(e).__name__}）：{path}")
            per_aspect.append(None)
            continue

        # ③ aspect ∈ 三枚举（按实际像素，±2px 容差）
        kind = _classify_aspect(w, h)
        per_aspect.append(kind)
        if kind is None:
            reasons.append(
                f"images[{i}] aspect 非三枚举：实际 {w}x{h} 不属 "
                f"{{9:16,16:9,1:1}}（±{_ASPECT_TOL_PX}px 容差内，aspect 枚举关）")

        # ⑤ 1K：长边落在 [_K1_MIN, _K1_MAX]
        long_e = max(w, h)
        if not (_K1_MIN <= long_e <= _K1_MAX):
            reasons.append(
                f"images[{i}] 非 1K 分辨率：长边 {long_e}px 不在 "
                f"[{_K1_MIN},{_K1_MAX}]（1K 标称 1024，分辨率关）")

        # ④ 压缩后 ≤ 2MB（按入参 bytes，与结构契约严格 int 语义一致）
        b = item.get("bytes")
        if isinstance(b, int) and not isinstance(b, bool):
            if b > _MAX_BYTES:
                reasons.append(
                    f"images[{i}] 体积超限：{b} bytes > {_MAX_BYTES}"
                    f"（压缩后须 ≤2MB）")
        # bytes 非严格 int 属 tier-1 结构契约职责，本门不重复报。

    # ② 构成：开篇 9:16 ×1 + 中间 16:9 ×≥2 + 结尾 9:16 ×1
    #    仅在张数足够时判位置语义（不足时 ① 已报，避免重复噪声）。
    if n >= 4:
        if per_aspect[0] != "9:16":
            reasons.append(
                f"构成不符：开篇（images[0]）须 9:16，实际 "
                f"{per_aspect[0] or '未知'}")
        if per_aspect[-1] != "9:16":
            reasons.append(
                f"构成不符：结尾（images[-1]）须 9:16，实际 "
                f"{per_aspect[-1] or '未知'}")
        mid_16_9 = sum(1 for k in per_aspect[1:-1] if k == "16:9")
        if mid_16_9 < 2:
            reasons.append(
                f"构成不符：中间段须 ≥2 张 16:9，实际 {mid_16_9} 张")

    return reasons


# ===== 【第 3 节】调研集合门 P2.2 =====
# ====================================================================
# tier-2 调研集合验证门（P2.2）—— 与 verify_infographic_set 并列同构。
# 对 **本次 fan-out 新产出** 的 research 集合强制，
# **不追溯历史冻结 golden**（历史 3 篇大纲/research 各异、字段形态不统一，
# 有的根本没 research 目录——追溯它们=误判门，与 P1.2 同理）。
#
# ⚠️ 这是 tier-2 **语义关**，与 tier-1 结构契约 validate_output 分开：
#   - 故意 **不** 写进 `_OUTPUT_SCHEMA` / `validate_output`
#     （塞进去会污染契约且与 agent-contracts.md「校验层级总纲」自相矛盾；
#      tier-1 只校验 sources[].url 结构，见 _validate_research_items）。
#   - 由编排器在 research fan-out 收齐后、对 **新产出** 单独调本函数把关。
#
# 纯函数：只读入参 findings/sources（不读磁盘、不碰网络、不碰 .state.json），
# 无写副作用。返回 list[str]：每条一个违规原因（带定位
# findings[i]/sources[i] + 规则名）；空 list = 通过。任何异常都转结构化
# 原因字符串（绝不裸抛），契合本仓 subagent「禁裸崩」铁律。
#
# === 判定规则（与 agent-contracts.md research 节验证清单对齐）===
# ① findings 非空，且每条有实质 support（claim 非空 + support 非空 str）
# ② sources 去重后 ≥ _MIN_SOURCES（去重按 url 归一化）
# ③ 版本/价格/日期类 finding 至少 1 条「官网级」source 兜底
#    （呼应全局铁律：版本/价格/时间须官网第一信源 + 权威媒体交叉核对）
# ④ sources 每条 url 非空 + 域名基本合法（tier-1 已保底 url 存在非空，
#    这里 tier-2 复检并加「能解析出 host」的基本合法性）
#
# === _MIN_SOURCES = 3 的依据 ===
# outline.md 步骤5「网络调研与竞品分析」要求「3-5个关键词组合 + 多渠道
# 搜集（行业报告/科技媒体/学术/竞品/官方）」，单一来源即判调研不足。
# 全局铁律又要求「官网第一信源 + 权威媒体交叉核对」（≥2 个不同档），
# 故取 3：官网 + 权威媒体 + 第三方交叉，构成最小可信三角，低于 3
# 视为「凭单点臆断」。去重按 url 归一化（去协议/末尾斜杠/小写 host），
# 防「同一篇换 http/https 或加 ? 凑数」绕过 ≥3。
#
# === 「官网级 source」启发式判据（可解释；P2.2 复审收紧）===
# 一条 source 判「官网级」当且仅当满足任一：
#   (a) 显式标注 tier == "官网"（agent-contracts.md 示例契约里 tier 枚举
#       含「官网|权威媒体|学术|社区」，官网是作者的一手声明）；
#   (b) host 命中「官方域」特征：以 docs./developer./dev./blog./help.
#       开头（厂商自家文档/开发者/博客/帮助子域 = 一手声明）；
#   (c) **仅当已先判定为「官方域」**（host 命中 (b) 前缀，或 tier=="官网"）
#       时，路径含 /blog|/release-notes|/releases|/pricing|/changelog 等
#       强信号才进一步确认——**路径提示不能单独把第三方权威媒体提成官网级**。
#   且 host 不属社媒/UGC/二手聚合域（精确域或后缀域匹配，见下）。
#
# 🔴 P2.2 复审 Important 1 修复：原 _OFFICIAL_PATH_HINTS 含裸 /news、/release，
#    使 theverge.com/news、techcrunch.com/.../release-notes、reuters /release-x
#    被单独提成「官网级」——端到端实测：版本/价格 finding 全部源自
#    The Verge/TechCrunch/Wired 零厂商官网时 rule③ 仍返回空（误放行），
#    恰好架空 作者 全局铁律「版本/价格/日期须官网第一信源 + 权威媒体≥2
#    交叉」。修法：① 从路径提示移除裸 /news；② /release 收紧为强信号
#    /release-notes、/releases；③ **路径提示只在 host 已是官方域 / tier==官网
#    时才生效**（第三方媒体即便路径像 /blog 也不算官网级）。厂商自家 blog
#    （blog. 前缀 / 官方域 + /blog）仍判官网级——厂商 blog 属一手声明、
#    符合铁律，保留不动。
#
# 仅 ③ 触发（finding 命中版本/价格/日期关键词）时才查官网级；
# 纯观点类 finding 不强制官网源（与铁律「版本/价格/时间」边界一致）。
# 启发式只做「门槛兜底」，不替代人工核实——判不准时倾向报违规（让编排器
# 就地重派补官网源），不放水（呼应「信息无法确认显式标注待核实」铁律）。
#
# 🟡 已知边界（Minor 4，供 P3-P5 语义门复用者知悉）：_VPD_KEYWORDS 含
#    v1/发布/更新 等宽词，会让一些**普通观点 finding** 也触发 rule③、
#    被索要官网级 source。这是**有意的 fail-safe**：宁严勿松——过度索要
#    官网源只会让编排器多补一条权威源（不误拒正例：合规组本就含官网源
#    仍通过），符合本门「判不准倾向报违规、不放水」的总设计。复用本启发式
#    作 P3-P5 样板时，触发词集合按各阶段语义自定，但保留「宁严勿松」取向。
# ====================================================================

_MIN_SOURCES = 3                       # 去重后最小信源数（依据见上）
# 版本/价格/日期类 finding 触发词（命中即要求官网级 source 兜底）
_VPD_KEYWORDS = (
    "版本", "价格", "定价", "收费", "费用", "美元", "元/", "/月", "/年",
    "日期", "发布", "上线", "更新", "参数", "v1", "v2", "v3", "v4",
    "version", "price", "pricing", "release", "美金", "免费额度",
)
# 社媒 / UGC 聚合 / 二手转述域：命中即**不**算官网级。
# 🔴 P2.2 复审 Important 2 修复：用**精确域或后缀域**匹配
#    （host == bad 或 host.endswith("." + bad)），不再 `bad in host` 裸
#    子串——裸子串使 "x.com" 命中 netflix.com / max.com、"medium.com"
#    命中 supermedium.com 等合法官方子域被误降级。同步去掉冗余裸 token
#    "zhihu"（与 "zhihu.com" 重复且无锚点）。
_NON_OFFICIAL_HOSTS = (
    "zhihu.com", "weibo.com", "xiaohongshu.com", "xhslink.com",
    "csdn.net", "jianshu.com", "medium.com", "36kr.com",
    "douyin.com", "bilibili.com", "twitter.com", "x.com",
    "juejin.cn", "segmentfault.com", "cnblogs.com",
)
# 官方一手特征：host 前缀（厂商自家子域）。
_OFFICIAL_HOST_PREFIXES = ("docs.", "developer.", "dev.", "blog.", "help.")
# 路径强信号：**仅在 host 已判官方域 / tier==官网 时**才用来确认官网级，
# 不能单独把第三方权威媒体提成官网级。已移除裸 /news；/release 收紧为
# /release-notes、/releases（强信号），避免媒体的 release-x 报道误命中。
_OFFICIAL_PATH_HINTS = (
    "/blog", "/release-notes", "/releases", "/pricing", "/price",
    "/changelog", "/docs", "/announcement", "/whatsnew",
)


def _norm_url(u: str) -> str:
    """url 归一化用于去重：小写 + 去协议 + 去末尾斜杠 + 去查询/锚点。
    任何解析异常返回原串小写（绝不裸抛——宁可少去重也不崩门）。"""
    try:
        s = u.strip().lower()
        for pre in ("https://", "http://", "//"):
            if s.startswith(pre):
                s = s[len(pre):]
                break
        for sep in ("?", "#"):
            if sep in s:
                s = s.split(sep, 1)[0]
        return s.rstrip("/")
    except Exception:
        return str(u).strip().lower()


def _url_host(u: str) -> str:
    """从 url 抽 host（小写、不含端口/路径）。解析不出返回空串。"""
    try:
        s = _norm_url(u)
        host = s.split("/", 1)[0]
        return host.split(":", 1)[0]
    except Exception:
        return ""


def _host_matches(host: str, domains) -> bool:
    """精确域或后缀域匹配：host == d 或 host.endswith("." + d)。
    替代有 bug 的裸子串 `d in host`（防 x.com 误命中 netflix.com）。"""
    for d in domains:
        if host == d or host.endswith("." + d):
            return True
    return False


def _is_official_source(src: dict) -> bool:
    """启发式判一条 source 是否「官网级」。判据见上方文档串
    （P2.2 复审收紧：路径提示只在官方域/tier==官网 时才生效；
    非官网域用精确/后缀匹配）。异常一律按「非官网级」保守处理（不放水）。"""
    try:
        if not isinstance(src, dict):
            return False
        tier_official = str(src.get("tier", "")).strip() == "官网"
        if tier_official:
            return True
        url = src.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return False
        host = _url_host(url)
        if not host:
            return False
        # 社媒/UGC/二手聚合域：精确或后缀域匹配 → 直接判非官网级。
        if _host_matches(host, _NON_OFFICIAL_HOSTS):
            return False
        # (b) host 命中官方子域前缀 → 官网级（厂商自家文档/blog/dev）。
        is_official_domain = any(
            host.startswith(p) for p in _OFFICIAL_HOST_PREFIXES)
        if is_official_domain:
            return True
        # (c) 路径强信号**仅当 host 已是官方域 / tier==官网 时**才确认
        #     官网级——第三方权威媒体即便路径像 /blog 也不提成官网级
        #     （Important 1 修复：防 theverge.com/news 误判）。
        #     此处 tier_official 已在上方 return True，能走到这里说明
        #     既非官方域也非 tier==官网，故路径提示一律不生效。
        return False
    except Exception:
        return False


def verify_research_set(findings: list, sources: list) -> list:
    """tier-2：校验**本次 fan-out 新产出**的调研集合。
    返回违规原因 list（空=通过）；每条带定位（findings[i]/sources[i]）+
    规则名。纯函数：只读入参，不读磁盘/网络/状态，异常转结构化原因不裸崩。

    入参：
      findings：[{claim, support, confidence?}, ...]（对齐 _OUTPUT_SCHEMA
                research 的 findings；item 结构属 tier-2，本门校验）。
      sources： [{url, title?, tier?, accessed?}, ...]（对齐同 schema sources；
                tier-1 已保底 sources[].url 存在非空，本门 tier-2 复检 +
                去重计数 + 官网级语义）。"""
    reasons = []

    # 类型兜底：非 list 直接结构化报，不裸崩（与 verify_infographic_set 同风格）
    if not isinstance(findings, list):
        reasons.append(
            f"findings 必须是 list，收到 {type(findings).__name__}"
            f"（tier-2 type_check）")
        findings = []
    if not isinstance(sources, list):
        reasons.append(
            f"sources 必须是 list，收到 {type(sources).__name__}"
            f"（tier-2 type_check）")
        sources = []

    # ① findings 非空 + 每条有实质 support
    if not findings:
        reasons.append("findings 为空：调研无任何结论（规则① findings_nonempty）")
    for i, fitem in enumerate(findings):
        if not isinstance(fitem, dict):
            reasons.append(
                f"findings[{i}] 不是 dict（裸 {type(fitem).__name__}）："
                f"无 claim/support，无法判实质（规则① finding_struct）")
            continue
        claim = fitem.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            reasons.append(
                f"findings[{i}].claim 缺失或空：结论无主张"
                f"（规则① finding_claim）")
        support = fitem.get("support")
        if not isinstance(support, str) or not support.strip():
            reasons.append(
                f"findings[{i}].support 缺失或空：结论无证据支撑"
                f"（规则① finding_support）")

    # ④ sources 每条 url 非空 + 域名基本合法（tier-1 保底，tier-2 复检）
    for i, sitem in enumerate(sources):
        if not isinstance(sitem, dict):
            reasons.append(
                f"sources[{i}] 不是 dict（裸 {type(sitem).__name__}）"
                f"（规则④ source_struct）")
            continue
        url = sitem.get("url")
        if not isinstance(url, str) or not url.strip():
            reasons.append(
                f"sources[{i}].url 缺失或空（规则④ source_url_nonempty）")
            continue
        host = _url_host(url)
        # 「域名基本合法」最低判据：能抽出含点的 host（如 a.com）
        if not host or "." not in host:
            reasons.append(
                f"sources[{i}].url 域名非法：'{url}' 解析不出合法 host"
                f"（规则④ source_url_host）")

    # ② sources 去重后 ≥ _MIN_SOURCES
    norm_set = set()
    for sitem in sources:
        if isinstance(sitem, dict):
            u = sitem.get("url")
            if isinstance(u, str) and u.strip():
                norm_set.add(_norm_url(u))
    if len(norm_set) < _MIN_SOURCES:
        reasons.append(
            f"信源不足：去重后 {len(norm_set)} 条 < {_MIN_SOURCES} 条"
            f"（规则② sources_min；单点臆断，需多渠道交叉）")

    # ③ 版本/价格/日期类 finding 至少 1 条官网级 source 兜底
    has_official = any(_is_official_source(s) for s in sources)
    for i, fitem in enumerate(findings):
        if not isinstance(fitem, dict):
            continue
        text = " ".join(
            str(fitem.get(k, "")) for k in ("claim", "support")).lower()
        hit_vpd = any(kw.lower() in text for kw in _VPD_KEYWORDS)
        if hit_vpd and not has_official:
            reasons.append(
                f"findings[{i}] 涉版本/价格/日期但全集无官网级 source 兜底"
                f"（规则③ vpd_needs_official；铁律：版本/价格/时间须官网"
                f"第一信源核实）")

    return reasons


# ===== 【第 4 节】内容增强集合门 P3.2 =====
# ====================================================================
# tier-2 内容增强集合验证门（P3.2）—— 与 verify_infographic_set /
# verify_research_set 并列同构。对 **本次 fan-out 合并后新产出** 的
# content_enhance 四策略集合强制，**不追溯历史冻结 golden**（历史 3 篇
# 文章无统一 content_enhance 产物，多数根本没 素材/enhance 目录——
# 追溯它们=误判门，与 P1.2/P2.2 同理）。
#
# ⚠️ 这是 tier-2 **语义关**，与 tier-1 结构契约 validate_output 分开：
#   - 故意 **不** 写进 `_OUTPUT_SCHEMA` / `validate_output`
#     （塞进去会污染契约且与 agent-contracts.md「校验层级总纲」自相矛盾；
#      tier-1 只校验 strategies 4 键齐全/仅认/值非空 str，见
#      _validate_content_enhance）。
#   - 由编排器在 content_enhance fan-out **收齐 + 主轴合并关之后**、对
#     **合并后新产出** 单独调本函数把关（合并关本身=编排器主轴自做、
#     绝不外派 subagent；见 autopilot.md / agent-contracts.md）。
#
# 纯函数：只读入参 strategies(dict) + 可选 article_body(str)（不读磁盘/
# 网络/状态），无写副作用。返回 list[str]：每条带定位（strategy 名 +
# 规则名）；空 list = 通过。任何异常都转结构化原因字符串（绝不裸抛），
# 契合本仓 subagent「禁裸崩」铁律。
#
# === 判定规则（与 agent-contracts.md content_enhance 节验证清单对齐）===
# ① 四策略文本两两去重：无大段雷同/复制粘贴
#    （归一化后用「最长公共子串占较短文本比例」+「归一化全等」双判据；
#     比例 ≥ _CE_DUP_RATIO 或归一化全等即判雷同，宁严勿松 fail-safe）
# ② 无显著自相矛盾：同一策略文本内同时出现「肯定 X」与「否定 X」式
#    对冲措辞（启发式词对，判不准倾向报违规）
# ③ 每策略实质性：strip 后长度 ≥ _CE_MIN_LEN，且不是纯占位/套话
#    （命中占位词且过短才判——给最小信号阈值，注释依据）
# ④ 若给 article_body 则校验策略与正文非完全脱节：策略与正文须有
#    最低限度的 token 交集（轻量启发式，注释边界）
#
# === 各阈值依据 ===
# _CE_MIN_LEN = 12：四策略每条是「针对初稿的增强说明/改写指引」，
#   低于 ~12 个字符（≈ 中文 6 字 / 英文一两个词）不可能承载一条可执行
#   的增强意见，必是占位（"待补"/"TODO"/"略"）或套话残片。取 12 偏松
#   只挡明显占位，不误杀「精炼但有效」的短指引（fail-safe 反向：实质性
#   关只在「又短又像占位」时才报，不单凭长度误拒）。
# _CE_DUP_RATIO = 0.65：四策略本应各司其职（角度/密度/细节/质感），
#   两条文本若 65%+ 内容雷同，等于其中一条没干活（复制粘贴凑数）。
#   取 0.65 而非 0.5：增强说明常共享选题名/术语等公共片段，0.5 会把
#   「各说各的但都提到同一主题词」误判雷同；0.65 要求「大段连续雷同」
#   才报，宁严勿松但不误杀正常用词重叠。子串用归一化文本（去空白/
#   标点/小写）算最长公共连续子串，吸收排版差异。
# _CE_MIN_OVERLAP = 1：脱节关只做「最低限度兜底」——策略与正文连
#   1 个长度≥2 的公共 token 都没有，基本可判该策略与本文无关（跑错题/
#   套用模板）。只要 ≥1 即放行（不强求高交集——增强说明本就用元语言
#   描述「怎么改」，未必复述正文原词；过严会误杀合规增强）。article_body
#   为 None / 空时本关整体跳过（无正文可比，不臆断）。
# 启发式只做「门槛兜底」，判不准时倾向报违规（让编排器就地重派该策略），
# 不放水（与 verify_research_set「判不准倾向报违规、不放水」总取向一致）。
# ====================================================================

_CE_MIN_LEN = 12              # 单策略 strip 后最小字符数（依据见上）
_CE_DUP_RATIO = 0.65          # 两两雷同比例阈值（依据见上）
_CE_MIN_OVERLAP = 1           # 与正文最小公共 token 数（依据见上）
# 占位/套话信号词：命中**且文本过短**才判实质性不足（宁松不误杀）
_CE_PLACEHOLDER_HINTS = (
    "todo", "tbd", "待补", "待填", "待定", "占位", "略", "xxx",
    "placeholder", "n/a", "暂无", "同上", "见上", "...", "。。。",
)
# 自相矛盾启发式词对：同一策略文本内**两词同现**视为对冲（fail-safe，
# 判不准倾向报违规——这些词对单独看不一定矛盾，但增强说明里同时出现
# 「应该/不应该」「保留/删除」式对冲多半是策略内部没拿定主意/自相打架）。
_CE_CONTRADICTION_PAIRS = (
    ("应该", "不应该"), ("保留", "删除"), ("保留", "删掉"),
    ("增加", "减少"), ("加长", "缩短"), ("强化", "弱化"),
    ("更口语", "更书面"), ("口语化", "书面化"),
    ("should", "should not"), ("keep", "remove"), ("add", "delete"),
)


def _ce_norm(s: str) -> str:
    """策略文本归一化用于去重比对：小写 + 去所有空白 + 去常见标点。
    任何异常返回原串小写（绝不裸抛——宁可少去重也不崩门）。"""
    try:
        out = []
        for ch in str(s).lower():
            if ch.isspace():
                continue
            # 去标点（中英常见），保留字母/数字/CJK 以保留语义骨架
            if ch in "，。、；：！？,.;:!?\"'“”‘’()（）[]【】<>《》-_/\\|*#`~":
                continue
            out.append(ch)
        return "".join(out)
    except Exception:
        return str(s).lower()


def _longest_common_substr_len(a: str, b: str) -> int:
    """最长公共**连续**子串长度（经典 DP，O(len(a)*len(b))）。
    入参已归一化且长度有限（策略文本，非海量），不做截断。
    异常一律返回 0（不裸抛——宁可少判雷同也不崩门）。"""
    try:
        if not a or not b:
            return 0
        # 滚动一维 DP，省内存；只需长度不需还原子串
        prev = [0] * (len(b) + 1)
        best = 0
        for i in range(1, len(a) + 1):
            cur = [0] * (len(b) + 1)
            ai = a[i - 1]
            for j in range(1, len(b) + 1):
                if ai == b[j - 1]:
                    cur[j] = prev[j - 1] + 1
                    if cur[j] > best:
                        best = cur[j]
            prev = cur
        return best
    except Exception:
        return 0


def _ce_tokens(s: str):
    """从文本抽「长度 ≥2 的 token」集合，用于脱节关公共 token 判定。
    中文按 2-gram 切（连续 CJK 取相邻двух字），英文/数字按 \\w+ 词。
    异常返回空集合（不裸抛）。"""
    try:
        import re
        text = str(s).lower()
        toks = set()
        # 英文/数字词（≥2 字符）
        for m in re.findall(r"[a-z0-9]{2,}", text):
            toks.add(m)
        # 连续 CJK 串里取 2-gram（≥2 才有区分度）
        for run in re.findall(r"[一-鿿]{2,}", text):
            for k in range(len(run) - 1):
                toks.add(run[k:k + 2])
        return toks
    except Exception:
        return set()


# ⚠️ 当前未被任何 pipeline/orchestration 运行时调用（dead，保留为未来接线预留）；
#   content_enhance 不在 STAGE_ORDER，唯一调用点在 tests/regression（test_contracts /
#   regression_baseline / make_fixtures）。若日后把 content_enhance 接成正式阶段，
#   再在 pipeline verify 里接上本门即可（详见审查 2026-06-20 C 类发现）。
def verify_content_enhance_set(strategies: dict,
                               article_body: "str|None" = None) -> list:
    """tier-2：校验**本次 fan-out 合并后新产出**的 content_enhance 四策略。
    返回违规原因 list（空=通过）；每条带定位（strategy 名 + 规则名）。
    纯函数：只读入参，不读磁盘/网络/状态，异常转结构化原因不裸崩。

    入参：
      strategies：{angle, density, detail, texture: str}（对齐
                  _OUTPUT_SCHEMA content_enhance；tier-1 已保底 4 键齐全/
                  仅认/值非空 str，本门 tier-2 校验合并后**质量/去重/
                  不矛盾/与正文非脱节**）。
      article_body：可选正文（合并去脱节判定用）；None/空 → 脱节关跳过。"""
    reasons = []

    # 类型兜底：非 dict 直接结构化报，不裸崩（与 verify_research_set 同风格）
    if not isinstance(strategies, dict):
        return [
            f"strategies 必须是 dict，收到 {type(strategies).__name__}"
            f"（tier-2 type_check）"]

    # 只对**规范 4 键**做 tier-2（tier-1 已保 4 键齐全/仅认/非空 str；
    # 这里防御性按 _CE_STRATEGY_KEYS 取值，缺/非 str 的位置结构化报后跳过，
    # 不裸崩 —— 单一事实源 = 模块级 _CE_STRATEGY_KEYS，不重抄 4 键）。
    texts = {}
    for k in _CE_STRATEGY_KEYS:
        v = strategies.get(k)
        if not isinstance(v, str) or not v.strip():
            reasons.append(
                f"[{k}] 策略文本缺失或非非空 str（tier-2 prereq；"
                f"通常 tier-1 _validate_content_enhance 已先拦下）")
            continue
        texts[k] = v

    # ③ 每策略实质性：过短 + 命中占位词才判（宁松不误杀，依据见文档串）
    for k, v in texts.items():
        body = v.strip()
        too_short = len(body) < _CE_MIN_LEN
        low = body.lower()
        is_placeholder = any(h in low for h in _CE_PLACEHOLDER_HINTS)
        if too_short and is_placeholder:
            reasons.append(
                f"[{k}] 策略实质性不足：文本过短（{len(body)}<{_CE_MIN_LEN}）"
                f"且疑似占位/套话（规则③ substantive）")
        elif too_short:
            reasons.append(
                f"[{k}] 策略实质性不足：文本仅 {len(body)} 字符 "
                f"< {_CE_MIN_LEN}（规则③ substantive_minlen）")

    # ② 无显著自相矛盾：同一策略文本内对冲词对同现（fail-safe）
    for k, v in texts.items():
        low = v.lower()
        for w1, w2 in _CE_CONTRADICTION_PAIRS:
            if w1 in low and w2 in low:
                reasons.append(
                    f"[{k}] 疑似自相矛盾：同文出现「{w1}」与「{w2}」"
                    f"（规则② no_contradiction；判不准倾向报，编排器复核）")
                break  # 一条策略报一次足够，避免噪声

    # ① 四策略两两去重：归一化后最长公共连续子串占比 ≥ 阈值，或全等
    keys = [k for k in _CE_STRATEGY_KEYS if k in texts]
    norm = {k: _ce_norm(texts[k]) for k in keys}
    for ai in range(len(keys)):
        for bi in range(ai + 1, len(keys)):
            ka, kb = keys[ai], keys[bi]
            na, nb = norm[ka], norm[kb]
            if not na or not nb:
                continue
            if na == nb:
                reasons.append(
                    f"[{ka}|{kb}] 两策略归一化后完全雷同"
                    f"（规则① dedup；复制粘贴凑数）")
                continue
            lcs = _longest_common_substr_len(na, nb)
            shorter = min(len(na), len(nb))
            ratio = lcs / shorter if shorter else 0.0
            if ratio >= _CE_DUP_RATIO:
                reasons.append(
                    f"[{ka}|{kb}] 两策略大段雷同：最长公共子串占较短文本 "
                    f"{ratio:.0%} ≥ {_CE_DUP_RATIO:.0%}"
                    f"（规则① dedup；疑复制粘贴）")

    # ④ 与正文非完全脱节（仅在给了非空 article_body 时启用，见文档串边界）
    if isinstance(article_body, str) and article_body.strip():
        body_tokens = _ce_tokens(article_body)
        if body_tokens:  # 正文抽不出 token 则不臆断（跳过本关）
            for k, v in texts.items():
                strat_tokens = _ce_tokens(v)
                overlap = len(strat_tokens & body_tokens)
                if overlap < _CE_MIN_OVERLAP:
                    reasons.append(
                        f"[{k}] 策略与正文完全脱节：公共 token {overlap} "
                        f"< {_CE_MIN_OVERLAP}（规则④ not_disjoint；"
                        f"疑跑错题/套模板，判不准倾向报）")

    return reasons


# ===== 【第 5 节】封面集合门 P4.2 =====
# ====================================================================
# tier-2 封面集合验证门（P4.2）—— 与 verify_infographic_set /
# verify_research_set / verify_content_enhance_set 并列同构。对 **本次
# fan-out 多风格打样新产出** 的 cover 候选集合强制，**不追溯历史冻结
# golden**（历史 3 篇封面各异：风格/比例形态不统一，有的根本没
# 素材/cover 目录——追溯它们=误判门，与 P1.2/P2.2/P3.2 同理）。
#
# ⚠️ 这是 tier-2 **语义关**，与 tier-1 结构契约 validate_output 分开：
#   - 故意 **不** 写进 `_OUTPUT_SCHEMA` / `validate_output`
#     （塞进去会污染契约且与 agent-contracts.md「校验层级总纲」自相矛盾；
#      tier-1 只校验 candidates[].path 非空 str + selected 非空 str，见
#      _validate_cover；`selected ∈ candidates`/磁盘 IO/像素属 tier-2）。
#   - 🔴 2026-05-22 封面锁定 montage-evidence：多风格 fan-out 选优 +「近 3 篇
#     回避」已废止/删除（规则⑥已从本函数移除，`recent_covers` 为废弃 no-op）。
#     默认路径只生成单张 cover，不调本函数；仅显式多候选覆盖模式才调，
#     校验候选集合合规（①②③④⑤）+ selected 可追溯，不做风格回避。
#
# 纯函数：只读磁盘 PNG 像素（IO）+ 入参 path/字段，无写副作用、不碰
# .state.json。返回 list[str]：每条带定位（candidate path / selected /
# 规则名）；空 list = 通过。任何 IO/解码异常都转结构化原因字符串
# （绝不裸抛），契合本仓 subagent「禁裸崩」铁律。判不准倾向报违规
# （让编排器就地重派该候选），不放水（与本仓 fail-safe 总取向一致）。
#
# === 判定规则（与 agent-contracts.md cover 节验证清单 tier-2 项对齐）===
# ① selected ∈ candidates 的 path 集合（跨字段，选定项可追溯）
# ② candidates ≥ _COVER_MIN_CANDIDATES（多风格并行打样，单张=没打样）
# ③ 每候选图**实际存在**（磁盘 IO；path 不存在/读不出报）
# ④ **1K 分辨率**：长边 ∈ [_K1_MIN, _K1_MAX]
# ⑤ 封面比例 **2.35:1**（cinematic 微信头条，给 ±容差）
# ⑥ 若给 recent_covers：selected 风格特征与近 3 篇不重复（轻量启发式）
#
# === ④ 1K 复用既定口径（不双写、防漂移）===
# 直接复用 verify_infographic_set 的模块级常量 _K1_MIN/_K1_MAX
# （= [900, 1200]，依据见该函数上方「1K 容差带的依据」文档串：1K 标称
# 1024，下界 900≈−12% 排缩略图、上界 1200≈+17% 容 1080/1152 且挡 2k
# 长卷）。封面与信息图同属 baoyu-* 1K 横切规范（见 image-routing.md
# §1K 分辨率横切规范 / iron-rules.md §生图分辨率铁律），**同一既定标准**，
# 故此处**不另立常量、不重复造规则**——改 1K 口径只在 verify_infographic_set
# 一处改即全域生效（单一事实源）。
#
# === ⑤ 2.35:1 比例与 ±容差依据 ===
# cover-styles.md「不变的底层铁律」第一条明确：封面比例 = `2.35:1`
# （微信头条封面），4 种风格 + montage 2 亚型**全部共享**此比例
# （文首「品牌一致性（深色底 + 品牌绿 + 2.35:1）」）。故本门按 2.35:1
# 单一目标比例判（不是信息图的三枚举）。2.35:1 = 2.35（电影宽银幕
# cinematic）。容差用「按高推理想宽，实际宽偏差 ≤ _COVER_RATIO_TOL_PX」
# ——与 _classify_aspect 同手法（取较大边定基避免误差放大），吸收
# baoyu/压缩链路取整误差（封面恒横图，长边=宽落 1K 带 [900,1200]；如
# 高 436 下理想宽≈1024，得 1022/1026 仍判 2.35:1），同时仍能把
# 16:9(1024×576)、1:1 这类非 cinematic 挡下。
# ±4px 容差略宽于信息图的 ±2px：封面比例更扁、按高推宽的杠杆更大
# （长边宽 ~1024px 量级、与 1K 约束 [900,1200] 自洽，同等相对取整
# 误差对应更大绝对像素），4px 仍远小于把 16:9 误判进来的距离。
#
# === ⑥ 风格回避启发式判据（可解释；fail-safe，注释边界）===
# recent_covers：近 3 篇已用 cover_style 字符串 list（由调用方从 <数据目录>/works.yaml
# 近 3 篇的 cover_style 字段取，见 cover-styles.md「选择机制·自动选择算法」）。
# selected 候选的风格取自该 candidate dict 的 `style` 字段（cover SOP
# 派发时每候选带 style，见 agent-contracts.md cover 输出 schema 示例
# `{"path":..., "style": "cinematic", ...}`）。判据：
#   - 归一化（小写 strip）后 selected.style 若**精确命中** recent_covers
#     任一项 → 报撞近 3 篇（规则⑥ recent_repeat）。
#   - **montage 同源家族回避**：cover-styles.md 自动选择算法第 4 条
#     「montage-evidence/pipeline/starry 三者视为同源 montage 家族，
#     近 3 篇用过任一亚型则下篇默认避开整个 montage 家族」。故 selected
#     风格与近 3 篇若**同属 montage 家族**（任一以 "montage" 起头）也报。
# 边界（有意 fail-safe，判不准倾向报）：
#   - selected 对应 candidate 无 `style` 字段 / 非 str / 空 → **跳过本关
#     不臆断**（无风格可比，不误报；风格缺失本身不是 ⑥ 的违规——
#     ⑥ 只管「与近 3 篇重复」，缺字段交由 SOP/人工，门不越界臆判）。
#   - recent_covers 为 None / 空 / 非 list → 本关整体跳过（无历史可比，
#     不臆断，与 verify_content_enhance_set 脱节关 None 跳过同精神）。
#   - 历史风格池兼容：cover-styles.md 说明 monument/horizon/focus/
#     obsidian 等下架风格在 works.yaml 残留时「视为非当前可用池、不
#     影响新文章选择」——本门**只做精确/家族字符串匹配报重复**，不内
#     置「当前可用风格白名单」（白名单会随 cover-styles.md 风格池增删
#     漂移、且越界替编排器做风格合法性判定）；风格是否在可用池由编排器
#     主轴按 cover-styles.md 裁量，门只兜「与近 3 篇撞车」这一条。
# 启发式只做「门槛兜底」，不替代编排器主轴选优；判不准倾向报违规
# （让编排器重选风格），不放水（与全门 fail-safe 取向一致）。
# ====================================================================

_COVER_MIN_CANDIDATES = 2          # 多风格并行打样最少候选数（依据见上）
# 2.35:1 cinematic 目标比例（宽:高）。依据见上方文档串（cover-styles.md
# 底层铁律：所有封面风格共享 2.35:1）。用 (w,h) 朝向：封面恒横图 w>h。
_COVER_RATIO_W, _COVER_RATIO_H = 235, 100   # = 2.35:1（整数表避免浮点）
_COVER_RATIO_TOL_PX = 4            # 比例长边容差（依据见上，略宽于信息图 ±2）
# 1K 长边带：**复用** verify_infographic_set 的 _K1_MIN/_K1_MAX
# （单一事实源，不另立常量、不重复造规则；见上方文档串 ④）。


def verify_cover_set(candidates: list, selected: str,
                     recent_covers: "list[str]|None" = None) -> list:
    """tier-2：校验**本次 fan-out 多风格打样新产出**的 cover 候选集合。
    返回违规原因 list（空=通过）；每条带定位（candidate path / selected /
    规则名）。纯函数：只读入参 + 磁盘 PNG 像素，不碰网络/状态，异常转
    结构化原因不裸崩。**选优是编排器主轴裁量、绝不外派**，本门是选优
    前置的机器化把关，不替编排器选（见上方文档串）。

    入参：
      candidates：[{path, style?, aspect?}, ...]（对齐 _OUTPUT_SCHEMA
                  cover 的 candidates；tier-1 已保底 candidates[].path
                  非空 str，本门 tier-2 校验数量/存在/1K/比例/可追溯）。
      selected：  编排器选定的封面 path（tier-1 已保底非空 str）；本门
                  tier-2 复检其 ∈ candidates 路径集合（跨字段可追溯）。
      recent_covers：🔴 已废弃（2026-05-22 封面锁定 montage-evidence，
                  「近 3 篇回避」规则已删）。参数保留仅为签名兼容，**完全忽略**，
                  不再触发任何风格回避校验。"""
    reasons = []

    # 类型兜底：非 list/非 str 直接结构化报，不裸崩（与其它 verify_* 同风格）
    if not isinstance(candidates, list):
        reasons.append(
            f"candidates 必须是 list，收到 {type(candidates).__name__}"
            f"（tier-2 type_check）")
        candidates = []
    if not isinstance(selected, str) or not selected.strip():
        reasons.append(
            f"selected 必须是非空 str，收到 {type(selected).__name__}"
            f"={selected!r}（tier-2 type_check；通常 tier-1 _validate_cover "
            f"已先拦下）")
        selected = ""

    # ② candidates ≥ _COVER_MIN_CANDIDATES（多风格并行打样）
    n = len(candidates)
    if n < _COVER_MIN_CANDIDATES:
        reasons.append(
            f"候选不足：需 ≥{_COVER_MIN_CANDIDATES} 个多风格候选，实际 "
            f"{n} 个（规则② candidates_min；单张=没并行打样）")

    # 逐候选：path 结构兜底 + 图实际存在 + 1K + 2.35:1 比例
    cand_paths = []   # 与 candidates 等长；非法位置填 None（用于 ① 可追溯）
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            reasons.append(
                f"candidates[{i}] 不是 dict（裸 {type(item).__name__}）："
                f"无 path，无法校验（规则③ candidate_struct）")
            cand_paths.append(None)
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            reasons.append(
                f"candidates[{i}].path 缺失或非法"
                f"（规则③ candidate_path；tier-1 通常已先拦）")
            cand_paths.append(None)
            continue
        cand_paths.append(path)

        # ③ 候选图实际存在 + 读真实像素（IO/解码异常转结构化原因，绝不裸抛）
        try:
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
        except FileNotFoundError:
            reasons.append(
                f"candidates[{i}] 文件不存在/缺失：{path}"
                f"（规则③ candidate_exists）")
            continue
        except Exception as e:
            reasons.append(
                f"candidates[{i}] 读取失败（{type(e).__name__}）：{path}"
                f"（规则③ candidate_readable）")
            continue

        # ⑤ 封面比例 2.35:1（cinematic 横图，按实际像素 ±容差）。
        #    封面恒横图（w>h）；按高推理想宽，实际宽偏差 ≤ 容差即命中。
        ideal_w = h * _COVER_RATIO_W / _COVER_RATIO_H
        if not (abs(w - ideal_w) <= _COVER_RATIO_TOL_PX and w > h):
            reasons.append(
                f"candidates[{i}] 比例非 2.35:1：实际 {w}x{h}"
                f"（理想宽≈{ideal_w:.0f}，±{_COVER_RATIO_TOL_PX}px 容差内；"
                f"规则⑤ cinematic_ratio；封面恒 cinematic 2.35:1）：{path}")

        # ④ 1K：长边 ∈ [_K1_MIN, _K1_MAX]（复用信息图既定口径，单一事实源）
        long_e = max(w, h)
        if not (_K1_MIN <= long_e <= _K1_MAX):
            reasons.append(
                f"candidates[{i}] 非 1K 分辨率：长边 {long_e}px 不在 "
                f"[{_K1_MIN},{_K1_MAX}]（1K 标称 1024，规则④ resolution_1k；"
                f"复用 verify_infographic_set 既定带）：{path}")

    # ① selected ∈ candidates 的 path 集合（跨字段可追溯）
    if selected:
        valid_paths = {p for p in cand_paths if isinstance(p, str)}
        if selected not in valid_paths:
            reasons.append(
                f"selected 不可追溯：'{selected}' 不在 candidates 的 path "
                f"集合内（规则① selected_in_candidates；选定项必须是某个"
                f"已打样候选）")

    # ⑥ 近 3 篇风格回避 / montage 同源家族回避：🔴 2026-05-22 起**已删除**。
    #    封面锁定单一 montage-evidence，不再做风格轮换/回避。`recent_covers`
    #    参数保留仅为签名兼容（已废弃 no-op），不再产生任何 recent_repeat 违规。

    return reasons


# ===== 【第 6 节】审稿集合门 P5.2 =====
# ====================================================================
# tier-2 审稿集合验证门（P5.2）—— 与 verify_infographic_set /
# verify_research_set / verify_content_enhance_set / verify_cover_set
# 并列同构。对 **本次 opt-in 审稿 team fan-out 新产出** 的 review
# verdicts 集合强制，**不追溯历史冻结 golden**（历史 3 篇文章无统一
# review 产物、多数根本没 素材/review 目录——追溯它们=误判门，与
# P1.2/P2.2/P3.2/P4.2 同理）。
#
# ⚠️ 这是 tier-2 **语义关**，与 tier-1 结构契约 validate_output 分开：
#   - 故意 **不** 写进 `_OUTPUT_SCHEMA` / `validate_output`
#     （塞进去会污染契约且与 agent-contracts.md「校验层级总纲」自相矛盾；
#      tier-1 只校验 verdicts[].role 非空 str + issues 是 list + pass
#      严格 bool，见 `_validate_review_items`；issues 内容质量 / role
#      合法性 / 裁决一致性属 tier-2）。
#   - 由编排器在审稿 team fan-out **收齐之后**、对 **新产出 verdicts
#     集合** 单独调本函数把关。**汇总裁决（合并 issues / 统一处置 /
#     按失败语义回流 / 应用 fixes）是编排器主轴自做、绝不外派
#     subagent**（与 verify_content_enhance_set 合并关 /
#     verify_cover_set 选优由主轴自做同精神）；本门是汇总裁决**前置**
#     对 verdicts 集合的机器化把关，**不是汇总裁决本身**——它不替编排器
#     裁决该不该回流、也不判 issue 内容对错。
#
# 纯函数：只读入参 verdicts(list) + 可选 ctx（不读磁盘/网络/状态），
# 无写副作用。返回 list[str]：每条带定位（verdicts[i] / role / 规则名）；
# 空 list = 通过。任何异常都转结构化原因字符串（绝不裸抛），契合本仓
# subagent「禁裸崩」铁律。判不准倾向报违规（让编排器复核/重派该角色），
# 不放水（与全门 fail-safe 总取向一致）。
#
# === 判定规则（与 agent-contracts.md review 节 tier-2 项对齐）===
# ① role 覆盖：去重后 ≥ _REVIEW_MIN_ROLES 个不同 role（三角色齐：
#    风格审 / 铁律审 / 事实核查；缺角色 = 围审维度不全，报）
# ② pass=false 的 verdict 其 issues 必须非空（判失败却无具体可定位
#    issue = 无效裁决，编排器无从回流处置）
# ③ 裁决一致性轻量启发式：某 verdict pass=true 却携带非空 issues =
#    弱不一致警示项（判不准倾向报——「过了但有问题没说清」要么是
#    issue 是噪声、要么是不该 pass，交编排器主轴复核）
#
# === 不内置「合法 role 白名单」做裁量（边界，复用 P4.2 ⑥ 划法）===
# 门**只兜确定性硬规则**（角色数量去重计数 / pass-false-issues 非空 /
# pass-true-却有 issues 的一致性弱提示）；**不**内置「{风格审,铁律审,
# 事实核查} 才算合法 role」的白名单：白名单会随审稿维度增删漂移、
# 且越界替编排器做「这个 role 算不算正经审稿角色」的语义裁量
# （issue 内容质量 / role 合法性归编排器主轴/tier-2 语义，门不越界，
# 与 verify_cover_set 不内置「当前可用风格白名单」同精神）。① 只数
# **去重后不同 role 个数**够不够 _REVIEW_MIN_ROLES，不判每个 role
# 叫什么是否「正统」。
#
# === _REVIEW_MIN_ROLES = 3 的依据 ===
# agent-contracts.md review 节 + autopilot.md 审稿 team SOP 明确：审稿
# team 三角色 = 风格审 / 铁律审 / 事实核查，三维度齐才构成一轮有效
# 围审（少一维 = 该维度无人把关）。取 3 = 三角色最小覆盖；去重计数
# 防「同一 role 报两条 verdict 凑数」绕过 ≥3。
# ====================================================================

_REVIEW_MIN_ROLES = 3          # 去重后最小覆盖角色数（依据见上）


def verify_review_set(verdicts: list, recent_or_ctx=None) -> list:
    """tier-2：校验**本次 opt-in 审稿 team fan-out 新产出**的 review
    verdicts 集合。返回违规原因 list（空=通过）；每条带定位
    （verdicts[i] / role / 规则名）。纯函数：只读入参，不读磁盘/网络/
    状态，异常转结构化原因不裸崩。**汇总裁决是编排器主轴自做、绝不
    外派**，本门是汇总裁决前置的机器化把关，不替编排器裁决（见上方
    文档串）。

    入参：
      verdicts：[{role, issues, pass}, ...]（对齐 _OUTPUT_SCHEMA
                review 的 verdicts；tier-1 已保底 verdicts[].role 非空
                str / issues 是 list / pass 严格 bool，本门 tier-2
                校验角色覆盖 / pass-false-issues 非空 / 裁决一致性）。
      recent_or_ctx：可选上下文位（对齐其它 verify_* 的可选第二参形态，
                如 verify_cover_set 的 recent_covers）；P5.2 本门当前
                规则①②③ 不消费历史/上下文（review 不追溯历史冻结），
                预留位保持签名同构、不臆断，**不参与任何判定**。"""
    reasons = []

    # 类型兜底：非 list 直接结构化报，不裸崩（与其它 verify_* 同风格）
    if not isinstance(verdicts, list):
        return [
            f"verdicts 必须是 list，收到 {type(verdicts).__name__}"
            f"（tier-2 type_check）"]

    # 逐 verdict：取 role / issues / pass（tier-1 通常已保结构；本门
    # 防御性取值，缺/类型错的位置结构化报后跳过该条规则判定，不裸崩）。
    roles = set()
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            reasons.append(
                f"verdicts[{i}] 不是 dict（裸 {type(v).__name__}）："
                f"无 role/issues/pass，无法校验（tier-2 prereq；"
                f"通常 tier-1 _validate_review_items 已先拦下）")
            continue
        role = v.get("role")
        issues = v.get("issues")
        pv = v.get("pass")

        # ① 角色覆盖累计（只收非空 str role；去重计数，不判 role 是否
        #    「正统审稿角色」——那归编排器主轴/tier-2 语义，门不越界）。
        if isinstance(role, str) and role.strip():
            roles.add(role.strip())
        role_loc = (role.strip()
                    if isinstance(role, str) and role.strip()
                    else f"<verdicts[{i}] role 缺失/非法>")

        # issues 非 list 的位置（tier-1 通常已拦）→ 结构化报后跳过 ②③
        if not isinstance(issues, list):
            reasons.append(
                f"verdicts[{i}]（role={role_loc}）.issues 非 list"
                f"（裸 {type(issues).__name__}）：无法判 issues 非空"
                f"（tier-2 prereq；通常 tier-1 已先拦下）")
            continue

        nonempty_issues = any(
            (not isinstance(it, str)) or it.strip() for it in issues)

        # ② pass=false 但 issues 空 = 无效裁决（判失败却无可定位 issue）。
        #    严格 bool 取值（pass 是关键字，用 v.get("pass")；tier-1 已保
        #    严格 bool，这里只对真 False 触发，非 bool 不臆断由 tier-1 管）。
        if pv is False and not nonempty_issues:
            reasons.append(
                f"verdicts[{i}]（role={role_loc}）pass=false 但 issues 为空"
                f"（规则② fail_needs_issues；判失败却无具体可定位 issue ="
                f"无效裁决，编排器无从回流处置）")

        # ③ 裁决一致性弱提示：pass=true 却携带非空 issues（判不准倾向报，
        #    交编排器主轴复核——要么 issue 是噪声、要么不该 pass）。
        if pv is True and nonempty_issues:
            reasons.append(
                f"verdicts[{i}]（role={role_loc}）pass=true 却携带非空 "
                f"issues={issues!r}（规则③ verdict_consistency；弱不一致"
                f"警示，判不准倾向报，编排器主轴复核裁决是否自相矛盾）")

    # ① 去重后不同 role 数 ≥ _REVIEW_MIN_ROLES（三角色齐才是一轮有效围审）
    if len(roles) < _REVIEW_MIN_ROLES:
        reasons.append(
            f"审稿角色覆盖不足：去重后 {len(roles)} 个不同 role "
            f"{sorted(roles)} < {_REVIEW_MIN_ROLES}（规则① roles_min；"
            f"风格审/铁律审/事实核查 三维度须齐，缺维度=该维度无人把关）")

    return reasons


# ===== 【第 7 节】词性比例门 I31 =====
# ============================================================================
# v5 新增：verify_pos_ratio（I31 形/副词 vs 名/动词比例检验）
# 关联：anti-ai-filter.md §1.7 文字密度天花板参照 + I31 量化检验
# 标准：
#   > 1:3 文笔可疑（形/副词过多 = AI 默认词堆砌）
#   < 1:5 接近阿城白描（极致名词+动词主导）
#   1:4 ~ 1:5 推荐区间（默认）
# ============================================================================

def verify_pos_ratio(text: str, sample_chars: int = 300) -> dict:
    """
    抽样计算文本的「形/副词 vs 名/动词」比例。

    :param text: 待检测文本（建议 ≥300 字段落）
    :param sample_chars: 抽样字符数（默认 300，对应 anti-ai-filter §1.7）
    :return: {
        'adj_adv_count': 形容词+副词数,
        'noun_verb_count': 名词+动词数,
        'ratio': 形/副词 ÷ 名/动词,
        'verdict': 'suspicious'(>1:3) | 'recommended'(1:4~1:5) | 'baimiao'(<1:5) | 'normal'(其他),
        'sample_length': 实际抽样字符数,
        'notes': 简短说明,
    }
    """
    try:
        import jieba.posseg as posseg
    except ImportError:
        return {
            'ratio': None,
            'verdict': 'jieba_missing',
            'notes': '需安装 jieba 库：pip install jieba',
        }

    if not text or not isinstance(text, str):
        return {'ratio': None, 'verdict': 'invalid_input', 'notes': '输入为空或非字符串'}

    # 抽样前剥离 frontmatter / 标题 / 卷首引语 blockquote：
    # 避免 300 字抽样窗口落在元数据和强标题上误判 -- 「卷首金句引语 + 反差标题」
    # 这类写法形容词天然密集，会让正文明明朴实却被判 suspicious。
    _lines = text.splitlines()
    if _lines and _lines[0].strip() == '---':
        for _i in range(1, len(_lines)):
            if _lines[_i].strip() == '---':
                _lines = _lines[_i + 1:]
                break
    _body_lines = [ln for ln in _lines
                   if not ln.strip().startswith('#') and not ln.strip().startswith('>')]
    _body = '\n'.join(_body_lines).strip() or text
    sample = _body[:sample_chars] if len(_body) > sample_chars else _body

    adj_adv = 0  # 形容词 a / 副词 d / 形容词派生 ad
    noun_verb = 0  # 名词 n* / 动词 v*
    for word, flag in posseg.cut(sample):
        if len(word.strip()) == 0:
            continue
        f = flag.lower()
        if f.startswith(('a', 'd')) and not f.startswith('an'):  # a/an=形容词性名词不算
            adj_adv += 1
        elif f.startswith(('n', 'v')):
            noun_verb += 1

    if noun_verb == 0:
        return {
            'adj_adv_count': adj_adv,
            'noun_verb_count': 0,
            'ratio': None,
            'verdict': 'no_content_words',
            'sample_length': len(sample),
            'notes': '抽样段落无名词/动词，可能不是正文',
        }

    ratio_value = adj_adv / noun_verb  # 形/副词 ÷ 名/动词

    if ratio_value > 1/3:  # > 0.333
        verdict = 'suspicious'
        notes = f'形/副词比例 {ratio_value:.3f} > 1:3（0.333）— AI 默认词堆砌嫌疑'
    elif ratio_value < 1/5:  # < 0.2
        verdict = 'baimiao'
        notes = f'形/副词比例 {ratio_value:.3f} < 1:5（0.2）— 接近阿城白描'
    elif 1/5 <= ratio_value <= 1/4:  # 0.2 ~ 0.25
        verdict = 'recommended'
        notes = f'形/副词比例 {ratio_value:.3f} 在 1:5 ~ 1:4 推荐区间'
    else:
        verdict = 'normal'
        notes = f'形/副词比例 {ratio_value:.3f} 在 1:4 ~ 1:3 之间（正常范围）'

    return {
        'adj_adv_count': adj_adv,
        'noun_verb_count': noun_verb,
        'ratio': round(ratio_value, 3),
        'verdict': verdict,
        'sample_length': len(sample),
        'notes': notes,
    }


# ===== 【第 8 节】加粗密度门 =====
# ============================================================================
# v5 新增（45 号实跑暴露 P1-4/P1-5）：verify_bold_density
# 关联：writing.md §加粗与重点标识 C3 + iron-rules.md 严禁整句加粗
# 标准（按字数档）：
#   <3000 字  → 粗体 ≤25  / 粗斜体 ≤5
#   3000-5000 → 粗体 ≤35  / 粗斜体 ≤7
#   5000-8000 → 粗体 ≤45  / 粗斜体 ≤9
#   >8000     → 粗体 ≤55  / 粗斜体 ≤12
# 整句加粗（≥15 中文字符的 **...** 块）：严禁，>0 即违规
# ============================================================================

def verify_bold_density(text: str, integral_threshold_chars: int = 15) -> dict:
    """
    校验 markdown 文本的粗体密度 + 整句加粗违规。

    :param text: 待检测的 markdown 全文
    :param integral_threshold_chars: 「整句加粗」的中文字符阈值（默认 15）
    :return: {
        'word_count': 中文字符数,
        'tier': '<3000' | '3000-5000' | '5000-8000' | '>8000',
        'bold_limit': 粗体上限,
        'italic_bold_limit': 粗斜体上限,
        'bold_count': 实际粗体数,
        'italic_bold_count': 实际粗斜体数,
        'integral_bold_count': 整句加粗数（≥阈值字符的粗体）,
        'integral_bold_samples': 前 3 个违规整句样本,
        'verdict': 'ok' | 'bold_over' | 'integral_bold_violation' | 'both_violations',
        'notes': str,
    }
    """
    import re

    if not text or not isinstance(text, str):
        return {'verdict': 'invalid_input', 'notes': '输入为空'}

    # 1. 中文字数（按档）
    word_count = len(re.findall(r'[一-鿿]', text))
    if word_count < 3000:
        tier = '<3000'
        bold_limit, italic_bold_limit = 25, 5
    elif word_count < 5000:
        tier = '3000-5000'
        bold_limit, italic_bold_limit = 35, 7
    elif word_count < 8000:
        tier = '5000-8000'
        bold_limit, italic_bold_limit = 45, 9
    else:
        tier = '>8000'
        bold_limit, italic_bold_limit = 55, 12

    # 2. 提取所有 ***粗斜体*** 和 **粗体**（粗斜体优先匹配）
    italic_bold_blocks = re.findall(r'\*\*\*[^*]+\*\*\*', text)
    # 去掉粗斜体后剩下的粗体
    text_no_italic = re.sub(r'\*\*\*[^*]+\*\*\*', '', text)
    bold_blocks = re.findall(r'\*\*[^*]+\*\*', text_no_italic)

    bold_count = len(bold_blocks)
    italic_bold_count = len(italic_bold_blocks)

    # 3. 整句加粗（≥integral_threshold_chars 中文字符）
    integral_bold = []
    for b in bold_blocks + italic_bold_blocks:
        zh_in_b = len(re.findall(r'[一-鿿]', b))
        if zh_in_b >= integral_threshold_chars:
            integral_bold.append(b)

    # 4. 裁决
    bold_over = bold_count > bold_limit
    italic_over = italic_bold_count > italic_bold_limit
    integral_violation = len(integral_bold) > 0

    if (bold_over or italic_over) and integral_violation:
        verdict = 'both_violations'
    elif integral_violation:
        verdict = 'integral_bold_violation'
    elif bold_over or italic_over:
        verdict = 'bold_over'
    else:
        verdict = 'ok'

    notes_parts = []
    if bold_over:
        notes_parts.append(f'粗体 {bold_count} > 上限 {bold_limit}')
    if italic_over:
        notes_parts.append(f'粗斜体 {italic_bold_count} > 上限 {italic_bold_limit}')
    if integral_violation:
        notes_parts.append(f'整句加粗 {len(integral_bold)} 处（严禁）')
    notes = '；'.join(notes_parts) if notes_parts else f'通过：粗体 {bold_count}/{bold_limit}，粗斜体 {italic_bold_count}/{italic_bold_limit}，无整句加粗'

    return {
        'word_count': word_count,
        'tier': tier,
        'bold_limit': bold_limit,
        'italic_bold_limit': italic_bold_limit,
        'bold_count': bold_count,
        'italic_bold_count': italic_bold_count,
        'integral_bold_count': len(integral_bold),
        'integral_bold_samples': [b[:60] for b in integral_bold[:3]],
        'verdict': verdict,
        'notes': notes,
    }




# ===== 【第 9 节】发布素材门 =====
def verify_publish_assets(article_dir: str) -> dict:
    """
    校验「发布前素材门」-- 把 layout.md 步骤1 前置检查 1-7 全部代码化。
    2026-05-21 新增（45 号 v5 实跑暴露：手工发布跳过素材嵌入检查 -> publish 流程没拦下）。

    检查项（任一失败 verdict=fail，全过 verdict=ok）：
      1. 定稿.md 存在
      2. 定稿.md 含 frontmatter（title + description）
      3. 素材/*.png 的每张图都在 定稿.md 中有 ![ 引用
      4. AUDIO-CARD（若存在）只出现一次且位于文件最末尾区块；
         状态感知：.state.json 的 bgm 阶段 == done 而 AUDIO-CARD 缺失 → error（BGM 静默丢失），
         bgm 为 pending/skip/无 state 时维持软兜底（历史归档文章不误伤）
      5. 定稿.md 不含 [插图] 占位符
      6. 信息来源（若存在）不使用 ### H3 标题
      7. 信息来源（若存在）不含 markdown 链接语法 [title](url)

    :param article_dir: 文章工作目录（含 定稿.md + 素材/）
    :return: {
        'verdict': 'ok' | 'fail' | 'no_article',
        'errors': [str],        # 阻塞错误，会让 format_layout 退出 2
        'warnings': [str],      # 提示性，不阻塞
        'checks_passed': int,
        'checks_total': 7,
    }
    """
    import re
    from pathlib import Path

    base = Path(article_dir)
    md = base / '定稿.md'
    errors = []
    warnings = []
    passed = 0
    total = 7

    if not md.exists():
        return {
            'verdict': 'no_article',
            'errors': ['定稿.md 不存在'],
            'warnings': [],
            'checks_passed': 0,
            'checks_total': total,
        }
    passed += 1
    text = md.read_text(encoding='utf-8')

    # 状态感知用的软读 .state.json：找不到/损坏一律退回 {}（不裸崩、不 sys.exit，
    # 与 pipeline.load_state 的硬退出语义刻意分开——本素材门要能在无 state 的散文目录
    # 上跑）。下面 check#4(BGM 硬门) / 信息图前移门 据此决定「软兜底」还是「硬校验」。
    import json as _json
    def _stage_status(stage_name: str) -> "str|None":
        sp = base / '.state.json'
        if not sp.exists():
            return None
        try:
            st = _json.loads(sp.read_text(encoding='utf-8'))
            return (st.get('stages', {}) or {}).get(stage_name, {}).get('status')
        except Exception:
            return None

    # 2) frontmatter title + description（H1 兜底）
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        has_title = bool(re.search(r'^\s*title\s*:', fm, re.MULTILINE))
        has_desc = bool(re.search(r'^\s*description\s*:', fm, re.MULTILINE))
        if not has_title or not has_desc:
            errors.append(
                f'定稿.md frontmatter 缺字段：'
                f'{"" if has_title else "title "}{"" if has_desc else "description "}'.strip()
            )
        else:
            passed += 1
    else:
        # 兜底：允许走 H1（baoyu-markdown-to-html 会从 H1 取 title），
        # 但缺 description 则警告
        if re.search(r'^# .+', text, re.MULTILINE):
            warnings.append('定稿.md 无 frontmatter（H1 可作 title 兜底，但缺 description）')
            passed += 1
        else:
            errors.append('定稿.md 既无 frontmatter 也无 H1，title/description 无来源')

    # 3) 素材/*.png 全部在 .md 中引用
    #    排除：cover/hero/bgm_cover/logo 这类「不在正文嵌入」的组件小图（由排版/发布流程单独使用）。
    #    music_cover.png 是 bgm_cover.png 的历史别名（兜底兼容），logo-black.png 是名片 logo
    #    防二次套印的姊妹件（2026-06-20 补齐，原本漏这两项会误把残留组件小图当未嵌入正文图报 error）。
    #    ⚠️ 三张跳过表「语义不同、刻意不完全一致」，别强行对齐：本表（嵌入检查）含 cover.png（封面不嵌正文）；
    #    add_logo.js SKIP_FILES 不含 cover.png（封面要打水印）；compress_images.py 只跳组件小图。
    #    共同子集是 hero/bgm_cover/music_cover/logo-white/logo-black，差异项各有设计理由。
    SKIP_PNG = {
        'cover.png', 'hero.png', 'bgm_cover.png', 'music_cover.png',
        'logo.png', 'logo-white.png', 'logo-black.png',
    }
    src_dir = base / '素材'
    if src_dir.exists():
        png_files = sorted(
            p for p in src_dir.glob('*.png')
            if not p.name.startswith('_') and p.name not in SKIP_PNG
        )
        missing = []
        for png in png_files:
            ref_patterns = [
                f']({png.relative_to(base).as_posix()})',
                f']({png.name})',
                f']({png.relative_to(base)})',
            ]
            if not any(p.replace('\\', '/') in text.replace('\\', '/') for p in ref_patterns):
                missing.append(png.name)
        if missing:
            errors.append(f'素材/*.png 未在 定稿.md 嵌入：{missing}')
        else:
            passed += 1
    else:
        warnings.append('素材/ 目录不存在，跳过图片嵌入检查')
        passed += 1

    # 4) AUDIO-CARD 位置 (BGM 2026-06-18 复活；对历史归档文章软兜底，硬存在校验
    #    见 pipeline.py verify bgm)。状态感知：读 .state.json 的 bgm 阶段——
    #      · 若 stages.bgm.status == 'done'（本文已声明产出 BGM）→ AUDIO-CARD 缺失判 error；
    #      · 若 bgm 为 pending/skip/无 state（历史 34/36/40 号归档文章无 bgm=done）→ 维持软兜底放行。
    #    历史 golden 基线仍含/不含 AUDIO-CARD 块均不误伤：缺失只在 bgm=done 时才硬拦。
    bgm_status = _stage_status('bgm')
    audio_marks = list(re.finditer(r'<!-- AUDIO-CARD-START -->', text))
    if not audio_marks:
        if bgm_status == 'done':
            # 本文已声明 BGM 阶段完成却无 AUDIO-CARD 块 → BGM 静默丢失，硬拦
            errors.append('bgm 阶段已标 done 但 定稿.md 无 AUDIO-CARD 块（BGM 产物缺失，疑似静默丢失）')
        else:
            passed += 1  # bgm 未声明产出（pending/skip/无 state）→ 软兜底，不存在是正常情况
    elif len(audio_marks) > 1:
        errors.append(f'AUDIO-CARD 块出现 {len(audio_marks)} 次（历史遗留, 应仅 1 次）')
    else:
        # 历史归档兼容: 距文末 ≤ 800 字符 即视为末尾
        last_idx = audio_marks[0].start()
        tail_chars = len(text) - last_idx
        if tail_chars > 800:
            warnings.append(
                f'AUDIO-CARD 距文末 {tail_chars} 字符 (历史归档兼容, 不强制)'
            )
        passed += 1

    # 5) [插图] 占位符
    if '[插图]' in text:
        errors.append('定稿.md 仍含 [插图] 占位符（必须替换为 ![alt](path)）')
    else:
        passed += 1

    # 6) 信息来源不使用 H3
    if re.search(r'^### .{0,8}(信息来源|参考资料|参考文献|引用来源)', text, re.MULTILINE):
        errors.append('信息来源使用了 ### H3 标题（会被转为时间线格式，应用 <section>）')
    else:
        passed += 1

    # 7) 信息来源段不含 [title](url) markdown 链接
    info_block = re.search(
        r'(?:📎\s*信息来源|信息来源)([\s\S]{0,3000}?)(?=\n##|\Z)',
        text,
    )
    if info_block:
        body = info_block.group(1)
        if re.search(r'\[[^\]]+\]\(https?://[^)]+\)', body):
            errors.append(
                '信息来源含 [title](url) MD 链接语法（baoyu --cite 会重复展开，请改纯文本）'
            )
        else:
            passed += 1
    else:
        warnings.append('未识别到「信息来源」段（深度文若有引用源建议补；非引用类文章可忽略）')
        passed += 1

    # 附加信号（不计入 checks_total 的 7 项契约，仅 warning）：信息图张数前移检查。
    # 把「信息图缺图」信号从 publish/verify infographic 前移到排版阶段（原本要到
    # pipeline.py verify infographic 才暴露，41 号曾漏整组直到 publish 后才发现）。
    # 状态感知 + 软提示：仅当 stages.infographic.status == 'done' 时才扫张数，<4 张报
    # warning（不 error）——故意不阻塞，避免误伤无信息图的历史 golden 34/36/40 现有测试。
    if _stage_status('infographic') == 'done' and src_dir.exists():
        info_pngs = [p for p in src_dir.glob('infographic*.png') if not p.name.startswith('_')]
        if len(info_pngs) < 4:
            warnings.append(
                f'infographic 阶段已标 done 但 素材/infographic*.png 仅 {len(info_pngs)} 张'
                f'（建议 ≥4 张；硬校验见 pipeline.py verify infographic）'
            )

    return {
        'verdict': 'ok' if not errors else 'fail',
        'errors': errors,
        'warnings': warnings,
        'checks_passed': passed,
        'checks_total': total,
    }


# ===== 【第 10 节】导读 lead 块门 =====
def verify_article_meta_lead(article_dir: str) -> dict:
    """
    校验 article-meta.yaml 的 lead 块完整性（line1/line2/subtitle 必填）。
    2026-05-21 新增（45 号 v5 实跑暴露：导读栏使用默认占位文案"深度拆解/硬核干货"
    -> 因 article-meta.yaml 没填 lead 块 -> writing.md 无强制 -> 漏看 format_layout 警告）。

    Verdict 语义（lead 是排版强烈建议项，非硬阻塞）：
      - ok: line1+line2+subtitle 三项均非空
      - warning: 缺一或多项（不阻塞 format_layout，仅提示）
      - no_meta: article-meta.yaml 不存在

    :param article_dir: 文章工作目录
    :return: {
        'verdict': 'ok' | 'warning' | 'no_meta',
        'missing': [str],   # 缺失的字段
        'notes': str,
    }
    """
    from pathlib import Path

    meta_path = Path(article_dir) / 'article-meta.yaml'
    if not meta_path.exists():
        return {
            'verdict': 'no_meta',
            'missing': ['article-meta.yaml'],
            'notes': 'article-meta.yaml 不存在，跳过 lead 校验',
        }

    try:
        import yaml
        meta = yaml.safe_load(meta_path.read_text(encoding='utf-8')) or {}
    except Exception as e:
        return {
            'verdict': 'warning',
            'missing': [],
            'notes': f'yaml 解析失败：{e}',
        }

    # 优先读嵌套 lead.line1/line2/subtitle；兼容扁平 lead_line1/...
    lead = meta.get('lead') if isinstance(meta.get('lead'), dict) else {}
    line1 = lead.get('line1') or meta.get('lead_line1') or ''
    line2 = lead.get('line2') or meta.get('lead_line2') or ''
    subtitle = lead.get('subtitle') or meta.get('lead_subtitle') or ''
    tag1 = lead.get('tag1') or meta.get('lead_tag1') or ''
    tag2 = lead.get('tag2') or meta.get('lead_tag2') or ''

    missing = []
    if not line1.strip():
        missing.append('line1')
    if not line2.strip():
        missing.append('line2')
    if not subtitle.strip():
        missing.append('subtitle')

    # 实测踩坑：加固：tag1/tag2 长度审计
    # 计算"视觉宽度"：中文 1 字、英数 0.5 字、空格不计
    # 超 4 字宽会导致导读栏底栏胶囊在窄屏换行（45 号实证：「AI 时代育儿」5 字断成两行）
    def _visual_width(s: str) -> float:
        import re as _re
        w = 0.0
        for ch in s:
            if ch == ' ':
                continue
            if _re.match(r'[一-鿿]', ch):
                w += 1.0
            else:
                w += 0.5
        return w

    tag_warnings = []
    for tag_name, tag_value in [('tag1', tag1), ('tag2', tag2)]:
        if tag_value.strip():
            vw = _visual_width(tag_value)
            if vw > 4.0:
                tag_warnings.append(
                    f'{tag_name}="{tag_value}" 视觉宽度 {vw} 超过 4 字上限'
                    f'（中文 1 字 / 英数 0.5 字 / 空格不计），导读栏底栏胶囊会换行'
                )

    if not missing and not tag_warnings:
        return {
            'verdict': 'ok',
            'missing': [],
            'notes': '导读栏字段完整',
        }

    notes_parts = []
    if missing:
        notes_parts.append(
            f'article-meta.yaml lead 块缺字段：{missing}。'
            f'排版会回退到通用占位文案"深度拆解/硬核干货"，发布前建议补全'
        )
    notes_parts.extend(tag_warnings)
    return {
        'verdict': 'warning',
        'missing': missing,
        'notes': ' | '.join(notes_parts),
    }


# ===== 【第 11 节】B-主门 AI 腔黑名单 =====
# ============================================================================
# B-主门：verify_anti_ai_blacklist（2026-05-22 Team refs-activation 落地）
# 把反例对照库 50 对里「有显性字符串特征」的约 30 对编译成黑名单正则，扫成稿。
# 设计铁律（skeptic 健康标尺）：谓词只能是「X 出现了吗」，不做任何「X 好不好」的语义判断。
# 分两档防误杀：A 档（_BLACKLIST_HARD）零误杀固定套话，命中即 fail；
#              B 档（_BLACKLIST_SOFT）有上下文风险，命中只 warning。
# ============================================================================

def _strip_for_scan(text: str) -> str:
    """清洗 定稿.md，剔除不该被黑名单扫描的部分，避免假阳性：
    frontmatter / HTML 标签注释 / 引用块 `>` 行（引别人的话）/ 信息来源 section。
    保留换行，便于 multiline 匹配与行号定位。
    """
    import re
    # 2026-05-22 系统化（旁观者复核：不再「踩一个坑补一个」，一次梳理 md 语法全集）
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.DOTALL)
    text = re.sub(r'```[\s\S]*?```', '', text)             # 围栏代码块
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)                    # HTML 标签
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)       # 图片（须在链接前处理）
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)   # 链接：留可见文字、去 url
    text = re.sub(r'`[^`\n]+`', '', text)                  # 行内代码
    text = re.sub(r'(?:📎\s*)?信息来源[\s\S]*?(?=\n##\s|\Z)', '', text)
    lines = [ln for ln in text.split('\n') if not ln.lstrip().startswith('>')]
    return '\n'.join(lines)


# A 档：命中即 fail（exit 2）。固定套话，几乎零误杀。(正则, 标签, ✅修复方向)
_BLACKLIST_HARD = [
    (r'本文将(?:为|带|和|与)', '开头宣告「本文将…」', '直接入场，第一句给画面/判断/数字'),
    (r'在这个[^，。、\n]{1,10}的时代', '「在这个 X 的时代」教科书腔', '用具体时间+地点开篇'),
    (r'随着[^，。\n]{0,12}(?:飞速|快速|迅猛|蓬勃)发展', '「随着…飞速发展」陈词', '亲历直入，给一手场景'),
    (r'我们(?:就)?来(?:聊聊|说说|谈谈)(?:吧)?', '「我们来聊聊」', '主语「我」直接入场'),
    (r'日新月异', '「日新月异」陈词', '换具体数字'),
    (r'自古以来', '「自古以来」', '亲历直入，12 字内给场景+动作'),
    (r'人类(?:从未停止|一直在追)', '「人类从未停止…」宏大开场', '从一个具体的人/事切入'),
    (r'致力于打造|打造极致', '「致力于打造/打造极致」', '直接说在做什么'),
    (r'让我们(?:一起|携手)', '「让我们一起/携手」套路收尾', '收回半步，把判断留给读者'),
    (r'拭目以待', '「拭目以待」', '用未答之问收尾'),
    (r'迎接[^，。\n]{0,8}(?:未来|春天|时代|明天)', '「迎接…未来」升维收尾', '收尾止于「我们这个社会」'),
    (r'(?:全方位|根本性|前所未有)地', '抽象副词「全方位地/根本性地」', '用具体动作链替代'),
    (r'毋庸置疑|不言而喻|细思极恐|不禁让人', '判断性陈词（毋庸置疑等）', '拿出证据，否则删掉该判断'),
    (r'久久(?:无法|不能|难以)平静|五味杂陈|泪水(?:模糊|打转|盈眶)', '抒情过度（一份感情十份用）', '一份情用一份字，用动作链'),
    (r'在当今社会|瞬息万变|跟上时代的步伐', '万能腔（在当今社会等）', '换具体数字'),
    (r'万万没想到|太绝了|太牛了', '标题党用语', '用反问/克制陈述代替'),
    (r'时代的浪潮|关乎人类(?:的)?未来', '升维到全人类', '升维止于「我们这个社会」'),
    (r'愿你[^，。\n]{0,12}|愿这[份篇]', '「愿你…」期许托付套路', '用未答之问收尾'),
]

# 导游腔元话语档：命中即 fail（exit 2）。2026-06-10 新增（49 号实证：6 处报幕句，
# 人类范文 0 处）。文章谈论自身结构 = 把读者从内容里踢出来、暴露写作脚手架，
# 是「不像人与人自然对话」的最大单一来源。伏笔回收靠重复具体意象，不靠「还记得吗」。
# 注意：cut_empty_transition 删掉书面空转场后，模型会换口语皮的同功能报幕
# （「聊到这儿」「这么一说」），所以这批触发词必须机器扫，不能靠写作期自觉。
_META_DISCOURSE_HARD = [
    (r'(?:我们)?不妨[^，。\n]{0,6}拆[成开]', '报幕「不妨拆成 N 件事」', '删报幕句，直接讲第一件事'),
    (r'先说最[^，。\n]{1,4}的', '报幕「先说最直观的」', '直接说，不预告顺序'),
    (r'后面再(?:说|讲|聊)', '报幕「这点后面再说」', '要么现在说，要么不提；伏笔靠具体意象自然回收'),
    (r'聊到这[儿里]', '口语皮报幕「聊到这儿」', '删过渡报幕，下一段直接从新画面/新问题进'),
    (r'还记得(?:前面|刚才|上面)', '报幕「还记得前面」', '伏笔回收靠原样重复那个具体意象/数字，不问读者记不记得'),
    (r'(?:临了|末了)[^，。\n]{0,10}(?:留|提)个问题', '报幕「临了留个问题」', '问题直接问，不宣告自己要问'),
    (r'翻译过来就是', '报幕「翻译过来就是」', '直接给那句人话，删翻译宣告'),
    (r'听起来(?:有点|很|挺)抽象', '报幕「听起来有点抽象」', '觉得抽象就直接给例子，不评论自己上一句'),
    (r'先别急着(?:说|讲|看|冲|下|亮|上)', '悬念延迟「先别急着说 X」', '直接说，别吊读者胃口——资讯/成果类读者要干货时被"先别急着"打断最恼人（2026-07-02 C11）'),
    (r'重点来了[：:]?', 'infomercial 钩子「重点来了」', '直接说重点，不预告（2026-07-02 C16 融合 avoid-ai-writing）'),
    (r'反转(?:来了|来啦)|反转(?:的地方)?就?在[于这]', 'infomercial 钩子「反转来了」', '直接讲那个反转，不预告'),
    (r'有(?:意思|趣)的(?:地方|点|是)[^，。\n]{0,4}(?:在于|是)[：:]', 'infomercial 钩子「有意思的地方在于」', '直接说那个点，不贴"有意思"标签'),
]

# AI 残留物档：命中即 fail（exit 2）。2026-07-02 C16 融合 conorbronsdon/avoid-ai-writing 候选1
# （语言无关、纯增量）：AI 工具指纹 URL 参数 / 引用标记 / 未填占位符——它们的存在本身
# 就是"从 AI 抓料或生成后没清理干净"的签名，与周围文字写得多像人无关。
# 🔴 扫原文（不经 _strip_for_scan），否则 utm_source 在 URL 里会被链接清洗吃掉。
_AI_ARTIFACT_HARD = [
    (r'utm_source=(?:chatgpt|claude|perplexity|openai|gemini|copilot)', 'AI 工具 URL 尾巴', '删 URL 的 ?utm_source=... 参数，只留干净链接'),
    (r'citeturn\d|oai_citation|turn\d+search\d', 'chat 引用标记泄漏', '删 citeturn/oai_citation/turnXsearchX 这类抓取残留标记'),
    (r'\[(?:INSERT|YOUR|Your Name|待核实|待补充|待填|占位|TODO|TK)', '未填占位符', '发布前必须填实或删除占位符'),
    (r'请主理人在此补充|\[⚠️', '§六 占位符未填', '§六人类经验插槽占位符还在——补真实亲历细节或删该段'),
    (r'20\d{2}-XX-XX|20\d{2}年X月|XX月XX日', '未填日期占位', '填实际日期或删'),
]

# B 档：命中只 warning（不阻塞）。有上下文误杀风险。
_BLACKLIST_SOFT = [
    (r'不[只仅](?:是|仅是)[^，。\n]{1,20}[，,][^，。\n]{0,4}(?:更|还|而)是', '负向平行「不只是 X 更是 Y」', '排比要挂具体场景或带反转'),
    (r'从[^，。\n]{1,8}到[^，。\n]{1,8}[，,]\s*从[^，。\n]{1,8}到', '「从 X 到 Y」连用', '用精确数字+具体动作替代'),
    (r'作为(?:一[名个位])?[^，。\n]{0,12}(?:观察者|从业者|先行者)[，,]', '「作为一个 X 者」立人设', '把自己写笨，不立权威人设'),
    (r'(?:调查|数据|研究)显示|(?:行业|业内人士)(?:普遍)?认为|专家(?:指出|表示)', '可能数据无源', '给具名信源：年份/期刊/姓名/可复核'),
    (r'显而易见|众所周知|方方面面', '陈词（显而易见/众所周知）', '若非反讽路由，改具体表达'),
    (r'面临[^。\n]{0,30}挑战[，,。][^。\n]{0,20}但[^。\n]{0,8}相信', '「面临挑战但相信」三段式', '硬切金句作结，不给免责声明'),
]


def verify_anti_ai_blacklist(article_path: str) -> dict:
    """
    B-主门：确定性 AI 腔黑名单硬验证。只问「固定套话字符串出现了吗」。

    🔴 诚实边界（必须随方案一起声明，不可省略）：
    黑名单源自反例对照库 50 对里「有显性字符串特征」的约 30 对。剩下约 40%
    是语义类反例（So What 缺失 / 类比缺位 / 反常细节缺失），正则零能力。
    **B-主门 verdict=ok ≠ AI 味已清除，只 = 显性 AI 套话已清。** 语义层靠
    anti-ai-filter.md 磨稿 + SKILL.md 内嵌正向规则 + Claude 自觉。

    :param article_path: 定稿.md 路径
    :return: {
        'verdict': 'ok' | 'fail' | 'no_article',
        'errors': [...],     # A 档命中，阻塞（format_layout exit 2）
        'warnings': [...],   # B 档命中 + 感叹号超标，不阻塞
        'hard_hits': int, 'soft_hits': int,
    }
    """
    import re
    from pathlib import Path

    p = Path(article_path)
    if not p.exists():
        return {'verdict': 'no_article', 'errors': [f'{article_path} 不存在'],
                'warnings': [], 'hard_hits': 0, 'soft_hits': 0}

    raw = p.read_text(encoding='utf-8')
    text = _strip_for_scan(raw)
    errors, warnings = [], []

    # 引号跨度（"" 「」 『』 ''）：报幕命中若整体落在引语内 = 被当例子/引语讨论，
    # 不是作者自己的元话语腔，降级为提示而非硬拦（50 号实证：文章在举例
    # 「还记得前面说的吗」这类要拦截的反例时，被自己的门判 exit 2）。凡写"AI 写作"
    # 题材都会踩——quoted ≠ 作者声音。仅对导游腔门生效；显性套话黑名单不放行（防引号藏腔）。
    _qspans = [(m.start(), m.end()) for m in re.finditer(
        r'“[^”]*”|「[^」]*」|'
        r'『[^』]*』|‘[^’]*’', text)]

    def _quoted(s, e):
        return any(a <= s and e <= b for a, b in _qspans)

    # AI 残留物（工具指纹/占位符）扫原文——不经 strip，防 URL 参数被链接清洗吃掉（2026-07-02 C16）
    for pattern, label, fix in _AI_ARTIFACT_HARD:
        for m in re.finditer(pattern, raw, re.IGNORECASE):
            line_no = raw[:m.start()].count('\n') + 1
            errors.append(f'[L~{line_no}] AI 残留物·{label}：命中「{m.group(0)}」→ {fix}')

    for pattern, label, fix in _BLACKLIST_HARD:
        for m in re.finditer(pattern, text):
            line_no = text[:m.start()].count('\n') + 1
            errors.append(f'[L~{line_no}] {label}：命中「{m.group(0)}」→ 改为：{fix}')

    for pattern, label, fix in _META_DISCOURSE_HARD:
        for m in re.finditer(pattern, text):
            line_no = text[:m.start()].count('\n') + 1
            if _quoted(m.start(), m.end()):
                warnings.append(
                    f'[L~{line_no}] 导游腔元话语·{label}：命中「{m.group(0)}」但落在引号内'
                    f'（当例子/引语讨论，非作者腔），降级提示。若确属作者元话语请改：{fix}')
            else:
                errors.append(f'[L~{line_no}] 导游腔元话语·{label}：命中「{m.group(0)}」→ {fix}')

    for pattern, label, fix in _BLACKLIST_SOFT:
        for m in re.finditer(pattern, text):
            line_no = text[:m.start()].count('\n') + 1
            warnings.append(f'[L~{line_no}] {label}：命中「{m.group(0)}」→ 建议：{fix}')

    excl = text.count('！') + text.count('!')
    if excl > 5:
        warnings.append(f'感叹号 {excl} 个（>5）：考虑用反问替代部分感叹')

    return {
        'verdict': 'fail' if errors else 'ok',
        'errors': errors,
        'warnings': warnings,
        'hard_hits': len(errors),
        'soft_hits': len(warnings),
    }


# ===== 【第 12 节】B-软门 风格信号 =====
# ============================================================================
# B-软门：audit_style_signals（2026-05-22 Team refs-activation 落地）
# team 定调：只打印自查信息，永不 pass/fail、不设阈值——避免诱导「为过门硬凑词」
# （那正是 verify_compact_strokes 的病根）。仅做 vocab 命中「存在性」检测。
# ============================================================================

def audit_style_signals(article_path: str, vocab_pool_path: str = None) -> dict:
    """
    B-软门：风格信号软审计。**永不阻塞**，只输出 vocab 命中自查信息。

    检测 作者 词汇温度池里的词在 定稿.md 的命中存在性。
    三档 verdict：命中 0 → blocked（软阻塞 exit 1）；1-4 → warning（偏低，不阻塞）；
    >=5 → info（正常诊断）。报命中绝对数，不报 N/213 失真比率。
    不设「命中 N 个才达标」的硬阈值——硬凑词 = 新的 AI 味。

    :param article_path: 定稿.md 路径
    :param vocab_pool_path: vocab-pool.md 路径（None = 自动定位 profile/corpus/）
    :return: {
        'verdict': 'info' | 'warning' | 'blocked' | 'no_article',
        'vocab_total': int, 'vocab_hits': int, 'hit_words': [...],
        'warnings': [...], 'notes': str,
    }
    """
    import re
    from pathlib import Path

    ap = Path(article_path)
    if not ap.exists():
        return {'verdict': 'no_article', 'notes': f'{article_path} 不存在',
                'vocab_total': 0, 'vocab_hits': 0, 'hit_words': [], 'warnings': []}
    text = ap.read_text(encoding='utf-8')

    if vocab_pool_path is None:
        # 词汇池是**可选**的私有语料，放在你的 profile 里：profile/corpus/vocab-pool.md
        # 没有就跳过这项软审计（它只是提示你用词是否单调，不是硬门）。
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from profile_config import corpus_dir as _corpus_dir
            vocab_pool_path = _corpus_dir() / 'vocab-pool.md'
        except Exception:
            return {'verdict': 'info', 'notes': 'profile 不可用，跳过词汇池软审计',
                    'vocab_total': 0, 'vocab_hits': 0, 'hit_words': [], 'warnings': []}
    vp = Path(vocab_pool_path)
    if not vp.exists():
        return {'verdict': 'info', 'notes': f'vocab-pool 不存在：{vp}，跳过软审计',
                'vocab_total': 0, 'vocab_hits': 0, 'hit_words': [], 'warnings': []}

    # 抽 vocab 词：markdown 表格第一列，按 / ／ 拆分变体
    vocab_words = []
    for line in vp.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s.startswith('|') or s.startswith('|--') or '| 词 ' in s:
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if not cells or not cells[0]:
            continue
        for w in re.split(r'[/／]', cells[0]):
            w = w.strip()
            if len(w) >= 2:
                vocab_words.append(w)
    vocab_words = list(dict.fromkeys(vocab_words))

    hits = [w for w in vocab_words if w in text]
    n = len(hits)

    # 三档 verdict（2026-05-22 旁观者复核重设计：12 词和 1 词不能同判 info，
    # 否则软门诊断价值≈0）。报「命中绝对数」不报「N/213」失真比率。
    #   0     → blocked：写作没用 prep 的铁证，软阻塞 exit 1
    #   1-4   → warning：命中偏低，建议回查是否真内化 _prep-context.md（不阻塞）
    #   >=5   → info：正常诊断（参考带 ≥8 更理想；不设硬阈值，硬卡会逼作弊）
    if vocab_words and n == 0:
        return {
            'verdict': 'blocked',
            'vocab_total': len(vocab_words), 'vocab_hits': 0, 'hit_words': [],
            'warnings': [
                '定稿一个 vocab 温度池词都没命中 —— 几乎可断定写作时没看 '
                '_prep-context.md 的词汇配方'
            ],
            'notes': 'vocab 命中 0 词 —— 软阻塞：回去内化 _prep-context.md '
                     '重写，或 --skip-preflight 跳过并说明理由',
        }
    if n < 5:
        return {
            'verdict': 'warning',
            'vocab_total': len(vocab_words), 'vocab_hits': n, 'hit_words': hits,
            'warnings': [
                f'vocab 温度词仅命中 {n} 个（参考带 ≥8 较理想）—— 偏低，'
                f'建议回查是否真内化了 _prep-context.md 的词汇配方'
            ],
            'notes': f'vocab 温度词命中 {n} 个（偏低，warning 不阻塞）',
        }
    return {
        'verdict': 'info',
        'vocab_total': len(vocab_words), 'vocab_hits': n, 'hit_words': hits[:20],
        'warnings': [],
        'notes': f'vocab 温度词命中 {n} 个（软审计诊断，不阻塞；参考带 ≥8）',
    }


# ===== 【第 13 节】半角标点门 =====
# ============================================================================
# verify_cjk_punctuation（2026-05-22 旁观者复核新增）
# v6 实战踩坑：正文 10 处中文间半角逗号/冒号。谓词是确定性的「中文紧邻半角
# 标点了吗」，做硬门。用 _strip_for_scan 清洗，规避代码/URL/时间/比例里的合法半角。
# ============================================================================

def verify_cjk_punctuation(article_path: str) -> dict:
    """
    检测中文字符间误用的半角标点（应为全角）。命中即 fail（确定性硬门）。

    只查 , ; : ! ? 五种（句号 . 不查 —— 与小数点冲突）。时间 15:38 / 比例 16:9
    因两侧是数字不命中；代码/URL 已被 _strip_for_scan 清掉。

    :param article_path: 定稿.md 路径
    :return: {'verdict': 'ok'|'fail'|'no_article', 'errors': [...], 'hits': int}
    """
    import re
    from pathlib import Path

    p = Path(article_path)
    if not p.exists():
        return {'verdict': 'no_article', 'errors': [f'{article_path} 不存在'], 'hits': 0}

    text = _strip_for_scan(p.read_text(encoding='utf-8'))
    full = {',': '，', ';': '；', ':': '：', '!': '！', '?': '？'}
    errors = []
    for m in re.finditer(r'[一-鿿][,;:!?]|[,;:!?][一-鿿]', text):
        line_no = text[:m.start()].count('\n') + 1
        seg = m.group(0)
        half = next(c for c in seg if c in full)
        errors.append(
            f'[L~{line_no}] 中文间半角「{half}」（在「{seg}」）→ 应改全角「{full[half]}」'
        )
    return {
        'verdict': 'fail' if errors else 'ok',
        'errors': errors,
        'hits': len(errors),
    }


# ===== 【第 14 节】产物 HTML 门 =====
# ============================================================================
# verify_final_html（2026-07-07 · 借鉴 gzh-design「产物关」思想，独立自研）
# 组件层 process_wechat_compat 是「相信剥干净」的单点信任；本门在排版后、publish 前
# 独立解析 定稿.html，断言不含「format_layout 绝不该产出、且真会破渲染」的平台违规。
# 🔑 校准（对真实 golden 定稿.html 实测）：**不查 <div>/class/id/flex/float**——baoyu 会大量
#    产出 class="p"/"td" 语义类 + <div id="output"> 工作壳 + display:flex（均实测正常发布），
#    查它们会全量误杀。只查以下 8 类「零合法出现 + 真破渲染」的硬违规（含 P2-2 四周虚线 WARN）。
# ============================================================================

def verify_final_html(html_path: str) -> dict:
    """排版后产物关：独立断言 定稿.html 不含破渲染的平台违规。

    命中任一硬违规即 fail（确定性硬门）。四周虚线框（正文强调禁用、仅居中占位例外）作 WARN。

    :param html_path: 定稿.html 路径
    :return: {'verdict':'ok'|'fail'|'no_article', 'errors':[...], 'warnings':[...], 'hits':int}
    """
    import re
    from pathlib import Path

    p = Path(html_path)
    if not p.exists():
        return {'verdict': 'no_article', 'errors': [f'{html_path} 不存在'], 'warnings': [], 'hits': 0}

    raw = p.read_text(encoding='utf-8', errors='replace')
    body = re.sub(r'<!--.*?-->', '', raw, flags=re.DOTALL)  # 剥 HTML 注释

    # 只查「零合法出现 + 真破渲染」8 类（flex/float/div/class/id 均合法出现，不查）。
    # 2026-07-10 独立重写：检查表直接从「微信编辑器会剥掉 / 不支持什么」的需求清单推导，
    # 按 标签 / CSS 能力 / at-rule 三类组织生成，不与任何外部实现共享文本。
    _stripped_tags = {"style": "<style> 标签（样式必须内联）", "script": "<script> 标签"}
    _css_capabilities = {
        r"position\s*:\s*(?:absolute|fixed|sticky)": "position fixed/absolute/sticky",
        r"display\s*:\s*(?:inline-)?grid": "display:grid",
        r"\bvar\s*\(\s*--": "CSS 变量 var(--x)",
    }
    _at_rules = ("media", "keyframes", "import")
    forbidden = (
        [(re.compile(rf"<\s*{tag}\b", re.I), msg) for tag, msg in _stripped_tags.items()]
        + [(re.compile(rx, re.I), msg) for rx, msg in _css_capabilities.items()]
        + [(re.compile(rf"@{word}\b", re.I), f"@{word}") for word in _at_rules]
    )
    errors = []
    for rx, msg in forbidden:
        n = len(rx.findall(body))
        if n:
            errors.append(f"{msg}（命中 {n} 处）")

    # P2-2：四周虚线框 border:…dashed（方向性 border-bottom-dashed 不算），非居中块 → WARN
    warnings = []
    foursided = re.compile(r"border\s*:(?:(?![;{}\"']).)*?dashed", re.I | re.S)
    for m in foursided.finditer(body):
        window = body[max(0, m.start() - 160):m.end() + 40]
        if 'center' not in window.lower():  # 居中占位块（text-align:center）豁免
            warnings.append("四周虚线框 border:…dashed 用于非居中块（正文强调请用左竖条；仅居中素材占位块可 dashed）")
            break

    return {
        'verdict': 'fail' if errors else 'ok',
        'errors': errors,
        'warnings': warnings,
        'hits': len(errors),
    }


# ===== 【第 15 节】H2 副标题对齐门 =====
# ============================================================================
# verify_h2_subtitle_align（2026-05-22 旁观者复核新增）
# 此前「H2 数量 == part_subtitles 数量」断言只在 format_layout 排版阶段 exit 3，
# 位置太晚。本函数让写完正文（pipeline.py verify writing）时即可拦下不对齐。
# ============================================================================

def verify_h2_subtitle_align(article_dir: str) -> dict:
    """
    校验 定稿.md 的 ## H2 数量 == article-meta.yaml 的 part_subtitles 数量。

    :param article_dir: 文章工作目录
    :return: {
        'verdict': 'ok'|'fail'|'skip', 'h2_count': int,
        'subtitle_count': int, 'notes': str,
    }
    """
    import re
    from pathlib import Path

    base = Path(article_dir)
    md = base / '定稿.md'
    meta = base / 'article-meta.yaml'
    if not md.exists():
        return {'verdict': 'skip', 'h2_count': 0, 'subtitle_count': 0,
                'notes': '定稿.md 不存在，跳过'}
    if not meta.exists():
        return {'verdict': 'skip', 'h2_count': 0, 'subtitle_count': 0,
                'notes': 'article-meta.yaml 不存在，跳过'}

    text = md.read_text(encoding='utf-8')
    body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.DOTALL)
    body = re.sub(r'```[\s\S]*?```', '', body)
    # `## ` 后是空格 → H2；`### ` 第三字符是 # 不会被 `^## ` 匹配
    h2_count = len(re.findall(r'^##\s', body, re.MULTILINE))

    try:
        import yaml
        m = yaml.safe_load(meta.read_text(encoding='utf-8')) or {}
        subs = m.get('part_subtitles') or []
        subtitle_count = len(subs) if isinstance(subs, list) else 0
    except Exception as e:
        return {'verdict': 'skip', 'h2_count': h2_count, 'subtitle_count': 0,
                'notes': f'article-meta.yaml 解析失败：{e}'}

    if h2_count == subtitle_count:
        return {
            'verdict': 'ok', 'h2_count': h2_count, 'subtitle_count': subtitle_count,
            'notes': f'H2 数量 == part_subtitles 数量（均 {h2_count}）',
        }
    return {
        'verdict': 'fail', 'h2_count': h2_count, 'subtitle_count': subtitle_count,
        'notes': (
            f'定稿.md 有 {h2_count} 个 ## H2，但 article-meta.yaml part_subtitles '
            f'有 {subtitle_count} 个 —— 不对齐。写完正文立即修，别等排版阶段才发现'
        ),
    }


# ===== 【第 16 节】量化体检报告 =====
# ============================================================================
# log_observation（2026-05-22 skill 自省机制）
# 每次 skill 运行时，把 verify 门的判定结果追加到 _skill-observations.jsonl。
# 只记事实不下判断 —— 判断留给 references/skill-review.md 流程里的旁观者。
# 设计原则：观察高频/便宜/确定性；修改低频/攒批/人工审（详见 skill-review.md）。
# ============================================================================

# ============================================================================
# 量化体检报告：audit_quant_signals（2026-06-10 P1-6 落地）
# anti-ai-filter.md §1-§3 的数值阈值（句长方差/段落节奏/副词密度/单句段/感叹号）
# 从写作上下文物理移除后，唯一的栖身处。**永不阻塞**（verdict 恒 'info'）：
# 数字是磨稿后的体检单，不是写作期 KPI——为数字改句子而伤语流，正是 6/7 诊断
# 确认的 Goodhart 病根。任何按本报告做的修改，以读出声终审为准、伤语流即回退。
# ============================================================================

_ADVERB_HINTS = [
    '非常', '十分', '极其', '特别', '格外', '显著', '迅速', '快速', '逐渐', '日益',
    '不断', '持续', '深刻', '充分', '全面', '积极', '大大', '极大', '显然', '确实',
    '的确', '相当', '颇为', '愈发', '越来越', '潜移默化', '从根本上', '全方位',
]


def audit_quant_signals(article_path: str) -> dict:
    """量化体检（原 anti-ai-filter §1.1/1.3/2.2/3.2 数值的机器化）。只报告，不裁决。

    :return: {'verdict': 'info'|'no_article', 'metrics': {...}, 'notes': [...]}
    """
    import re
    import statistics
    from pathlib import Path

    p = Path(article_path)
    if not p.exists():
        return {'verdict': 'no_article', 'metrics': {}, 'notes': [f'{article_path} 不存在']}

    text = _strip_for_scan(p.read_text(encoding='utf-8'))
    body_lines = [ln for ln in text.split('\n') if not ln.lstrip().startswith('#')]
    body = '\n'.join(body_lines)

    # 段落：空行分隔，去掉 markdown 装饰字符后量长度
    paras = []
    for blk in re.split(r'\n\s*\n', body):
        s = re.sub(r'[*`>\s]', '', blk)
        if s:
            paras.append(s)

    # 句子：按句终符切，量纯文字长度
    plain = re.sub(r'[*`>\n\s]', '', body)
    sents = [s for s in re.split(r'[。！？!?；;]', plain) if len(s) >= 2]
    lens = [len(s) for s in sents]

    metrics, notes = {}, []
    if len(lens) >= 5:
        metrics['sent_count'] = len(lens)
        metrics['sent_len_std'] = round(statistics.pstdev(lens), 1)
        metrics['sent_len_min'] = min(lens)
        metrics['sent_len_max'] = max(lens)
        run = best_run = 1
        for a, b in zip(lens, lens[1:]):
            run = run + 1 if abs(a - b) <= 5 else 1
            best_run = max(best_run, run)
        metrics['max_similar_len_run'] = best_run
        if metrics['sent_len_std'] < 12:
            notes.append(f"句长标准差 {metrics['sent_len_std']}（人类典型 ≥15，偏均匀）——读出声若不觉单调可不动")
        if best_run >= 4:
            notes.append(f"连续 {best_run} 句长度相近（±5 字）——节奏可能催眠，读出声判断")

    metrics['para_count'] = len(paras)
    if len(paras) >= 3:
        plens = [len(x) for x in paras]
        adj = sum(1 for a, b in zip(plens, plens[1:]) if abs(a - b) <= 20)
        metrics['adjacent_similar_paras'] = adj
        metrics['paras_over_150'] = sum(1 for x in plens if x > 150)
        metrics['one_liner_paras'] = sum(1 for x in plens if x <= 15)
        if adj >= len(plens) // 2:
            notes.append(f'相邻段落长度接近的有 {adj} 对——段落节奏偏匀速，按内容判断要不要拆/并')

    n_chars = max(len(plain), 1)
    adv_hits = sum(plain.count(w) for w in _ADVERB_HINTS)
    metrics['adverb_per_100'] = round(adv_hits * 100 / n_chars, 2)
    if metrics['adverb_per_100'] > 1.5:
        notes.append(f"程度副词密度 {metrics['adverb_per_100']}/100字 偏高——优先换具体描述（'非常快'→'三个月翻一番'）")

    excl = body.count('！') + body.count('!')
    metrics['exclamations'] = excl
    if excl > 3:
        notes.append(f'感叹号 {excl} 个（>3）——考虑收一收')

    if not notes:
        notes.append('量化体检无异常项（体检单仅供参考，语流第一）')
    return {'verdict': 'info', 'metrics': metrics, 'notes': notes}


# ===== 【第 17 节】skill 自省日志 log_observation =====
def log_observation(stage: str, event: str, verdict: str,
                    detail: str = "", article: str = "") -> None:
    """追加一条运行观察到 `_skill-observations.jsonl`（仅本地文件，**不联网**）。

    这份日志给「复核 skill」用：攒够若干篇之后，可以让它读这份日志，
    看看哪些质量门在反复报警，从而知道该改哪条规则。

    :param stage: 阶段（如 format_layout / verify_writing）
    :param event: 事件 = 门名（如 verify_bold_density / verify_cjk_punctuation）
    :param verdict: 该门这次的判定（ok / fail / warning / blocked / suspicious ...）
    :param detail: 简短事实描述（≤200 字），不含主观判断
    :param article: 文章名（空则取当前工作目录名）

    隐私默认值：
      - **文章名默认写入哈希**，不写明文标题。想看明文就设 `SANSHENG_WRITE_LOG_TITLES=1`。
      - 整个日志可以关掉：设 `SANSHENG_WRITE_TELEMETRY=off`。
      - 这个文件已在 `.gitignore` 里，不会被误提交。

    失败静默 -- 记 log 出任何错都绝不能影响主流程（自省是附加价值，不是关键路径）。
    """
    import json
    import datetime
    import hashlib
    import os
    from pathlib import Path

    if (os.environ.get('SANSHENG_WRITE_TELEMETRY', '').strip().lower()
            in {'off', '0', 'false', 'no'}):
        return

    try:
        # 观察日志归飞轮目录（profile 配置时在 <profile>/flywheel/，未配置回退仓根）
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from profile_config import observations_file
        log_path = observations_file()
        raw_article = article or Path.cwd().name
        article = raw_article
        if os.environ.get('SANSHENG_WRITE_LOG_TITLES', '').strip() not in {'1', 'true', 'yes'}:
            article = 'a-' + hashlib.sha256(article.encode('utf-8')).hexdigest()[:10]
        detail_text = (detail or '')
        if article != raw_article and raw_article and raw_article in detail_text:
            # 匿名态下 detail 里若被调用方带进了明文文章名，同样替换成哈希（复核 F6）
            detail_text = detail_text.replace(raw_article, article)
        rec = {
            'ts': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'),
            'article': article,
            'stage': stage,
            'event': event,
            'verdict': verdict,
            'detail': detail_text[:200],
        }
        with log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass  # 记 log 失败绝不影响主流程
