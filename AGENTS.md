# AGENTS.md

## 项目概览

MyCollab 是一个**单团队 Mission 协作系统**：发布 Mission、认领未分配任务、拆分为可独立认领的子任务，走「发布 → 认领 → 拆分 → 执行 → 提交 → 验收」。后端 Django API + Vue SPA + Docker 部署均已实现并可运行。

- 产品规则与数据模型：`PROJECT_STRUCTURE.md`
- 技术栈与实现约束（MUST 为硬性要求）：`TECH_STACK.md`
- 命令与本地上手：`README.md`

浏览器文件直传的隔离验收命令见下方开发验证规则与 `README.md`。

已实现功能包括：Mission 全流程、任务下的 Markdown 评论（作者可编辑/删除）、按用户隔离的素材库（文件按用户存放，Markdown 只可引用自己的素材或外链 URL）、用户注册（需管理员审批）、以及 SPA 内自行实现的管理后台（`/manage`，区别于 Django Admin）。

两份设计文档为中文；用户明确的需求优先，与文档冲突时先改规则与测试，再改代码。

## 项目规则入口

以下规则共同构成本项目的 Agent 指令，与本文件同样有效。开始工作前读取全部规则；即使工具不会自动加载 `.cursor/rules/*.mdc`，也必须按此索引读取。具体条款按各规则的适用场景执行。

- [沟通语言](.cursor/rules/communication.mdc)
- [发布阶段与数据库兼容性](.cursor/rules/database-lifecycle.mdc)
- [开发命令与验证（含 testrun 自动启动 LocalRunner）](.cursor/rules/development-validation.mdc)
- [架构与业务约束](.cursor/rules/architecture.mdc)
- [需求规格与文档同步](.cursor/rules/documentation.mdc)
- [提交与推送规范](.cursor/rules/git-workflow.mdc)
- [前端卡片审美](.cursor/rules/card-aesthetics.mdc)
- [前端超链接审美](.cursor/rules/link-aesthetics.mdc)

## 维护方式

- 本文件只保留项目概览、规则索引与加载要求；详细约束在对应规则中维护，避免重复或互相矛盾。
- 新增或拆分规则时同步更新索引；使用中文说明、明确职责，并保持原有授权与约束完整。
