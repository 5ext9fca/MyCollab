# MyCollab — Mission 协作系统

一个小型团队内部协作工具：发布 Mission、认领未分配任务、拆分为可独立认领的子任务，并完成「发布 → 发现 → 认领 → 拆分 → 执行 → 提交 → 验收」的完整流程。任务详情页支持 Markdown 评论（作者可编辑/删除），每个用户拥有独立素材库（文件按用户隔离存放，Markdown 只能引用自己的素材或外链 URL）；此外支持带管理员审批的用户自助注册，以及前端自行实现的管理后台。

在基础流程之上，系统已支持：任务类型（`Feature`/`Task`/`Bug`）、优先级（`P0`–`P3`）、目标里程碑、显式前置依赖与**派生阻塞**（不新增状态）、独立验收者与转交验收、按轮次不可覆盖的成果提交（含源码/构建引用与验收时选择验证构建）、以及已完成任务的重新打开。所有对现有对象的写请求都强制携带 `expected_version`。SPA 已提供对应的创建/编辑表单、列表筛选、详情页（任务树 / 前置 / 下游 / 未完成子任务分开展示、成果与验收历史）、里程碑页面（`/milestones`）与可视化工作台（`/workspace`，里程碑 × 状态概览 + 依赖图，详见 `PROJECT_STRUCTURE.md` 第 8、9 节）。

产品规则与数据模型见 [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md)，技术栈与实现约束见 [`TECH_STACK.md`](./TECH_STACK.md)。

第一次接触游戏开发或任务协作，请先阅读 [从零开始用 MyCollab 协作开发游戏](./TUTORIAL.md)：从游戏制作流程讲起，通过一个小型游戏案例练习设计、分工、认领、提交、验收与发布。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router |
| 依赖图 | Vue Flow（`@vue-flow/core` + `@vue-flow/controls`）+ 自研分层布局（`src/composables/useGraphLayout.ts`） |
| 后端 | Python + Django + Django REST Framework |
| 数据库 | PostgreSQL 16 |
| 认证 | Django Session + Cookie + CSRF |
| 部署 | Gunicorn + Caddy + Docker Compose |

渲染用户 Markdown 前会用 DOMPurify 清洗，避免 XSS。

## 目录结构

```text
backend/            Django 项目
  config/           settings、URL、WSGI
  common/           跨 app 共享的领域异常
  accounts/         用户、认证、注册申请与管理员审批
  missions/         Mission、标签、服务层、API、测试
  library/          用户素材库、授权下载与 Markdown 引用校验
  Dockerfile
frontend/           Vue 3 SPA
  src/api/          类型化 API 客户端
  src/components/   共享组件
  src/views/        页面
  src/tests/        Vitest 测试
deploy/             Caddyfile、生产 Docker Compose
docker-compose.yml  本地 PostgreSQL
testrun.sh          一键启动本地测试环境
```

后端业务写入集中在 `backend/missions/services.py`（Mission 流程）、`backend/accounts/services.py`（注册审批）与 `backend/library/services.py`（素材上传/删除），视图与 Django Admin 都调用同一套服务逻辑，无法绕过状态机。

## 本地开发

需要 Python 3.13、Node 24+、Docker。数据库用 PostgreSQL（并发测试依赖它，不能用 SQLite）。

```bash
# 1. 启动本地 PostgreSQL
docker compose up -d

# 2. 后端
cd backend
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # 或 shell 里 create_user
.venv/bin/python manage.py runserver         # http://127.0.0.1:8000

# 3. 前端（另开一个终端）
cd frontend
npm install
npm run dev                                  # http://127.0.0.1:5173
```

已有其他 Python 版本的 `backend/.venv` 时，先停止后端与 LocalRunner，再重建虚拟环境（只删除依赖环境，不删除数据库或素材）：

```bash
cd backend
rm -rf .venv
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Vite 开发服务器把 `/api` 代理到 Django，代理不改变 Host/Origin，因此 Session Cookie 与 CSRF 在开发环境可直接工作。

### 一键启动测试环境

在仓库根目录运行（也支持从其他目录使用脚本绝对路径）：

```bash
./testrun.sh
./testrun.sh --seed  # 可选：创建演示数据，已存在时跳过
```

脚本检查 Python 3.13、Node 24+ 和 Docker Compose；首次缺少虚拟环境或依赖时自动安装，因此首次运行需联网。随后启动根目录 Compose 的 PostgreSQL 并等待就绪，执行迁移和系统检查，同时启动 Django 与 Vite。访问 `http://127.0.0.1:5173`；端口 8000 或 5173 被占用时直接提示退出，不终止已有服务。

