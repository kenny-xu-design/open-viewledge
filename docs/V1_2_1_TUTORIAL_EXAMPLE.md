---
title: "如何用 Codex 管理一个长期项目"
source: "https://www.bilibili.com/video/BV1dY7S6yEQu/"
platform: "bilibili"
author: "oil欧呦"
knowledge_id: "如何用 Codex 管理一个长期项目_BV1dY7S6yEQu"
analysis_profile: "tutorial"
generator_version: "1.2.1"
created: "2026-07-18"
type: "video-note"
status: "processed"
tags:
  - 外源/视频
  - AI摘要
  - tutorial
---

# 如何用 Codex 管理一个长期项目

> [!info] 视频来源
> - 平台：B站
> - 作者：oil欧呦
> - 原视频：[打开视频](https://www.bilibili.com/video/BV1dY7S6yEQu/)
> - 分析类型：tutorial

## 摘要

视频介绍了如何通过独立项目目录、`AGENTS.md`、项目级 Skill 和可重复执行的 Workflow，让 Agent 在长期任务中持续读取项目规则与既有资料。

## 亮点

- **项目与临时对话的区分**：长期任务应保存在独立工作区中，让文件成为可持续读取的项目记忆。[00:00](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=0)
  `#项目管理` `#Codex`

- **AGENTS.md 入口文件**：用统一入口描述项目目标、目录结构与执行约束。[02:31](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=151)
  `#AGENTS.md` `#项目初始化`

- **项目级 Skill**：将只服务于当前项目的 Skill 放在项目目录，避免污染其他任务。[03:43](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=223)
  `#Skill` `#项目隔离`

## 前置条件

- 已经建立长期项目目录。（[01:28](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=88)）
- 能够查看并维护项目中的 Markdown 文件。

## 操作步骤

### 1. 建立独立项目工作区

为长期任务选择独立目录，使相关文件、数据和后续对话集中在同一项目中。

- 时间：[01:28](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=88)
- 预期结果：项目资料不会与临时聊天混在一起。

### 2. 创建或检查 AGENTS.md

在项目根目录维护 `AGENTS.md`，说明项目定位、重要文件和执行规则。

- 时间：[02:31](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=151)
- 预期结果：Agent 进入项目后能快速理解任务边界。

### 3. 将专用 Skill 放入项目目录

只在当前项目需要的 Skill 应保持项目级作用域。

- 时间：[03:43](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=223)
- 预期结果：其他项目不会误触发这些专用规则。

## 关键术语

- **AGENTS.md**：向 Agent 说明项目目标、目录结构和执行规则的项目入口文件。
- **项目级 Skill**：只在当前项目中生效的技能说明。
- **Workflow**：由多个固定步骤组成、可以重复执行的工作流程。

## 可执行动作

- [ ] 创建或检查项目根目录的 `AGENTS.md`（[02:31](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=151)）
- [ ] 将项目专用 Skill 放入项目目录（[03:43](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=223)）
- [ ] 整理长期项目的文件结构（[07:23](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=443)）

## 注意事项

- 不要把只服务于单个项目的 Skill 全部放到全局环境。（[04:20](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=260)）

## 视频章节总结

### [00:00](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=0) 项目与聊天的区别

区分临时聊天与长期项目，说明文件如何承担项目记忆。

### [01:28](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=88) 创建项目与 AGENTS.md

介绍项目创建与入口文件的作用。

### [03:43](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=223) 项目级 Skill 管理

说明如何减少全局技能污染。

### [07:23](https://www.bilibili.com/video/BV1dY7S6yEQu/?t=443) 总结与最佳实践

通过目录、Workflow 和项目级 Skill 维护长期任务。

## 原文资料

- [分组字幕](../output/如何用%20Codex%20管理一个长期项目_BV1dY7S6yEQu/transcript.grouped.md)
- `transcript.raw.jsonl`
- `timeline.json`
