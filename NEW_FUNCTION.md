# 新功能：依赖线按源 Mission 着色，退出详情时清除焦点

本文件供负责编码的 Agent 使用，是待实现需求。已核对当前仓库：工作台依赖图和 Mission 详情抽屉均已存在，但本次两项行为尚未实现。只改工作台依赖图的展示与焦点状态，不新增模型、业务写接口或后端颜色字段。

## 1. 待实现行为

### 1.1 依赖线颜色来自源 Mission

- 依赖方向仍为 `prerequisite_id → mission_id`；**源 Mission** 是 `prerequisite_id` 对应的任务，不是目标任务。对源 Mission 的 `id` 生成稳定的展示颜色；同一个可见源 Mission 发出的所有依赖线及末端箭头使用同一颜色，刷新、筛选、状态改变和选择切换后颜色保持一致。不同源任务应尽量容易区分；颜色不作为唯一识别依据。
- 颜色与现有卡片的“所属里程碑”颜色是两套语义。卡片色块和里程碑图例继续表示里程碑，不因新线色而改变。图上增加简短说明“依赖线颜色对应前置 Mission”，并确保选中线段或关系信息中能读到源任务标识／标题。
- 目前线段灰色表示已满足、橙色表示等待；改为按源 Mission 着色后，不能再让状态 CSS 覆盖线色。仍需用线型、透明度或其他非颜色提示，并在关系列表／点击反馈中以文字区分“已满足”和“尚未满足”。选中高亮、非相关线淡化及箭头样式须与源任务颜色兼容。颜色对比度应足以在现有浅色画布上看清。
- 父子任务折叠时，现有 `groupByParent` 会把隐藏任务的依赖边重指向可见父任务并可能合并多条边；线色以**当前可见边的源端卡片**为准。展开后恢复各真实源 Mission 的颜色。无可见源端的异常边使用中性回退色，并继续显示现有关系不完整提示；不能误用目标任务的颜色。

### 1.2 关闭 Mission 详情时清除焦点

- 用户从工作台关闭 `MissionDetailDrawer`（关闭按钮、Esc、遮罩，或抽屉因任务不存在而发出 `close`）时，清除当前 Mission 焦点：`selectedId = null`、详情关闭、相关节点／边的选中高亮及淡化消失、选中任务的上下游摘要消失，并从工作台 URL 移除 `selected`。若有已选依赖边，也清除该边的选中信息。筛选、视图模式、父子展示／折叠状态和画布视口保持不变。
- 若此前开启“只看相关”，关闭详情时同时退出该模式并恢复完整范围，避免清除焦点后仍停留在按旧任务裁剪的图上；必要时重新获取团队范围的图。关闭过程中旧请求不能把旧焦点或旧范围写回。
- 从详情中点击“定位／查看另一 Mission”等操作时，目标任务应成为新焦点；程序化关闭原抽屉不能随后把这个新焦点清掉。再次点击卡片仍能正常打开详情并重新建立焦点。从带 `selected` 的工作台链接打开详情后，关闭也应移除该参数。

## 2. 已实现的项目结构与数据流

- `frontend/src/views/WorkspaceView.vue` 管理 `/workspace` 的 `selectedId`、`drawerOpen`、`selectedEdge`、`relatedOnly`、筛选、图请求和 URL 参数。`onSelect()` 选择卡片并打开详情；`onFocus()` 设置焦点并定位；`onDrawerClose()` **目前仅设置 `drawerOpen=false`**。`queryFromState()` 将 `selectedId` 写入 URL 的 `selected`；`syncUrl()` 用 `router.replace` 同步。`loadGraph()` 按 `selectedId` 和 `relatedOnly` 决定请求范围，`reload()` 带请求代次控制；`selectedRelations` 与 `emphasisIds` 依赖当前焦点。
- `frontend/src/components/MissionDetailDrawer.vue` 接收 `missionId`、`open`，关闭时发出 `close`；关系项可发出 `focus`。页面把 `@close` 接到 `onDrawerClose`、`@focus` 接到 `onFocus`。详情数据另通过已有任务／依赖／成果接口读取，改动不应扩大写入权限。
- `frontend/src/components/DependencyGraph.vue` 接收可见 `nodes`、`edges`、`selectedId` 和高亮集合；`buildDependencyEdges()` 的输出送入 Vue Flow。组件 CSS 的 `.ws-edge--satisfied` 与 `.ws-edge--pending` **目前分别固定 `stroke: #94a3b8`、`stroke: #f59e0b`**，会覆盖按源任务设置的颜色。边点击事件向页面发出 `edgeSelect`。
- `frontend/src/workspace/dto.ts` 的 `buildDependencyEdges(edges, selectedId)` 目前只处理方向、上／下 Handle、箭头、满足状态与选中类，**没有源节点颜色输入**；`buildMissionNodes()` 用 `milestoneColor(node.milestone_id)` 给卡片配色。需要从可见节点建立 `id → Mission` 查找后再为可见边着色，避免把里程碑色误认为 Mission 专属线色。
- `frontend/src/workspace/parentGrouping.ts` 的 `groupByParent()` 返回折叠合并后的可见 `nodes`／`edges`，页面将其传给图组件；颜色应在这一步之后依据可见源端确定。`frontend/src/workspace/milestoneColor.ts` 仅负责里程碑色，不能改变其既有语义。
- 后端 `GET /api/workspace/graph/`（`backend/missions/workspace.py`，前端 `frontend/src/api/workspace.ts`）返回 `nodes`、`edges`、`parent_edges`、`meta`。`WorkspaceEdge`（`frontend/src/api/types.ts`）含 `prerequisite_id`、`mission_id`、`is_satisfied` 等；颜色属于前端展示层。接口受登录会话保护，当前无需新增参数或迁移。业务写入仍只走 `backend/missions/services.py`。
- 现有测试入口：`frontend/src/tests/workspace.spec.ts` 覆盖 DTO 边映射、图事件和页面行为；`frontend/src/tests/workspaceGraph.integration.spec.ts` 覆盖真实 Vue Flow 挂载。产品描述在 `PROJECT_STRUCTURE.md` 第 9 节，技术约束在 `TECH_STACK.md`；实现并验证后同步更新与线色／焦点相关的描述。

## 3. 验收与验证

1. 两条边共用源 Mission 时线段和箭头同色；更换源 Mission 时按其 `id` 稳定得色；筛选、刷新、状态变更不改变同一源的颜色。折叠后颜色跟随可见的代表源端，展开后恢复。
2. 已满足／未满足边在相同源颜色下仍可由非颜色样式和文字区分；选中、高亮、淡化及关系列表仍正确，里程碑卡片配色不变。
3. 关闭详情后 `selectedId`、`selectedEdge`、URL `selected` 与焦点高亮均清空；“只看相关”恢复完整图。直接链接进入并关闭、再选另一任务、从详情定位其他任务均正常。
4. 更新对应前端单元及 Vue Flow 集成测试，覆盖上述行为与无源端回退。按仓库顺序运行后端迁移检查／`check`／`test` 和前端 `type-check`／`test`／`build`，如未运行某项须如实说明。实现通过后同步 `PROJECT_STRUCTURE.md`；若技术栈约束变化也更新 `TECH_STACK.md`。同一功能的代码、测试和文档作为一次聚焦提交，不推送。
