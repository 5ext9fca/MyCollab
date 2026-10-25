# 前端条目卡片与交互统一

## 用户原始需求

- 移除“打开详情抽屉”，因其与点击卡片行为重复。
- 仿照先前提交，将所有选择框移至选择项卡片最左侧。
- 将通知条目重构为带选择框的卡片。
- 将设计/资产条目重构为卡片。
- 将“设计与资产”与“生产模板”切换重构为按钮。
- 修改里程碑条目的标题，复用 Mission 卡片的标题。
- 完成上述修改后，再次检查卡片审美的落实情况。

## 已有能力与本次范围

任务广场已通过 MissionCard 的 selection 插槽将复选框放在卡片内左侧，并阻止选择事件触发详情。该能力应复用，不重复实现。我的工作仍使用外置复选框和重复的“打开详情抽屉”按钮；通知是工具栏式条目；设计树是链接行；里程碑标题为链接内的 strong，与 Mission 标题不一致。

本次只改前端展示和交互，不新增后端模型、接口、权限或业务状态。条目选择框指任务和通知列表的多选框；甘特图关系显示、快捷筛选等布尔开关保持原有用途，不强行转换为条目选择卡片。

## 待实现规格

1. 我的工作移除重复详情按钮，复用 MissionCard.selection；选择框置于卡片左侧，正文和未完成子任务提示放在右侧卡片内容区。点击选择框只改变选择状态，点击卡片仍打开详情抽屉。
2. 通知列表每条使用 el-card shadow="never"，左侧复选框、右侧任务标题、已读状态、摘要和时间。选择不标记已读、不打开详情；打开通知仍先标记已读，成功后打开关联任务。保留分页、筛选和批量已读行为。
3. 设计树中的每个设计/资产条目使用独立卡片，保留标题导航、类型、归档状态、展开/折叠和分页加载。根据后续修订，资产子卡片嵌入所属设计母卡片内，保留展开/折叠，以轻边框表达归属。详情中独立功能区按卡片分组。
4. 两个页面使用一致的“设计与资产 / 生产模板”按钮导航，当前页高亮，保留既有路由与新建操作；页头等宽侧列固定导航位置，小屏导航独占第二行。
5. 提取可复用的卡片标题样式，Mission、里程碑及本次新增条目统一使用；里程碑保留原详情路由、状态与进度，不改业务标题文字。
6. 落实 .cursor/rules/card-aesthetics.mdc：轻边框、无悬浮阴影、相邻区域通常 16px、内部 8–12px；标题/说明/操作同区；长标题可换行，小屏不撑破页面。交互保留键盘入口和焦点；卡片内选择与展开操作不误触打开。

## 当前项目结构与数据流

- frontend/src/components/MissionCard.vue：任务卡片、路由跳转或 open 事件、已有 selection 插槽。frontend/src/style.css 提供全局卡片标题和间距样式。
- frontend/src/views/MissionSquareView.vue：已实现卡片左侧选择框；作为复用基线。
- frontend/src/views/MyWorkView.vue：workMissions/workSummary 加载六类待办，selectedIds 交给 BulkMissionEditor；selected 驱动 MissionDetailDrawer。分类/分页对应 resetKey，保留现有清选逻辑。
- frontend/src/views/NotificationsView.vue：listNotifications 加载分页，readNotifications 成功后 notifyChanged、刷新列表并设置抽屉 target；API 位于 frontend/src/api/notifications.ts。通知字段含 id、mission、mission_title、payload.summary、created_at、read_at。
- frontend/src/components/DesignTreeBranch.vue：递归分页加载 listDesignElements；expanded 集合控制子树。筛选时保持现有列表查询规则。
- frontend/src/views/DesignView.vue：设计搜索/筛选、条目详情、MarkdownContent、直属进度、ProductionPanel、关联任务与活动记录。数据来自 api/designElements.ts 和 api/missions.ts；写操作保持既有版本校验与 allowed_actions。
- frontend/src/views/ProductionTemplatesView.vue：模板列表、详情、编辑和归档；本次只调整页面切换导航及必要布局。
- frontend/src/views/MilestoneListView.vue：里程碑卡片；name 为标题，状态/延期/日期/进度独立展示。
- frontend/src/api/types.ts：Mission、DesignElement、Milestone 等现有类型；不改接口字段。

## 约束与验证

- API 调用仍集中于 src/api；Markdown 继续经 MarkdownContent 清洗渲染。
- 不改变任务选择上限、批量计划修改权限、通知已读授权或设计/模板写入权限。
- 回归入口：frontend/src/tests/myWork.spec.ts、designElements.spec.ts、productionTemplates.spec.ts、bulkUpdates.spec.ts、workspace.spec.ts；新增必要的选择/打开隔离与键盘交互测试。
- 按顺序运行前端 npm run type-check、npm run test、npm run build。此次没有后端变更，无需重跑后端套件。
- 完成后同步 PROJECT_STRUCTURE.md 的页面交互规则，并在本文记录验收结果。

## 实现与验收结果

本规格已实现。任务/通知选择框位于卡片左侧；重复详情按钮已移除；设计树和详情功能区、通知、模板列表/详情均按卡片分组；新增 DesignNavigation 统一按钮切换；全局 card-title 复用 Mission 的标题样式并提供原生键盘入口。

卡片审美复查已统一无阴影、区域间距、长标题换行及焦点样式；设计子树按后续需求嵌入母卡片内，选择与展开事件独立于打开详情。全仓复查未再发现“打开详情抽屉”或 shadow="hover"；剩余非条目选择框均为显示/筛选开关。

验证：前端 type-check 通过，19 个测试文件共 99 项测试通过，生产构建通过（保留原有大体积 bundle 提示）。新增 4 项交互测试。后端未修改，未重复运行后端测试。本次未完成浏览器截图验收，小屏布局依据响应式样式和代码检查确认，未宣称实际设备验收。
