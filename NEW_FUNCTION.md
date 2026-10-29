# 新功能：迁移 Electron 并交付 Windows / macOS 完整桌面客户端

## 1. 决策、目标与状态

用户已确认：开发完整桌面客户端，支持 Windows 与 macOS，桌面宿主从 Tauri 迁移至 Electron。当前目标调整为“完成完整客户端，除正式发行”，已明确允许恢复 GUI 测试与验收；签名、公证、发布和真实线上更新不作为本阶段完成条件。下文正式发行设计保留为未来规格。本文件替换此前已归档的统一 Agent Panel 方案，是本次完整需求与分阶段开发计划；现已进入实现阶段；除下方进度明确列出的模块外，其余新增能力仍待实现。

交付目标是用户安装一个 App 后，在其中完成现有 MyCollab 业务流程、本地 Agent 配置与运行、文件直传，不再依赖浏览器承载主要业务页面。保留 Web 端，两个入口复用同一套 Vue 业务代码和 Django 服务。

“完整打包”包括 Electron、Chromium、Vue 静态资源及内置 Python 的 Runner 可执行文件；不包括把 Django/PostgreSQL 部署到每台用户电脑。OpenCode 仍由用户本机安装并完成供应商登录，App 提供检查与引导；不得宣称包含模型账户、模型费用或离线推理环境。

首批目标平台为 Windows x64、macOS arm64 与 x64，分别构建与验收；Windows arm64 和 Linux 不在本次承诺范围。最低系统版本在第一阶段依据所选 Electron 的官方支持范围确定并记录，不凭开发机成功推定所有系统受支持。

## 2. 当前已实现的基础与缺口

### 2.1 业务前端

`frontend/` 使用 Vue 3、TypeScript、Element Plus、Pinia、Vue Router 与 Vite：

- `src/router/index.ts` 使用 `createWebHistory()`，已有登录、注册、我的工作、任务广场、工作区、任务创建/详情、认领/发布列表、里程碑、设计、生产模板、素材库、通知、设备、文件直传和 `/manage` 管理页；路由守卫区分登录与管理员。
- `src/api/client.ts` 统一请求、FormData、取消信号、CSRF 与 `{code, message, field_errors}` 错误。当前依赖相对 `/api/`、`credentials: 'same-origin'` 和 `document.cookie`，不能原样假设适用于本地页面访问远程 Django。
- `src/api/auth.ts` 提供 `/api/auth/login/`、`logout/`、`me/`、`register/`；`client.ts` 从 `/api/auth/csrf/` 初始化 CSRF。`src/stores/auth.ts` 保存业务登录状态。
- `src/api/library.ts` 以 FormData 上传，Markdown 使用接口返回的文件 URL；私有图片、链接与下载不全部经过 JSON 请求封装，迁移时必须覆盖资源加载链路。
- `src/components/MarkdownContent.vue` 负责清洗 Markdown；`src/style.css` 提供卡片与 `app-link` 规范。桌面整合继续复用。
- `src/api/agentBridge.ts` 提供设备及文本辅助请求；当前包括四类文本辅助与 `agent_requirements` 需求文档整理导出。不得把旧方案中的图像执行、代码委派、交互会话或远程工具审批当作主分支已有能力。

### 2.2 后端、模型与数据流

服务端继续使用 Django/DRF/PostgreSQL：

- `backend/accounts/` 提供 Session 登录、用户与注册审批；桌面普通业务身份与 Runner 设备身份必须分开。
- `backend/missions/services.py` 承载 Mission 业务写入，保留事务锁、状态机与 `expected_version` 乐观锁，冲突仍返回 409；客户端不能直接修改数据库或绕过服务层。
- `backend/library/` 文件按用户隔离，经 `/api/library/files/` 上传/列表、`/api/library/files/{id}/` 授权访问/删除；禁止公开 MEDIA_ROOT。Markdown 仍只允许作者自己的素材引用及允许的外链。
- `backend/agent_bridge/models.py` 的 `AgentDevice` 有 owner、capabilities、token_digest、expires_at、revoked_at、last_seen_at；设备令牌服务端仅存摘要。
- `AssistanceRequest` 有 owner/device、kind、input/result、base_version、submission_id、status、claimed_at、attempt_id、lease_expires_at、expires_at、stopped_at、retry_of、idempotency_key、payload_digest。状态为 queued/running/succeeded/failed/cancelled/expired；每设备最多一个 running，保留幂等与租约校验，不新增重复状态机。
- `backend/agent_bridge/urls.py` 提供 `/api/agent-devices/`、设备 `revoke/`、`/api/assistance-requests/`、请求详情与 `cancel/`；浏览器业务接口使用 Session + CSRF。Runner 使用设备 Bearer 访问 `/api/agent-runner/status/`、`claim/`、`requests/{id}/heartbeat/`、`result/`，不能将此令牌用于一般业务 API。

