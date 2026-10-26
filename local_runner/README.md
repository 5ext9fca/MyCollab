# 本地文本与图像 Runner

本目录只在用户电脑运行，不能加入 Django/Gunicorn 部署。模型通信、供应商登录、调用费用均由本地 OpenCode 环境处理。服务器仅收取结构化候选、固定错误码及本地明确选中的图像文件。

## 环境与绑定

1. 使用 Python 3.11 或更新版本与本仓库检出；文本 Runner 只依赖 Python 标准库；图像流程另需下文的本地 Pillow。
2. 安装 **OpenCode CLI 2.1.3**。适配器按此版本验证，其他版本会拒绝执行，需重新验证权限与协议后再升级支持范围。
3. 在用户电脑运行 `opencode auth login` 完成供应商登录；用 `opencode auth list`、`opencode models --standalone` 检查可用模型。不要把供应商凭据填写到 MyCollab。
4. 登录 MyCollab 的「本地 Agent」页面，创建设备，选择四类文本能力。设备凭据只展示一次，可设置 1–90 天有效期；服务器仅存摘要。
5. 在仓库以外保存如下本机 JSON 配置，并执行 `chmod 600 /实际路径/mycollab-runner.json`。文件不能提交 Git。

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
python3 -m local_runner --config /实际路径/mycollab-runner.json
```

`--once` 只领取一次，可用于接入检查。日常使用保持 Runner 运行，然后在设计/资产、模板、Mission 或验收表单中选择设备、预览上下文并生成候选。逐字段采纳后仍需点击原表单保存或人工验收。

## 权限和运行边界

每次调用创建临时目录和专用 `mycollab-text` Agent，以显式配置路径启动 `opencode run --standalone --format json`，经标准输入传递文本，避免需求出现在进程参数中。禁用全部工具权限，并使用 `tool.use` 与 `integration.use` 拒绝策略；不复用用户工作区或已有会话。模型子进程不接收 MyCollab 凭据。此模式禁止读取源码、执行命令、浏览链接、使用 MCP/技能或生成文件。

Runner 不修改用户 OpenCode 全局配置，也不搬运供应商凭据。OpenCode 自身在本机保存的会话和日志受它自己的管理策略控制；不要在输入中包含不希望发送给模型的秘密。管理配置若覆盖了本适配器的限制，不能将该环境视为首批受支持环境，需先核对有效权限。

协议版本为 1，输出校验复用 `backend/agent_bridge/protocol.py` 的纯 Python 模块，不加载 Django。类型、字段、列表数量、体积及依赖图在本地检查，服务器再检查素材引用与业务权限。失败只回传固定错误码，供应商原始异常和日志不会上传。

## 断线、取消与排错

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
local_runner/.venv/bin/python -m unittest discover -s local_runner/tests -v
```

