# CareerConsole 技术实现方案

> 文档状态：工程底座方案；2026-07-26 起 Runtime 处置以[产品功能设计](../product/product-function-design.md)第 23 节为准
> 依据：[CAREER_REQUIREMENTS_ANALYSIS.md](./CAREER_REQUIREMENTS_ANALYSIS.md)  
> 日期：2026-07-22  
> 目标：将需求分析收敛为一套可实施、可测试、可演进的工业级工程方案

## 1. 方案结论

本项目采用**本地单用户、模块化单体、事件驱动的后台任务模型**。

整体技术定位：

```text
React Local Web UI
        ↓ REST / SSE
FastAPI Application
        ↓
Career Application Services
        ↓
Career Domain + Unit of Work
        ↓
SQLite / File Store / Outbox / Job Queue
        ↑
Connector Workers + Agent Task Workers
        ↓
IMAP / OpenCLI / Model Providers / Local Files
```

核心技术决策：

| 领域 | 选型 |
|---|---|
| 架构形态 | 模块化单体，不拆微服务 |
| 后端 | Python 3.11+、FastAPI、Pydantic v2 |
| ORM/迁移 | SQLAlchemy 2.0、Alembic |
| 数据库 | SQLite，WAL 模式、短事务、显式 Unit of Work |
| 前端 | React、TypeScript、Vite、React Router、TanStack Query |
| 后台任务 | 数据库持久化 Job Queue + 进程内 Dispatcher/Worker |
| 调度 | 数据库 Schedule + `croniter` 计算，不以 Agent turn 作为调度单位 |
| 外部事件 | Source Event + Inbox 去重 + Transactional Outbox |
| Agent | 保留并重构 AgentLoop，统一支持 interactive/task execution policy；业务知识不使用 Markdown Memory |
| 招聘网站 | 将 OpenCLI 作为外部应用，通过受控子进程使用其公开 CLI 和 Browser Bridge；Career 侧只做输出校验与业务映射 |
| 邮箱 | 新建严格只读 IMAP Connector |
| 文件 | 本地内容寻址 File Store，数据库只保存元数据和引用 |
| Secret | OS Keyring；配置和数据库只保存 `secret_ref` |
| 进度推送 | SSE；不以 WebSocket 作为 P0 必需能力 |
| 日志 | 延续 Loguru，增加结构化字段、滚动、脱敏和关联 ID |
| 打包 | Python wheel + 预构建 Web 静态资源；OpenCLI 保持外部依赖 |

本方案特意不引入 Redis、Celery、Kafka、PostgreSQL 或 Kubernetes。对于本地单用户产品，这些组件会显著增加安装和运维成本，而无法带来等比例收益。接口和数据边界仍按照未来可替换数据库、拆分 Worker 的方式设计。

## 2. 目标和约束

### 2.1 技术目标

1. 关键业务状态由确定性代码维护，不能依赖聊天上下文或 Prompt 记忆。
2. 外部同步可增量、可恢复、可幂等、可审计。
3. Agent 只处理适合模型的非结构化任务，并通过受控接口访问业务数据。
4. 任何重要状态变化都有来源、证据、置信度和确认记录。
5. 本地数据、Secret 和外部模型调用满足隐私最小化原则。
6. Windows 为首要开发和 Demo 平台，同时保持 Linux/macOS 可移植性。
7. 不以旧 CareerConsole 业务兼容为目标；只保留符合 Career 产品需求且优于重写成本的底层能力。

### 2.2 非目标

- 不设计多租户和企业权限体系。
- 不拆分网络微服务。
- 不实现跨设备实时同步。
- 不使用自动批量投递、自动发邮件或自动招聘沟通。
- 不把 OpenCLI 内部源码嵌入 Python 进程。
- 不修改 OpenCLI 本体及其内置通用 Adapter；站点能力缺失时允许在本项目维护独立安装、只读、受 allowlist 控制的 OpenCLI Plugin。
- 不把通用 Chat Channel、对话 Memory、Session 或 agent-turn Cron 带入 Career 发布运行路径。

### 2.3 已确认的代码处置前提

现有 CareerConsole 是可完全调整的源码基础，而不是需要兼容的独立产品。技术处置以 Career 价值为唯一判断依据：

- **保留**：不影响 Career 主流程、安全和模块边界，并可能支持未来扩展。
- **扩展**：职责基本合适，只需增加接口、策略或测试。
- **重构/重写**：现有结构会导致业务状态不确定、权限过大、耦合或可靠性问题。
- **迁移后删除**：新路径接管后删除旧实现，避免长期双轨。
- **删除/退出发布包**：与 Career 无关、功能重复或持续带来依赖、安全和维护负担。

不为了重构形式而移动代码，也不为了旧产品兼容而保留两套业务状态。Provider、Runner、AgentLoop、Cron、Channels、Skills 和 Tools 具有基础能力价值，按 Career-only 目标保留并重构；Markdown Memory、旧 Career Store 等错误业务模型直接替换或删除。

## 3. 工业级设计原则

### 3.1 依赖倒置

Domain 只包含实体、值对象、策略和领域错误。数据库、HTTP、Agent、OpenCLI、IMAP 都通过 Application Port 接入。

```text
Web/API ───────────────┐
CLI ───────────────────┤
Scheduler/Worker ──────┼→ Application → Domain
Agent Tools ───────────┤       ↑
Connectors ────────────┘       Ports
                                ↑
                         Infrastructure
```

### 3.2 命令和查询分离

- Command 表示会改变状态的业务动作，例如 `ConfirmApplicationEvent`。
- Query 表示只读查询，例如 `GetApplicationTimeline`。
- API 不允许用通用 PATCH 直接修改状态字段。
- Agent Tool 必须映射到具体 Command 或 Query。

不需要引入完整 CQRS 框架；读写仍使用同一 SQLite，只在代码职责上分离。

### 3.3 短事务

数据库事务内禁止等待：

- 网络请求。
- IMAP/OpenCLI 操作。
- LLM 调用。
- PDF/DOCX 转换。
- 用户确认。

外部操作通过 Job 分阶段执行，每一阶段以短事务保存状态和输出。

### 3.4 至少一次执行、业务幂等

本地进程崩溃后，后台任务可能被再次执行。本方案不承诺基础设施层“恰好一次”，而是采用：

```text
At-least-once delivery
+ Idempotency Key
+ Unique Constraint
+ State Transition Guard
= Effectively-once business result
```

### 3.5 不可变证据和可重建投影

- `SourceEvent`、`ApplicationEvent`、材料最终快照不可变。
- 当前申请状态、Dashboard 计数等是可重建投影。
- 错误信息通过追加更正或 supersede 表达，不原地销毁历史。

### 3.6 默认拒绝高风险能力

- Connector 命令采用 allowlist。
- Agent Tool 采用 allowlist。
- 未识别的外部字段不自动写入事实或状态。
- 未配置 Secret 时失败关闭，不回退到明文配置。

## 4. 运行拓扑

### 4.1 生产态本地拓扑

