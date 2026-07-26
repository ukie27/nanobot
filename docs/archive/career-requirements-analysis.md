# Nanobot Career 三项目需求与架构分析报告

> 分析对象：`nanobot-career`、`ai-job-search`、`OpenCLI`  
> 分析日期：2026-07-22  
> 当前阶段：需求分析与目标架构确认，不包含大规模业务代码改造

## 1. 执行摘要

本项目的目标不是继续扩展一个“会处理求职问题的通用聊天 Agent”，而是构建一个本地优先、持续运行、面向个人完整求职周期的求职操作系统。系统需要长期维护用户事实、招聘岗位、申请记录、材料版本、邮件事件、时间安排、面试反馈和策略变化，并通过本地 Web 页面让用户管理这些内容。

三个项目应承担不同角色：

| 项目 | 角色 | 结论 |
|---|---|---|
| `nanobot-career` | Agent 框架和工程基础 | 保留不影响产品边界且具有扩展价值的能力；冲突部分修改或重构；当前粗糙 Career MVP 等确有问题的实现可替换或删除 |
| `ai-job-search` | 产品工作流和质量规范参考 | 吸收事实单一来源、Drafter–Reviewer、申请快照、PDF/ATS 验证、面试闭环；不复制其以 Markdown/CSV/Prompt 代替业务域的实现 |
| `OpenCLI` | 登录态招聘网站访问基础设施 | 通过受控子进程调用其稳定 CLI、Browser Bridge、Profile 和 Adapter；不让它承担岗位去重、匹配、申请状态或数据持久化 |

推荐目标架构为：

```text
Local Web UI
    ↓
Career API / Application Layer
    ↓
Career Domain（确定性业务核心）
    ↓                         ↘
Repositories / Scheduler       Agent Runtime
    ↑                         ↙
Connectors → Source Event → Review Task
```

最关键的设计原则是：

1. Domain 不依赖 Agent；Agent 只能通过结构化业务工具访问 Domain。
2. Connector 不直接修改岗位或申请状态，只产生可追溯、可幂等的 `SourceEvent`。
3. 外部信息先形成候选判断，关键变化通过 `ReviewTask` 由用户确认。
4. 用户事实、状态、时间、版本、关联和审计由确定性代码管理。
5. Agent 负责非结构化理解、提取、匹配、生成、审查和规划，不负责最终事实裁决。
6. 所有敏感数据默认本地保存，发送给模型前执行分级过滤和数据最小化。

已确认的重构前提：产品目标高于对现有实现的机械兼容，但这不意味着重写整个 nanobot。后续按影响评估代码去留：不影响 Career Domain、仍有扩展价值且维护成本可控的框架能力保持不动；妨碍业务边界、安全或可靠性的部分进行修改或重构；完全无用、重复且持续增加维护成本的部分才删除。当前粗糙 Career MVP 不作为新业务模型的基础，但 Agent Runtime、Channel、MCP、Session 等通用能力只要不干扰产品路径，可以隔离保留。

第一版 Demo 应优先完成一个可验证闭环：导入简历建立事实库 → 采集或导入岗位 → 岗位匹配 → 生成并审查材料 → 用户确认投递 → 只读 IMAP 同步 → 申请事件候选与提醒 → 面试准备和复盘 → 本地 Web 时间线展示。

## 2. 分析范围和证据

本报告以实际代码为依据，不把需求文档中的设想当作已经实现的功能。

已检查的主要内容包括：

- `nanobot-career`：README、项目配置、CLI、Agent Loop、Agent Runner、Tool Registry、Skill、Career Store、Resume Service、Cron、Email Channel、配置、Session、Memory、HTTP API、安全模块和相关测试。
- `ai-job-search`：README、CLAUDE.md、AGENTS.md、`.claude/commands/`、`.claude/skills/`、`.agents/skills/`、岗位抓取状态、申请归档约定、材料模板、PDF 验证工具和测试。
- `OpenCLI`：README、CLI 入口、Adapter discovery/registry、Browser Bridge、daemon、Profile、session lease、错误类型、输出格式、BOSS Adapter、Adapter Author Skill 和测试结构。

当前 `nanobot-career` 没有 `.venv`，系统也没有可用的 `python` 或 Windows `py` 启动器，因此本轮无法执行 Python 测试。报告中的代码判断来自静态代码和测试用例阅读；正式开发开始前必须补齐本地 Python 环境并建立可重复测试基线。

## 3. 产品定位

### 3.1 产品是什么

产品是一个运行在用户个人电脑上的求职信息和行动管理系统，包含受控 Agent 能力、定时任务和多种数据 Connector。它长期维护同一个用户的完整求职上下文，并把外部招聘信息、材料、申请进度和面试反馈组织成可查询、可追溯的业务数据。

核心价值包括：

- 用统一事实库避免多版材料之间的虚构和矛盾。
- 自动发现并整理分散的岗位信息。
- 记录每次申请使用的材料和完整事件时间线。
- 从招聘邮件中提取进度和时间，但不擅自修改最终状态。
- 把历史面试反馈转化为下一次准备和长期能力改进建议。
- 让用户在本地 Web 页面而非散落的聊天记录中管理求职过程。

### 3.2 产品不是什么

- 不是通用聊天机器人。
- 不是企业 ATS 或招聘方协作系统。
- 不是多人、多租户 SaaS。
- 不是全网招聘聚合爬虫。
- 不是自动批量投递或自动联系招聘方的机器人。
- 不是依赖大模型记忆来维护关键业务状态的系统。
- 不是把用户全部邮箱、录音和文件无差别发送给云端模型的系统。

### 3.3 第一阶段用户

- 校招、春招、秋招和应届求职者。
- 同期申请大量公司、容易遗漏流程节点的用户。
- 需要管理多个测评、笔试和面试安排的用户。
- 重视隐私、希望敏感数据留在本地的用户。
- 希望用 AI 提升材料针对性和面试表现，但不接受虚构经历的用户。

## 4. 核心产品原则和业务不变量

以下规则应作为 Domain、API、Connector 和 Agent Tool 的共同约束，而不应只写在 Prompt 中。

### 4.1 用户事实不可虚构

- 简历、求职信、自我介绍和面试回答只能引用已确认事实。
- Agent 提取出的新事实默认是 `proposed`，用户确认后才成为 `confirmed`。
- 每条事实必须保存来源、提取方式、确认状态和版本。
- 修改已确认事实必须产生审计记录，不允许静默覆盖。

### 4.2 申请状态由事件推导

- `Application.current_status` 是便于查询的投影，不是唯一历史。
- 所有状态变化必须对应一条 `ApplicationEvent`。
- 外部邮件或网页不能直接创建最终事件，只能先创建事件候选。
- 状态转换需要经过状态机验证；冲突、回退和更正必须显式记录。

### 4.3 材料按申请保存不可变快照

- 基础简历、工作草稿、确认版本和实际投递版本需要区分。
- 投递时保存实际材料快照及内容哈希，之后的模板或基础简历更新不能改变历史申请。
- Reviewer 结果、用户确认、导出文件和验证结果均与同一材料版本关联。

### 4.4 外部输入不可信

- 邮件正文、网页、附件、岗位描述和用户导入文件都可能包含提示注入内容。
- Connector 只进行采集和标准化，不执行外部内容中的命令。
- Agent 处理外部内容时只能使用专用低权限工具，不能因此读取其他本地文件、修改配置或上传隐私数据。

### 4.5 关键操作可追溯且可更正

至少保存：发生时间、记录时间、来源、原始证据引用、前后值、置信度、执行者、是否用户确认、Agent Run 和 Connector 版本。

