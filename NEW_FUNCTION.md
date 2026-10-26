# NEW_FUNCTION — 统一 Agent Panel 实现方案

## 1. 目标与本次范围

在现有 Mission 协作流程上统一本地 Agent 的入口、执行状态和成果展示。Agent 是用户拥有、可替换的执行资源；MyCollab 管理业务权限，本地 Runner 管理执行环境和本机授权。

本文是待实施规格，已按当前 Django + Vue + Python Runner 结构修正；不表示以下新增功能已经实现。首批交付轻量统一面板，不要求实现全功能 Agent WebUI，也不要求先完成聊天、流式输出、工具审批或会话恢复。

用户可以在 Mission 详情选择委派类型与自己的设备，预览需求后发起执行，查看进度、取消或明确新建执行，并将已发布成果引用到人工提交草稿。设计、资产说明、生产模板、Mission 编写和验收辅助继续保留各自表单入口，不强制都绑定到一个已存在的 Mission。

后续可按需增加设备能力发现、工作区选择、交互会话和有限事件展示；这些扩展不能阻塞首批交付。

## 2. 强制边界

- **新增服务器负担最小化**：服务器仅做认证、业务授权、有界任务交接、协议校验、有限结果与成果存储。全部 LLM/图像提供商通信、登录、凭据保管、认证刷新和输出下载由用户本地 Agent 环境承担。
- 复用 Django/PostgreSQL 与 HTTPS 短轮询；首批不新增 WebSocket Gateway、Redis、Celery、模型 SDK、远程终端或服务端构建/测试。浏览器不连接用户 localhost，不代理本地 OpenCode 服务。
- 复用现有 `local_runner/` Python 程序，不另建 Node Worker。Worker 是本文对 Runner 的职责称呼，不是第二个进程产品。首批继续命令行安装、配置和启动；系统服务安装器、配对登录向导和跨平台打包另行实施。
- 服务器只传业务需求和本地注册的标识，不能指定本机绝对路径、任意 shell 命令或扩大本地权限。供应商凭据不能进入 SPA、任务正文、服务器或上传日志。
- 代码在基于固定 Git 提交导出的独立副本执行，保持当前原仓库保护；不得改为直接编辑用户原目录。独立目录不是操作系统安全沙箱。
- Agent 完成只表示候选或成果已返回；认领、提交和验收继续由人操作。不得自动提交 Mission、验收、应用补丁到原仓库、push、创建 PR、合并或部署。
- 多用户不等于设备共享：首批只允许使用本人设备。团队成员查看 Mission 不获得操作他人设备、读取私有会话或批准本地工具的权限。

## 3. 当前已经实现的基础

### 3.1 后端结构与模型

`backend/agent_bridge/` 已提供设备认证、请求队列、租约、取消、过期、幂等和协议校验：

- `models.py` 的 `AgentDevice`：owner、name、capabilities、token_digest、expires_at、revoked_at、last_seen_at。设备令牌仅创建时展示，服务器保存摘要。没有工作区注册表、Agent 实例表或实时连接状态字段。
- `AssistanceRequest`：owner/device、kind、object_id、base_version、submission_id、input、status、attempt_id、lease_expires_at、expires_at、result、error、stopped_at、retry_of、idempotency_key 与 payload_digest。
- 七类 kind：`design_polish`、`template_generate`、`mission_write`、`review_assist`、`image_generate`、`image_edit`、`code_implement`。这是业务任务能力，不是 Agent 品牌或模型列表。
- 请求状态固定为 `queued/running/awaiting_selection/succeeded/failed/cancelled/expired`。每设备最多一个 running，请求创建限制每用户最多三个活跃请求。已有幂等键与 attempt_id 校验。
- `services.py` 负责设备及交接逻辑；`authentication.py` 限定 Runner 使用设备 Bearer，浏览器使用 Session + CSRF；`protocol.py`、`image_protocol.py`、`code_protocol.py` 为两端复用的纯 Python 有界协议。

`backend/missions/models.py` 已有成果领域对象：

- `MissionExecution`：图像执行，关联 request、Mission、Asset、actor、业务版本、前一执行、参考素材与选择集合。
- `ExecutionCandidate`：图像候选摘要、尺寸及已上传 LibraryFile；`SubmissionExecutionArtifact` 固定提交轮次引用。
- `CodeExecution`：关联 request、Mission、actor、mission_version、repository_key、version、previous、manifest、report 与 patch。
- `SubmissionCodeExecution`：固定提交轮次的代码成果引用。

