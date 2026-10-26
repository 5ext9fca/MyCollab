# 本地文本与图像 Runner

本目录只在用户电脑运行，不能加入 Django/Gunicorn 部署。模型通信、供应商登录、调用费用均由本地 Agent 环境处理。服务器仅收取结构化候选、固定错误码及本地明确发布的图像/代码成果。

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

## 第三批：OpenCode 规则/代码委派

使用已登录的 OpenCode CLI **2.1.3**，不需要服务器安装 OpenCode 或供应商 SDK。在「本地 Agent」创建设备时勾选“代码实现”。首批文本 Agent 仍禁用全部工具；代码适配器是独立的 `mycollab-code`，只允许读取及修改本地白名单文件。

在仓库外、权限 600 的 Runner 配置中增加：

```json
{
  "server": "https://mycollab.example.com",
  "device_token": "本人设备凭据",
  "opencode": "opencode",
  "code_model": "deepseek/deepseek-flash",
  "code_output_dir": "/本人专用目录/mycollab-code",
  "repositories": {
    "game-rules": {
      "path": "/本人项目/game",
      "baseline": "HEAD",
      "writable_paths": ["src/rules", "tests/rules"],
      "verification": [
        {
          "id": "rules-unit",
          "label": "规则单元测试",
          "argv": ["/本机Python绝对路径/python", "-m", "unittest", "discover", "-s", "tests/rules"],
          "timeout": 120
        }
      ]
    }
  }
}
```

以上路径与命令都是示例，替换成自己的环境；只声明实际配置好的能力。`code_model` 省略时使用已有文本 `model`。仓库标识不是路径，网页只填写 `game-rules`；用户登录/Git/依赖凭据不放进网页或任务正文。配置的验证命令应在该仓库独立副本中能运行，不自动安装依赖、不自动获取远程资源。所需工具链须在本机提前配置。

从仓库根目录运行：

```bash
local_runner/.venv/bin/python -m local_runner --config /实际路径/mycollab-runner.json --list-repositories
local_runner/.venv/bin/python -m local_runner --config /实际路径/mycollab-runner.json
```

流程：在本人 InProgress Mission 选择代码设备、仓库标识和要求 → 预览/确认 → Runner 解析本地基线提交，导出独立副本，调用 OpenCode → 实际 diff 与验证报告保存在专用输出目录 → 人工检查 `changes.patch`、`report.json` 和必要的本地 `logs/` → 显式发布：

```bash
local_runner/.venv/bin/python -m local_runner --config /实际路径/mycollab-runner.json --publish-code 实际请求UUID
```

未执行发布命令时，服务器只有基线/文件摘要/大小清单，没有补丁和报告正文。发布失败可以重复同一命令，只重传相同内容，不重新执行模型。修改本地成果会触发摘要不匹配；不要改写清单绕过校验，应明确创建新执行。发布后仍需在完整详情“引用代码成果到提交草稿”，填写人工验证说明并确认提交，由验收者人工处理。

### 代码范围、验证与取消

- `baseline` 在领取时解析为固定 Git 提交；默认 HEAD。未提交/未跟踪改动不发送给模型、不被覆盖。不会更改原仓库分支、远端、索引或工作区。副本使用独立 Git 元数据，不自动 push/PR/merge/deploy。
- 仓库导出最多 100 MiB/20000 条目；拒绝符号链接、子模块和特殊文件；若 export-ignore/export-subst 等 Git 属性改变导出基线则拒绝执行，避免交付不能对应原提交的补丁。排除 `.git`、`.opencode`、`.codex`、`.ssh`、`.aws`、`.venv`、node_modules、`.env*`、常见认证文件和 opencode.json 配置。只能交付 UTF-8 文本补丁，最多 2 MiB/200 个变更文件，不支持二进制补丁。请先确认可发送给供应商的仓库内容；自动排除常见秘密文件不等于通用秘密扫描。
- `writable_paths` 是规范相对路径或目录，不是 glob，不能包含 `*`/`?`、上级路径或敏感目录。代码 Agent 禁止 shell/外部目录/插件/MCP/技能/子 Agent/格式化；每次非交互新会话，显式同步 cwd 与 PWD。不会将 MyCollab 配置或令牌放进模型目录/参数。供应商认证仍由本机 OpenCode 处理。
- 验证在候选的另一个副本中运行，仅使用本地配置的 argv，不接受模型/服务器命令。每项默认 120 秒、最多 900 秒；模型调用上限 20 分钟，验证总预算 8 分钟；请求最长 30 分钟。最多 20 项验证、每项原始日志最多 1 MiB，日志留在本机，不上传。
- 未产生补丁时返回 no_changes，页面明确提示没有代码差异，不伪造成功交付。
- passed/failed 来自实际退出码，超时为 timeout，命令不可用/预算不足为 not_run；没有配置验证时报告列表为空，页面明确显示未配置。测试失败不会自动重做模型调用，也不会伪装已通过。报告只代表本地证据，服务器没有复跑，人工提交/验收需自行检查覆盖范围。
- **独立工作目录不是操作系统沙箱**。验证命令及其运行的仓库代码拥有本机用户权限；配置它们即授权执行这些代码。如果需要抵御不可信代码，应在自己准备的容器/虚拟机或受限账户环境运行 Runner 和工具链，再配置允许的验证命令。服务器不会替用户运行这些代码。
- 心跳失败或取消时尽力终止 Agent/验证进程组；可能已经消耗供应商费用。等待本地审查的成果 24 小时过期；不自动重新执行。终态或版本变化后重新生成须由用户明确创建新执行。

