# 新功能规格：个人工作中心、站内通知、保存视图与受控批量操作

实现日期：2026-10-25。本文件覆盖第 1、2 优先级，个人工作中心、站内通知、保存视图和受控批量操作均已实现。业务规则已同步至 PROJECT_STRUCTURE.md，技术约束与日期提醒调度分别同步至 TECH_STACK.md、README.md。以下保留完整功能规格与验收口径。

## 1. 目标与现有能力核对

目标：成员打开一个页面就知道当前需要处理什么；团队可复用常用任务筛选，并安全地一次调整多个任务的计划字段。

已实现、应复用：

- Mission 五态、认领与退出、提交与验收、退回、重新打开；发起者、认领者、验收者分离。
- 个人「我认领的」「我发布的」列表；工作台已有我的任务、待验收、受阻、需复核快捷筛选与 URL 参数复现。
- Mission 列表支持角色、状态、类型、优先级、标签、里程碑、设计条目、生产批次、日期窗口等筛选。
- 派生阻塞、需复核、逾期、日期冲突；里程碑、任务事件、成果多轮历史、评论；单任务字段编辑。
- 工作台概览、只读甘特图、任务详情抽屉；设计与资产、生产模板已实现，不再列为本次待办。

本次已实现：

1. 统一个人工作中心与明确的实时待办分类。
2. 数据库站内通知、任务订阅、已读管理、跨日日期提醒。
3. 数据库持久化的个人/团队保存视图。
4. 批量调整优先级、里程碑、计划日期，逐项权限与版本校验，显式部分成功结果。

不包含：邮件/聊天软件推送、@提及解析、WebSocket/SSE、通用自动化引擎、容量规划、工时、交付趋势报表、代码/构建平台同步、多团队、自定义状态、拖拽排期、自动平移依赖、批量认领/验收/取消/删除。未引入的第三、四优先级不得混入实现。

## 2. 必须保留的业务约束

- 单团队；Mission 阅读对登录成员开放，写权限仍由服务层判断。用户主键是整数，Mission/里程碑/设计条目主键是 UUID，不可混用类型。
- Mission 业务写入全部走 `backend/missions/services.py`；新通知与个人配置写入可以在各自服务模块中，但不得直接更新 Mission。
- 当前实际写接口参数是 `expected_version`，不是旧文字中的 `version`。批量每项也必须携带它。版本过期返回 `409 version_conflict`，缺失/格式错误返回 400。
- Mission 字段编辑仅发起者或管理员可在 Open/InProgress 执行；认领者并不自动拥有改期权限。Submitted/Done/Cancelled 不可被新入口绕过冻结。
- 单任务 PATCH 里程碑字段是 `milestone`；创建接口才是 `milestone_id`。本次批量沿用 PATCH 命名。
- 日期允许双空、单端、同日；严格 ISO 日期；双端开始不得晚于结束。直接前置与下游结束日期都已知时，下游不得早于前置结束；更改任一端都检查，失败为 `409 schedule_dependency_conflict`。
- 提交/验收仍要求前置 Done、有效子任务 Done；取消前置仍阻塞，依赖解除不等于任务可立即提交。
- 保留 PostgreSQL 团队 advisory lock、行锁、事务、事件同事务写入、版本控制与组合环校验。禁止 SQLite 替代事务/并发测试。
- Session + CSRF、统一 `{code, message, field_errors}`、Element Plus、API 集中封装、Markdown 清洗规则不变。

## 3. A：个人工作中心

### 3.1 入口与范围

新增 `/my-work`，导航名「我的工作」；登录后的默认落点改为这里。保留任务广场、`/claimed`、`/published`、工作台和原链接。不覆盖已有登录 redirect 参数。

工作中心由待办分类计数、分页任务列表、站内通知入口组成。任务待办按当前业务状态动态查询，不用未读通知数量代替；阅读通知不移除待办，任务状态变化才影响待办。

固定分类（下列是新增口径）：

