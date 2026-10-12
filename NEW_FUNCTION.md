# NEW_FUNCTION

## 1. 目标、范围与优先级

为现有 Mission 协作系统增加四组高优先级能力，使其适合 50 人以内的游戏开发团队：

1. Mission 类型、依赖关系、阻塞状态。
2. 优先级与目标里程碑。
3. 独立验收者与重新打开。
4. 关联版本控制提交和游戏构建版本。

本文件是供 coding agent 使用的增量需求规格。MUST 为必须实现，SHOULD 为推荐。字段与接口名称为默认约定；已有仓库使用其他命名时保持一致并记录映射。

- 沿用 `TECH_STACK.md` 的 Django + DRF + Vue 3 + TypeScript + PostgreSQL 技术栈和单机部署架构。
- 本文件明确替换旧规则中的“仅发起者验收”和“已完成任务无法重新打开”；其他未提及的规则继续有效。
- 以下细节是本次扩展的默认设计。明确的用户需求优先；已有实现与默认设计有差异时先检查、记录差异，避免静默破坏兼容性。
- 本次交付范围是需求实现；该文档本身不表示已有代码、接口或测试。

### 非目标

本轮不实现独立 Asset 实体、3D 预览、视频逐帧评审、工时统计、资源排班、发布审批、多人同时认领或可配置工作流引擎。

本轮采用手动填写提交与构建引用。Git / Perforce / Unity Version Control Webhook、自动拉取 CI 状态、自动触发构建均为后续集成。不要实现文件存储版本控制、文件锁或构建执行器来替代现有工具。

## 2. 保持的基础规则

- 每个 Mission 至多一个主要认领者和一个父 Mission；标签不自动继承。
- 状态仍为 `Open`、`InProgress`、`Submitted`、`Done`、`Cancelled`。
- 子任务归属与任务依赖是不同关系，必须分别建模。
- 父任务的认领、退出和取消不自动变更子任务的认领者或状态。
- 所有动作由后端检查权限和状态；前端按钮隐藏不能替代授权。
- 状态更新、关联关系更新和活动事件写入应在同一数据库事务内完成。
- 现有认领的原子性、Session / CSRF 和对象可见范围规则继续适用。

## 3. F1：类型、依赖与阻塞

### 3.1 Mission 类型

为 Mission 增加 `type`，默认 `Task`：

| 值 | 含义 | 示例 |
| --- | --- | --- |
| `Feature` | 功能或较大交付目标 | 实现角色 Dash |
| `Task` | 具体执行工作 | 接入 Dash 动画 |
| `Bug` | 已有行为的缺陷 | Dash 结束后输入未恢复 |

- 三种类型复用同一 Mission 模型、认领与状态机。
- 类型不限制父子组合；Bug 也可以拆成多个 Task。
- 发起者或管理员可在 `Open` / `InProgress` 修改类型，记录变更事件。
- 类型不能仅通过 tag 表达，也不能影响任务是否完成的判断。

### 3.2 依赖模型

新增 `MissionDependency`：

| 字段 | 含义 |
| --- | --- |
| `id` | 主键 |
| `mission_id` | 等待前置工作的任务，即 dependent |
| `prerequisite_id` | 必须先完成的任务 |
| `created_by_id` | 添加依赖的用户 |
| `created_at` | 创建时间 |

语义：`mission_id` 依赖 `prerequisite_id`。例如 Dash 测试依赖 Dash 程序和 Dash 动画接入，可保存两条依赖。

- MUST 使用唯一约束禁止重复 `(mission_id, prerequisite_id)`，并禁止自依赖。
- 依赖可以跨父任务，但只能引用同一协作团队内、操作者有权访问的任务。
- MUST 禁止依赖环，并检查依赖与父子完成约束组合后的环；仅检查依赖表自身不足以防止死锁。
- 检查时可把“子任务完成后父任务才能完成”表示为隐含的 `child -> parent` 前置边，和显式 `prerequisite -> dependent` 边一起验证。
- 创建子任务、调整父节点、增加依赖均须保持上述约束。例如子任务依赖祖先任务必须拒绝。
- 发起者或当前认领者可在 `Open` / `InProgress` 添加、移除依赖；管理员具有同等业务操作权限。
- `Submitted` / `Done` / `Cancelled` 不允许直接修改依赖；先按允许的动作返回可编辑状态。

### 3.3 阻塞与操作规则

阻塞是派生信息，不增加 `Blocked` 状态枚举，也不维护需要手动同步的状态字段。

API 返回：