业务写入经过 `backend/missions/services.py` 入口，其中复用 `execution_services.py` 和 `code_services.py`；视图不绕过服务层。文件保存和删除经过 `backend/library/services.py`。

**不新建重复的 AgentRun 状态机。** 首批 UI 中的“执行记录”是现有请求与对应成果对象的展示投影。以 request_id 标识一次交接，以 execution_id 标识成果记录；取消、重试及提交关联不能混用这两个 ID。

不是每个请求都有 Mission 或 workspace：设计与模板辅助可能独立存在，Mission 编写可能发生在创建前，图像执行关联 Asset，只有代码执行需要 repository_key。不得给全部 AssistanceRequest 增加必填 Mission/工作区关系。

### 3.2 当前接口

以下路径均以 `/api/` 为前缀并保留结尾斜杠。首批复用，不另建 `/api/agent/runs` 系列。

浏览器接口：

- `GET/POST agent-devices/`：本人设备列表与创建；`POST agent-devices/{id}/revoke/`：撤销。
- `GET/POST assistance-requests/`：本人请求历史与四类文本请求创建；`GET assistance-requests/{id}/`、`POST assistance-requests/{id}/cancel/`。
- `GET mission-executions/?mission={id}`、`POST mission-executions/`：图像历史与创建；`GET mission-executions/{id}/`、`POST mission-executions/{id}/cancel/`。
- `GET code-executions/?mission={id}`、`POST code-executions/`：代码历史与创建；`GET code-executions/{id}/`、`POST code-executions/{id}/cancel/`。
- 现有 `POST missions/{id}/submit/` 接收人工填写的提交内容，可附带 `execution_candidate_ids` 和 `code_execution_ids`；使用现有提交/验收权限与状态校验。

Runner 接口（只接受设备认证，写入须绑定当前 attempt）：

- `POST agent-runner/claim/`。
- `POST agent-runner/requests/{request_id}/heartbeat/`、`result/`。
- 图像：同一请求路径下的 `references/{file_id}/`、`candidates/`、`selection/`、`candidates/{key}/upload/`、`complete/`，均为 POST。
- 代码：同一请求路径下的 `code-manifest/` 与 `code-publish/`，均为 POST；后者上传 patch/report。

代码创建的关键字段为 mission_id、device_id、repository_key、expected_version、instructions、idempotency_key、previous_id。图像创建额外需要 asset_id、asset_version、kind 和 reference_ids。统一面板保留各类型字段与两端校验，不能将图像/代码请求发到只支持文本创建的接口。

现有权限需要准确区分：设备及原始辅助请求按用户隔离；图像/代码执行历史与已发布成果在当前单团队中可查看，创建/取消受服务层权限限制。素材列表按所有者隔离，下载通过认证 API，不能把 MEDIA_ROOT 公开为静态目录。尚未发布的本地补丁、图片正文和原始 Agent 日志不因此变成团队可见。

### 3.3 当前前端

前端是 Vue 3 + TypeScript + Element Plus + Pinia + Vue Router，不使用 React hooks 或 TSX 组件树：

- `frontend/src/api/agentBridge.ts`：设备与文本请求；`executions.ts`：图像；`codeExecutions.ts`：代码；`types.ts`：提交与成果类型。
- `components/AssistancePanel.vue`：四类文本辅助，预览输入、候选逐字段采纳和过期检查。
- `components/MissionExecutionPanel.vue`：图像委派、历史及成果引用。
- `components/MissionCodePanel.vue`：代码委派、历史及成果引用。
- `components/CodeReport.vue`：摘要、基线、文件列表、补丁下载和本地验证结果。
- `views/MissionDetailView.vue` 与 `components/MissionDetailDrawer.vue` 已嵌入图像/代码面板；完整详情支持采纳到提交草稿，抽屉保留跳转完整详情的操作。
- `views/AgentDevicesView.vue` 已负责设备创建、撤销和请求历史。设计、模板、Mission 表单、验收对话框已有文本辅助入口。

API 统一通过 `src/api/` 的请求封装处理 CSRF/错误；Markdown 使用 `MarkdownContent.vue` 清洗，链接使用 app-link，卡片沿用项目 Element Plus 规范。

