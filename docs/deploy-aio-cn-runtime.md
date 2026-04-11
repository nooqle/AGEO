# 内地 AIO Runtime 部署说明

## 当前边界

AIO 内地服务器不运行 AGEO 应用代码。它运行官方 Sandbox 镜像：

- 镜像：`ghcr.io/agent-infra/sandbox:latest`
- 容器：`aio-sandbox`
- 服务端口：`8080`
- 持久化目录：`/opt/specta-aio-home:/home/gem`

AGEO 后端通过 `AIO_BASE_URL=http://10.206.16.17:8080` 调用它。

## 推荐运行参数

使用 `ops/aio/docker-compose.cn.yml` 启动，核心要求：

- 不限制 CPU 和内存，让容器使用整台 4C/16G 机器资源。
- 设置 `shm_size: "2gb"`，避免 Chrome 在默认 64MB `/dev/shm` 下退化。
- 保留 `security_opt: ["seccomp=unconfined"]`，这是当前 AIO 镜像启动 Chromium 的必要参数。
- 保留 `/opt/specta-aio-home:/home/gem`，否则登录态、浏览器 profile 和采集数据会丢失。

## 更新流程

在 AIO 主机上执行：

```bash
cd /opt/specta-aio
docker compose pull
docker compose up -d
docker ps --filter name=aio-sandbox
curl -fsS http://127.0.0.1:8080/v1/browser/info
```

如果当前容器使用了持久化浏览器 profile，重建前必须先停止旧容器，再删除旧 profile 的 Chromium 单例锁：

```bash
docker stop aio-sandbox
docker rename aio-sandbox aio-sandbox-before-$(date +%Y%m%d%H%M%S)
find /opt/specta-aio-home/.config/browser -maxdepth 1 \
  \( -name 'Singleton*' -o -name 'DevToolsActivePort' \) \
  -print -delete
```

这些锁文件只表示上一个 Chromium 进程占用 profile，不是登录态数据。旧容器停止后删除它们是安全的；不删除会导致新容器因为 profile 被旧容器 hostname 锁定而无法启动浏览器。

如果只是检查镜像是否更新：

```bash
before=$(docker image inspect ghcr.io/agent-infra/sandbox:latest --format '{{.Id}}')
docker pull ghcr.io/agent-infra/sandbox:latest
after=$(docker image inspect ghcr.io/agent-infra/sandbox:latest --format '{{.Id}}')
test "$before" = "$after" && echo "image_changed=no" || echo "image_changed=yes"
```

## 回滚

不要删除 `/opt/specta-aio-home`。

如新容器异常，先保留旧容器或旧镜像，再恢复：

```bash
docker compose down
docker run -d \
  --name aio-sandbox \
  --restart unless-stopped \
  -p 8080:8080 \
  --shm-size=2g \
  --security-opt seccomp=unconfined \
  -v /opt/specta-aio-home:/home/gem \
  ghcr.io/agent-infra/sandbox:latest
```