| 字段 | 含义 |
| --- | --- |
| `has_unresolved_prerequisites` | 任一直接前置任务不是 `Done` |
| `is_blocked` | 当前任务处于 Open / InProgress / Submitted 且有未完成前置任务 |
| `blocking_mission_ids` | 可见的、未完成前置任务 ID |
| `unfinished_child_ids` | 尚未完成的有效直接子任务 ID；与依赖阻塞分开表示 |

- 前置任务仅在 `Done` 时满足依赖。前置任务 `Cancelled` 仍阻塞，需要显式移除依赖或改为其他前置任务。
- 父任务的有效子任务排除 `Cancelled` 子任务，沿用旧规则；这与显式依赖的取消处理不同。
- 阻塞任务仍可认领，允许前期准备；禁止提交成果和验收通过。
- 提交和验收通过 MUST 同时检查所有显式前置任务为 Done，以及所有有效直接子任务为 Done。
- 前置任务重新打开后，未完成的下游任务自动显示派生阻塞；不得自动更改其认领者。
- 下游已为 Submitted 时保留提交记录和状态，但禁止验收通过，允许验收者退回。
- 下游已为 Done 时不自动重新打开；显示“前置任务已不满足，需复核”的提示，由有权用户显式重新打开。
- 第一版不实现递归自动推进或自动关闭任务。

### 3.4 验收条件

- 可正确添加、列出和移除跨父任务依赖。
- 自依赖、重复依赖、显式环、父子关系与依赖组合形成的环均被拒绝。
- 前置任务完成、取消、重新打开后，查询结果正确反映阻塞与复核提示。
- 已阻塞任务可以认领，不能提交或验收通过。
- 依赖与子任务的取消处理分别符合约定。

## 4. F2：优先级与目标里程碑

### 4.1 优先级

增加 `priority`，使用固定枚举，默认 `P2`：

| 值 | 含义 |
| --- | --- |
| `P0` | 紧急阻断，如主干无法构建或关键运行崩溃 |
| `P1` | 当前交付的重要工作 |
| `P2` | 普通计划内工作 |
| `P3` | 可延期的改进 |

- 发起者或管理员可在 Open / InProgress 修改；待验收或终态任务需先返回可编辑状态。
- 认领者可以在评论中建议调整，不默认拥有优先级修改权限。
- 优先级不代表状态、依赖或截止日期，不触发自动抢占和重新分配。
- 列表支持按优先级筛选和排序；相同优先级使用创建时间与 ID 保持稳定顺序。

### 4.2 里程碑模型

新增 `Milestone`：

| 字段 | 含义 |
| --- | --- |
| `id` | 主键 |
| `name` | 名称，如“首个可玩版本” |
| `description` | 交付目标 |
| `due_date` | 可空目标日期，使用团队时区解释 |
| `status` | Planned / Active / Completed / Cancelled；默认 Planned |
| `version` | 乐观并发版本号 |
| `created_by_id` | 创建者 |
| `created_at` / `updated_at` | 时间戳 |

Mission 增加可空 `milestone_id`，表示唯一目标里程碑。

- 里程碑是排期维度，不是父 Mission，也不是游戏构建版本。
- 团队成员可创建；里程碑创建者或管理员可编辑并变更状态。
- Mission 发起者或管理员可在 Open / InProgress 调整目标里程碑。
- 父子任务不自动继承里程碑；UI 可提供明确勾选的批量设置操作，但本轮不要求实现。
- 只有 Planned / Active 的里程碑可接收新的或重新分配的任务。
- 受控状态流转为 Planned -> Active、Planned / Active -> Cancelled、Active -> Completed、Completed / Cancelled -> Active；完成前必须满足下述条件，恢复需记录原因。
- 不硬删除有任务关联的里程碑；使用取消状态保留历史。
- 里程碑完成条件：至少一个关联任务，且关联任务全部为 Done 或 Cancelled。必须由创建者或管理员手动确认，不自动完成。
- 有效任务数为 0、仅包含已取消任务的里程碑不能确认为 Completed；可以 Cancelled。
- Completed 里程碑内任务需要重新打开时，先把里程碑恢复为 Active；Cancelled 里程碑同样需恢复后才允许重新打开关联任务。

### 4.3 进度、延期与验收条件