### 3.4 当前本地执行结构

- `local_runner/__main__.py`：配置读取、BridgeClient、领取与按 kind 分发。配置保存在本机，POSIX 权限 600；模型子进程不接收 MyCollab 设备凭据。
- `opencode.py`：四类文本任务，独立无工具会话。
- `opencode_code.py`：代码任务专用 OpenCode 配置，限定读写路径，禁止 shell 和外部集成；同时设置规范 cwd/PWD。
- `code_workspace.py`：本地 repositories 注册表、固定基线导出与实际 diff；`code_verification.py`：仅运行本地配置的 argv；`code_execution.py`：清单、本地审查与明确发布。
- `codex_image.py`、`images.py`：Codex 图像生成/编辑、本地候选预览、显式选择后上传。
- 当前文本/代码适配验证版本是 OpenCode CLI 2.1.3，图像是 Codex CLI 0.164.0；这表示仓库已验证范围，不代表所有版本或账户都支持。供应商登录仍由各 CLI 本地完成。
- 当前使用结构化 CLI 输出，不解析 ANSI 终端文本；没有通用交互会话 API、浏览器聊天或远程权限审批。

本地 repositories 将 repository_key 映射为 path、baseline、writable_paths、verification。`--list-repositories` 可列出可用标识；服务器不持有绝对路径。现有 `--select REQUEST_ID --keys ...` 发布选中图片，`--publish-code REQUEST_ID` 发布人工检查后的代码成果；这些操作不是网页按钮已具备的能力。

## 4. 首批：统一轻量面板（必须实现的新增部分）

### 4.1 页面与组件

新增 `frontend/src/components/AgentPanel.vue`，以 Mission 为上下文统一图像与代码委派入口。优先组合、抽取已有组件，保留它们的服务与成果逻辑，不一次性重写所有辅助表单。

面板提供：

1. 委派类型切换：代码实现、图像生成/编辑；只展示与当前 Mission、设备能力匹配的操作。
2. 执行配置：本人设备、代码 repository_key 或图像 Asset/参考图、初始要求、输入快照预览。模型/供应商选择留在本地配置。
3. 状态与历史：请求状态、创建时间、过期时间、失效原因、取消状态、成果摘要。首批可以按类型切换历史，不必实现跨接口全局排序与分页。
4. 操作：明确创建、取消、基于旧执行创建新版本；网络重试沿用幂等键，用户明确重新生成才使用新键。不能把“重试”实现为恢复旧 attempt。
5. 成果：复用 CodeReport、已上传图像预览及引用到提交草稿；代码 diff 使用补丁下载与本机查看即可，无须内嵌逐行 diff 编辑器。
6. 本地待办提示：图片等待本地选择，代码等待本地审查发布；显示不含令牌和本机私有路径的 CLI 操作说明。浏览器不能代替本地发布确认。

Mission 完整详情与抽屉使用同一 AgentPanel；完整详情接收采纳事件更新原提交草稿，抽屉继续使用现有完整页入口。设计/资产、生产模板、Mission 编写与验收表单保留 AssistancePanel，统一标题、状态文案等可复用展示，不丢失表单上下文或把候选自动保存。

设备页继续复用已有注册/撤销方式，不新建配对后端。展示 last_seen_at 时标注“最近联系”，不能把历史时间当作实时在线证明，也不要求设备在线才能先排队。

### 4.2 前端数据组织

保留三个 API 模块的领域类型；需要共享展示时增加判别联合类型（例如 text/image/code），保留 request_id、execution_id、kind 和原始状态。公共逻辑可放入 Vue composable，但不要为统一 UI 引入第二套后端写接口、缓存框架或全局状态机。

面板打开且存在活跃请求时按现有约 15 秒频率轮询；切换 Mission、关闭抽屉、组件卸载或全部终态后停止对应轮询，避免新旧组件同时请求。失败退避，重新打开先取当前状态。状态未知不触发自动重建任务。

首批“进度”是生命周期状态，不是百分比、token 流或工具执行日志。无真实执行耗时字段时不要用 created_at 到当前时间冒充模型耗时。

### 4.3 首批不要求的 UI

聊天续写、逐 token 输出、工具活动时间线、Web 工具审批、代码编辑器、内嵌完整 OpenCode WebUI、远程终端、供应商登录/模型管理、会话恢复与跨设备迁移均不作为首批验收条件。用户仍可在本机使用 Agent 自身工具查看详细输出。

