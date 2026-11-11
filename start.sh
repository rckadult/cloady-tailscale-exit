#!/bin/bash
# Cloady 备用出口：Tailscale（userspace 模式，PaaS 容器无 /dev/net/tun）
# + tinyproxy（只绑 127.0.0.1，经 tailscale serve 暴露到内网）
# + xray VLESS+WS（手机 v2rayNG 经公网域名连入；mux.py 在 $PORT 上分流，
#   普通 GET/HEAD 回 ok 应付平台健康检查，WebSocket Upgrade 转给 xray）。
set -u

PORT="${PORT:-8080}"
TS_SOCKET=/run/tailscale/tailscaled.sock

mkdir -p /var/lib/tailscale /run/tailscale /etc/xray

# 1. xray：UUID 只从环境变量 XRAY_UUID 读；未设置则跳过 xray。
if [ -n "${XRAY_UUID:-}" ]; then
  cat > /etc/xray/config.json <<EOF
{"log":{"loglevel":"warning"},"inbounds":[{"port":10086,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":"$XRAY_UUID"}],"decryption":"none"},"streamSettings":{"network":"ws","wsSettings":{"path":"/vless"}}}],"outbounds":[{"protocol":"freedom","tag":"direct"},{"protocol":"socks","tag":"tailscale","settings":{"servers":[{"address":"127.0.0.1","port":1055}]}}],"routing":{"domainStrategy":"IPIfNonMatch","rules":[{"type":"field","ip":["100.64.0.0/10"],"outboundTag":"tailscale"}]}}
EOF
  xray -config /etc/xray/config.json >/tmp/xray.log 2>&1 &
  echo "[start] xray VLESS+WS on 127.0.0.1:10086 (path /vless)"
else
  echo "[warn] XRAY_UUID not set, xray skipped (VLESS proxy unavailable)"
fi

# 2. mux.py：接管 $PORT——普通请求回 ok，WS 升级转 xray
python3 /usr/local/bin/mux.py >/tmp/mux.log 2>&1 &
echo "[start] mux on :$PORT (health ok / ws -> xray)"

# 3. tinyproxy：转发代理，只监听本机 8888
tinyproxy -c /etc/tinyproxy/tinyproxy.conf
echo "[start] tinyproxy on 127.0.0.1:8888"

# 4. tailscaled：userspace 模式，状态放内存（每次启动用 auth key 重新入网）
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
