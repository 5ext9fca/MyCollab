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

需要 Python 3.14、Node 24+、Docker。数据库用 PostgreSQL（并发测试依赖它，不能用 SQLite）。

```bash
# 1. 启动本地 PostgreSQL
docker compose up -d

# 2. 后端
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # 或 shell 里 create_user
.venv/bin/python manage.py runserver         # http://127.0.0.1:8000

# 3. 前端（另开一个终端）
cd frontend
npm install
npm run dev                                  # http://127.0.0.1:5173
```

Vite 开发服务器把 `/api` 代理到 Django，代理不改变 Host/Origin，因此 Session Cookie 与 CSRF 在开发环境可直接工作。

### 一键启动测试环境

在仓库根目录运行（也支持从其他目录使用脚本绝对路径）：

```bash
./testrun.sh
./testrun.sh --seed  # 可选：创建演示数据，已存在时跳过
```

脚本检查 Python 3.14、Node 24+ 和 Docker Compose；首次缺少虚拟环境或依赖时自动安装，因此首次运行需联网。随后启动根目录 Compose 的 PostgreSQL 并等待就绪，执行迁移和系统检查，同时启动 Django 与 Vite。访问 `http://127.0.0.1:5173`；端口 8000 或 5173 被占用时直接提示退出，不终止已有服务。

使用本地 `127.0.0.1:5432/mycollab` 数据库及本地开发账号配置，保留已有数据，不读取生产部署配置。按 Ctrl+C 停止本次前后端进程，PostgreSQL 容器继续运行；需要时可在根目录手动执行 `docker compose stop db`。前端保留热更新，后端使用 `--noreload` 以可靠清理进程，修改后端代码后需重启脚本。

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