使用本地 `127.0.0.1:5432/mycollab` 数据库及本地开发账号配置，保留已有数据，不读取生产部署配置。按 Ctrl+C 停止本次前后端与 LocalRunner 进程，PostgreSQL 容器继续运行；需要时可在根目录手动执行 `docker compose stop db`。前端保留热更新，后端使用 `--noreload` 以可靠清理进程，修改后端代码后需重启脚本。

`./testrun.sh` 在前后端就绪后自动启动 LocalRunner，读取 `~/.config/MyCollab/mycollab-runner.json`；配置缺失时提示并跳过，Runner 退出时提示且保持前后端运行，不自动重启。Ctrl-C 或终止脚本时一并停止本次 Runner，通过 SIGTERM 复用模型进程清理，数据库与数据保留。启动前应确认配置中的服务器地址和设备凭据属于预期环境；Runner 仍使用该配置，不覆盖服务器地址。此启动流程不改变数据模型、接口或权限。

这是供浏览器体验功能的本地环境启动入口；自动化测试仍使用下方“验证命令”。

## 演示数据

本地开发可一键生成样板数据；所有场景通过服务层执行真实流程，计划日期相对生成当天计算：

```bash
cd backend
.venv/bin/python manage.py seed_demo         # 不存在样板数据时创建
.venv/bin/python manage.py seed_demo --reset # 重建演示账号的业务数据，保留账号与其他成员数据
```

首次创建的演示账号为 `alice`、`bob`、`carol`、`dave`、`erin`，密码统一为 `demo12345`。重建保留已有账号及其有效密码，修复旧版示例的空密码，不修改管理员权限。

- 用 `alice` 查看待验收、临期、逾期和需复核；用 `bob` 查看退回待改、解除阻塞和私有筛选。
- 任务覆盖五种状态、父子拆分、前置阻塞、人工验收、退回、上游重开后的下游复核，以及源码/构建证据。
- 工作台甘特图展示完整日期、仅交付日期、未排期任务；任务广场可体验选择当前页与批量计划修改。
- 设计目录包含设计树、动画资产、三步生产模板及实例化批次；保存筛选包含团队阻塞、需复核、未来七天计划和个人认领条件。
- 通知包含业务事件、评论、临期/逾期提醒、已读/未读；详情中可以体验关注与静音。
- 打开“示例导览：当前能力与边界”任务阅读体验顺序。系统不自动排期、执行构建或完成下游任务；构建链接是示意地址，未预置私人素材文件。提醒的持续更新仍需运行 `send_mission_reminders` 或配置外部定时调度。

`--reset` 会删除上述演示账号创建的任务、里程碑、设计、模板、批次，以及名称以“示例 · ”开头的筛选，再重建场景；保留账号、个人素材、其他筛选及共享标签。请勿把这五个账号用于需要长期保留的业务数据。其他成员引用演示任务时拒绝重建；受保护的其他引用也会使事务回滚。

## 用户注册与审批

成员加入采用「先申请、后审批」：

1. 未登录用户访问注册页（`/register`）提交申请；后端写入一条 `Pending` 记录（密码立即哈希，**不创建用户**）。
2. 管理员（`is_staff`）在管理后台（`/manage`）或 Django Admin 的「注册申请」中通过或拒绝。
3. 通过后后端创建并激活用户，申请人即可用原密码登录；未通过前登录返回 `401`。

先创建一个管理员：

```bash
cd backend
.venv/bin/python manage.py createsuperuser
```

`/manage` 是 SPA 自带的管理后台（审批注册、查看成员），与 Django Admin（`/admin/`）相互独立，两者都要求 `is_staff`。相关接口：`POST /api/auth/register/`（公开，需 CSRF）、`GET /api/admin/registrations/`、`POST /api/admin/registrations/{id}/approve/`、`POST /api/admin/registrations/{id}/reject/`、`GET /api/admin/users/`。

## 素材库与 Markdown 引用规则

每个用户有自己的素材库，文件存放在 `MEDIA_ROOT` 的 `library/<user_id>/` 下（数据库记录归属与元信息）。在素材库页面（`/library`）或任务/评论编辑器的「插入素材」按钮上传后，会得到形如 `/api/library/files/{id}/` 的链接。