### 4.6 单个子系统失败不能拖垮全局

一个邮箱、一个招聘网站、一个 Adapter 或一次模型调用失败，不应停止其他数据源、Web 页面、材料管理或提醒服务。

## 5. 核心用户场景

### 5.1 首次建立资料

用户导入 PDF、DOCX、Markdown、文本简历或粘贴内容。系统解析为事实候选，标明来源和不确定项，用户批量确认后形成事实库。用户随后补充目标岗位、城市、时间范围、偏好和排斥条件。

### 5.2 发现和评估新岗位

定时任务调用招聘网站 Connector。Connector 通过 OpenCLI Adapter 获取岗位，保存原始来源和版本，Domain 完成去重和归一化，Agent 根据岗位要求和用户事实产生有证据的匹配分析。高价值岗位进入用户待办，而不是直接申请。

### 5.3 生成定制材料

用户选择岗位后，系统锁定岗位版本和事实快照。Drafter 生成材料草稿，Reviewer 独立审查事实一致性、岗位覆盖、表达和风险，系统执行格式与 ATS 验证，用户确认后保存最终版本。

### 5.4 用户完成投递

系统不自动代投。用户确认完成投递后创建 `Application` 和 `submitted` 事件，并把实际简历、求职信、岗位原文和投递时间绑定为快照。

### 5.5 收到招聘邮件

只读 IMAP Connector 增量读取新邮件，先做规则过滤，只对可能相关邮件进行分类和字段提取。系统匹配已有申请，形成状态事件候选、时间候选和提醒候选。用户确认后才更新申请时间线。

### 5.6 面试准备和复盘

识别面试安排后，系统结合岗位版本、实际投递材料、面试轮次、用户事实和历史弱点生成准备包。面试后用户手动填写记录或上传录音，系统提取问题、回答和改进项，并将确认后的结论沉淀到面试记录和长期弱点库。

## 6. 核心业务闭环

```text
资料导入
  → 事实候选
  → 用户确认
  → Candidate Fact
        ↓
Connector 同步 → Source Event → 去重/归一化 → Job Post / Message
                                                ↓
                                      匹配分析与优先级
                                                ↓
                                      材料生成与 Reviewer
                                                ↓
                                          用户确认投递
                                                ↓
                                      Application + 快照
                                                ↓
IMAP 增量同步 → 邮件分类 → 申请匹配 → Event Proposal
                                                ↓
                                           Review Task
                                                ↓
                                    Application Event + Reminder
                                                ↓
                                     面试准备 → 反馈 → 复盘
                                                ↓
                                  事实、弱点和求职策略持续更新
```

该闭环中有三类不同信息，必须分开建模：

1. **事实**：用户已确认的真实经历和偏好。
2. **外部证据**：网页、岗位、邮件、文件、录音及其原始引用。
3. **推断与建议**：匹配分析、分类结果、材料草稿和策略建议。

推断不能覆盖事实，外部证据不能直接改变业务状态。

## 7. `nanobot-career` 当前架构分析

### 7.1 当前核心调用链

```text
CLI / Channel / OpenAI-compatible API
                ↓
             MessageBus
                ↓
             AgentLoop
      ┌─────────┼──────────┐
 ContextBuilder AgentRunner SessionManager
                  ↓
             ToolRegistry
      ┌──────────┼───────────────┐
 Filesystem / Exec / Web / MCP / Cron / CareerResume
```

主要特点：

- `AgentLoop` 负责接收消息、构造上下文、驱动模型、执行工具和保存会话。
- `AgentRunner` 已有结构化工具调用、并发分批、结果预算和生命周期 Hook。
- `Tool` 基类提供 JSON Schema、参数校验、只读/独占属性。
- `SessionManager` 使用 JSONL 保存聊天会话和运行时 checkpoint。
- `CronService` 使用工作区 JSON 文件保存 `at`、`every` 和 cron expression 三类任务。
- HTTP API 只有 `/v1/chat/completions`、`/v1/models` 和 `/health`，没有 Career 业务 API。
- 当前产品仍在 README、包元数据、CLI 和大多数模块中定位为通用个人 AI assistant。

### 7.2 当前求职改造

已经实现：

- `candidate_profile` 单例表。
- `resumes` 表及父版本引用、默认版本。
- 粘贴文本和 `.txt`、`.md` 文件导入。
- 简历内容复制到工作区目录。
- `ResumeService` 的导入与保存版本操作。
- `career_resume` Tool。
- `resume-assistant` Skill，包含不虚构事实和用户确认后保存版本的规则。
- `boss-job-assistant` Skill，通过通用 Exec Tool 临时调用 OpenCLI BOSS 和小红书命令。
- 少量 Career Store 和 Career Tool 测试。

尚未实现：

- 独立 Candidate Fact、事实来源、确认状态和变更历史。
- Company、Job Post、岗位版本、岗位要求、岗位去重。
- Application、Application Event 和状态机。
- Source、Connector、Source Event、Sync Cursor、Sync Run。
- Message、邮件分类、申请匹配、Review Task。
- Reminder、业务 Task、Interview 和 Agent Run 审计。
- Career Web API 和本地管理页面。

当前模型的主要问题：

- `candidate_profile` 把技能、项目、实习等列表压成文本字段，无法逐条确认、引用和查询。
- `source_resume_id` 只能表达整份简历来源，不能表达每条事实的多个来源。
- 时间使用本地 `datetime.now().isoformat()`，没有明确时区。
- SQLite 连接没有统一 Repository、事务边界、WAL、foreign key pragma 或并发策略。
- 迁移只有在 Store 内执行 `CREATE TABLE IF NOT EXISTS` 的初始版本，不足以支持长期模式演进。
- 数据默认位于 Agent workspace 下，与“用户数据独立于代码仓库”的产品要求不完全一致。
- 当前 Career Tool 同时承担 API、校验和序列化职责，后续不宜继续堆叠所有求职操作。

### 7.3 Email Channel 评估

当前 `EmailChannel` 是通信 Channel，不是业务 Connector：

- 通过 IMAP 搜索 `UNSEEN` 邮件。
- 使用 `BODY.PEEK[]` 获取正文。
- 默认 `mark_seen=true`，随后通过 `STORE +FLAGS \\Seen` 修改邮件状态。
- UID 只保存在进程内存集合，重启后丢失。
- 没有保存 UIDVALIDITY、文件夹游标、Sync Run 或 Message-ID 幂等记录。
- 同时要求 SMTP 配置并支持自动回复。
- 用户名、IMAP/SMTP 密码是普通配置字符串，配置默认写入 `~/.career_console/runtime/config.json`。
- 已有 multipart、字符集、HTML 转文本、SPF/DKIM header 检查等可借鉴解析逻辑。

结论：**不能直接复用为求职邮箱同步模块**。应新建严格只读的 Email Connector，只复用经过拆分和测试的纯邮件解析函数。原 Email Channel 在产品收敛阶段应默认禁用或删除。

### 7.4 Cron 评估

当前 Cron 支持：

- 固定时间 `at`。
- 固定间隔 `every`。
- cron expression 和时区。
- 任务持久化、启停、手动执行、最近运行历史和错误。

不足：

- 任务 payload 只有 `agent_turn`，所有任务最终向 Agent 发送一段消息。
- 没有确定性业务 Job Handler、分布式/进程锁、幂等键或错过执行后的补偿策略。
- Job 状态存 JSON，不能与 Connector Sync Run、业务事务和 Web 状态统一查询。

