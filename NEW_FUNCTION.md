# 新功能：调整工作台依赖图布局

本文件描述 `/workspace` 依赖图的一次布局调整。它**不改变** Mission 数据模型、依赖含义、状态机或写入接口，只改变依赖图的坐标算法与必要的展示文案。

下文分三部分：

1. **需求**——目标、布局规则、实现约束与验收场景。
2. **项目当前结构（核对自当前代码）**——本次实现所需的目录职责、数据模型与接口、前后端数据流、关键业务约束与测试入口。
3. **实现状态**——哪些已完成、哪些明确不在本次范围。

需求已完成并验证；`PROJECT_STRUCTURE.md`（第 9 节）与 `TECH_STACK.md`（第 2、8、11 节）已同步为实际实现。本文件本身只作为需求与结构参考，不作为已实现功能的权威说明。

## 1. 需求

### 1.1 目标与布局规则

1. **整体自顶向下。** 工作台依赖图中的 Mission 卡片按依赖层级从上到下排列。显式依赖边始终表示 `prerequisite_id → mission_id`。对当前图中每个可见 Mission 计算依赖层级：没有可见前置的节点为第 0 层，其余节点的层级必须大于**每一个**可见前置的层级，建议使用 `1 + max(所有可见前置的层级)`。同层节点可横向排布。卡片的顶边坐标应确保有依赖的卡片整体位于所有可见前置卡片下方，而不只是中心点更低。多前置、跨父子组及跨里程碑依赖同样遵守此规则；孤立节点也要显示。
2. **父子关系横向展开。** “显示父子任务关系”开启时，父任务在左，直接子任务在其右方；多级子任务逐级向右展开。同一依赖层级且没有排序冲突的父子卡片共享水平行。父子关系仅用于分组和位置，不增加依赖边，也不改变业务依赖方向。
3. **依赖优先于父子对齐。** 子任务有前置时，必须处于全部前置卡片下方，即使因此不能与父任务同排。子任务之间也按真实显式依赖分层。例如父任务 `P` 有子任务 `A`、`B`，`B` 依赖 `A`：`A` 在 `P` 右侧；`B` 仍位于父任务所属的横向区域内，但必须在 `A` 下方。若子任务依赖其他家庭的节点，也以依赖层级决定纵向位置。不要为了强制同排而隐藏或忽略依赖。
4. **父任务预留垂直空间。** 一个父任务及其展开的可见后代形成布局区域；根据这些子任务占用的依赖层级、实际卡片尺寸和间距，向下扩张该区域预留的**垂直空间**。父任务卡片无需随区域变高。排布其他任务或家庭时，不能侵入该区域造成卡片重叠；子任务增减、依赖变化、展开或折叠后重新计算区域尺寸。独立的家庭之间也不能重叠。
5. **折叠与选项保持可用。** 沿用已有“显示父子任务关系”开关和父任务的展开／折叠交互。关闭开关时，所有可见 Mission 仍按自顶向下的依赖层级布局，不做父子横向编排。折叠后隐藏子树、合并其可见依赖关系以及合并边的满足情况，沿用现有语义；布局应对当前实际显示的卡片和边重新计算，不让隐藏卡片继续占位。若折叠映射导致表面上的自环或环，不应把异常图强行排成违反依赖方向的结果；给出关系异常或不完整提示，并保持页面可用。

### 1.2 实现约束

