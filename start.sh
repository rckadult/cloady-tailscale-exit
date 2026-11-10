#!/bin/bash
# Cloady 备用出口：Tailscale（userspace 模式，PaaS 容器无 /dev/net/tun）
# + tinyproxy（只绑 127.0.0.1，经 tailscale serve 暴露到内网）
# 另起一个极简 HTTP 服务应付平台的 $PORT 健康检查。
set -u

PORT="${PORT:-8080}"
TS_SOCKET=/run/tailscale/tailscaled.sock

# 1. 平台健康检查用的占位 HTTP 服务（只返回 ok，不暴露任何文件）
mkdir -p /tmp/www /var/lib/tailscale /run/tailscale
echo ok > /tmp/www/index.html
cd /tmp/www
python3 -m http.server "$PORT" --bind 0.0.0.0 >/tmp/http.log 2>&1 &
echo "[start] status server on :$PORT"

# 2. tinyproxy：转发代理，只监听本机 8888
tinyproxy -c /etc/tinyproxy/tinyproxy.conf
echo "[start] tinyproxy on 127.0.0.1:8888"

# 3. tailscaled：userspace 模式，状态放内存（每次启动用 auth key 重新入网）
tailscaled --tun=userspace-networking --state=mem: --socket="$TS_SOCKET" >/tmp/tailscaled.log 2>&1 &
echo "[start] tailscaled (userspace mode)"

# 等 socket 就绪
for i in $(seq 1 30); do
  [ -S "$TS_SOCKET" ] && break
  sleep 1
done

TS="tailscale --socket=$TS_SOCKET"

if [ -n "${TS_AUTHKEY:-}" ]; then
  if $TS up --authkey="$TS_AUTHKEY" --hostname=cloady-exit \
      --accept-dns=false --advertise-exit-node; then
    echo "[ok] tailscale up, node: $($TS ip -4)"
    # 把本机代理暴露到内网 8888 端口（TCP 直通，无 TLS）
    $TS serve --bg tcp:8888 tcp://127.0.0.1:8888 \
      && echo "[ok] tailscale serve tcp:8888 -> tinyproxy"
  else
    echo "[warn] tailscale up failed, check TS_AUTHKEY"
  fi
else
  echo "[warn] TS_AUTHKEY not set, tailscale not joined (set env var and redeploy)"
fi

# 保持容器存活；平台重启容器即恢复
while true; do sleep 3600; done
