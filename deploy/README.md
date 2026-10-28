# 仅使用 IP 的 HTTPS 部署

本文提供两套从零部署流程，均不要求域名：

- **局域网 IP**：Caddy 内部 CA 签发证书，每台客户端安装根证书。
- **公网 IP**：Caddy 向 Let's Encrypt 申请受浏览器信任的 IP 证书，客户端无需安装内部根证书。

先完成“公共准备”，然后选择一种方案。示例以全新 **Ubuntu 24.04、IPv4、标准 TCP 80/443 端口**为准。服务器还需要能够联网下载依赖和镜像。客户端不需要安装 Docker。

公网部署只改变网站和信令服务器的位置。当前文件直传无 STUN/TURN、无服务器文件中继；双方浏览器仍需能直接连接，不能据此承诺跨局域网传文件。

## 1. 公共准备

### 1.1 安装 Docker Engine 与 Compose

在服务器执行以下命令。软件源中的 `noble` 对应 Ubuntu 24.04，其他系统应采用对应的 [Docker 官方安装说明](https://docs.docker.com/engine/install/ubuntu/)。

```bash
sudo apt update
sudo apt install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF_DOCKER
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

如果已经安装其他来源的 Docker，先按官方说明处理包冲突，不直接混装。宿主机无需另装 Python、Node 或 PostgreSQL，它们由项目镜像提供。

### 1.2 获取项目

示例部署目录为 `/opt/MyCollabAdvanced`。将下面的仓库地址替换成自己的地址，或复制完整项目到该目录。

```bash
sudo mkdir -p /opt/MyCollabAdvanced
sudo chown "$USER":"$(id -gn)" /opt/MyCollabAdvanced
git clone <你的仓库地址> /opt/MyCollabAdvanced
cd /opt/MyCollabAdvanced/deploy
cp .env.example .env
chmod 600 .env
```

确认代码包含文件互传功能。本地尚未推送的提交不会出现在远程克隆中。只在首次部署时复制 `.env.example`；更新已有部署时保留原 `.env`。

**后续服务器上的 Compose 命令均在 `deploy/` 执行。**仓库根目录的 Compose 仅用于开发数据库；不要同时把它作为生产栈启动。

### 1.3 生成密钥

运行两次，分别生成 Django 密钥和数据库密码，填入所选方案的 `.env`：

```bash
openssl rand -hex 32
openssl rand -hex 32
```

不要把真实 `.env` 提交到 Git。以下配置中所有占位值都必须替换。

### 1.4 Caddy 版本与配置位置

项目的 `Dockerfile.caddy` 构建 Vue 前端后，使用 `caddy:2-alpine` 提供 HTTPS；`Caddyfile` 被复制进镜像，不是运行时挂载文件。下文两个完整 Caddyfile 均替换服务器上的 `deploy/Caddyfile`，并通过重新构建生效，不改 `/api`、`/admin` 或静态资源路由。

公网 IP 方案需要支持 IP ACME 和 `profile` 的 Caddy。维护者确认该支持已进入 2.10.1；本文配置在 **2.11.7** 上验证。部署时核对版本，并将经过验证的补丁版本固定到 `Dockerfile.caddy` 的最终 `FROM` 行（例如 `FROM caddy:2.11.7-alpine`），避免依赖旧缓存或长期使用浮动版本。[Caddy 官方项目说明](https://github.com/caddyserver/caddy/issues/7118)

## 2. 方案 A：局域网 IP

### 2.1 网络准备

示例地址为 `192.168.8.10`，全文替换为实际服务器内网地址。

1. 在路由器中为服务器设置 DHCP 地址保留；客户端仍可动态获取地址。
2. 客户端必须能访问服务器 TCP 80/443，端口未被其他服务占用。
3. 不配置公网端口转发；如果服务器同时有公网网卡，应限制端口绑定或上游访问范围，避免意外公开。

Docker 发布端口可能绕过部分 UFW 规则，不能仅依赖 UFW 判断访问范围；使用路由器、上游防火墙或 Docker 对应规则控制。[Docker 防火墙说明](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations)

### 2.2 编辑 `deploy/.env`

```dotenv
DJANGO_SECRET_KEY=替换为第一段随机字符串
POSTGRES_PASSWORD=替换为第二段随机字符串
DOMAIN=192.168.8.10
DJANGO_ALLOWED_HOSTS=192.168.8.10
DJANGO_CSRF_TRUSTED_ORIGINS=https://192.168.8.10
POSTGRES_DB=mycollab
POSTGRES_USER=mycollab
DJANGO_TIME_ZONE=Asia/Shanghai
```

虽然变量名是 `DOMAIN`，这里直接填写 IP，不带协议、端口或路径。CSRF 配置包含 `https://`。

### 2.3 替换 `deploy/Caddyfile`

```caddyfile
{
	default_sni {$DOMAIN}
}

{$DOMAIN} {
	tls internal
	encode gzip

	handle /api/* {
		reverse_proxy backend:8000
	}

	handle /admin/* {
		reverse_proxy backend:8000
	}

	handle /static/* {
		root * /srv
		file_server
	}

	handle {
		root * /srv/frontend
		try_files {path} /index.html
		file_server
	}
}
```

`tls internal` 使用内部 CA。`default_sni` 为不携带 SNI 的 IP 访问提供证书选择名称，尤其用于 Docker 端口映射下避免按容器地址寻找证书；它不会改变证书的信任要求。[Caddy default_sni 文档](https://caddyserver.com/docs/caddyfile/options#default-sni)

### 2.4 构建、检查并启动

```bash
sudo docker compose config --quiet
sudo docker compose build --pull
sudo docker compose run --rm --no-deps caddy caddy version
sudo docker compose run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 backend caddy
```

`db` 应显示 healthy，`backend` 与 `caddy` 保持运行。后端启动命令已包含迁移和 collectstatic，无需另跑宿主机 Python。等待后端启动完成后创建管理员：

```bash
sudo docker compose exec backend python manage.py createsuperuser
```

### 2.5 导出并安装根证书

在服务器执行：

```bash
sudo docker compose cp \
  caddy:/data/caddy/pki/authorities/local/root.crt \
  ./mycollab-root.crt
openssl x509 -in mycollab-root.crt -noout -fingerprint -sha256
```

通过可信方式将 `mycollab-root.crt` 复制到每台客户端，并核对指纹。只分发公开根证书，不分发 `root.key`、`intermediate.key` 或整个 Caddy 数据卷。

以下命令在**客户端**证书所在目录执行，选择对应系统：

macOS：

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain ./mycollab-root.crt
```

Windows（管理员 PowerShell）：

```powershell
certutil -addstore -f ROOT .\mycollab-root.crt
```

Ubuntu：

```bash
sudo cp mycollab-root.crt /usr/local/share/ca-certificates/mycollab-root.crt
sudo update-ca-certificates
```

重启浏览器。若浏览器使用独立证书库，还需在其“证书颁发机构”管理页导入同一根证书。容器内的信任操作不会替客户端安装证书。[Caddy 客户端信任说明](https://caddyserver.com/docs/running#local-https-with-docker)

### 2.6 验收

客户端打开 `https://192.168.8.10`，应无证书警告并能登录。也可以显式指定根证书验证，避免命令行与浏览器信任库不同造成误判：

```bash
curl --cacert ./mycollab-root.crt -I https://192.168.8.10
```

继续执行第 4 节的功能验收与维护。

## 3. 方案 B：仅有公网 IP，无域名

### 3.1 证书与网络前提

**公网 IP 可以获得受浏览器信任的证书，不需要购买域名。**Let's Encrypt 已开放 IPv4/IPv6 IP 证书，要求使用 `shortlived` profile，有效期为 **160 小时，约 6 天 16 小时**。因此必须保持自动续期，不能按传统长期证书手工更新。[Let's Encrypt 正式公告](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/)

本方案使用 Caddy 自带 ACME 客户端申请并自动续期，无需 Certbot。准备条件：

1. 一台拥有稳定、可路由公网 IPv4 的服务器；云服务器有弹性公网 IP 时填写该公网 IP，不填写控制台中的私网 IP。
2. 云安全组、主机防火墙及 NAT 转发允许外部访问 TCP 80/443，并将流量交给此 Caddy。外部证书验证不能被登录页或来源白名单拦截；续期期间也保持可达。
3. 服务器能向外访问 ACME 服务，系统时间正确。SSH 管理端口只向管理来源开放。
4. 不开放 PostgreSQL 5432、Gunicorn 8000、Vite 5173 或 Caddy 管理端口。项目只发布 TCP 80/443。

以下 `203.0.113.10` 是**文档保留地址，不能用于申请证书**，必须全部替换为自己的真实公网 IP。私有地址、CGNAT 地址和只有出站公网访问能力的机器不能按此流程完成公网验证。

### 3.2 编辑 `deploy/.env`

```dotenv
DJANGO_SECRET_KEY=替换为第一段随机字符串
POSTGRES_PASSWORD=替换为第二段随机字符串
DOMAIN=203.0.113.10
DJANGO_ALLOWED_HOSTS=203.0.113.10
DJANGO_CSRF_TRUSTED_ORIGINS=https://203.0.113.10
POSTGRES_DB=mycollab
POSTGRES_USER=mycollab
DJANGO_TIME_ZONE=Asia/Shanghai
```

客户端统一通过这个公网 IP 访问。没有域名，不需要 DNS A/AAAA 记录。本文只给 IPv4 可复制配置；IPv6 的 URL 方括号和 Django 主机校验需要另行配置，不能原样替换。

### 3.3 替换 `deploy/Caddyfile`

```caddyfile
{
	default_sni {$DOMAIN}
}

{$DOMAIN} {
	tls {
		issuer acme {
			dir https://acme-v02.api.letsencrypt.org/directory
			profile shortlived
		}
	}
	encode gzip

	handle /api/* {
		reverse_proxy backend:8000
	}

	handle /admin/* {
		reverse_proxy backend:8000
	}

	handle /static/* {
		root * /srv
		file_server
	}

	handle {
		root * /srv/frontend
		try_files {path} /index.html
		file_server
	}
}
```

这里显式选择 Let's Encrypt **生产** ACME 地址与 `shortlived` profile。不要保留 `tls internal` 或全局 `local_certs`，也不要使用 staging 地址作为最终部署；staging 证书不受普通浏览器信任。仅修改 `.env` 为公网 IP、沿用默认 Caddyfile，并不等于启用了公共 IP 证书。[Caddy ACME profile 配置](https://caddyserver.com/docs/caddyfile/directives/tls#issuers)

### 3.4 构建、检查并启动

```bash
sudo docker compose config --quiet
sudo docker compose build --pull
sudo docker compose run --rm --no-deps caddy caddy version
sudo docker compose run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 backend caddy
```

确认版本支持第 3.3 节语法。配置验证通过只代表可加载，不代表证书已经签发；启动后查看 Caddy 日志，等待实际签发成功。若失败，先修复公网验证和网络问题，不通过反复删除数据卷或重建账户来重试。

后端就绪后创建管理员：

```bash
sudo docker compose exec backend python manage.py createsuperuser
```

### 3.5 验证公网 IP 证书

在另一台设备或另一网络访问真实公网 IP：

```bash
curl -I https://203.0.113.10
```

不要加 `-k`。浏览器应直接信任证书，无需安装第 2 节的内部根证书；若要求安装内部根证书，检查是否误用了 `tls internal` 或旧镜像。

检查证书颁发者、有效期和 IP SAN：

```bash
openssl s_client -connect 203.0.113.10:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer -dates -ext subjectAltName
```

IP SAN 必须包含实际公网 IP。此命令用于查看证书，不能替代前面的 `curl` 信任验证。若同一 IP 曾经使用过内部 CA，在重新构建并启动后再次核对实际证书，不以旧的浏览器信任结果作为公共证书验收。

### 3.6 保持续期

Caddy 运行期间管理自动续期。保留 `caddy_data` 卷、保证公网验证端口和出站网络长期可达，并监控日志及证书过期时间。容器停止数日后可能遇到证书过期；恢复网络并启动 Caddy 后等待重新签发，不能靠跳过浏览器警告维持使用。

公网验证无法满足时，可改用第 2 节的内部 CA 方式并让所有客户端安装根证书，但这不再是浏览器默认信任的公网证书方案。不要把证书失败静默降级为 HTTP。

## 4. 功能验收与维护（两种方案共用）

### 4.1 登录与安全上下文

1. 浏览器使用所选 IP 的 HTTPS 地址访问，无证书警告并能登录。
2. 刷新任务详情页，确认 SPA 路由正常；管理员可访问 `/manage` 审批其他成员注册。
3. 在浏览器开发者工具控制台检查：

```javascript
window.isSecureContext
// 应为 true

typeof crypto.subtle?.digest
// 应为 "function"
```

点击“忽略证书警告继续访问”不算通过 HTTPS 验收。

### 4.2 双机直传

两台设备登录同一个部署地址，打开“文件互传”：发送端选择小文件、生成配对码；接收端输入码、核对信息并确认接收。双方保持页面打开，接收端 SHA-256 一致后保存文件。再测接近 100 MiB 的文件与传输中取消。

浏览器或系统询问局域网访问权限时允许本站。HTTPS 成功与 WebRTC 成功是两个独立条件：即使网站位于公网，同局域网设备仍可能因 mDNS、UDP、防火墙或浏览器权限而无法直连。本机曾复现默认 mDNS 受限；临时原始 IP 模式的自动测试成功不替代实际双机验收。详细测试入口见[浏览器文件直传验收](../TECH_STACK.md#浏览器文件直传验收)。

### 4.3 定时清理

在服务器执行 `sudo crontab -e`，添加以下任务（服务器目录和 Docker 路径不同时调整）：

```cron
*/5 * * * * cd /opt/MyCollabAdvanced/deploy && /usr/bin/docker compose exec -T backend python manage.py cleanup_transfers
```

日期提醒和本地 Agent 历史清理沿用[技术文档](../TECH_STACK.md#16-部署与升级操作)中的其他计划任务；它们不负责 TLS 证书续期。

### 4.4 更新与数据保留

数据库、素材、Caddy 证书/内部 CA 都存储在 Compose 命名卷中。部署前建立数据库和素材的备份方案，同时保管 `.env`、实际部署的 Caddyfile 和 Caddy 数据卷；包含 CA 私钥的备份不能分发给客户端。

已有数据的部署应先备份再更新：后端每次启动都会执行待应用迁移，首次空库部署和已有库升级的影响不同。不要在已初始化数据库上仅修改 `.env` 中的 `POSTGRES_PASSWORD`，该变量不会自动更改数据库中的现有密码。

更新代码后，核对并保留本机选择的 IP/Caddyfile 配置，再在 `deploy/` 执行：

```bash
sudo docker compose build
sudo docker compose run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo docker compose up -d
```

修改 Caddyfile 后必须重新构建，因为文件打包在镜像中。仅修改 `.env` 时执行 `docker compose up -d` 以重新创建受影响容器，单纯 `restart` 不会更新容器环境变量。

普通停止与恢复：

```bash
sudo docker compose stop
sudo docker compose up -d
```

**不要用 `docker compose down -v` 做普通重启**，它会删除包括数据库、素材和证书在内的命名卷。局域网 CA 丢失重建后，客户端需要重新安装新根证书。

### 4.5 常见故障定位

- **无法连接**：核对实际 IP、云安全组/路由转发、端口占用及 `docker compose ps`；容器内部地址不是客户端访问地址。
- **公网证书申请失败**：确认是可路由公网 IP、80/443 验证可达、ACME 出站可达、`profile shortlived`、生产目录地址以及 Caddy 版本。不要向 Let's Encrypt 申请 RFC1918 私有 IP 或文档示例 IP。
- **IP TLS 握手失败**：确认全局 `default_sni` 与实际访问 IP 一致，新的 Caddyfile 已重建进镜像，实际返回证书 SAN 正确。
- **证书不受信任**：局域网检查客户端根证书与浏览器证书库；公网检查颁发者是否误为内部 CA 或 staging。
- **400 / DisallowedHost**：`DJANGO_ALLOWED_HOSTS` 应包含实际访问 IP，不带协议。
- **登录或写入 403 / CSRF**：`DJANGO_CSRF_TRUSTED_ORIGINS` 与浏览器的完整 HTTPS origin 一致；更改环境变量后重新创建容器。
- **502**：检查 backend 日志和数据库健康状态，尤其是首次迁移、数据库密码及镜像构建错误。
- **文件互传无法建立连接**：先通过安全上下文检查，再排查双方 mDNS/UDP 和局域网权限；部署 HTTPS 本身不会提供 TURN 中继。

## 5. 验证范围

本次文档编写核对了项目 Compose、Dockerfile、环境变量和官方证书说明，并以本地 Caddy 2.11.7 验证两份 Caddyfile。验证未向外部 CA 提交证书申请，也未部署到实际公网服务器；公网签发、自动续期和用户设备信任必须在真实目标 IP 上验收。