结论：保留时间计算和单机调度思路，但增加确定性 Job 类型，例如 `sync_connector`、`dispatch_reminder`、`generate_digest`。Connector 定时同步不应先让 LLM 决定是否执行。

### 7.5 配置、安全和 API 评估

- Pydantic 配置结构清晰，支持环境变量嵌套覆盖，可以复用。
- 普通 JSON 配置会包含 API key、邮箱密码等敏感字符串，不能满足目标凭证安全要求。
- Exec Tool 已有确认和路径/网络保护，但它仍是通用 Shell，不能成为自动 Connector 的稳定业务接口。
- SSRF 防护和工具确认框架可复用，但需要补充外部内容提示注入隔离、日志脱敏和 localhost Web 鉴权。
- 当前 HTTP API 只是 Agent Chat API，不适合作为页面的 Career CRUD、查询、同步状态和 Review Task API；需要新增独立路由和 Application Service。

### 7.6 nanobot 模块处置建议

处置必须基于实际影响，不为“架构纯洁”制造没有业务收益的重写。保留的通用能力应与 Career 业务隔离，不能反向决定 Domain 设计。

| 模块 | 处置 | 理由 |
|---|---|---|
| Provider 抽象 | 保留并按需扩展 | 支持本地和云端模型切换，与产品目标一致 |
| Agent Runner / Tool 调用 | 保留并增强 | 增加 Task Agent 的 Schema、预算和 allowlist，不无故重写稳定循环 |
| Agent Loop | 保留、解耦业务 | 继续服务交互 Agent；确定性后台任务走独立 Task Agent 入口 |
| ContextBuilder/通用 Prompt | 保留交互能力，新增 Career Context | 不让通用上下文进入所有后台任务 |
| Tool Registry / Schema | 保留 | Career Task 使用明确 allowlist，通用工具仍可供受控交互扩展 |
| Skill 系统 | 保留并版本化 Career Skill | 无关 Skill 默认不加载，不必仅因 P0 未使用就删除 |
| MCP | 隔离保留 | P0 非核心，但可能用于后续 Connector/工具扩展 |
| Session | 保留 | 仅服务交互 Agent，与业务数据彻底分离 |
| MessageBus | 保留现有交互用途 | Career Application/Job 不通过聊天消息总线维护状态 |
| Cron | 修改或扩展 | 保留通用 Agent 定时能力；新增确定性 Schedule/Job，必要时再合并实现 |
| ConfirmManager | 保留即时交互用途 | 业务确认另建持久化 Review Task |
| CareerStore | 替换并最终删除 | 粗糙两表模型不作为新 Domain 基础 |
| ResumeService/Tool | 重构或替换 | 迁入 Document、Fact、Material Application Service |
| Email Channel | 隔离保留 | 可作为未来通信 Channel，但绝不复用为只读业务 Connector |
| 通用 Exec Tool | 保留交互/开发用途 | 自动 Connector 禁用，OpenCLI 使用专用 Process Runner |
| 通用 Memory | 保留交互用途 | 不得作为 Career 事实库 |
| aiohttp Chat API | 可过渡保留 | Career API 独立设计；确认无消费者且新入口稳定后再决定删除 |
| 通用聊天 Channel | 默认禁用、按需保留 | 不进入 P0 主流程，但未来提醒或交互可能使用 |
| Subagent | 保留为可选扩展 | P0 工作流不依赖；若不影响功能无需删除 |
| 通用模板和示例 | 按维护成本清理 | 不影响构建的资源可保留，重复或误导内容再删除 |

## 8. `ai-job-search` 分析

### 8.1 产品工作流

该项目已经形成清晰的人工作业流：

```text
/setup
  → /scrape
  → /rank
  → /apply
  → /outcome 或 /gmail-sync
  → /interview
  → /upskill / html-report
```

其中：

- `/setup` 从 documents、单份 CV 或访谈建立候选人资料。
- `/scrape` 发现 Portal Skills，搜索岗位并用 `seen_jobs.json` 去重。
- `/rank` 使用完整匹配框架批量评分。
- `/apply` 执行 Drafter–Reviewer、LaTeX 编译、视觉检查和 ATS 文本层检查。
- `/outcome` 保存投递材料、岗位原文、结果和跟进信息。
- `/gmail-sync` 从 Gmail 提出状态更新，用户批准前不写记录。
- `/interview` 强制使用实际投递材料、岗位和前序反馈准备面试。

### 8.2 值得吸收的设计

1. **单一事实来源**：候选人主档案是生成内容的唯一事实依据，历史定制简历只能参考表达，不能反向成为事实。
2. **Drafter–Reviewer 分工**：生成和批判分离，Reviewer 检查事实、覆盖、语气和风险。
3. **申请快照**：每次申请归档岗位原文、实际 CV、求职信、结果和阶段材料。
4. **用户批准后写入**：Gmail 同步只提出批量更新，不擅自改变跟踪记录。
5. **质量门禁**：编译 PDF 后进行页面视觉检查和 ATS 文本层验证。
6. **差距诚实表达**：缺失技能作为 gap 处理，不做关键词填塞。
7. **面试上下文连续性**：面试准备优先使用岗位、实际材料和前一轮反馈。
8. **Portal Skill 契约**：每个门户有独立 CLI、参数和测试，主流程动态发现。
9. **防提示注入意识**：岗位内容和粘贴文本被当作数据，而非操作指令。
10. **隐私目录约定**：个人文档、申请归档和抓取状态默认不提交版本库。

### 8.3 不适合直接复用的部分

- 候选人事实散落在 CLAUDE.md 和多份 Skill Markdown，缺少逐条来源、确认和版本模型。
- 申请状态主要存 CSV 和 Markdown，缺少状态机、事务、引用完整性和事件投影。
- `seen_jobs.json` 的 URL 或 company+title 去重适合个人脚本，不足以处理岗位更新、下线和跨来源转载。
- Commands 依赖特定 Agent 平台的 Prompt 执行语义和工具名。
- 大量业务正确性依赖模型遵守长文档，而不是代码约束。
- Gmail Connector、Notion MCP、LaTeX 和特定国家招聘网站不能成为通用产品的强依赖。
- 主要交互仍是命令和文件，不是可查询、可编辑的本地 Web 应用。

### 8.4 迁移策略

| 内容 | 处理方式 |
|---|---|
| 事实来源与不虚构规则 | 转成 Domain 不变量、Tool 校验和 Skill 提示 |
| `/setup` 工作流 | 转成 Profile Import Application Use Case + Review Task |
| `/scrape` 和 Portal Skill 思路 | 参考 Connector/Adapter 发现与健康检查，不复用状态文件 |
| `/rank` 评分框架 | 迁移为可解释的 Job Match Skill，结论落结构化分析表 |
| `/apply` | 迁移为材料工作流，保留 Drafter–Reviewer 和验证门禁 |
| `/outcome` | 迁移为 Application Event 和 Interview Record |
| `/gmail-sync` | 迁移“提出、引用、批准后写入”原则，不依赖 Gmail 专有 API |
| `/interview` | 迁移上下文选择顺序和阶段化准备逻辑 |
| PDF 工具和模板 | 可选择性复用代码/思想，第一版同时支持 DOCX/PDF 路径 |

## 9. `OpenCLI` 分析

### 9.1 当前能力

OpenCLI 1.8.6 是 Node.js 20+ CLI，主要能力包括：