- `review` 待我验收：reviewer=当前用户且 status=Submitted。管理员不因此看到全团队待验收，仍可从工作台访问管理范围。
- `returned` 被退回：assignee=当前用户、status=InProgress，且 current_submission 指向的成果 outcome=Rejected。重新提交或重新打开后按当前记录退出分类，不能仅凭任意历史退回事件判断。
- `due_soon` 即将到期：活动状态 Open/InProgress/Submitted，计划结束在今天至今天后 3 个自然日（含边界），且用户是 creator/assignee/reviewer 任一角色。
- `overdue` 已逾期：同样的关联角色与活动状态，计划结束早于今天。
- `unblocked` 依赖已解除：当前用户是 assignee、status=InProgress，至少有一条显式前置且所有直接前置 Done。这是持续的就绪列表，不是事件列表；不保证子任务已完成，列表仍展示未完成子任务提示。删除最后一条依赖的任务不进入此列表，但可收到依赖解除通知。
- `revalidation` 需要复核：现有 needs_dependency_review=true，且当前用户是 creator 或 reviewer。历史已完成成果不自动撤销。

同一任务可出现于多个分类，分类数不得相加声称为独立任务总数。默认分类为待我验收；空分类正常显示空态，允许切换。单分类按 planned_end_date 升序（空值最后）、updated_at 降序、id 稳定排序；分页计数覆盖全部匹配任务，不受工作台图节点上限影响。

### 3.2 接口与数据流

新增 GET `/api/my-work/summary/`，返回 `today`、`counts`（六种分类）、`unread_notification_count`。新增 GET `/api/my-work/missions/?category=review&page=1&page_size=20`，category 必填且严格枚举，返回现有分页结构及 MissionListSerializer 同等字段；未知分类 400。本期不接受客户端覆盖用户身份或额外业务筛选。

用共享查询函数实现分类列表和计数，返回的 today 采用 Django `timezone.localdate()`；前端不自行用浏览器时区猜测截止日。服务端查询和返回风险使用一致的当天基准；页面显示数据获取时间。

任务打开原详情抽屉，生命周期动作复用原接口与 allowed_actions；操作完成刷新列表、分类计数和通知角标。页面重新获得焦点、跨服务端日期后刷新；慢请求不得覆盖新的分类请求。只在页面可见时以约 60 秒间隔刷新摘要，不持续重载展开的表单。

## 4. B：站内通知与订阅

### 4.1 已实现模型

新增 `backend/notifications/` Django app，迁移、服务、API、测试完整注册。

`Notification`：UUID id、recipient（User）、mission（Mission）、actor（User，可空，定时提醒为空）、kind、source_key（非空字符串）、payload（最小纯文本摘要及关联标识）、created_at、read_at（可空）。唯一约束 `(recipient, source_key)`，索引 `(recipient, read_at, created_at)`。不保存完整 Markdown、评论正文或附件内容；读取时附当前任务标题/状态与内部详情链接。通知为历史事实，任务后续状态变化不删除历史通知。

`MissionSubscription`：UUID id、user、mission、mode（Follow/Mute）、version（初始 1）、created_at/updated_at；唯一 `(user, mission)`。缺记录表示默认规则，Follow 表示额外关注，Mute 表示关闭该任务普通动态。

- 默认关联人是当前 creator/assignee/reviewer 去重后的有效成员；其普通动态默认开启。Follow 可让其他成员关注；Mute 关闭普通动态，Follow 恢复开启。
- 与用户职责直接相关的提交待验收、退回、转交给自己的验收、需要复核、日期提醒仍送达，即使 Mute；UI 必须说明「静音普通动态，职责提醒仍保留」。
- 不因阅读、评论自动创建订阅；不回填上线前历史事件，不向停用成员发送新通知，不给操作本人发送由其操作触发的通知。系统日期提醒无 actor，不适用本人排除。
- 管理员不拥有读取/更改他人私人通知或订阅的权限。

### 4.2 事件与接收人

普通动态默认发送给任务当前关联人及 Follow 成员，减去 Mute 和操作者；相同来源对同一用户只产生一条。下列职责接收人与普通接收人合并去重：

- `submitted`：当前 reviewer 为职责接收人。
- `review_rejected`：当前 assignee 为职责接收人；验收通过产生普通动态。
- `review_transferred`：新 reviewer 为职责接收人，原 reviewer 也收到普通转交通知（未静音时）；不能只读取转交后的角色集合而遗漏旧验收者。
- 新建评论产生普通动态；编辑/删除评论本期不再通知，已有通知只显示“新增评论”摘要，删除后不泄露已删除正文。
- 认领、退出、重新打开、取消、优先级/里程碑/日期变化产生普通动态；退出使用变化前后角色并集，避免丢失相关人。通用 updated 事件不与对应细分字段事件重复发信；单次更新可将这三个计划字段合并为一条“计划已调整”通知。
- 前置状态或依赖边变化导致直接下游从“有未完成前置”变为“无未完成前置”，发 `dependency_unblocked` 普通动态；只在真假翻转时发送。取消前置不算解除；移除最后一条未完成依赖可触发。
- 直接下游 Done 任务的 needs_dependency_review 从 false 变 true，发送 `dependency_revalidation`，下游 creator/reviewer 为职责接收人。不得自动重开下游；反复查询不重复发信，复核恢复后再次恶化属于新事件。

