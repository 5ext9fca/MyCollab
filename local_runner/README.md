# 本地 OpenCode 文本辅助 Runner

本目录只在用户电脑运行，不能加入 Django/Gunicorn 部署。模型通信、供应商登录、调用费用均由本地 OpenCode 环境处理。服务器仅收取结构化候选与固定错误码。

## 环境与绑定

1. 使用 Python 3.11 或更新版本与本仓库检出；Runner 只依赖 Python 标准库。
2. 安装 **OpenCode CLI 2.1.3**。适配器按此版本验证，其他版本会拒绝执行，需重新验证权限与协议后再升级支持范围。
3. 在用户电脑运行 `opencode auth login` 完成供应商登录；用 `opencode auth list`、`opencode models --standalone` 检查可用模型。不要把供应商凭据填写到 MyCollab。
4. 登录 MyCollab 的「本地 Agent」页面，创建设备，选择四类文本能力。设备凭据只展示一次，可设置 1–90 天有效期；服务器仅存摘要。
5. 创建目录 `mkdir -p ~/.config/MyCollab`，将如下本机 JSON 配置保存为 `~/.config/MyCollab/mycollab-runner.json`，并执行 `chmod 600 ~/.config/MyCollab/mycollab-runner.json`。文件不能提交 Git。

```json
{
  "server": "https://mycollab.example.com",
  "device_token": "填入页面本次展示的设备凭据",
  "model": "deepseek/deepseek-flash",
  "opencode": "opencode"
}
```

`model` 必须选择自己已配置且有额度的模型。生产要求 HTTPS；本机开发允许 `http://127.0.0.1:8000`。

从仓库根目录启动：

```bash
python3 -m local_runner
```

默认读取 `~/.config/MyCollab/mycollab-runner.json`；可用 `--config /实际路径/mycollab-runner.json` 覆盖，路径支持 `~` 展开。配置缺失、格式错误或权限过宽时会给出提示并退出，不自动生成或覆盖凭据文件。

`--once` 只领取一次，可用于接入检查。日常使用保持 Runner 运行，然后在设计/资产、模板、Mission 或验收表单中选择设备、预览上下文并生成候选。逐字段采纳后仍需点击原表单保存或人工验收。

## 权限和运行边界

每次调用创建临时目录和专用 `mycollab-text` Agent，以显式配置路径启动 `opencode run --standalone --format json`，经标准输入传递文本，避免需求出现在进程参数中。禁用全部工具权限，并使用 `tool.use` 与 `integration.use` 拒绝策略；不复用用户工作区或已有会话。模型子进程不接收 MyCollab 凭据。此模式禁止读取源码、执行命令、浏览链接、使用 MCP/技能或生成文件。

Runner 不修改用户 OpenCode 全局配置，也不搬运供应商凭据。OpenCode 自身在本机保存的会话和日志受它自己的管理策略控制；不要在输入中包含不希望发送给模型的秘密。管理配置若覆盖了本适配器的限制，不能将该环境视为首批受支持环境，需先核对有效权限。

协议版本为 1，输出校验复用 `backend/agent_bridge/protocol.py` 的纯 Python 模块，不加载 Django。类型、字段、列表数量、体积及依赖图在本地检查，服务器再检查素材引用与业务权限。失败只回传固定错误码，供应商原始异常和日志不会上传。

## 断线、取消与排错

- 按 Ctrl-C 停止轮询或当前模型调用，终止并回收模型子进程（POSIX 下终止进程组），清理临时目录，不打印异常堆栈，以退出码 130 退出。进程终止清理期间忽略重复 Ctrl-C；未回传的请求由服务器租约过期处理，不自动重跑模型。
- 空闲短轮询退避至约 60 秒，加入抖动；每设备只领取一个执行。运行约每 30 秒续租，服务器租约 180 秒、请求总时限 15 分钟。
- 取消或无法续租时尽力终止本地进程组。取消不能保证供应商退费；页面会区分等待停止和已确认停止。
- 模型执行不自动重试。回传失败最多重传三次**同一结果**，不重新调用模型；之后服务器租约过期，由用户决定重新请求。
- `local_configuration`：核对 OpenCode 版本与模型配置；`model_unavailable`：在本地检查登录、额度与网络；`invalid_result`：输出不符合协议；`model_timeout`：本次调用超时。不要上传原始认证错误。
- 凭据到期、撤销或用户停用会停止 Runner。重新绑定需要在 MyCollab 页面生成新设备凭据。
- 浏览器请求状态不明时会沿用原幂等键；先查看请求历史，不应另开多份付费请求。

## 验证记录

2026-10-26，本机 Python + OpenCode **2.1.3**，使用本地已登录的 `deepseek/deepseek-flash`。四类虚构测试输入均经真实 CLI 调用返回，并通过共享协议校验；凭据未输出或写入项目。另已通过隔离测试数据库/临时 HTTP 服务中的四项领取、回传与显式业务保存/验收闭环；测试服务器进程禁止外网，本地 OpenCode 子进程独立通信。页面人工采纳逻辑由前端组件测试覆盖，未声称人工浏览器逐页验收。临时文件对抗测试未返回私有哨兵、未创建要求的文件。验收依据必须是输入字段 JSON Pointer 与逐字摘录，两端均校验。

自动化测试无需模型或付费凭据：

```bash
python3 -m unittest discover -s local_runner/tests -v
```

官方依据：[OpenCode CLI](https://opencode.ai/docs/cli/)、[V2 配置](https://opencode.ai/v2/docs/config)、[V2 权限](https://opencode.ai/v2/docs/permissions)、[V2 策略](https://opencode.ai/v2/docs/policies)。V1 与 V2 权限字段不同，不能混用。


## Agent 需求文档

更新 Runner 后，在设备绑定时选择 `agent_requirements`（Agent 需求文档）能力，从 Mission 点击“导出为Agent需求文档”。沿用本文的 OpenCode 文本环境与启动命令，不需要图像模型、代码仓库或验证命令。模型只能整理已提供的 Mission/设计/资产文本，不能执行任务；结果按 `markdown` 字段回传，浏览器预览并下载 `.md`。无可用本地设备时不会用模板替代模型结果。

图像、代码委派及执行中审批已迁至 `feature/agent-delegation`，对应旧 Runner 参数在主分支不再支持。

2026-10-26 真实需求文档验收：`MYCOLLAB_LIVE_MODEL=deepseek/deepseek-flash` 运行 `agent_bridge.tests.test_requirements_live`，浏览器 API 创建请求、真实本地 OpenCode 整理、Bearer 回传、浏览器 API 读取均通过；输出包含 Markdown 章节及 Mission 来源 ID，任务状态与版本未改变。服务端进程限制为本机网络，供应商调用仅在本地 OpenCode 子进程；这不等同于浏览器人工验收。
