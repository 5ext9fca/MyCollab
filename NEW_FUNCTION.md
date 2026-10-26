# 本地 Agent 辅助与模型手动委派分批规格

## 1. 状态、目标与范围

本文替换原有功能规格，记录本次完整需求。本文所列 Agent 能力均为待实现；本次仅编写规格，不代表功能已经上线。

当前已实现设计/资产编辑、生产模板编辑与实例化、Mission 编写、提交与人工验收；尚未实现本地 Agent 绑定、辅助请求、模型建议回传或模型执行委派。不得将已有业务功能重复实现。

首批只交付四项业务能力：

1. 设计、资产说明润色。
2. 生产模板生成。
3. Mission 编写。
4. 验收辅助。

本地 Agent 连接、授权、请求交接、结构化结果与人工采纳是四项能力共用的必要基础，不另行扩展为通用自动执行平台。首批不生成美术文件、不操作代码仓库、不运行构建或测试、不自动提交或验收 Mission。

## 2. 全批次硬性原则：新增服务器负担最小化

- MyCollab 服务器不负责与 LLM 或图像模型提供商通信：不得代理模型请求、保存供应商凭据、托管模型 OAuth 刷新令牌、下载模型输出地址、执行推理或承担供应商重试。
- 所有模型通信、供应商认证、凭据保管、模型选择、费用额度与调用重试均由用户本地 Agent 环境负责。使用云端模型也由本地 Agent 直接访问提供商；不要求必须在本机运行模型权重。
- SPA 不直接访问模型供应商，不接收或持久化供应商密钥。配置页仅展示本地设备与非敏感能力信息。
- 服务器仅承担现有业务、授权后的上下文交接、轻量请求状态、有限结果持久化及人工采纳后的校验。首批复用 Django/PostgreSQL，不新增 Redis、Celery、WebSocket、服务端 Agent、GPU、容器执行沙箱或向量数据库。
- 本地 Runner 主动通过 HTTPS 访问 MyCollab，使用短请求轮询；服务器不连接用户电脑，不要求公网端口、浏览器直连 localhost 或反向隧道。Runner 是本地 Agent 的协议适配器，不是服务器上的执行进程。
- 首批每设备同时运行一个请求；空闲与故障轮询退避并加入抖动，页面仅在存在活动请求时轮询。限制输入/输出体积、活动请求数量、分页大小与历史保留期，不保存完整 token 流和无限原始日志。
- 所有外部执行均发生在数据库事务与锁之外。服务器接收模型输出只视为候选数据，不能视为业务操作指令。

## 3. 分批计划与完成边界

### 第一批：四项文本辅助与最小本地接入

交付第 4–7 节。先完成通用协议和一个可实际运行的本地适配器，再依次接入四个业务入口。具体 Agent 产品尚未指定，接口保持独立；首批无需兼容所有 CLI/SDK，也不能以仅有 mock 适配器宣告交付。选定适配器后记录安装版本、非交互调用方式、认证方式及真实接入验证结果。

### 第二批：Mission 手动委派美术资产

用户在自己认领的 InProgress Mission 中选择本地设备、图像生成/编辑能力、需求与参考素材。本地 Agent 调用图像提供商或本地 GPU 工作流，处理下载、转换与候选预览，用户选择后再上传成果到本人素材库。服务器不获取供应商图片 URL，也不代理生成或编辑调用。

新增 MissionExecution 与成果关联、候选版本和取消/断线处理；执行记录关联 Mission、发起人、输入版本与 Asset。成果完成后仍由认领者人工提交，验收者人工验收。模型不是 Mission 的认领者。上传沿用文件类型、大小、归属和引用校验；仅上传用户选中的成果，减少存储与带宽。

本批前置条件：第一批设备协议、权限隔离、幂等回传和人工确认已验收。详细文件协议与模型适配在本批实施前细化，首批不预建完整成果系统。

### 第三批：Mission 手动委派规则/代码实现

用户在本地预先配置允许的仓库与工作区，选择一个 Mission 委派本地代码 Agent。由本地环境建立隔离工作区，读取基线、修改代码、运行用户允许的验证，返回补丁、变更摘要与测试报告。服务器只传仓库配置标识，不下发任意本机路径或任意 Shell 命令。