依赖派生通知以受影响的下游 Mission 为通知目标，不能只通知被操作的前置任务。比较变更前后的真实直接邻接关系与状态，覆盖验收、重开、加/删依赖等可改变条件的入口；不能依赖当前画布可见范围。不做跨多跳的风险通知推断。

### 4.3 事务与幂等

Mission 服务在业务事务中调用通知服务，将业务变更、事件和应产生的站内通知一起提交/回滚；不使用会丢失持久化保证的进程内异步任务。通知服务不能反向调用 Mission 状态流转，避免循环写入。

来源键必须可稳定重建：例如 `event:<event_id>:<kind>:<target_mission_id>`、`comment:<comment_id>:created`。一个操作产生多个细分事件时选定一个稳定来源，禁止依赖时间戳或随机 UUID 去重。并发重复插入依赖唯一约束安全处理，不能破坏外层事务。可对通知行 bulk_create，但不能借此绕过 Mission 写服务。

日期提醒新增可重复运行命令 `manage.py send_mission_reminders`：

- 用服务器本地今天扫描所有匹配任务，分批处理，不限前端分页；仅当前有效 creator/assignee/reviewer 收到职责提醒，非关联订阅者不接收日期提醒。
- 活动任务 end 在今天至后 3 天发 `due_soon`；end < 今天发 `overdue`。每个截止日期、每个接收人、每种提醒只发送一次，不每日重复轰炸。
- 来源键 `deadline:<mission_id>:<planned_end_date>:<kind>`；用户改期到新日期可产生新提醒，改回已提醒过的日期不再重复。漏跑后按当前日期补发当前适用提醒，不伪造过去每日通知。
- 无日期、Done/Cancelled 不发。扫描后写入前在一致的锁/事务内重新检查日期、状态及接收人，避免并发完成/改期产生过期提醒；锁顺序与 Mission 服务一致。
- 命令报告扫描/新增数量并以非零退出码报告失败。部署提供每天运行一次的可执行调度示例（使用 `deploy/docker-compose.yml` 中的 `backend` 服务名），README 说明配置时区、日志与手动重跑；不能只实现命令而遗漏调度落地说明。

本期无需 Redis/Celery；使用现有数据库与部署侧 cron/systemd timer。通知已读操作和订阅变更不会递增 Mission version，也不产生新的任务动态。

### 4.4 接口、权限与页面

- GET `/api/notifications/?read=all|unread|read&page=...`，默认 all，按 created_at/id 倒序，标准分页；GET `/api/notifications/summary/` 返回当前用户 unread_count。
- POST `/api/notifications/read/` 接受 `{ids: [UUID, ...]}`，1–100 个唯一 ID，仅批量标记自己通知已读；验证全部归属后原子更新，重复标记幂等，返回 changed_count。出现他人/不存在 ID 统一 404，全部不写。不提供无边界“全部标为已读”。
- GET `/api/missions/{id}/subscription/` 返回本人显式记录（无记录时 null）、effective_following、mandatory_reminders=true。
- PUT 同一路径接受 `{mode, expected_version}`；首次创建 expected_version=0，随后使用记录当前版本，原子校验唯一键并递增；并发首次设置一方成功，其余 409。不提供客户端 user 字段。
- 所有通知与订阅写操作走对应 services，Session+CSRF；已读动作是明确的幂等例外，无需 expected_version，订阅仍需版本。

新增 `/notifications` 收件箱与顶部未读角标，可切换全部/未读/已读；仅查看列表不标已读，点击通知或批量选中后显式调用已读 API。可用键盘打开关联任务；标记已读失败显示错误，不伪造已读成功。无权访问/目标不可用时给明确提示。

