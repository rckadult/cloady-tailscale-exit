# Cloady Tailscale 备用出口

给 Muse 的备用上网出口：一台 Cloady 免费层小主机，装 Tailscale 进内网，
再跑一个转发代理。主出口（hatch-egress-proxy）出问题时走这条路。

## 架构

```
Muse VM --(tunnel proxy :3130)--> tailnet: cloady-exit:8888 --(tinyproxy)--> 互联网
```

- 主机：Cloady 工作区 Workspace（USW1），免费层，应用名 `tailscale-exit`
- 容器：Debian + Tailscale（userspace 模式，PaaS 没有 /dev/net/tun）
  + tinyproxy（只绑 127.0.0.1:8888）+ 占位 HTTP 服务（应付平台 $PORT 健康检查）
- `tailscale serve tcp:8888` 把代理暴露到内网；代理本身不对外网开放
- 另带 `--advertise-exit-node`：用户的手机/电脑也能把它当 exit node 用
  （Muse 这侧内置客户端用不了 exit node，Muse 只走代理这条路）

## 为什么不是纯 exit node

Muse 的内置 Tailscale 客户端是 client-only，不支持使用 exit node，
也不允许装上游客户端。所以出口必须做成"内网里的一个转发代理"，
Muse 经 tunnel proxy 连过去再出公网。

## 部署

1. 把本目录推到 GitHub（或按 Cloady 控制台支持的方式部署 Dockerfile）
2. Cloady 建应用，环境变量：
   - `TS_AUTHKEY`：Tailscale auth key（管理后台 Settings → Keys 生成，
     Reusable、非 ephemeral；不要进聊天记录，直接填控制台环境变量）
   - `PORT`：平台自动注入
3. 部署后核验：`tailscale status` 里出现 `cloady-exit`，且经 tunnel proxy
   能 `curl --proxy <tunnel> http://cloady-exit:8888/` 通

## Muse 侧用法（待容器就绪后配）

本机起一个链路代理（127.0.0.1:18080），把请求经 tunnel proxy 转给
内网 tinyproxy；主出口失败时把 `HTTPS_PROXY` 指过去即可。
实测一条公网抓取通过才算数。

## 花费

免费层内：0.5 vCPU / 1 GB RAM / 5 GB SSD / 200 GB 流量每月（整个工作区共用）。
本容器常驻约 50–100 MB 内存；流量只在备用出口启用时产生。
注意悬崖计费：任一项超限整个工作区变计费，超了就停。
