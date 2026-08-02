#!/usr/bin/env python3
"""独立视觉复核适配器 · Codex CLI 后端。

`pipeline.py visual-qa` 会按固定契约调用本脚本：

    python visual_qa_codex.py --request <_visual-qa-request.json> --output <candidate.json>

本脚本把 request 里的每张图**逐张**交给一个独立的 codex 进程看图打分，再把逐图结论
汇总成 `_visual-qa.json` 的候选字节。

设计红线（改动前先读）：

1. **只转述，不裁决。** 复核模型说 false 就写 false，脚本绝不把 checks 改成 true、
   也绝不把模型没看见的文字塞进 observed_text。视觉闸的全部价值在于它会真的拦下东西；
   一旦这里做任何"兜底修正"，它就退化成盖章机。
2. **复核模型必须独立于生图模型。** `visual_qa.py::validate_qa_result` 会拿 reviewer.model
   和 request 里所有 generation.model 求交集，撞上就判不合格。默认 `gpt-5.6-codex`。
3. **失败要留证。** 无论通过与否都落一份 `_visual-qa.raw.json`；候选 JSON 在校验不过时
   会被上游删掉，raw 是事后查"到底哪张图哪一项没过"的唯一线索。

环境变量：

- `SANSHENG_WRITE_VISUAL_QA_MODEL`   复核模型，默认 `gpt-5.6-terra`
- `SANSHENG_WRITE_VISUAL_QA_JOBS`    并发看图进程数，默认 3（上游总超时 900s）
- `SANSHENG_WRITE_VISUAL_QA_CODEX`   codex 可执行文件，默认 `codex`
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

# 走 ChatGPT 账号的 codex 只放行部分模型 —— `gpt-5.6-codex` 会被服务端 400 拒掉
# （"not supported when using Codex with a ChatGPT account"），别照抄历史文章里记的那个名字。
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_JOBS = 3
PER_ASSET_TIMEOUT = 600

# ⚠️ 这些定义直接决定闸门松紧，改之前想清楚：
# 判太松 = 闸门形同虚设；判太严 = 每次都误杀，真出问题时反而没人信它。
# 两条口径必须和下游 visual_qa.py::validate_qa_result 保持一致，否则会出现
# 「复核说不过、校验器说过」的分裂，人只能靠猜。
CHECK_DEFINITIONS = {
    "text_match": (
        "required_text 里的每一条都真实出现在图上；若没有 required_text，才检查 expected_text。"
        "比对时**忽略空格、换行、全半角差异**（中日文与拉丁字母之间多一个空格属于正常排版，"
        "下游校验器同样按去空格后比对）；允许一句话拆到两行、允许分散在画面不同位置。"
        "只看「字是不是那些字」，不看排版细节。"
    ),
    "crop_safe": (
        "所有文字与核心主体都完整在画面内，没有被边缘切掉；纯装饰性的连接箭头、背景舞台幕布可自然延伸至边缘。"
        "**右下角的品牌署名不在本项范围内** —— 它由脚本按固定 2% 内边距叠加，"
        "位置是既定设计，不算裁切风险，不要因为它靠近边角就判 false。"
        "本项只看画面里**生成出来的**内容有没有被切到。"
    ),
    "semantic_hierarchy": (
        "视觉层级分明，读者一眼知道先看哪里。"
        "注意按图片用途判断：banner / hero 这类图天然只有「主体 + 一行说明」两层，"
        "两层清晰即算通过，不要因为它没有三级标题结构就判 false。"
    ),
    "style_consistent": "整张图内部风格自洽（线条、材质、光照、色温统一），不像多张图拼起来的。",
    "no_unexpected_text": (
        "画面上的文字必须是 expected_text 的子集。expected_text 是完整白名单，required_text 才是"
        "必须出现的子集：里面出现的产品名、公司名、账号署名都是作者刻意允许的，不算意外文字。"
        "这一项要抓的是：乱码、错别字、缺笔画或多笔画的字、"
        "会造成歧义的同一句重复渲染；同一允许标签在叙事路径的两个节点复现不算意外文字、"
        "只渲染了半个字、以及白名单之外凭空多出来的任何词、编号或字母。"
        "与主题直接相关的、没有语义标签的比赛记分牌数字不算意外文字。"
        "另外，画面里不得**画出**任何真实公司的图形 logo（图标本身，不是文字名称）。"
        "唯一例外是后处理脚本加在右下角、并与白名单中的本站署名相邻的品牌标记；"
        "它是发布规范要求的署名组成部分，不是陌生公司 logo。"
    ),
    "style_contract_match": (
        "required_visual_traits 全部出现，forbidden_visual_traits 一条都没出现。"
        "注意 forbidden 只约束 expected_text 之外的内容 —— 白名单里的文字不构成违禁，"
        "例如 forbidden 写了「不得出现署名」而 expected_text 里恰好有署名时，以 expected_text 为准。"
        "后处理脚本加在右下角的本站官方品牌水印不属于画面叙事内容，不参与黏土材质、"
        "立体字或场景嵌入要求；不得仅因该水印是平面品牌字而判 false。"
    ),
    "brand_palette_match": (
        "**设计元素**的配色落在给定色板内（背景色 / 主色 / 中性色）——"
        "标签条、箭头、边框、高亮块、图标、容器、数据元素都算设计元素。"
        "这些地方一旦出现色板之外的色相（橙、砖红、芥末黄、蓝、紫、霓虹），判 false，"
        "并在 notes 里点名是哪个色、用在了什么元素上。"
        "**例外**：黏土人物的肤色、木头/纸张等自然材质的柔和土色是配方明确允许的，"
        "不要因为人偶是肉色、台阶是木色就判 false —— 要盯的是「有没有第二个色相被拿来做设计」。"
        "还要检查明暗关系：画面大部分必须是高明度暖象牙白/浅中性色，玉绿色只能做浅粉彩点缀；"
        "大标题、长箭头、连续路径或大面板一旦使用深绿、森林绿或近黑色，哪怕色相仍是绿色也判 false。"
        "最深色只允许用于很小的接触阴影、轮廓和微型细节。"
    ),
    "typography_contract_match": (
        "正文图的全部白名单文字必须是立体、圆润、厚实、略带手工不规则感的黏土字，"
        "并与周围物体共用同一哑光黏土材质、真实嵌入场景。若是平面印刷黑体、商务无衬线体、"
        "手写马克笔、毛笔、书法、粉笔字，或大多数文字都有底板/方框/条幅/卡片包住，判 false。"
        "唯一豁免是后处理脚本加在右下角的本站官方品牌水印：它应按品牌原字标显示，"
        "不要求转成黏土字，也不得因此判 false。"
    ),
    "composition_contract_match": (
        "构图符合 style_contract.layout 描述的版面分区。比例是设计目标而非像素测量题："
        "当左侧文字区约占 44%-52%、左右内容不碰撞、主标题仍是第一视觉焦点且中间保有可辨认的安静过渡时，"
        "不得只因未机械等于 50/6/44 而判 false；若文字区小于约 44%、证据区明显压过标题或两区粘连，再判 false。"
    ),
}

RESPONSE_SCHEMA_NOTE = (
    "只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释性前后文。"
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _loose(text: str) -> str:
    """去空格小写，用于宽松比对 trait 文案。"""
    return "".join(str(text).split()).lower()


def _resolve_codex(name: str) -> str:
    """把 `codex` 解析成真正能被 CreateProcess 拉起来的路径。

    Windows 上 npm 装出来的是 `codex.cmd`（还有一个无扩展名的 sh 脚本给 Git Bash 用）。
    subprocess 不走 shell 时无法执行无扩展名的 sh 脚本，直接传 "codex" 会
    `FileNotFoundError: [WinError 2]`。shutil.which 会按 PATHEXT 找到 .cmd。
    """
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return name
    return shutil.which(name) or name


def _build_schema(required_checks: list[str]) -> dict[str, Any]:
    """按本资产实际要求的 checks 动态生成 JSON Schema（codex --output-schema 用）。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "observed_text",
            "observed_layout",
            "visual_evidence",
            "checks",
            "notes",
        ],
        "properties": {
            "observed_text": {
                "type": "array",
                "items": {"type": "string"},
                "description": "图上你实际读到的每一段文字，逐条列出，原样转写。看不清就不要写。",
            },
            "observed_layout": {
                "type": "string",
                "description": "一句话描述实际版面：分了几个区、各区放了什么、主体在哪。",
            },
            "visual_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["trait", "observed", "location"],
                    "properties": {
                        "trait": {"type": "string"},
                        "observed": {"type": "string"},
                        "location": {"type": "string"},
                    },
                },
                "minItems": 1,
                "description": "对 required_visual_traits 逐条给出你实际看到了什么、在画面什么位置。至少一条，不许空数组。",
            },
            "checks": {
                "type": "object",
                "additionalProperties": False,
                "required": list(required_checks),
                "properties": {
                    name: {"type": "boolean"} for name in required_checks
                },
            },
            "notes": {
                "type": "string",
                "description": "任何异常、可疑之处，或判 false 的具体理由。没有就写「无」。",
            },
        },
    }