任务详情与抽屉提供关注/静音开关；需显示职责提醒不可静音的语义。通知与任务加载分离，通知接口失败不阻断原任务操作；重登/切换账户清空所有用户相关前端缓存。

## 5. C：保存视图

### 5.1 模型与权限

新增 `SavedMissionView`（建议放在 missions app）：UUID id、name（去首尾空格后 1–100 字符）、owner、visibility（Private/Team，默认 Private）、target（List/Overview/Gantt）、definition（JSON）、version（初始 1）、created_at/updated_at。

- 所有人可创建，owner 固定为当前用户。个人视图仅 owner 可读写删除；管理员不例外。团队视图全员可读，仅 owner 或管理员可修改/删除。
- 创建团队视图须显式选择，默认不公开；同一 owner 内名称唯一，不同 owner 可以同名，列表显示作者与可见范围。
- PATCH/DELETE 必须 expected_version，事务锁校验；冲突不覆盖输入。不允许通过 owner 字段转让所有权。
- 共享定义只共享查询，不保存结果快照、不授予额外任务权限；`me` 始终解释为当前打开者，不是创建者。

### 5.2 定义与校验

`definition` 固定为 `{filters, ordering, date_window, zoom}`，四项按 target 校验。无分页、无选中任务、无抽屉焦点、无平移坐标、无父子折叠状态；禁止任意 URL、SQL、脚本或 JSON 表达式。

filters 白名单：q、status、type、priority、tag（字符串数组，AND 语义）、creator、assignee、reviewer、parent、milestone、design_element、production_batch、blocked、revalidation。统一使用 q 保存文本查询，加载 List 时映射到已有 q/search 能力；重复标签去重。枚举、布尔、整数用户 ID、UUID 和现有 me/none/root 特殊值按各字段含义校验，不使用“未知值忽略”策略。角色整数筛选需修正现有 filters.py 中将非 me 角色 ID 按 UUID 解析的问题，并增加回归。

ordering 白名单沿用现有 created_at/updated_at/title/status/priority/type 及其负号倒序；target 非 List 时不承诺影响现有工作台分组。zoom 仅 Gantt 可选 day/week，与现有页面值一致。

date_window 支持：

- null：List/Overview 不限制日期；Gantt 使用原默认窗口。
- `{mode: "absolute", date_from, date_to}`：沿用现有 1–366 天与完整/单端/未排期匹配语义。
- `{mode: "relative", preset: "this_week"|"next_7_days"}`：this_week 为本地周一到周日，next_7_days 为今天到后 6 天；每次打开由服务端按今天解析，不能保存一次计算后的过期日期。

日期窗口仍是计划区间匹配，包含原规则中的未排期任务，UI 标明“计划窗口（含未排期）”；不能将它表述成严格“截止日在本周”。保存视图的相对日期解析统一在服务端执行。

创建/修改时验证引用对象存在，且用户可读；已有视图引用对象失效时保留定义并返回可读警告，禁止悄悄丢弃条件扩大结果。不能执行的定义阻止打开并提示修复；空结果不等同于非法定义。引用关闭里程碑、归档设计条目用于历史查询合法。

### 5.3 API 与前端

新增 GET/POST `/api/saved-views/`（分页，可按 visibility 筛选，仅返回自己 Private 与全员 Team），GET/PATCH/DELETE `/{id}/`。DELETE 的 expected_version 使用查询参数，成功 204；POST 成功 201，更新成功 200。

新增 GET `/{id}/resolve/`，返回 target、规范化可执行 query、today、warnings；每次打开重新解析日期和 me。不可执行返回统一 400 与字段错误；不可见 ID 返回 404。不得把定义中的任意字符串拼成跳转 URL，前端只按 target 映射到固定站内路由。

任务广场、工作台增加保存/打开/管理视图入口：保存当前筛选，选择名称与个人/团队；打开后恢复筛选、目标视图与日期，重置页码和选择；后续手动调整只影响当前页面，必须显式“更新视图”才写数据库。当前页面可显示“已修改”；提供另存为，不自动写回共享定义。

目标为 List 使用 `/missions`，Overview 使用 `/workspace?view=overview`，Gantt 继续 `/workspace?view=graph`。前端保留常用筛选控件，并通过 MissionQueryForm.vue 补齐全部白名单参数；SavedViewsBar.vue 显示可移除的生效条件摘要，不存在生效但不可见的过滤条件。

## 6. D：受控批量操作

### 6.1 范围与输入