首个交付范围是补丁与报告，经人工审查后由用户提交 Mission。Git 凭据、私有依赖凭据、运行工具链与资源消耗均留在本地。自动推送分支、创建 PR、跨设备调度、合并与部署不属于本批默认范围，另行明确后实施。

本地测试报告属于提交证据，不能冒充服务器独立验证。继续保留人工认领、提交与验收，执行成功不自动推进业务状态。

## 4. 第一批四项功能

### 4.1 设计、资产说明润色

- 入口：设计/资产创建或编辑表单的说明区域；已有对象仅对具备 edit 权限且未归档的用户开放。新建时要求有效成员。
- 输入：当前标题、说明草稿、条目类型、用户补充要求；关联设计/资产说明须逐项选择，不自动发送整个工作区。
- 输出：title、content、修改摘要和待澄清问题；保留原始事实与约束，不擅自增加已确定需求。类型、父级、引用关系和依赖关系不属于可生成写入字段。
- 用户对照原文和建议，可逐字段采纳并继续编辑；采纳只修改表单，显式保存才调用现有创建/PATCH 接口。取消和生成失败保留原始草稿。

### 4.2 生产模板生成

- 入口：生产模板新建/编辑页面；可从用户选择的资产/设计说明与生产目标生成候选模板。
- 输出严格对应现有 name、description、steps。每步包含 key、title、content、acceptance_criteria、type、priority、tags、prerequisite_keys。
- 复用现有 1–30 步限制；key 唯一且为 1–50 位字母/数字/下划线；前置 key 必须存在，不得自依赖或成环；类型、优先级与标签遵守现有枚举和校验。
- 模板步骤不得引用私人素材链接，继续使用现有外链规则。模型生成的不存在引用或未知字段须明确报错，不静默写入。
- 返回后进入 ProductionStepsEditor，由用户修改、保存。生成模板不实例化 Mission；保存模板后，用户仍通过现有资产生产入口显式生成任务。
- 编辑模板不改写已有 ProductionBatch 快照与已生成 Mission；每个资产一个生产批次的现有约束保持有效。

### 4.3 Mission 编写

- 入口：Mission 新建/编辑表单；支持根据简述生成草稿或润色已有草稿，现有任务沿用 edit 权限与可编辑状态限制。
- 输入：用户填写的目标、当前表单字段及显式选中的设计/资产说明；创建子任务时可选择父任务作为上下文。
- 输出允许 title、content、acceptance_criteria、type、priority、tags，并提供待澄清问题。验收标准应可核对，不能把猜测写成既定事实。
- reviewer、assignee、parent、关联设计/资产、里程碑、日期及依赖由用户通过既有控件选择；模型不得通过返回 ID 自动设置这些关系。
- 用户采纳到表单后显式保存；创建仍生成 Open、未认领的 Mission，不自动拆分、认领、提交或变更其他任务。

### 4.4 验收辅助

- 入口：Submitted Mission 的验收区域，仅对当前具备 review 权限的人开放；第一批范围为验收者检查当前待验收轮次，不扩展为执行代码或自动验证构建。
- 输入：任务内容、验收标准、明确选定的 submission_id、该轮 description、verification_description、源码引用与构建引用元数据；评论等附加上下文由用户选择。
- 输出：逐项验收标准的“材料支持 / 材料存在矛盾 / 证据不足”判断、依据定位、缺失材料、建议核对步骤以及可编辑验收意见草稿。
- 依据只可引用本次已提供的内容。源码 URL、revision、构建成功状态和下载链接不代表 Agent 已读取源码、运行测试或核验产物；未读取的外部证据必须标记为未验证。
- 首批不自动打开外链、不下载构建、不读取本机仓库、不执行命令。即使 Agent 本身具备这些工具，也须以只读文本分析能力运行。
- 建议不得自动选择 accept/reject、verified_build_reference_id 或提交 review。用户自行选择实际验证的构建、填写意见并确认；服务器继续执行当前验收规则。
- 分析绑定 Mission 版本和提交轮次；版本、轮次、验收人或状态变化后标记过期，禁止直接采纳到当前验收表单，必须重新请求。

## 5. 第一批本地接入与交接协议

### 5.1 用户需要准备的环境与凭据

