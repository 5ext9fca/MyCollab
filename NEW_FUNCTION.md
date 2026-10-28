# 新功能：迁移 Electron 并交付 Windows / macOS 完整桌面客户端

## 1. 决策、目标与状态

用户已确认：开发完整桌面客户端，支持 Windows 与 macOS，桌面宿主从 Tauri 迁移至 Electron。本文件替换此前已归档的统一 Agent Panel 方案，是本次完整需求与分阶段开发计划；现已进入实现阶段；除下方进度明确列出的模块外，其余新增能力仍待实现。

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
- `local_runner/__main__.py` 负责配置、BridgeClient、领取、执行、自检、状态与父进程监测；`local_runner/opencode.py` 调用 OpenCode，当前验证版本为 2.1.3。
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

用户已授权实施，但暂不执行涉及 GUI 的测试与验收；本文件原有 GUI、双机界面及安装交互验收要求暂缓，不将其记录为已通过。

- 已新增 Electron 45.1.0 主进程/preload/安全协议与共享 Vue 接入，服务器设置、单实例、托盘、可选自启动、局域网权限、私有素材下载和系统外链；业务 Session 与页面隔离，切换服务器/退出清理会话。包含 macOS/Windows 原生打包配置，开发包临时签名、发行命令强制签名。
- 已生成过 macOS arm64 临时签名开发包，通过签名完整性和静态资源核对，未启动应用。本轮已重打包含绑定、启停控制器和内置 Runner 的开发包，通过签名完整性及包内 Runner 非 GUI 检查；这一产物不是最终客户端，也不能证明窗口运行行为。
- Runner 已增加 `--config-stdin` 有界私有管道入口；已完成 39 项非 GUI Runner 测试（37 项通过，2 项 Windows 原生测试在 macOS 跳过），保持结果恢复和父进程退出语义。
- 已接入主进程和桌面本地 Agent 页的设备绑定：后端只读探测增加经过认证的用户/设备身份，主进程与业务登录身份交叉核验后使用系统加密保存。读取仅返回脱敏摘要，不回显已保存令牌；切换身份拒绝旧绑定操作。使用异步系统密钥接口，密钥轮换重新加密，不可用时拒绝保存而不回退明文。
- 41 项桌面非 GUI 测试、29 项前端 API/传输纯逻辑测试及类型/构建检查已通过；后端 PostgreSQL 回归 272 项完成（3 项按既有条件跳过），迁移检查与系统检查通过。系统钥匙串/DPAPI 仍未实机验收；真实 Electron 会话、系统权限、双机 WebRTC、Windows/macOS 各架构运行均未验收。
- 后续仍需跨平台 Runner 启停/进程树/文件权限、诊断、更新、旧配置迁移、原生 CI 和发行配置；旧 Tauri 暂留，不将当前开发宿主称为完整客户端。

- 已实现 Windows 非阻塞文件锁、原生私有 DACL、基于进程句柄的父进程探测，以及三个目标平台/架构的原生 Runner 构建入口；macOS arm64 打包后二进制通过匿名管道、中文路径、空领取和状态检查。Windows 模型子进程树已加入原生 Job 管理，实机验证仍待完成。

- 已实现桌面停止管道、Windows 挂起创建后加入 Job 再执行、Runner 外层 Job 崩溃清理和模型内层 Job 收尾。macOS 独立程序已验证管道 EOF 停止；Electron 启停控制器已接入；Windows 原生测试仍待完成。

- 已接入 Runner 页面启停、自检、脱敏状态与待发数量；退出、切换登录/服务器、重新绑定先等待停止，停止失败保留会话。启动等待设备锁就绪事件，打包必须包含对应平台 Runner。控制器已通过真实子进程的非 GUI 测试，Electron 窗口中的运行行为仍未验收。

- 桌面修改同一已绑定设备的模型和 OpenCode 路径时，可将令牌留空；主进程仅从当前服务器、当前用户的加密绑定读取原令牌，再次验证设备归属后保存，不向页面回显。更换设备或没有本机绑定时必须提供令牌。绑定期间拒绝启动和自检，开始绑定前取消尚在验证的启动并等待已有进程停止。

- 已添加三个目标架构的原生非 GUI GitHub Actions 工作流，涵盖类型/边界测试、前端纯逻辑回归、原生 Runner 和开发包构建、包内 Runner 检查及开发产物归档。尚未推送或在远端执行；Windows 与 Intel 构建结果仍待验证，不作为正式签名发行或 GUI 验收证据。

- 已实现默认 macOS 旧伴侣配置导入：校验权限、当前服务器与用户后加密保存，原地复用待发箱与独占锁，不删除旧文件、不自动启动。独立 Runner 已验证同状态目录竞争启动被拒绝。自定义 CA 旧配置暂拒绝导入；实际旧伴侣 GUI 迁移未验收。

- 已接入手动更新检查、下载、停止 Runner 后安装的控制流程，默认不下载、不随退出安装；发行构建要求固定 HTTPS 源、平台/架构元数据、代码签名及 macOS 公证，开发包禁用更新。控制器测试通过，真实更新服务、签名证书、公证与原生安装/升级仍未验证，不视为发行完成。

- 已将 Windows CI 扩展到完整 Runner 非 GUI 测试发现入口，使用原生测试假 CLI 覆盖真实领取/执行/回传恢复链路；三个目标的打包后二进制均增加断线恢复与宿主退出检查。本机 macOS 源码回归通过，Windows/Intel 远端运行仍未执行。

- 已修复退出失败仍跳登录页的问题，并接入业务请求确认会话过期后的 Runner 停止、旧流取消、Cookie 清理和页面重载；普通权限拒绝不清登录，断网仍支持停止成功后的本机退出。新增状态层与传输层非 GUI 回归，未执行页面交互验收。