现有数据流为：业务前端提交辅助需求 → Django 有界交接 → 本地 Runner 领取并调用 OpenCode → 幂等回传结果 → 用户审阅/采纳或导出文档。迁移仅改变桌面承载与本地接入体验，不自动提交 Mission、验收、执行代码、push 或部署。

### 2.3 桌面伴侣与 Runner

- `desktop/src/App.vue` 是独立配置面板；`desktop/src/bridge.ts` 调用 Tauri 的配置读写、自检、Runner 启停/状态、网站打开、自启动及更新命令。
- `desktop/src-tauri/src/main.rs` 已有原生命令、托盘、单实例、关闭隐藏、父子进程生命周期和更新互斥；只加载本地页面。当前不是完整业务客户端。
- `desktop/scripts/build_sidecar.py` 使用 PyInstaller 打包 Runner，明确只支持 macOS/Python 3.13；当前产物实际验证过 macOS arm64，不能据此宣称 Windows 或 Intel 已支持。
- `local_runner/__main__.py` 负责配置、BridgeClient、领取、执行、自检、状态与父进程监测；`local_runner/opencode.py` 调用 OpenCode，当前接受的精确版本为 2.1.3 与 2.2.0。
- `local_runner/state.py` 按服务器和设备令牌派生隔离目录，原子保存结果后再上传；待发箱最多 100 条、每条最多 512 KiB、保留 24 小时。恢复只重传原结果，不自动重新调用付费模型。
- 现有 POSIX `fcntl.flock`、`os.fchmod`、进程组信号与父 PID 探测需要 Windows 适配。只把 Rust 换成 Node 或生成 `.exe` 不等于完成跨平台移植。
- 原 macOS 配置位于 `~/.config/MyCollab/mycollab-runner.json`；配置与待发箱迁移需保留设备身份，避免两个宿主同时启动同一设备。

### 2.4 文件直传

`frontend/src/transfers/controller.ts`、`protocol.ts`、`views/FileTransferView.vue` 及 `src/api/transfers.ts` 实现 WebRTC DataChannel 直传；`backend/transfers/urls.py` 提供 `/api/file-transfers/`、`join/` 和会话操作接口。Django 只承担有界信令，文件不经服务器中转。

当前 `iceServers: []`，无 STUN/TURN；单文件最多 100 MiB，接收端校验大小与 SHA-256 后才允许成功/下载。没有后台接收、断点续传或多 GB 承诺。已有 Chrome 默认 mDNS 连接失败而测试专用原始 IP 候选通过的记录，说明 Chromium 不能替代网络可达性验证。

## 3. 目标架构与强制边界

### 3.1 统一前端与桌面宿主

- `frontend/` 保持唯一业务页面实现；新增平台适配层，区分 Web 的浏览器能力与桌面的窄接口。禁止复制整套页面到 `desktop/` 后分别维护。
- `desktop/` 改为 Electron 主进程、preload、打包与桌面测试入口；建议新增 `desktop/electron/`，具体文件拆分由实现确定。主进程管理窗口、会话、资源访问、Runner、托盘、文件对话框、凭据与更新。
- 渲染进程加载随包分发的 Vue 资源。使用明确的应用协议/路由回退方案，覆盖刷新、深链和资源路径；不能仅用 `file://` 打开产物后忽略路由与安全上下文。
- 本地控制页并入业务导航；Web 端继续提供原有业务页面，对仅本地可用操作给出准确说明。
- Electron/Chromium 版本固定并记录，建立定期安全升级与回归流程；开发用 Node 版本不等于 Electron 内置 Node 版本。

### 3.2 认证与文件访问

首选方案是主进程持有按服务器隔离的业务会话，以受限请求适配层复用 Django Session + CSRF。第一阶段必须完成登录和私有图片的可运行验证，确定 Cookie 保存、CSRF 获取/轮换、请求 Origin/Referer、资源协议与重定向规则；普通浏览器认证规则不得放宽。

- 不向 renderer 暴露 HttpOnly 会话值、已保存设备令牌或供应商凭据；不保存用户登录密码。
- 请求仅能到用户配置并验证的服务地址及允许的业务路径/方法；禁止任意 URL 代理、任意请求头注入、跨源重定向携带凭据或将业务凭据发给 Markdown 外链。
- 统一处理 JSON、multipart、私有图片、下载、导出、取消、错误码与会话过期；大文件使用有界流/分块，不通过通用 IPC 复制无限制缓冲。
- Markdown 中持久化的素材链接保持现有规范，桌面映射仅在显示/访问层处理，不能把本机协议或绝对路径写回服务器。
- 切换服务器或账户、退出登录时停止当前 Runner 和轮询，清理对应渲染状态、资源 URL 与会话，阻止旧响应进入新账户界面；旧设备待发箱仍隔离保存，不能转交新身份。
- HTTPS 严格校验证书；若支持自定义 CA，应限定到指定服务器并覆盖业务与 Runner 请求。禁止关闭证书校验、全局关闭 Web 安全或取消服务端 CSRF 检查。
- 若上述会话方案无法满足约束，先更新本规格和相关认证规则，明确替代协议与测试，再实施；不得悄悄用设备令牌替代用户登录。

