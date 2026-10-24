# 新功能规格：设计关联、资产生产模板与轻量时间规划

本文件已替换原有需求，作为本次功能的实现与验收规格。核对日期：2026-10-25。本文作为实现与验收依据；A/B 已实现并提交，C 已按用户补充要求改造为甘特图。先依据本文件定位并阅读直接涉及的代码，信息不足时再扩大仓库调查范围。

## 1. 目标与借鉴边界

保留单团队 Mission 的「发布 → 认领 → 拆分 → 执行 → 提交 → 验收」，让成员能回答：这个任务服务于什么设计、某项资产还缺哪些生产步骤、依赖链是否赶得上交付日期。

借鉴来源（官方资料，访问日期同上）：

- [HacknPlan Game Design Model](https://hacknplan.com/docs/design-model/game-design-model)：结构化设计条目连接任务和进度。本项目只增加轻量设计树与 Mission 关联。
- [Codecks Project Setup](https://manual.codecks.io/project-setup/)：资产、执行任务和生产步骤相互关联。本项目用生产模板生成普通 Mission，资产不是上传文件，也不是第二套任务状态机。
- [OpenProject Scheduling](https://www.openproject.org/docs/user-guide/gantt-chart/scheduling/)：时间计划与前后置关系一起展示。本项目把现有依赖图改为甘特图，保留原关系与操作，只做手动日期、结束顺序约束与风险提示，不照搬自动排程。

以下字段、权限、接口与交互是适配 MyCollab 的产品决策，不声称与参考产品完全一致，也不接入其 API。

### 1.1 明确不做

不做多项目/多团队、通用 Wiki 平台、实时多人编辑、自定义字段和状态、任意工作流引擎、资源容量和工时核算、预算、Sprint、自动排程、关键路径算法、日历例外、排期基线、通知中心、文件版本仓库或 Git/构建服务自动同步。不新增专用资产审批状态。不引入新的前端组件体系、后台队列或图布局引擎。

## 2. 实施前基线与本次差量

以下为编写规格时核对的实施前基线；本次完成状态见第 10 节：

- Mission 五态、唯一认领者、父子拆分、类型 `Feature/Task/Bug`、优先级、标签已存在。
- `MissionDependency`、组合环校验、派生阻塞已存在。阻塞任务仍可认领，提交与验收通过要求直接前置全部 `Done`、有效直接子任务全部 `Done`。前置取消仍阻塞；子任务取消不计入父任务完成约束。
- `Milestone` 有目标日期、进度和手动完成规则；它不是父任务。Mission 目前没有计划开始/结束日期。
- 独立验收者、成果多轮历史、源码/构建引用、退回、转交与重新打开已存在，不再开发另一套资产成果交付系统。
- `/workspace` 已有「里程碑 × 状态」概览与 Vue Flow 依赖图，支持筛选、上下游、父子折叠、详情抽屉与 URL 复现。依赖线按可见源 Mission 着色、关闭详情清除焦点已实现，原文件所述两项不继续列为待办。
- `/library` 是用户文件库，文件经登录 API 下载、仅所有者可删除；Markdown 写入只能引用归属作者的素材或 http(s) 外链。它不是团队资产生产台账。
- 尚无设计条目模型及关联、生产模板与生成批次、Mission 日期与时间视图。这三项才是本次新增范围。

## 3. 不变的业务基础

1. 所有执行工作仍是 Mission。新增入口不自动认领、不指派负责人、不自动推进状态；生成的任务进入任务广场，成员照常认领。
2. `Open/InProgress/Submitted/Done/Cancelled` 不变；父子关系表达拆分，依赖表达完成前提，设计树表达产品结构，里程碑表达交付归属，四者不得混用。
3. Mission 业务写入统一进入 `backend/missions/services.py`；新增设计、模板、生成动作也在这里提供服务入口，视图与 Admin 不直接改模型。
4. 当前实际接口使用 `expected_version`，包括 Mission PATCH，不能依据早期文字改回 `version` 入参。创建由服务端设初始版本；版本冲突为 `409 version_conflict`，缺失为 `400 validation_error`。
5. Mission 内容、关联与日期仅在 `Open/InProgress` 可编辑，权限沿用发起者或管理员；认领者不因认领获得内容/排期编辑权。依赖维护仍允许发起者、当前认领者或管理员。`Submitted/Done/Cancelled` 不能通过新入口绕过冻结规则。
6. 沿用 Session + CSRF、统一 `{code, message, field_errors}`、`DomainError`、PostgreSQL 事务锁和事件审计。重新打开、取消、验收权限及历史均保持现有行为。

## 4. A：设计条目与 Mission 双向关联

### 4.1 数据模型

在 `backend/missions/models.py` 新增 `DesignElement`：

- `id`：UUID。
- `title`：非空，最多 200 字符；`content`：Markdown，可空。
- `kind`：固定 `Design/Asset`，分别表示设计说明与可交付资产；创建后不可改类型。资产例如角色、武器、关卡、音效，不等同于某个文件。
- `parent`：可空、自引用、`PROTECT`；两种条目均可作为父节点。禁止自引用与祖先环。
- `created_by`：创建者、不可修改；`version`：从 1 开始。
- `archived`：默认 false；`created_at/updated_at`。

Mission 增加可空 `design_element` 外键，`PROTECT`，每个 Mission 最多关联一个主要设计条目；不做多对多。子 Mission 不自动继承，创建表单可预填父任务的关联并允许清空，服务端不隐式补值。跨条目依赖、无关联任务仍合法。

新增 `DesignElementEvent(element, actor, action, payload, created_at)`，记录创建、修改、移动、归档/恢复与模板实例化。Mission 关联变化用 `MissionEvent` 记录新旧 ID；不把关联操作重复写成条目内容更新。

### 4.2 权限、编辑与历史

- 所有有效登录成员可读取、创建；仅条目创建者或管理员可编辑、移动、归档/恢复。提供后端 `allowed_actions`，前端据此显示按钮。
- 所有现有条目写动作携带 `expected_version`，事务中行锁校验并递增版本。树结构变更复用团队 advisory lock，阻止并发移动形成环。
- 归档不级联、不删除关联 Mission、不改变任务状态；仅允许归档没有未归档直接子条目的节点，需自底向上操作。恢复要求父节点未归档；创建/移动不能进入归档节点下。归档后内容冻结，可恢复再编辑。
- 已有任务仍显示归档条目及内容；禁止新建关联到归档条目。允许在 Mission 可编辑且操作者有权限时解除/更换既有关联；无关字段修改不能因保留原归档关联而失败。
- 第一期不提供硬删除、文档分支、差异对比或历史回滚。条目内容是当前设计上下文，更新不覆盖 Mission 验收标准或既有成果，也不自动重开已完成任务。详情展示设计更新时间，验收仍依据 Mission 的冻结内容与提交记录。
- `content` 经 `library/references.py` 校验，素材引用归属按条目创建者判断，与 Mission 作者规则一致；管理员代编辑也不能把他人的素材变成该作者可引用素材。现有素材可被删除，不承诺新增附件永久保留机制。

### 4.3 接口与页面

新增 `/api/design-elements/`：GET 分页列表，POST 创建；`/{id}/` GET 详情、PATCH 更新；`/{id}/events/` GET 分页事件。PATCH 支持 title/content/parent/archived 与 expected_version，一次变更原子执行；不提供 DELETE。

列表支持 `q`（标题/正文）、`kind`、`parent`（UUID 或 `root`）、`archived`（默认 false）。详情包含父节点摘要、祖先路径、版本、操作能力与进度；子节点用分页列表按 parent 加载，不一次返回无限树。

Mission 创建接口新增 `design_element_id`；PATCH 新增同名字段（null 解除），返回 `design_element` 摘要含 id/title/kind/archived。Mission 列表、工作台概览和依赖图增加 `design_element`（UUID 或 `none`）筛选；默认只匹配直接关联，不隐式包含设计后代。

新增 `/design` 与 `/design/:id`，导航「设计与资产」。左侧懒加载树，右侧 Markdown 正文、直属任务、进度、事件；默认只统计直接关联且非 Cancelled 的任务，进度为 Done/有效总数，无有效任务显示「暂无有效任务」。分别显示受阻数与需复核数，不把 100% 当作已验收的资产状态。父子 Mission 分别关联时分别计数，这是任务数比例，不是工时或物理资产完成率；不做递归汇总。

从条目点击「发布 Mission」进入既有创建页并预填关联，操作者仍是任务发起者。Mission 详情页与抽屉增加可跳转的「设计依据」，允许无关联；设计修改不静默同步到 Mission 正文。点击关联任务继续打开现有详情抽屉/详情页，操作后刷新条目进度与任务数据。

## 5. B：资产生产模板

### 5.1 最小模型与模板格式

新增 `ProductionTemplate`：UUID id、name（非空，最多 200 字符）、description（纯文本）、steps（JSON）、created_by、version、archived、created_at/updated_at。有效登录成员可创建和读取，仅创建者或管理员可修改、归档/恢复；使用 expected_version，不提供硬删除。模板变更另记 `ProductionTemplateEvent`（与设计事件相同的 actor/action/payload/created_at 结构）。

`steps` 是 1–30 个步骤的有序数组，每项固定字段：

- `key`：模板内唯一、非空、最多 50 字符，仅字母数字及下划线；修改模板后旧批次保留旧 key。
- `title`（最多 200 字符）、`content`、`acceptance_criteria`：后两项为 Markdown。
- `type`：沿用 Mission 枚举，默认 Task；`priority`：默认 P2；`tags`：现有标签字符串列表。
- `prerequisite_keys`：同一模板内的前置 key 列表，支持分支、汇合和并行。数组顺序只控制展示，不隐式生成依赖。

拒绝未知 key、自依赖、重复边、循环、空标题、超限与未知字段。模板 Markdown 仅允许 http(s) 外链，不允许私人素材链接，避免跨用户实例化绕过引用归属；复用现有解析/协议校验，不用正则替代 Markdown 安全检查。生成后由任务发起者按现有规则补充自己的素材。不支持任意表达式、变量脚本或自动上传。

新增不可变 `ProductionBatch`：UUID id、asset（DesignElement，必须 kind=Asset）、template（PROTECT）、template_version、template_snapshot（名称与完整 steps）、created_by、created_at。新增 `ProductionBatchItem(batch, step_key, mission)`，`(batch, step_key)` 唯一，mission 唯一；保留步骤到任务的稳定映射。批次与条目不随模板归档而消失。

### 5.2 实例化规则

- 在资产详情选择模板，先显示步骤、显式依赖、任务数与可选里程碑；确认后一次生成。不得因进入页面、切换模板或刷新而生成。
- 仅资产创建者或管理员可生成，资产与模板必须未归档。第一期每个资产最多一个生产批次（数据库对 batch.asset 唯一）；重复操作返回 `409 production_already_generated`，前端加载已有批次。追加工作通过普通 Mission 创建，不提供再次批量生成/重置入口。
- 请求必须携带资产 `expected_version` 与 `template_version`，任一过期返回 `409 version_conflict`。事务内先取团队锁，再锁资产/模板、核验版本、权限、状态与里程碑，再生成全部 Mission、依赖、映射与事件。任何失败全部回滚，不遗留部分任务或批次。
- 生成的 Mission：title 为“资产标题 · 步骤标题”（预检拼接后不超过 200 字符，超长提示调整资产或步骤标题，不静默截断）；creator 为操作者，assignee=null，status=Open，reviewer 默认为操作者；design_element 为资产；parent=null。type/priority/tags/content/acceptance_criteria 来自模板快照。
- 可选统一 `milestone_id`，只接受 Planned/Active，未选则为空。生成日期均为空。模板不保存认领者、验收者、里程碑或日期，不复制用户身份和历史状态。
- 每个 prerequisite_key 转为现有 `MissionDependency`，使用同一服务校验和事件入口，不用 bulk_create 绕过状态机；外层事务内维护生成 Mission 的最新版本，避免用初始 version 写多条依赖。资产版本在成功生成后递增并记事件，模板版本不因读取而变化。
- 模板后续修改不回写生成任务；任务后续编辑不修改模板快照。生成步骤仍可按现有权限拆分、退回、取消、增加跨资产依赖，批次映射保持不变；更换 design_element 前必须先检查映射，批次任务不允许解除/改绑资产，返回 `409 production_asset_locked`，避免资产生产页与任务归属分裂。
- 取消阶段并不自动解除下游依赖，必须显式调整现有依赖。所有有效步骤 Done 仅展示进度，不自动完成其他任务或里程碑。

### 5.3 接口与交互

新增 `/api/production-templates/` GET 分页列表、POST 创建；`/{id}/` GET/PATCH；`/{id}/events/` GET 分页事件。列表支持 q/archived，默认未归档。嵌入「设计与资产」的模板管理入口，用表单编辑步骤和前置选择，不新增可视化流程编排器。

新增 `POST /api/design-elements/{id}/instantiate/`，请求 `{template_id, template_version, expected_version, milestone_id?}`；成功 `201` 返回 batch_id、asset_version、template_version 与 `{step_key, mission_id}` 映射。新增 `GET /api/design-elements/{id}/production/`，无批次返回 `{batch: null, items: []}`；有批次返回快照摘要和最多 30 个步骤的 Mission 当前摘要（状态、认领者、阻塞、成果入口）。额外手工关联任务在“其他关联任务”分页展示，不冒充模板步骤。

资产页按模板原顺序展示步骤列表及前置关系，可并行步骤同时显示；操作使用普通 Mission 抽屉，不在资产页手改阶段状态。按钮显示“生成 N 个待认领 Mission”，确认时禁用重复提交，冲突后刷新。链接「查看依赖」进入现有工作台并设置 design_element 筛选，跨资产前置保留上下文提示。

## 6. C：Mission 日期与甘特图

### 6.1 日期与风险规则

Mission 增加 `planned_start_date`、`planned_end_date`，均为可空 DateField；创建/PATCH 使用同名字段。允许两者都空、仅开始、仅结束；两者都有时必须 start <= end（服务校验 + 数据库约束）。日期使用 ISO YYYY-MM-DD；“今天”按 Django settings.TIME_ZONE 解释。它们是人工计划，不是实际工作时间或工时。

只允许 Mission 发起者或管理员在 Open/InProgress 修改，记录 `schedule_changed` 事件（前后日期）并递增 Mission version。任务表单与详情编辑区增加日期；未到开始日不限制认领，逾期不阻止提交/验收，清空日期合法。父子日期不继承、不自动汇总、修改日期不改变里程碑或状态。

后端统一派生以下风险，由列表/详情/工作台复用，不能只在当前画布可见节点上计算：

- `overdue`：status 为 Open/InProgress/Submitted，end 非空且早于今天。
- `dependency_date_conflict_ids`：直接前置 end 与本任务 start 都存在，且前置 end > 本任务 start。允许同日交接，仅为计划冲突，不代表业务依赖已满足；前置 Done 后仍可有计划冲突，不追溯修改计划。
- `beyond_milestone_due`：任务 end 与关联里程碑 due_date 都存在且 end > due_date。
- 日期缺失时不推算风险；前置取消仍按原业务显示阻塞。对 Done/Cancelled 不显示“当前逾期”，日期和已存在的计划冲突可留作历史提示。业务阻塞与日期冲突分别标识。

用户补充决策优先：**修改现有依赖图为甘特图，不新增第三套独立时间视图**。横轴改为日期，任务条表达计划区间，保留父子折叠、上/下游聚焦、源任务线色、里程碑颜色、详情抽屉与只读画布。

**结束顺序是硬约束**：直接前置和本任务都设有 planned_end_date 时，本任务不得早于任一前置结束，允许同日完成与重叠执行。修改任一端日期或新增依赖均须在团队事务锁内校验；延后前置而导致已有下游早于前置也拒绝，返回 409 schedule_dependency_conflict，提示先调整下游。没有结束日期时不猜测日期、不自动补排；实际提交/验收仍要求前置 Done。开始早于前置结束仍只是风险提示，不能混淆为禁止并行开工。

不增加通用 FS/SS/FF/SF 类型配置、时间滞后、假日计算、自动平移下游、父子日期包含约束或拖拽改期。

### 6.2 查询接口与甘特图

将 `/workspace` 的 `view=graph` 直接升级为甘特图，保留原链接、概览、Vue Flow 的平移/缩放/定位/适应视图、源任务线色、满足状态线型、父子折叠、关系等效列表和详情操作。旧的上下分层布局被日期横轴与逐任务行替代；父子层级通过任务标签缩进与折叠控件表达，不再让横轴兼任父子层级。无日期任务显示为“未排期”，仅有一端日期时明确缺失另一端，不伪造时长。

扩展现有 `GET /api/workspace/graph/`，不另造一套任务读写协议：新增 date_from/date_to（同时提供，ISO 日期，范围 1–366 个自然日），默认本地今天前 14 天至后 42 天，meta 返回实际范围与 today。复用现有筛选、上下文、节点/边上限、关系不完整提示与 revision；节点增加日期、风险和里程碑目标日期。日期完整时按窗口相交匹配，单端按该日期匹配，双空纳入未排期；关系上下文仍保留，范围外日期只做裁剪/延伸标注，不移动任务日期。

日期轴提供日/周两档、今天及里程碑目标标记；依赖连线连接双方的结束端，表达“下游不能早于前置完成”，没有结束日期时明确未排期/缺结束日期，线仅说明业务关系。父子折叠后的合并边只表达原始关系汇总，不能把代表父任务日期误认成全部隐藏子任务的排期；显示提示并可展开查看。图中不写状态、不拖拽排期，改期仍在现有任务表单通过 PATCH 完成。

增加同等信息的可访问任务日期列表，带状态、认领者、日期、阻塞与风险，可键盘打开原详情。任务/边截断时明确提示并提供分页列表入口；列表复用 date_from/date_to 与既有筛选，不将一页结果视作完整关系。

revision 包含日期风险所依赖的直接前置日期（即使前置未加载）、里程碑日期与 today；改期、依赖、验收、里程碑改期、跨日与页面重新获得焦点后刷新。筛选、date_from/date_to/zoom/selected 写入 URL；旧慢响应不覆盖新请求。关闭抽屉清除焦点但保留日期范围和视口。新日期约束不能改变原有状态机、取消/重开规则或依赖环校验。

## 7. 实现所需的当前代码结构与数据流

### 7.1 后端现有文件

- `backend/missions/models.py`：Mission、MissionDependency、Milestone、MissionSubmission、SubmissionSourceReference、SubmissionBuildReference、MissionEvent、MilestoneEvent、Comment、Tag，以及本次新增 DesignElement/DesignElementEvent、ProductionTemplate/ProductionTemplateEvent、ProductionBatch/ProductionBatchItem。模型和日期/关联字段放此处，迁移放 `backend/missions/migrations/`。
- `backend/missions/services.py`：`create_mission/update_mission`、`claim_mission/release_mission`、`submit_mission/review_mission`、`reopen_mission/cancel_mission`、`add_dependency/remove_dependency`、里程碑与评论写入口；`derived_state/derived_state_bulk` 和 `allowed_actions` 负责派生信息与操作能力。新增服务在此复用校验，不改成通用 ModelViewSet 写入。
- 同文件 `_acquire_team_lock()` 使用固定 `TEAM_OPS_LOCK_KEY` 的 PostgreSQL 事务级 advisory lock；`_get_locked()` 行锁与 `_check_version()` 实现并发控制。图结构读取/校验前先取团队锁，新增批次与树修改沿用固定锁序。依赖图环检查使用 `_graph_adjacency/_reaches/_assert_edge_allowed`，包含 child → parent 隐含完成边。
- `backend/missions/serializers.py`：输入与列表/详情输出。注意当前创建字段是 reviewer_id/milestone_id，更新字段是 reviewer/milestone；新增字段按本规格统一 design_element_id，不顺带重命名旧字段。
- `backend/missions/views.py`、`urls.py`：DRF 解析、认证与服务调用，已有 missions/comments/milestones 路由；新增设计与模板 ViewSet，但只暴露本规格动作。
- `backend/missions/filters.py`：`apply_mission_filters()` 是分页列表与工作台的共享筛选。新增设计筛选应在此集中实现并去重，不能让列表/图/时间视图各自定义不同语义。
- `backend/missions/workspace.py`：WorkspaceOverviewView、WorkspaceGraphView，输出节点/边、上下文、revision 与截断信息。现有图上限为 200 节点、50 上下文节点、1000 边；甘特图扩展原只读查询入口，复用筛选与摘要序列化，风险计算避免逐任务查询。
- `backend/missions/admin.py`：已有业务模型管理入口；新增模型若注册，写动作调用服务，否则只读，不留下可绕过权限/版本的默认保存入口。
- `backend/library/references.py`：Markdown 引用校验；`library/services.py` 上传/删除，`library/models.py` 的 LibraryFile 保存 owner/file/original_name/content_type/size。无需修改文件归属或下载权限。
- `backend/config/exception_handler.py` 与 `missions/exceptions.py`：错误统一出口；账号由 `backend/accounts/` 管理，继续使用 is_staff 判断管理员。

### 7.2 前端现有文件

- `frontend/src/api/client.ts`：request()/CSRF/错误与 buildQuery；`api/types.ts` 共享类型；`api/missions.ts` 封装任务/依赖/成果/事件接口；`api/milestones.ts` 和 `api/workspace.ts` 封装对应查询。新增 `api/designElements.ts`、`api/productionTemplates.ts`，甘特图接口扩展 workspace.ts，不在组件直接 fetch。
- `frontend/src/router/index.ts` 与 `components/AppLayout.vue`：受登录保护的路由与导航；新增设计路由，模板管理可在设计页子区域完成。
- `views/MissionCreateView.vue`、`views/MissionDetailView.vue`、`components/MissionForm.vue`：关联与日期表单的接入点；`components/MissionDetailDrawer.vue` 提供工作台复用的操作和详情。
- `views/WorkspaceView.vue`：视图切换、筛选、URL、请求代次和抽屉焦点；`components/WorkspaceFilterBar.vue`：共享筛选；改造 `components/DependencyGraph.vue` 与 `MissionGraphNode.vue`，使用甘特日期布局并保留原交互。
- `components/DependencyGraph.vue`、`MissionGraphNode.vue`、`workspace/dto.ts`、`workspace/parentGrouping.ts`、`workspace/dependencyTraversal.ts`：现有依赖图数据映射与折叠；`workspace/edgeColor.ts` 和 `milestoneColor.ts` 分别负责源 Mission 线色与里程碑卡片色；`composables/useGraphLayout.ts` 是自研依赖分层布局。本次将分层坐标替换为甘特日期布局，着色、关系遍历与父子折叠继续复用。
- `components/MarkdownEditor.vue`、`MarkdownContent.vue`、`LibraryPicker.vue`：复用 Markdown 编辑/清洗/素材选择。模板编辑隐藏私人素材插入并给出说明，但安全限制仍须在后端执行。

### 7.3 数据流与现有接口

读取：登录会话 → Vue 页面 → 类型化 API request → DRF 认证/筛选 → ORM 与派生字段 → 序列化 → MarkdownContent/任务卡片/抽屉。写入：表单提交 expected_version → 服务权限、锁、校验 → 原子更新与事件 → 返回新版本 → 刷新相关列表/聚合；409 保留用户输入、提示并刷新服务端版本，不能静默覆盖。

复用接口：`GET/POST /api/missions/`、`GET/PATCH /api/missions/{id}/`，以及 POST `claim/release/submit/review/transfer-review/reopen/cancel`；GET/POST `dependencies/`，DELETE `dependencies/{dependency_id}/?expected_version=...`；GET `submissions/`、`events/`；`/api/milestones/`；GET `/api/workspace/overview/`、`/api/workspace/graph/`。日期与设计关联通过原创建/PATCH 写入，不另造“资产任务完成”接口。

成果仍保存为 MissionSubmission 的独立轮次及源码/构建引用，模板/资产页只展示入口与当前状态，不复制历史记录。验收的 submission_id/current Pending 检查保持现状。

## 8. 迁移、范围控制与实现顺序

1. A：新增设计模型、事件、Mission 可空关联、权限/接口/页面/筛选与测试。旧 Mission 关联默认 null，不根据名称或标签猜测归属。
2. B：新增模板、事件、批次与映射，事务生成和资产步骤页。不要把现有父 Mission 自动转换为资产；不批量修改历史任务。
3. C：新增可空日期、日期约束、风险字段、手动编辑与时间视图。旧 Mission 两日期均为 null，不把 created_at/updated_at/里程碑日期当作计划回填。

每一单元实现并验证后，将实际数据模型、接口、权限、页面、规则并入 PROJECT_STRUCTURE.md；若技术约束描述需调整，同步 TECH_STACK.md（例如现有依赖图改为甘特图），仍保持只读聚合和原写入口。实现通过后按实际状态同步文档。各单元独立提交代码、测试与同步文档，不推送。

## 9. 验收与验证

### 9.1 完整业务样例

创建设计“敌人系统”，下建 Asset“森林守卫”。模板步骤为原画 → 建模；建模后动画与音效并行；动画、音效完成后引擎接入；最后验收测试。生成 6 个 Open、无人认领的 Mission 和 6 条显式依赖，不生成虚构的父 Mission。

美术、动画、程序可分别认领；下游即使已认领，在前置未 Done 时不能提交。任务按既有路径提交成果与人工验收；资产页按任务进度更新、可查看成果轮次；模板编辑不影响已生成任务。设动画结束日晚于接入开始日，显示计划冲突；手动修改合法日期消除冲突，不改变阻塞状态。完成前置后业务阻塞才解除。所有任务完成不自动完成里程碑；某前置重开后沿用现有下游阻塞/复核规则。

### 9.2 必须覆盖的边界

- 设计：普通成员只读他人条目、管理员代编辑、匿名拒绝、并发改版冲突、并发移动防环、归档/恢复树约束、旧关联保留、新关联拒绝、Markdown 越权与危险协议拒绝、无关联旧任务兼容、直接计数不递归。
- 模板：分支汇合、不按数组顺序误建边、30 步上限、未知 key/环拒绝、跨用户私人素材拒绝、两次并发生成仅一个成功、过期版本无写入、模板归档与生成竞态、关闭里程碑与生成竞态、中途失败完整回滚、旧快照不变、生成任务禁止改绑资产、取消前置不自动解锁。
- 日期：空值/单端/同日/反向区间、非法格式、数据库约束、无权限/冻结状态修改、跨日今天更新、里程碑单独改期风险刷新、取消前置、缺日期不猜测、下游前置被筛掉仍有正确风险。
- 页面：原认领/拆分/提交/验收入口正常，日期和设计 URL 可复现，生成预览不写入，提交失败保留输入，旧慢请求不覆盖新筛选，图/时间截断明确提示，抽屉关闭焦点行为保持，空数据与无有效任务不显示 100%。

### 9.3 测试入口与命令

现有后端入口：`backend/missions/tests/test_services.py`、`test_api.py`（生命周期与版本）、`test_dependencies.py`（依赖/组合环）、`test_milestones.py`、`test_submissions.py`、`test_workspace.py`、`test_markdown_references.py`、`test_concurrency.py`、`test_concurrency_features.py`；素材规则另见 `backend/library/tests/test_references.py`。新增 `test_design_elements.py`、`test_production_templates.py`、`test_scheduling.py`，并扩展原并发测试和工作台测试。

现有前端入口：`frontend/src/tests/missions.spec.ts`、`milestones.spec.ts`、`workspace.spec.ts`、`workspaceGraph.integration.spec.ts`、`library.spec.ts`、`client.spec.ts`。新增设计、模板、时间视图测试，保留真实 Vue Flow 挂载回归。

实现后按 README 顺序执行，后端事务/并发测试必须使用 PostgreSQL：

```bash
# 在 backend/ 下
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
.venv/bin/python manage.py test

# 在 frontend/ 下
npm run type-check
npm run test
npm run build
```

交付前核对路径、规则、引用与 git diff，并逐项说明实际验证结果和未完成事项。


## 10. 实现与验收记录

- A 已实现：设计树、Markdown 权限、版本与归档约束、Mission 双向关联、直接进度、分页筛选与页面。提交 `58ec206`；设计边界和并发测试见 `test_design_elements.py`，页面版本冲突保留输入见 `designElements.spec.ts`。
- B 已实现：生产模板校验、不可变批次快照、原子生成普通待认领 Mission、显式分支依赖与原有人工验收。提交 `8546595`；完整六步流程、回滚、竞态与取消/重开见 `test_production_templates.py`，预览无写入与防重复确认见 `productionTemplates.spec.ts`。
- C 已实现：现有依赖画布改为日期甘特图，新增可空日期、结束顺序硬约束、风险、窗口、日/周档位、等效日期列表、结束端连线及原有折叠/聚焦交互。没有新增第三套工作台视图。浏览器日期 URL 导航使旧请求失效；窗口获得焦点刷新数据并保留视口。
- 验证：后端 `makemigrations --check --dry-run`、`check`、全量 183 项测试通过，随后补充设计并发改版测试并执行 `DesignConcurrencyTests` 3 项通过；前端 `type-check`、全量 85 项测试与 `build` 通过。真实 Vue Flow 挂载回归覆盖坐标、结束端与只读交互；`git diff --check` 通过。构建保留原有大于 500 kB 的 chunk 提示。
- 本次只生成迁移文件，未对现有业务数据库执行迁移；部署时按 README 执行 `manage.py migrate`。当前环境没有可用浏览器会话，未完成截图级视觉检查，不把 jsdom 集成测试称为真实浏览器验收。没有推送远端。