官方依据：[OpenCode CLI](https://opencode.ai/docs/cli/)、[V2 配置](https://opencode.ai/v2/docs/config)、[V2 权限](https://opencode.ai/v2/docs/permissions)、[V2 策略](https://opencode.ai/v2/docs/policies)。V1 与 V2 权限字段不同，不能混用。

## 第二批：Codex CLI 图像生成与编辑

用户本机安装并登录 **Codex CLI 0.164.0**，用 `codex --version`、`codex login status` 检查。适配器使用原生图像工具；并非所有 CLI 版本/账户都有该能力，本项目只验证上述版本及本机 ChatGPT 登录。不要把登录文件或 API Key 上传到 MyCollab。第一批四类文本任务仍使用 OpenCode。

从仓库根目录创建本地虚拟环境并安装转换依赖（仅本地需要 Pillow 13.0.0）：

```bash
python3 -m venv local_runner/.venv
local_runner/.venv/bin/python -m pip install -r local_runner/requirements.txt
```

在 MyCollab「本地 Agent」新建设备时勾选图像生成/图像编辑能力；只声明本机实际支持的能力。现有文本设备不自动增加图像权限。配置例子（保存于仓库外、权限 600）：

```json
{
  "server": "https://mycollab.example.com",
  "device_token": "本人设备凭据",
  "model": "deepseek/deepseek-flash",
  "opencode": "opencode",
  "image_adapter": "codex",
  "codex": "codex",
  "image_output_dir": "/本人专用目录/mycollab-images"
}
```

只使用图像设备时可省略 OpenCode 的 model/opencode 字段。`image_output_dir` 必须是本人专用目录，首次自动创建并设权限 700；已有目录须自行 `chmod 700`。不能使用符号链接。目录保存需求授权的参考图、转换后的候选、清单和本地静态 HTML；不保存供应商凭据或设备令牌。不要将整个目录同步到公开仓库。

```bash
local_runner/.venv/bin/python -m local_runner --config /实际路径/mycollab-runner.json
```

1. 在本人 InProgress Mission 里关联 Asset，填写图像委派；编辑至少选一张本人素材库中的参考图。服务器不下载任何外链。
2. Runner 执行一次模型调用，最多接收四张原生图片；当前提示请求一张。完成后终端打印 `preview.html` 路径，用本机浏览器打开。未选图片和缩略图不会上传。
3. 看完预览后，按终端提供的 request UUID 与实际候选编号执行：

```bash
local_runner/.venv/bin/python -m local_runner --config /实际路径/mycollab-runner.json --select 实际请求UUID --keys candidate_1
```

多选显式列出各 key。没有 `--keys` 会拒绝执行，不默认全选。选择集合一经确认不可覆盖；上传失败可重复**同一命令**，只校验/重传同一文件，不调用模型。改选或改需求需在网页明确新建执行。清单回传失败时，只能在仍有效的执行租约内重传，已过期不能恢复。

4. 页面显示“选中成果已上传”后，使用“引用到提交草稿”，填写人工验证说明并确认提交，仍需人工验收。模型不会认领、提交或验收 Mission。

### 本地边界与清理

Codex 每次在新的临时目录运行 `exec --ignore-user-config --ephemeral --skip-git-repo-check --sandbox workspace-write`，禁用 shell、应用/插件、浏览器、computer_use、hooks、技能搜索与多 Agent；保留本机认证，图像通过 `-i` 显式附加。MyCollab 设备配置不放进模型工作目录或参数，`MYCOLLAB_` 环境变量从子进程移除。Codex 自己管理的原生输出位于其本机 `generated_images/<thread_id>`；Runner 只接受本次事件对应目录中的普通 PNG，不读取模型回答中的任意路径。它不是通用代码 Agent，也不开放服务器下发命令。

本地 Pillow 校验静态图片、像素上限，转换为 8 位 RGB/RGBA PNG，去除原始元数据。服务器只校验压缩流/块/尺寸/摘要，不能承担转换。图像请求总限时 30 分钟，Runner 模型调用上限 28 分钟，30 秒心跳/180 秒租约；等待选择限时 24 小时。中断或离线不会自动重做付费调用，取消只尽力停止本地进程，不能保证供应商退费。

人工清理：先确认网页执行已结束或取消，再在文件管理器中打开配置的专用输出目录，只删除对应请求 UUID 子目录；这会删除本地未选候选和参考副本，不删除服务器已经上传的素材。不要在仍等待选择/上传时清理。Codex 原生 `generated_images` 另由用户在本机管理，本 Runner 不自动删除它，避免影响其他会话。服务器清理任务只清除老请求输入快照，不删除图像成果/提交历史。

### 图像验证记录

2026-10-26，Codex CLI 0.164.0、本机 ChatGPT 已登录、原生 image_generation 可用：实际生成白底绿色叶片；随后通过本适配器附加该图片，将叶片编辑为金黄色。编辑结果经本地 Pillow 转换与共享 PNG 校验，1254 × 1254，745834 字节，已查看确认颜色与白底；所有图片及认证留在本机测试目录，未写入业务素材库。真实供应商调用只在此单独验收中发生。普通回归使用确定性适配器，另测试真实 HTTP 的生成/编辑、授权参考、显式选择、仅选中上传、人工提交/验收；不把 mock 测试等同于真实供应商验证。

官方依据：[Codex 图像生成](https://learn.chatgpt.com/docs/image-generation)、[Codex CLI 参数](https://learn.chatgpt.com/docs/cli/reference)、[Pillow 13.0.0](https://pypi.org/project/pillow/13.0.0/)。未宣称所有账户、其他 CLI 版本或其他提供商均可用。