- 进度为直接关联且非 Cancelled 的 Mission 中，Done 数量 / 有效总数；没有有效任务时进度为 null，而不是 100%。
- 父子任务分别关联时按不同任务计数；该指标是任务数比例，不表示工时或实际工作量比例。
- overdue = 已超过目标日期且状态为 Planned / Active；不要将时区差异造成的日期变化误判为延期。
- 里程碑页面显示关联任务、按状态统计、进度、阻塞任务和延期提示。
- 列表支持 type / priority / milestone / blocked / assignee / creator 筛选，并保持分页。
- 旧 Mission 迁移为 Task、P2、无里程碑，不自动推断已有标签的业务含义。

## 5. F3：独立验收者与重新打开

### 5.1 独立验收者

增加 `reviewer_id`。新建时默认发起者，旧任务回填发起者。

- reviewer 必须是本团队有效成员；新任务和新增提交均必须具有验收者。
- 发起者或管理员可在 Open / InProgress 修改验收者，记录历史。
- Submitted 状态允许发起者或管理员执行专用“转交验收”动作，修改 reviewer 并记录原因；不得通过普通 PATCH 修改。
- 当前 reviewer 或管理员可验收通过、退回；发起者只有在同时为 reviewer 或管理员时才能验收。
- 认领者仍为唯一主要执行者；不新增多个 assignee。
- 默认继续允许 assignee = reviewer。独立验收者表示角色可分开，不强制双人审核。
- 当验收者失效或离开团队时，任务显示需重新指定验收者，不得静默改为任意用户或无人验收。
- 本轮使用单人单阶段验收，不实现多级审核。

### 5.2 成果提交与历史

新增 `MissionSubmission`，每次提交创建独立记录：

| 字段 | 含义 |
| --- | --- |
| `id` / `mission_id` | 提交标识与所属 Mission |
| `submitted_by_id` / `submitted_at` | 提交者和时间 |
| `description` | 本次成果与验证说明 |
| `verification_description` | 可空人工验证步骤与结果；没有源码或构建引用时必填 |
| `is_legacy` | 是否由旧数据导入，默认 false，客户端不可设置 |
| `reviewer_id_snapshot` | 提交时的验收者，仅作历史记录 |
| `outcome` | Pending / Accepted / Rejected |
| `reviewed_by_id` / `reviewed_at` | 可空实际验收者与时间 |
| `review_comment` | 验收意见；退回时必填 |

- Mission 保存可空 `current_submission_id`。历史提交按时间列出，不覆盖旧记录。
- 提交者只能是当前认领者。提交后描述与关联证据冻结，退回后重新提交产生新记录。
- 验收权限由 Mission 当前 reviewer 决定，而不是 snapshot。
- 验收请求必须针对当前 Pending 提交，携带 submission ID 和 expected_version，防止验收过期成果。
- 原有 `result` 文本可作为最新成果描述的兼容展示；客户端不可通过修改 result 绕过提交动作。

### 5.3 重新打开

增加 `reopen` 动作：

- 仅限 Done；Cancelled 不通过 reopen 恢复，本轮不增加恢复已取消任务的功能。
- 发起者、当前验收者或管理员可执行，必须提供非空原因。
- 原认领者仍为有效成员时恢复 InProgress；原认领者失效时清空 assignee，恢复 Open。
- 保留全部历史提交与验收，Accepted 表示过去该轮验收通过，不表示当前 Mission 仍完成。
- 清空 current_submission_id，后续提交创建新记录；保留 reviewer，失效时要求重新指定。
- 如果祖先任务已为 Done，必须先从最上层向下显式重新打开相应祖先；不能留下“父任务已完成，子任务进行中”的结构。
- 不自动重新打开依赖它的其他任务；按 F1 展示阻塞或复核提示。
- 必须遵守目标里程碑的恢复规则；失败时不部分改变任务或历史。

### 5.4 验收条件

- 发起者、认领者、验收者可以是三个不同用户，权限正确。
- 非验收者无法通过或退回，管理员操作也记录实际身份。
- 转交验收后只有新验收者或管理员可以处理当前提交。
- 重复验收、过期 submission、过期 version 被拒绝。
- 重新打开必须有原因，保留验收历史，并正确处理成员失效、祖先完成、里程碑关闭与下游依赖。

## 6. F4：关联提交与游戏构建

### 6.1 证据引用

新增不可变的 `SubmissionSourceReference` 和 `SubmissionBuildReference`，均隶属于 MissionSubmission；一轮成果可引用多个提交或构建。

| 对象 | 字段 |
| --- | --- |
| SourceReference | id、submission_id、provider、repository、revision、browse_url（可空） |
| BuildReference | id、submission_id、provider、build_id、platform、source_revision（可空）、artifact_url（可空）、status、verification_note（可空） |

