# Cloady 上的 Tailscale 备用出口
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release \
    tinyproxy python3 procps \
 && rm -rf /var/lib/apt/lists/*

# Tailscale 官方安装脚本（走 apt 源，始终装当前稳定版）
RUN curl -fsSL https://tailscale.com/install.sh | sh

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

CMD ["/usr/local/bin/start.sh"]