首批原则上不需要数据库迁移或新服务依赖；只有实现中确认现有接口无法支持明确需求时才增加最小字段/接口，并同步规格。不可为了组件重组提前创建 AgentRun、Workspace、Session 三套表。

## 5. 首批端到端流程与状态含义

代码流程：

1. 用户在本人 InProgress Mission 选择本人代码设备，填写本地已配置的 repository_key，预览后创建 CodeExecution + AssistanceRequest。
2. Runner 主动领取，按本地白名单解析仓库，将固定提交导出到独立副本，再执行代码 Agent 与本地允许的验证命令。
3. 实际补丁、报告和日志留在本机；服务器先接收有界摘要清单，状态进入 awaiting_selection，面板显示“等待本地审查并发布”。
4. 用户本机检查后执行 `--publish-code`，只上传同一补丁与报告。服务器校验摘要、版本与权限后标记 succeeded。
5. 用户在完整详情引用到提交草稿，补充人工验证说明并提交，由验收者处理。测试 failed/timeout/not_run 必须如实展示，服务器未复跑测试。

图像流程类似，但需要关联 Asset；编辑需要授权参考图。Runner 本地生成/转换/预览，用户明确选择后仅上传选中成果，再由人引用提交。统一面板不上传未选候选或把本地文件路径作为下载地址。

四类文本继续“上下文预览 → 本地生成 → 有界结构化候选 → 人工逐字段采纳 → 原表单保存/验收”。

状态映射只修改文案，不另建 completed/starting/interrupted 等持久状态：queued 等待设备，running 本地执行，awaiting_selection 按图像/代码显示不同待办，succeeded 候选/已发布成果可用，failed/cancelled/expired 为终态。

连接健康与执行状态独立理解：目前是约 30 秒心跳、180 秒租约，Runner 续租失败时尽力停止进程组，服务器在租约失效后拒绝旧 attempt。浏览器离线不终止 Runner；Runner 离线不能保证本地或供应商立刻停止。不得在重连后将 expired 改回 running 或接收旧结果。待选择/发布窗口现为 24 小时，文本总时限 15 分钟，图像/代码执行总时限 30 分钟。

## 6. 第二批：本地能力发现与适配器整理（可独立实施）

目的：减少手工填写 repository_key，支持多个本地 Agent 实现；不是重做已有供应商接入。

### 6.1 复用适配器

在 local_runner 内抽取 Python 适配器注册与分发接口，区分任务能力和交互能力：

- 任务能力继续使用七个 kind，不以 opencode/codex 名称替代业务类型。
- 交互能力单独声明 supports_followup、supports_resume、supports_tool_events、supports_permission_requests、supports_cancel；没有验证过的能力默认 false。
- 第一阶段适配接口只需能力检查、一次执行、取消及结果规范化。会话创建、续写和权限回复作为可选接口，不能要求所有适配器实现。
- 复用现有 OpenCode 文本/代码和 Codex 图像实现。图像适配器不冒充通用代码 Agent；更换品牌不得绕过每类成果协议及本地审核。

### 6.2 最小设备描述协议（待新增，非现有接口）

可新增 `POST /api/agent-runner/descriptor/`（设备 Bearer）及 `GET /api/agent-devices/{id}/descriptor/`（仅设备所有者 Session）。在现有设备旁保存一份有界描述快照及上报时间，不新建服务器本地路径表：

- protocol_version、descriptor_revision、最多 16 个 Agent 标识/展示名/声明能力，最多 100 个 workspace 描述。
- workspace 使用当前 repository_key 作为设备内唯一标识，只含展示名和允许的 Agent 标识；不包含绝对路径、Git URL、验证 argv、环境变量或登录信息。
- 本地上报不能扩大设备创建时授权的 kinds；可用能力取服务器授权与本地声明交集，Runner 执行时再次检查配置。
- 首批已有单适配器路由继续可用；真正允许选择多个适配器时，再为请求快照增加可选 adapter_id 及两端严格校验，不能仅加下拉框却忽略执行端选择。
- 描述只在启动、配置变化或低频刷新时发送；限制请求大小（建议 64 KiB），过期描述标注陈旧，设备撤销后不能更新。刷新不等于 Agent 一定可用。