- 通过本地 daemon（默认 `127.0.0.1:19825`）和 Browser Bridge 扩展连接 Chrome/Chromium。
- 使用用户已有登录 Cookie 和页面上下文。
- 提供导航、点击、输入、DOM/可访问性树、网络请求和结构化提取能力。
- 支持内置 Adapter、`~/.opencli/clis` 用户 Adapter 和插件。
- 内置 Adapter 通过 manifest 快速注册，执行时延迟加载。
- 支持 JSON、YAML、CSV、Markdown、table 等输出。
- 提供 `read`/`write` access、Strategy、ephemeral/persistent site session、foreground/background window。
- 提供 Profile list/rename/use 和显式 `--profile` 路由。
- 提供结构化错误和稳定退出码。

实际加载优先级是：

```text
OpenCLI 内置 Adapter
  → ~/.opencli/clis 用户 Adapter 覆盖
  → OpenCLI Plugin 最后加载并可再次覆盖
```

这与需求文档中的“用户覆盖 → 用户自定义 →项目内置”可以兼容，但项目必须避免另造一套和 OpenCLI 冲突的物理加载规则。建议区分：

- **OpenCLI Adapter**：实际执行网站访问的 JS 命令。
- **Career Source Adapter Descriptor**：项目内定义的命令映射、输出 Schema、版本和调度策略。

### 9.2 BOSS Adapter 现状

OpenCLI 已有 BOSS Adapter：

- `auth.js` 注册登录状态检查、验证和登录流程。
- `search.js` 通过浏览器 Cookie 上下文调用 BOSS 页面接口，返回岗位列表。
- `detail.js` 获取完整描述、技能、公司、招聘者和地址。
- Adapter 声明为 `read`，适合 Demo 的只读采集。

它没有直接提供名为 `latest` 的命令。项目层统一接口可以做以下映射：

| Career Adapter 操作 | OpenCLI BOSS 命令 |
|---|---|
| `status` | `boss auth status` 或对应共享认证命令 |
| `login` | `boss auth login` |
| `latest` | `boss search` + Career 侧 `since/limit` 策略 |
| `detail` | `boss detail <security-id>` |

不要为了统一命名修改 OpenCLI 核心；在 Career Connector 适配层完成映射。

### 9.3 推荐集成方式

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| Agent 直接调用通用 Exec Tool | 改动最少 | 输出、超时、权限、幂等和审计不可控 | 只用于人工调试，不用于正式同步 |
| Python 直接导入 OpenCLI TypeScript/JS | 调用紧密 | 跨语言困难，绑定内部 API，升级脆弱 | 不采用 |
| 独立常驻 OpenCLI 微服务 | 状态和并发可集中 | 部署复杂，Demo 过度设计 | 暂不采用 |
| 受控子进程调用 `opencli` | 使用公开 CLI/退出码，升级边界清楚，易模拟测试 | 需要进程管理和 JSON 校验 | **Demo 推荐** |

推荐实现独立 `OpenCliProcessRunner`：

- 使用参数数组调用 `opencli`，不拼接 shell 字符串。
- 只允许配置中注册的只读 site/command。
- 固定 `--format json`，设置超时、输出上限和编码。
- 捕获 stdout、stderr、exit code、耗时和 Adapter 版本。
- 将退出码映射为 Connector 错误，不把 stderr 直接展示给用户或模型。
- Windows 优先解析 `opencli.cmd`，Linux/macOS 解析 `opencli`，路径由初始化向导验证并持久化。
- 定时任务直接调用 Application Use Case，不经过 LLM 或通用 Shell。
- Agent 如需主动刷新，只调用 `sync_job_source(source_id)` 业务 Tool。

### 9.4 Browser Bridge 和 Profile 生命周期

OpenCLI daemon 已支持按需启动和版本/扩展健康检查。Adapter 默认使用后台窗口、一次性 ephemeral site session，结束后释放 tab lease；登录和调试可以使用 foreground 并保留必要页面。

Demo 推荐：

- 只支持一个显式配置的 Browser Profile alias。
- 每次扫描前执行轻量健康和认证检查。
- 正常只读扫描使用 background + ephemeral session。
- 登录使用 foreground，由用户人工完成，不保存网站密码。
- 登录失效只把对应 Source 标记为 `requires_login`。
- 不自行复制 Cookie，不把 Cookie 写入 Career 数据库。
- 不尝试让用户长期保持招聘页面开启；Browser Bridge 扩展和 Chrome Profile 是实际前置条件。

### 9.5 可直接利用的错误模型

| OpenCLI 退出码 | 含义 | Career Connector 处理 |
|---|---|---|
| 0 | 成功 | 校验 Schema 后入 Source Event |
| 2 | 参数错误 | `configuration_error`，停止重试 |
| 66 | 空结果 | 成功但零数据；结合历史判断是否疑似 Adapter 退化 |
| 69 | Browser Bridge/服务不可用 | `connection_failed`，提示检查扩展 |
| 75 | 临时超时 | 指数退避重试 |
| 77 | 登录/权限问题 | `requires_login`，等待用户操作 |
| 78 | 配置错误 | 禁用本轮同步并提示修正 |
| 1/其他 | 未知或 Adapter 错误 | 保存诊断，标记 `adapter_failed` |

## 10. 三项目能力差距对比

| 能力 | nanobot-career | ai-job-search | OpenCLI | 目标处置 |
|---|---|---|---|---|
| Agent Runtime | 完整 | 依赖宿主 Agent | 不负责 | 复用 nanobot |
| 用户事实 | 单表文本字段 | Markdown 单一事实源 | 无 | 新建结构化 Fact Domain |
| 岗位发现 | 临时 BOSS Skill | 多 Portal CLI 工作流 | 网站 Adapter | OpenCLI Connector + Domain |
| 岗位去重 | 无 | URL/company+title JSON | Adapter 内仅单次去重 | 外部 ID + 版本哈希 + 跨源实体归一 |
| 岗位匹配 | Prompt Skill | 完整评分框架 | 无 | 迁移框架，结构化证据 |
| 材料版本 | 简单 parent resume | 文件命名和申请归档 | 无 | ResumeVersion + Application Snapshot |
| Reviewer | 无专门流程 | 成熟 | 无 | 迁移为 Agent Workflow |
| 申请管理 | 无 | CSV + Markdown | 无 | 新建状态机和 Event |
| 邮件同步 | IMAP/SMTP Channel | Gmail 批量确认 | 无 | 新建只读 IMAP Connector |
| 提醒 | 通用 Cron | Prompt/文件 | 无 | Domain Reminder + Scheduler |
| 面试 | 无 | 阶段准备和归档 | 无 | 迁移工作流，结构化记录 |
| Web UI | 无业务 UI | 离线 HTML 报告 | 无 | 新建本地 Web 应用 |
| 审计 | Session/日志 | 文件历史 | trace/错误 | AgentRun、SyncRun、Event 审计 |
| 凭证安全 | 普通 JSON 字符串 | 外部 Connector | 浏览器 Cookie 由 Profile 管理 | OS keyring + 引用式配置 |
| 测试 | 通用框架较多，Career 很少 | Prompt/工具/Portal 测试 | 单元、Adapter、E2E 丰富 | Domain + Contract + Fixture 测试 |

## 11. 目标架构和具体模块划分

### 11.1 分层职责

#### Local Web UI

负责页面、表单、看板、时间线、同步状态、人工确认和 Agent 执行展示。页面不能直接写数据库。

#### Career API

负责 HTTP/SSE、身份/本地会话、DTO 校验和调用 Application Service。API handler 不包含匹配、状态转换或 Connector 逻辑。

#### Career Application Layer

编排一个完整用例和事务，例如导入资料、同步来源、创建申请、确认事件、生成材料、安排提醒。该层调用 Domain、Repository、Connector Port 和 Agent Port。