```text
┌─────────────────────────────────────────────────────────┐
│ User Browser                                            │
│ React UI @ http://127.0.0.1:<port>                      │
└──────────────────────┬──────────────────────────────────┘
                       │ REST / SSE
┌──────────────────────▼──────────────────────────────────┐
│ CareerConsole process                                  │
│                                                        │
│ FastAPI ─ Application Services ─ Domain                 │
│               │                   │                     │
│               ├─ Job Dispatcher ─ Workers               │
│               ├─ Scheduler                              │
│               ├─ Agent Runtime                          │
│               └─ Connector Runtime                      │
│                                                        │
│ SQLite + File Store + Config + Secret references        │
└───────────────┬──────────────────────┬──────────────────┘
                │                      │
       controlled subprocess           │ IMAP TLS
                │                      │
┌───────────────▼─────────────┐  ┌─────▼──────────────┐
│ OpenCLI CLI + local daemon  │  │ Mail Server       │
│ Browser Bridge Extension    │  └────────────────────┘
│ Chrome/Chromium Profile     │
└─────────────────────────────┘
```

### 4.2 进程模型

P0 使用一个 Python 主进程，内部包含：

- FastAPI Server。
- Scheduler tick loop。
- Job Dispatcher。
- 受限数量的异步 Worker。
- Agent Runtime。

默认 Worker 并发建议：

| 工作类型 | 并发 |
|---|---:|
| DB-only Command | 1 个写入串行通道 |
| OpenCLI Connector | 每个 Browser Profile 1 |
| IMAP Connector | 每个账户 1，全局最多 2 |
| LLM Task | 全局 2，可配置 |
| 文件解析/导出 | 全局 2 |

SQLite 写事务仍可能来自多个协程，因此所有 Repository 写操作都通过 Unit of Work 和统一 Engine；`busy_timeout` 负责短暂竞争，业务代码不得持有长事务。

未来若任务量增加，可把 Worker 启动为独立本地进程，但 Job、Lease 和 Port 不需要重写。

### 4.3 启停顺序

启动：

```text
解析数据目录和配置
→ 初始化脱敏日志
→ 获取应用实例锁
→ 连接数据库并设置 PRAGMA
→ 校验 schema revision
→ 恢复过期 Job lease
→ 初始化 Secret Store
→ 初始化 Agent Provider
→ 启动 Scheduler/Dispatcher
→ 启动 FastAPI
→ 标记 readiness=true
```

关闭：

```text
readiness=false
→ 停止接收新后台任务
→ 等待当前短任务到安全点
→ 释放 Job lease
→ 关闭 IMAP/OpenCLI 子进程句柄
→ flush 日志和数据库连接
→ 释放实例锁
```

## 5. 技术选型详解

### 5.1 后端 Web：FastAPI

选择 FastAPI 的原因：

- 与现有 Pydantic v2 类型体系一致。
- OpenAPI 自动生成便于前后端契约和测试。
- 原生 async，适合 SSE、IMAP 和子进程编排。
- 生态中间件和 Problem Details 支持成熟。

Career Web 推荐 FastAPI。现有 `aiohttp` Chat API 的处理方式：

1. 新建 FastAPI app 和 Career `/api/v1` 路由。
2. 为 Local Web 和 Task Agent 实现产品所需接口。
3. 新入口稳定且确认无迁移调用后删除旧 API，不作为独立兼容产品入口保留。
4. 两套 API 不共享业务逻辑，均通过 Application Service；不长期复制实现。

### 5.2 前端：React + TypeScript

选择独立前端而非服务端模板，因为产品包含看板、时间线、后台进度、批量确认、筛选和复杂编辑状态。

推荐依赖：

- React 19 或项目建立时的稳定主版本。
- TypeScript strict mode。
- Vite。
- React Router。
- TanStack Query 管理 server state。
- React Hook Form + Zod 管理表单和前端校验。
- Zustand 仅用于少量纯 UI 状态；禁止复制服务端业务状态。
- UI 组件选择一个轻量、可访问性良好的体系，并统一主题，不同时引入多个组件库。

前端 API 类型由 OpenAPI 生成，避免手写重复 DTO。

### 5.3 数据访问：SQLAlchemy 2.0 + Alembic

选择原因：

- 当前手写 sqlite3 Store 无法支撑迁移、关系、事务和测试隔离。
- SQLAlchemy Repository 可以保持 Domain 与 SQLite 解耦。
- Alembic 提供显式、可审查、可回滚评估的迁移版本。

约束：

- ORM Model 不是 Domain Entity。
- Repository 完成 ORM 与 Domain 之间的映射。
- API DTO 也不能直接复用 ORM Model。
- 禁止在 route handler 内直接使用 Session 执行任意 SQL。

### 5.4 SQLite 配置

连接初始化设置：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

要求：

- 每个 Command 一个 Unit of Work。
- 写事务目标小于 100ms。
- 网络和模型调用在事务外执行。
- 所有外键显式启用。
- 高频查询建立组合索引并通过 query plan 验证。
- 每次 schema migration 前自动创建可恢复备份。

### 5.5 后台任务：数据库 Job Queue

不使用 Celery。实现最小但可靠的持久化 Job 系统：

```text
background_jobs
- id
- job_type
- payload_json
- idempotency_key UNIQUE
- status
- priority
- run_after
- attempt_count
- max_attempts
- lease_owner
- lease_expires_at
- last_error_code
- last_error_message_redacted
- created_at / started_at / finished_at
```

状态：

```text
pending → running → succeeded
                 ↘ retry_wait → running
                 ↘ failed
pending/running → cancelled
```

Worker 领取任务时使用条件更新获得 lease。进程崩溃后，`lease_expires_at` 到期的任务可重新领取。每种 Job Handler 声明：超时、最大重试、退避策略、并发键和幂等策略。

### 5.6 调度器

`schedules` 表保存：

- `schedule_type`：cron/interval/once。
- `expression`、`timezone`。
- `job_type`、`payload_json`。
- `next_run_at`、`last_enqueued_at`。
- `enabled`。

Scheduler 只负责按时向 `background_jobs` 投递确定性任务。默认每秒或数秒 tick，一次性补偿有限窗口内错过的任务。

保留并重构现有 `CronService`：复用 cron 计算、时区、一次性和周期调度能力，引入数据库 `ScheduleRepository` 和类型化 Job/Notification payload。Scheduler 负责何时触发，BackgroundJob Worker 负责可靠执行，最终不保留 JSON Cron 与 Career DB Schedule 两套状态。

## 6. 模块划分

### 6.1 顶层目录

```text
CareerConsole/
├── career_console/runtime/
│   ├── agent/                     # 保留并按需增强的通用 Runtime
│   ├── providers/
│   ├── session/
│   ├── bus/
│   ├── channels/                  # 可选扩展，默认不进入 Career 主流程
│   ├── career/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   ├── connectors/
│   │   ├── agent/
│   │   └── api/
│   ├── api/
│   └── cli/
├── web/
│   ├── src/
│   ├── tests/
│   └── package.json
├── migrations/
├── resources/
│   ├── adapter_descriptors/
│   ├── schemas/
│   ├── prompts/
│   └── templates/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   └── fixtures/
├── tools/
└── docs/
```

在现有包内先建立 `career_console` 的清晰边界。通用 Agent 模块保持可用，Career 代码通过 Port 使用其能力。只有确认发生职责冲突、循环依赖或安全问题时才移动或重写旧模块；删除只针对确认冗余且没有扩展价值的内容。

### 6.2 Domain 模块

```text
career/domain/
├── common/
│   ├── ids.py
│   ├── time.py
│   ├── errors.py
│   └── events.py
├── profile/
├── documents/
├── opportunities/
├── jobs/
├── materials/
├── applications/
├── messages/
├── planning/
├── interviews/
├── reviews/
└── connectors/
```

各子域职责：

