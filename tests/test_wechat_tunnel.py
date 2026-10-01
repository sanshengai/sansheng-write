"""SOCKS5 隧道客户端：本地假 SOCKS5 代理 + 假服务，验证请求真的经代理出去，代理失败时是明确错误。"""
import contextlib
import socket
import socketserver
import struct
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import wechat_tunnel as T  # noqa: E402


class Web(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"via-" + self.headers.get("Host", "").encode())


def _socks_server(seen, target_port, refuse=False):
    class H(socketserver.BaseRequestHandler):
        def handle(self):
            s = self.request
            assert s.recv(3) == b"\x05\x01\x00"; s.sendall(b"\x05\x00")
            head = s.recv(4); n = s.recv(1)[0]; host = s.recv(n).decode(); port = struct.unpack(">H", s.recv(2))[0]
            seen.append((host, port))
            if refuse:
                s.sendall(b"\x05\x05\x00\x01" + b"\0" * 6); return
            up = socket.create_connection(("127.0.0.1", target_port)); s.sendall(b"\x05\x00\x00\x01" + b"\0" * 6)
            def pipe(a, b):
                try:
                    while (d := a.recv(4096)): b.sendall(d)
                except OSError: pass
                finally:
                    with __import__("contextlib").suppress(OSError): b.shutdown(socket.SHUT_WR)
            threading.Thread(target=pipe, args=(up, s), daemon=True).start(); pipe(s, up)
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_request_goes_through_socks_with_domain_name():
    web = HTTPServer(("127.0.0.1", 0), Web); threading.Thread(target=web.serve_forever, daemon=True).start()
    seen = []; proxy = _socks_server(seen, web.server_port)
    opener = T.make_opener(proxy.server_address[1])
    body = opener.open("http://api.weixin.qq.com:%d/x" % web.server_port, timeout=5).read()
    assert body.startswith(b"via-api.weixin.qq.com")          # 域名交给代理解析（不是本机解析）
    assert seen == [("api.weixin.qq.com", web.server_port)]


def test_refused_by_proxy_is_an_error_not_a_direct_connection():
    web = HTTPServer(("127.0.0.1", 0), Web); threading.Thread(target=web.serve_forever, daemon=True).start()
    proxy = _socks_server([], web.server_port, refuse=True)
    with pytest.raises(Exception):
        T.make_opener(proxy.server_address[1]).open("http://127.0.0.1:%d/x" % web.server_port, timeout=5)


def test_config_from_env_and_legacy_file(monkeypatch, tmp_path):
    monkeypatch.delenv("SANSHENG_WRITE_WECHAT_TUNNEL", raising=False)
    monkeypatch.setenv("SANSHENG_WRITE_WECHAT_TUNNEL", "deploy@10.0.0.9:2222")
    assert T.tunnel_config() == {"host": "10.0.0.9", "user": "deploy", "port": 2222, "key": ""}
    monkeypatch.delenv("SANSHENG_WRITE_WECHAT_TUNNEL")
    f = tmp_path / "t.json"; f.write_text('{"host": "1.2.3.4", "user": "root", "port": 22, "key": "~/.ssh/k"}', encoding="utf-8")
    monkeypatch.setattr(T, "CONFIG_FILE", f)
    assert T.tunnel_config() == {"host": "1.2.3.4", "user": "root", "port": 22, "key": "~/.ssh/k"}
    monkeypatch.setattr(T, "CONFIG_FILE", tmp_path / "nope.json")
    assert T.tunnel_config() is None


# ---------- 直连优先，被白名单拒了才走隧道 ----------
import wechat_api as W  # noqa: E402


class _FakeTunnel:
    opened = 0


def _fake_world(monkeypatch, direct_ok):
    """直连时（_OPENER 为空）按 direct_ok 决定成败；隧道里（_OPENER 非空）一律成功。"""
    calls = {"direct": 0, "tunnel": 0}

    def fake_token(app_id, secret, force=False):
        if W._OPENER is None:
            calls["direct"] += 1
            if not direct_ok:
                raise W.WechatError("微信接口 token 失败：errcode=40164", errcode=40164, step="token")
        else:
            calls["tunnel"] += 1
        return "T"

    monkeypatch.setattr(W, "access_token", fake_token)
    monkeypatch.setattr(W, "upload_html_images", lambda html, base, tok: (html, []))
    monkeypatch.setattr(W, "upload_cover", lambda cover, tok: {"media_id": "C"})
    monkeypatch.setattr(W, "add_draft", lambda tok, article: "D")
    monkeypatch.setattr(T, "tunnel_config", lambda: {"host": "h", "user": "u", "port": 22, "key": ""})

    @contextlib.contextmanager
    def fake_ssh(cfg, wait=20.0):
        _FakeTunnel.opened += 1
        yield 12345
    monkeypatch.setattr(T, "ssh_tunnel", fake_ssh)
    monkeypatch.setattr(T, "make_opener", lambda port: object())
    return calls


def _pub():
    return W.publish_draft(html="<p>x</p>", base_dir=Path("."), cover=Path("c.png"), title="t", digest="d", app_id="a", secret="s")


def test_direct_first_no_tunnel_when_local_ip_is_whitelisted(monkeypatch):
    monkeypatch.delenv("SANSHENG_WRITE_WECHAT_TUNNEL", raising=False)
    before = _FakeTunnel.opened
    calls = _fake_world(monkeypatch, direct_ok=True)
    assert _pub()["media_id"] == "D" and calls["tunnel"] == 0 and _FakeTunnel.opened == before


def test_falls_back_to_tunnel_only_on_whitelist_error(monkeypatch):
    monkeypatch.delenv("SANSHENG_WRITE_WECHAT_TUNNEL", raising=False)
    calls = _fake_world(monkeypatch, direct_ok=False)
    assert _pub()["media_id"] == "D" and calls["direct"] == 1 and calls["tunnel"] >= 1
    # 反例：关掉隧道时，白名单错误必须原样报出，不能悄悄换出口
    monkeypatch.setenv("SANSHENG_WRITE_WECHAT_TUNNEL", "off")
    _fake_world(monkeypatch, direct_ok=False)
    with pytest.raises(W.WechatError) as e:
        _pub()
    assert e.value.errcode == 40164