在分页任务列表增加多选与批量编辑入口（任务广场、个人工作中心及 List 保存视图）；工作台甘特图保持只读，不在画布直接批改。首期只选择当前页，翻页/换分类/换筛选/打开保存视图清空选择；不提供“选中全部匹配结果”。最多 50 个唯一任务。

新增 POST `/api/missions/bulk-update/`：

```json
{
  "items": [
    {"id": "任务 UUID", "expected_version": 3}
  ],
  "changes": {
    "priority": "P1",
    "milestone": null,
    "planned_start_date": "2026-11-01",
    "planned_end_date": "2026-11-05"
  }
}
```

items 必须 1–50 项、ID 唯一、版本正整数；changes 至少一个字段，严格白名单仅 priority/milestone/planned_start_date/planned_end_date。省略表示保持原值；里程碑/日期 null 表示显式清空；priority 不允许 null。不接受 status/assignee/reviewer/parent/tags/design_element、其他字段或客户端 actor。一次统一设置所选任务的字段，不做日期偏移或逐任务不同 changes。

### 6.2 执行语义：逐项提交，允许部分成功

- 请求外形、未知字段、非法日期字面值、枚举、重复 ID 等整体输入问题返回 400，任何任务都不修改。
- 输入合法后按 items 原顺序逐项调用 `services.update_mission`；每项独立事务，重用权限、expected_version、冻结、里程碑可接收状态与双向日期依赖检查。不能为整个请求包一层事务，不并行抢团队锁。
- 每个成功项立即提交任务、现有事件和通知；该项失败则全部回滚，但已成功项保留。预期 DomainError 转成逐项结果；未知程序/数据库异常不得伪装为业务失败继续执行。
- 无权限、任务不存在、版本过期、冻结、关闭里程碑、日期冲突分别给真实错误。对不可见对象按现有读权限处理，不泄露额外信息。管理员也不能绕过状态/日期约束。
- 日期按每项执行时的真实数据库状态检查，不做整个选择集的最终排程推演。例如延后前置可能因下游尚未改期而失败；本期明确提示先调整下游再重试。不得为了提高成功率暂时写入违规中间状态或自动改动未选中的任务。
- 即使新值与当前值相同也沿用单任务服务的版本行为，不另造跳过语义；通知只针对实际字段变化生成。

只要请求结构合法且处理完成，HTTP 200，返回 `{results, succeeded_count, failed_count}`，每项包含 id、success、status；成功附最新 Mission 摘要/version，失败附 `{code,message,field_errors}`。全部逐项失败也返回 200，前端必须检查结果而非只看 HTTP 状态。整体认证/CSRF/格式错误仍走原 HTTP 错误结构。

### 6.3 用户确认、重试与审计

提交前展示选中数量、任务标题、准备修改的字段、保持/清空/设值三种含义，明确“逐项执行，可能部分成功”；预览仅基于当前读取数据，不写入、不保证最终通过。表单不得用默认空值误清空未勾选字段。

确认后禁用重复点击；完成后逐项呈现成功与失败、原因和详情入口。成功项取消选择，失败项保留供修正；刷新任务版本、风险、工作台关联数据及通知角标。

失败重试仅提交用户明确确认的失败项；版本冲突先刷新并展示新数据，再确认，不能自动换新版本覆盖。网络中断/500 视为结果不确定，提示已有部分可能成功，重新读取全部涉及任务后再决定；禁止静默重发整个批次。首期不做可恢复批量作业队列或自动重试。

每个任务沿用现有 priority_changed/milestone_changed/schedule_changed/updated 事件及真实 actor，不新增绕过审计的 bulk SQL。批量修改后普通动态通知按每个实际变更的 Mission 生成并去重。

## 7. 已核对的项目结构与前后端数据流

### 7.1 现有后端文件

