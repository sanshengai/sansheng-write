# gen_img.py -- 直调 Google 图像模型端点生图（本 skill 的唯一生图入口）
#
# 为什么自己直调而不经第三方插件：插件层的 env / 版本 / base_url 拼法互相覆盖，
# 排查成本远高于直接打一次 REST。这里按 key 前缀自动分流端点，零额外配置：
#   AIza... → AI Studio       generativelanguage.googleapis.com
#   AQ....  → Vertex Express  aiplatform.googleapis.com（需 GOOGLE_VERTEX_PROJECT）
#
# 用法:
#   python gen_img.py <prompt_file.md> <out_png> <model> <W> <H>
# 精确尺寸:
#   2.35:1 封面 -> 1024 436 | 9:16 -> 576 1024 | 16:9 -> 1024 576 | 1:1 -> 1024 1024
#
# 缺 GOOGLE_API_KEY 时会明确报错指路，不静默降级。
# 出图后照常: add_logo.js -> compress_images.py -> pipeline.py log
import sys, os, json, base64, io, subprocess
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_config as pc

AI_STUDIO = ("https://generativelanguage.googleapis.com/v1beta/"
             "models/{model}:generateContent")
VERTEX_EXPRESS = ("https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
                  "publishers/google/models/{model}:generateContent")


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


def gen(prompt_file, out_path, model, w, h):
    prompt = open(prompt_file, encoding="utf-8").read()
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"imageSize": "1K", "aspectRatio": _aspect_ratio(w, h)}},
    }
    key = _key()
    r = subprocess.run(
        ["curl", "-s", "--max-time", "300", _endpoint(model, key),
         "-H", "Content-Type: application/json",
         "-H", f"x-goog-api-key: {key}",
         "-d", "@-"],
        input=json.dumps(body), capture_output=True, text=True, encoding="utf-8",
    )
    if not r.stdout.strip():
        raise SystemExit(f"empty response (curl stderr: {pc.redact(r.stderr[:300])})")
    resp = json.loads(r.stdout)
    if "error" in resp:
        raise SystemExit(f"API error: {pc.redact(json.dumps(resp['error'])[:400])}")
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
        raise SystemExit(f"no image in response: {json.dumps(resp)[:300]}")
    img = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
    img = img.resize((w, h), Image.LANCZOS)  # 缩到精确目标尺寸（aspect 容差 ±2px）
    img.save(out_path)
    print(f"OK {out_path} {w}x{h}")

if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit("usage: python gen_img.py <prompt_file.md> <out_png> <model> <W> <H>")
    gen(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