- Source provider 默认支持 Git / Perforce / UVCS / Other；revision 为完整提交标识、changelist 或 changeset 字符串。
- repository 必须提供可辨识的仓库名称或地址；revision 不能为空。
- Build 的 build_id 和 platform 必填；例如 build_id = 2026.10.12.42、platform = Windows。
- Build status 为 Unknown / Pending / Succeeded / Failed，表示构建结果，不表示 QA 验收结果。
- provider 为外部工具名称或标识，不要求配置外部工具账户。
- source_revision 仅说明构建对应的源码版本；手工记录不声称已由外部系统验证。
- 一个 Mission 可以保留多轮提交，同一构建也可用于验证多个 Mission；这些引用不提供文件版本控制功能。

### 6.2 提交与验收规则

- submit 请求可以包含 source_references 和 build_references；后端在同一事务内保存并进入 Submitted。
- 证据必须满足以下之一：至少一个源码引用；至少一个构建引用；提供清楚的人工验证说明。文档类 Task 不被强制要求提供 Build。
- 验收通过时，如果附带构建，至少一个构建必须声明为 Succeeded，并由验收者选择所验证的构建引用。只有失败、等待或未知状态的构建时禁止通过。
- 保存验收者选中的 `verified_build_reference_id`；它必须属于当前提交。没有构建时该字段为空，验收意见必须说明人工验证方式。
- 提交内容有误或构建尚未就绪时先退回，待更新证据后重新提交；不得覆盖已提交证据或旧验收记录。
- 构建成功只表示生成构建成功；不能自动把 Mission 设为 Done，也不代表已经发布。
- URL 限制为 http / https；不保存访问 token、密码或带凭据的仓库地址。
- 后端不自动访问用户填写的 URL。下载授权由外部构建服务负责，UI 明确表示其为外部链接。

### 6.3 验收条件

- 详情页可以定位某轮成果对应的仓库提交、平台、构建 ID、构建结果与验收记录。
- 多次退回和重新提交不会覆盖旧证据，重新打开后旧轮次仍可查看。
- 非法引用、空 revision、跨提交的 verified_build_reference_id 被拒绝。
- 无构建的文档任务可凭人工说明验收；附带构建的任务遵守成功构建与选择验证版本的规则。
- 不需要外部账户凭据即可跑通本轮完整流程。

## 7. 接口与前端增量

保留既有接口，并增加或扩展：

| 接口 | 用途 |
| --- | --- |
| `GET /api/missions/` | 增加 type / priority / milestone / blocked 筛选和 priority 排序 |
| `POST /api/missions/` | 支持 type、priority、reviewer_id、milestone_id |
| `PATCH /api/missions/{id}/` | 按字段权限修改扩展字段；禁止直接改状态和 current_submission_id |
| `GET /api/missions/{id}/dependencies/` | 查询直接前置与直接下游任务 |
| `POST /api/missions/{id}/dependencies/` | 添加前置依赖 |
| `DELETE /api/missions/{id}/dependencies/{dependency_id}/` | 移除该任务的依赖 |
| `POST /api/missions/{id}/submit/` | 描述、验证说明、源码与构建引用 |
| `GET /api/missions/{id}/submissions/` | 分页查询各轮成果与证据 |
| `POST /api/missions/{id}/review/` | 当前 submission_id、decision、comment、verified_build_reference_id |
| `POST /api/missions/{id}/transfer-review/` | 指定新验收者和转交原因 |
| `POST /api/missions/{id}/reopen/` | 原因与 expected_version |
| `GET/POST /api/milestones/` | 列表与创建 |
| `GET/PATCH /api/milestones/{id}/` | 详情和普通字段编辑 |
| `POST /api/milestones/{id}/transition/` | 受控里程碑状态变更 |

所有对现有对象的变更请求应携带 expected_version；旧客户端的兼容策略须明确记录。对象创建由服务端初始化版本。冲突返回 409；输入错误返回 400；无权限返回 403。保持现有 Session 和 CSRF 行为。

前端 MUST 提供：

- 创建与编辑表单中的类型、优先级、验收者、目标里程碑。
- 列表中的类型与优先级标识、里程碑、派生阻塞标签和筛选。
- 详情页独立展示任务树、前置依赖、下游任务、未完成子任务，避免混为同一种关系。
- 阻塞原因、已完成任务的依赖复核提示、验收者失效提示。
- 成果提交表单、每轮证据和验收历史、验收版本选择、重新打开原因输入。
- 里程碑页面和目标日期提示；不实现复杂资源甘特图。
- 操作后刷新相关数据；同时处理 409，不能乐观显示验收或认领成功。