网页有新描述时展示工作区/Agent 下拉选择；没有描述仍允许按现有方式输入标识。本机注册表是权限权威，服务器描述不是本地授权。此批需要新增模型字段/迁移与严格序列化测试，不属于首批必需项。

## 7. 第三批：有限交互与会话（按需扩展）

保留原需求中的追问、活动展示、工具审批与恢复方向，但必须先验证所选本地 Agent 的实际协议和受支持版本，再确定实现范围。不能把现有非交互 CLI 包装为已经支持 session/prompt/permission API。

### 7.1 传输与数据模型

默认仍用 HTTPS 轮询。若增加交互，在现有 request/attempt 下增加有界命令与事件记录，而不是另起一套任务状态机：

- 命令包含 command_id、request_id、attempt_id、类型、有限 payload、有效期及处理状态；设备主动领取，本地持久去重后处理。ACK 只代表收取，不能当作执行完成。
- 事件按 request/attempt 保存递增 seq 和客户端去重 ID，分页按游标读取；只接收当前认证设备、当前 attempt 的允许事件。事件不能直接覆写业务终态。
- 单次运行建议最多 1000 条、累计 1 MiB 共享事件，单条不超过 8 KiB；本地聚合限速，不逐 token 写数据库。达到上限只停止细节上传，最终结果仍走现有有界成果接口。
- 新增路由仍放在 agent_bridge 下，分别使用 Session 与 DeviceAuthentication，不开放通用 HTTP 代理。具体路由和状态迁移在这一批实现前补齐规格。
- 只有测量证实延迟要求无法由轮询满足时才评估 SSE/WSS，并同步 TECH_STACK 的部署、连接限额和维护成本；当前 ASGI 入口只是 Django 应用，不是现成 Gateway。

### 7.2 权限与本地会话

本地持久化 request_id/attempt_id 到 Agent session 的映射；私有 session 标识、工作路径及原始日志留本地。服务端只保存需要展示的能力与会话可用性。

追问、取消及审批默认仅发起人/设备所有者操作。原始消息和工具事件默认私有；新建会话数据不能继承当前团队可读的成果历史权限。需要团队共享时另行增加明确分享动作与逐资源权限测试。

工具审批只允许对本地已允许、仍待决的具体操作作一次决定，绑定 request、attempt、session、permission_id 与操作摘要；过期、撤销、会话变化或重复响应不得授权新操作。默认拒绝超时请求；网页批准不能扩大本地白名单，也不能开启现有代码 Agent 禁用的 shell。未经本地用户配置允许的操作应直接拒绝，无须弹出可批准按钮。

恢复仅在适配器支持、租约/业务版本仍有效且本地状态一致时提供。旧任务已过期或取消时，以明确新执行承载后续工作，不复活终态；不得自动重做付费模型调用。若需放宽租约容忍断线，必须同步重新设计时限、独占约束、迟到结果和停止确认测试。

### 7.3 可选展示与后续能力

轻量消息列表、有限活动时间线、只读 diff、单次权限卡片按已验证能力逐项开放。无能力时隐藏入口并解释，不制造假进度。ACP 适配器、会话恢复、设备共享、多执行并发均为后续独立需求；ACP 不能替代 MyCollab 设备认证、Mission 权限和交接协议。

不要求提供完整 Agent WebUI。若以后需要，作为单独需求评估本地访问方式、身份与资源隔离，不在此方案中建设公网反向隧道或任意接口代理。

## 8. 安全、保留与业务一致性

- Mission 图像/代码执行仅当前认领人对 InProgress 任务创建，校验 expected_version；图像还校验 Asset 版本及关联。修改、改派、取消或提交后必须沿用现有失效检查。
- Session 与设备 Bearer 不混用。设备令牌到期、撤销或用户停用后不可领取/续租/上传；服务端资源关系取数据库，不信任客户端 owner/device 声明。
- 对象版本、提交轮次、活跃限额和幂等校验继续在事务内执行；错误沿用项目统一结构。不得新增通用字段更新绕过状态机。
- 当前代码补丁最多 2 MiB，报告最多 128 KiB，最多 200 个改动文件；实际 diff 与本地验证结果是证据，模型摘要不能证明测试通过。代码本地审查后才上传正文，原始日志不上传。
- 图像候选最多四张，每张 20 MiB，按现有 PNG/像素协议校验；转换在本地，服务器不下载模型输出 URL。参考素材仅按授权接口获取。
- `cleanup_assistance` 已负责请求过期与历史清理；图像/代码保留成果和提交关联，清除旧输入/结果快照。后续共享事件建议默认保留七天并复用清理入口，不删除已引用交付证据；撤销设备不等于删除所有已分享成果。
- 本地日志、未选图像、未发布补丁和供应商会话由用户本地管理。任何新增上报都须采用字段白名单及体积限制，不把原始 Agent 事件任意 JSON 透传到服务器。

