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

### 本机性能基线（2026-10-28）

在发布编译结束后，以本机已有演示账号 `alice` 对当前数据库执行 `performance_probe --iterations 20`，每端点预热一次：任务列表 p95 87.995 ms、SQL 最多 69 次；工作台概览 p95 114.484 ms、SQL 最多 74 次；工作台图 p95 117.321 ms、SQL 最多 76 次；任务详情 p95 41.883 ms、SQL 最多 14 次。此为当时数据与设备上的串行服务端基线，不含网络/渲染，不证明 50 人并发容量；后续优先分析列表与工作台查询数，不据此直接重写技术栈。

## 19. Runner 恢复与诊断

本批最初使用 POSIX 本机进程锁；当前 Windows 原生文件锁实现与 CI 结果见后文桌面章节。配置旁 `runner-state/<identity>/` 保存私有待发结果；旧设备/服务器的结果不能跨配置回传。原有“心跳失败立即停止”“回传最多三次后丢弃”的行为由本节替代：仅在已确认租约内短暂容忍断网，持久化结果按原轮次重传。服务器过期后仍拒收，保留期不是租约延长。

```bash
backend/.venv/bin/python -m local_runner --diagnose
backend/.venv/bin/python -m local_runner --status
backend/.venv/bin/python -m unittest discover -s local_runner/tests -v
```

诊断不领取任务、不调用收费模型；CLI 版本通过不代表供应商额度或登录一定有效。空闲领取间隔约 3–10 秒（加 0–1 秒抖动），网络失败退避最多 30 秒。恢复的是结果投递；模型本身不自动重试。待发箱错误或存储耗尽时应修复本机存储，不能通过删除执行记录来假定任务可安全重跑。

Runner 可配置可选 `ca_file` 指向管理员提供的 PEM 根证书；用于内部 CA 的 HTTPS，仍进行证书与主机名校验，不提供跳过验证开关。桌面进程通过 `--parent-pid` 启动 Runner；父进程消失时 Runner 收到 SIGTERM 并清理模型子进程。命令行独立运行不受桌面父进程约束。

## 20. 桌面伴侣构建

macOS 首批使用 Tauri 2，原生层只管理固定 Runner 进程，前端沿用 Vue + Element Plus。独立 Node 依赖在 `desktop/package-lock.json`，Rust 依赖在 `desktop/src-tauri/Cargo.lock`。需要 Xcode Command Line Tools、Rust（依赖要求至少 1.90）、Node 24+、Python 3.13。

从仓库根执行：

```bash
backend/.venv/bin/python -m pip install -r desktop/requirements-build.txt
npm ci --prefix desktop
npm --prefix desktop run sidecar
npm --prefix desktop run build
npm --prefix desktop run test
cargo test --manifest-path desktop/src-tauri/Cargo.toml --features custom-protocol
npm --prefix desktop run tauri -- build --features custom-protocol --bundles app
```

产物位于 `desktop/src-tauri/target/release/bundle/macos/MyCollab Companion.app`。运行时不依赖源码目录或用户 Python，OpenCode 仍由用户安装并认证。当前构建架构取宿主机；本机 Apple Silicon 验收不代表 Intel 或旧版 macOS 已验收。

`npm --prefix desktop run tauri -- dev` 用于界面联调，需先构建 sidecar；`build --debug --features custom-protocol --bundles app` 可生成带本地前端的调试包。只有调试构建支持 `MYCOLLAB_COMPANION_TEST_CONFIG` 指向隔离测试配置，不修改用户 HOME 或默认凭据；发布构建忽略该变量。

验证独立二进制的真实断线恢复与桌面父进程退出（假 CLI，不调用供应商）：

```bash
MYCOLLAB_TEST_RUNNER_BINARY="$PWD/desktop/src-tauri/binaries/mycollab-runner-aarch64-apple-darwin" backend/.venv/bin/python -m unittest local_runner.tests.test_delivery_integration -v
```

Intel 构建将上述后缀改为 `x86_64-apple-darwin`。测试会监听临时 localhost 端口，需要运行环境允许本机网络。

### 对外发行与签名更新

本地验证不要求使用开发者证书；对外分发需维护者配置 Apple Developer ID 签名和公证。更新公钥和固定 HTTPS 端点分别由构建环境的 `MYCOLLAB_UPDATE_PUBLIC_KEY`、`MYCOLLAB_UPDATE_URL` 注入，不能由网页、配置文件或模型结果覆盖。

发布时配置 Tauri `bundle.createUpdaterArtifacts=true`，提供 `TAURI_SIGNING_PRIVATE_KEY`（仅发布环境保管）及相应密码，生成带签名的更新包和版本清单；更新清单需使用实际平台/架构、版本、HTTPS 下载地址与签名。不得将签名私钥提交仓库。本地构建没有发布源时不发起更新请求，界面提示手动安装。