#### Career Domain

保存实体、值对象、状态机、校验、去重规则、事件生成和业务策略。Domain 是纯 Python，不导入 Agent、HTTP、IMAP、OpenCLI 或 SQLite 实现。

#### Agent Runtime

在现有 nanobot Provider、Runner、Tool Schema、AgentLoop 和流式能力上按需扩展。交互 Agent 可以继续使用当前 Loop；后台 Career Task 增加受约束执行入口。只有现有实现确实影响边界或可靠性时才重构。Agent 只能调用 Application 层公开的 Career Tools。

#### Connectors

负责外部系统访问和标准化。每个 Connector 独立失败，输出统一 Source Event，不写申请状态。

#### Infrastructure

负责 SQLite、文件存储、Secret Store、进程运行、调度器、日志、迁移和系统时间。

### 11.2 推荐目录

建议在现有 nanobot 包内建立清晰的 Career 分层，同时保持通用 Runtime 边界：

```text
career_console/runtime/
├── agent/                         # 现有通用交互 Runtime，按需改进
├── providers/
├── session/
├── bus/
├── channels/                      # 可选扩展，默认不参与 Career 主流程
├── career/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   ├── connectors/
│   ├── agent/
│   └── api/
├── api/
└── cli/
web/
tests/
resources/
```

不要求为建设 Career 模块整体搬迁或重写 `nanobot` 包。只有当现有模块确实阻碍依赖边界时才移动或拆分；删除应在新路径稳定、确认无扩展价值且相关测试和调用已清理后进行。

目标包内部建议为：

```text
career_console/business/
├── domain/
├── application/
├── infrastructure/
├── connectors/
├── agent/
└── api/
```

### 11.3 依赖规则

```text
domain          → 仅标准库/轻量值对象
application     → domain + ports
connectors      → application ports + 外部库
infrastructure  → application ports + domain
agent tools     → application use cases
api             → application use cases
web             → api
```

禁止反向依赖：Domain 不导入 Agent；Connector 不导入具体 Repository；API 不直接执行 SQL；Agent Tool 不直接拿数据库连接。

## 12. 核心数据模型

### 12.1 用户与事实

#### `candidate_profiles`

单用户产品仍保留 profile 实体，用于身份和整体设置；不要用一行保存全部经历。

主要字段：`id`、`display_name`、`timezone`、`locale`、`created_at`、`updated_at`。

#### `candidate_facts`

主要字段：

- `id`、`profile_id`。
- `fact_type`：education、employment、project、skill、achievement、preference、constraint、star_case 等。
- `subject`、`value_json`、`normalized_value`。
- `status`：proposed、confirmed、rejected、superseded。
- `confidence`、`valid_from`、`valid_to`。
- `created_at`、`updated_at`、`confirmed_at`。

#### `fact_sources`

关联 Fact 与 Document、用户输入、URL 或 Agent Run，允许一个事实有多个证据。

### 12.2 文档和材料

#### `documents`

记录本地文件元数据、类型、MIME、哈希、存储路径、原始文件名和来源。数据库保存相对存储引用，不把大文件直接塞入业务表。

#### `resumes` / `resume_versions`

- `resumes` 表示逻辑简历系列，如“基础简历”“后端方向简历”。
- `resume_versions` 表示不可变内容版本，保存 parent、状态、目标岗位、事实快照引用、生成 Agent Run、用户确认和导出文件。

#### `application_material_snapshots`

申请与实际投递材料之间的不可变绑定，记录内容哈希和提交时间。

### 12.3 招聘来源和岗位

#### `connectors` / `job_sources`

保存类型、显示名、配置引用、调度、Profile alias、Adapter descriptor、状态和最近错误。Secret 只保存 keyring reference。

#### `sync_cursors`

按 Connector + scope 保存游标。OpenCLI 来源可保存最后扫描窗口或分页状态；IMAP 保存 folder、UIDVALIDITY 和 last UID。

#### `sync_runs`

保存开始/结束、状态、扫描/新增/更新/重复/失败数、错误类型、Connector/Adapter 版本和重试次数。

#### `source_events`

统一的不可变采集事件：

- `source_type`、`source_id`、`external_id`。
- `event_type`、`occurred_at`、`collected_at`。
- `content_type`、`normalized_payload_json`。
- `raw_reference_json`、`deduplication_key`。
- `connector_version`、`sync_run_id`。

#### `companies`

保存规范名、别名、域名和人工确认信息。

#### `job_posts` / `job_post_versions`

- `job_posts` 表示跨时间稳定的岗位身份。
- `job_post_versions` 保存每次内容变更和原始 payload 引用。
- 外部来源映射单独保存 `job_post_sources`，允许跨来源转载归一到同一岗位。

#### `job_requirements`

保存硬性/优先条件、类别、原文证据和结构化值。

#### `job_match_analyses`

保存总体建议、优先级、每项要求对应的 Candidate Fact 证据、差距、置信度、成本和 Agent Run。不要只保存单个分数。

### 12.4 申请与事件

#### `applications`

主要字段：`id`、`job_post_id`、`company_id`、`current_status`、`applied_at`、`closed_at`、`created_at`、`updated_at`。

#### `application_events`

不可变事件字段：

- `event_type`、`occurred_at`、`recorded_at`。
- `previous_status`、`next_status`。
- `source_type`、`source_id`、`evidence_json`。
- `confidence`、`confirmed_by_user`。
- `supersedes_event_id`、`agent_run_id`。

#### `application_event_proposals`

邮件或 Agent 生成的候选事件，在确认前不进入正式时间线。

### 12.5 邮件、任务和面试

#### `messages`

只保存与求职相关或待判断邮件的必要元数据、正文摘要/最小必要正文、哈希和原始引用。无关邮件不长期保存正文。

#### `message_entities`

保存提取出的公司、岗位、申请编号、时间、链接和分类证据。

#### `review_tasks`

保存待用户确认的事实、岗位合并、申请匹配、事件变化或材料发布。包含 payload、候选项、风险、状态、截止时间和处理结果。

#### `tasks` / `reminders`

Task 表示用户要完成的工作；Reminder 表示何时提醒。两者不能混为 Cron Job。

#### `interviews` / `interview_records` / `interview_questions`

分别表示安排、某次实际面试记录及其中问题。录音和转写通过 Document 引用，反馈和长期弱点分开保存。

### 12.6 Agent 审计

#### `agent_runs` / `agent_actions`

保存任务类型、模型、Skill/Prompt 版本、输入数据引用、工具调用、输出、token/耗时、状态和错误。默认不永久保存不必要的敏感全文。

## 13. 申请状态机

推荐状态：

```text
discovered
pending_evaluation
recommended
not_pursuing
preparing_materials
ready_to_apply
submitted
application_confirmed
assessment
written_test
interview
offer
rejected
withdrawn
archived
```

状态机规则示例：

- `discovered → pending_evaluation → recommended/not_pursuing`。
- `recommended → preparing_materials → ready_to_apply → submitted`。
- `submitted → application_confirmed/assessment/written_test/interview/rejected`。
- `assessment/written_test → interview/rejected`。
- `interview → interview/offer/rejected/withdrawn`，多轮面试通过独立 Interview 实体表达。
- `offer → archived/withdrawn`，是否接受 Offer 应由用户明确确认，不从邮件自动推断。

状态不是严格线性流程。迟到邮件、流程跳级、同一申请多轮面试和更正都必须支持。状态机应允许“追加更正事件并重建投影”，不删除历史事件。