| 子域 | 核心聚合/规则 |
|---|---|
| Profile | CandidateProfile、CandidateFact、FactSource、确认/替代规则 |
| Documents | Document、BlobReference、哈希和保留策略 |
| Opportunities | RecruitmentOpportunity、OpportunitySource、OpportunityVersion、OpportunityJobLink、分流状态 |
| Jobs | Company、JobPost、JobPostVersion、Requirement、MatchAnalysis |
| Materials | Resume、ResumeVersion、Draft、Review、Export、Snapshot |
| Applications | Application、ApplicationEvent、EventProposal、状态机 |
| Messages | Message、MessageEntity、邮件分类结果 |
| Planning | Task、Reminder、时间冲突 |
| Interviews | Interview、Record、Question、Feedback |
| Reviews | ReviewTask、Resolution、到期策略 |
| Connectors | ConnectorConfig、SyncCursor、SyncRun、SourceEvent |

### 6.3 Application 模块

```text
career/application/
├── commands/
├── queries/
├── handlers/
├── dto/
├── ports/
├── policies/
└── services/
```

Ports 至少包括：

- `UnitOfWork`。
- 各聚合 Repository。
- `BlobStore`。
- `SecretStore`。
- `Clock`。
- `IdGenerator`。
- `AgentTaskPort`。
- `ConnectorPort`。
- `ProcessRunner`。
- `EventPublisher`。
- `TranscriptionPort`。

Handler 负责：加载聚合 → 调用领域行为 → 保存 → 写 Outbox → 提交事务。

### 6.4 Infrastructure 模块

```text
career/infrastructure/
├── database/
│   ├── models/
│   ├── repositories/
│   ├── uow.py
│   └── engine.py
├── jobs/
├── scheduler/
├── files/
├── secrets/
├── process/
├── logging/
└── settings/
```

### 6.5 Connector 模块

```text
career/connectors/
├── runtime.py
├── contracts.py
├── errors.py
├── email_imap/
│   ├── connector.py
│   ├── client.py
│   ├── parser.py
│   ├── cursor.py
│   └── filters.py
├── opencli/
│   ├── connector.py
│   ├── runner.py
│   ├── descriptor.py
│   ├── schema.py
│   └── error_mapping.py
└── files/
```

Connector 只产出标准化事件和游标，不导入 Application Repository。牛客公司招聘批次映射为 `RecruitmentOpportunity`；只有包含具体职责和任职要求的真实 JD 才映射为 `JobPost`。从机会导入 JD 时，岗位版本和 `OpportunityJobLink` 必须在同一事务内提交，重复命令保持幂等。

### 6.6 Agent 模块

```text
career/agent/
├── task_runner.py
├── context_policy.py
├── output_validation.py
├── prompt_registry.py
├── tools/
└── workflows/
```

`AgentTaskPort` 适配同一个 AgentLoop 的 task execution policy，复用 Provider、重试、消息转换和 Tool Registry；固定 Context、Schema、预算和 allowlist。Application 层只依赖 Port，Domain 不依赖 AgentLoop 实现。

Phase A 已落地统一审计读模型：`AgentRun` 记录 Provider、模型、版本、输入引用与哈希、工具摘要、Token、耗时、重试、错误和敏感等级；`ReviewTask` 记录跨事实、申请事件和面试反馈的统一人工确认投影，并可引用产生候选的 AgentRun。通用审查查询不直接执行领域确认命令。

### 6.7 API 模块

```text
career/api/
├── app.py
├── dependencies.py
├── errors.py
├── middleware/
├── schemas/
└── routes/
```

Route 只负责鉴权、参数解析、调用 Handler 和响应映射。

## 7. 模块依赖和边界检查

允许依赖：

```text
domain → Python standard library
application → domain + application ports
infrastructure → application ports + domain types
connectors → connector contracts + application DTO
agent adapter → application ports + existing CareerConsole runtime
api → application commands/queries
cli → application commands/queries
web → HTTP API only
```

禁止依赖：

- Domain 导入 FastAPI、SQLAlchemy、OpenCLI、IMAP 或 CareerConsole Agent。
- Connector 直接更新 Application 或 Candidate Fact。
- Agent Tool 直接访问 SQLAlchemy Session。
- API route 直接访问 ORM Model。
- 前端根据本地猜测改变最终申请状态。
- Infrastructure 反向调用 API。

CI 增加架构依赖测试，可使用 `import-linter` 或自定义 AST 检查强制上述规则。

## 8. 数据规范

### 8.1 ID、时间和版本

- 所有业务实体使用 UUID4 字符串，API 不暴露自增数据库 ID。
- 所有时间在 Domain 中必须是 timezone-aware `datetime`。
- 数据库存储 UTC，API 使用 RFC 3339；用户界面按 Profile timezone 转换。
- 每个可并发修改的聚合包含 `version`，Command 使用乐观锁。
- 外部版本单独记录 `external_updated_at`，不能与 `collected_at` 混用。

### 8.2 JSON 字段

JSON 只用于：

- 外部原始 payload。
- 类型差异明显且无需跨行检索的扩展字段。
- Job/Outbox payload。

需要筛选、唯一约束、关联和统计的字段必须正规化。JSON Schema 必须有版本号。

### 8.3 软删除和数据删除

- 核心审计数据不使用无条件物理删除。
- 用户删除个人数据是例外，必须按数据图执行受控级联并写入本地删除审计；审计中不得残留已删除敏感内容。
- Connector 禁用和 Source 删除分开：禁用不删除历史。
- 文件 Blob 只有在无引用后才由垃圾回收 Job 删除。

### 8.4 主要表组

```text
Profile:
  candidate_profiles, candidate_facts, fact_sources, fact_revisions

Documents/Materials:
  documents, blobs, resumes, resume_versions,
  material_reviews, material_exports, application_material_snapshots

Jobs:
  companies, company_aliases, job_posts, job_post_versions,
  job_post_sources, job_requirements, job_match_analyses, job_match_evidence

Applications:
  applications, application_events, application_event_proposals

Messages/Interviews:
  messages, message_entities, interviews, interview_records,
  interview_questions, interview_feedback

Planning/Review:
  tasks, reminders, review_tasks, review_resolutions

Integration/Audit:
  connectors, sync_cursors, sync_runs, source_events,
  agent_runs, agent_actions, background_jobs, schedules,
  outbox_events, audit_entries
```

### 8.5 关键唯一约束

- `source_events(connector_id, deduplication_key)`。
- `sync_cursors(connector_id, scope_key)`。
- `job_post_sources(source_id, external_id)`。
- `messages(mail_account_id, folder, uid_validity, uid)`。
- Message-ID 不是所有邮箱都稳定，作为辅助唯一条件而不是唯一依据。
- `background_jobs(idempotency_key)`。
- `outbox_events(event_id)`。
- 同一 Application 同一 Proposal source/event fingerprint 唯一。

## 9. 一致性与事件机制

### 9.1 三类事件

必须区分：

1. `SourceEvent`：外部数据采集事实，例如收到一封邮件。
2. `DomainEvent`：领域行为结果，例如申请事件已确认。
3. `OutboxEvent`：需要异步分发的持久化消息。

不能把三者混成一张“万能事件表”。

### 9.2 Transactional Outbox

Command 在同一数据库事务中保存：

- 聚合变化。
- Domain Event 对应的 Outbox 记录。

Outbox Dispatcher 事务外领取并创建后续 Job。即使进程在提交后崩溃，Outbox 仍能重放。

