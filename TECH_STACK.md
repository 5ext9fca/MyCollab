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
| 后端 | Python、Django | 业务逻辑、用户体系、ORM、迁移、事务 |
| API | Django REST Framework（DRF） | JSON REST API、输入校验、权限检查 |
| 数据库 | PostgreSQL | 业务数据、约束、索引、并发控制 |
| 身份认证 | Django Session、Cookie、CSRF | 同域浏览器登录与请求认证 |
| 管理界面 | Django Admin + SPA 自建管理后台 | 数据检查、注册审批、成员与标签管理 |
| 应用服务器 | Gunicorn，WSGI 部署 | 运行 Django HTTP 应用 |
| HTTP 入口 | Caddy | HTTPS、静态文件、反向代理 |
| 服务部署 | Docker Compose | 管理 Caddy、应用和数据库 |

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

## 4. 代码组织与业务入口

推荐在同一个仓库中维护以下目录。它们是初始化建议，不表示这些文件已经存在。

| 路径 | 内容 |
| --- | --- |
| `frontend/` | Vue 应用、组件、页面、API 客户端、测试 |
| `backend/config/` | Django settings、URL、WSGI 配置 |
| `backend/common/` | 跨 app 共享的基础模块（如领域异常） |
| `backend/accounts/` | 用户、团队成员、注册审批与认证接口 |
| `backend/missions/` | Mission、标签、权限、状态流转、活动记录 |
| `backend/library/` | 用户素材库：上传、授权下载、Markdown 引用校验 |
| `backend/notifications/` | 有通知需求时添加 |
| `deploy/` | Caddy 与部署配置 |

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
- 成果按轮次保存为不可变的 `MissionSubmission`（含 `source` / `build` 引用与验收结论），历史不被覆盖；旧成果以 `is_legacy` 导入。
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

- 写入 API MUST 校验输入，发起者取自当前用户，不能信任客户端提供的身份字段。
- MUST 实现对象与操作级权限，例如只有发起者能验收、只有认领者能提交。
- 列表可见范围须通过 queryset 过滤；不能假定 DRF 自动对每条列表记录执行对象权限检查。
- 初始版本支持管理员创建成员与自助注册审批两种加入方式；自助注册需管理员批准，默认接口要求登录。
- `/api/admin/*` 要求 `is_staff`；普通成员与匿名请求一律返回 `403`。`POST /api/auth/register/` 对匿名开放，但 MUST 校验 CSRF。
- Session Cookie 使用生产所需的 Secure、HttpOnly 与适当 SameSite 配置。
- POST、PATCH、DELETE 等修改请求 MUST 校验 CSRF；登录入口也必须有 CSRF 保护。
- 权限拒绝返回明确错误；认领冲突、状态冲突或版本冲突使用 `409 Conflict`。
- 现有对象的变更请求 MUST 携带 `expected_version`（创建由服务端初始化版本）；版本过期返回 `409`（`version_conflict`）。缺少 `expected_version` 的写请求返回 `400`。这相对旧客户端是破坏性变更，SPA 已与后端一并升级并携带 `expected_version`。
- Markdown 字段（Mission 的 `content`、`acceptance_criteria`、`result` 与评论 `content`）写入时 MUST 校验引用：只允许作者自己的 `/api/library/files/{id}/` 或 `http(s)` 外链，其余返回 `400`（`validation_error`）；校验位于服务层，API 与 Admin 等写入口一致。
- API SHOULD 使用一致的错误结构，例如 `code`、`message`、`field_errors`。
- 默认日期时间以带时区 ISO 8601 格式输出，数据库和后端使用 UTC，前端按显示时区格式化。

## 8. 前端约束

- 使用 Vue 3 单文件组件、Composition API 与 TypeScript。
- 所有 API 调用集中在类型化客户端模块中。
- 默认使用浏览器 fetch；统一处理 CSRF、错误响应、加载状态与会话失效。
- 共享状态确有需求时再添加 Pinia；组件内状态优先保持局部。
- 主要页面：任务广场、我认领的、我发布的、素材库、Mission 详情（含评论/讨论区）与任务树；另有注册页与仅管理员可见的管理后台。
- 根据后端提供的状态或操作能力显示按钮，后端仍执行最终权限检查。
- 认领等操作应展示服务器确认后的结果，并明确处理 `409`。
- Markdown 和成果内容的渲染必须处理不可信 HTML，不能直接注入用户输入。
- 初始版本通过操作后刷新与按需轮询同步状态；不假设具有实时协同编辑能力。
- UI 组件库选用 Element Plus（初始化时已确定），避免混用多个组件体系。

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

后端测试、迁移检查、前端类型检查、前端测试和生产构建的真实命令已记录在 `README.md` 与 `AGENTS.md`。新增或修改脚本时同步更新这两处；不得把尚未创建的脚本写成可直接运行的命令。

每次交付应说明修改内容、验证结果与未完成事项。不得声称未执行的测试已通过；依赖、迁移或部署配置变化应同步更新相应说明。

## 11. 官方参考

- Django：https://docs.djangoproject.com/
- DRF：https://www.django-rest-framework.org/
- DRF 认证：https://www.django-rest-framework.org/api-guide/authentication/
- DRF 权限：https://www.django-rest-framework.org/api-guide/permissions/
- Vue：https://vuejs.org/guide/quick-start.html
- PostgreSQL 行锁：https://www.postgresql.org/docs/current/explicit-locking.html
- Caddy：https://caddyserver.com/docs/
- Docker Compose 生产部署：https://docs.docker.com/compose/how-tos/production/