- **读取**：任何登录成员都可以下载（`GET /api/library/files/{id}/`），图片内联显示、其余作为附件下载；删除只能由所有者本人发起。
- **引用**：Mission 的 `content`、`acceptance_criteria`、提交的 `description` 以及评论 `content` 在写入时校验，只允许引用**作者自己的素材**或 **`http(s)` 外链**；他人素材、站内路径（如 `/media/...`）、相对路径与 `javascript:`/`data:` 等协议一律返回 `400`。校验同时覆盖 Markdown 语法与内联 HTML 属性，并忽略代码块。
- **限制**：允许 `png/jpg/jpeg/gif/webp/pdf/zip/txt/md`，单文件上限 20 MB（可用环境变量 `LIBRARY_MAX_UPLOAD_BYTES`、`LIBRARY_ALLOWED_EXTENSIONS`、`DJANGO_MEDIA_ROOT` 调整）。

附件目录**不对外静态公开**，生产环境也不挂到 Caddy，只通过上述 API 经授权下载。

## 验证命令

```bash
# 后端：迁移检查 + 系统检查 + 测试（在 backend/ 下）
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
.venv/bin/python manage.py test

# 前端：类型检查 + 单元测试 + 生产构建（在 frontend/ 下）
npm run type-check
npm run test
npm run build
```

后端测试使用 Django 测试框架，其中 `missions/tests/test_concurrency.py` 用多线程 + 独立连接验证「并发认领只有一个成功」，**必须在 PostgreSQL 上运行**。

## 生产部署

```bash
cd deploy
cp .env.example .env     # 填入 DJANGO_SECRET_KEY、POSTGRES_PASSWORD、DOMAIN 等
docker compose up -d --build
```

Caddy 在同一域名下按 `/api/*`、`/admin/*`、`/static/*`、其余交给 SPA 的顺序处理请求；数据库只在内部网络开放。上传的附件保存在 `media_data` 卷（`/app/media`），Caddy 不提供该目录，下载一律经 `GET /api/library/files/{id}/`。备份、关闭 DEBUG、使用真实密钥等要求见 `TECH_STACK.md` 第 9 节。

### 站内日期提醒调度

后端 `DJANGO_TIME_ZONE` 默认 `UTC`，需要中国自然日口径时在部署环境中设置为 `Asia/Shanghai`，重建 backend 后生效。任务待办、保存视图相对日期和提醒使用同一服务端日期。

生产服务器可通过 cron 每天运行一次（替换 `/opt/MyCollabAdvanced` 为实际路径，运行用户须有 Docker 权限）：

```cron
0 8 * * * cd /opt/MyCollabAdvanced/deploy && docker compose exec -T backend python manage.py send_mission_reminders >> /var/log/mycollab-reminders.log 2>&1
```

cron 的 08:00 使用宿主机时区；确认宿主机时区与期望调度时间一致，并确保日志路径可写、配置日志轮转及非零退出监控。手动重跑：

```bash
docker compose -f deploy/docker-compose.yml exec -T backend python manage.py send_mission_reminders
```

命令输出扫描任务数及新增通知数，失败非零退出。同一任务/截止日/提醒类型/接收人只写一次；漏跑后补发当前适用提醒。无需 Redis 或 Celery。

## 本地 Agent 文本辅助

第一批提供设计/资产说明润色、生产模板生成、Mission 编写和验收材料分析。登录后在「本地 Agent」创建设备凭据，在本人电脑运行 Runner，再从对应业务表单预览输入、生成并逐字段采纳；最后仍需手动保存或验收。

服务器和浏览器均不调用模型提供商，也不保管供应商凭据。首个本地适配器是 **OpenCode CLI 2.1.3**；安装、登录、绑定、撤销、权限及排错见 [本地 Runner 说明](local_runner/README.md)。升级后照常运行后端迁移以创建 agent_bridge 表。

服务器每天清理一次超过 30 天的辅助历史（沿用部署 cron，无常驻 worker）：

```cron
30 3 * * * cd /opt/MyCollabAdvanced/deploy && docker compose exec -T backend python manage.py cleanup_assistance
```

从仓库根目录运行本地适配器自动化测试，不调用收费模型：

```bash
backend/.venv/bin/python -m unittest discover -s local_runner/tests -v
```