示例：

```text
ConfirmApplicationEvent Command
  [DB transaction]
    → 写 application_event
    → 更新 application.current_status
    → 完成 review_task
    → 写 outbox(application_event_confirmed)
  [commit]
Outbox Dispatcher
    → enqueue reminder_reconcile
    → enqueue interview_prep_if_needed
```

### 9.3 Inbox/幂等消费

Source Event 通过 deduplication key 进入 Inbox。处理器保存 `processing_status` 和处理版本。解析器或规则升级时，可以创建新的处理版本重放，不重新采集外部数据。

### 9.4 并发控制

- Application、Resume、Review Task 使用 `version` 乐观锁。
- Connector 同步使用 `concurrency_key=connector:<id>`，同一来源同时最多一个 Job。
- OpenCLI 进一步使用 `profile:<alias>` 锁，避免多个任务争用同一浏览器 Profile。
- IMAP 使用 `mail-account:<id>:<folder>` 锁。
- 状态冲突返回 409，并提供当前版本和可重试信息。

## 10. 核心执行流程

### 10.1 简历导入和事实确认

```text
UI 上传文件
→ POST /documents/import
→ BlobStore 计算 SHA-256 并原子写入
→ 创建 Document + parse_document Job
→ Parser 提取文本
→ enqueue agent.extract_candidate_facts
→ Agent 使用只读文档上下文输出 schema 化候选事实
→ 校验/规范化/去重
→ 创建 CandidateFact(proposed) + ReviewTask
→ UI SSE 收到待确认通知
→ 用户批量确认/编辑/拒绝
→ ConfirmFacts Command
→ CandidateFact(confirmed) + Audit + Outbox
```

安全点：Agent 不直接写 confirmed；原始文件路径不进入 Prompt，只传经过允许的文本片段和 Document ID。

### 10.2 OpenCLI 岗位同步

```text
Schedule 或用户手动触发
→ Enqueue sync_connector(connector_id, idempotency_key)
→ 创建 SyncRun
→ 读取 Career Adapter Descriptor
→ OpenCliProcessRunner.health
→ auth status
→ opencli --profile <alias> boss search ... -f json
→ 捕获退出码/stdout/stderr
→ JSON Schema 校验
→ 为每条记录生成 SourceEvent
→ [短事务] 保存 SourceEvent + 推进 SyncCursor
→ enqueue process_job_source_event
→ 规范公司/岗位、去重并建立 JobPostVersion
→ enqueue analyze_job_fit
→ 完成 SyncRun 和统计
```

OpenCLI 调用规则：

- 使用 `asyncio.create_subprocess_exec` 参数数组。
- 禁止 `shell=True`。
- executable 由 setup/doctor 解析为绝对路径。
- 命令必须来自 Descriptor allowlist。
- P0 仅允许 read command。
- stdout 有最大字节限制，stderr 脱敏后保存摘要。
- 超时后先终止子进程，再按平台安全回收；不能杀死用户 Chrome。

### 10.3 登录失效

```text
OpenCLI exit=77 / AUTH_REQUIRED
→ SyncRun(authentication_required)
→ Connector status=requires_login
→ 本轮不推进游标
→ 创建用户通知
→ 用户点击“重新登录”
→ 后端生成一次性 login operation
→ foreground 调用 OpenCLI login
→ 用户在浏览器完成登录
→ status 校验成功
→ Connector=healthy
→ 用户手动重试或下个 Schedule 恢复
```

### 10.4 岗位归一化和版本化

```text
SourceEvent
→ 精确 source/external_id 查找
→ 若存在：比较 canonical content hash
   → 相同：只更新 last_seen_at
   → 不同：创建 JobPostVersion
→ 若不存在：公司/岗位/地点规则生成候选
   → 唯一高置信度：关联现有 JobPost
   → 多候选：ReviewTask(job_merge)
   → 无候选：新建 JobPost
```

跨来源模糊合并不得由 LLM 自动最终确认。

### 10.5 岗位匹配

```text
JobPostVersion + confirmed CandidateFacts + Preferences
→ 硬门槛规则检查
→ 提取/读取 JobRequirements
→ Agent 对每条 requirement 建立 Fact evidence 或 gap
→ schema 校验
→ 计算确定性分项/优先级
→ 保存 JobMatchAnalysis + Evidence
→ UI 展示“要求—证据—缺口—建议”
```

分数由确定性权重计算，Agent 只输出结构化维度判断和证据引用。硬性条件 veto 不能被总体分数稀释。

### 10.6 材料 Drafter–Reviewer

```text
用户启动材料生成
→ 锁定 JobPostVersion + CandidateFact revision set
→ 创建 Material Workflow Run
→ Drafter 只读事实和岗位，输出 Draft
→ 事实引用校验
→ Reviewer 获得 Draft + 独立最小上下文
→ 输出结构化 review findings
→ 确定性应用可机械修改项，其余进入修订
→ 导出 PDF/DOCX
→ 文本层/页数/渲染检查
→ 用户确认
→ ResumeVersion(final) + hashes
```

失败的事实引用、未解析的占位符、导出错误会阻止进入 final。

### 10.7 确认投递

```text
用户选择 Job + Final Materials
→ ConfirmSubmitted Command
→ 校验材料状态和事实快照
→ [transaction]
   创建/更新 Application
   创建 submitted ApplicationEvent
   保存 MaterialSnapshot
   更新 current_status
   写 Audit/Outbox
→ 创建默认跟进 Task
```

投递行为本身由用户在外部网站完成；系统只记录用户确认的结果。

### 10.8 IMAP 首次同步

```text
用户配置 account + SecretRef
→ 连接测试（TLS + readonly select）
→ 创建 initial_sync Job
→ 按日期搜索 UID
→ 分批读取 envelope/header
→ 本地规则过滤
→ 仅对候选邮件 BODY.PEEK
→ Parser 标准化
→ SourceEvent + Message minimal record
→ 分类/字段提取 Job
→ 申请匹配
→ EventProposal + ReviewTask
→ 完成一批后提交 cursor/checkpoint
```

首次同步批次建议 100 封 header、20 封正文；具体值可配置并通过性能测试调整。

### 10.9 IMAP 增量同步

```text
读取 UIDVALIDITY + last_committed_uid
→ readonly select
→ 校验 UIDVALIDITY
→ UID SEARCH last_uid+1:*
→ 分批 BODY.PEEK
→ 保存 SourceEvent/Message
→ 成功提交 last_committed_uid
```

Cursor 只能推进到连续成功处理的最大 UID。单封解析失败进入 quarantine，记录失败 UID；策略明确选择“阻塞游标后重试”或“保存原始事件后推进”，P0 推荐后者，因为原始事件已持久化，可离线重放。

### 10.10 邮件分类、申请匹配和事件确认

```text
Message
→ 本地规则分层
→ 候选招聘邮件进入 Agent 分类
→ 提取 category/company/job/time/reference
→ 精确匹配规则
→ Agent 仅对候选排序
→ 唯一高置信度或多候选均生成 Proposal
→ ReviewTask
→ 用户确认
→ ApplicationEvent + Reminder/Task
```

即使高置信度，P0 也不自动更新正式申请状态。

### 10.11 面试准备

```text
interview_invited Event confirmed
→ Outbox
→ 创建 Interview + Reminder
→ enqueue interview_prep
→ 加载岗位版本、实际投递材料、Fact、历史反馈
→ Agent 生成准备包和问题证据
→ 保存 Document + AgentRun
→ UI 展示准备任务
```