def _build_prompt(asset: dict[str, Any]) -> str:
    contract = asset.get("style_contract") or {}
    palette = contract.get("palette") or {}
    required_checks = asset.get("required_checks") or []
    metrics = asset.get("pixel_metrics") or {}

    lines = [
        "你是一名独立的视觉验收员。附件里是一张待验收的图，请逐项如实核对。",
        "",
        "⚠️ 你的职责是**挑毛病**，不是放行。任何一项你不能亲眼确认，就判 false 并在 notes 里说明。",
        "宁可误杀，不可放过 —— 放行一张有杂字或裁切的图，代价远大于让作者重出一次。",
        "",
        f"## 图片用途：{asset.get('stage')}",
        f"## 目标风格：{asset.get('target_style')}",
        f"## 实际像素：{metrics.get('width')}×{metrics.get('height')}",
        "",
        "## 文字白名单（expected_text）",
        "这是允许出现在图上的全部文字，是严格上限；白名单之外不得出现任何可读字符。"
        "白名单内的产品名、公司名或账号署名不是违规。",
        "右下角由后处理添加的官方品牌 Logo 作为一个完整图形标识验收：其中固定的"
        "中文名、Sansheng 字样与 AI 缩写均已在白名单内；不要因其极小字号无法逐字 OCR "
        "而判 no_unexpected_text=false。此例外只限右下角官方 Logo，本图其他位置的"
        "微小、模糊或未知文字仍必须判为违规。",
    ]
    expected = asset.get("expected_text") or []
    if expected:
        lines += [f"{i}. {t}" for i, t in enumerate(expected, 1)]
    else:
        lines.append("（空 —— 这张图不应出现任何文字）")
    required = asset.get("required_text") or []
    lines += [
        "",
        "## 必须文字（required_text）",
        "下列每条必须逐字正确，并且在整张图中恰好出现一次：",
    ]
    lines += [f"{i}. {t}" for i, t in enumerate(required, 1)] or ["（空）"]

    lines += [
        "",
        "## 风格契约",
        f"- 版面：{contract.get('layout') or '（未指定）'}",
        f"- 背景色：{palette.get('background') or '—'}　主色：{palette.get('accent') or '—'}"
        f"　中性色：{'、'.join(palette.get('neutrals') or []) or '—'}",
        "- 必须出现的视觉特征：",
    ]
    lines += [f"  - {t}" for t in contract.get("required_visual_traits") or ["（无）"]]
    lines += ["- 禁止出现的视觉特征："]
    lines += [f"  - {t}" for t in contract.get("forbidden_visual_traits") or ["（无）"]]

    lines += ["", "## 逐项判定标准"]
    for name in required_checks:
        lines.append(f"- `{name}`：{CHECK_DEFINITIONS.get(name, '按字面含义判定。')}")

    lines += [
        "",
        "## 🔴 转写纪律（最容易出错的地方，先读这段）",
        "生图模型渲染中文时经常把字画坏 —— 缺笔画、多笔画、张冠李戴、拼成根本不存在的字。",
        "而看图模型的天性是**把看不清的字自动补成上下文里合理的词**。这两件事一叠加，",
        "你就会「读到」一句通顺的话，而图上其实是一串废字。这是本次复核唯一不可接受的失误。",
        "",
        "所以转写时：",
        "1. **逐字辨认**，不要整句猜。先确认每一个字的字形，再组词。",
        "2. **不许补全**。字形不是标准简体字、或你不能确定是哪个字，就在该位置写 `□`，",
        "   并在 notes 里指出「第 N 句第 M 字疑似坏字」。宁可标 □，也不要写出一个通顺的句子。",
        "3. 只要出现哪怕一个 `□` 或一个你能认出的错别字，`text_match` 和 `no_unexpected_text`",
        "   **都必须判 false**。",
        "4. 先转写、再回头对白名单。**顺序反了就会被白名单带着走**。",
        "5. **每个出现位置都要单独转写**。同一句出现两次，就在 observed_text 里写两次，",
        "   不能合并、去重或只记一次。",
        "6. **按「块」转写，不要打碎**：视觉上属于同一块的文字（同一个标签条、同一个气泡、",
        "   同一张卡片）合并成**一条**，块内按从上到下、从左到右拼接。一句话折成两行、",
        "   或「名字在上、说明在下」的两行标签，都算同一块，必须拼成一条。",
        "   ❌ 错误示范：把两张卡片转写成 `['Codex', 'Claude', '主动补发 20 次', '事故赔偿 6 次']`",
        "   —— 这是把每张卡的第一行先写完、再写第二行，块被拆散且顺序错乱。",
        "   ✅ 正确：`['Codex 主动补发 20 次', 'Claude 事故赔偿 6 次']`。",
        "   拆碎或错序会让下游误判成「这句话根本不在图上」，白白让一张好图被打回。",
        "",
        "## 输出",
        "- `observed_text`：**原样转写**你在图上读到的所有文字，按上面的纪律来。",
        "  不要照抄 expected_text，要写你眼睛实际看到的。两者对不上正是我们要发现的问题。",
        "- `visual_evidence`：必须逐条覆盖 required_visual_traits；每项的 trait 字段原样复制合同文本，",
        "  再说出你看到的具体对象、数量、位置。不得改写、合并或遗漏；只回布尔值视为无效。",
        "- `checks`：逐项 true/false。",
        "",
        RESPONSE_SCHEMA_NOTE,
    ]
    return "\n".join(lines)