真实闭环测试需本人本机已登录 OpenCode，并明确选择模型。该测试使用独立 PostgreSQL 测试库与临时 HTTP 服务，不修改正常业务数据，但会产生模型调用：

```bash
cd backend
MYCOLLAB_LIVE_MODEL=deepseek/deepseek-flash .venv/bin/python manage.py test agent_bridge.tests.test_live_opencode --noinput
```


## 导出为 Agent 需求文档

图像、代码委派和权限审批已保存到本地分支 `feature/agent-delegation`，主分支以需求文档导出替代。

1. 更新本地 Runner，在“本地 Agent”页面绑定声明“Agent 需求文档”能力的设备。已有设备不会自动扩大权限，可重新绑定；模型凭据仍只在本地。
2. 在 Mission 完整详情或抽屉点击“导出为Agent需求文档”。有多台设备时选择后再点击导出；任务和关联设计、资产说明由本地 LLM 整理。
3. 等待文档返回，预览后点击“下载 Markdown”。文档包含目标、约束、实施要求、交付物、验收标准、待澄清事项和来源；不执行代码或生成图片。

升级仍需执行 `python manage.py migrate`。**本次迁移删除旧图像/代码执行、对话审批、成果提交关联及旧委派请求**，保留 Mission、普通提交正文与素材文件。需要历史数据时先备份数据库；feature 分支保存的是代码，验证旧功能应使用独立数据库。尚未在业务数据库执行本次删除迁移。

## 局域网文件互传

升级后执行后端迁移 `python manage.py migrate`。双方登录，打开顶部“文件互传”：发送方选择文件并生成配对码；接收方输入码、核对信息后点击“确认接收”。支持同一账号在不同设备使用；单文件最多 100 MiB。双方保持页面打开，接收端 SHA-256 一致后点击“保存已校验文件”。文件直传，不进入服务器素材库；首次配对 5 分钟内确认，会话总期限 30 分钟，中断后重新发送。

局域网必须通过受信任 **HTTPS** 访问（本机 localhost 开发除外），否则 Web Crypto SHA-256 不可用。浏览器/操作系统提示访问局域网时允许本站；若连接失败，检查双方网络、防火墙、UDP 和 mDNS。普通 HTTP 互访不保证 WebRTC 能建立连接。本版无跨网中继或后台接收。

每 5 分钟清理过期配对、信令和文件元信息：

```cron
*/5 * * * * cd /opt/MyCollabAdvanced/deploy && docker compose exec -T backend python manage.py cleanup_transfers
```

真实浏览器验收使用隔离 PostgreSQL 测试库，不修改业务数据、不调用模型。先在 `frontend/` 执行 `npm ci` 和 `npx playwright install chromium`，然后在 `backend/` 执行：

```bash
MYCOLLAB_BROWSER_TEST=1 POSTGRES_DB=mycollab_browser .venv/bin/python manage.py test transfers.test_browser --noinput
```

已有 Google Chrome 时可增加 `MYCOLLAB_BROWSER_CHANNEL=chrome`，无需下载 Chromium。测试自动启动临时 Django 服务及 localhost:5179 的 Vite，执行 `npm run test:transfer`；该 npm 命令依赖测试服务和测试用户，不作为单独启动应用的命令。覆盖空文件、普通文件、100 MiB 文件下载摘要一致、篡改字节拒收和取消；同机两个独立浏览器会话不能替代实际两台设备的网络环境验收。失败截图/trace 保存在 `frontend/test-results/`，不提交版本库。

若自动验收机器的 mDNS 解析受限，可在上述验收命令中额外设置 `MYCOLLAB_TEST_RAW_IP=1` 进行对照测试：仅让临时 Chrome/Chromium 测试进程使用原始 IP 候选，不修改系统或日常浏览器设置，也不改变应用代码。该模式下通过的结果证明文件传输及校验协议可用，不证明默认 mDNS 或真实跨设备网络可达；实际部署仍需正常浏览器双机验证。

本次实现的本机验收记录：Chrome 默认 mDNS 候选未能建立连接，独立 WebRTC 探针也复现该现象；临时测试浏览器启用原始 IP 候选后，6 项真实浏览器测试全部通过（空文件、约 2 MiB、100 MiB、字节篡改拒收、配对后取消、传输中取消）。桌面与 390px 窄屏截图已检查。未修改系统或日常浏览器权限；真实两台设备的默认浏览器环境仍需部署后验证。
