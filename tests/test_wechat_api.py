"""内置微信 API：用本地假服务验证真实 HTTP 代码——上传失败必须是硬错误、errcode 要报清楚、token 过期重取一次。"""
import io
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import wechat_api as W  # noqa: E402


class State:
    def __init__(self):
        self.calls, self.fail, self.token_no = [], {}, 0


@pytest.fixture
def server(monkeypatch, tmp_path):
    st = State()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            st.calls.append(("GET", self.path)); st.token_no += 1
            self._send({"access_token": f"T{st.token_no}", "expires_in": 7200})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
            st.calls.append(("POST", self.path, len(body)))
            step = self.path.split("?")[0].rsplit("/", 1)[-1]
            if step in st.fail:
                code = st.fail[step]
                if isinstance(code, list):
                    code = code.pop(0) if code else None
                if code:
                    return self._send({"errcode": code, "errmsg": "boom"})
            if step == "uploadimg":
                return self._send({"url": f"http://mmbiz.qpic.cn/x/{len(st.calls)}"})
            if step == "add_material":
                return self._send({"media_id": "COVER1", "url": "http://x"})
            if step == "add":
                st.last_article = json.loads(body)["articles"][0]
                return self._send({"media_id": "DRAFT1"})
            self._send({})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(W, "API_BASE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("SANSHENG_WRITE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    yield st
    srv.shutdown()


def png(path: Path, size=(40, 30)):
    Image.new("RGB", size, (200, 30, 30)).save(path)


def make_article(tmp_path, n=2):
    d = tmp_path / "art"
    (d / "素材").mkdir(parents=True)
    png(d / "素材/cover.png", (900, 383))
    imgs = ""
    for i in range(n):
        png(d / f"素材/i{i}.png")
        imgs += f'<p><img src="素材/i{i}.png" data-local-path="素材/i{i}.png" style="width:100%"></p>'
    return d, f"<section><p>正文</p>{imgs}<img src=\"https://mmbiz.qpic.cn/keep.png\"></section>"


def publish(d, html, **kw):
    return W.publish_draft(html=html, base_dir=d, cover=d / "素材/cover.png", title="标题", digest="摘要", app_id="wx1", secret="s", **kw)


def test_full_flow_replaces_every_local_image_and_returns_structured_ids(server, tmp_path):
    d, html = make_article(tmp_path)
    out = publish(d, html, author="叁笙", source_url="https://example.com")
    assert out["media_id"] == "DRAFT1" and out["cover_media_id"] == "COVER1" and len(out["images"]) == 2
    content = server.last_article["content"]
    assert "素材/i0.png" not in content and "data-local-path" not in content and "mmbiz.qpic.cn/keep.png" in content
    assert content.count("https://mmbiz.qpic.cn") == 3
    assert server.last_article["author"] == "叁笙" and server.last_article["content_source_url"] == "https://example.com"
    assert server.last_article["thumb_media_id"] == "COVER1"


def test_image_upload_failure_is_a_hard_error_not_a_silent_local_path(server, tmp_path):
    """反例：旧实现吞掉上传失败，草稿里留着本地路径。这里必须抛错。"""
    d, html = make_article(tmp_path)
    server.fail["uploadimg"] = 40005
    with pytest.raises(W.WechatError, match="40005") as e:
        publish(d, html)
    assert e.value.errcode == 40005 and "jpg" in str(e.value)
    assert "add" not in [c[1].split("?")[0].rsplit("/", 1)[-1] for c in server.calls if c[0] == "POST"]  # 没走到建草稿


def test_missing_local_image_and_external_image_are_rejected(server, tmp_path):
    d, html = make_article(tmp_path, 1)
    with pytest.raises(W.WechatError, match="不存在"):
        publish(d, html + '<img src="素材/none.png">')
    with pytest.raises(W.WechatError, match="外链"):
        publish(d, html + '<img src="https://example.com/a.png">')


def test_ip_whitelist_error_has_a_useful_hint(server, tmp_path):
    d, html = make_article(tmp_path)
    server.fail["draft/add"] = 40164
    server.fail["add"] = 40164
    with pytest.raises(W.WechatError, match="IP 白名单"):
        publish(d, html)


def test_expired_token_is_refetched_once_then_succeeds(server, tmp_path):
    d, html = make_article(tmp_path, 1)
    server.fail["uploadimg"] = [42001]
    out = publish(d, html)
    assert out["media_id"] == "DRAFT1" and server.token_no == 2


def test_token_is_cached_between_calls(server, tmp_path):
    d, html = make_article(tmp_path, 1)
    publish(d, html); publish(d, html)
    assert server.token_no == 1


def test_large_or_webp_body_images_are_compressed_under_one_megabyte(server, tmp_path):
    d, html = make_article(tmp_path, 0)
    import random
    random.seed(1)
    big = Image.frombytes("RGB", (1600, 1200), bytes(random.randrange(256) for _ in range(1600 * 1200 * 3)))
    big.save(d / "素材/big.png")
    assert (d / "素材/big.png").stat().st_size > W.BODY_IMAGE_MAX_BYTES
    Image.new("RGB", (50, 40), (1, 2, 3)).save(d / "素材/a.webp", "WEBP")
    out = publish(d, html + '<img src="素材/big.png"><img src="素材/a.webp">')
    assert len(out["images"]) == 2 and any("压缩" in i["note"] for i in out["images"])
