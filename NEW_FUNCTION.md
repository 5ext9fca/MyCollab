# 第二批：Mission 手动委派美术资产

## 1. 实施状态与批次边界

第一批文本辅助已在提交 0869e0c 完成：设计/资产润色、生产模板生成、Mission 编写、验收辅助，及设备授权、轮询/租约/幂等、本地 OpenCode 2.1.3 适配器。现进入第二批实现；本文件完整替换旧规格，第一批事实已并入 PROJECT_STRUCTURE.md、TECH_STACK.md、README.md 与 local_runner/README.md。

第二批目标：本人认领的 InProgress Mission → 手动选择本人设备、图像生成或编辑、相关 Asset、要求及参考素材 → 本地模型产出/转换/预览候选 → 用户本地选择 → 仅上传选中成果到本人素材库 → 成果关联执行/Asset/Mission → 认领者人工提交 → 验收者人工验收。

第三批仍待实现：本地代码 Agent 在用户允许的隔离仓库工作区产出补丁与验证报告；不在本批引入代码执行、自动推送、PR、合并或部署。模型始终不是 Mission 的认领者。

## 2. 必须保持的边界

- 服务器及 SPA 不调用模型提供商、不接收供应商凭据、不下载提供商输出 URL、不托管模型或 GPU；本地 Agent 环境负责认证、模型调用、结果下载、转换、预览与选择。
- 复用 Django/PostgreSQL 和已有设备 Bearer 认证，不新增 Redis/Celery/WebSocket、反向隧道或浏览器直连 localhost。
- 本地 Runner 主动短轮询；文本和图像共享每设备单执行限制。候选等待选择不重复生成；断线、超时、撤销、取消都不能自动再次收费调用。
- 服务器只接受明确选中的文件，未选候选仅有有界元数据，不上传缩略图。所有上传复用 library/services.py，所有 Mission/成果业务写入经 missions/services.py。
- 生成、上传及候选选择不自动提交/验收 Mission；人工提交仍遵守版本、认领者、依赖和冻结规则。

## 3. 委派、版本与参考素材

- 入口在 Mission 完整详情及详情抽屉，只有当前有效认领者且状态 InProgress 能创建委派；管理员不替代认领者执行。历史成果可由有效团队成员查看，与任务可见性一致；本机执行输入与设备令牌仍按本人隔离。
- 必选一个当前 Mission 关联的未归档 Asset；保存 Mission 版本、Asset 版本、标题/说明/验收标准快照、用户指令与显式选中的参考素材。不得自动抓取 Markdown 外链。
- 参考素材只能从本人素材库逐项选择，限静态图片且数量/总量有界；编辑至少选一张。设备仅能在本次执行有效期间下载明确授权的参考 ID，不能枚举或下载其他素材。
- 新执行带客户端幂等键；相同键/相同输入重发不重复生成，键冲突返回 409。每次显式重试/修改要求生成新执行并关联上次执行，候选版本单调递增且保留旧成果。
- 领取、心跳、选中确认、文件上传和完成时检查设备、用户、任务认领者/状态/基础版本、Asset 版本及关联；变化时过期并拒绝迟到上传，重新生成由人明确决定。

## 4. 交接与候选选择协议

- AssistanceRequest 扩展 image_generate/image_edit 与 awaiting_selection 状态，复用设备、attempt_id、幂等键、配额及领取通道。
- 新 MissionExecution 关联 AssistanceRequest、Mission、Asset、发起者、输入版本及前次执行；候选序号/版本、SHA-256、文件名、大小、尺寸与格式为有限元数据。新成果关联记录保留选中候选到本人 LibraryFile 的映射。
- 状态流程 queued → running → awaiting_selection → succeeded；任一步可 failed/cancelled/expired。running 继续 180 秒租约；图像执行总限时 30 分钟，候选等待选择最多 24 小时；终态不自动派发。设备只执行一个 running，awaiting_selection 不占计算槽但计入用户活动上限。
- 本地生成后保存到专用输出目录，校验并转成允许的静态图片格式，生成本地预览。最多 4 个候选、单张最多 20 MiB；服务器只收有界清单，不接收提供商 URL、本机绝对路径或供应商原始日志。
- 用户在本地预览后使用显式选择命令确认候选；Runner 先提交选择集合，再只上传集合内的文件，全部成功后确认完成。选择不自动发生；批处理/非交互运行也不能默认选中全部。
- 上传绑定 execution/attempt/candidate/hash，重复同一文件幂等，不同文件不能覆盖候选；服务器验证文件大小、格式/尺寸、摘要与清单。上传失败只重试相同文件，不再调用模型。部分上传明确显示状态，已明确选中的文件保留本人素材库，不能误记为完整执行成功。
- 取消阻止继续上传与完成，本地尽力取消模型任务；撤销/超时不能保证提供商退费。迟到结果与重复终态遵守不可覆盖规则。本地候选提供人工清理命令/说明，服务器历史清理不能删除已入库成果或提交证据。

## 5. API 与界面

浏览器 Session+CSRF：创建/列表/详情/取消 MissionExecution；仍由原 /api/missions/{id}/submit/ 与 /review/ 完成人工流转。委派界面包括设备能力、Asset、生成/编辑、要求、参考素材、输入预览、状态/取消、历史版本和已上传成果；生成前明确未配置/离线等待，绝不转交服务器。

Runner 专用 Bearer：复用 claim/heartbeat；增加本执行参考文件读取、候选清单、选择集合、选中候选文件上传及完成端点。令牌只允许本人设备的当前执行，不开放通用业务 API 或通用素材库写权限。

上传成果页面提供预览与引用到提交草稿；引用只回填草稿，人仍确认提交。提交轮次保存执行成果关联，禁止跨任务、未上传、取消/失败执行或他人文件冒充本次成果；历史引用不可因后续候选替换而改变。

