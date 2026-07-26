# Nanobot Runtime 的 Career-only 改造范围

> 2026-07-26 产品决策：Nanobot 是本项目可自由改造的源码基础，不再以兼容通用个人助手为目标。

## 1. 核心原则

- 最终发布和运行只服务 Nanobot Career。
- 不为旧 Nanobot 业务长期保留重复的业务状态路径；AgentLoop、Cron、Channel 和 Tool 作为基础能力保留并按 Career 需求改造。
- 可复用的底层能力抽取后复用；不符合产品要求的模块重写并在迁移完成后删除。
- Career 的长期上下文是结构化业务知识和事件，不是聊天摘要或 Markdown Memory。
- 用户主要通过 Web 明确操作；Agent 主要是固定输入输出的后台 Task Agent，不是自由对话主循环。

## 2. 目标运行链路

```text
Web UI
→ Career API Command/Query
→ Domain + Database
→ Background Job / Workflow
→ Career Agent Task Runtime
→ Schema validation + Proposal
→ ReviewTask
→ Confirmed Domain Event
```

## 3. 模块处置

| 现有能力 | 目标处置 | 迁移结果 |
|---|---|---|
| Provider registry/adapters | 抽取、保留并增强 | 增加 Provider 隐私和本地/在线路由策略 |
| Agent Runner 的请求/重试/转换 | 抽取复用 | 成为 `CareerAgentTaskRuntime` 的模型调用层 |
| Agent Loop | 保留并重构 | 统一核心支持 interactive/task 两种受策略控制的执行模式 |
| MemoryStore/Consolidator | 重写 | 删除 Markdown 全量 consolidation，改接业务知识和 ContextPack |
| ContextBuilder | 重写 | 按 Task ContextManifest 构造最小上下文 |
| SessionManager/JSONL | 保留抽象并评估存储重构 | 只服务短期交互，不承担业务状态和审计 |
| Tool Registry/Base Tool | 保留并增强 | 按 execution policy、风险和数据范围控制暴露 |
| CronService/cron Tool | 保留并重构 | 与 DB Schedule 合并，负责定时触发 Job/Notification |
| MessageBus | 保留并明确边界 | 用于运行时消息，不替代 Domain Event/Outbox |
| Email Channel | 拆分改造 | 入站使用严格只读 IMAP，出站可发送通知 |
| 其他 Chat Channels | 保留并改造 | 以向用户发送提醒为主，未来支持安全回执 |
| Skills Loader/通用 Skills | 保留并规范 | 正式任务使用版本化 Task Prompt/Schema |
| filesystem/exec/web 通用 Agent Tool | 保留并策略隔离 | 不默认开放给处理不可信输入的后台任务 |
| 旧 Career store/resume tool | 直接删除旧业务逻辑 | 不做旧数据迁移，只清理引用和旧测试 |

## 4. 业务知识而非传统对话记忆

| 层次 | Career 实现 |
|---|---|
| 工作上下文 | 单次 Task 的临时 `ContextPack` |
| 经历/事件 | ApplicationEvent、MailEvidence、InterviewRecord、用户操作事件 |
| 语义知识 | confirmed CandidateFact、Preference、Company、Job、CapabilityEvidence |
| 反思结果 | ProfileInsight、ImprovementItem、StrategySnapshot Proposal |
| 程序知识 | 版本化 Workflow、Prompt、Schema 和 Domain Rule |
| 检索层 | 结构化查询、FTS 和可重建 embedding 索引 |

Agent 不拥有 `save_memory` 之类的通用长期写入能力。Agent 只能提出带证据的业务 Proposal，经 Schema 和 Domain 校验、必要时经用户确认后，写入明确的业务实体。

## 5. 删除条件

旧 Career Store、Resume Service 和重复 Career Tool 在以下条件满足后直接删除，不做旧数据迁移：

1. 新路径已覆盖全部实际调用。
2. 已确认不需要保留旧 Career 数据。
3. 安装、CLI、Web 和后台任务不再引用旧模块。
4. 自动化与真实验收通过。
5. 备份恢复和回滚方案已经验证。

AgentLoop、CronService、Channels、Tool Registry 不适用上述删除清单；它们按照 Career 产品需要重构并继续使用。详细产品和 Runtime 设计见根目录 `PRODUCT_FUNCTION_DESIGN.md` 第 23 节。