### 3.3 本地权限边界

renderer 禁用 Node integration，启用 context isolation 与 sandbox；preload 只暴露固定、可校验的操作，不暴露通用 shell、文件系统、IPC 或 HTTP 客户端。主进程校验调用来源、参数、路径与当前身份；严格限制导航、新窗口、权限请求及外链协议。远程网页和用户 Markdown 不获得本地 Agent 控制权。

设备凭据采用系统保护存储，配置与待发箱按当前 OS 用户隔离；Windows 使用实际 ACL/平台机制，不把 POSIX chmod 当作同等保障。Runner 读取凭据的交接方式必须避免命令行参数、日志与模型子进程继承泄漏。首次配置可受控导入旧配置，保存后不再回显令牌。

## 4. Windows / macOS Runner 与桌面体验

1. 抽取平台相关的文件锁、原子写入权限、进程树终止和父进程存活机制。Windows 可采用 Job Object 等受控进程树方案，必须验证宿主崩溃后模型子进程不遗留；不能仅终止直接子进程。
2. 针对三个目标架构，在相应系统构建独立 Runner；安装后不要求 Python、Rust、Node 或源码。验证带空格/中文路径、CLI 路径、证书路径和权限错误。
3. 保留租约、取消、退避、状态、待发箱与结果幂等语义。网络失败、App 崩溃或更新不得触发重复模型调用；401/403、撤销和过期必须明确停止。
4. 将设备创建/绑定、模型与 OpenCode 路径、诊断、启动/停止、脱敏状态、待发结果提示整合进客户端。设备必须属于当前用户和服务器，绑定不成立时禁止启动。
5. 实现托盘、单实例、关闭隐藏、明确退出和可选开机启动；首次安装不默认自动启动 Runner。切换身份与退出要等待停止结果，异常时显示真实状态。
6. 隐藏窗口期间允许已启动的 Runner 按设置继续运行；退出必须停止。文件直传首批仍要求页面保持打开，不承诺隐藏/休眠期间持续传输；发生中断必须有提示和重试入口。
7. macOS 旧伴侣采用受控导入与手动安装新客户端的迁移路径；校验旧进程已停止后再启用新宿主，不能假设 Tauri updater 可直接更新为 Electron。导入失败保留原文件与可恢复信息，不自动删除旧待发箱。

## 5. WebRTC 专项要求

Electron 内核一致性是迁移收益之一，不作为默认网络一定可用的证明。保留当前协议与完整性校验，优先验证默认配置下的真实双机互通。

- 验证 Windows↔Windows、macOS↔macOS、Windows↔macOS，以及桌面客户端↔受支持浏览器；覆盖空文件、普通文件、100 MiB、篡改拒收、配对后取消、传输中取消与双方退出。
- 覆盖局域网权限拒绝/恢复、防火墙受限、VPN/多网卡、断网/重连、休眠/唤醒；部分网络允许明确失败，但不得假成功、无限等待或遗留会话。
- 记录 OS、架构、Electron/Chromium 版本、ICE 阶段、建立连接耗时、吞吐与失败分类；默认不上传原始 SDP、局域网地址或文件正文。
- 发布验收不得使用测试专用原始 IP 开关代替默认配置测试，不要求用户全局修改浏览器或系统安全设置。
- 本期仍为局域网直传，不新增 STUN/TURN 或服务端文件中转。若后续需要跨网成功率保障，另行定义中继部署、费用、隐私和访问控制，并同步现有技术约束。

## 6. 分阶段开发与完成条件

### 阶段一：Electron 骨架与纵向验证

确定 Electron、打包工具、最低 OS 与架构矩阵，添加锁文件和构建入口；搭建 main/preload/renderer 边界。使用现有 Vue 完成“选择服务器 → 登录 → 任务详情 → 私有图片 → 上传/下载 → 退出”的纵向流程，并运行最小 WebRTC 双机探针。

完成条件：Windows 与 macOS 都有可安装的开发验证包；认证/资源访问方案有实际证据，Web 端未回归；记录尚未覆盖的架构，不将探针成功写成完整客户端交付。

### 阶段二：迁移 Runner 与现有伴侣能力

完成第 4 节跨平台生命周期、系统凭据存储、设备绑定、诊断、单实例、托盘、自启动及旧配置导入。复用 Python 协议与恢复实现，不另造 Node 模型 Worker。

完成条件：两系统实际打包 Runner 通过“服务端已收结果但确认丢失”的恢复测试及宿主崩溃清理测试；不重复模型调用、不跨服务器/设备回传，旧伴侣与新客户端不会双重领取。

### 阶段三：整合完整业务前端