- 安装本地 Runner 和一种支持程序化调用的 Agent，配置兼容的文本/结构化输出能力。仅有聊天网页或 GUI 登录不能视为已满足调用要求。
- 模型供应商 API Key、官方支持的本地登录授权或本机推理服务认证仅保存在本地 Agent/操作系统凭据存储中。用户自行承担调用额度；不同产品的订阅是否覆盖程序化调用以该产品认证方式为准。
- 在已登录的 MyCollab 设置页创建可撤销、可过期的设备凭据，仅用于 Runner 访问 MyCollab。服务端只存令牌摘要，明文只在创建时展示一次；不得要求用户复制 Session Cookie 或密码给 Agent。
- 首批不需要 Git 凭据、云服务器凭据、生产数据库密钥或部署权限。设备撤销、用户停用后立即禁止继续领取或回传。

### 5.2 用户流程

1. 用户绑定本机 Runner，页面显示设备名称、能力、最近联系时间与可用性；离线时明确提示，不静默转交其他设备或服务器执行。
2. 用户选择四项辅助之一，检查即将交给本地 Agent 的字段与上下文，指定本人设备，点击生成。
3. 服务器验证权限和体积限制，保存输入快照与基础版本；Runner 主动领取属于自己的请求。
4. Runner 在本地调用 Agent，校验结构化结果、处理供应商超时/限流，并仅回传规定字段和简短错误摘要。不得回传凭据、原始认证响应或完整环境变量。
5. 页面展示候选、问题和错误。用户可以编辑、放弃或采纳到表单，再通过现有业务接口保存。

第一批上下文只含用户选择的文本与引用元数据，不自动附带素材二进制；相关链接不能被当作已读内容。设备令牌不得获取任意团队对象或自动遍历素材库。

### 5.3 待新增数据与 API

建议新增 `backend/agent_bridge/` 管理设备、辅助请求及其授权，不集成任何供应商 SDK。以下均为新接口，不是已有事实：

- AgentDevice：owner、名称、能力列表、token 摘要、expires_at、revoked_at、last_seen_at。能力和设备名称是非敏感信息，不含供应商令牌。
- AssistanceRequest：UUID、owner、device、kind（design_polish/template_generate/mission_write/review_assist）、schema_version、关联对象类型/ID（新建草稿可空）、base_version、submission_id（验收必填）、输入快照、状态、attempt_id、lease_expires_at、结构化结果、错误摘要、时间戳、客户端幂等键。
- 状态：queued/running/succeeded/failed/cancelled/expired。首批不建服务端 token 流或通用自动编排。成功只表示候选已返回，不表示已保存或通过验收。
- 浏览器：`POST/GET /api/agent-devices/`，`POST /api/agent-devices/{id}/revoke/`；`POST/GET /api/assistance-requests/`，`GET /api/assistance-requests/{id}/`，`POST /api/assistance-requests/{id}/cancel/`。沿用 Session + CSRF；设备与请求仅本人可访问。
- Runner：`POST /api/agent-runner/claim/`，`POST /api/agent-runner/requests/{id}/heartbeat/`，`POST /api/agent-runner/requests/{id}/result/`。仅接受专用 Bearer 设备令牌，独立认证，不接受 Cookie 回退；该认证范围不得覆盖普通业务 API。
- 领取使用数据库短事务原子分配；设备只领取显式分配给自己且属于 owner 的请求。心跳和回传必须匹配当前 attempt_id；相同结果重复上传幂等，不同结果不得覆盖终态。
- 断线与租约过期不等于模型调用已停止。首批过期请求转 expired，不自动重新派发或重复付费调用；用户明确重试创建关联的新请求。迟到结果拒绝写入终态，Runner 可保留本地副本供排查。
- 取消立即禁止采纳/覆盖结果；Runner 下次心跳获得取消标志并尽力终止。页面区分“已取消，等待本地停止”与本地已确认停止，不承诺供应商费用回滚。
- 首批建议默认值：每设备 1 个 running、每用户最多 3 个活动请求；输入 JSON 最大 256 KiB、结果最大 128 KiB、错误摘要最大 2 KiB；运行心跳约 30 秒、租约 180 秒、请求最长 15 分钟；空闲轮询从 15 秒退避至 60 秒。均需服务端强制上限，可按实测调整并记录。
- 历史列表分页；输入/结果默认保留 30 天，清理由管理命令配合部署 cron 完成，不引入常驻 worker。请求过期在相关读写入口判断，清理命令负责回收历史记录。