- 保留现有 Vue Flow 的只读交互、选择、高亮、定位、缩放、适应视图、详情抽屉、关系替代列表、颜色图例及筛选行为。依赖连线和箭头应适配自上而下的阅读方向，不能保留会误导用户的左右方向提示。
- 可以沿用或调整第三方布局库，也可以自行实现算法；以满足节点层级、父子横向编排、垂直空间预留和无重叠为准。若更换布局库，同步修改依赖及 `TECH_STACK.md`。旧的“父任务＋子任务为单个纵向块、把依赖边映射到块根”的方式不能作为最终结果，因为它会掩盖单个子任务自己的依赖层级。
- 层级只依据已加载的图计算。若后端标明关系不完整，或某条依赖的端点未加载，继续显示现有不完整提示；不要把未知前置解释成“没有依赖”，也不要声称已证明该节点处于全部真实前置下方。
- 布局顺序稳定：相同结构和尺寸得到相同坐标；状态、标题或满足情况变化若未影响尺寸和结构，不应让画布跳动。结构或尺寸变化时更新坐标，并尽量保留当前视口、选中任务与定位行为。节点坐标不持久化，也不通过画布事件写业务 API。
- 先调整规则与相关测试，再改实现。实现通过验证后，把数据模型、接口、权限、页面和业务规则的最终描述并入 `PROJECT_STRUCTURE.md`；若技术约束变化，同步 `TECH_STACK.md`。

### 1.3 验收场景

1. `A → C`、`B → C`、`C → D`：`C` 完整位于 `A` 和 `B` 下方，`D` 完整位于 `C` 下方；无边节点仍可见。前置顺序不依赖数组输入顺序。
2. 父任务 `P` 与无依赖子任务 `A`：`A` 在 `P` 右侧，同一水平行；有多级子任务时逐级右移，卡片不重叠。
3. 父任务 `P` 的子任务 `A → B → C`：`A` 在父任务右侧，`B` 在 `A` 下方，`C` 在 `B` 下方；父任务所属布局区域向下扩张，邻近任务或家庭不会侵入。
4. 子任务具有家庭外的多个前置：它位于所有这些前置下方，同时仍显示在所属父任务的横向区域内；折叠、展开及切换父子显示开关后，依赖层级和边方向仍正确。
5. 更新结构、筛选范围或节点尺寸后布局正确且无重叠；仅更新不影响尺寸的状态时坐标保持稳定。关系不完整或异常时有明确提示，关系列表仍可用。

## 2. 项目当前结构（核对自当前代码）

> 以下为编写本次功能时需要的事实信息，路径与行为均与当前仓库一致。只覆盖本功能涉及的范围。

### 2.1 相关目录与文件职责

后端（只读聚合，本次不修改）：

- `backend/missions/workspace.py`——唯一的工作台聚合入口，两个 **GET-only** 视图 `overview` 与 `graph`；集中组装节点、依赖边、父子边、`revision` 与 `meta`。
- `backend/missions/filters.py`——工作台与列表共享的筛选解析（`apply_mission_filters`、`parse_bool/int/uuid`）。
- `backend/missions/services.py`——所有业务写入入口（本次不涉及）；工作台复用其 `derived_state_bulk` 派生字段。
- `backend/missions/models.py`——`Mission`、`MissionDependency`、`Milestone` 等模型。
- `backend/missions/tests/test_workspace.py`——工作台聚合的接口/权限/截断/修订标识测试（依赖 PostgreSQL）。

前端（依赖图相关）：

