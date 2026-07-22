# gen_img.py -- 统一生图入口：Google 直调（默认）+ OpenAI 兼容端点兜底
#
# 为什么自己直调而不经第三方插件：插件层的 env / 版本 / base_url 拼法互相覆盖，
# 排查成本远高于直接打一次 REST。Google 路径按 key 前缀自动分流端点，零额外配置：
#   AIza... → AI Studio       generativelanguage.googleapis.com
#   AQ....  → Vertex Express  aiplatform.googleapis.com（需 GOOGLE_VERTEX_PROJECT）
#
# 用法:
#   python gen_img.py <prompt_file.md> <out_png> <model> <W> <H>
# Google 不可用时的 OpenAI 兼容兜底（.env 配 OPENAI_API_KEY，可选 OPENAI_BASE_URL）:
#   python gen_img.py --provider openai -m <模型名> <prompt_file.md> <out_png> <W> <H>
# 干跑（只打印将发的请求摘要，不真正调 API、不含 key）:
#   python gen_img.py --dry-run ...
# 精确尺寸:
#   2.35:1 封面 -> 1024 436 | 9:16 -> 576 1024 | 16:9 -> 1024 576 | 1:1 -> 1024 1024
#
# 缺 GOOGLE_API_KEY / OPENAI_API_KEY 时会明确报错指路，不静默降级。
#
# 模型 fallback 链（2026-07-21 实战固化，google 路径）：部分 Vertex 项目对
# `-preview` 后缀的模型 ID 无访问权（404），去掉 `-preview` 的裸 ID 才通。脚本按序自动尝试：
#   请求的 ID → 去 `-preview` 裸 ID → gemini-2.5-flash-image（兜底）
# 并在输出里打印实际使用的模型（fallback 到 2.5 且图含中文时务必核字）。
# 日志行刻意纯 ASCII：emoji 在 GBK 控制台会 UnicodeEncodeError。
# 出图后照常: add_logo.js -> compress_images.py -> pipeline.py log
import sys, os, json, base64, io
import urllib.request
import urllib.error
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_config as pc

AI_STUDIO = ("https://generativelanguage.googleapis.com/v1beta/"
             "models/{model}:generateContent")
VERTEX_EXPRESS = ("https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
                  "publishers/google/models/{model}:generateContent")

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _key():
    return pc.load_secret(
        "GOOGLE_API_KEY",
        hint="AI Studio 的 AIza... 或 Vertex Express 的 AQ... 都行，脚本按前缀自动分流端点。",
    )


def _endpoint(model: str, key: str) -> str:
    """按 key 前缀分流端点。陌生人拿自己的 AIza key 也能直接跑通。"""
    if key.startswith("AQ."):
        project = pc.load_secret(
            "GOOGLE_VERTEX_PROJECT",
            hint="AQ. 开头的 Vertex Express key 必须同时给 GCP 项目 ID（项目级端点）。",
        )
        return VERTEX_EXPRESS.format(project=project, model=model)
    return AI_STUDIO.format(model=model)