## 6. 校验、权限与采纳规则

- 请求创建与领取时复核有效用户、设备归属、对象权限与版本；用户提供的 ID 必须逐个检查，不能因模型请求绕过业务授权。
- 协议使用版本化 JSON Schema/等价严格校验，区分四种输出；拒绝未知字段、错误枚举、超长文本及非法依赖。客户端给出可理解的字段错误；服务端和本地适配器均校验，不能只依赖模型承诺。
- 模型建议视为不可信内容。上下文中的评论、Markdown 和引用不得改变协议权限或要求调用额外工具。第一批适配器须关闭文件/命令/网络浏览等无关工具；不能约束工具权限的适配器不作为首批支持项。
- 普通润色/编写请求返回期间若用户继续编辑表单，应提示草稿已变更，允许对照后逐字段合并，不静默覆盖。服务器对象版本变化后要求重新加载/比较再显式保存，禁止自动使用新版本重试覆盖。
- 所有设计、模板、Mission 保存继续通过 `backend/missions/services.py`；新桥接服务只管理请求生命周期，不能直接修改业务模型。素材写入继续走 `library/services.py`。
- 浏览器正常保存时携带当前明确确认的 expected_version；服务端重新检查权限、状态、引用和依赖约束。验收建议不能绕过既有 submission_id、构建引用与 reviewer 校验。
- Markdown 展示经 MarkdownContent.vue 清洗，保持作者素材引用限制。请求与结果不写入普通访问日志；错误只记录脱敏摘要。
- 独立辅助区采用项目现有轻边框卡片，包含状态、输入预览、结果、采纳和取消操作；保留键盘焦点与小屏布局，链接复用 app-link。

## 7. 第一批验收与验证

- 用一个真实本地适配器完成四项“输入 → 本地模型 → 候选 → 人工采纳 → 现有业务保存/验收”验证；记录使用环境与结果，不记录密钥。自动化测试使用确定性假 Runner，无需访问收费模型。
- 确认服务端没有供应商请求与认证配置；在服务器不能访问模型提供商而本地可访问的条件下，四项能力仍可用。本地未配置/离线时明确失败或等待，不由服务器兜底调用。
- 测试设备隔离、令牌过期/撤销、用户停用、权限变化、超限请求、领取并发、幂等键、重复回传、迟到回传、取消与断线；确认重试不会自动执行第二次供应商调用。
- 测试四类输出校验、模板依赖环与私人素材链接、模型伪造对象 ID/额外写入字段、Markdown 注入、表单编辑冲突、对象版本冲突与验收轮次过期。
- 验证生成成功不修改原对象；采纳只改表单；模板保存不实例化任务；验收辅助不改变状态或自动选择构建。
- 后端按 `makemigrations --check --dry-run` → `check` → `test` 验证，并发/事务测试使用 PostgreSQL。前端按 `npm run type-check` → `npm run test` → `npm run build` 验证。新增 Runner 的协议与适配器测试，并记录真实接入是否完成。
- 第一批完成后将实际模型、API、权限、页面与规则并入 PROJECT_STRUCTURE.md，同步 TECH_STACK.md 与 README 的安装/绑定/撤销/排错说明。未完成真实 Agent 验证时明确标注，不宣告完整验收。

## 8. 实现所需的当前项目结构（已核对事实）

### 8.1 后端与约束

