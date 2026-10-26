# 第三批：Mission 手动委派规则/代码实现（OpenCode）

## 1. 目标与已有事实

第一批文本辅助已于 0869e0c 完成，第二批 Codex 图像委派已于 01010a5 完成。本批开始时工作区干净；当时已有设备 Bearer、短轮询、租约、幂等、图像成果与人工提交，尚无代码委派或仓库配置接口。本文件完整替换第二批规格。

本批实现：本人认领的 InProgress Mission → 选择本人 OpenCode 设备和本地仓库配置标识 → 预览任务与要求 → 本地导出已配置 Git 基线到独立工作区 → OpenCode 读取/修改代码 → Runner 执行本地允许的验证 → 本地检查补丁与报告 → 显式发布成果 → 人工提交 Mission → 人工验收。

用户已指定使用隔离示例仓库做真实接入验收；不得据此让模型修改本项目工作区。自动推送、PR、合并、部署及跨设备调度不在本批范围。

## 2. 服务器负担与信任边界

- 所有供应商通信、模型认证、Git/依赖凭据、工具链和运行资源均在本地。服务器不拉取仓库、不运行模型或验证命令、不下载外部结果、不新增执行队列或沙箱服务。
- 服务器只接收本地仓库标识（字母数字、下划线、短横线），不接受本机路径、仓库 URL、任意 Shell 命令。设备仅领取显式分配的任务。
- 代码与图像、文本共享每设备一条 running 和每用户三个活动请求。运行限时 30 分钟，心跳 30 秒、租约 180 秒；生成结束后等待本地审查最长 24 小时。取消、断线和超时均不自动重做模型调用。
- OpenCode 2.1.3 使用专用非交互 Agent；只允许隔离副本中受限路径的文件读取/修改，禁止模型 shell、外部目录、集成、子 Agent、网页访问与自动格式化。验证由 Runner 按本地命令数组执行，不使用 shell=True，不接受模型/服务器给出的命令。
- 隔离副本保护原仓库及未提交文件，不等同于操作系统安全沙箱。用户配置验证命令即授权在本机执行该仓库的验证代码，权限与本机工具链相同；不宣称能隔离恶意测试代码。凭据不传给模型工作目录或上传服务器。

## 3. 本地仓库与执行

本地 JSON 配置增加 repositories：每个标识含绝对 repository 路径、baseline（默认 HEAD）、允许修改的相对路径范围及 verification 列表（id、显示名、argv、timeout）。配置不上传；网页输入标识，未知标识明确失败。可列出本地标识及验证摘要供配置核对。

- 固定解析基线提交 SHA，不取工作区未提交/未跟踪内容；独立导出到每次执行的私人目录，无源仓库共享 .git 写权限、远端配置或 hooks。源仓库不需要 clean，但其脏改动不可被覆盖或包含在补丁。
- 有界导出，拒绝路径穿越、符号链接、子模块及特殊文件；排除 Agent 配置、凭据目录和本地秘密文件。模型仅能修改本地允许范围，完成后再次检查路径、文件类型和体积。
- 补丁由 Runner 从基线与实际文件差异生成，含新增/修改/删除，非模型自报。记录基线 SHA、补丁摘要、文件变更清单。无变化明确报告，不能伪造成功补丁。
- 验证逐项执行本地白名单命令，记录真实退出码、时长与 passed/failed/timeout/not_run；未配置、超时、失败不能伪装通过。原始日志保留本地且有界；上传报告不包含环境变量、原始日志或本机绝对路径。报告明确为本地证据，非服务器独立验证。
- 生成不会上传补丁正文。用户先查看本地补丁与报告，再显式发布该执行的同一成果。上传失败只重传相同内容，不能触发模型重跑。取消与版本变化拒绝迟到交付；人工新执行记录前次关系和递增版本。

## 4. 数据与 API

- AssistanceRequest 新增 code_implement，复用 queued/running/awaiting_selection/succeeded/failed/cancelled/expired。
- 新 CodeExecution 关联 request、mission、actor、mission_version、repository_key、version、previous，记录待发布成果清单及发布后补丁/报告。补丁以本人 LibraryFile 保存，报告严格 JSON；最多 2 MiB 补丁、128 KiB 报告、200 个变更路径、20 项验证。服务器只做结构/体积/摘要验证，不执行补丁。
- 浏览器 Session+CSRF：创建/分页列表/详情/取消 code-executions；创建带 expected_version、设备、仓库标识、要求、幂等 UUID、可选 previous。
- Runner 专用 Bearer：代码清单和显式发布接口，绑定 device/request/attempt；通用 result 仅允许固定错误码。任何普通 Mission/素材业务 API 不接受设备令牌。
- 创建、领取、心跳、发布时复核有效账号/设备、任务状态/认领者/版本。业务写入由 missions/services.py 导出，事务锁及幂等与现有规范一致。
- 人工提交支持 code_execution_ids，只允许当前任务/本人、已发布且版本有效的执行；提交轮次保留补丁与报告证据，不允许取消已引用执行或删除历史成果。清理老请求输入不能破坏执行/提交记录。

## 5. 页面与交付