逐一覆盖当前所有业务路由：Mission 全流程与评论、工作区/图布局、设计/模板、里程碑、素材库、通知、注册审批及管理、本地文本辅助和 Agent 需求文档导出。统一导航、加载/错误状态和桌面设置；浏览器打开外链和本地保存使用平台适配层。

完成条件：桌面中可以完成原有完整业务操作，无须跳回浏览器；管理员与普通用户权限准确；CSRF、409 冲突、附件授权、Markdown 清洗、跨账户隔离和离线提示均有回归覆盖。离线时禁止伪装保存成功，本期不做离线编辑同步。

### 阶段四：WebRTC 与稳定性验收

执行第 5 节真实网络矩阵；测试窗口隐藏/恢复、长时间待机、系统睡眠、网络变化、App 异常退出与重开。测量冷启动、空闲内存、关键页面耗时、传输峰值内存和包体，记录可复现基线及明显回归，不能用主观“更快”代替数据。

完成条件：支持矩阵内的默认局域网环境能完成跨系统传输；受限网络能正确诊断/失败；测试报告标明设备和环境。未拥有的物理设备或未运行的场景明确列为未验收。

### 阶段五：安装、签名、更新与迁移收尾

建立 Windows/macOS 原生构建流水线，提供 Windows 安装程序和 macOS 安装产物；对实际发布包执行签名验证，macOS 完成 Developer ID 签名/公证，Windows 配置代码签名。更新端点固定、使用 HTTPS，验证更新包真实性与平台/架构匹配；私钥仅放发布环境。

覆盖全新安装、旧版升级、下载失败、签名错误、更新中断、运行中 Runner 的更新互斥与失败恢复。更新不能默认中断模型任务或悄悄重跑；停止后才可替换二进制。未配置证书或更新源时明确为开发验证包，签名分发和线上更新仍是未完成项。

功能与验收通过后删除废弃 Tauri 依赖、Rust 宿主、旧构建脚本及过期说明，保留仍复用的 Runner 入口与测试。同步 TECH_STACK、PROJECT_STRUCTURE、desktop/README；README/TUTORIAL 只增加已交付的用户安装和操作说明。不得把计划中的 Electron 描述成当前已运行实现。

## 7. 测试入口与交付规则

现有入口：

- 前端：`frontend/src/tests/client.spec.ts`、`library.spec.ts`、`agentBridge.spec.ts`、`agentRequirementsExport.spec.ts`、`fileTransferProtocol.spec.ts`、`fileTransferController.spec.ts`，以及其余业务组件测试；真实浏览器传输为 `frontend/e2e/file-transfer.spec.ts`。
- 后端：`backend/accounts/tests.py`、`backend/agent_bridge/tests/test_bridge.py`、`test_requirements.py`、`test_metrics.py`、`backend/missions/tests/` 和 `backend/transfers/tests.py`；浏览器隔离验收入口 `transfers.test_browser`。
- Runner：`local_runner/tests/test_runner.py`、`test_recovery.py`、`test_delivery_integration.py`、`test_testrun.py`。
- 旧桌面：`desktop/src/App.spec.ts`、Rust 宿主内测试和 `desktop/scripts/smoke_fixture.py`。迁移测试意图，不能仅删除旧测试而不验证替代行为。

新增 Electron 测试覆盖实际 main/preload 边界、拒绝非法 IPC、导航/外链限制、会话隔离、资源授权与打包后的 Runner 生命周期。使用假 CLI 做确定性测试；诊断不调用模型，真实供应商验收单独记录，不能用 mock 宣称供应商可用。

按改动范围执行：

- 后端：在 `backend/` 依次运行 `.venv/bin/python manage.py makemigrations --check --dry-run`、`check`、`test`；事务/并发测试必须使用 PostgreSQL。
- 前端：在 `frontend/` 运行 `npm run type-check`、`npm run test`、`npm run build`。
- Runner：使用 Python 3.13 执行 `python -m unittest discover -s local_runner/tests -v`；增加 Windows/macOS 各自打包后二进制验收，不能只测源代码。
- Electron：第一阶段建立并记录类型检查、测试、构建与安装包 smoke 命令；两系统运行实际产物。现有 Tauri 命令不作为新客户端验证命令。
- 每阶段提交代码、必要测试与已实现文档；所有新增数据模型/API/权限变化同步 PROJECT_STRUCTURE，技术约束变化同步 TECH_STACK 与适用规则。未来计划保持未完成标识，不提前修改当前实现说明。

最终交付需同时满足完整业务前端、跨平台 Runner、文件直传、安装与发行要求。不得以仅包裹远程网站、单平台开发包或只有 Electron 空壳作为“完整客户端完成”。

## 8. 本次范围外

不迁移 Django/Vue 技术栈，不嵌入本地数据库/服务端，不实现离线编辑同步、云端 Agent、远程终端、代码/图像执行、通用 Agent 聊天或工具审批；不恢复旧归档方案。不新增 TURN、中转存储、后台接收、断点续传或多 GB 文件支持。上述能力如需加入，另行定义业务权限与验收范围。

