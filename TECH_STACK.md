# TECH_STACK

## 1. 目的与适用范围

本文定义 Mission 协作系统的技术栈与实现约束，供 coding agent 和开发者阅读。

- 使用规模：单个团队，最多约 50 名使用者；不是 50 名开发者。
- 产品核心：发布 Mission、标签分类、递归子 Mission、单人认领、提交与验收。
- 部署目标：单台 Linux 服务器；前端静态资源、后端和数据库可共同部署。
- 架构：模块化单体后端 + SPA 前端 + 关系型数据库。
- 优先级：业务正确性、可维护性、开发效率、运行成本。

本文中的 MUST 表示实现要求，SHOULD 表示默认建议。明确的用户需求优先；已有仓库的实际配置应先检查再修改。第 5 节是初始业务假设，不能据此覆盖用户后来确定的产品规则。

## 2. 已选技术栈

| 层 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | Vue 3、TypeScript、Vite | SPA、任务列表、任务树、交互表单 |
| 前端路由 | Vue Router | 页面导航与路由参数 |
| 后端 | Python 3.13、Django | 业务逻辑、用户体系、ORM、迁移、事务 |
| API | Django REST Framework（DRF） | JSON REST API、输入校验、权限检查 |
| 依赖图渲染 | Vue Flow（`@vue-flow/core` + `@vue-flow/controls`） | 只读依赖图的节点/边、平移与缩放控制 |
| 依赖图布局 | 前端自研甘特布局（`frontend/src/composables/useGanttLayout.ts`） | 真实日期横轴、逐任务行与父子标签缩进 |
| 数据库 | PostgreSQL | 业务数据、约束、索引、并发控制 |
| 身份认证 | Django Session、Cookie、CSRF | 同域浏览器登录与请求认证 |
| 管理界面 | Django Admin + SPA 自建管理后台 | 数据检查、注册审批、成员与标签管理 |
| 应用服务器 | Gunicorn，WSGI 部署 | 运行 Django HTTP 应用 |
| HTTP 入口 | Caddy | HTTPS、静态文件、反向代理 |
| 服务部署 | Docker Compose | 管理 Caddy、应用和数据库 |

运行时 MUST 使用 Python 3.13（后端及 LocalRunner），本地虚拟环境与 Docker 镜像保持一致；Python 补丁版本跟随 3.13 系列更新。

版本策略：使用相互兼容、仍受支持的稳定版本。初始化时记录并锁定依赖，复用仓库已有的包管理器；不得无理由升级主版本或使用浮动的生产镜像标签。本文不指定未经验证的精确版本号。

## 3. 架构与部署边界

生产环境使用同一域名：

| 路径 | 处理方 |
| --- | --- |
| `/api/` | Caddy 代理至 Django / DRF |
| `/admin/` | Caddy 代理至 Django Admin |
| `/static/` | Django collectstatic 产物，由 Caddy 提供 |
| 其他前端页面路径 | Vue 构建产物；支持 SPA 路由回退 |

- MUST 先匹配 API、Admin 和静态资源路径，再处理 SPA 回退；API 错误不能返回前端首页 HTML。
- Vue 构建为静态文件，生产环境不运行 Vite 开发服务器。
- Django 在服务端执行所有权限检查与业务写入。
- PostgreSQL 为持久化数据源；数据库与附件分别存放在持久化卷中。
- 附件（用户素材库）存放在 `MEDIA_ROOT` 下的 `library/<user_id>/`，**不得作为公开静态目录对外提供**；只能通过 `GET /api/library/files/{id}/` 经授权下载，Caddy 不配置该目录的静态服务。
- 数据库仅向内部容器网络开放。
- 开发环境用 Vite 代理 `/api/` 至 Django，并正确配置开发域名与 CSRF。
- 第一版可以从 2 vCPU、4 GB 内存开始评估；这只是普通任务管理负载下的起步估算，不是容量保证。

### 本地 Agent 与模型接入约束（新增功能实施原则）

以下为模型辅助与委派功能的硬性边界。第一批实现由 `backend/agent_bridge/` 和用户本机 `local_runner/` 承担；完成状态与后续批次见 `NEW_FUNCTION.md`。