Mission 完整详情和抽屉提供代码委派卡片，包含设备、仓库标识、要求、输入预览、离线等待、运行/审查/发布状态、取消、新版本及成果历史。生成不自动提交；“引用到提交草稿”仅回填成果与证据，仍由人确认。测试失败/未运行必须清楚展示，并标注本地报告的来源。

设备页面增加代码实现能力。补丁下载与本地应用说明必须要求用户检查基线和差异；不提供自动推送或自动应用到原仓库的流程。同步 PROJECT_STRUCTURE.md、TECH_STACK.md、README.md 和 local_runner/README.md。

## 6. 当前项目结构

- backend/agent_bridge/models.py：设备、请求种类/状态/租约和每设备单运行约束；services.py 实现设备/请求生命周期、配额和 stale_reason；serializers.py 严格输入校验；views.py/urls.py 提供 Session 与独立 Bearer 入口。
- backend/missions/models.py：Mission 五态/认领者/version、MissionSubmission 不可变轮次、图像 MissionExecution/ExecutionCandidate/SubmissionExecutionArtifact。代码执行需要独立模型，不要求关联 Asset。
- backend/missions/services.py：所有业务写入口，submit_mission 已检查图像成果归属与版本；execution_services.py 为图像专用。代码服务新增独立模块并由公共入口导出。
- backend/library/services.py：本人文件保存/删除，允许 txt/md/图片等，图像成果文件禁止删除；补丁可使用文本文件交付，下载沿用授权 API，不能添加公开媒体地址。
- local_runner/__main__.py：claim 分发文本/图像，BridgeClient 拒绝重定向，供应商信息不经服务器。opencode.py 是第一批禁止一切工具的文本适配器，不能直接放开它的权限；新增代码专用适配器。images.py 提供本地生成/显式选择、幂等重传模式。
- frontend/src/api/agentBridge.ts、executions.ts：设备/文本/图像类型与客户端；MissionExecutionPanel.vue 为图像专用。MissionDetailView.vue 管理人工提交草稿与验收，MissionDetailDrawer.vue 展示详情/历史；MarkdownContent.vue 清洗动态文本。
- 现有测试：agent_bridge/tests/test_bridge.py、test_images.py、test_image_roundtrip.py；local_runner/tests/test_runner.py、test_images.py；frontend/src/tests/missionExecution.spec.ts、missionDetailActions.spec.ts。

## 7. 验收

1. 确定性测试覆盖创建→领取→本地修改→实际 diff/验证→本地明确发布→人工提交/验收，服务器进程禁止外网。
2. PostgreSQL 覆盖权限/状态/版本、设备撤销/失效、共享并发领取、幂等、取消/租约/迟到发布、补丁与报告伪造/超限、历史保留和提交归属。
3. 本地覆盖固定基线与原仓库脏改动不变、路径/符号链接/仓库配置隔离、允许范围、真实命令成功/失败/超时、取消、补丁新增删除、明确发布与重传不重做模型。
4. 前端覆盖本人 InProgress 限制、预览不执行、执行不自动采纳/提交、版本过期、失败报告与人工引用。
5. 用用户授权的隔离示例仓库与本机 OpenCode 完成真实代码修改、真实测试及可应用补丁验证。不得以 mock 冒充真实接入。
6. 后端迁移检查→check→test；前端 type-check→test→build；本地 Runner 回归。文档同步后提交，不推送。

## 8. 实施与验收记录

2026-10-26，第三批代码链路已实现：本人 Mission 委派、仓库标识、隔离 Git 基线、OpenCode 受限文件修改、实际 diff、本地允许命令验证、本地审查/显式发布、补丁/报告历史、人工提交与验收。服务器不承担模型通信或代码执行。所有入口、模型与限制已同步 PROJECT_STRUCTURE.md、TECH_STACK.md、README.md、local_runner/README.md。

- 真实 OpenCode 2.1.3 / deepseek/deepseek-flash 在用户选择的隔离示例仓库实现负数归零/非负数加倍；真实 unittest 退出码 0，补丁对原基线 apply --check 通过。初次验证发现继承 PWD 导致 Location 错位，误生成的测试文件已移除，修复 cwd/PWD 后复测通过并增加回归，不把失败计作成功。
- 真实对抗示例仅修改允许文件，未读取并输出外部哨兵、未改保护文件、未产生 shell 目标文件。运行测试代码仍是本机授权，不宣称 OS 沙箱隔离。
- PostgreSQL 全量 268 项完成（267 通过、1 项显式真实文本模型测试默认跳过）；最终修正与新增检查后，桥接/代码/真实 HTTP 闭环定向 29 项通过。迁移一致性和 Django check 通过。
- 前端 type-check、135 项测试、生产构建通过；本地 Runner 28 项通过。补丁新增/修改/删除、原仓库脏改动不变、路径/链接、导出基线核对、退出码/失败/超时、未知仓库、无差异、人工发布和幂等重传均有验证。
- 页面由组件测试验证；真实模型调用与 HTTP 确定性闭环分别验证，未宣称人工浏览器逐页验收。保留现有构建大 chunk 提示，不影响构建成功。

本批不包含自动应用回原仓库、Git 推送、PR、合并、部署或通用 OS 沙箱；无上述功能的隐式授权。
