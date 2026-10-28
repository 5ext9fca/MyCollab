# 本地 OpenCode 文本辅助 Runner

Runner 在你的电脑上连接 MyCollab，提供文本辅助和 Agent 需求文档导出。模型通信、供应商登录与调用费用由你的本地 OpenCode 环境处理。

## 环境与绑定

1. 使用 Python 3.13 与本仓库检出；Runner 只依赖 Python 标准库。
2. 安装 **OpenCode CLI 2.1.3**。适配器按此版本验证，其他版本会拒绝执行，需重新验证权限与约定后再升级支持范围。
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
backend/.venv/bin/python -m local_runner
```

默认读取 `~/.config/MyCollab/mycollab-runner.json`；可用 `--config /实际路径/mycollab-runner.json` 覆盖，路径支持 `~` 展开。配置缺失、格式错误或权限过宽时会给出提示并退出，不自动生成或覆盖凭据文件。

`--once` 只领取一次，可用于接入检查。日常使用保持 Runner 运行，然后在设计/资产、模板、Mission 或验收表单中选择设备、预览上下文并生成候选。逐字段采纳后仍需点击原表单保存或人工验收。

`./testrun.sh` 在前后端就绪后自动启动 LocalRunner，读取 `~/.config/MyCollab/mycollab-runner.json`；配置缺失时提示并跳过，Runner 退出时提示且保持前后端运行，不自动重启。Ctrl-C 或终止脚本时一并停止本次 Runner，通过 SIGTERM 复用模型进程清理，数据库与数据保留。启动前应确认配置中的服务器地址和设备凭据属于预期环境；Runner 仍使用该配置，不覆盖服务器地址。此启动流程不改变数据模型、接口或权限。

## 权限和运行边界

Runner 仅处理你预览并提供的文本，不能读取源码、执行命令、浏览链接或生成文件。它不会修改 OpenCode 全局配置；模型调用不会收到 MyCollab 设备凭据。

OpenCode 的本机会话与日志由其自身管理。不要在输入中包含不希望发送给模型的秘密；如果本机管理配置放宽了权限，请先核对后再使用。

## 断线、取消与排错

- 按 Ctrl-C 停止轮询或当前模型调用，终止并回收模型子进程（POSIX 下终止进程组），清理临时目录，不打印异常堆栈，以退出码 130 退出。进程终止清理期间忽略重复 Ctrl-C；未回传的请求由服务器租约过期处理，不自动重跑模型。
- 空闲短轮询退避至约 60 秒，加入抖动；每设备只领取一个执行。运行约每 30 秒续租，服务器租约 180 秒、请求总时限 15 分钟。
- 取消或无法续租时尽力终止本地进程组。取消不能保证供应商退费；页面会区分等待停止和已确认停止。
- 模型执行不自动重试。回传失败最多重传三次**同一结果**，不重新调用模型；之后服务器租约过期，由用户决定重新请求。
- `local_configuration`：核对 OpenCode 版本与模型配置；`model_unavailable`：在本地检查登录、额度与网络；`invalid_result`：输出不符合约定；`model_timeout`：本次调用超时。不要上传原始认证错误。
- 凭据到期、撤销或用户停用会停止 Runner。重新绑定需要在 MyCollab 页面生成新设备凭据。
- 浏览器请求状态不明时会沿用原幂等键；先查看请求历史，不应另开多份付费请求。

## Agent 需求文档

更新 Runner 后，在设备绑定时选择 `agent_requirements`（Agent 需求文档）能力，从 Mission 点击“导出为Agent需求文档”。沿用本文的 OpenCode 文本环境与启动命令，不需要图像模型、代码仓库或验证命令。模型只能整理已提供的 Mission/设计/资产文本，不能执行任务；结果按 `markdown` 字段回传，浏览器预览并下载 `.md`。无可用本地设备时不会用模板替代模型结果。

当前 Runner 支持文本辅助与需求文档导出，不提供图像、代码执行或执行中审批。
