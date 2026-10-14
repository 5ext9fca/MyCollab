# AGENTS.md

## 项目概览
MyCollab 是一个**单团队 Mission 协作系统**：发布 Mission、认领未分配任务、拆分为可独立认领的子任务，走「发布 → 认领 → 拆分 → 执行 → 提交 → 验收」。后端 Django API + Vue SPA + Docker 部署均已实现并可运行。

- 产品规则与数据模型：`PROJECT_STRUCTURE.md`
- 技术栈与实现约束（MUST 为硬性要求）：`TECH_STACK.md`
- 命令与本地上手：`README.md`

已实现功能包括：Mission 全流程、任务下的 Markdown 评论（作者可编辑/删除）、按用户隔离的素材库（文件按用户存放，Markdown 只可引用自己的素材或外链 URL）、用户注册（需管理员审批）、以及 SPA 内自行实现的管理后台（`/manage`，区别于 Django Admin）。

两份设计文档为中文；用户明确的需求优先，与文档冲突时先改规则与测试，再改代码。

## 沟通语言（强制）
- **与用户的所有交互必须使用中文**：回复、提问、计划、进度与交付说明、提交信息，以及代码注释中的说明文字，一律用中文。
- 代码标识符、命令、文件路径、API 字段名与第三方专有名词保留原文；引用 `PROJECT_STRUCTURE.md`、`TECH_STACK.md` 等中文文档时保持中文表述。

## 常用命令
后端（在 `backend/`，使用 `.venv`）：
- 启动依赖数据库（仓库根）：`docker compose up -d`
- 迁移：`.venv/bin/python manage.py migrate`
- 建用户：`.venv/bin/python manage.py createsuperuser`
- 开发服务器：`.venv/bin/python manage.py runserver`（http://127.0.0.1:8000）
- 全部测试：`.venv/bin/python manage.py test`
- 单个测试：`.venv/bin/python manage.py test missions.tests.test_services.MissionServiceTests.test_claim_sets_assignee_and_is_exclusive`
- 迁移检查：`.venv/bin/python manage.py makemigrations --check --dry-run`

前端（在 `frontend/`）：
- 开发：`npm run dev`（http://127.0.0.1:5173，代理 `/api` 到 8000）
- 类型检查：`npm run type-check`
- 测试：`npm run test`（单个文件：`npm run test -- src/tests/client.spec.ts`）
- 生产构建：`npm run build`

## 架构关键点（容易踩坑）
- **所有业务写入必须走 `backend/missions/services.py`。** DRF 视图只做解析/认证/调用服务/序列化；Django Admin 的写操作也调用同一服务。禁止新增绕过状态机的通用字段更新。
- 认领/退出/提交/验收/取消都在事务内用 `select_for_update` + 状态校验实现；并发认领只有一个成功，其余返回 `409`（`code=claim_conflict`）。不要写成“先查再写”。
- 状态固定为 `Open/InProgress/Submitted/Done/Cancelled`：`Open` 认领者为空，`InProgress/Submitted/Done` 必须有认领者，`Cancelled` 保留原认领者（数据库 CheckConstraint 强制）。
- `Submitted`/`Done` 冻结内容；父任务需未取消的子任务全部 `Done` 才能提交，但不会自动完成；禁止父子循环与自引用。
- 编辑用 `version` 乐观锁：`PATCH /api/missions/{id}/` 必须带当前 `version`，过期返回 `409`（`code=version_conflict`）。
- API 错误统一为 `{code, message, field_errors}`（`backend/config/exception_handler.py`）；服务层抛 `backend/missions/exceptions.py` 的 `DomainError` 子类。
- 认证是 Django Session + CSRF。Vite 代理必须保持 `changeOrigin: false`，否则 CSRF Origin 校验会失败。
- 前端 API 调用集中在 `src/api/`，统一用 `request()` 处理 CSRF/错误；Markdown 必须经 `MarkdownContent.vue`（DOMPurify 清洗）渲染，不得直接 `v-html` 用户输入。
- 用户素材库（`backend/library/`）：文件按用户隔离存放于 `MEDIA_ROOT/library/<user_id>/`，**不作为公开静态目录**（生产由 Caddy 代理 `/api` 后经 API 下载），只能经 `GET /api/library/files/{id}/` 授权下载；上传与删除走 `library/services.py`。
- 所有 Markdown 字段（Mission 的 `content`/`acceptance_criteria` 与评论 `content`）在服务层校验引用：只允许作者自己的素材链接或 `http(s)` 外链，其余返回 `400`（见 `library/references.py`）。
- **不要用 SQLite 跑并发/事务测试**：`missions/tests/test_concurrency.py` 依赖 PostgreSQL。

## 修改后如何验证
按 `README.md` 的顺序执行：后端 `makemigrations --check --dry-run` → `check` → `test`；前端 `type-check` → `test` → `build`。不得声称未运行的测试已通过；每次交付说明改动、验证结果与未完成事项。

## 文档同步（强制）
- 接到写入 `NEW_FUNCTION.md` 的请求时，先检查目标功能在当前代码、测试与文档中是否已经实现。若已完整实现，向用户说明现状，不重复写成待实现功能；若仅部分实现，明确已有能力与剩余工作。
- 需要写入 `NEW_FUNCTION.md` 时，**先清空原有内容，再写入本次功能的完整规格**，不得将新需求追加到旧需求后面。写入时一并提供实现所需的**项目当前结构信息**：相关目录与文件职责、已有数据模型与接口、前后端数据流、关键业务约束及现有测试入口。区分已实现的事实与待实现的需求；信息只需覆盖本次功能，路径和行为必须与当前代码一致，不能只引用 `PROJECT_STRUCTURE.md` 或 `TECH_STACK.md` 让编码 Agent 自行查找。
- 负责编码的 Agent 先以 `NEW_FUNCTION.md` 中的需求和项目结构信息为依据；**只有认为其中信息不足时才重新理解项目**，不把通读整个仓库作为固定前置步骤。实现时仍须阅读直接涉及的代码并执行必要验证。
- 每实现并通过验证一个新功能，必须把它的**数据模型、接口、权限、页面与业务规则**并入 `PROJECT_STRUCTURE.md`，与代码一起交付；不要只改代码而不同步该文档。
- 若改动涉及技术栈或技术约束（`TECH_STACK.md` 中的 MUST/SHOULD），同步更新 `TECH_STACK.md`，并保证文档描述与实际代码一致。

## 提交规范（强制）
- **提交时机与内容由代理自行决定**，无需每次先征得用户同意：一个聚焦的改动完成并验证通过后立即提交，不等用户催促；未完成、未验证或会破坏构建的工作不提交。
- 一次提交只做一件事：同一功能的代码、测试与文档同步改动放在同一个提交里；不要把互不相关的改动混在一起，也不要按文件逐个提交。若一批改动天然包含多个独立的可验证单元，则拆成多个提交。
- 提交信息用中文、简短祈使句描述改动，例如 `新增任务类型、依赖与阻塞`；必要时在正文补充改动范围、验证命令与破坏性变更说明。
- 只提交明确属于本次工作的文件，不顺手提交无关的临时文件或未跟踪产物；工作区中他人的既有改动不擅自纳入。
- **推送（push）仍以用户明确要求为准**，不擅自推送到远端。

## 已确定决策
- UI 组件库：**Element Plus**（见 `TECH_STACK.md` 第 8 节）。
- 运行时：Python 3.14 / Django 6.1 / DRF 3.18 / PostgreSQL 16 / Node 24（依赖版本见 `backend/requirements.txt` 与 `frontend/package.json`）。
