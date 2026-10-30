# 接入公共 MyCaddy 的生产部署

服务器公网入口由独立项目 **MyCaddy** 管理。MyCollab 的 `web` 服务仅监听容器
HTTP 80，负责前端、`/static/*` 和 `/api/*`、`/admin/*` 转发；不发布宿主机端口，
不管理公网证书。用户素材仍只能通过授权 API 下载，不能作为静态文件公开。

## 首次部署

服务器需要 Docker Engine、Compose 和完整项目 checkout，无需宿主机 Python 或 Node。
先按 MyCaddy README 创建外部网络 `caddy-public`，配置公网地址与持久化证书卷。

```sh
cd /opt/MyCollabAdvanced/deploy
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 32
```

将两次随机值分别填入 `DJANGO_SECRET_KEY`、`POSTGRES_PASSWORD`。
`DJANGO_ALLOWED_HOSTS` 填实际公网 IP 或域名（不带协议），
`DJANGO_CSRF_TRUSTED_ORIGINS` 填对应的 `https://` origin；
`CADDY_NETWORK` 与 MyCaddy 一致。公网地址只在 MyCaddy 的 `PUBLIC_HOST` 中设置。
不要提交真实 `.env`。中国自然日口径可设置 `DJANGO_TIME_ZONE=Asia/Shanghai`。

```sh
docker compose config --quiet
docker compose build
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d
docker compose ps
docker compose logs --tail=100 backend web
docker compose exec backend python manage.py createsuperuser
```

之后在 MyCaddy 项目启动公共入口。内部 Web 通过别名 `mycollab-web` 接入公共网络，
backend 与 db 只在 MyCollab 默认网络。共享网络仅连接可信容器；内部 Web 信任私有
代理地址，保留入口设置的 `X-Forwarded-Proto`，避免 HTTPS 登录和 CSRF 判断错误。

## 迁移已有部署

先阅读 MyCaddy README 的迁移与回滚步骤。保留项目名 `mycollab-prod`、数据库、
素材和静态卷；将原 Caddy 的证书卷交给公共入口继续使用。
旧服务 `caddy` 被内部 `web` 替代。先构建并启动 `backend web`，保留旧 Caddy 容器
直到切换时再停止；不要提前执行 `--remove-orphans`，也不要运行 `down -v`。
旧 `DOMAIN` 不再由业务 Compose 使用；地址转移到 MyCaddy，Django 两个地址变量仍需保留。
已有库不要仅修改 `.env` 的数据库密码，该变量不会改变现有数据库用户密码。

## 验收与更新

使用真实 HTTPS 地址，确认没有证书警告，登录和写入正常，刷新任务详情页仍显示 SPA，
`/api/*` 的 404 不返回前端 HTML，实际 `/static/*` 文件可读取。
浏览器 `window.isSecureContext` 应为 `true`，`crypto.subtle.digest` 可用。
公网证书签发、续期与入口故障查看 MyCaddy 日志；502 同时检查 `backend web` 日志。

文件互传仍无 STUN/TURN 或服务器文件中继；HTTPS 不保证跨网络 WebRTC 可达。
实际双机验收与自动化入口见 [TECH_STACK.md](../TECH_STACK.md#浏览器文件直传验收)。

更新前备份数据库、素材与 `.env`，后端启动会执行迁移。更新后：

```sh
docker compose build
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d
```

内部 Caddyfile 与前端打包在镜像中，修改后需重建；公共入口配置挂载与 reload
由 MyCaddy 管理。修改业务 `.env` 后使用 `up -d`，不能只 restart。
业务 `docker compose down` 不删除外部网络，不影响 Clash 或公共入口。
禁止用 `down -v` 做普通重启。

在服务器 crontab 保留临时传输清理（按实际目录调整）：

```cron
*/5 * * * * cd /opt/MyCollabAdvanced/deploy && /usr/bin/docker compose exec -T backend python manage.py cleanup_transfers
```

其他提醒与清理计划见 [部署与升级操作](../TECH_STACK.md#16-部署与升级操作)。
局域网内部 CA 如有需要也统一在 MyCaddy 配置 `tls internal`，并向客户端安装其根证书；
不要在业务 Web 中重新启用 TLS 或发布 80/443。