def _aspect_ratio(w, h):
    """把目标 W×H 映射到 Banana 支持的最近 aspectRatio 档。
    2026-06-25 补：原先只传 imageSize、模型默认出方图，第 60 行 resize((w,h)) 会把
    9:16/16:9 强行拉伸变形（潜在 bug）。现按目标比例传 aspectRatio，模型直接出对比例，
    再 resize 到精确 W×H 就只是缩放不拉伸。"""
    cand = {"1:1": 1.0, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3,
            "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3, "21:9": 21 / 9}
    r = w / h
    return min(cand.items(), key=lambda kv: abs(kv[1] - r))[0]


def _candidate_models(model):
    """模型 fallback 链：请求的 ID → 去 `-preview` 裸 ID → 2.5-flash 兜底（去重保序）。"""
    cands = [model]
    if model.endswith("-preview"):
        cands.append(model[: -len("-preview")])
    cands.append("gemini-2.5-flash-image")
    seen, out = set(), []
    for m in cands:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _post_json(url: str, headers: dict, body: dict, timeout: int = 300) -> str:
    """POST JSON（标准库直连，Google / OpenAI 两路共用）。

    为什么不再 subprocess 调 curl：以前 key 拼在 curl 的 argv（`-H "x-goog-api-key: ..."`），
    进程列表（ps / 任务管理器 / procmon）对同机其他用户进程可见——key 只该进请求头。
    urllib 直连后 key 不落 argv、不落磁盘。HTTP 4xx/5xx 仍返回响应体字符串
    （与原 `curl -s` 行为一致：Google/OpenAI 都用 JSON error 字段描述错误，交给上层统一报）。
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        if payload.strip():
            return payload
        return json.dumps({"error": {"code": e.code, "message": f"HTTP {e.code} (empty body)"}})
    except urllib.error.URLError as e:
        raise SystemExit(f"request failed: {pc.redact(str(getattr(e, 'reason', e))[:300])}")


def gen(prompt_file, out_path, model, w, h):
    prompt = open(prompt_file, encoding="utf-8").read()
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"imageSize": "1K", "aspectRatio": _aspect_ratio(w, h)}},
    }
    key = _key()
    # 404/not-found 才沿 fallback 链降级；非 404 错误（配额、鉴权、参数等）直接报错，不降级
    resp, used, last_err = None, None, None
    for cand in _candidate_models(model):
        text = _post_json(_endpoint(cand, key), {"x-goog-api-key": key}, body)
        if not text.strip():
            raise SystemExit("empty response from Google endpoint")
        resp = json.loads(text)
        if "error" not in resp:
            used = cand
            break
        last_err = json.dumps(resp["error"])
        if "404" in last_err or "not found" in last_err.lower():
            print(f"  [warn] model {cand} unavailable (404), trying next in fallback chain")
            continue
        raise SystemExit(f"API error: {pc.redact(last_err[:400])}")
    if not used:
        raise SystemExit(
            f"API error: fallback 链全部失败，最后错误: {pc.redact((last_err or '')[:400])}"
        )
    if used != model:
        print(f"  [info] requested {model} unavailable in this project, auto-fell-back to {used}")
    data = None
    for c in resp.get("candidates", []):
        for part in c.get("content", {}).get("parts", []):
            d = part.get("inlineData", {}).get("data")
            if d:
                data = d
                break
        if data:
            break
    if not data:
        # 先 redact 再截断：错误响应可能整段回显请求（含 key），截断后再打码会漏掉被切一半的 key
        raise SystemExit(f"no image in response: {pc.redact(json.dumps(resp))[:300]}")
    img = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
    img = img.resize((w, h), Image.LANCZOS)  # 缩到精确目标尺寸（aspect 容差 ±2px）
    img.save(out_path)
    print(f"OK {out_path} {w}x{h} (model={used})")


# ===== OpenAI 兼容端点兜底（Google 不可用时，image-routing.md §「可选：OpenAI 兼容端点兜底」）=====

# OpenAI Images API 每个模型只接受少数离散 size 档，这里按目标宽高比映射到最接近的一档：
#   方 1024x1024 / 横 1536x1024 / 竖 1024x1536（gpt-image-1 的三档）
#   2.35:1 封面(1024x436, r≈2.35) → 1536x1024 ｜ 16:9(1024x576) → 1536x1024
#   9:16(576x1024) → 1024x1536 ｜ 1:1 → 1024x1024
# "最接近"只须比例近似：与 Google 路径一样，出图后由 PIL 缩到精确 W×H（只缩放不拉伸容忍
# 少量裁切误差由 resize 吸收）。个别兼容端点若不认某档 size，会以 JSON error 报出，不静默。
_OPENAI_SIZES = {"1024x1024": 1.0, "1536x1024": 1536 / 1024, "1024x1536": 1024 / 1536}


def _openai_size(w, h):
    r = w / h
    return min(_OPENAI_SIZES.items(), key=lambda kv: abs(kv[1] - r))[0]


def _openai_key():
    return pc.load_secret(
        "OPENAI_API_KEY",
        hint="任何 OpenAI 兼容生图端点的 key。可选搭配 OPENAI_BASE_URL"
             f"（默认 {DEFAULT_OPENAI_BASE_URL}）与 OPENAI_IMAGE_MODEL（默认模型名）。",
    )


def _openai_base() -> str:
    """OPENAI_BASE_URL 未配置时默认打 api.openai.com（与 .env.example 注释一致）。"""
    return (pc.load_secret("OPENAI_BASE_URL", required=False) or DEFAULT_OPENAI_BASE_URL).rstrip("/")


def _openai_model(cli_model):
    """模型解析：CLI 的 -m/位置参数 > .env 的 OPENAI_IMAGE_MODEL > 明确报错（不猜默认模型）。"""
    m = cli_model or pc.load_secret("OPENAI_IMAGE_MODEL", required=False)
    if not m:
        raise SystemExit(
            "[openai] 缺模型名：传 -m <模型名>（如 --provider openai -m gpt-image-1），"
            "或在 .env 配 OPENAI_IMAGE_MODEL。"
        )
    return m


def _download(url: str, timeout: int = 300) -> bytes:
    """兼容 url 返回形态（response_format=url）：GET 拿图字节。签名 URL 含临时票据，不打印。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except urllib.error.URLError as e:
        raise SystemExit(f"image download failed: {pc.redact(str(getattr(e, 'reason', e))[:300])}")


def gen_openai(prompt_file, out_path, model, w, h):
    """OpenAI Images API 兼容路径：POST {OPENAI_BASE_URL}/images/generations。

    响应兼容两种返回形态：data[0].b64_json（gpt-image-1 默认）与 data[0].url（dall-e 系 /
    部分第三方兼容端点默认）。出图后与 Google 路径同一套：PIL 缩到精确 W×H → save → OK 行。
    """
    prompt = open(prompt_file, encoding="utf-8").read()
    model = _openai_model(model)
    key = _openai_key()
    url = f"{_openai_base()}/images/generations"
    text = _post_json(url, {"Authorization": f"Bearer {key}"},
                      {"model": model, "prompt": prompt, "size": _openai_size(w, h), "n": 1})
    if not text.strip():
        raise SystemExit("empty response from OpenAI-compatible endpoint")
    resp = json.loads(text)
    if resp.get("error"):
        raise SystemExit(f"API error: {pc.redact(json.dumps(resp['error'], ensure_ascii=False))[:400]}")
    items = resp.get("data") or []
    raw = None
    if items:
        if items[0].get("b64_json"):
            raw = base64.b64decode(items[0]["b64_json"])
        elif items[0].get("url"):
            raw = _download(items[0]["url"])
    if raw is None:
        # 同 Google 路径：先 redact 再截断，防错误回显里带 key
        raise SystemExit(f"no image in response: {pc.redact(json.dumps(resp))[:300]}")
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = img.resize((w, h), Image.LANCZOS)  # 缩到精确目标尺寸
    img.save(out_path)
    print(f"OK {out_path} {w}x{h}")


def dry_run(provider, prompt_file, model, w, h):
    """只打印将发的请求摘要（URL / 模型 / 尺寸），不发请求。key 照常校验存在性但绝不打印。"""
    prompt = open(prompt_file, encoding="utf-8").read()
    if provider == "openai":
        model = _openai_model(model)
        _openai_key()  # 缺 key 时与真跑同样报错指路
        print("DRY-RUN provider=openai")
        print(f"  POST {_openai_base()}/images/generations")
        print(f"  model={model} size={_openai_size(w, h)} (由目标 {w}x{h} 映射，出图后 PIL 缩回精确尺寸) n=1")
    else:
        key = _key()
        print("DRY-RUN provider=google")
        print(f"  POST {_endpoint(model, key)}")
        print(f"  model={model} aspectRatio={_aspect_ratio(w, h)} imageSize=1K target={w}x{h}")
    print(f"  prompt={prompt_file} ({len(prompt)} chars)  [未发送请求，key 不打印]")


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="gen_img.py",
        description="统一生图入口：google（默认，按 key 前缀分流端点）/ openai（OpenAI 兼容端点兜底）",
    )
    ap.add_argument("--provider", choices=("google", "openai"), default="google",
                    help="生图后端，默认 google；Google 不可用时 --provider openai 走 OpenAI 兼容端点")
    ap.add_argument("-m", "--model", dest="model_opt", default=None,
                    help="模型名（给了就覆盖位置参数里的 model；openai 未指定时回退 OPENAI_IMAGE_MODEL）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将发的请求摘要（URL/模型/尺寸，不含 key），不真正调 API")
    ap.add_argument("args", nargs="+", metavar="prompt_file out_png [model] W H",
                    help="model 可省略（用 -m 或 OPENAI_IMAGE_MODEL 代替）")
    ns = ap.parse_args(argv)
    pos = ns.args
    # `-m` 给全批次统一模型时，每组 4 项；否则 Google 每组 5 项（逐图模型）。
    # OpenAI 兼容旧的单组 4 项（模型由 env 解析）。多组按输入顺序串行，避免并发
    # 生图把上游打到 429 / RESOURCE_EXHAUSTED。
    if ns.model_opt:
        group_size = 4
    elif ns.provider == "openai" and len(pos) == 4:
        group_size = 4
    elif len(pos) % 5 == 0:
        group_size = 5
    elif ns.provider == "openai" and len(pos) % 4 == 0:
        group_size = 4
    else:
        ap.error(
            "位置参数应为一组或多组: <prompt_file.md> <out_png> [model] <W> <H>；"
            "传 -m 时每组省略 model"
        )
    if not pos or len(pos) % group_size != 0:
        ap.error(
            f"位置参数数量 {len(pos)} 不能按每组 {group_size} 项解析；"
            "检查 prompt/out/model/W/H 是否成组"
        )

    jobs = []
    for i in range(0, len(pos), group_size):
        group = pos[i:i + group_size]
        if group_size == 5:
            prompt_file, out_path, model, w, h = group
        else:
            prompt_file, out_path, w, h = group
            model = ns.model_opt
        try:
            w, h = int(w), int(h)
        except ValueError:
            ap.error(f"W/H 必须是整数像素，收到: {w} {h}")
        if ns.provider == "google" and not model:
            ap.error("google provider 必须给模型名（位置参数第 3 个，或 -m <模型名>）")
        jobs.append((prompt_file, out_path, model, w, h))

    for prompt_file, out_path, model, w, h in jobs:
        if ns.dry_run:
            dry_run(ns.provider, prompt_file, model, w, h)
        elif ns.provider == "openai":
            gen_openai(prompt_file, out_path, model, w, h)
        else:
            gen(prompt_file, out_path, model, w, h)


if __name__ == "__main__":
    _main()