- `frontend/src/views/WorkspaceView.vue`——页面：视图切换（`overview`/`graph`）、URL 状态、请求代次、筛选、详情抽屉、**父子分组与折叠状态**、依赖环提示。
- `frontend/src/components/DependencyGraph.vue`——Vue Flow 画布与事件；只读，向页面抛 `select`/`focus`/`edgeSelect`/`toggleCollapse`，对外暴露 `fit`/`reset`/`locate`。
- `frontend/src/composables/useGraphLayout.ts`——**本次新增的布局引擎**：`dependencyLevels`（自顶向下分层 + 环检测）、`computeGraphLayout`（分层 + 父子横向编排 + 家庭区域打包）、`graphStructureSignature`（结构签名）、`useGraphLayout`（结构不变则保留坐标）。
- `frontend/src/workspace/dto.ts`——DTO 适配：`NODE_WIDTH=220`、`NODE_HEIGHT=120`、上/下 Handle id、`GroupInfo`、`buildMissionNodes`、`buildDependencyEdges`。
- `frontend/src/workspace/parentGrouping.ts`——父子森林 `buildForest`、可见性/折叠合并 `groupByParent`（返回可见 `nodes`/`edges`/`childrenOf`）、`revealPath`。
- `frontend/src/workspace/dependencyTraversal.ts`——已加载图上的展示层上下游遍历（`directRelations`、`collectRelated`、`relatedHighlight`）。
- `frontend/src/workspace/milestoneColor.ts`——按 `milestone_id` 稳定散列的卡片配色（`milestoneColor`、`milestoneLabel`）。
- `frontend/src/workspace/filters.ts`——前端筛选契约（`WorkspaceFilters`、`emptyFilters`、`readParam`）。
- `frontend/src/components/WorkspaceMissionCard.vue`——共享卡片；图内为 `compact`（固定高 120px）、里程碑色条/色块、子任务折叠控件与嵌套标记（`↳`）。
- `frontend/src/components/MissionGraphNode.vue`——图节点包装：上端 target Handle、下端 source Handle、卡片与折叠事件转发。
- `frontend/src/components/WorkspaceFilterBar.vue`、`MilestoneBoard.vue`、`MilestoneGroup.vue`、`MissionDetailDrawer.vue`——筛选栏、看板与详情抽屉。

### 2.2 数据模型与只读接口

- 数据模型：`Mission`（`id`、`title`、`type`、`priority`、`status`、`creator`、`assignee`、`reviewer`、`parent_id`、`milestone`、`version`、`created_at`、`updated_at`）、`MissionDependency`（`mission_id` 依赖 `prerequisite_id`）、`Milestone`。状态固定为 `Open`/`InProgress`/`Submitted`/`Done`/`Cancelled`。
- `GET /api/workspace/overview/`——里程碑 × 状态看板与摘要；参数含 `column_limit`（默认 20、上限 100）等共享筛选。
- `GET /api/workspace/graph/`——依赖图数据。参数：共享筛选 + `scope`（`team`/`milestone`/`mission`）、`focus`、`expand`（`none`/`one`/`all`）、`direction`（`upstream`/`downstream`/`both`）、`depth`（1–5）、`context`、`include_parent`。
  - 返回 `nodes`（`WorkspaceNode`：任务摘要 + 派生字段 `is_blocked`/`has_unresolved_prerequisites`/`requires_revalidation`/`blocking_count`/`unfinished_child_count`/`reviewer_missing`/`milestone_closed`/`allowed_actions`/`is_context`）、`edges`（`id`、`prerequisite_id`、`mission_id`、`is_satisfied`、`cross_milestone`）、`parent_edges`（`parent_id`、`child_id`，仅当 `include_parent=true` 且父子都在返回范围内）、`revision`（稳定数据修订标识）、`meta`。
  - 节点排序为 `_board_sort_key` = `(priority, created_at, id)`，**与状态无关**，因此状态刷新不会重排节点顺序。
  - 上限：节点 200（其中上下文 50）、依赖边 1000；触顶时 `meta.truncation_reasons` 与 `meta.relationships_complete=false`，前端据此提示。
- 权限：登录成员可见全部任务（无受限节点），只读接口不做写操作；`graph` 直接对应 `frontend/src/api/workspace.ts` 的类型化客户端。

### 2.3 前后端数据流

```
WorkspaceView.reload()
  → GET /api/workspace/graph/（带筛选 + scope/expand/direction/include_parent）
  → graph.value = { nodes, edges, parent_edges, meta, revision }
  → grouped = showParentRelations ? groupByParent(nodes, edges, parent_edges, collapsedParents) : null
  → visibleNodes / visibleEdges（节点为可见集合，边为折叠合并后的可见边）
  → <DependencyGraph :nodes :edges :grouping />（grouping = { descendantCount, collapsed, depth, childrenOf }）
      → useGraphLayout.update(visibleNodes, visibleEdges, { childrenOf })  // 结构签名不变则不重算
      → buildMissionNodes + buildDependencyEdges → Vue Flow 渲染
  → 折叠开关 / 折叠控件 → 更新 collapsedParents → grouped 重算 → 重新布局（不重新请求后端）
```