## 11. Agent Runtime 工程方案

### 11.1 Career Task Agent 入口

用户主要通过 Web 执行明确操作。AgentLoop 保留为核心编排器，并增加 task execution policy：后台任务输入输出固定 Schema、默认无工具、具有超时和幂等键，不以无限制自由对话方式运行。

未来如增加自然语言入口，它只负责解释和生成明确 Application Command，不形成第二套 Session/Memory/业务写入路径。

### 11.2 AgentTaskPort

```python
class AgentTaskPort(Protocol):
    async def run(
        self,
        task_type: str,
        input: BaseModel,
        policy: AgentExecutionPolicy,
    ) -> AgentTaskResult: ...
```

`AgentExecutionPolicy` 包含：

- model/provider policy。
- tool allowlist。
- timeout、max iterations、token budget。
- sensitive data classification。
- output schema version。
- prompt version。
- retry policy。

### 11.3 上下文最小化

每个 Task Handler 明确声明数据需求。例如邮件分类只获得：主题、发件域、候选正文片段和已有申请候选摘要，不获得完整简历、其他邮件或文件系统。

### 11.4 输出校验

执行顺序：

```text
LLM raw output
→ JSON/Pydantic parse
→ schema version check
→ domain validation
→ fact reference validation
→ confidence/evidence validation
→ accept / retry repair once / quarantine
```

不能使用 `json-repair` 后无校验直接写正式数据。

### 11.5 Prompt 和 Skill 版本

- Prompt、Skill、Schema 放在资源目录并有显式版本。
- `agent_runs` 记录版本和内容哈希。
- 变更 Prompt 必须跑固定 Fixture 回归集。
- 历史结果不因 Prompt 更新自动覆盖；需要显式 reprocess。

### 11.6 工具权限

Task Agent 默认没有：

- 通用 Exec。
- 任意文件读写。
- 任意 Web Fetch。
- SMTP 或消息发送。
- 数据库工具。

仅注册用例所需的只读查询和受控 Command Tool。

## 12. Connector 工程规范

### 12.1 统一契约

```python
class Connector(Protocol):
    connector_type: str
    version: str

    async def health(self, request: HealthRequest) -> ConnectorHealth: ...
    async def sync(self, request: SyncRequest) -> SyncBatch: ...
```

`SyncBatch` 包含：

- 标准化 `SourceEventInput`。
- 候选新 Cursor。
- 统计。
- 可重试/不可重试诊断。

Connector 不持有数据库事务，由 Runtime 分批提交。

### 12.2 Source Event Envelope

```json
{
  "schema_version": 1,
  "source_type": "email",
  "source_id": "uuid",
  "external_id": "message-or-job-id",
  "event_type": "content_received",
  "occurred_at": "2026-07-22T02:00:00Z",
  "collected_at": "2026-07-22T02:01:00Z",
  "content_type": "email",
  "payload": {},
  "raw_reference": {},
  "deduplication_key": "sha256:...",
  "connector_version": "imap/1"
}
```

### 12.3 错误分类

```text
configuration_error       不重试
authentication_required   等待用户
connection_error          指数退避
timeout                   指数退避
rate_limited              按 retry-after
schema_invalid            隔离数据，不写业务表
adapter_regression        标记 degraded
external_not_found        业务判断
unknown                   有限重试后失败
```

### 12.4 重试策略

- 网络/超时：1m、5m、15m、1h，带随机抖动。
- Auth/Config：不自动重试，配置或登录变化后重新入队。
- Schema invalid：不重试同一 payload；等待 Adapter/Parser 版本变化后重放。
- Rate limit：优先使用对方提供的 retry-after。
- LLM transient：最多 2 次；验证错误只允许一次受控修复。

## 13. OpenCLI 集成细节

### 13.1 Career Adapter Descriptor

Descriptor 定义业务统一接口到 OpenCLI 命令的映射：

```yaml
schema_version: 1
id: boss
display_name: BOSS直聘
adapter_version: "1.0.0"
access: read_only
opencli_site: boss
commands:
  status: [auth, status]
  login: [auth, login]
  latest: [search]
  detail: [detail]
output_schemas:
  latest: boss-latest-v1.json
  detail: boss-detail-v1.json
timeouts:
  status_seconds: 20
  latest_seconds: 90
  detail_seconds: 45
```

Descriptor 从项目资源加载；用户覆盖放在用户数据目录。解析后的最终 Descriptor 及哈希记录在 SyncRun。

### 13.2 命令安全

- `opencli_site`、command path、参数定义均来自已验证 Descriptor。
- 用户输入只作为单独 argv 值传递。
- 禁止 Descriptor 引用 BOSS 写命令。
- 可执行文件路径必须由 `doctor` 校验，不能从每次请求自由传入。
- 环境变量只传递最小集合。
- 子进程工作目录使用独立 runtime 临时目录。

### 13.3 Profile

- Connector 保存 OpenCLI Profile alias，不保存 Cookie。
- 一个 Profile 对应一个并发锁。
- Profile 不存在或未连接映射为明确健康状态。
- Web UI 展示 `connected/authenticated/requires_login`，不展示 Cookie 内容。

### 13.4 Adapter 更新

- 每次 SyncRun 保存 OpenCLI version、Descriptor version、实际命令来源和 Adapter version。
- 输出 Schema 失败时隔离原始 stdout 摘要和 trace reference。
- Demo 只提示更新/覆盖，不实现自动回滚。
- 用户 Adapter 遮蔽内置 Adapter 时在 Data Sources 页面明确告警。

## 14. IMAP Connector 细节

### 14.1 只读保证

代码层通过两道防线：

1. IMAP Client 包装器只暴露 `select_readonly`、`uid_search`、`uid_fetch_peek`、`status`。
2. Contract Test 使用 Fake IMAP Server 断言从未发出 STORE、COPY、MOVE、EXPUNGE、APPEND 或 SMTP。

不能直接把原始 `imaplib.IMAP4` 对象传给上层。

### 14.2 标准邮件模型

字段包括 account、folder、UID、UIDVALIDITY、Message-ID、thread key、from/to、subject、received time、body text、必要 HTML、附件元数据、header 子集、content hash。

附件 P0 只保存名称、MIME、大小和 part identifier，不自动下载正文。

### 14.3 解析器

纯函数解析层负责：

- Header 编码。
- multipart/alternative。
- text/plain 优先。
- HTML 安全转文本。
- 字符集降级。
- 回复链、签名和页脚分段。
- 日历邀请元数据。

解析器不调用模型、不写数据库，使用真实脱敏 `.eml` Fixture 回归。

### 14.4 UIDVALIDITY 恢复

UIDVALIDITY 变化时：

1. 将 Connector 状态设为 `reconciling`。
2. 选取可配置时间窗口重新检索 Header。
3. 使用 Message-ID、时间、发件人和 content hash 对账。
4. 只为未见消息创建 Source Event。
5. 用户数据量异常时暂停并提示，不无限全量扫描。

## 15. File Store

### 15.1 目录结构

使用 `platformdirs` 决定平台目录，概念结构：

```text
<data-root>/
├── database/career.db
├── blobs/sha256/ab/<hash>
├── exports/resumes/
├── recordings/
├── traces/
├── backups/
├── logs/
├── runtime/
└── adapters/overrides/
```