- `backend/config/urls.py`：挂载 `/api/auth/`、`/api/library/` 与 missions 等 API；`backend/missions/urls.py` 注册 missions、design-elements、production-templates 等 ViewSet。
- `backend/missions/models.py`：DesignElement 含 title/content/kind/parent/assets/prerequisites/created_by/version/archived；Design 与 Asset 是同级业务对象，父子和依赖限同类型，Design 单向引用多个 Asset。
- 同文件 ProductionTemplate 保存 name/description/steps/version/created_by/archived；ProductionBatch 保存模板版本与快照，asset 为 OneToOne；ProductionBatchItem 用 step_key 关联生成的 Mission。
- 同文件 Mission 存任务正文、验收标准、认领者、验收者、状态、版本与设计/资产关系；MissionSubmission 保存不可覆盖的提交轮次材料，验收结果另行记录；SubmissionSourceReference、SubmissionBuildReference 保存源码及构建元数据。
- `backend/missions/services.py`：create/update_design_element、create/update_production_template、instantiate_production、create/update_mission、submit_mission、review_mission 是复用写入入口；design_allowed_actions、template_allowed_actions、allowed_actions 决定操作权限。
- 设计/模板编辑限创建者或管理员，归档后需先恢复；Mission 编辑受创建者/管理员与状态限制，认领者并非天然拥有编辑权。Submitted/Done 冻结任务内容，提交由认领者执行，验收使用当前 reviewer/管理员权限与阻塞检查。
- 模板 `_validate_template_steps` 已校验 1–30 步、key、枚举、标签、链接和无环依赖；instantiate_production 已创建快照及 Open 未认领 Mission 并关联步骤依赖。无需重新实现模型生成后的业务流程。
- 相关写入使用事务、乐观锁，图修改使用团队锁；冲突按现有 DomainError 返回 `{code, message, field_errors}`。新辅助能力不得长时间持有这些锁。
- `backend/missions/views.py`、`serializers.py`：现有 API 解析、服务调用与序列化；`backend/library/services.py`、`references.py`：文件写入和 Markdown 引用规则。

### 8.2 现有接口与前后端数据流

- 设计/资产：`GET/POST /api/design-elements/`、`GET/PATCH /api/design-elements/{id}/`；`frontend/src/api/designElements.ts` 提供类型化调用，`frontend/src/views/DesignView.vue` 承载编辑与详情。
- 模板：`GET/POST /api/production-templates/`、`GET/PATCH /api/production-templates/{id}/`；`frontend/src/api/productionTemplates.ts`、`views/ProductionTemplatesView.vue`、`components/ProductionStepsEditor.vue` 对应列表、编辑与步骤。
- 生产实例化：`GET /api/design-elements/{id}/production/`、`POST /api/design-elements/{id}/instantiate/`；POST 携带 template_id、template_version、expected_version、milestone_id；`components/ProductionPanel.vue` 承载现有入口。
- Mission：`GET/POST /api/missions/`、`GET/PATCH /api/missions/{id}/`；`components/MissionForm.vue`、`views/MissionCreateView.vue`、`views/MissionDetailView.vue` 和 `components/MissionDetailDrawer.vue` 承载编写与详情。
- 提交/验收：`POST /api/missions/{id}/submit/`、`GET /api/missions/{id}/submissions/`、`POST /api/missions/{id}/review/`。review 使用 submission_id、decision（accept/reject）、comment、verified_build_reference_id、expected_version；详情抽屉已有轮次展示与验收对话框。
- `frontend/src/api/missions.ts` 封装 Mission 调用；`api/types.ts` 定义 MissionCreatePayload、SubmitPayload、ReviewPayload、ProductionStep 等；`api/client.ts` 的 request 统一处理 Session/CSRF/错误。
- 现有数据流：Vue 表单 → src/api → DRF → missions/services.py → PostgreSQL/事件 → 序列化响应 → 前端更新。新增建议先回填表单，再走此链路，不增设绕过服务的自动保存入口。
- `components/MarkdownContent.vue` 负责安全 Markdown 展示。素材只能经 `/api/library/files/{id}/` 授权下载，Markdown 引用归属以现有服务校验为准，不能把私有下载地址作为模型已读取附件的证据。

### 8.3 现有测试入口与待新增目录

- 后端回归：`backend/missions/tests/test_design_elements.py`、`test_design_dependencies.py`、`test_production_templates.py`、`test_services.py`、`test_submissions.py`、`test_api.py`、`test_concurrency.py`、`test_markdown_references.py`；素材规则另见 `backend/library/tests/`。
- 前端回归：`frontend/src/tests/designElements.spec.ts`、`productionTemplates.spec.ts`、`missions.spec.ts`、`missionDetailActions.spec.ts`、`assetReferences.spec.ts`、`client.spec.ts`。
- 待新增建议：`backend/agent_bridge/` 及其测试；`frontend/src/api/agentBridge.ts` 和共用辅助面板/设备设置组件；`local_runner/` 放协议客户端、单一适配器与安装说明。以上目录/文件尚未实现，编码时按最终命名同步文档。

## 9. 本次规格交付记录

已核对当前模型、服务、接口、前端入口及测试路径；本次仅更新需求与技术原则，不修改运行时代码，不把上述待实现功能记录为已上线。实现与实际接入验证留待对应批次执行。