## 9. 实现进度与本次验证限制

用户已授权实施、推送独立分支、创建草稿 PR，并已恢复 GUI 测试与验收。以下历史非 GUI 结果不自动升级为 GUI 通过；正式发行排除在当前目标之外。当前工作在 [草稿 PR #1](https://github.com/5ext9fca/MyCollab/pull/1)，不合并、不发布。

### 已实现并完成非 GUI 验证的部分

- Electron 45.1.0 主进程、固定 preload、安全应用协议和共享 Vue 前端；服务器设置、单实例、托盘、关闭隐藏、可选自启动、局域网权限、系统外链及私有素材下载。业务 Session 与页面隔离，切换服务器/退出清理会话，停止失败保留身份。
- 主进程核验用户、服务器和设备归属，使用系统加密接口保存绑定；页面不回显令牌，系统保护不可用不退回明文。同一设备修改模型/路径可留空沿用令牌，重新绑定与启停互斥；macOS arm64 的真实系统加密保存与重新读取已通过 GUI 验收；Windows DPAPI 已通过下述原生 CI GUI 验收。
- Runner 内置 Python，匿名管道交接配置及停止指令；启动等待设备锁就绪，退出等待真实进程关闭。Windows 原生 DACL、文件锁、父进程句柄和 Job Object 进程树清理已在原生 CI 执行。
- 本地 Agent 页提供绑定、启停、自检、脱敏状态和待发摘要。本次已核验身份下可离线自检，启动仍在线核验。会话过期须经身份端点确认再停止 Runner、取消旧请求并清理；普通权限拒绝不误清登录。
- 默认 macOS 旧伴侣配置可受控导入，加密保存后原地复用待发箱与锁，不删除旧文件、不自动启动；自定义 CA 配置明确拒绝导入，GUI 迁移仍未验收。
- 手动检查、下载、停止 Runner 后安装更新；默认不自动下载、不随退出安装、不自动启动模型。正式构建强制签名和 macOS 公证配置；开发包禁用更新并隔离发行凭据。
- 本地 Agent/桌面设置的状态轮询卸载后停止，慢请求不叠加。Markdown 导出和已校验接收文件交给 Chromium 保存，身份切换/退出/安装更新取消未完成保存，中断给出通用错误提示；实际保存交互尚未验收。
- 用户指南区分新客户端与旧伴侣，说明连接、绑定、恢复、迁移、更新和使用限制；未把开发产物描述为正式发行。

### 原生 CI 的实际证据

2026-10-29（北京时间），提交 `2b32024` 的[三平台非 GUI 工作流](https://github.com/5ext9fca/MyCollab/actions/runs/40744537700)全部通过。首轮 PR 中打包器默认跳过 macOS 临时签名，导致两架构签名检查失败；修复仅在已剥离发行凭据的开发环境允许固定临时签名，未降低完整性检查。

- Windows x64：Electron 53 项中 51 项通过、2 项 macOS 旧配置测试跳过；Runner 39 项中 35 项通过、4 项 POSIX 专属测试跳过。Windows ACL/Job 实际执行通过。
- macOS arm64/x64：各自 Electron 53 项通过；Runner 各 39 项中 37 项通过、2 项 Windows 原生测试跳过。
- 三平台各自通过前端 29 项纯逻辑回归、类型/构建检查、发行归档脚本 3 项测试、独立 Runner 的 2 项断线恢复/宿主退出测试，以及包内 Runner 的匿名管道、中文路径、锁、自检、停止等检查；macOS 另外通过开发签名完整性检查。
- 三份 `desktop-<target>-development` 开发包已归档，保存七天；不包含正式安装/发行验收证据。Windows Server CI 不证明 Windows 客户端最低版本支持。
- 后端 PostgreSQL 回归此前完成 272 项（3 项按条件跳过），迁移与系统检查通过；本轮没有改后端，也没有重复运行后端回归。

### 开发安装包补充

已增加 `electron:dist:dev`，使用与开发目录包相同的凭据隔离和更新禁用策略，生成名称带 `development` 的 macOS DMG/ZIP 与 Windows NSIS。提交 `04239f0` 的[三平台 CI](https://github.com/5ext9fca/MyCollab/actions/runs/40746830510)已通过这一入口，实际生成并归档 Windows x64 NSIS 和 macOS arm64/x64 DMG/ZIP；未安装或运行 GUI。新增模式解析测试，两种 macOS 桌面非 GUI 测试各 54 项通过；Windows 52 项通过、2 项 macOS 专属跳过。构建目标已显式限定为本机架构，避免目标配置覆盖 CLI 后生成缺少 Runner 的异构包；本机 arm64 DMG/ZIP 构建、容器完整性及内置文件检查通过，未安装或启动。

### 仍未完成的工作

- 真实 Electron 会话、系统钥匙串/DPAPI、页面完整业务流程、权限交互和保存文件等 GUI 验收已获授权，继续逐项验证，不能用已通过的登录流程替代完整覆盖。
- 双机 WebRTC、网络/休眠矩阵和桌面性能基线仍未验收；共享 Chromium 或协议单测不替代这些证据。
- `.github/workflows/desktop-release.yml` 已提供正式包构建、签名、公证及归档入口，但发行环境、证书、公证身份和更新服务尚未配置，未生成或验证正式发行安装包，也未执行真实升级/中断恢复。
- 旧 Tauri 代码仍保留；按第 6 节，在替代客户端功能与验收通过后再清理，不以开发包构建成功宣称迁移收尾完成。

### 恢复 GUI 验收后的进展

已添加 `accounts.test_desktop` 与 `frontend/e2e/desktop.spec.ts`：独立 PostgreSQL 测试库、临时客户端配置，启动真实 Electron 宿主及真实 Django API，覆盖设置服务器、Session/CSRF 登录、任务广场导航、刷新保持登录、退出后不恢复登录，并确认 renderer 不获得 Node require 或 Session Cookie。本机 macOS arm64 已通过，留存截图与 trace；另已通过真实 multipart 素材上传、图片解码、私有文件字节读取及点击下载的流式落盘；退出后读取被拒绝，另一账号的素材列表隔离、允许读取引用素材但拒绝删除，普通权限拒绝不清除登录。下载测试仅替换系统保存路径选择，未验收原生保存对话框。上传文件使用临时 MEDIA_ROOT，随隔离测试清理。尚不是实际安装后验收，也未覆盖完整业务、Runner 界面或双机 WebRTC。

桌面业务 GUI 验收新增：通过真实页面发布任务、由发布者认领、提交人工验证说明并验收通过；刷新后读取实际 API 确认状态为 Done，验收记录仍显示。评论发布、编辑后刷新保留、确认删除均通过。本机 macOS arm64 的同一隔离验收同时回归登录、素材与账号隔离；这不替代多用户协作、子任务、其他业务路由或跨系统验收。

本地 Agent GUI 验收：本机 macOS arm64 使用真实 safeStorage 和内置原生 Runner，完成设备创建、绑定加密保存（磁盘密文不含测试令牌）、刷新读取且令牌不回显、自检、启动空闲轮询、手动停止及再次启动后退出登录。切换另一账号后显示已停止、无原设备/模型/令牌且启动禁用。OpenCode 指向不存在的隔离路径，验证自检报告 CLI 不可用而服务器通过；未执行模型或验证结果采纳。

跨平台 GUI CI 已接入 `.github/workflows/desktop.yml` 的三个原生目标：构建后安装 Electron 测试运行时，使用 `desktop/scripts/check_gui.py` 新建仅监听本机的临时 PostgreSQL 集群，再运行隔离 Django/Electron 验收并保存截图与 trace 七天。macOS 安装 PostgreSQL 16；Windows 使用运行器预装工具（当前为 PostgreSQL 17），不触碰运行器原有数据库目录或服务。测试结束停止临时集群。该新增远端流程尚待实际运行验证；不等同于安装器交互或最低操作系统版本验收。正式发行工作流复用此桌面验证入口，因而也会包含 GUI 验证，但当前不执行正式发行。

窗口生命周期 GUI 补验：Runner 空闲运行期间触发真实 BrowserWindow.close，确认窗口仍存在但已隐藏；重新显示后页面可操作且 Runner 继续等待任务。通过的是关闭隐藏与恢复行为，托盘菜单点击、登录系统后启动和系统休眠恢复仍需独立验收。

桌面直传排查记录：本机两个隔离 Electron 会话在默认 mDNS 候选下完成配对和 offer/answer 交换，但 45 秒内仍停在建立连接、未传输字节；仅为测试进程启用原始 IP 候选后，2 MiB + 7 字节直传、双方 SHA-256 校验、真实 Chromium Blob 下载落盘与磁盘摘要一致均通过。保存位置由测试固定，未验收原生对话框。产品未启用该开关，默认连接问题尚未解决，不能据此宣称默认网络或双机直传已通过。新增直传验收仍在工作区排查，尚未提交到 CI。

修复页面 beforeunload 阻止退出后客户端无法继续退出的问题：原生确认默认停留，取消后恢复退出控制状态并显示窗口，再次确认可正常结束进程。真实 Electron GUI 测试覆盖取消、窗口隐藏/恢复、再次确认退出；对话框选择由测试固定。桌面 54 项回归与严格类型检查通过。

提交 `44666bf` 的[三平台 GUI CI](https://github.com/5ext9fca/MyCollab/actions/runs/40813474508)已全部通过。Windows x64、macOS arm64/x64 均实际运行隔离 Django 与 Electron 窗口，覆盖登录、Mission 发布/认领/提交/验收、评论、素材上传下载及账号隔离、系统 safeStorage 加密保存/刷新读取、原生 Runner 自检/启停/退出停止。三个目标均生成开发安装包并归档截图与 trace。此提交不包含后续关闭隐藏、离开保护修复或尚在排查的直传测试，不代表安装器交互、所有业务路由、真实双机网络与正式发行通过。

桌面注册审批 GUI 已通过：新申请审批前拒绝登录，管理员批准后成员列表立即更新，新成员可登录，普通用户看不到管理入口且直接访问 `/manage` 会返回任务广场。验收修复了批准后成员列表仍使用旧数据的问题。前端 151 项测试、类型检查及构建通过；主题测试同步为加载实际外置 `theme-init.js`，不再假设内联脚本。

桌面业务 GUI 补验已通过：设计条目创建、编辑后刷新显示修订内容；里程碑创建、详情打开后刷新保留目标说明；工作台切换甘特图、保存个人筛选、刷新后恢复甘特视图与保存筛选名称。上述操作均通过真实页面与隔离 Django/PostgreSQL；不代表设计依赖、生产模板实例化、里程碑完整状态变更等所有分支已覆盖。

实际打包应用 GUI 验收：增加 `MYCOLLAB_TEST_APP_BINARY` 指定 App 可执行文件，测试传入临时 `--user-data-dir` 并断言 `app.isPackaged`。macOS arm64 开发目录包已通过核心业务、设计/里程碑/甘特筛选、私有素材、系统加密、包内 Runner、退出保护与注册审批。此验收发现并修复打包 ESM 主入口顶层等待 ready 的启动死锁；源码引导模式未能暴露该问题。三平台 CI 改为 `check_gui.py --app` 启动实际包内应用，远端新结果待确认。既有开发安装包需重新构建，不应再把旧包作为可启动验收通过的产物。直传对照仍使用源码宿主且不能证明默认连接可用；安装器交互尚未覆盖。

macOS arm64 开发安装产物已重新构建：从新版 DMG 只读挂载并复制 `MyCollab.app` 到 `desktop/build/安装验收 e669779/`，卸载镜像后通过签名完整性及实际 GUI 回归，覆盖包内前端、系统加密与原生 Runner。路径包含中文和空格。当前 DMG/ZIP 位于 `desktop/build/electron/`，哈希与源码提交记录在同目录 `local-validation.json`。此项验证安装副本运行，不代表 Finder 拖放交互、Gatekeeper、公证、其他平台安装器或默认 WebRTC 已通过。

新增 Windows CI 开发安装验收入口 `desktop/scripts/check_windows_install.py`：仅允许 GitHub Windows 运行器，使用实际 NSIS `/S /currentuser /D=` 安装到临时中文空格目录，检查 App 与 Runner 后调用打包 GUI 验收，再静默卸载并检查主程序消失。生成 `desktop/build/windows-install-validation.json` 并随 GUI 产物归档。工作流与脚本已通过语法检查，Windows 原生执行结果待 CI 确认；不代表安装向导交互、最低 Windows 客户端版本或正式发行通过。

本地 Agent 结果闭环 GUI 补验已通过：实际 macOS 安装副本内的 Runner 使用隔离假 CLI（固定结果、无供应商调用），重新绑定时留空沿用设备令牌，领取设计润色请求并回传；候选未自动更改表单，用户采纳标题后仍须手动保存，刷新后确认持久化。测试计数文件确认 CLI 仅执行一次。测试复用 Runner 原有跨平台夹具，Windows 使用 CI 已构建的原生假 CLI；本轮新增流程的远端结果尚待确认。

提交 `e669779` 的实际打包应用 CI 中，Windows x64 GUI 通过；macOS 两架构均在里程碑详情刷新处失败，日志表明测试点击后未等待路由切换便刷新。测试已增加详情 URL 和标题就绪检查，再执行刷新；本机 macOS arm64 安装副本的业务与 Runner 候选闭环回归通过。三平台修复后结果及 Windows 安装/卸载验收仍待新 CI 确认。


桌面直传诊断入口已独立为 `MYCOLLAB_DESKTOP_TRANSFER_TEST=1`（配合 `MYCOLLAB_DESKTOP_TEST=1` 运行 `accounts.test_desktop`），默认业务 GUI 套件不包含这项尚未通过默认网络验收的测试。可用 `MYCOLLAB_TEST_APP_BINARY` 指定实际安装副本；测试断言打包状态及临时配置目录。macOS arm64 安装副本已在 `MYCOLLAB_TEST_RAW_IP=1` 对照模式完成双会话 2 MiB + 7 字节传输、SHA-256 校验与下载字节验证；仅固定保存路径，未验证原生对话框。默认 mDNS 与真实双机网络仍未验收通过，不将诊断成功作为产品网络验收结论。

本机 GUI 复测曾连续超时（90 秒），用户随后确认此前长期阻塞来自 macOS 密码访问的手动权限确认。该记录不再作为已证实的客户端启动死锁或 trace 时序缺陷；自动化不能替代用户完成系统授权，也不能以放宽凭据保护规避。后续 macOS arm64 安装副本的三项业务 GUI 测试通过（45.2 秒），覆盖候选执行前 CLI 自检；系统授权等待与测试进程清理仍应单独处理。

Windows `243e60f` GUI 在候选执行时报 `local_failure`，尚不能确认根因。已为假 CLI 修正独立复现的编码问题：只消费原始输入字节，避免标准输入为 ASCII 等编码时因中文内容退出；新增回归通过，断线重传与宿主退出两项集成测试通过。GUI 另增加候选执行前的真实 CLI 自检，本机通过。该修复不代表 Windows 候选闭环或安装验收已通过，仍须远端复验。


Windows `7bd8052` 的 CLI 自检仍报告不可用，说明假 CLI 输入编码修复未解决该阻塞。新增自检失败固定分类以继续定位，严格过滤原始异常和输出；本机 Runner 41 项测试（2 项 Windows 专属跳过）、Electron 55 项及前端 151 项回归通过，类型检查与构建通过。远端具体失败类别及安装验收仍待下一轮确认。


桌面生产模板 GUI 补验通过：在实际 macOS arm64 安装副本中创建单步骤生产模板，刷新后重新读取；创建资产并选择模板、预览、生成待认领 Mission，刷新后生产批次及模板版本仍存在且不再提供重复生成入口。本机三项 GUI 测试合计 44.5 秒通过；多步骤依赖与生产任务完整协作仍需继续验收。双机开发验收步骤见 `desktop/ACCEPTANCE.md`，用户已确认有 Windows 实机可配合；实际默认网络矩阵尚未通过，本机默认 mDNS 双会话仍在 45 秒内未建立连接。


macOS arm64 开发安装包已更新至 `dbea94a`，从 DMG 复制的 `desktop/build/安装验收 dbea94a/MyCollab.app` 通过三项 GUI 回归（49.4 秒），包括缺失 CLI 的具体提示与正常 CLI 自检、候选回传和模板实例化。首次等待系统密码访问确认后，用户完成授权，重跑通过。DMG/ZIP 哈希和验收状态已更新至 `desktop/build/electron/local-validation.json`。

GUI 套件新增 `startup-baseline.json`：记录新进程到设置页可见的耗时、系统/架构、Electron/Chromium 版本与 `getAppMetrics()` 各进程内存快照（KB，按 Electron MemoryInfo 定义）。使用临时配置但未清系统磁盘缓存，启用 Playwright 与 trace，不包含 Runner；只用于后续同条件比较，不能视为纯冷启动、稳定空闲或传输峰值验收。JSON 直接落在 GUI 输出目录，随现有 CI 产物归档；本机副本保存在安装验收目录。


版本检查子进程的标准输入改为关闭输入（DEVNULL），不继承桌面宿主持续开启的停止控制管道；模型请求仍使用独立 stdin 管道传递上下文，Windows Job 保护保持不变。新增真实 HTTP/子进程回归：保持宿主控制管道开启，自检应返回 CLI/服务器通过且不产生模型调用；三平台 CI 的独立二进制测试也运行此项。本机 Runner 42 项测试通过（2 项 Windows 专属跳过）。Windows GUI 的最新失败分类是版本检查超时，本项是否解决该阻塞仍待 Windows 原生复验。


旧伴侣迁移新增隔离 GUI 证据：源码 Electron 宿主在加载前设置临时 home（仅测试引导脚本），真实页面导入默认旧配置，使用系统加密保存且令牌不回显，保留原文件逐字节不变；旧原生 Runner 持有设备锁时新宿主不能启动，旧 Runner 正常退出后新宿主复用同一状态目录进入空闲、停止并刷新后读回配置。此项不触碰用户真实 home，不调用模型；本机迁移测试与另外三项安装副本业务测试合计四项通过（52.4 秒）。该证据属于源码宿主与原生 Runner，不代表真实用户旧配置、旧待发箱恢复或打包应用迁移全部通过。


开发包归档新增 `development-validation.json`，记录实际构建提交、PR 头提交、CI 运行编号、架构、打包 GUI 与安装/卸载步骤的原始 outcome，以及安装文件 SHA-256。仅构建成功且清单/归档成功时上传；GUI 失败也可保留该开发包用于诊断，清单如实保留 failure/skipped/not_run，不能把归档存在当成验收通过。仍为七天保留的开发产物，不正式发行。

OpenCode 2.2.0 兼容与实际 macOS 安装副本的真实供应商闭环已补验：一次候选生成、显式采纳、保存刷新核对及 Runner 停止整项通过（47.8 秒）；版本白名单、自检提示、用户文档同步。实际记录见 TECH_STACK 对应章节，Windows 原生真实调用和网络异常矩阵仍未完整验证。