配置放在平台 config directory，不和数据、日志混放。

### 15.2 原子写入

```text
写临时文件
→ flush/fsync（对关键材料）
→ 计算并验证哈希
→ 同文件系统 atomic rename
→ 数据库提交引用
```

上传文件名不直接作为路径。路径由系统生成，原始文件名只作为元数据。

### 15.3 保留策略

- Final application snapshot 默认长期保留。
- 临时导出和中间草稿可配置清理。
- 无关邮件正文不落 Blob。
- Agent trace 默认保留有限天数并脱敏。
- 录音必须由用户主动开启/上传，并单独展示保留和删除控制。

## 16. Secret 和配置

### 16.1 配置分层

```text
代码默认值
→ 用户 config.json
→ 环境变量覆盖
→ CLI 一次性覆盖
```

普通配置只包含非敏感项和 `secret_ref`。Pydantic Settings 继续使用，但拆分为应用、模型、Connector、调度和隐私策略配置。

### 16.2 Secret Store

```python
class SecretStore(Protocol):
    def put(self, namespace: str, key: str, value: SecretStr) -> str: ...
    def get(self, secret_ref: str) -> SecretStr: ...
    def delete(self, secret_ref: str) -> None: ...
```

默认实现使用 OS Keyring。API：

- 写 Secret 只返回 reference 和 masked metadata。
- 读 API 永不返回明文。
- 更新采用覆盖写，日志不记录请求体。
- 导出配置不包含 Secret。

## 17. API 规范

### 17.1 基本约定

- Base path：`/api/v1`。
- JSON 使用 snake_case 或 camelCase 必须统一；推荐 API camelCase、Python 内部 snake_case，由 Pydantic alias 处理。
- 所有写操作接收 `Idempotency-Key`。
- 所有聚合更新携带 `expectedVersion`。
- 时间为 RFC 3339 UTC，UI 本地化。
- 列表使用 cursor pagination，不用无上限数组。
- 错误遵循 RFC 9457 Problem Details。

### 17.2 错误示例

```json
{
  "type": "https://CareerConsole.local/problems/version-conflict",
  "title": "Version conflict",
  "status": 409,
  "code": "APPLICATION_VERSION_CONFLICT",
  "detail": "The application changed after it was loaded.",
  "instance": "/api/v1/applications/...",
  "correlationId": "..."
}
```

### 17.3 路由组

```text
/api/v1/profile
/api/v1/facts
/api/v1/documents
/api/v1/resumes
/api/v1/jobs
/api/v1/job-analyses
/api/v1/applications
/api/v1/application-events
/api/v1/messages
/api/v1/interviews
/api/v1/tasks
/api/v1/reminders
/api/v1/review-tasks
/api/v1/connectors
/api/v1/sync-runs
/api/v1/agent-runs
/api/v1/background-jobs
/api/v1/dashboard
/api/v1/events/stream
```

### 17.4 SSE

SSE 事件只发送轻量通知：

- entity changed。
- job progress。
- review task created。
- connector health changed。
- notification created。

前端收到事件后通过 TanStack Query invalidate/refetch 获取权威状态，不在 SSE 中传完整敏感实体。

## 18. 本地 Web 安全

### 18.1 网络边界

- 默认只监听 `127.0.0.1`。
- 不允许配置成 `0.0.0.0`，除非用户显式启用高级模式并确认风险。
- 严格 CORS，只允许本服务 origin。
- 设置 CSP、X-Content-Type-Options、Referrer-Policy。

### 18.2 本地认证

即使是 localhost，也需要防止恶意网页调用本地 API：

1. 首次启动生成高熵 local access token，保存为权限受限文件。
2. CLI 打开浏览器时使用一次性 bootstrap token。
3. 后端交换为 HttpOnly、SameSite=Strict session cookie。
4. 所有写请求验证 CSRF token 和 Origin。
5. bootstrap token 使用后立即失效，不留在浏览器历史。

### 18.3 上传和渲染

- 限制文件大小、类型和扩展名。
- 不执行 Office/PDF 中的宏、脚本或嵌入内容。
- HTML 邮件以纯文本或严格 sanitize 后展示。
- 外部链接明确标记并使用安全打开方式。
- 前端不使用未经 sanitize 的 `dangerouslySetInnerHTML`。

## 19. 可观测性

### 19.1 关联 ID

每个 HTTP request、Command、Job、SyncRun、AgentRun 都有 ID，并在日志上下文中传递：

```text
correlation_id
request_id
job_id
sync_run_id
agent_run_id
connector_id
```

### 19.2 日志

- 开发环境人类可读，生产本地日志可选择 JSON Lines。
- 按大小和日期滚动，限制保留量。
- 中间件统一脱敏 email、token、password、cookie、authorization、正文和文件路径。
- 用户界面只展示稳定错误码和脱敏摘要，详细 trace 需用户主动打开。

### 19.3 健康检查

- `/health/live`：进程存活。
- `/health/ready`：数据库 revision、关键目录和主循环可用。
- Data Sources 页面单独展示每个 Connector health，不让一个来源影响全局 readiness。

### 19.4 指标

本地记录有限指标，不需要 Prometheus 服务：

- Job 延迟/失败率。
- Sync 新增/更新/重复数。
- Agent 耗时、token、验证失败。
- DB busy/slow query。
- Review Task 积压。

## 20. 测试策略

### 20.1 测试金字塔

| 层级 | 内容 | 目标 |
|---|---|---|
| Domain Unit | 状态机、事实、去重、时间、策略 | 快速、无 IO |
| Application Unit | Command/Query Handler、Port mock | 验证编排和事务 |
| Repository Integration | SQLite 真库、迁移、约束 | 验证持久化 |
| Connector Contract | Fake IMAP、Fake Process Runner、Fixture | 验证协议和幂等 |
| Agent Contract | 固定输入输出、Schema、事实引用 | 防 Prompt 回归 |
| API Integration | FastAPI test client + 真 DB | 验证契约和错误 |
| Frontend Component | 表单、看板、Review 行为 | 验证交互 |
| E2E | 安装后的关键 Demo 闭环 | 发布门禁 |

### 20.2 必测不变量

- 未确认 Fact 不能进入 Final Material。
- Connector 不能直接更新 Application status。
- Email Connector 不发出任何修改邮箱状态命令。
- 重复 SourceEvent 不产生重复业务实体。
- Job 重试不重复创建事件。
- Final Material Snapshot 不受后续 Resume 修改影响。
- Offer 邮件不能自动产生 accepted/hired。
- 状态机拒绝非法转换并保留当前状态。
- 所有时间必须含时区。

### 20.3 Fixture

- 脱敏真实 `.eml` 样本。
- OpenCLI stdout/error/exit code 样本。
- 多版本岗位 JSON。
- 简历 PDF/DOCX/Markdown 样本。
- Prompt injection 岗位和邮件样本。
- 中文、英文、混合编码和不同时区样本。

### 20.4 质量门禁

PR 必须通过：

- Ruff format/lint。
- 类型检查，推荐 Pyright strict 逐模块启用。
- Pytest。
- Alembic upgrade from empty 和 from previous release。
- 前端 ESLint、TypeScript、Vitest。
- OpenAPI breaking-change 检查。
- `git diff --check`。
- Secret scan 和依赖漏洞扫描。

覆盖率建议：Domain 核心模块不低于 90%，项目总体不低于 75%。覆盖率不是唯一质量指标，状态机和幂等场景必须按行为枚举。