## 14. 关键应用模块和用例

### 14.1 Profile 模块

- 导入简历/文档。
- 生成事实候选。
- 批量确认、拒绝和编辑事实。
- 管理偏好、限制、目标岗位和 STAR 案例。
- 查询事实来源与变更历史。

### 14.2 Job Discovery 模块

- 配置 OpenCLI 来源和调度。
- 手动刷新、健康检查和重新登录。
- 校验 Adapter 输出。
- 岗位身份解析、版本化、下线检测和跨来源合并。
- 生成匹配分析和优先级。

### 14.3 Materials 模块

- 管理基础简历和模板。
- 锁定岗位版本与事实范围。
- Drafter 生成草稿。
- Reviewer 审查事实、岗位覆盖、语气和风险。
- 导出 PDF/DOCX，并执行视觉、文本层和 ATS 检查。
- 用户确认后创建最终版本和申请快照。

### 14.4 Application 模块

- 创建申请。
- 用户确认投递。
- 维护完整事件时间线和状态投影。
- 处理事件候选、冲突和更正。
- 关联邮件、岗位、材料、任务和面试。

### 14.5 Message 模块

- 只读 IMAP 同步。
- 规则过滤、轻量分类和详细提取。
- 申请匹配与冲突处理。
- 创建事件候选、时间候选和 Review Task。

### 14.6 Planning 模块

- 截止时间和日程管理。
- 多阶段提醒和冲突检测。
- 自动创建笔试、面试准备任务。
- 每日/每周求职简报。

### 14.7 Interview 模块

- 面试安排和轮次。
- 基于岗位、实际材料和历史反馈生成准备包。
- 手动记录或主动上传录音。
- 转写、问题提取、答案分析和用户确认。
- 形成长期弱点和学习任务。

### 14.8 Review Center

统一处理：

- 新事实确认。
- 岗位重复/合并确认。
- 邮件与申请匹配确认。
- 申请事件和状态变化确认。
- 材料最终版本确认。
- 高风险 Agent 操作确认。

现有聊天 `ConfirmManager` 不能替代该模块，因为 Review Task 必须持久化、可稍后处理、可从 Web 查询和审计。

## 15. Connector 统一模型

### 15.1 接口建议

```python
class Connector(Protocol):
    type: str
    version: str

    async def health(self, context) -> ConnectorHealth: ...
    async def initial_sync(self, context, options) -> SyncBatch: ...
    async def incremental_sync(self, context, cursor) -> SyncBatch: ...
    async def close(self) -> None: ...
```

`SyncBatch` 包含 Source Events、新游标、统计和诊断；Application Service 负责在同一事务中保存事件和游标。只有事件成功持久化后才能推进游标，防止进程中断导致丢数据。

### 15.2 生命周期状态

```text
unconfigured
disabled
connecting
healthy
syncing
requires_login
authentication_failed
connection_failed
configuration_error
adapter_failed
rate_limited
degraded
```

### 15.3 错误分类

- `permanent_configuration`：不自动重试。
- `authentication`：等待用户重新登录或更新授权码。
- `transient_network`：指数退避和抖动重试。
- `rate_limit`：尊重冷却时间，不密集重试。
- `schema_validation`：保留隔离样本，不写正式业务表。
- `adapter_regression`：标记 degraded，提醒升级或覆盖。
- `unknown`：有限重试后进入人工诊断。

### 15.4 测试契约

每个 Connector 必须有：

- Fixture 驱动的解析测试。
- 游标前进和断点恢复测试。
- 相同事件重复同步的幂等测试。
- Schema 不合法隔离测试。
- 单来源失败不影响其他来源测试。
- Secret 和日志脱敏测试。
- 初次同步与增量同步边界测试。

## 16. 招聘信息采集方案

### 16.1 定时扫描流程

```text
Scheduler 触发 source_id
  → 创建 SyncRun
  → 获取来源互斥锁
  → OpenCLI health/profile/auth 检查
  → 调用 Career Adapter latest
  → JSON Schema 校验
  → 写 Source Event
  → 外部 ID/哈希去重
  → 创建或更新 JobPostVersion
  → 标记疑似下线/变化
  → 提交游标和 SyncRun
  → 异步触发匹配分析
```

默认每天 09:00 和 18:00 扫描，但必须使用用户时区并允许配置。

### 16.2 去重和版本

优先级：

1. 同一来源 + 外部岗位 ID。
2. 规范化 URL。
3. 公司规范实体 + 岗位规范名 + 地点。
4. 描述指纹和发布时间。
5. 模糊候选进入 Review Task，不自动合并。

每次描述、地点、截止时间或状态变化都生成新 `JobPostVersion`。连续若干次未出现不能立即认定下线；需要 Adapter 明确状态或达到来源特定阈值。

### 16.3 Adapter Descriptor

项目中保存描述符而不是复制 OpenCLI 内部注册系统：

```yaml
id: boss
adapter_version: 1
opencli_site: boss
commands:
  status: [auth, status]
  login: [auth, login]
  latest: [search]
  detail: [detail]
output_schema: boss-job-candidate-v1.json
access: read_only
default_schedule: "0 9,18 * * *"
```

用户覆盖主要覆盖 descriptor 或 `~/.opencli/clis` 中的具体命令。Web UI 应明确展示当前实际命令来源和版本，避免用户不知道某个本地 Adapter 正在遮蔽内置版本。

### 16.4 Demo Adapter 范围

- 一个 Browser Profile。
- 一个 BOSS 来源。
- status/login/latest/detail。
- 手动刷新和每天两次扫描。
- Schema 校验、同步记录、登录失效提示。
- 只读搜索和详情；不允许 greet、send、exchange、invite、mark、batchgreet 等写操作。

## 17. 邮箱读取方案

### 17.1 独立 Email Connector

新 Connector 使用标准 IMAP，不依赖 Gmail/Outlook 专有 API。Demo 支持一个账户和一个或少量配置文件夹。

强制规则：

- `select(mailbox, readonly=True)`。
- 使用 IMAP UID 命令，不使用易变化的 sequence number 作为游标。
- 使用 `BODY.PEEK`，不修改 `\\Seen`。
- 不调用 STORE、COPY、MOVE、EXPUNGE、DELETE 或 SMTP。
- 初期不使用 IMAP IDLE，只做每十分钟轮询。

### 17.2 首次同步

1. 用户选择 90/180 天或自定义范围。
2. 只获取候选邮件的 envelope/header。
3. 规则判断后才获取可能相关的正文。
4. 相关邮件创建 Message、Source Event 和事件候选。
5. 无关邮件只保存去重所需的最小哈希/ID，或按隐私策略完全丢弃正文。
6. 将历史申请重建结果作为批量 Review Task 展示。

### 17.3 增量游标

每个 account + folder 保存：

- `uid_validity`。
- `last_committed_uid`。
- `last_success_at`。
- `message_id/content_hash` 幂等索引。

流程中先保存邮件和 Source Event，再提交游标。UIDVALIDITY 改变时不能简单从 1 全量重放，应进入恢复流程，按时间范围 + Message-ID + 哈希重新对账。

### 17.4 过滤和分类

```text
Header/发件域名/主题规则
  → 招聘相关概率分类
  → 仅对相关或可能相关邮件读取/分析正文
  → 类型与字段提取
  → 申请实体匹配
  → Event Proposal / Reminder Proposal
```

分类类型至少包括：application_confirmation、assessment_invitation、written_test_invitation、interview_invitation、interview_reschedule、interview_result、rejection、offer、onboarding、career_event、job_recommendation、follow_up、irrelevant、unknown。