- `backend/missions/models.py`：Mission 含 creator/assignee/reviewer/status/version、priority、milestone、计划日期；MissionDependency 表示显式前置；MissionSubmission 的 outcome/current_submission 支持识别当前退回；MissionEvent 含 actor/action/payload/time。Comment 当前没有对应的 MissionEvent 新评论动作，通知不能假定现成评论事件存在。
- `backend/missions/services.py`：update_mission、submit_mission、review_mission、transfer_review、reopen_mission、claim/release/cancel、add/remove_dependency、create/update/delete_comment；_acquire_team_lock、_check_version、_record_event；derived_state/derived_state_bulk 与 schedule_risks_bulk。核心计划写入和所有通知触发入口位于这里。
- `backend/missions/filters.py`：apply_mission_filters，任务列表与工作台复用；多标签 AND，角色 me，依赖 blocked/revalidation，设计/生产批次及日期筛选。本次已将角色具体 ID 修正为整数解析，并增加回归测试。
- `backend/missions/scheduling.py`：日期窗口校验与区间匹配；`workspace.py`：概览与图读模型，图限 200 节点、50 上下文、1000 边，不能拿图返回内容计算全量个人待办。
- `backend/missions/views.py`、`serializers.py`、`urls.py`：DRF 入口、输入校验、MissionListSerializer/DetailSerializer、现有 router 与 workspace 路由。Mission PATCH 使用 milestone/reviewer，创建使用 milestone_id/reviewer_id；避免接口字段猜测。
- `backend/accounts/models.py`：User 继承 AbstractUser、整数 ID、is_staff 管理员、is_active；注册审批为独立表。`backend/config/settings.py` 注册 app、认证与时区；`config/urls.py` 挂载 API。
- `backend/config/pagination.py`：默认 20、page_size 最大 100、count/next/previous/results 标准分页。`backend/common/permissions.py` 与 `missions/permissions.py` 提供成员权限；`common/exceptions.py` 定义领域异常，missions/exceptions.py 重新导出；`config/exception_handler.py` 统一错误。
- `backend/missions/management/commands/` 包含 seed_demo；提醒命令已置于 notifications/management/commands/send_mission_reminders.py。`deploy/docker-compose.yml` 为生产部署入口，根 docker-compose.yml 用于本地数据库；定时命令示例须依据真实生产服务名编写。

本次新增文件：notifications/{models,services,views,urls}.py、迁移、管理命令与 tests/（通知序列化器在 views.py）；missions/my_work.py 负责个人工作读模型，missions/saved_views.py 负责保存视图校验、服务与接口。批量写服务位于 missions/services.py，复用同一套 Mission 写规则。

### 7.2 现有前端文件

- `frontend/src/api/client.ts`：request、ApiException、CSRF 与 buildQuery（数组转重复参数）；types.ts：Mission 等 DTO；missions.ts：列表、详情、单任务更新、状态动作、事件与成果接口；workspace.ts：工作台聚合。新增个人工作/通知/保存视图 API 模块，批量接口可放 missions.ts。
- `frontend/src/router/index.ts`：登录守卫、默认任务广场、/claimed、/published、/workspace 等；`components/AppLayout.vue`：导航。新增路由与角标在此接入。
- `views/MyClaimedView.vue` 和 MyPublishedView.vue 仅把 assignee/creator=me 交给 `components/MissionListSection.vue`；后者目前是简单分页卡片，pageSize=10，没有多选或保存视图。
- `views/MissionSquareView.vue`、WorkspaceView.vue 与 `components/WorkspaceFilterBar.vue`：任务与工作台筛选入口；`workspace/filters.ts` 共享筛选类型和快捷键，当前仅覆盖后端部分筛选。
- `components/MissionDetailDrawer.vue`、`views/MissionDetailView.vue`：复用任务操作与详情；`MissionForm.vue`：单任务编辑；`MissionCard.vue`/WorkspaceMissionCard.vue：摘要显示。新增入口不复制状态机操作逻辑。
- `components/MarkdownContent.vue`：DOMPurify 安全渲染；通知摘要用纯文本，禁止直接 v-html。`stores/auth.ts`：登录用户状态，账号变化时清理个人数据。

已有数据流：页面筛选 → api/client request → DRF views/serializers → filters/read model 或 services → PostgreSQL → 序列化 DTO → 列表/抽屉刷新。

新增数据流：任务写服务 → 同事务站内通知 → 个人收件箱；部署定时命令 → 同一通知服务 → 日期提醒；个人工作接口实时聚合业务状态；保存定义 → 服务端 resolve → 原任务查询；批量接口 → 顺序独立事务复用 update_mission → 逐项结果 → 前端确认与刷新。

## 8. 测试、验收与文档同步

### 8.1 既有回归入口

后端 `backend/missions/tests/`：test_services.py、test_api.py、test_submissions.py、test_dependencies.py、test_scheduling.py、test_workspace.py、test_milestones.py、test_comments.py、test_concurrency.py、test_concurrency_features.py；并保留 design_elements/production_templates 测试。