## 8. 事务、权限与兼容性

- 复用既有业务 service 入口，新增依赖、里程碑流转、转交验收、重新打开等专用操作。
- 不引入新后端服务、任务队列、缓存或工作流框架来实现本轮需求。
- 图结构变更与可能改变完成约束的状态操作 MUST 采用一致的并发控制。单团队版本可使用固定键的 PostgreSQL 事务级 advisory lock，在读取约束和写入之前获取。
- 涉及里程碑完成、任务改里程碑和任务重新打开的操作也必须互斥验证，避免检查后集合发生变化。
- 50 人以内第一版可以复用一个团队级事务锁来协调这些写入；只读查询不取锁，锁内不进行外部网络请求。
- 配合对象版本检查，防止并发修改依赖、验收与重新打开覆盖彼此的结果。
- Mission 字段、依赖、提交、验收和转交等变更均递增所属 Mission 的 version；里程碑字段与状态变更递增其 version。版本检查和递增必须与业务写入原子执行。
- 每次操作的事件记录包含实际操作者、动作、对象、原因及必要前后值；不得记录密钥。
- 新引用对象与里程碑详情继承团队及任务可见范围，不能通过新接口绕过原有访问限制。
- 构建引用允许在多个任务中重复；任务依赖不允许重复；两种场景不要误用相同唯一约束。
- 迁移时保留原 Mission ID、关系、状态和成果文本，增加 type = Task、priority = P2、reviewer = creator、milestone = null。
- 对旧 Submitted / Done 的成果使用标记为 legacy 的导入记录保存。没有的源码、构建、验收人和验收时间不能伪造；历史已完成任务不因缺少新证据被自动重新打开。
- 新证据要求适用于迁移后的新提交；旧待验收记录可先退回补充证据，或由验收者提供明确人工验证说明后验收。此兼容分支必须有测试和活动记录。
- 若已有旧版无 version 的客户端，实施过渡策略并说明；不要静默破坏现有调用。
- 更新 TECH_STACK 的规则描述与接口说明以消除旧新规范冲突；本任务文档本身不要求现在修改该文件。

## 9. 实施顺序与完成定义

推荐顺序：

1. 检查现有模型、权限、迁移、测试和 UI；记录与本文件的差异。
2. 扩展 type / priority / reviewer、Milestone 模型与迁移。
3. 实现依赖、派生阻塞与并发约束。
4. 实现独立验收、成果历史与重新打开。
5. 实现源码与构建证据引用、验收版本选择。
6. 完成前端筛选、详情、提交、评审、里程碑页面。
7. 验证迁移、并发、权限和端到端流程，更新规范与操作说明。

必须使用 PostgreSQL 验证至少以下关键场景：

| 场景 | 预期 |
| --- | --- |
| 同时认领同一任务 | 只有一个成功，保留旧行为 |
| 并发增加 A 依赖 B、B 依赖 A | 最多一个成功，图保持无环 |
| 子任务依赖祖先 | 拒绝；组合完成约束无死锁 |
| 添加依赖或子任务与提交/验收并发 | 结果满足状态冻结和完成约束 |
| 前置重新打开与下游验收并发 | 不允许在未满足条件的状态下验收通过；若先验收后重新打开，展示复核提示 |
| 里程碑完成与加入任务/重新打开并发 | 不产生已关闭里程碑中的新增未完成工作 |
| reviewer 与 creator 不同 | 仅当前 reviewer 或管理员验收 |
| 转交后旧 reviewer 提交验收 | 拒绝 |
| 相同 submission 被重复验收 | 只有一次成功 |
| reopen 后重新提交 | 旧验收仍保留，新提交独立 |
| 引用其他 submission 的构建 | 拒绝 |
| 业务操作中途失败 | 状态、关联、成果和事件一起回滚 |
| 旧数据迁移 | 无数据丢失，不虚构证据与审核身份 |

端到端示例：创建“首个可玩版本”里程碑；发布 Dash Feature、程序 Task、动画 Task 与测试 Task；测试 Task 依赖程序和动画 Task；不同成员认领；指定独立验收者；上游完成后提交带成功构建的测试成果；验收者选择构建并通过；重新打开上游，观察下游复核提示和历史保留。

完成定义：四组功能均可通过 UI 与 API 操作；后端权限、状态约束、并发、证据与迁移测试通过；前端类型检查和构建通过；实际验证命令与未完成项如实记录。不以只新增数据库字段或只绘制 UI 作为完成。