### 20.5 CI 平台

- Windows latest：主平台。
- Ubuntu latest：可移植性和路径/编码验证。
- Python 3.11、3.12。
- Node.js 20 LTS 及项目选定前端版本。

涉及真实邮箱、浏览器和模型的测试不进入普通 PR；使用 nightly/manual E2E，并严格隔离测试账号和 Secret。

## 21. 开发规范

### 21.1 类型和 Schema

- 公共函数和 Port 完整类型标注。
- DTO 使用 Pydantic，Domain 使用 dataclass/value object。
- 外部 JSON 一律先校验后使用。
- Enum 值一旦发布不得直接重命名，需迁移。

### 21.2 异常

- Domain 抛稳定领域异常。
- Infrastructure 将底层异常映射为 Port 异常。
- API 统一映射 Problem Details。
- 不向前端返回堆栈、SQL、Secret 或外部完整响应。
- 不使用裸 `except Exception: pass` 吞掉关键错误。

### 21.3 数据库迁移

- migration 文件不可在合并后修改，只追加。
- migration 必须能从上一发布版真实数据库升级。
- 破坏性迁移分 expand/migrate/contract 多阶段。
- 迁移前备份，迁移失败恢复原库并停止 readiness。

### 21.4 ADR

以下决策应创建 Architecture Decision Record：

- ADR-001 模块化单体。
- ADR-002 SQLite + SQLAlchemy + Alembic。
- ADR-003 持久化 Job/Outbox。
- ADR-004 Agent 与 Domain 边界。
- ADR-005 OpenCLI 受控子进程。
- ADR-006 独立只读 IMAP Connector。
- ADR-007 React/FastAPI 本地 Web。
- ADR-008 OS Keyring Secret Store。

## 22. CLI 和运维命令

推荐统一产品命令：

```text
CareerConsole setup
CareerConsole serve
CareerConsole doctor
CareerConsole status
CareerConsole db migrate
CareerConsole db backup
CareerConsole db restore <backup>
CareerConsole connectors list
CareerConsole connectors health <id>
CareerConsole connectors sync <id>
CareerConsole jobs list
CareerConsole jobs retry <id>
CareerConsole export
CareerConsole delete-all-data
```

`doctor` 检查：

- Python 和数据目录权限。
- DB revision/完整性。
- Node.js 20+。
- OpenCLI executable/version。
- Browser Bridge daemon/Profile。
- Web 端口。
- OS Keyring。
- PDF/DOCX 可选工具。

诊断输出不得显示 Secret、Cookie 或完整邮箱地址。

## 23. 安装、打包和升级

### 23.1 开发环境

遵循项目规则：存在 `.venv` 时全部使用 `.venv\Scripts\python.exe`。首次开发初始化创建 `.venv`，前端依赖位于 `web/node_modules`。

### 23.2 发布物

P0 可以发布 Python wheel：

- 包含预构建 `web/dist`。
- 包含 Alembic migrations、Schema、Descriptor、Prompt 和模板。
- OpenCLI 不打包进 Python wheel；setup/doctor 检测并提示安装。

后续可提供 Windows installer，但不把 installer 作为首个业务里程碑。

### 23.3 升级流程

```text
停止接受新任务
→ 等待/释放 lease
→ 备份数据库和配置
→ 安装新版本
→ 运行 migration
→ 校验资源/Descriptor
→ 启动并执行 readiness
→ 失败则恢复旧版本和备份
```

用户文件、Secret、Browser Profile 和自定义 Adapter 位于代码安装目录之外，升级不得覆盖。

## 24. 现有代码处置与演进策略

### 24.1 处置标准

每个现有模块按以下维度评估：

- 是否影响 Career Domain 的确定性和依赖方向。
- 是否扩大隐私或执行权限风险。
- 是否阻碍 Web、Job、Connector 或 Task Agent 的实现。
- 当前稳定性和测试覆盖。
- 后续扩展价值。
- 保留带来的依赖、安装和维护成本。

处置结果为：

```text
keep：保持现状，仅补必要测试
extend：保留主体，增加清晰接口或策略
refactor/rewrite：确实妨碍产品正确性时修改实现
isolate/disable：P0 不使用但有潜在扩展价值
replace：业务模型错误，由新模块接管后退出
delete：确认冗余、无价值或持续产生负担
```

默认不是“全部保留”，也不是“全部重写”。任何重写或删除都需要说明具体影响和收益。

### 24.2 旧模块处置矩阵

| 旧模块 | 处置 | 目标 |
|---|---|---|
| Provider registry/实现 | keep/extend | 支持多模型；增加统一错误和隐私策略 |
| AgentRunner 工具迭代 | extend | 增加 Task Agent 所需 Schema、预算和 allowlist |
| AgentLoop | keep/refactor | 统一支持 interactive/task execution policy，不承担业务状态 |
| ContextBuilder/Memory | rewrite/replace | 使用 ContextManifest、Evidence/Fact/Event/Insight/Strategy 业务知识系统 |
| Tool base/registry | keep/extend | 保留工具能力，按 execution policy 控制 allowlist 和风险 |
| SessionManager | keep/refactor | 只服务短期交互；业务使用 Domain Event/AgentRun |
| MessageBus | keep + boundary | 服务运行时消息，不替代 Domain Event/Outbox |
| CronService | keep/refactor | 与数据库 Schedule 合并为统一调度引擎 |
| ConfirmManager | replace | 统一使用持久化 ReviewTask |
| CareerStore/ResumeService | replace | 新 Domain 接管后再删除粗糙实现 |
| career_resume Tool | replace | 改为用例级 Career Tool，旧 Tool 在切换后删除 |
| Email Channel | refactor/split | 入站严格只读 IMAP；出站作为通知适配器 |
| Chat Channels | keep/refactor | 以发送提醒为主，未来支持安全回执 |
| aiohttp API | replace/delete | FastAPI 是唯一产品 API |
| Exec Tool | keep with policy | 保留未来能力；不默认开放给不可信后台任务，Connector 使用固定 Runner |
| SubagentManager | keep/evaluate | 暂不删除，只有具体 Workflow 才启用 |
| MCP | keep/evaluate | 暂不删除，按具体 Connector/Tool 需求启用 |
| 通用 Skills/Templates | keep/refactor | 正式任务另用版本化 Career Task Prompt/Schema |

### 24.3 演进步骤

1. 冻结旧 Career MVP 的功能扩展，只处理安全和阻塞问题。
2. 在 `career_console` 中建立 Domain/Application/Infrastructure 新边界。
3. 保留并重构 Provider、Runner、AgentLoop、Cron、Channels、Tools 等基础能力，Career Domain 只通过 Port 使用。
4. 新 Career API/Web 成为主产品入口；AgentLoop 继续作为受 execution policy 管理的 Agent 核心。
5. 以 Career 回归测试保证业务正确性，同时保留经过明确评估的通用基础能力。
6. 旧 Career Store、Resume Service 和重复 Career Tool 不做数据迁移，清除引用和旧测试后直接删除。

### 24.4 旧 Career 数据处置

旧 Career Store 属于早期粗糙实现，本项目不保留其数据，也不开发迁移命令。新 Domain/Application/Repository 路径覆盖启动和测试引用后，直接删除旧数据库逻辑、Resume Service、旧 Tool 及对应兼容测试。删除前只需确认目标文件和运行引用，不需要转换旧 `career.db`。

## 25. 分阶段落地计划