## 9. 实施顺序与验收

### 第一批验收：统一入口即可交付

1. 新增 AgentPanel 并接入完整详情/抽屉，复用图像、代码面板及现有 API；设计/模板等文本入口保持可用。
2. 设备和能力过滤正确；代码仓库标识与图像 Asset/参考图不会相互串用；创建前可审查实际发送上下文。
3. 状态、取消、新执行、幂等与失效提示保持准确；组件切换/关闭后停止轮询，不重复领取或调用模型。
4. 未本地发布的成果不可在网页直接引用；已发布成果引用到原提交草稿，仍需人工提交和验收；失败的本地验证不会显示为通过。
5. 浏览器刷新/离线不导致创建第二次付费调用；其他用户不能操作设备或执行，团队已发布成果仍按现有权限显示。
6. 现有三类执行闭环回归通过，不需要 Chat、WSS、工具审批、ACP 或完整 Agent WebUI 才算完成。

### 第二批验收：发现与可替换适配器

验证 descriptor 的所有者隔离、字段/体积限制、能力交集、过期提示与本地再次授权；验证未知仓库/适配器拒绝执行，不泄漏本机路径。已有配置仍可运行，适配器抽取不改变成果协议与明确发布流程。

### 第三批验收：逐能力交付

每次只启用已验证的交互能力。覆盖重复命令去重、乱序/重复事件、断线游标恢复、迟到结果拒绝、权限超时与重放、跨用户访问、过期任务不可恢复、取消后的进程停止确认。真实供应商测试与确定性适配器测试分别记录，不能互相替代。

### 测试入口与验证命令

现有后端测试在 `backend/agent_bridge/tests/test_bridge.py`、`test_images.py`、`test_image_roundtrip.py`、`test_code.py`、`test_code_roundtrip.py`；Mission 业务回归在 `backend/missions/tests/`。真实 OpenCode 文本测试入口为 `test_live_opencode.py`，需要已配置本地环境，不作为普通回归的付费依赖。

前端重点复用 `frontend/src/tests/agentBridge.spec.ts`、`missionExecution.spec.ts`、`missionCode.spec.ts`，增加统一面板入口、生命周期与事件转发测试。本地回归在 `local_runner/tests/`，继续验证 cwd/PWD、隔离副本、白名单、真实退出码、补丁/报告摘要及发布幂等。

实现后的验证按修改范围执行并如实记录：

- 后端在 backend 中运行 `.venv/bin/python manage.py makemigrations --check --dry-run`、`check`、`test`；事务/并发测试使用 PostgreSQL。
- 前端在 frontend 中运行 `npm run type-check`、`npm run test`、`npm run build`。
- 本地执行改动在根目录运行 `local_runner/.venv/bin/python -m unittest discover -s local_runner/tests -v`。
- 真实接入使用用户已配置的本地 CLI 和隔离示例仓库；服务器禁止提供商网络访问，检查原仓库未被修改、只有授权成果上传。新增 UI 记录实际浏览器验收情况，组件测试不能表述为人工浏览器验收。

## 10. 编码与文档交付要求

实施时以本文提供的结构和直接相关源文件为起点，信息不足再扩大阅读，不把通读整个项目当作固定步骤。首批优先完成现有能力的统一体验，不重复实现设备系统、队列、代码隔离和图像成果协议。

每批完成后，将实际数据模型、API、权限、页面和业务规则同步到 PROJECT_STRUCTURE.md；仅在技术约束发生变化时更新 TECH_STACK.md，本地配置/命令变化同步 local_runner/README.md 与主 README。保持“已实现”与“计划”明确分开，不将未来交互接口写成当前能力。

本次修正只更新 NEW_FUNCTION.md 的实现方案，不实施上述新增面板或扩展协议。
