"""经 SSH 隧道（SOCKS5）访问微信 API：本机出口不在公众号 IP 白名单时，让请求从白名单里的服务器出去。

配置（任一来源，前者优先）：
- 环境变量 ``SANSHENG_WRITE_WECHAT_TUNNEL=user@host[:port]``，可选 ``SANSHENG_WRITE_WECHAT_TUNNEL_KEY=<私钥路径>``；
- 配置文件 ``~/.config/sansheng-write/wechat-tunnel.json``：``{"host": "...", "user": "root", "port": 22, "key": "~/.ssh/id_ed25519"}``。
都没有配置时不走隧道，直连。``SANSHENG_WRITE_WECHAT_TUNNEL=off`` 强制直连。只用标准库：ssh 子进程 + 一个最小的 SOCKS5 客户端。
"""
from __future__ import annotations

import contextlib
import http.client
import json
import os
import socket
import ssl
import struct
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Iterator

CONFIG_FILE = Path.home() / ".config/sansheng-write/wechat-tunnel.json"


def tunnel_config() -> dict | None:
    spec = os.environ.get("SANSHENG_WRITE_WECHAT_TUNNEL", "").strip()
    if spec:
        user, _, rest = spec.rpartition("@")
        host, _, port = rest.partition(":")
        return {"host": host, "user": user or "root", "port": int(port or 22), "key": os.environ.get("SANSHENG_WRITE_WECHAT_TUNNEL_KEY", "").strip()}
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not raw.get("host"):
        return None
    return {"host": str(raw["host"]), "user": str(raw.get("user") or "root"), "port": int(raw.get("port") or 22), "key": str(raw.get("key") or "")}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def ssh_tunnel(cfg: dict, *, wait: float = 20.0) -> Iterator[int]:
    port = _free_port()
    cmd = ["ssh", "-N", "-D", f"127.0.0.1:{port}", "-o", "ExitOnForwardFailure=yes", "-o", "BatchMode=yes",
           "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=15", "-p", str(cfg["port"])]
    if cfg.get("key"):
        cmd += ["-i", os.path.expanduser(cfg["key"])]
    cmd.append(f'{cfg["user"]}@{cfg["host"]}')
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        end = time.time() + wait
        while time.time() < end:
            if proc.poll() is not None:
                raise RuntimeError("SSH 隧道没有建起来：" + (proc.stderr.read().decode("utf-8", "replace")[-200:] if proc.stderr else ""))
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("SSH 隧道等待超时")
        yield port
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


def socks5_connect(proxy_port: int, host: str, port: int, timeout: float = 60) -> socket.socket:
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    try:
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00":
            raise OSError("SOCKS5 握手被拒")
        h = host.encode("idna")
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + struct.pack(">H", port))
        head = s.recv(4)
        if len(head) < 4 or head[1] != 0:
            raise OSError(f"SOCKS5 连接失败（{head[1] if len(head) > 1 else '?'}）")
        skip = {1: 4, 4: 16}.get(head[3])
        if skip is None:
            skip = s.recv(1)[0]
        s.recv(skip + 2)
        return s
    except Exception:
        s.close()
        raise


def make_opener(proxy_port: int) -> urllib.request.OpenerDirector:
    class _Http(http.client.HTTPConnection):
        def connect(self):
            self.sock = socks5_connect(proxy_port, self.host, self.port, self.timeout or 60)

    class _Https(http.client.HTTPSConnection):
        def connect(self):
            raw = socks5_connect(proxy_port, self.host, self.port, self.timeout or 60)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)

    class HttpH(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(_Http, req)

    class HttpsH(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(_Https, req)

    return urllib.request.build_opener(HttpH, HttpsH, urllib.request.ProxyHandler({}))