### 17.5 申请匹配

按以下顺序：

1. 申请编号、候选人编号等精确标识。
2. 邮件线程或已确认 Message 关联。
3. 规范公司 + 规范岗位。
4. 公司域名、投递时间和当前状态组合。
5. 模糊规则和 Agent 排序。
6. 不唯一时创建 Review Task。

Agent 只能排序候选申请并说明证据，不能在不确定时自行选定。

### 17.6 凭证安全

推荐优先使用跨平台 Python keyring 抽象：

- Windows Credential Manager。
- macOS Keychain。
- Linux Secret Service。
- 无可用系统钥匙串时，明确提示用户并提供本地加密文件降级方案；主密钥不能与密文同文件保存。

普通配置和数据库只保存 `secret_ref`。导出配置不包含授权码，API 不返回 secret，日志对邮箱地址和服务器错误做脱敏。

### 17.7 Demo 邮箱范围

- 一个标准 IMAP 账户。
- 一个 INBOX 文件夹。
- 只读首次历史同步和十分钟增量轮询。
- 主题、发件人、时间、文本/HTML 正文解析。
- 识别笔试、面试、拒信和 Offer。
- 创建申请事件候选、用户确认任务和提醒。
- 不支持 OAuth、IDLE、多邮箱统一收件箱、附件全文解析或邮件发送。

## 18. Agent、Skill 和 Workflow 设计

推荐 Career Skills：

- `career-profile-extraction`
- `career-job-requirement-extraction`
- `career-job-fit-analysis`
- `career-resume-drafter`
- `career-resume-reviewer`
- `career-email-classification`
- `career-interview-preparation`
- `career-interview-analysis`
- `career-outcome-review`
- `career-strategy-analysis`

但 Skill 不等于业务模块。Skill 负责模型如何思考，Application Service 负责何时运行、允许读取什么、输出如何校验、是否需要用户确认和如何持久化。

推荐 Tool 粒度：

```text
get_candidate_facts
propose_candidate_facts
confirm_candidate_facts
import_job_source_item
evaluate_job
create_application
confirm_application_submitted
propose_application_event
confirm_application_event
create_material_draft
review_material_draft
confirm_material_version
create_review_task
create_reminder
save_interview_feedback
sync_connector
```

禁止提供 `execute_sql`、`update_any_table` 或让 Agent 直接使用通用文件编辑器维护业务数据。

## 19. 本地 Web 产品模块

### 19.1 Dashboard

今日待办、新岗位、待确认事项、临近截止、笔面试、最近状态变化和申请漏斗。

### 19.2 Profile

按类型展示事实、来源、确认状态、冲突和历史版本；支持导入和补充。

### 19.3 Job Pool

岗位列表、来源、版本变化、匹配证据、优先级、截止时间和处理状态。

### 19.4 Application Board

看板与列表双视图，支持完整事件时间线、材料快照、邮件和任务关联。

### 19.5 Review Center

集中处理事实、岗位合并、邮件匹配、状态变化和材料确认。

### 19.6 Materials

基础简历、版本、模板、生成记录、Reviewer 结果和导出验证。

### 19.7 Interview Center

日程、准备包、问题、记录、转写、反馈和重复弱点。

### 19.8 Data Sources

OpenCLI/IMAP 来源配置、健康、游标、最近同步、错误、重新登录、手动刷新和 Adapter 来源。

### 19.9 Agent Runs

展示任务计划、使用的数据来源、Tool 调用、结果和错误；对敏感字段默认折叠或脱敏。

## 20. API 划分

建议最小路由组：

```text
/api/profile
/api/facts
/api/documents
/api/resumes
/api/jobs
/api/job-analyses
/api/applications
/api/application-events
/api/messages
/api/interviews
/api/tasks
/api/reminders
/api/review-tasks
/api/connectors
/api/sync-runs
/api/agent-runs
/api/dashboard
```

命令型操作使用显式 endpoint，例如：

```text
POST /api/connectors/{id}/sync
POST /api/connectors/{id}/login
POST /api/review-tasks/{id}/resolve
POST /api/applications/{id}/confirm-submitted
POST /api/jobs/{id}/evaluate
POST /api/materials/{id}/review
```

不要通过通用 PATCH 任意改变 `current_status`。状态必须通过 Application Command 和 Event 创建。

## 21. 非功能需求

### 21.1 本地优先和可迁移

- 用户数据位于代码仓库之外，例如 `~/.nanobot-career/`。
- SQLite 数据库、文件和配置可以整体备份和导出。
- 数据库升级使用显式 migration，支持备份和失败恢复。
- 路径在 Windows、macOS、Linux 上通过平台 API 解析，不在业务数据中混用路径格式。

### 21.2 性能

- 常规 Dashboard 本地查询目标小于 300ms。
- Connector 同步、材料生成和录音分析作为后台 Job，不阻塞 HTTP 请求。
- 首次邮箱同步分批处理，限制每批数量和模型并发。
- SQLite 启用 WAL、busy timeout 和短事务；异步代码不在事务内等待网络或模型。

### 21.3 可恢复性

- Sync Run 和 Agent Run 有状态与 checkpoint。
- Source Event 和游标提交具备原子性或可重放补偿。
- 所有外部写入具有幂等键。
- 应用异常重启后能继续待处理 Review Task 和后台 Job。

### 21.4 隐私和安全

- Secret 使用系统钥匙串。
- 原始邮件、录音和材料按数据类别设置保留策略。
- 模型调用前展示或记录将发送的数据范围。
- 支持删除单一来源数据和“删除全部个人数据”。
- 日志不记录 API key、授权码、Cookie、完整简历、完整邮件或录音内容。
- localhost Web 服务默认只监听 loopback，并使用随机本地 token、防 CSRF 和严格 CORS。
- OpenCLI 只允许读命令；BOSS 写命令不进入 Connector allowlist。

### 21.5 可观测性

- 区分业务错误、Connector 错误、模型错误和用户待确认。
- 每个 Sync Run 和 Agent Run 有 correlation ID。
- Web 页面展示健康摘要，详细日志保存在本地并脱敏。

## 22. 功能优先级

### P0：Demo 必须完成

- 结构化 Candidate Fact 和用户确认。
- 简历导入及基础版本管理。
- 一个 OpenCLI BOSS Connector、一个 Profile、手动/定时同步。
- Job Post、版本、去重和可解释匹配。
- 定制材料 Drafter–Reviewer 和用户确认。
- Application、事件时间线和材料快照。
- 一个严格只读 IMAP Connector、首次/增量同步和游标。
- 笔试、面试、拒信、Offer 分类及 Review Task。
- Reminder 和基础面试准备/反馈。
- 本地 Web 的 Dashboard、Profile、Job、Application、Review、Data Source 基础页面。

### P1：第一版产品

- PDF/DOCX 完整导入和导出验证。
- 多个招聘来源、Adapter 管理和版本提示。
- 多邮箱账户与更多文件夹。
- 复杂岗位归一化、跨来源去重。
- 每日/每周简报、时间冲突检测。
- 录音上传、转写和面试问题提取。
- 数据导出、备份、恢复和删除中心。

### P2：增强

- 用户自定义 Adapter 创建和验证 UI。
- OAuth 邮箱、IMAP IDLE。
- 高置信度规则的可配置自动确认。
- 长期申请漏斗、材料效果和来源效果分析。
- 本地模型处理敏感分类与转写。

### P3：长期探索

- 公众号/浏览器扩展主动转发的稳定产品化。
- 跨设备只读查看。
- 更完整的实时录音辅助，但必须满足明确同意与法律合规。
- 在用户明确授权下的低风险投递辅助；不包含自动批量投递。