def _review_one(
    asset: dict[str, Any],
    *,
    article_dir: Path,
    codex_bin: str,
    model: str,
) -> dict[str, Any]:
    rel = str(asset["path"])
    image_path = (article_dir / rel).resolve()
    if not image_path.is_file():
        return {"path": rel, "_error": f"图片不存在：{image_path}"}

    required_checks = list(asset.get("required_checks") or [])
    workdir = Path(tempfile.mkdtemp(prefix="visual-qa-"))
    try:
        schema_path = workdir / "schema.json"
        schema_path.write_text(
            json.dumps(_build_schema(required_checks), ensure_ascii=False),
            encoding="utf-8",
        )
        answer_path = workdir / "answer.json"
        cmd = [
            codex_bin,
            "exec",
            "--model", model,
            "--image", str(image_path),
            "--sandbox", "read-only",
            "--ephemeral",
            "--skip-git-repo-check",
            "--color", "never",
            "--output-schema", str(schema_path),
            "--output-last-message", str(answer_path),
            # 刻意不把 prompt 放进 argv：Windows 上 npm 装的 codex 入口是 codex.cmd，
            # 批处理 shim 转发 %* 时会把**多行参数**吃掉，模型只收到图片、收不到要求，
            # 结果是它自说自话地"通过"（实测症状：notes 写"未提供目标文案或风格合同"，
            # 但 checks 照样给 true）。这种失败不报错、只是悄悄把闸门架空，最危险。
            # 走 stdin 则完全绕开 shell 解析：codex exec 在 PROMPT 缺省时从 stdin 读指令。
        ]
        completed = subprocess.run(
            cmd,
            cwd=str(workdir),
            input=_build_prompt(asset),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PER_ASSET_TIMEOUT,
            check=False,
        )
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-600:]
            return {"path": rel, "_error": f"codex exit={completed.returncode}：{tail}"}
        if not answer_path.is_file():
            return {"path": rel, "_error": "codex 没有写出结论文件"}
        raw = answer_path.read_text(encoding="utf-8").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"path": rel, "_error": f"结论不是合法 JSON：{exc}；原文前 300 字：{raw[:300]}"}
        if not isinstance(payload, dict):
            return {"path": rel, "_error": "结论 JSON 顶层必须是对象"}

        checks = payload.get("checks")
        if not isinstance(checks, dict) or any(
            not isinstance(checks.get(name), bool) for name in required_checks
        ):
            return {"path": rel, "_error": f"checks 不完整，需要 {required_checks}"}
        evidence = payload.get("visual_evidence")
        if not isinstance(evidence, list) or not evidence:
            return {"path": rel, "_error": "缺 visual_evidence（只回布尔值不放行）"}

        # 「提示词没送到」的结构化探针。
        # 复核模型如果压根没收到风格契约，仍然可能凭 schema 编出一份格式合法、
        # checks 全 true 的结论 —— 闸门就这么被静默架空了。required_visual_traits 是
        # 只有读过提示词才可能复述的内容，用它当信道自检：一条都对不上就判进程失败，
        # 而不是当成"复核未通过"（后者会让人去改图，改到天亮也没用）。
        required_traits = (asset.get("style_contract") or {}).get(
            "required_visual_traits"
        ) or []
        if required_traits:
            echoed = {_loose(str(item.get("trait", ""))) for item in evidence}
            echoed.discard("")
            missing_traits = [
                trait for trait in required_traits if _loose(trait) not in echoed
            ]
            if missing_traits:
                return {
                    "path": rel,
                    "_error": (
                        "复核结论没有逐条原样复述 required_visual_traits："
                        f"{missing_traits}；判定提示词未完整送达或复核未按合同执行"
                    ),
                }

        return {
            "path": rel,
            # sha256 取自磁盘实际字节，不取 request 里的声明值 —— 这样图在
            # 生成 request 之后被改过，上游比对会立刻发现。
            "sha256": _sha256_file(image_path),
            "observed_text": [
                str(t) for t in (payload.get("observed_text") or []) if str(t).strip()
            ],
            "observed_layout": str(payload.get("observed_layout") or ""),
            "visual_evidence": evidence,
            "checks": {name: bool(checks[name]) for name in required_checks},
            "notes": str(payload.get("notes") or ""),
        }
    except subprocess.TimeoutExpired:
        return {"path": rel, "_error": f"codex 超时（>{PER_ASSET_TIMEOUT}s）"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _normalized(text: str) -> str:
    return "".join(str(text).split()).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex 后端的独立视觉复核适配器")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    article_dir = request_path.parent
    assets = request.get("assets") or []
    if not assets:
        print("request 里没有资产", file=sys.stderr)
        return 2

    model = os.getenv("SANSHENG_WRITE_VISUAL_QA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    codex_bin = _resolve_codex(
        os.getenv("SANSHENG_WRITE_VISUAL_QA_CODEX", "codex").strip() or "codex"
    )
    if not Path(codex_bin).is_file():
        print(f"找不到 codex 可执行文件：{codex_bin}", file=sys.stderr)
        return 2
    try:
        jobs = max(1, int(os.getenv("SANSHENG_WRITE_VISUAL_QA_JOBS", str(DEFAULT_JOBS))))
    except ValueError:
        jobs = DEFAULT_JOBS

    generation_models = {
        str((a.get("generation") or {}).get("model") or "").strip() for a in assets
    }
    if model in generation_models:
        print(f"复核模型 {model} 与生图模型重合，视觉闸失效", file=sys.stderr)
        return 2

    print(f"▶ 独立视觉复核：{len(assets)} 张图 / 模型 {model} / 并发 {jobs}", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(
            pool.map(
                lambda a: _review_one(
                    a, article_dir=article_dir, codex_bin=codex_bin, model=model
                ),
                assets,
            )
        )

    qa = {
        "schema_version": 1,
        "status": "pass",
        "request_sha256": _sha256_file(request_path),
        "reviewer": {
            "role": "independent-visual-reviewer",
            "model": model,
            "run_id": str(uuid.uuid4()),
            "independent": True,
        },
        "assets": [r for r in results if "_error" not in r],
    }

    # 逐图汇报 + 判定整体状态。任何一项不过就如实写 fail，绝不修正模型结论。
    failures: list[str] = []
    by_path = {str(a["path"]): a for a in assets}
    for result in results:
        rel = result["path"]
        if "_error" in result:
            failures.append(f"{rel}：{result['_error']}")
            print(f"  ✗ {rel}  {result['_error']}", file=sys.stderr)
            continue
        required_checks = set(by_path[rel].get("required_checks") or [])
        bad = [
            name for name, ok in result["checks"].items()
            if name in required_checks and not ok
        ]
        observed = [_normalized(t) for t in result["observed_text"]]
        joined = "".join(observed)
        allowed = {
            _normalized(t)
            for t in by_path[rel].get("expected_text") or []
            if _normalized(t)
        }
        unexpected = [
            value
            for value in observed
            if value and not any(value == item or value in item for item in allowed)
        ]
        missing = [
            t
            for t in by_path[rel].get("required_text") or []
            if _normalized(t) not in observed and _normalized(t) not in joined
        ]
        # 复核员按转写纪律，认不出的字要写成 □。它出现就说明图上有坏字，
        # 无论复核员把 checks 判成了什么 —— 这不是替它裁决，是执行它自己给出的信号。
        garbled = [t for t in result["observed_text"] if "□" in t]

        # 同一句渲染两遍：确定性可判，**不要指望模型自觉**。
        # 实测复核员如实转写出了 ['57 条档案', '53 条官方出处', '57 条档案', '53 条官方出处']
        # —— 重复就摆在它自己的输出里，它照样把 no_unexpected_text 判成 true。
        # 凡是能用代码判死的规则就别留给模型：它的职责是「看见」，判定交给这里。
        seen_once: dict[str, int] = {}
        for value in result["observed_text"]:
            key = _normalized(value)
            if key:
                seen_once[key] = seen_once.get(key, 0) + 1
        repeated = sorted(k for k, n in seen_once.items() if n > 1)
        required_not_once = [
            value
            for value in by_path[rel].get("required_text") or []
            if joined.count(_normalized(value)) != 1
        ]
        if bad:
            failures.append(f"{rel} 未通过：{'、'.join(bad)} —— {result['notes']}")
        if garbled:
            failures.append(f"{rel} 转写里有无法辨认的字（坏字）：{garbled}")
        if repeated:
            failures.append(f"{rel} 同一句被渲染多遍（EXACTLY ONCE 违例）：{repeated}")
        if required_not_once:
            failures.append(f"{rel} 必须文字未恰好出现一次：{required_not_once}")
        if unexpected:
            failures.append(f"{rel} 出现白名单外文字：{unexpected}")
        if "text_match" in required_checks and missing:
            failures.append(f"{rel} 缺文字：{missing}")
        ok = not (
            bad
            or (missing if "text_match" in required_checks else [])
            or garbled
            or repeated
            or required_not_once
            or unexpected
        )
        print(
            f"  {'✓' if ok else '✗'} {rel}"
            + (f"  未过：{'、'.join(bad)}" if bad else "")
            + (f"  重复：{repeated}" if repeated else "")
            + (f"  缺字：{missing}" if missing else ""),
            file=sys.stderr,
        )

    if failures:
        qa["status"] = "fail"
        qa["failures"] = failures

    # raw 永远落盘：候选 JSON 校验不过会被上游删除，raw 是事后排查的唯一线索。
    (article_dir / "_visual-qa.raw.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.output).write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if failures:
        print("\n未通过明细：", file=sys.stderr)
        for item in failures:
            print(f"  • {item}", file=sys.stderr)
        # 仍返回 0：把不合格结论交给 visual_qa.py 的校验器裁决，
        # 由它统一报错，避免"进程失败"和"复核不通过"两种语义混在一起。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