布局只用**已加载且可见**的节点与边；不写任何业务接口。视口/选中/定位由 Vue Flow 与页面保持，结构不变时坐标不变。

### 2.4 关键业务约束（与本次布局相关）

- 所有业务写入必须走 `missions/services.py`；依赖图与工作台**没有任何写接口**，画布的 `connect`/`remove`/`update`/拖动/删除一律禁用或不落地。
- 依赖方向固定 `prerequisite_id → mission_id`；父子关系是另一种关系，**不是依赖边**，不参与阻塞判断，也不改变完成约束。
- 禁止父子循环与自引用；依赖与父子组合环在服务层拒绝。折叠合并只在**前端展示层**重指向可见边，不写回后端。
- 折叠合并语义：隐藏子树的关系合并到折叠祖先；多条边合并为一条，仅当被合并的边**全部满足**才标记为已满足；落在折叠子树内部的边丢弃；自环丢弃。
- 关系完整性：以 `meta.relationships_complete` 为准；端点未加载的依赖不作为分层约束，也不当作“无依赖”。
- `WorkspaceNode.allowed_actions`、`is_blocked` 等均由后端计算，前端不自行推断权限或阻塞。

### 2.5 现有测试入口

- 前端布局与工作台单元测试：`frontend/src/tests/workspace.spec.ts`（`layered graph layout`、`parent/child grouping`、`DTO adapter`、`WorkspaceMissionCard`、`DependencyGraph`、`WorkspaceView` 等）。
- 真实 Vue Flow 挂载与坐标测试：`frontend/src/tests/workspaceGraph.integration.spec.ts`（含依赖方向、父子横向位置）。
- 测试环境 polyfill（`ResizeObserver`、`getBBox`）在 `frontend/src/tests/setup.ts`。
- 后端聚合测试：`backend/missions/tests/test_workspace.py`。
- 命令：前端 `npm run type-check` / `npm run test` / `npm run build`；后端 `manage.py makemigrations --check --dry-run` / `check` / `test`（并发与事务测试需 PostgreSQL）。

## 3. 实现状态

### 3.1 已完成

- **自顶向下分层**：`dependencyLevels` 用 `1 + max(所有可见前置层级)` 计算层级；卡片整体位于全部可见前置下方；层级与边数组顺序无关。
- **父子横向展开**：`computeGraphLayout` 按家庭（根 + 可见后代）局部排布，父任务在左、子任务逐级右移，同层不冲突的父子共享水平行。
- **依赖优先**：行由依赖层级决定，子任务有前置时排在其全部前置下方，同时保持在自己的家庭横向区间内。
- **区域预留**：家庭按行区间打包，行区间重叠的家庭列区间互斥，家庭区域不互相侵入、卡片不重叠。
- **折叠与选项**：沿用“显示父子任务关系”开关与折叠控件；折叠后隐藏子树、合并其依赖（AND 判定满足、内部边丢弃），布局按可见卡片与边重算；关闭开关时全部任务仍按自顶向下分层。
- **方向与提示**：图节点改为上/下 Handle，箭头自上而下；折叠合并产生依赖环时显示「依赖关系存在环」提示并保持可用。
- **稳定性**：结构签名不含状态/标题；纯状态刷新不重算坐标、不移动画布。
- **依赖与文档**：移除 `@dagrejs/dagre`（含 `package.json`/锁文件）；`PROJECT_STRUCTURE.md` 与 `TECH_STACK.md` 已同步。

### 3.2 明确不在本次范围

- 不新增甘特图、关键路径、工时预测、实时协同画布。
- 不做节点坐标持久化（刷新后按结构重算）或节点尺寸的真实测量（卡片为固定尺寸）。
- 环检测只保证“可绘制 + 有提示”，不在前端修复数据；组合环仍由后端服务层拒绝。
- 折叠状态不写入 URL（仅当前会话内保留）。
