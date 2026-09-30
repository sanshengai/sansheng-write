"""SOCKS5 隧道客户端：本地假 SOCKS5 代理 + 假服务，验证请求真的经代理出去，代理失败时是明确错误。"""
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