- MUST 最小化新增服务器负担：服务器仅负责业务授权、轻量请求交接、有限结果存储及人工确认后的业务校验，不执行模型推理、代码 Agent、构建或测试。
- MUST 由用户本地 Agent 环境完成所有 LLM/图像模型提供商通信、凭据保管、认证刷新、调用重试和输出下载；服务器与 SPA 均不得保存供应商密钥或代理模型调用。使用云端模型时也由本地环境直接通信。
- MUST 将 MyCollab 设备凭据与供应商凭据分离：前者仅授权本人设备领取和回传限定请求，服务端仅保存令牌摘要；后者不进入 MyCollab。浏览器仍使用 Session + CSRF，新增设备认证不得放宽现有业务 API 权限。
- MUST 由本地 Runner 主动访问服务器，模型执行不占用数据库事务或锁；模型结果经严格校验与人工采纳后复用既有业务服务，不自动推进 Mission 状态。
- SHOULD 复用 Django/PostgreSQL，以有上限、可退避的短请求轮询和历史清理完成交接。首批不新增 Redis、Celery、WebSocket、服务端沙箱或供应商 SDK；限制上下文、结果、并发与保留期，不保存无限日志或 token 流。

## 4. 代码组织与业务入口

当前目录与职责统一见 [PROJECT_STRUCTURE](PROJECT_STRUCTURE.md#仓库目录与职责)。业务入口遵守以下约束。

业务写入 SHOULD 集中在 `missions/services.py`、`accounts/services.py` 或同等职责的模块中，例如：

```python
claim_mission(...)
release_mission(...)
submit_mission(...)
review_mission(...)
cancel_mission(...)
```

- API 负责解析请求、身份认证、调用业务入口和序列化响应。
- 业务入口 MUST 统一检查操作者权限、当前状态及数据约束。
- API、管理命令和未来的其他客户端入口 SHOULD 复用同一业务逻辑。
- Django Admin 的业务写操作也必须遵守状态约束；必要时将相关字段设为只读并提供专用 action。
- 不要通过未经校验的通用字段更新绕过认领、提交或验收流程。

## 5. 初始业务假设

以下规则来自初始设计；产品需求变化时先更新规则与测试。

- Mission 至少包含标题、内容、验收标准、发起者、可空认领者、可空父任务、状态、成果说明、版本号和时间戳。
- 每个 Mission 最多一个认领者、一个父 Mission。
- 父子 Mission 使用同一模型，分别保存发起者、认领者与状态。
- 父任务的认领不自动分配子任务；退出父任务不自动清除子任务认领者。
- 标签通过多对多关联保存，不自动继承。
- 状态使用固定枚举：`Open`、`InProgress`、`Submitted`、`Done`、`Cancelled`。
- `Open` 的认领者为空；`InProgress`、`Submitted`、`Done` 的认领者非空。
- 认领使任务从 `Open` 进入 `InProgress`；退出使其回到 `Open`。
- 认领者提交后进入 `Submitted`；**验收者（`reviewer`，新建默认发起者）或管理员**验收进入 `Done`，退回进入 `InProgress`。默认允许认领者与验收者相同，也允许指定为他人。
- 待验收和已完成任务冻结目标与成果内容；修改待验收任务前应先退回。`Done` 任务可由发起者、验收者或管理员带原因重新打开。
- 父任务在有效子任务全部完成后允许提交，但不会自动完成。
- 取消子任务必须记录原因，父任务验收者判断是否接受该范围变化。
- 父任务的取消不自动取消子任务；已完成或已取消的父任务禁止新增子任务。
- 创建或调整父子关系必须禁止自引用与循环，并遵守父任务状态约束。
- Mission 有固定 `type`（`Feature` / `Task` / `Bug`，默认 `Task`）与 `priority`（`P0`–`P3`，默认 `P2`）；发起者或管理员可在可编辑状态修改。
- Mission 可有唯一目标里程碑（`Milestone`，Planned / Active / Completed / Cancelled）；里程碑是排期维度，不是父任务或构建版本。完成需人工确认且所有有效关联任务 Done/Cancelled。
- Mission 可有显式前置依赖（`MissionDependency`）；阻塞为派生信息，不新增状态。提交与验收通过都要求所有直接前置 Done 且所有有效直接子任务 Done。
- 成果按轮次保存为不可变的 `MissionSubmission`（含 `source` / `build` 引用与验收结论），历史不被覆盖。
- 用户可通过自助注册申请加入团队：申请先进入待审批状态，管理员批准后才创建可登录的用户；未批准的用户名不占用、不可登录。
- Mission 下的评论（Comment）复用与 `Mission.content` 相同的 Markdown 文本定义；任何成员可在任意状态（含已完成/已取消）发表评论，只有作者可编辑或删除自己的评论。
- 用户上传的文件按用户隔离存放（每个用户一个 library）；读取对团队开放，但 Markdown 只能引用作者自己的素材或外链 URL。类型白名单为 `png/jpg/jpeg/gif/webp/pdf/zip/txt/md`，单文件上限 20 MB。

`MissionEvent` 记录操作者、任务、操作类型、必要的变更摘要与时间；事件应与对应业务变更在同一事务内写入。

## 6. PostgreSQL 与并发要求

- MUST 使用 Django ORM 和迁移管理数据库结构。
- MUST 为外键、标签关联和关键状态关系设置适当数据库约束。
- SHOULD 根据实际查询建立索引，例如状态、认领者、父任务和创建时间。
- 任务树默认使用 `parent_id` 邻接表；先按需加载直接子节点，避免无界递归与 N+1 查询。
- 查询列表 MUST 分页；按标签、状态、发起者和认领者筛选。多标签查询为 AND 语义（任务需同时含有全部标签），客户端可重复 `tag` 参数（`?tag=a&tag=b`）或用逗号（`?tag=a,b`）。
- 认领 MUST 使用条件更新或事务内行锁，保证同时认领只有一个成功。
- 禁止使用“先查询未认领，再无条件写入认领者”的方式。
- 编辑与所有写动作 MUST 使用 `version` 做乐观并发检查（`expected_version`），避免覆盖其他用户的修改；创建对象由服务端初始化版本。冲突返回 `409`。
- 与父子/依赖结构有关的写入必须采用一致的并发策略，防止检查完子任务后另一个事务新增子任务，或并发改父节点/加依赖形成循环。
- 图结构变更（父节点、依赖）与可能改变完成约束的状态操作（提交、验收、里程碑完成、改里程碑、重新打开）统一使用固定键的 PostgreSQL 事务级 advisory lock：在读取约束和写入之前获取，只读查询不取锁，锁内不做外部网络请求。单团队第一版复用一个团队级事务锁即可。
- 依赖环检查 MUST 在「子任务先于父任务完成」的隐含边与显式 `prerequisite -> dependent` 边的合并图上进行；只检查依赖表不足以防止死锁。
- PostgreSQL 是涉及事务和并发的测试环境；不能只依赖 SQLite 测试这些行为。

## 7. API 与权限

默认接口风格：

| 接口 | 用途 |
| --- | --- |
| `GET /api/missions/` | 分页查询 |
| `POST /api/missions/` | 发布任务 |
| `GET /api/missions/{id}/` | 详情 |
| `PATCH /api/missions/{id}/` | 修改允许编辑的内容 |
| `POST /api/missions/{id}/claim/` | 认领 |
| `POST /api/missions/{id}/release/` | 退出 |
| `POST /api/missions/{id}/submit/` | 提交成果与证据（description、验证说明、source/build 引用） |
| `POST /api/missions/{id}/review/` | 验收（`submission_id`、`decision`、`comment`、`verified_build_reference_id`） |
| `POST /api/missions/{id}/transfer-review/` | 转交验收者 |
| `POST /api/missions/{id}/reopen/` | 重新打开已完成任务 |
| `POST /api/missions/{id}/cancel/` | 取消 |
| `GET/POST /api/missions/{id}/dependencies/` | 查询 / 添加前置依赖 |
| `DELETE /api/missions/{id}/dependencies/{dependency_id}/` | 移除依赖 |
| `GET /api/missions/{id}/submissions/` | 分页查询各轮成果与证据 |
| `GET/POST /api/milestones/` | 里程碑列表与创建 |
| `GET/PATCH /api/milestones/{id}/` | 里程碑详情与字段编辑 |
| `POST /api/milestones/{id}/transition/` | 受控里程碑状态流转 |
| `GET /api/members/` | 有效成员列表（id / username / display_name），供选择验收者 |
| `POST /api/auth/register/` | 提交注册申请（公开） |
| `GET /api/admin/registrations/` | 管理员查看注册申请，可按状态筛选 |
| `POST /api/admin/registrations/{id}/approve/` | 管理员通过注册申请 |
| `POST /api/admin/registrations/{id}/reject/` | 管理员拒绝注册申请 |
| `GET /api/admin/users/` | 管理员查看成员列表 |
| `GET /api/missions/{id}/comments/` | 分页查看评论（最新在前） |
| `POST /api/missions/{id}/comments/` | 发表评论 |
| `PATCH /api/comments/{id}/` | 编辑自己的评论 |
| `DELETE /api/comments/{id}/` | 删除自己的评论 |
| `POST /api/library/files/` | 上传文件到自己的素材库（multipart） |
| `GET /api/library/files/` | 分页查看自己的素材 |
| `GET /api/library/files/{id}/` | 经授权下载素材 |
| `DELETE /api/library/files/{id}/` | 删除自己的素材 |
| `GET /api/workspace/overview/` | 只读聚合：工作台「里程碑 × 状态」看板与摘要（含稳定数据修订标识与统计范围） |
| `GET /api/workspace/graph/` | 只读聚合：工作台依赖图节点与有向边（含截断原因与关系完整性标记） |

- 写入 API MUST 校验输入，发起者取自当前用户，不能信任客户端提供的身份字段。
- MUST 实现对象与操作级权限，例如只有发起者能验收、只有认领者能提交。
- 列表可见范围须通过 queryset 过滤；不能假定 DRF 自动对每条列表记录执行对象权限检查。
- 初始版本支持管理员创建成员与自助注册审批两种加入方式；自助注册需管理员批准，默认接口要求登录。
- `/api/admin/*` 要求 `is_staff`；普通成员与匿名请求一律返回 `403`。`POST /api/auth/register/` 对匿名开放，但 MUST 校验 CSRF。
- Session Cookie 使用生产所需的 Secure、HttpOnly 与适当 SameSite 配置。
- POST、PATCH、DELETE 等修改请求 MUST 校验 CSRF；登录入口也必须有 CSRF 保护。
- 权限拒绝返回明确错误；认领冲突、状态冲突或版本冲突使用 `409 Conflict`。
- 现有对象的变更请求 MUST 携带 `expected_version`（创建由服务端初始化版本）；版本过期返回 `409`（`version_conflict`）。缺少 `expected_version` 的写请求返回 `400`。这相对旧客户端是破坏性变更，SPA 已与后端一并升级并携带 `expected_version`。
- Markdown 字段（Mission 的 `content`、`acceptance_criteria` 与评论 `content`）写入时 MUST 校验引用：只允许作者自己的 `/api/library/files/{id}/` 或 `http(s)` 外链，其余返回 `400`（`validation_error`）；校验位于服务层，API 与 Admin 等写入口一致。
- API SHOULD 使用一致的错误结构，例如 `code`、`message`、`field_errors`。
- 默认日期时间以带时区 ISO 8601 格式输出，数据库和后端使用 UTC，前端按显示时区格式化。

## 8. 前端约束

- 使用 Vue 3 单文件组件、Composition API 与 TypeScript。
- 所有 API 调用集中在类型化客户端模块中。
- 默认使用浏览器 fetch；统一处理 CSRF、错误响应、加载状态与会话失效。
- 共享状态确有需求时再添加 Pinia；组件内状态优先保持局部。
- 主要页面：设计与资产（懒加载设计树、关联任务与进度、生产模板与步骤）、任务广场、工作台（里程碑 × 状态概览与甘特图）、我认领的、我发布的、里程碑、素材库、Mission 详情（含评论/讨论区）与任务树；另有注册页与仅管理员可见的管理后台。
- 工作台为只读聚合视图，复用既有写接口；依赖图使用 Vue Flow 渲染，坐标由工作台自研的**甘特日期布局**（`frontend/src/composables/useGanttLayout.ts`：真实日期横轴、独立任务行、未排期区域；`GanttAxis.vue` 绘制日期与目标标记）计算，画布关闭拖线连边、端点重接、节点拖动与删除快捷键，且不在画布上写入任务状态。
- 根据后端提供的状态或操作能力显示按钮，后端仍执行最终权限检查。
- 认领等操作应展示服务器确认后的结果，并明确处理 `409`。
- Markdown 和成果内容的渲染必须处理不可信 HTML，不能直接注入用户输入。
- 初始版本通过操作后刷新与按需轮询同步状态；不假设具有实时协同编辑能力。
- UI 组件库选用 Element Plus（初始化时已确定），避免混用多个组件体系。
- 外观主题复用 Element Plus 官方深色 CSS 变量，通过根元素 `dark` 类切换；自定义页面和图表的背景、文字、边框使用主题变量。主题偏好仅保存在浏览器，首屏在应用加载前恢复，不增加主题依赖或后端接口。

## 9. 第一版基础设施与扩展条件

| 需求 | 第一版 | 增加组件的条件 |
| --- | --- | --- |
| 会话 | Django 数据库 Session | 实测需要缓存或共享会话优化 |
| 通知 | 数据库中的站内通知 | 邮件重试或其他可靠异步任务需要 worker |
| 最新状态 | 操作后刷新、按需轮询 | 明确要求及时推送时评估 SSE |
| 搜索 | PostgreSQL 查询 | 搜索体验或性能有明确缺口 |
| 附件 | 按用户隔离的持久化目录、经授权下载 | 附件规模增长时评估对象存储 |

Redis、后台任务队列、WebSocket、独立搜索服务与 Kubernetes 不属于第一版默认依赖。只有业务需求或测量结果支持时才引入，并记录用途和维护成本。

生产 MUST 使用环境变量或部署侧配置管理密钥，关闭 DEBUG，配置允许的域名；不得提交真实密钥。数据库与附件需要定期备份到服务器之外，并验证恢复流程。Compose 的持久化卷不等于备份。

## 10. Agent 验证与交付要求

后端默认使用 Django 测试框架；并发与事务测试使用适当的事务测试方式、独立连接和 PostgreSQL。前端默认使用 TypeScript 检查、Vitest；关键跨页面流程可使用 Playwright。已有仓库采用其他测试工具时保持一致。

优先覆盖以下行为：

1. 同时认领同一任务只有一个成功，失败方收到冲突响应。
2. 非发起者不能验收，非认领者不能提交；列表不泄露不可见任务。
3. 合法与非法状态流转，包括任务冻结后的修改。
4. 父子任务权限、完成条件、循环检查与并发结构修改。
5. 业务更新失败时回滚，不留下孤立活动记录。
6. Session、CSRF 与前端冲突提示行为。
7. 注册审批：未审批用户不可登录，审批通过后可登录，重复审批返回冲突，非管理员不能访问 `/api/admin/*`。
8. 评论权限：任意成员可评论，非作者不能编辑或删除他人的评论。
9. 多标签查询：多个 `tag` 为 AND（需同时包含），重复参数与逗号写法等价。
10. 素材库：上传的类型/大小校验、经授权下载、非所有者不能删除；Markdown 引用只接受自己的素材与外链，他人素材、站内路径与非 http(s) 协议返回 `400`。
11. 依赖：自依赖、重复、显式环、父子与依赖组合环均被拒绝；跨父依赖允许；阻塞任务可认领但不能提交/验收通过；前置取消仍阻塞、取消子任务不阻塞父任务；前置重开后下游显示阻塞/复核。
12. 优先级与里程碑：默认值与筛选/排序；里程碑受控流转、完成条件（有效任务全 Done）、恢复需原因、只有 Planned/Active 可接收任务、进度与延期。
13. 独立验收与成果：发起者/认领者/验收者可分离，仅当前验收者或管理员验收；转交后旧验收者被拒；每轮成果不可覆盖；重新打开需原因并保留历史，成员失效、祖先完成、里程碑关闭正确处理。
14. 证据引用：非法引用/空 revision/跨提交构建被拒；成功构建与选择验证版本规则；无构建文档任务凭人工说明验收；并发验收、并发环、里程碑完成与加任务互斥。

后端测试、迁移检查、前端类型检查、前端测试和生产构建的命令统一记录在本文第 15 节，规则入口见 `AGENTS.md`。新增或修改脚本时同步更新命令与相关规则；不得把尚未创建的脚本写成可直接运行的命令。

每次交付应说明修改内容、验证结果与未完成事项。不得声称未执行的测试已通过；依赖、迁移或部署配置变化应同步更新相应说明。

## 11. 官方参考

- Django：https://docs.djangoproject.com/
- DRF：https://www.django-rest-framework.org/
- DRF 认证：https://www.django-rest-framework.org/api-guide/authentication/
- DRF 权限：https://www.django-rest-framework.org/api-guide/permissions/
- Vue：https://vuejs.org/guide/quick-start.html
- Vue Flow：https://vueflow.dev/guide/
- PostgreSQL 行锁：https://www.postgresql.org/docs/current/explicit-locking.html
- Caddy：https://caddyserver.com/docs/
- Docker Compose 生产部署：https://docs.docker.com/compose/how-tos/production/

- Mission 日期写入复用原创建/PATCH 和服务事务，结束顺序约束与新增依赖在团队锁内共同校验；不做自动排程。甘特图继续使用 `/api/workspace/graph/`，日/周档位、日期窗口和可访问列表均使用现有 Vue/Element Plus/Vue Flow，不增加图布局或时间管理依赖。

## 12. 站内通知与日期提醒

数据库 `notifications` app 保存站内通知与任务订阅。MUST 与任务事件同事务持久化通知，以 recipient/source_key 唯一约束去重；不使用进程内异步任务承担可靠投递。日期提醒复用团队 advisory lock 后锁任务并重新检查，部署侧 cron 每日运行 `send_mission_reminders`，无需增加队列服务。

通知已读是版本规则的明确幂等例外：只允许当前用户明确选择的 1–100 个 ID，整批归属预检后更新，不要求 expected_version。订阅仍要求乐观锁，首次版本 0。前端个人数据随账户切换卸载，通知失败不阻断任务操作。

## 13. 保存视图与批量写入

保存视图是严格白名单的查询定义，MUST 校验 JSON 形状、枚举、整数用户 ID/UUID 引用和可见范围；相对日期在服务端按 DJANGO_TIME_ZONE 解析。失效引用必须阻止执行，不得删除条件扩大结果。个人视图不提供管理员越权入口。

批量计划更新 MUST 在整体输入校验之后，顺序调用既有 Mission 写服务；每项独立事务，禁止在整个 HTTP 请求外层设置 ATOMIC_REQUESTS 或包裹整批事务。DomainError 逐项报告，未知异常停止。客户端 MUST 检查每项结果，未知网络结果不得自动重试或自动更新版本覆盖。图画布继续只读。

## 14. 设计与资产引用

设计与资产复用 DesignElement 存储但为同级业务对象；MUST 在服务层约束同类型父子结构、同类型无环依赖、Design → Asset 单向多对多引用、Mission 的 Design 单选与 Asset 多选。所有引用写入与归档沿用团队事务锁、权限、乐观锁和审计事件；不得由前端直接写入关联表。生产任务 MUST 保留批次资产引用，设计依据可独立调整。列表序列化预加载资产摘要，筛选与进度使用直接引用，避免多对多连接重复计数。

设计/资产的依赖图 MUST 与父子组成树、Mission 执行依赖分别维护和验环。添加或替换依赖必须在团队锁内检查完整可达路径，防止并发反向依赖成环；数据库兜底禁止自依赖与重复边。

第一批本地适配器锁定 OpenCode CLI 2.1.3，使用 Python 标准库启动独立非交互会话，显式传入专用禁用工具配置。MUST 在本地和服务端重复校验输出，正常服务端测试不得调用付费模型；真实接入测试须显式设置 MYCOLLAB_LIVE_MODEL。服务器仅存 MyCollab 设备凭据摘要，不配置模型、供应商 URL 或供应商认证信息。


主分支使用本地 LLM 整理 Agent 需求 Markdown，MUST 复用有界文本交接，不增加服务器模型 SDK 或执行环境，不将模板拼接当作 LLM 整理。图像/代码执行及审批实现仅保留于 `feature/agent-delegation`；恢复该分支须使用独立数据库，不能假定主分支迁移后的执行历史仍存在。

## 浏览器文件直传约束

- 文件直传使用浏览器原生 WebRTC DataChannel 和 Web Crypto SHA-256；首版单文件最多 100 MiB，页面在线。MUST 在接收端独立校验完整文件大小与 SHA-256，一致后才允许下载和显示成功；发送端排空缓冲不等于成功。
- Django/PostgreSQL 只存有界、短期会话与 SDP，不上传或中转文件。没有 STUN/TURN 配置，不新增 WebSocket、Redis 或后台队列；信令用有限短轮询，过期数据由外部 cron 清理。
- 此会话是 expected_version 规则的明确例外：通过参与者身份、页面凭据、事务行锁、一次性状态转换、不可覆盖 SDP 和幂等终态保证一致性。写入口经 missions/services.py 转交独立 transfers 服务，不改变 Mission 状态。
- 局域网部署 MUST 使用受信任 HTTPS 以支持 Web Crypto；本机 localhost 开发可例外。浏览器/系统局域网权限及 UDP/mDNS 必须可用；不能以普通 HTTP/IP 可访问推定 WebRTC 一定可用。
- 增加 @playwright/test 开发依赖用于真实浏览器验收，无运行时依赖。显式浏览器测试使用独立 PostgreSQL 测试库，Vite 的 MYCOLLAB_TEST_API_TARGET 仅用于将测试代理指向 LiveServer；默认开发代理仍为 127.0.0.1:8000，changeOrigin 保持 false。


## 15. 本地开发与验证操作

本节面向开发者与维护 Agent；用户功能入口见 [README](README.md)，协作教程见 [TUTORIAL](TUTORIAL.md)。

### 本地开发

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

#### 一键启动测试环境

在仓库根目录运行（也支持从其他目录使用脚本绝对路径）：

```bash
./testrun.sh
./testrun.sh --seed  # 可选：创建演示数据，已存在时跳过
```

脚本检查 Python 3.13、Node 24+ 和 Docker Compose；首次缺少虚拟环境或依赖时自动安装，因此首次运行需联网。随后启动根目录 Compose 的 PostgreSQL 并等待就绪，执行迁移和系统检查，同时启动 Django 与 Vite。访问 `http://127.0.0.1:5173`；端口 8000 或 5173 被占用时直接提示退出，不终止已有服务。

使用本地 `127.0.0.1:5432/mycollab` 数据库及本地开发账号配置，保留已有数据，不读取生产部署配置。按 Ctrl+C 停止本次前后端与 LocalRunner 进程，PostgreSQL 容器继续运行；需要时可在根目录手动执行 `docker compose stop db`。前端保留热更新，后端使用 `--noreload` 以可靠清理进程，修改后端代码后需重启脚本。

`./testrun.sh` 在前后端就绪后自动启动 LocalRunner，读取 `~/.config/MyCollab/mycollab-runner.json`；配置缺失时提示并跳过，Runner 退出时提示且保持前后端运行，不自动重启。Ctrl-C 或终止脚本时一并停止本次 Runner，通过 SIGTERM 复用模型进程清理，数据库与数据保留。启动前应确认配置中的服务器地址和设备凭据属于预期环境；Runner 仍使用该配置，不覆盖服务器地址。此启动流程不改变数据模型、接口或权限。

这是供浏览器体验功能的本地环境启动入口；自动化测试仍使用下方“验证命令”。

### 演示数据

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

### 验证命令

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

### 本地 Agent 自动化验证

从仓库根目录运行本地适配器自动化测试，不调用收费模型：

```bash
backend/.venv/bin/python -m unittest discover -s local_runner/tests -v
```

真实闭环测试需本人本机已登录 OpenCode，并明确选择模型。该测试使用独立 PostgreSQL 测试库与临时 HTTP 服务，不修改正常业务数据，但会产生模型调用：

```bash
cd backend
MYCOLLAB_LIVE_MODEL=deepseek/deepseek-flash .venv/bin/python manage.py test agent_bridge.tests.test_live_opencode --noinput
```

### 浏览器文件直传验收

真实浏览器验收使用隔离 PostgreSQL 测试库，不修改业务数据、不调用模型。先在 `frontend/` 执行 `npm ci` 和 `npx playwright install chromium`，然后在 `backend/` 执行：

```bash
MYCOLLAB_BROWSER_TEST=1 POSTGRES_DB=mycollab_browser .venv/bin/python manage.py test transfers.test_browser --noinput
```

已有 Google Chrome 时可增加 `MYCOLLAB_BROWSER_CHANNEL=chrome`，无需下载 Chromium。测试自动启动临时 Django 服务及 localhost:5179 的 Vite，执行 `npm run test:transfer`；该 npm 命令依赖测试服务和测试用户，不作为单独启动应用的命令。覆盖空文件、普通文件、100 MiB 文件下载摘要一致、篡改字节拒收和取消；同机两个独立浏览器会话不能替代实际两台设备的网络环境验收。失败截图/trace 保存在 `frontend/test-results/`，不提交版本库。

若自动验收机器的 mDNS 解析受限，可在上述验收命令中额外设置 `MYCOLLAB_TEST_RAW_IP=1` 进行对照测试：仅让临时 Chrome/Chromium 测试进程使用原始 IP 候选，不修改系统或日常浏览器设置，也不改变应用代码。该模式下通过的结果证明文件传输及校验协议可用，不证明默认 mDNS 或真实跨设备网络可达；实际部署仍需正常浏览器双机验证。

文档重组前已有的本机验收记录（本次未重跑）：Chrome 默认 mDNS 候选未能建立连接，独立 WebRTC 探针也复现该现象；临时测试浏览器启用原始 IP 候选后，6 项真实浏览器测试全部通过（空文件、约 2 MiB、100 MiB、字节篡改拒收、配对后取消、传输中取消）。桌面与 390px 窄屏截图已检查。未修改系统或日常浏览器权限；真实两台设备的默认浏览器环境仍需部署后验证。

## 16. 部署与升级操作

### 生产部署

无域名的局域网 IP 与公网 IP HTTPS 部署，见 [deploy/README.md](deploy/README.md)，包含内部 CA、公共 IP 短期证书、客户端信任和续期流程。

```bash
cd deploy
cp .env.example .env     # 填入 DJANGO_SECRET_KEY、POSTGRES_PASSWORD、DOMAIN 等
docker compose up -d --build
```

Caddy 在同一域名下按 `/api/*`、`/admin/*`、`/static/*`、其余交给 SPA 的顺序处理请求；数据库只在内部网络开放。上传的附件保存在 `media_data` 卷（`/app/media`），Caddy 不提供该目录，下载一律经 `GET /api/library/files/{id}/`。备份、关闭 DEBUG、使用真实密钥等要求见 `TECH_STACK.md` 第 9 节。

#### 站内日期提醒调度

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

### 本地 Agent 历史清理

服务器每天清理一次超过 30 天的辅助历史（沿用部署 cron，无常驻 worker）：

```cron
30 3 * * * cd /opt/MyCollabAdvanced/deploy && docker compose exec -T backend python manage.py cleanup_assistance
```

### Agent 需求文档升级

图像、代码委派和权限审批已保存到本地分支 `feature/agent-delegation`，主分支以需求文档导出替代。

升级仍需执行 `python manage.py migrate`。**本次迁移删除旧图像/代码执行、对话审批、成果提交关联及旧委派请求**，保留 Mission、普通提交正文与素材文件。需要历史数据时先备份数据库；feature 分支保存的是代码，验证旧功能应使用独立数据库。原实现交付时尚未在业务数据库执行该删除迁移；当前部署是否已应用须检查目标环境的迁移记录。

### 文件互传清理

升级后执行后端迁移 `python manage.py migrate`。

每 5 分钟清理过期配对、信令和文件元信息：

```cron
*/5 * * * * cd /opt/MyCollabAdvanced/deploy && docker compose exec -T backend python manage.py cleanup_transfers
```

## 17. 本地 Runner 实现与历史验证

以下记录从 Runner 使用指南迁入，本次文档重组未重新运行这些验证。

### Runner 实现与协议边界

每次调用创建临时目录和专用 `mycollab-text` Agent，以显式配置路径启动 `opencode run --standalone --format json`，经标准输入传递文本，避免需求出现在进程参数中。禁用全部工具权限，并使用 `tool.use` 与 `integration.use` 拒绝策略；不复用用户工作区或已有会话。模型子进程不接收 MyCollab 凭据。此模式禁止读取源码、执行命令、浏览链接、使用 MCP/技能或生成文件。

Runner 不修改用户 OpenCode 全局配置，也不搬运供应商凭据。OpenCode 自身在本机保存的会话和日志受它自己的管理策略控制；不要在输入中包含不希望发送给模型的秘密。管理配置若覆盖了本适配器的限制，不能将该环境视为首批受支持环境，需先核对有效权限。

协议版本为 1，输出校验复用 `backend/agent_bridge/protocol.py` 的纯 Python 模块，不加载 Django。类型、字段、列表数量、体积及依赖图在本地检查，服务器再检查素材引用与业务权限。失败只回传固定错误码，供应商原始异常和日志不会上传。

### Runner 历史验证记录

2026-10-26，本机 Python + OpenCode **2.1.3**，使用本地已登录的 `deepseek/deepseek-flash`。四类虚构测试输入均经真实 CLI 调用返回，并通过共享协议校验；凭据未输出或写入项目。另已通过隔离测试数据库/临时 HTTP 服务中的四项领取、回传与显式业务保存/验收闭环；测试服务器进程禁止外网，本地 OpenCode 子进程独立通信。页面人工采纳逻辑由前端组件测试覆盖，未声称人工浏览器逐页验收。临时文件对抗测试未返回私有哨兵、未创建要求的文件。验收依据必须是输入字段 JSON Pointer 与逐字摘录，两端均校验。

自动化测试无需模型或付费凭据：

```bash
backend/.venv/bin/python -m unittest discover -s local_runner/tests -v
```

官方依据：[OpenCode CLI](https://opencode.ai/docs/cli/)、[V2 配置](https://opencode.ai/v2/docs/config)、[V2 权限](https://opencode.ai/v2/docs/permissions)、[V2 策略](https://opencode.ai/v2/docs/policies)。V1 与 V2 权限字段不同，不能混用。



2026-10-26 真实需求文档验收：`MYCOLLAB_LIVE_MODEL=deepseek/deepseek-flash` 运行 `agent_bridge.tests.test_requirements_live`，浏览器 API 创建请求、真实本地 OpenCode 整理、Bearer 回传、浏览器 API 读取均通过；输出包含 Markdown 章节及 Mission 来源 ID，任务状态与版本未改变。服务端进程限制为本机网络，供应商调用仅在本地 OpenCode 子进程；这不等同于浏览器人工验收。

## 18. 性能测量

性能指标先于技术栈迁移。默认不采集；生产可设置 `MYCOLLAB_PERFORMANCE_SAMPLE_RATE=0.1` 采样 10% API 请求，设为 `1` 全量记录，`0` 关闭。JSON 日志写入标准错误，由部署方收集和轮转；`X-Request-ID` 仅在采样请求返回。SQL 耗时包含锁等待，不能与团队锁耗时相加。流式下载的后续传输不计入请求处理耗时。

后端先迁移，随后可在 `backend/` 执行：

```bash
.venv/bin/python manage.py performance_probe --username alice --iterations 20
.venv/bin/python manage.py agent_metrics --hours 24
```

探针需要已存在的有效用户；可用 `--mission-id UUID` 指定详情任务，空库不测详情。每个端点一次预热后统计 p50/p95、最大 SQL 数和 SQL 中位耗时；并非并发压测。Agent 统计最近 1–720 小时内创建的请求，输出样本数；未出现样本返回 null，不将无数据当成零耗时。运行耗时包含模型及回传，不能当作纯模型速度。

前端在开发/构建时设置 `VITE_PERFORMANCE_METRICS=1`。完成工作台操作后，在浏览器控制台调用 `window.mycollabPerformance.snapshot()` 读取最近 200 条记录，`clear()` 清空。记录只有固定事件名、耗时、图规模与完成状态，不含业务文本；切换页面或刷新会影响样本范围，比较时固定设备、任务规模、日期窗口和筛选。
