# Cloady 上的 Tailscale 备用出口
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release unzip \
    tinyproxy python3 procps \
 && rm -rf /var/lib/apt/lists/*

# Tailscale 官方安装脚本（走 apt 源，始终装当前稳定版）
RUN curl -fsSL https://tailscale.com/install.sh | sh

# xray：VLESS+WS 代理，供手机 v2rayNG 经公网连入
# 平台边缘只把明文 HTTP 转给容器 $PORT，mux.py 在 $PORT 上分流：
# 普通 GET/HEAD 回 ok（健康检查），WebSocket Upgrade 转给 xray。
RUN curl -fsSL -o /tmp/xray.zip \
      https://github.com/XTLS/Xray-core/releases/download/v26.11.9/Xray-linux-64.zip \
 && unzip -o /tmp/xray.zip xray -d /usr/local/bin \
 && chmod +x /usr/local/bin/xray \
 && rm -f /tmp/xray.zip \
 && xray version

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY start.sh /usr/local/bin/start.sh
COPY mux.py /usr/local/bin/mux.py
RUN chmod +x /usr/local/bin/start.sh

CMD ["/usr/local/bin/start.sh"]