前端 `frontend/src/tests/`：missions.spec.ts、workspace.spec.ts、workspaceGraph.integration.spec.ts、scheduling.spec.ts、comments.spec.ts、client.spec.ts，以及现有设计与生产模板回归。

### 8.2 本次必须新增的有效测试

- 个人工作：六种分类角色/状态边界、当前退回与历史退回区分、分类重叠、管理员仍只看本人待办、全量计数与分页一致、跨日边界、缺日期、需复核与未完成子任务提示。
- 通知：真实提交/退回/转交/评论服务触发，自己操作不通知自己、角色去重、关注与静音职责例外、旧验收者通知、停用用户、字段事件去重、业务失败无通知、并发来源去重。
- 依赖通知：有阻塞到无阻塞真假翻转、部分前置完成不触发、前置取消不解除、删最后一条依赖、Done 下游需复核、同一风险多次查询不重复、恢复后再次风险可重发。
- 日期命令：今天/后 3 天/逾期边界、重复/并发运行、错过执行、改期与改回、完成和扫描并发、无日期、真实部署命令说明。
- 隔离：他人通知/订阅/Private 视图不可访问，管理员无私人绕过；标已读重复幂等、混入无权 ID 全部回滚，首次订阅并发冲突、CSRF。
- 保存视图：个人/团队权限、owner 不可变、版本冲突、非法 JSON/枚举/字段/类型、整数成员 ID 回归、标签 AND、me 按访问者解释、相对周跨日、无效引用不扩大查询、URL 与 UI 过滤条件一致。
- 批量：整体非法零写入，逐项成功/失败混合、版本冲突、冻结与权限、关闭里程碑、缺省保持与显式清空、日期双向依赖、按顺序部分提交、每项事件通知一致、并发单项编辑不覆盖、错误结果不被 200 掩盖。
- 前端：分类切换慢响应、详情操作后刷新、通知已读失败、账号缓存清理；保存/打开/另存为与不自动覆盖；选择上限/翻页清空、变更预览不写入、防重复提交、只重试确认后的失败项、网络中断不盲重发。

上述后端测试文件现已创建。前端新增 myWork.spec.ts、notificationCache.spec.ts、savedViews.spec.ts、bulkUpdates.spec.ts，并保留原有业务回归。

### 8.3 实施与交付顺序

1. 个人工作分类、通知模型/服务/接口、职责动态、日期命令及页面，完成第 1 优先级闭环。
2. 保存视图模型、校验与 resolve、前端筛选恢复。
3. 批量操作服务与 UI，接入通知并完成部分成功/重试验证。

每个可独立验证单元按项目规范提交，提交信息中文；不自动 push。空数据库必须能迁移建立最新结构，允许未发布阶段破坏性调整，不额外承担旧条目兼容。实现后将数据模型、接口、权限、页面、通知/筛选/批量规则同步并入 PROJECT_STRUCTURE.md；TECH_STACK.md 同步数据库通知、定时提醒与新增幂等写例外，README 同步真实调度步骤。本次规则已并入上述文档；README 的 cron 示例需由部署维护者在实际服务器配置，仓库实现不会自动修改宿主机定时任务。

实现后的标准验证顺序：

```bash
# 在 backend/ 执行，PostgreSQL
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
.venv/bin/python manage.py test

# 在 frontend/ 执行
npm run type-check
npm run test
npm run build
```

交付报告须说明实际完成项、实际运行验证和未完成事项；不得将本次规格核查等同于功能测试通过。

### 8.4 本次实际验证记录（2026-10-25）

- 后端依次执行 `makemigrations --check --dry-run`、`check`、`test --noinput`：无未生成迁移、系统检查通过、PostgreSQL 上 211 项测试全部通过，测试库正常清理。
- 前端依次执行 `npm run type-check`、`npm run test`、`npm run build`：类型检查通过、18 个测试文件共 94 项测试通过、生产构建成功；保留既有的大分块体积提示。
- 本地开发数据库已应用 missions.0008 与 notifications.0001 迁移；个人工作摘要/列表、通知列表/摘要、保存视图列表五个只读接口检查均返回 200。
- 已补充生产每日提醒 cron 示例和时区配置；未替实际生产服务器安装定时任务，未推送远端。