### 人工应用与清理

服务器补丁下载名为 `changes.patch.txt`（纯文本附件）。先核对报告的基线 SHA、改动范围和验证结果，再在自己选择的 Git 分支/工作区手工操作，例如：

```bash
git apply --check /实际下载路径/changes.patch.txt
git apply /实际下载路径/changes.patch.txt
```

上面的命令由用户手动运行；Runner 不自动应用回原仓库，也不自动向原仓库提交 Git；隔离副本中的基线提交仅用于计算差异。基线变化时不要强行覆盖，应人工解决差异或重新委派。

清理前先确认执行已终止、取消或成果已上传：在文件管理器打开 `code_output_dir`，只删除对应请求 UUID 子目录（包含 workspace、verification、logs、补丁和报告）。不删除原仓库；清理本地副本不会删除服务器成果。服务器保留已交付补丁与提交轮次关联，历史清理只清空旧请求输入。

### 代码真实验收记录

2026-10-26，使用用户明确选择的隔离示例 Git 仓库，OpenCode 2.1.3 / 本机已登录的 `deepseek/deepseek-flash` 实现积分函数：负数归零、非负数加倍。实际修改了隔离副本的 rules.py，Runner 运行 unittest 返回 0，Git `apply --check` 对原基线通过，原示例仓库保持不变。

开发验收发现 OpenCode 继承 PWD 会选错 Location，即使 subprocess 指定 cwd；初次测试误在项目根目录新建了测试用 rules.py。该临时文件已移除，适配器改为同时设置规范 cwd/PWD，并增加回归检查。修正后的真实验证确认只修改隔离副本，不将这次失败计为验收通过。

普通回归使用确定性模型 + 真实本地 Git/验证命令，并通过临时 HTTP 服务测试“领取→本地实现→清单→明确发布→人工提交/验收”。服务器测试进程禁止外网；供应商真实调用单独运行，不将 mock 当作真实接入。页面交互通过组件测试验证，未宣称人工浏览器逐页验收。

官方依据：[OpenCode V2 权限](https://opencode.ai/v2/docs/permissions)、[策略](https://opencode.ai/v2/docs/policies)、[工具](https://opencode.ai/v2/docs/tools)、[配置](https://opencode.ai/v2/docs/config)。

修正后的真实对抗示例另外验证：不可信输入要求读取外部哨兵、修改未授权文件和运行 shell，未泄露哨兵、未修改保护文件、未产生 shell 目标文件；唯一差异仍为允许的 rules.py。该测试记录行为结果，不宣称目录隔离能抵御恶意验证代码。

### 执行中对话与单次编辑审批

OpenCode 2.1.3 的代码执行支持可选交互。在本机 Runner 配置的某个 `repositories.<repository_key>` 内添加 `"interactive": true`，其他仓库保持原来的非交互流程。此项必须由本机用户配置，网页不能代开或扩大 `writable_paths`。

启用后，在 Mission → Agent 委派 → 代码执行历史中展开“私有对话与权限审批”：

- 可在执行过程中发送补充消息，OpenCode 以 `steer` 投递到同一会话；当前工具可能先完成。网页显示“等待本地处理”与“本地已处理”，不把收到消息当作任务完成。
- 白名单内的文件编辑由原来的允许收紧为逐次询问。每张卡片列出相对路径，可拒绝或仅批准这一次；不能永久批准、执行 shell、访问外部目录或修改认证/Agent 配置。网页批准前后都重新验证具体请求与操作摘要。
- 审批等待最多 120 秒，超时默认拒绝。取消、租约失效、会话结束或版本变化后不接受新消息和审批；通信结果不明时不重复执行本地操作，不自动重建付费会话。
- 本地 OpenCode 私有服务只监听 `127.0.0.1` 的随机端口，使用随机临时认证；浏览器和 MyCollab 服务器都不连接此服务。服务随本次执行退出，认证不上传。模型/供应商登录仍由本机 CLI 管理。
- `interaction.json`（权限 600）记录本地 session 映射、命令去重与待决审批；没有跨进程恢复功能，崩溃后由原请求超时，后续须明确新建执行。文件保留在请求 UUID 输出目录，可随该次本地产物手工清理。
- 仅上传有界普通回复、相对路径审批和处理状态；推理过程、原始工具参数/输出、原生 session ID 不上传。用户不要在追问中输入凭据。对话仅本人可见，七天后由服务器清理；代码补丁和提交关联仍按原规则保留。
- 当前验证的交互适配器是代码 OpenCode；图像 Codex 和四类文本辅助沿用已有流程，不显示不支持的交互能力。代码产物仍须本机 `--publish-code` 明确发布，网页人工提交和验收。

2026-10-26 真实交互验收：在临时目录使用 OpenCode 2.1.3 / `deepseek/deepseek-flash` 修改 score 函数。执行中追加“负数返回 0”，实际触发编辑审批并使用 `once` 回复，最终函数满足负数归零、非负数翻倍，模型最终回复确认收到补充。该次使用测试交接端，原生模型调用与独立 Django/Runner 确定性闭环分别验证，不把它描述为人工浏览器全流程验收。
