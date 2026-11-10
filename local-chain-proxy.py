#!/usr/bin/env python3
"""Local chaining proxy: lets Muse use the Cloady tailnet proxy as backup egress.

Chain: local tool --(http://127.0.0.1:18080)--> this script
       --(CONNECT via tunnel proxy hatch-egress-proxy:3130)--> tailnet tinyproxy
       --(forward proxy)--> public internet.

The script never parses HTTP itself: after the tunnel CONNECT succeeds it
relays bytes verbatim in both directions, so curl's absolute-URI requests
and CONNECT tunnels both pass through untouched.

Usage:
  TARGET_HOST=cloady-exit TARGET_PORT=8888 python3 local-chain-proxy.py [port]
  # then: HTTPS_PROXY=http://127.0.0.1:18080 curl https://example.com/

Env:
  TARGET_HOST   tailnet name/IP of the proxy host (default: cloady-exit)
  TARGET_PORT   proxy port on that host (default: 8888)
  TUNNEL_PROXY  host:port of the runtime tunnel proxy (default: derived from
                HTTPS_PROXY by swapping its port to 3130)
"""
import base64
import os
import socket
import sys
import threading
from urllib.parse import urlparse

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
TARGET_HOST = os.environ.get("TARGET_HOST", "cloady-exit")
TARGET_PORT = int(os.environ.get("TARGET_PORT", "8888"))


def _auth_header(u):
    if u.username:
        raw = f"{u.username}:{u.password or ''}".encode()
        return "Proxy-Authorization: Basic " + base64.b64encode(raw).decode()
    return None


def tunnel_proxy():
    """Return (host, port, auth_header) for the runtime tunnel proxy.

    The proxy URL carries userinfo (user:pass@host:port); urlparse handles
    that, while a naive split on ':' would mistake the user for the host.
    """
    tp = os.environ.get("TUNNEL_PROXY")
    if tp:
        u = urlparse(tp if "://" in tp else "//" + tp)
        return u.hostname, u.port or 3130, _auth_header(u)
    u = urlparse(os.environ.get("HTTPS_PROXY", ""))
    return u.hostname, 3130, _auth_header(u)


def relay(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            b.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client):
    try:
        tp_host, tp_port, tp_auth = tunnel_proxy()
        tun = socket.create_connection((tp_host, tp_port), timeout=30)
        # CONNECT through the tunnel proxy to the tailnet proxy
        lines = [
            f"CONNECT {TARGET_HOST}:{TARGET_PORT} HTTP/1.1",
            f"Host: {TARGET_HOST}:{TARGET_PORT}",
        ]
        if tp_auth:
            lines.append(tp_auth)
        tun.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        tun.settimeout(15)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = tun.recv(4096)
            if not chunk:
                raise OSError("tunnel proxy closed the connection")
            resp += chunk
        tun.settimeout(None)
        if b" 200 " not in resp.split(b"\r\n", 1)[0]:
            raise OSError(f"tunnel CONNECT failed: {resp.splitlines()[0]!r}")
        t1 = threading.Thread(target=relay, args=(client, tun), daemon=True)
        t2 = threading.Thread(target=relay, args=(tun, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print(f"[chain] {e}", file=sys.stderr)
    finally:
        try:
            client.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", LISTEN_PORT))
    srv.listen(50)
    print(
        f"[chain] listening on 127.0.0.1:{LISTEN_PORT} "
        f"-> {TARGET_HOST}:{TARGET_PORT} via tunnel proxy",
        flush=True,
    )
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