### Milestone 0：工程基线

交付：

- 创建 `.venv` 和锁定依赖。
- 现有测试基线。
- 新模块目录、依赖规则、ADR。
- 现有模块影响评估、依赖边界检查和处置记录。
- FastAPI skeleton、配置、数据目录和 health。
- SQLAlchemy/Alembic、Unit of Work、测试数据库。
- CI Windows/Linux。

退出标准：空库可迁移到 head，服务可启动，架构边界测试通过。

### Milestone 1：确定性 Career Core

交付：

- CandidateFact、Document、JobPost/Version。
- Application/Event 状态机。
- ReviewTask。
- Repository、Command/Query Handler、Audit/Outbox。
- 如盘点确认存在真实旧数据，提供一次性导入器；否则不实现。

退出标准：不使用 Agent 也能完成手工“事实—岗位—申请—事件—确认”闭环。

### Milestone 2：Agent 材料闭环

交付：

- AgentTaskPort。
- Fact/Requirement extraction。
- Job Fit。
- Drafter–Reviewer。
- Material Version/Snapshot。
- 输出验证基础。

退出标准：生成材料中的每条事实可追溯，用户确认投递后快照不可变。

### Milestone 3：Job/Outbox/Scheduler

交付：

- background_jobs、lease、retry。
- schedules。
- transactional outbox。
- SSE 进度。
- 崩溃恢复和幂等测试。

退出标准：任务执行中强制结束进程后，重启可恢复且不重复业务结果。

### Milestone 4：IMAP Connector

交付：

- OS Keyring。
- 只读 IMAP client。
- 初次/增量同步、UIDVALIDITY。
- 邮件解析/过滤/分类/申请匹配。
- Event Proposal/Review/Reminder。

退出标准：协议测试证明不修改邮箱；重启后游标正确；事件必须确认。

### Milestone 5：OpenCLI Connector

交付：

- Process Runner。
- Descriptor/Schema。
- Profile/Login/health。
- BOSS latest/detail。
- 岗位去重/版本、每天两次 Schedule。

退出标准：重复扫描幂等；登录失效局部隔离；写命令无法从 Connector 执行。

### Milestone 6：完整本地 Web Demo

交付：

- Dashboard、Profile、Job Pool、Application Board。
- Review Center、Materials、Data Sources、Interview Center。
- 本地安全、备份、导出和诊断。

退出标准：用户无需直接编辑数据库、JSON 或 Markdown 即可完成 Demo 闭环。

## 26. 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| SQLite 并发写竞争 | 短事务、WAL、busy timeout、Worker 限流、乐观锁 |
| 后台任务重复执行 | Job idempotency key、唯一约束、状态 guard |
| OpenCLI/网站变化 | Descriptor/Schema、错误码映射、SyncRun、Adapter health、隔离坏数据 |
| 邮件隐私泄漏 | Header-first、本地过滤、最小正文、模型上下文策略、脱敏日志 |
| Prompt injection | 外部内容标记、工具 allowlist、无通用 Exec/文件工具、输出校验 |
| Agent 幻觉 | Fact ID 引用、Domain 校验、ReviewTask、不可直接 confirmed |
| 通用框架语义污染 Career 边界 | Port/Adapter、import 边界测试、后台任务不走聊天消息总线 |
| 确有旧数据需要保留 | 先盘点；仅提供只读、幂等、一次性离线导入器 |
| Windows 环境差异 | `create_subprocess_exec`、绝对路径 doctor、CI Windows 主门禁 |
| Secret 无安全后端 | fail closed，明确提示；不自动降级为明文 |
| 单进程崩溃 | 持久 Job/Outbox/lease、原子文件、启动恢复 |

## 27. 需要评审确认的技术决策

以下决策已经在本方案中给出推荐值，架构评审只需接受或提出替代，不应继续无限开放：

1. 接受模块化单体，而非微服务。
2. 接受 FastAPI 作为 Career 主 Server；旧 aiohttp Chat API 按影响评估，可隔离保留或在无价值时删除。
3. 接受 React/TypeScript 独立前端。
4. 接受 SQLAlchemy 2.0 + Alembic + SQLite WAL。
5. 接受数据库 Job Queue/Outbox，不引入 Celery/Redis。
6. 接受 OpenCLI 受控子进程，不通过通用 Exec Tool 正式同步。
7. 接受新建只读 IMAP Connector，不复用现有 Email Channel。
8. 接受 OS Keyring fail-closed Secret 策略。
9. 接受 `~/.CareerConsole` 的概念数据根目录，实际路径由 `platformdirs` 决定。
10. 接受牛客校招日程作为默认每日信息来源，BOSS 保留为可选定向岗位来源；自动日程严格限制为中国时间当天，7/14/30 天回填只能由用户触发。
11. 接受现有代码按 keep/extend/refactor/isolate/replace/delete 评估，不进行无收益的整体重写或批量删除。

简历导出格式建议 P0 先保证 PDF，并把 DOCX 作为 P1；面试录音 P0 只支持手动文本反馈，录音上传/转写进入 P1。这样可以控制首版依赖和合规范围。

## 28. 首个实施切片

第一个开发切片应控制在一个可审查的垂直范围：

```text
现有 CareerConsole Runtime
+ Career Settings/Data Paths
+ SQLAlchemy/Alembic
+ Unit of Work
+ CandidateFact
+ JobPost/Version
+ Application/Event
+ ReviewTask
+ FastAPI Career Command/API
+ Domain/API/Repository tests
```

该切片明确不包含 OpenCLI、IMAP、前端复杂页面或 LLM。它在不重写现有 Agent Runtime 的前提下证明最关键的业务边界和数据一致性成立，并为所有后续外部集成提供统一落点。

完成后再依次接入 Agent Task、持久任务、IMAP 和 OpenCLI，避免任何 Connector 先行形成临时数据库和第二套业务规则。

## 29. 方案验收检查表

进入开发前：

- [ ] 模块化单体和依赖方向已确认。
- [ ] 技术选型和新增依赖已确认。
- [ ] 数据目录、Secret Store 和备份策略已确认。
- [ ] 核心表、状态机和事件类型已评审。
- [ ] Job/Outbox/幂等语义已评审。
- [ ] Agent Tool allowlist 和上下文策略已评审。
- [ ] OpenCLI 与 IMAP 安全边界已评审。
- [ ] P0 范围和退出标准已确认。

每个 Milestone：

- [ ] 有明确迁移和回滚方式。
- [ ] 有单元、集成和契约测试。
- [ ] 不在事务内执行外部 IO。
- [ ] 不泄露 Secret 和敏感正文。
- [ ] 重试不产生重复业务结果。
- [ ] 重要状态变化可追溯。
- [ ] Windows 和 Linux CI 通过。
- [ ] 文档、OpenAPI 和 ADR 同步更新。

## 30. 总结

本方案把 CareerConsole 的 Agent 能力降到正确的位置：它是受控推理引擎，不是业务数据库和状态机。Career Domain 成为系统事实源，Application Service 负责用例编排，Connector 只采集外部事件，Review Task 承接所有需要用户裁决的变化。

模块化单体、SQLite、持久 Job/Outbox 和受控外部进程能够在不增加本地部署负担的前提下提供工业级的事务、幂等、恢复和审计能力。等产品真实规模证明需要独立 Worker 或 PostgreSQL 时，现有 Port、Job 和 Repository 边界允许演进；在此之前不提前承担分布式系统复杂度。