参考：[Tauri sidecar](https://v2.tauri.app/develop/sidecar/)、[原生权限](https://v2.tauri.app/security/capabilities/)、[签名更新](https://v2.tauri.app/plugin/updater/)。

### 本批验证记录（2026-10-28）

- 后端迁移检查与系统检查通过；完整测试 272 项，其中 3 项需显式开启的浏览器/真实模型验收跳过。
- 原 SPA 类型检查、149 项测试和生产构建通过；桌面类型检查、3 项界面测试、5 项 Rust 测试及发布模式打包通过。
- Runner 28 项测试通过；最终 `.app` 内独立 Runner 在临时目录完成两项真实本机 HTTP/进程验收：服务器接受结果后丢失确认再重启仍只调用一次假模型；桌面父进程消失会终止正在运行的假模型。未调用收费供应商。
- 原生窗口已检查配置脱敏、自检、启动、假模型结果回传、停止、单实例、关闭后恢复，以及未配置签名更新源的提示。最终发布包可加载内置页面，Runner 保持停止。未实际开启用户登录启动设置、未进行操作系统重启验收。
- 当前产物为 Apple Silicon macOS 本机版，未做 Developer ID 公证或实际远程更新发布；Intel/其他系统尚未验收。构建存在 Element Plus 主包体积提示，不影响打包；现有前端也有类似提示。

### Electron 迁移与非 GUI 检查

新桌面宿主固定使用 Electron 45.1.0、electron-builder 26.18.0，依赖及锁文件在 `desktop/`，业务前端继续复用 `frontend/`。依据 [Electron 破坏性变更说明](https://www.electronjs.org/docs/latest/breaking-changes)，Electron 44 起最低 macOS 13，打包元数据已明确 `minimumSystemVersion: 13.0`；首批目标 macOS arm64/x64、Windows x64。Windows 具体最低受测系统版本仍待原生 CI/环境验证，不以声明的架构替代实测支持。Electron 自带 Node 与开发用 Node 各自独立。安全升级须同时更新固定版本、锁文件并重新运行边界检查。

`desktop/electron-builder.json` 包含 macOS DMG/ZIP、Windows NSIS 配置，打包时复制 Vue 静态资源到 `resources/frontend`。`scripts/package_electron.mjs` 限制原生平台/架构构建：开发目录包使用临时签名，不自动使用钥匙串的个人开发证书；正式分发命令强制代码签名，发行证书、公证与更新源仍待配置。当前开发包已包含对应架构 Runner，但尚未完成正式发行与 GUI 验收。

在 `desktop/`：

- `npm run electron:check`：主进程、策略、传输与打包脚本的严格 JS 类型检查，以及 preload 语法检查。
- `npm run electron:test`：Node 单元测试，检查实际 preload 固定接口、IPC 来源、路径、外链、局域网权限、CSRF、身份清理、资源流取消和重定向失败，不启动 Electron 窗口。
- `npm run electron:build`：共享 Vue 类型检查与生产构建。
- `npm run electron:pack`：构建本机架构的临时签名目录包，不启动应用；macOS 产物位于 `desktop/build/electron/mac-arm64` 或 `mac` 等 builder 平台目录。
- `npm run electron:dist`：原生架构安装产物，强制签名；需发布环境的证书。公证与发行验收未完成前不能发布。
- `npm run electron:setup`：下载开发运行所需的 Electron 可执行文件，不启动应用。
- `npm run electron:dev`：确保 Electron 已安装后构建并启动 GUI；已获用户授权，可用于当前 GUI 验收。

前期曾暂缓 GUI 测试与验收；当前已恢复授权，实测进展见下方“Electron GUI 隔离验收”。已选择性运行前端 API 和文件传输纯逻辑测试：`npm run test -- src/tests/desktopAuth.spec.ts src/tests/client.spec.ts src/tests/missions.spec.ts src/tests/library.spec.ts src/tests/fileTransferProtocol.spec.ts src/tests/fileTransferController.spec.ts`。这些测试不渲染组件，不替代真实 Electron 会话、系统权限、GUI 或跨系统验证。

2026-10-29 已以临时签名生成 `desktop/build/electron/mac-arm64/MyCollab.app`（约 259 MiB），通过 `codesign --verify --deep --strict`；静态核对 ASAR 内 4 个宿主模块及资源目录的 68 个共享前端文件与当前构建一致。未启动应用，不代表 GUI、登录或 WebRTC 实测通过。

桌面凭据模块使用 Electron 45 的异步 `safeStorage` 接口（[官方说明](https://www.electronjs.org/docs/latest/api/safe-storage)）；主进程已注入系统实现，macOS arm64 的实际系统加密保存和读取已通过下方 GUI 验收；Windows DPAPI 已通过下述原生 CI GUI 验收。当前 Node 测试以独立 AES-GCM 测试适配器验证密文落盘、身份隔离、篡改拒绝、密钥轮换与失败保留旧文件，不调用钥匙串，也不代表 Windows DPAPI/macOS 钥匙串实机验收。`electron:check` 包含该模块的严格类型检查。

Runner 的匿名管道入口由 `local_runner/tests/test_private_handoff.py` 使用真实 Python CLI 子进程检查，覆盖中文/空格路径、有界读取、错误脱敏及不创建明文配置。Python 3.13 的 Runner 测试共 30 项；本轮普通沙箱运行 28 项通过，另 2 项因本机监听权限受限，授权后单独重跑 `local_runner.tests.test_delivery_integration` 通过。所有检查均不涉及 GUI 或真实模型调用。

桌面绑定使用独立内存 `device-probe` Session，只对已配置服务器的固定状态端点发送设备 Bearer，`credentials: omit`、`redirect: error`；不借用业务 Cookie。后端状态接口的身份字段为加法兼容变更，无新增迁移。macOS arm64 的 GUI 绑定交互已通过下方隔离验收，核验逻辑另通过 Node 测试及后端 API 回归验证。


Runner 原生构建与非 GUI 二进制检查（仓库根，使用 Python 3.13）：

```bash
backend/.venv/bin/python desktop/scripts/build_sidecar.py --electron
backend/.venv/bin/python desktop/scripts/check_runner.py desktop/build/runner/mac-arm64/mycollab-runner
```

Windows 使用其 Python 3.13 解释器运行同一构建脚本，将检查路径替换为 `desktop/build/runner/win-x64/mycollab-runner.exe`；Intel macOS 使用 `mac-x64`。验证器创建临时本机 HTTP 服务，仅空领取一次、不执行模型，检查管道配置、中文/空格路径、状态与不落盘令牌，不启动 GUI。

早期本机验证记录（当前结果见下方原生 CI）：Runner 回归 34 项完成，33 项通过，1 项 Windows 原生 ACL 测试在 macOS 上明确跳过；macOS arm64 独立 Runner 构建及上述二进制检查通过。Windows 和 Intel macOS 未实际构建/运行，Windows Job Object 的原生验证和原生 CI 仍待完成。DACL 实现依据 [Microsoft SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)，文件锁依据 [Python msvcrt](https://docs.python.org/3.13/library/msvcrt.html)；不能以 POSIX 测试替代 Windows 验证。


Windows 模型树使用 [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) 的 KILL_ON_JOB_CLOSE；通过挂起创建、Job 分配、主线程恢复保证模型执行前已受控制。非 Windows 的模拟失败测试仅证明不会在分配失败时回退，不替代 `test_child_process.WindowsJobTests` 的 Windows 原生父进程崩溃与孙进程清理测试。

Runner 最新回归共 39 项：37 项通过，Windows 原生 DACL 与 Job 测试 2 项在 macOS 跳过。`check_runner.py` 增加打包后持续运行、停止管道 EOF、退出码和停止状态检查，仍不启动 GUI 或调用模型。

Electron Runner 控制器的非 GUI 子进程测试覆盖就绪、重复启动、启动取消、EOF 停止、自检脱敏与缺失程序；业务传输测试覆盖停止失败时保留会话。打包前必须先运行 `backend/.venv/bin/python desktop/scripts/build_sidecar.py --electron`（仓库根目录），打包脚本拒绝缺少本平台 Runner 的产物；electron-builder 将其复制到 `resources/runner`。`--desktop-events` 仅供私有控制管道，在获得设备锁后输出就绪事件。

### 桌面原生 CI（不启动 GUI）

`.github/workflows/desktop.yml` 配置 PR 路径触发与手动触发，分别使用 `macos-15`（arm64）、`macos-15-intel`（x64）和 `windows-2025`（x64）。标签依据 [GitHub 官方运行器列表](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。每个平台安装锁文件依赖、执行 Electron 类型和边界测试、前端纯逻辑测试、构建原生 Python 3.13 Runner 与 Electron 开发安装包（保留解包目录），再对实际包内 Runner 执行管道及状态检查。macOS 另外检查临时签名完整性。

三个原生目标均执行完整 Runner 非 GUI 测试发现入口；Windows 使用 PyInstaller 构建测试专用假模型 CLI，覆盖结果恢复、取消、文件锁、ACL、Job、凭据交接与停止。只有 POSIX 权限位、进程组、符号链接及 `testrun.sh` 的专属测试按平台跳过，Windows 对应机制由原生测试覆盖。构建后通过 `MYCOLLAB_TEST_RUNNER_BINARY` 对实际 Runner 二进制额外执行结果确认丢失恢复和宿主退出清理。产物以 tar.gz 归档保留可执行权限，保存七天，只作为开发产物，不发布、不安装、不启动窗口、不使用发行密钥。Windows Server CI 不等于 Windows 客户端最低版本验收。用户已授权推送独立分支并创建草稿 PR。提交 `2b32024` 的[三平台原生 CI](https://github.com/5ext9fca/MyCollab/actions/runs/40744537700)已全部通过，三份开发包已归档；不代表正式签名发行或 GUI 验收通过。

旧 macOS 配置导入采用原地复用状态目录与锁的方案，不复制待发箱。新增非 GUI 测试覆盖文件权限、符号链接、有界读取、服务器/用户核验、拒绝覆盖、加密状态标记及固定路径选择；`check_runner.py` 额外尝试竞争启动，验证实际二进制拒绝同状态目录的第二个 Runner。自定义 CA 的旧配置明确拒绝导入，相关信任适配仍待实现。

### Electron 更新与发行构建

更新运行时固定为 `electron-updater 6.8.12`（生产依赖），与现有 electron-builder 26 配套。采用该版本的 `autoDownload = false`、`autoInstallOnAppQuit = false`；不混用 updater 7 的破坏性 API。来源：[electron-builder v26 更新说明](https://www.electron.build/v26/docs/features/auto-update/)。下载完成只表示可进入安装流程，不替代 macOS 原生安装阶段的签名验证。

`electron:pack` 生成更新禁用的开发目录包；`electron:dist:dev` 使用相同的凭据隔离和更新禁用策略生成 macOS DMG/ZIP 或 Windows NSIS 开发安装包，文件名含 `development`，不等于正式签名、公证发行；打包子进程剥离继承的 `CSC_*`、`WIN_CSC_*` 与 `APPLE_*` 发行身份，macOS 明确使用临时签名并禁用公证，Windows 明确关闭签名但保留可执行文件资源编辑，避免本机发行凭据影响开发构建；`electron:dist` 要求发布环境提供 `MYCOLLAB_UPDATE_URL`（以 `/` 结尾的 HTTPS 目录，每个系统/架构使用独立目录）。Windows 另外要求 `MYCOLLAB_UPDATE_PUBLISHER` 匹配签名证书发布者；构建强制代码签名并保持更新签名验证。macOS 正式构建强制签名及公证，证书与公证认证使用 electron-builder 的标准发布环境配置。脚本生成 `build/electron-config.json`，把更新策略写入包元数据，生成匹配的 `app-update.yml`；始终 `--publish never`，不自动上传或发布。

发布负责人需把同次构建的安装包、ZIP、blockmap 与更新清单放到对应固定目录，先传包再传清单；禁止配置跨域 CDN 跳转，更新网络策略会拒绝。当前没有配置真实发布证书、公证身份及更新服务，不能宣称正式签名发行或线上升级已通过。控制器以注入更新适配器运行非 GUI 测试，覆盖停止失败、并发操作、错误脱敏与手动安装边界，不调用原生安装器。

Windows 测试假 CLI 源码为 `local_runner/tests/fixtures/opencode.py`，由 CI 打包后经 `MYCOLLAB_TEST_OPENCODE_BINARY` 指定；该夹具只在测试中使用，不随客户端分发、不调用供应商。路径由 Python 生成原生绝对路径，避免 Git Bash `/d/...` 路径进入 Windows 子进程环境。

`frontend/src/tests/desktopAuth.spec.ts` 是不挂载组件的 Pinia 状态测试，覆盖桌面停止失败时保留身份、成功退出后才重载。桌面传输测试另覆盖权限拒绝与会话过期区分、过期清理顺序及停止失败保护。

独立 Runner 检查脚本另验证 `--diagnose --control-stdin` 在缺少 OpenCode、服务器拒绝设备时可返回 `unavailable` / `unauthorized`，管道保持打开直到自检结束，不领取或执行模型任务。桌面单元测试区分本地自检解析和在线启动核验，并验证会话代次变化使本地缓存失效。

### macOS 正式打包的公证前置检查

`electron:dist` 在调用打包器前必须通过公证配置检查，不能仅依赖 `notarize: true`：当前锁定打包器在未找到凭据时会警告后跳过公证。支持完整的 `APPLE_ID`、`APPLE_APP_SPECIFIC_PASSWORD`、`APPLE_TEAM_ID` 组合，或 `APPLE_API_KEY`、`APPLE_API_KEY_ID`、`APPLE_API_ISSUER` 组合，或 `APPLE_KEYCHAIN_PROFILE`（可选 `APPLE_KEYCHAIN`）。检查按打包器的账户 → API → 钥匙串优先级执行；残缺的高优先级配置直接失败，不回退。不输出凭据值。此检查只证明配置存在，实际凭据有效性及公证成功仍由发行构建验证；开发包不要求这些凭据。

### 手动构建正式发行产物

`.github/workflows/desktop-release.yml` 仅支持手动触发，只允许默认分支；先复用 `desktop.yml` 完成同一提交的三个原生目标非 GUI 验证，再在对应原生运行器重新构建正式安装包。工作流只拥有 `contents: read`，不创建 Release、不上传更新源、不启动安装器或应用窗口。此工作流已随草稿 PR 推送，但尚未配置发行环境、执行或取得正式签名产物，不能把工作流存在视为跨平台发行通过。

发布负责人需预先建立 `desktop-release-mac-arm64`、`desktop-release-mac-x64`、`desktop-release-win-x64` 三个 GitHub Environments，并限制为默认分支；按团队需求配置审批。环境隔离机制见 [GitHub 环境说明](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments)。每个环境设置：

- 变量 `MYCOLLAB_UPDATE_URL`：该平台/架构独立的 HTTPS 更新目录，以 `/` 结尾。
- Windows 变量 `MYCOLLAB_UPDATE_PUBLISHER`：与证书匹配的发布者名称。
- Secret `CSC_LINK`：electron-builder 支持的签名证书（此工作流建议使用导出证书的 base64 内容）；Secret `CSC_KEY_PASSWORD`：对应密码。Windows 需适用于该证书供应商的可导出签名方案；若供应商要求硬件或云签名，必须先接入其方案，不能退回未签名发行。
- 两个 macOS 环境另需 Secrets `APPLE_ID`、`APPLE_APP_SPECIFIC_PASSWORD`、`APPLE_TEAM_ID`，使用 Developer ID Application 签名证书。此工作流使用账户公证方式；本地发行脚本仍支持技术文档上节列出的其他方式。

变量名依据 [electron-builder v26 签名文档](https://www.electron.build/v26/docs/features/code-signing/)。签名与 Apple 凭据仅注入正式打包步骤，不传给依赖安装、普通回归或产物归档。工作流引用环境不会自动配置环境的分支限制或审批，维护者必须在 GitHub 中完成设置。不要把任何真实凭据写入仓库。

正式构建后检查实际包内 Runner；macOS 执行 `codesign --verify --deep --strict`、`xcrun stapler validate` 和 `spctl --assess --type execute`；Windows 使用 `Get-AuthenticodeSignature` 检查应用、Runner 和唯一安装器，必须返回 `Valid`。这些非 GUI 检查不替代首次安装、更新恢复或用户交互验收。

`desktop/scripts/collect_release.py` 只收集顶层安装包（macOS DMG/ZIP、Windows EXE）、对应 `latest*.yml` 与 blockmap，生成 `SHA256SUMS.txt` 和包含提交及目标的 `build-info.json`，不归档整个构建目录或调试配置。缺少安装包/清单、同类型多个安装包或输出目录已有文件时失败，防止混入旧产物。工作流归档保存 14 天；下载同次构建的归档后，仍由发布负责人按前述顺序上传更新服务。测试命令：`backend/.venv/bin/python -m unittest discover -s desktop/scripts -p test_collect_release.py -v`。

页面 Blob 导出与接收文件保存通过 Session 的 `will-download` 和 DownloadItem 交给 Chromium 管理，不开放文件系统 IPC。使用 Electron 45 的下载来源主框架参数校验调用方；保存失败只返回通用提示，不记录路径或正文。依据 [Electron DownloadItem](https://www.electronjs.org/docs/latest/api/download-item) 与 [Session 下载事件](https://www.electronjs.org/docs/latest/api/session#event-will-download)。非 GUI 注入对象测试覆盖来源、身份切换取消、完成清理和中断提示；系统保存对话框、真实 Blob 下载和跨平台磁盘失败尚未进行 GUI 验收。

PR 开发构建在剥离全部发行身份后设置 `CSC_FOR_PULL_REQUEST=true`，仅让 electron-builder 执行命令行固定的 macOS `identity=-` 临时签名；否则工具在 PR 中默认跳过签名，导致打包后的资源封装无法通过完整性检查。此开关不放入正式发行环境，也不向 PR 提供证书或 Apple 凭据。首轮原生 CI 已确认 Windows 全部通过、两个 macOS 在此签名步骤失败；修复后的结果以对应运行记录为准。

2026-10-29 原生 CI 汇总（提交 `2b32024`）：Windows Electron 51 通过/2 项 macOS 专属跳过，Runner 35 通过/4 项 POSIX 专属跳过；两种 macOS 各 Electron 53 通过、Runner 37 通过/2 项 Windows 专属跳过。三平台各前端纯逻辑 29 项、归档脚本 3 项和实际二进制恢复/退出 2 项通过，包内 Runner 检查通过，两种 macOS 开发签名完整性通过。详见[运行记录](https://github.com/5ext9fca/MyCollab/actions/runs/40744537700)；没有执行 GUI、签名发行或实际升级。

开发打包模式只接受 `--dir` 或 `--development` 单一参数，无参数才是正式发行；未知/冲突参数拒绝执行。原生 CI 已切换到 `electron:dist:dev`，只生成安装产物，不运行安装器或应用窗口。开发安装包的系统签名/信任限制不应通过关闭系统安全设置绕过。

安装目标自身的 `arch` 数组会优先于 electron-builder 命令行架构；脚本因此在生成配置时把所有目标限定为当前 `process.arch`，与已检查存在的 Runner 保持一致，禁止在本机顺带生成缺少对应 Runner 的其他架构安装包。macOS arm64 本机开发 DMG/ZIP 已通过构建、DMG 校验和、ZIP 完整性与所需文件检查，未启动应用。

开发安装包原生验证：提交 `04239f0` 的[三平台 CI](https://github.com/5ext9fca/MyCollab/actions/runs/40746830510)全部通过，实际生成 `MyCollab-0.1.0-win-x64-development.exe`、`MyCollab-0.1.0-mac-arm64-development.dmg/.zip` 和 `MyCollab-0.1.0-mac-x64-development.dmg/.zip`，包含于对应平台归档中。两种 macOS 各 54 项桌面测试通过，Windows 52 通过/2 项 macOS 专属跳过；其他既有回归及包内检查通过。未执行安装或 GUI；仓库发行环境列表目前为空，正式签名与更新服务仍需配置。

### Electron GUI 隔离验收

#### 桌面测试的三个入口

桌面环境测试统一位于 `desktop/tests/`，分为本地 macOS、本地 Windows、CI 三类。`shared/` 只存放两种本地入口复用的 Playwright 用例、HTTP 夹具与依赖锁文件；不直接作为第四种环境入口。原有 `desktop/electron/tests/` 边界单元测试和 `local_runner/tests/` 子进程测试保持原位置，供各平台共用。

| 类别 | 入口 | 环境与覆盖 | 报告位置 |
| --- | --- | --- | --- |
| 本地 macOS | `desktop/tests/local-macos/run.mjs` | macOS 原生 Node 24、已安装开发版 `.app`；本机 HTTP 夹具与真实 Electron 宿主 | `desktop/test-results/local-macos/<运行标识>/` |
| 本地 Windows | `desktop/tests/local-windows/run.ps1` | Windows 原生 Node 24、已安装开发版 EXE；同一组本机 HTTP 夹具与宿主用例 | `desktop/test-results/local-windows/<运行标识>/` |
| CI | `.github/workflows/desktop.yml` → `desktop/tests/ci/check_gui.py`，Windows 另调用 `check_windows_install.py` | 原生三平台构建、真实 Django/PostgreSQL、假模型 CLI、包内 Runner；Windows CI 静默安装卸载 | `frontend/test-results/desktop/`、`desktop/build/windows-install-validation.json`，由工作流归档 |

本地套件无需重新打包、不安装 Chromium、不依赖 PostgreSQL 或模型 CLI。服务只监听 `127.0.0.1` 随机端口，提供合成账号、素材和设计树；每用例使用独立 `--user-data-dir`，退出后只清理测试配置。保存对话框选择由测试替换，窗口恢复通过宿主事件触发，不代表原生交互实测。**本地 HTTP 夹具不验证 Django 权限、业务状态机或真实网络互通，不替代 CI 集成验收。**

#### 本地 macOS 测试

在 macOS 仓库根目录执行：

```bash
node desktop/tests/local-macos/run.mjs --app /Applications/MyCollab.app
node desktop/tests/local-macos/run.mjs --app /Applications/MyCollab.app --smoke-only
```

`--app` 接受已安装开发版 `.app` 目录，默认 `/Applications/MyCollab.app`；`--report-root` 可指定报告根目录。入口检查 `darwin` 平台，拒绝在 WSL/Linux/Windows 上伪造 macOS 测试。需要本机 Node 与 npm；不会自动安装或卸载 App、配置钥匙串、调用模型或修改系统自启动。

#### 本地 Windows 测试

Windows PowerShell 中执行（仓库根目录）：

```powershell
& .\desktop\tests\local-windows\run.ps1 -AppPath 'C:\Program Files\MyCollab\MyCollab.exe'
& .\desktop\tests\local-windows\run.ps1 -AppPath 'C:\Program Files\MyCollab\MyCollab.exe' -SmokeOnly
```

脚本兼容 Windows PowerShell 5.1（UTF-8 BOM），要求 Windows Node，`-ReportRoot` 可指定报告根目录。WSL 下调用的是 Windows PowerShell 与 Windows Node，不使用 Linux Electron。若系统策略拒绝 WSL UNC 路径上的未签名脚本，将 `tests` 目录复制到 Windows 本地目录、保留 `local-windows` 与 `shared` 的相对关系后，在原策略下运行：

```powershell
$source = '\\wsl.localhost\FedoraLinux-44\home\hx\MyCollab\desktop\tests'
$localTests = Join-Path $env:TEMP ('mycollab-acceptance-tests-' + [guid]::NewGuid().ToString('N'))
Copy-Item -LiteralPath $source -Destination $localTests -Recurse
& (Join-Path $localTests 'local-windows\run.ps1') -ReportRoot '\\wsl.localhost\FedoraLinux-44\home\hx\MyCollab\desktop\test-results\local-windows'
```

不设置 `ExecutionPolicy Bypass`；本地脚本仍被策略拒绝时由本机管理员处理授权或签名。

本地 Windows 另提供显式真实站点模式：

```powershell
& .\desktop\tests\local-windows\run.ps1 -LiveServer 'https://测试站点根地址' -ReportRoot '.\desktop\test-results\local-windows-live'
```

此模式会在指定站点写入测试数据，须先获得站点测试授权；用户在独立窗口手动登录专用账号，脚本最多等待 5 分钟，不接收聊天密码，不保存 trace、截图或登录状态。`shared/live.config.mjs` 与 `live.spec.mjs` 独立于默认夹具套件，默认运行绝不触发真实站点测试；`LiveServer` 与 `SmokeOnly` 互斥，只接受 HTTPS 根地址，保持证书校验。

登录后由真实页面创建唯一“Windows自动验收”前缀的里程碑、两步依赖模板和资产，实例化两个任务并依次认领/提交/验收，检查里程碑必须手动完成；保存并刷新个人甘特筛选；创建设备，使用不存在的 CLI 路径验证 DPAPI 绑定、自检、包内 Runner 空闲启停、窗口隐藏恢复及退出登录停止。测试不创建辅助请求，不调用模型，不修改已有任务。只读 API 用于复核页面写入结果。`acceptance.json` 分项记录通过/失败和新建数据 ID；这些站点测试数据保留，不自动删除或归档，临时本机配置在退出后删除。真实供应商、网络中断待发箱恢复及进程异常终止仍需独立验收。

2026-10-29 Windows 真实站点模式实际完成上述 6 项检查，全部通过；用户只手动登录一次。另一次只读进程检查确认没有 mycollab-runner 进程残留。夹具基础模式补充 HTTP 503 下载失败、目标为目录导致落盘失败的提示及恢复，11 项通过；完整模式另有 2 项既有问题回归，不将基础模式当作完整通过。

两个本地入口都会将 `shared` 中的测试文件复制到系统临时工具目录，执行 `npm ci --ignore-scripts`、夹具服务测试和 Playwright。报告包含 HTML、JSON、截图、trace、应用可执行文件及 app.asar SHA-256；工具暂存目录保留便于复查。报告仅含测试数据，仍应检查后再分享。默认完整模式保留 `@known-issue` 用例的真实失败；基础模式显式排除这些用例，不等于完整验收通过。

2026-10-29 Windows 11 x64 / Node 24.11.1 既有本机结果：完整套件 11 项中 9 项通过、英文默认文件名和树展开状态 2 项失败；基础模式 9 项通过；HTTP 夹具测试 1 项通过。历史报告保留原 `desktop/test-results/windows/` 路径。新 macOS 本地入口尚需 macOS 实机运行，不能沿用 Windows 或历史 CI 结果宣称通过。

三入口整理后的本机复验：新 Windows 入口完整运行仍为 9 项通过、2 项相同产品失败，报告位于 `desktop/test-results/local-windows/20261029-174840-1f0a525d/`；HTTP 夹具测试通过。macOS 入口仅完成 Node 语法、帮助命令和 Windows 上拒绝执行检查。CI 脚本完成 Python 语法、仓库根路径与工作流引用检查，以及非 CI 环境拒绝执行检查；未触发远端 CI 或本地安装卸载。

本地套件使用 Playwright 的实验性 [Electron API](https://playwright.dev/docs/api/class-electron)；版本或安装包变化后重新验证。真实安装向导、登录启动、卸载、Runner/供应商与双机矩阵按专项验收文档独立执行。

#### CI 测试

CI 专用脚本集中于 `desktop/tests/ci/`，工作流已使用新路径。`check_gui.py` 保留 `CI=true` 环境检查，创建并停止临时 PostgreSQL 集群；调用 `backend/accounts/test_desktop.py`，由其管理隔离测试数据库、媒体目录与假模型夹具，再运行 `frontend/playwright.desktop.config.ts`、`frontend/e2e/desktop*.ts`。业务集成用例保留在前端依赖所在目录，避免复制第二份业务用例或改变模块解析。`check_windows_install.py` 仍只接受 GitHub Windows 临时运行器，不用于本地安装卸载。发布工作流继续复用桌面工作流。

下面保留完整后端集成验收的命令、覆盖和历史记录；本地高级排查可显式运行 Django 隔离命令，但不要伪造 CI 环境变量调用 CI 安装脚本。

#### Django 与完整后端集成验收

当前已恢复 GUI 验收授权，但不执行正式发行。先构建共享前端并安装锁定 Electron：`npm --prefix frontend run build`、`npm --prefix desktop run electron:setup`。在 backend 运行 `MYCOLLAB_DESKTOP_TEST=1 POSTGRES_DB=mycollab_desktop_gui .venv/bin/python manage.py test accounts.test_desktop --noinput`。此入口创建并销毁独立 PostgreSQL 测试库，启动真实 Django LiveServer 和 Electron 窗口；测试引导文件在加载产品宿主前指定临时 userData，不修改产品安全策略、用户配置或模型账号。

`frontend/playwright.desktop.config.ts` 与浏览器文件传输配置分开；截图和 trace 位于 `frontend/test-results/desktop`。普通后端测试跳过此显式 GUI 入口。本机 macOS arm64 已通过服务器设置、登录、导航、刷新和退出流程；其他平台及真实安装产物的 GUI 行为仍需单独验证。此测试不启动 Runner 或调用模型。

素材 GUI 验收已覆盖真实 multipart 上传、缩略图解码、授权读取与下载字节一致、退出拒绝读取、跨账号列表隔离及删除拒绝后保持登录。测试使用临时 MEDIA_ROOT；下载只替换系统保存路径选择，点击、IPC、主进程认证和流式落盘使用实际实现，不代表原生文件对话框验收通过。

桌面业务 GUI 验收新增：通过真实页面发布任务、由发布者认领、提交人工验证说明并验收通过；刷新后读取实际 API 确认状态为 Done，验收记录仍显示。评论发布、编辑后刷新保留、确认删除均通过。本机 macOS arm64 的同一隔离验收同时回归登录、素材与账号隔离；这不替代多用户协作、子任务、其他业务路由或跨系统验收。

本地 Agent GUI 验收使用真实 safeStorage 与 `desktop/build/runner/mac-arm64/mycollab-runner`，覆盖设备创建、加密保存、刷新解密读取、令牌不回显、自检、启动空闲轮询、手动停止、退出登录停止及另一账号绑定隔离。测试设备仅属于独立数据库，配置与密文位于临时 userData；OpenCode 使用不存在的隔离路径，自检应报告不可用，服务器应报告通过。不调用模型，不代表结果采纳、系统登录启动、旧版迁移或 Windows DPAPI 已验收。

跨平台 GUI CI 已接入 `.github/workflows/desktop.yml` 的三个原生目标：构建后安装 Electron 测试运行时，使用 `desktop/tests/ci/check_gui.py` 新建仅监听本机的临时 PostgreSQL 集群，再运行隔离 Django/Electron 验收并保存截图与 trace 七天。macOS 安装 PostgreSQL 16；Windows 使用运行器预装工具（当前为 PostgreSQL 17），不触碰运行器原有数据库目录或服务。测试结束停止临时集群。该新增远端流程尚待实际运行验证；不等同于安装器交互或最低操作系统版本验收。正式发行工作流复用此桌面验证入口，因而也会包含 GUI 验证，但当前不执行正式发行。

窗口生命周期 GUI 补验：Runner 空闲运行期间触发真实 BrowserWindow.close，确认窗口仍存在但已隐藏；重新显示后页面可操作且 Runner 继续等待任务。通过的是关闭隐藏与恢复行为，托盘菜单点击、登录系统后启动和系统休眠恢复仍需独立验收。

桌面直传排查记录：本机两个隔离 Electron 会话在默认 mDNS 候选下完成配对和 offer/answer 交换，但 45 秒内仍停在建立连接、未传输字节；仅为测试进程启用原始 IP 候选后，2 MiB + 7 字节直传、双方 SHA-256 校验、真实 Chromium Blob 下载落盘与磁盘摘要一致均通过。保存位置由测试固定，未验收原生对话框。产品未启用该开关，默认连接问题尚未解决，不能据此宣称默认网络或双机直传已通过。新增直传验收仍在工作区排查，尚未提交到 CI。

修复页面 beforeunload 阻止退出后客户端无法继续退出的问题：原生确认默认停留，取消后恢复退出控制状态并显示窗口，再次确认可正常结束进程。真实 Electron GUI 测试覆盖取消、窗口隐藏/恢复、再次确认退出；对话框选择由测试固定。桌面 54 项回归与严格类型检查通过。

提交 `44666bf` 的[三平台 GUI CI](https://github.com/5ext9fca/MyCollab/actions/runs/40813474508)已全部通过。Windows x64、macOS arm64/x64 均实际运行隔离 Django 与 Electron 窗口，覆盖登录、Mission 发布/认领/提交/验收、评论、素材上传下载及账号隔离、系统 safeStorage 加密保存/刷新读取、原生 Runner 自检/启停/退出停止。三个目标均生成开发安装包并归档截图与 trace。此提交不包含后续关闭隐藏、离开保护修复或尚在排查的直传测试，不代表安装器交互、所有业务路由、真实双机网络与正式发行通过。

桌面注册审批 GUI 已通过：新申请审批前拒绝登录，管理员批准后成员列表立即更新，新成员可登录，普通用户看不到管理入口且直接访问 `/manage` 会返回任务广场。验收修复了批准后成员列表仍使用旧数据的问题。前端 151 项测试、类型检查及构建通过；主题测试同步为加载实际外置 `theme-init.js`，不再假设内联脚本。

桌面业务 GUI 补验已通过：设计条目创建、编辑后刷新显示修订内容；里程碑创建、详情打开后刷新保留目标说明；工作台切换甘特图、保存个人筛选、刷新后恢复甘特视图与保存筛选名称。上述操作均通过真实页面与隔离 Django/PostgreSQL；不代表设计依赖、生产模板实例化、里程碑完整状态变更等所有分支已覆盖。

实际打包应用 GUI 验收：增加 `MYCOLLAB_TEST_APP_BINARY` 指定 App 可执行文件，测试传入临时 `--user-data-dir` 并断言 `app.isPackaged`。macOS arm64 开发目录包已通过核心业务、设计/里程碑/甘特筛选、私有素材、系统加密、包内 Runner、退出保护与注册审批。此验收发现并修复打包 ESM 主入口顶层等待 ready 的启动死锁；源码引导模式未能暴露该问题。三平台 CI 改为 `check_gui.py --app` 启动实际包内应用，远端新结果待确认。既有开发安装包需重新构建，不应再把旧包作为可启动验收通过的产物。直传对照仍使用源码宿主且不能证明默认连接可用；安装器交互尚未覆盖。

GUI 验收入口直接运行 Node/Playwright CLI，避免 npm 包装进程超时后遗留测试。Playwright 总时限 150 秒、首个失败即停止；外层 180 秒。POSIX 独立进程组先发 TERM 让框架清理浏览器，再清理残留测试组；Windows 超时使用指定 PID 的进程树终止。正常打包 App 回归已通过，强制超时与系统原生弹窗仍可能需要检查遗留进程，不能把失败后的数据库清理当成验收成功。

macOS arm64 开发安装产物已重新构建：从新版 DMG 只读挂载并复制 `MyCollab.app` 到 `desktop/build/安装验收 e669779/`，卸载镜像后通过签名完整性及实际 GUI 回归，覆盖包内前端、系统加密与原生 Runner。路径包含中文和空格。当前 DMG/ZIP 位于 `desktop/build/electron/`，哈希与源码提交记录在同目录 `local-validation.json`。此项验证安装副本运行，不代表 Finder 拖放交互、Gatekeeper、公证、其他平台安装器或默认 WebRTC 已通过。

新增 Windows CI 开发安装验收入口 `desktop/tests/ci/check_windows_install.py`：仅允许 GitHub Windows 运行器，使用实际 NSIS `/S /currentuser /D=` 安装到临时中文空格目录，检查 App 与 Runner 后调用打包 GUI 验收，再静默卸载并检查主程序消失。生成 `desktop/build/windows-install-validation.json` 并随 GUI 产物归档。工作流与脚本已通过语法检查，Windows 原生执行结果待 CI 确认；不代表安装向导交互、最低 Windows 客户端版本或正式发行通过。

本地 Agent 结果闭环 GUI 补验已通过：实际 macOS 安装副本内的 Runner 使用隔离假 CLI（固定结果、无供应商调用），重新绑定时留空沿用设备令牌，领取设计润色请求并回传；候选未自动更改表单，用户采纳标题后仍须手动保存，刷新后确认持久化。测试计数文件确认 CLI 仅执行一次。测试复用 Runner 原有跨平台夹具，Windows 使用 CI 已构建的原生假 CLI；本轮新增流程的远端结果尚待确认。


桌面直传诊断入口已独立为 `MYCOLLAB_DESKTOP_TRANSFER_TEST=1`（配合 `MYCOLLAB_DESKTOP_TEST=1` 运行 `accounts.test_desktop`），默认业务 GUI 套件不包含这项尚未通过默认网络验收的测试。可用 `MYCOLLAB_TEST_APP_BINARY` 指定实际安装副本；测试断言打包状态及临时配置目录。macOS arm64 安装副本已在 `MYCOLLAB_TEST_RAW_IP=1` 对照模式完成双会话 2 MiB + 7 字节传输、SHA-256 校验与下载字节验证；仅固定保存路径，未验证原生对话框。默认 mDNS 与真实双机网络仍未验收通过，不将诊断成功作为产品网络验收结论。


本机 GUI 曾因 macOS 密码访问等待手动授权而超时（用户确认）。运行真实 safeStorage 验收前应留意系统弹窗并由用户完成授权；不以关闭系统保护、明文回退或替换加密实现通过验收。超时本身不能证明应用启动死锁。


本地 Runner 自检增加可选 `opencode_error` 固定分类：`not_found`、`permission_denied`、`timeout`、`invalid_output`、`spawn_failed`、`nonzero_exit`、`version_mismatch`。主进程仅在 CLI 未通过时转发允许值；页面将分类显示为路径、权限、超时、安装或版本排错提示。仍只运行 `--version`，不调用模型，不传递异常文本、CLI 输出、设备令牌或供应商信息；账号与服务器隔离规则不变。


桌面生产模板 GUI 补验通过：在实际 macOS arm64 安装副本中创建单步骤生产模板，刷新后重新读取；创建资产并选择模板、预览、生成待认领 Mission，刷新后生产批次及模板版本仍存在且不再提供重复生成入口。本机三项 GUI 测试合计 44.5 秒通过；多步骤依赖与生产任务完整协作仍需继续验收。双机开发验收步骤见 `desktop/ACCEPTANCE.md`，用户已确认有 Windows 实机可配合；实际默认网络矩阵尚未通过，本机默认 mDNS 双会话仍在 45 秒内未建立连接。


macOS arm64 开发安装包已更新至 `dbea94a`，从 DMG 复制的 `desktop/build/安装验收 dbea94a/MyCollab.app` 通过三项 GUI 回归（49.4 秒），包括缺失 CLI 的具体提示与正常 CLI 自检、候选回传和模板实例化。首次等待系统密码访问确认后，用户完成授权，重跑通过。DMG/ZIP 哈希和验收状态已更新至 `desktop/build/electron/local-validation.json`。

GUI 套件新增 `startup-baseline.json`：记录新进程到设置页可见的耗时、系统/架构、Electron/Chromium 版本与 `getAppMetrics()` 各进程内存快照（KB，按 Electron MemoryInfo 定义）。使用临时配置但未清系统磁盘缓存，启用 Playwright 与 trace，不包含 Runner；只用于后续同条件比较，不能视为纯冷启动、稳定空闲或传输峰值验收。JSON 直接落在 GUI 输出目录，随现有 CI 产物归档；本机副本保存在安装验收目录。


版本检查子进程的标准输入改为关闭输入（DEVNULL），不继承桌面宿主持续开启的停止控制管道；模型请求仍使用独立 stdin 管道传递上下文，Windows Job 保护保持不变。新增真实 HTTP/子进程回归：保持宿主控制管道开启，自检应返回 CLI/服务器通过且不产生模型调用；三平台 CI 的独立二进制测试也运行此项。本机 Runner 42 项测试通过（2 项 Windows 专属跳过）。Windows GUI 的最新失败分类是版本检查超时，本项是否解决该阻塞仍待 Windows 原生复验。