## 23. Demo 技术方案和验收标准

### 23.1 Demo 用户流程

1. 安装并完成本地向导。
2. 导入简历，确认一组用户事实。
3. 连接 Browser Bridge，选择 Profile，登录 BOSS。
4. 手动或定时获取新岗位。
5. 查看岗位匹配证据并选择一个岗位。
6. 生成、审查和确认定制材料。
7. 用户确认已投递，系统保存申请和材料快照。
8. 配置一个 IMAP 邮箱并同步邮件。
9. 系统提出面试/笔试/拒信/Offer 事件，用户确认。
10. 系统创建提醒并生成面试准备包。
11. 用户记录面试反馈，系统生成改进建议。

### 23.2 验收标准

- 相同 OpenCLI 结果重复同步不产生重复 Job Post。
- 岗位正文变化产生新版本且保留旧版本。
- OpenCLI 登录失效时只暂停该来源并提示用户。
- 邮箱连接全过程不改变已读状态或其他服务器状态。
- 重启后 IMAP 从已提交 UID 继续，不重复创建事件。
- 邮件不能直接改变 Application 状态，必须产生 Review Task。
- 每条材料事实都能追溯到已确认 Candidate Fact。
- 投递后修改基础简历不会改变历史申请材料快照。
- 用户可以从 Web 查看一次申请的完整岗位、材料、邮件和事件时间线。
- 单个 Connector 失败不影响其他页面和任务。

### 23.3 Demo 明确不做

- 所有招聘网站和多个 Browser Profile。
- 自动发布或自动回滚 Adapter。
- OAuth、IMAP IDLE、实时推送、附件全文分析。
- 自动改变申请状态或自动发送邮件。
- 自动投递、自动打招呼或批量沟通。
- 多租户、企业协作和云端托管。

## 24. 分阶段开发路线

### Phase 0：架构与基线

- 确认本报告中的模块边界和关键决策。
- 建立 Python `.venv`、锁定依赖、运行现有测试并记录基线。
- 确定用户数据目录、SQLite migration 工具、Secret Store 和 Web 技术栈。
- 盘点真实用户数据和旧 Career 调用；新模型稳定后替换 CareerStore。无数据且无调用时可删除，有数据则提供迁移/导入。

### Phase 1：Career Domain 和数据基础

- Candidate Fact、Document、Job、Application、Event、Review Task 核心实体。
- Repository 接口、SQLite schema/migration、事件和时区规范。
- Career Application Service 和第一批结构化 Tool。

### Phase 2：岗位与材料闭环

- 手动岗位导入和 Job Match。
- Drafter–Reviewer。
- Resume Version、材料确认和 Application Snapshot。
- Application 状态机和时间线。

### Phase 3：Connector 基础与邮件

- Connector、Source Event、Cursor、Sync Run 统一模型。
- 严格只读 IMAP、过滤、分类、匹配和 Review Task。
- Reminder 与确定性 Scheduler Job。

### Phase 4：本地 Web UI

- Dashboard、Profile、Job Pool、Application、Review Center、Data Sources。
- 后台 Job 状态和 SSE 进度。

### Phase 5：OpenCLI 招聘来源

- 受控 Process Runner、Profile/Login 向导、BOSS Descriptor。
- 定时扫描、Schema 校验、岗位版本和 Adapter 健康。

说明：OpenCLI 可在 Phase 2 使用手动调用做原型，但正式 Connector 建议在统一 Source Event 模型完成后接入，避免形成第二套临时数据结构。

### Phase 6：面试和长期优化

- 面试准备、反馈、录音上传和转写。
- 重复弱点、漏斗、材料效果、来源效果和策略建议。

## 25. 风险和待确认问题

### 25.1 高风险

1. **招聘网站稳定性和合规**：页面、接口和风控会变化；BOSS Adapter 不能视为永久稳定接口。
2. **邮件隐私**：错误过滤可能把无关敏感邮件送入模型，需要严格本地预筛和保留策略。
3. **Prompt Injection**：邮件和岗位内容是高风险外部输入，必须通过工具权限和数据边界限制。
4. **边界混淆**：如果直接让 Career Domain 依赖 CareerStore、MessageBus、Agent Loop 或 Chat API，会把交互框架语义带进业务核心。解决方式是依赖隔离和适配，不要求删除这些通用模块。
5. **SQLite 并发**：Web、Scheduler、Agent 和 Connector 同时运行时需要明确写入串行化和事务策略。

### 25.2 中风险

- Windows 下 Node/OpenCLI、`.cmd`、Chrome Profile 和 Python 环境初始化复杂。
- OpenCLI 用户 Adapter 和 Plugin 的覆盖顺序可能造成难以诊断的版本漂移。
- PDF/DOCX 跨平台渲染、字体和 ATS 验证存在环境差异。
- 邮箱供应商在 IMAP、文件夹命名、UIDVALIDITY 和认证方式上存在差异。
- 模型输出 Schema、时间解析和公司/岗位归一化需要大量真实样例回归。

### 25.3 需要产品/架构确认

1. 本地 Web 前端采用轻量服务端模板，还是 React/Vue 独立前端。
2. 是否接受以 `~/.nanobot-career/` 作为新的独立数据根目录。
3. Demo 的唯一内置招聘来源是否确定为 BOSS。
4. Demo 简历输出优先 PDF、DOCX，还是两者都做。
5. 云端模型处理前是否需要默认显示数据发送预览。
6. 第一版以 Local Web 和必要 CLI 为主入口；通用聊天 Channel 不进入 P0 核心路径，但可以默认禁用并保留作后续扩展。
7. 面试录音首版采用本地 Whisper、可选云端转写，还是暂只支持文本记录。

## 26. 推荐的首个代码里程碑

首个里程碑不应是“先把 OpenCLI 或邮箱跑起来”，而应是：

> 建立可迁移的 Career Domain 最小骨架，并打通“事实 → 岗位 → 申请 → 事件 → Review Task”的确定性数据路径。

建议第一批交付：

1. 用户数据目录和 SQLite migration 基础。
2. CandidateFact、JobPost/Version、Application/Event、ReviewTask。
3. Repository 和 Application Service。
4. 结构化 Career Tools，不允许 Agent 直接写表。
5. 手动导入一个岗位，完成匹配并由用户确认创建申请。
6. API 层可查询完整时间线。

完成这一骨架后，Email 和 OpenCLI 都可以作为同一种 Source Event 生产者接入；如果先各自实现同步，很容易产生两套游标、错误、去重和确认逻辑。

## 27. 最终结论

新产品的核心不是 Agent 本身，而是一个可信、连续、可追溯的 Career Domain。nanobot 提供可持续改进的 Agent Runtime 和扩展基础，ai-job-search 提供经过实践验证的求职工作流，OpenCLI 提供登录态网站访问能力。正确组合方式是保持清晰边界：保留不冲突且有扩展价值的框架能力，只修改真正影响产品正确性的部分。

```text
nanobot       = Adaptable Agent Runtime Foundation
ai-job-search = Workflow and Quality Reference
OpenCLI       = Browser-backed Source Infrastructure
Career Domain = Product System of Record
```

后续所有实现判断都应回到一个标准：它是否强化了“事实可信、状态确定、来源可追溯、用户可控制”的完整求职闭环。如果某项能力只能在一次聊天中工作、无法持久化和审计，它就不是产品核心能力；如果某项外部自动化会绕过用户确认或破坏本地隐私，它就不应进入第一版。
