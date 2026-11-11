#!/usr/bin/env python3
"""$PORT 多路复用器：普通 HTTP 请求回 ok（平台健康检查），
WebSocket Upgrade 中继到本机 xray（127.0.0.1:10086）。
只用 Python 标准库。日志打到 /tmp/mux.log。"""
import os
import socket
import threading
import sys

PORT = int(os.environ.get("PORT", "8080"))
XRAY_ADDR = ("127.0.0.1", 10086)
LOG_PATH = "/tmp/mux.log"
MAX_HEADER = 8192
READ_TIMEOUT = 5


def log(msg):
    line = "[mux] %s\n" % msg
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)
    sys.stderr.flush()


def relay(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(conn, addr):
    conn.settimeout(READ_TIMEOUT)
    try:
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
            if len(buf) > MAX_HEADER:
                log("%s header too large, close" % (addr,))
                return
        head = buf.split(b"\r\n\r\n", 1)[0]
        lines = head.decode("iso-8859-1", "replace").split("\r\n")
        request_line = lines[0] if lines else ""
        parts = request_line.split(" ", 2)
        method = parts[0].upper() if parts else ""
        path = parts[1] if len(parts) > 1 else ""
        headers = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        upgrade = headers.get("upgrade", "").lower()
        if "websocket" in upgrade:
            log("%s websocket upgrade -> xray %s" % (addr, path))
            try:
                upstream = socket.create_connection(XRAY_ADDR, timeout=10)
            except OSError as e:
                log("%s xray connect failed: %s" % (addr, e))
                return
            upstream.sendall(buf)
            t1 = threading.Thread(target=relay, args=(conn, upstream), daemon=True)
            t2 = threading.Thread(target=relay, args=(upstream, conn), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            return
        # 健康检查：origin-form 的 GET/HEAD，路径以 / 开头
        if method in ("GET", "HEAD") and path.startswith("/"):
            resp = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    b"Content-Length: 2\r\nConnection: close\r\n\r\n")
            if method == "GET":
                resp += b"ok"
            conn.sendall(resp)
            log("%s health check %s %s -> 200 ok" % (addr, method, path))
            return
        log("%s unhandled request %r, close" % (addr, request_line))
    except (OSError, ValueError) as e:
        log("%s error: %s" % (addr, e))
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(128)
    log("listening on 0.0.0.0:%d, xray at %s:%d" % (PORT, XRAY_ADDR[0], XRAY_ADDR[1]))
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