## 6. 本地适配器与凭据

第一批 OpenCode 文本适配器保留其禁用工具限制，不将文本 CLI 当作默认图像能力。第二批需要一个真实可调用的图像生成/编辑适配器；用户已选择 Codex CLI，适配器锁定已验证的 0.164.0，使用本机 ChatGPT 登录与原生图像工具。

服务器只保存能力标识，图像提供商 URL/API Key、ComfyUI 工作流、模型权重、输出目录及可执行命令只在本地配置。服务器不得下发任意 Shell 命令或任意本机路径。协议先与提供商无关实现，适配器的真实参数、认证、超时与取消行为须按选定环境核对官方文档并记录。

## 7. 验证与交付标准

- 自动化测试不依赖收费提供商：确定性假图像适配器覆盖生成/编辑、参考文件、候选清单、本地明确选择、仅选中上传、人工提交/验收闭环。
- PostgreSQL 验证权限/版本/Asset 关联/归属、设备撤销/停用、并发领取及候选版本、幂等创建/上传、超限/伪造格式/摘要/路径、取消/断线/租约、迟到结果与部分上传；首批文本能力回归。
- 前端验证只有本人 InProgress 可委派、预览不执行、无自动选择/上传/提交、历史成果引用及过期处理。Runner 测试凭据不传服务器、参考/输出地址校验、本地路径隔离和停止/恢复逻辑。
- 完成一个真实图像生成及编辑接入验证，记录实际环境、结果和未完成项；仅 mock 通过不能宣告真实适配器验收。
- 后端依次 makemigrations --check --dry-run、check、test；前端 type-check、test、build；本地 Runner 测试。同步 PROJECT_STRUCTURE.md、TECH_STACK.md、README.md、本地安装/绑定/预览/选择/清理说明；验证后提交，不推送。

## 8. 实施前核对的代码结构（基线 0869e0c）

- backend/agent_bridge/models.py：AgentDevice(owner/name/capabilities/token_digest/expires_at/revoked_at/last_seen_at)，AssistanceRequest(kind/object_id/base_version/submission_id/input/status/attempt_id/lease/result/retry/idempotency)，仅四种文本 kind。每设备一条 running 的条件唯一约束。
- agent_bridge/services.py：create_device、create_request、claim、heartbeat、finish、cancel；短事务、用户配额、版本/权限检查；create_request 当前仅接受文本。authentication.py 的 DeviceAuthentication 只挂 Runner 端点。serializers.py 严格拒绝未知字段；urls.py 挂 agent-devices/assistance-requests/agent-runner。
- backend/missions/models.py：Mission 当前 assignee/status/version、assets 多对多；DesignElement 的 Asset 与 Design 同级且有 version/archived。MissionSubmission 轮次不可覆盖，有 current_submission、source/build 引用和人工验收结论，尚无 MissionExecution/图像成果关联。
- backend/missions/services.py：业务写入口；团队事务锁和 select_for_update 保护任务结构/状态；submit_mission 创建不可变轮次，review_mission 人工验收，已有 Markdown 所有权校验。
- backend/library/models.py：LibraryFile(owner/file/original_name/content_type/size)，文件路径 library/<owner_id>/<uuid>；services.save_library_file 校验扩展名和大小并保存，delete_library_file 仅本人删除；views._file_response 授权流式下载且 nosniff。普通下载团队可读，列表仅本人；设备令牌不能访问此 API。现有库没有图像解码与像素校验，第二批需补充上传验证而不让服务器执行转换。
- local_runner/__main__.py：BridgeClient 仅根地址 HTTPS（本机开发例外）、拒绝重定向、设备认证；claim→OpenCode→result，30 秒心跳、同结果最多重传三次；opencode.py 专用临时目录、标准输入、禁用工具；协议复用 backend/agent_bridge/protocol.py。
- frontend/src/components/AssistancePanel.vue：首批候选预览/逐字段采纳；views/AgentDevicesView.vue：设备及历史。MissionDetailView.vue 有成果提交草稿、参考元数据、人工提交/验收；MissionDetailDrawer.vue 有详情与验收入口。api/library.ts 提供本人素材列表、上传与 Markdown 引用；api/client.ts 统一 Session/CSRF/错误。
- 测试入口：backend/agent_bridge/tests/test_bridge.py、test_live_opencode.py，missions/tests/test_submissions.py、test_concurrency*.py，library/tests/；frontend/src/tests/agentBridge.spec.ts、missionDetailActions.spec.ts、assetReferences.spec.ts；local_runner/tests/test_runner.py。

## 9. 实施记录

2026-10-26，第二批已实现：Mission 详情/抽屉委派、输入预览、授权参考、候选版本、本地预览与显式选择、选中 PNG 幂等上传、成果入库、提交轮次关联及人工验收。实际使用 Codex CLI 0.164.0 完成白底叶片生成与参考图改色编辑；真实模型图片仅保留在本机测试目录。

验证结果：后端迁移一致性与 check 通过；全量 PostgreSQL 回归 257 项通过（1 项需显式启用的真实文本模型测试跳过），随后新增/完善的图像测试集 13 项通过，含真实 HTTP 确定性生成/编辑闭环与并发版本；前端 type-check、131 项测试、生产构建通过；本地 Runner 12 项测试通过。构建仅有既有大 chunk 提示。未进行人工浏览器逐页验收，页面交互由组件测试覆盖。

PROJECT_STRUCTURE.md、TECH_STACK.md、README.md 与 local_runner/README.md 已同步。服务器无供应商通信/认证、图片转换或新队列依赖；第三批代码 Agent 仍待实现。
