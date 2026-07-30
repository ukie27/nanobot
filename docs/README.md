# CareerConsole 核心业务与使用手册

> 文档性质：唯一持久产品文档
> 基线日期：2026-07-29
> 当前版本：`0.1.0.dev0`
> 数据库 revision：`20260729_0031`
> 维护原则：功能、规则、页面、配置或运行方式发生变化时，必须在同一变更中更新本文。

## 1. 文档职责

本文是 CareerConsole 的业务事实源，统一回答以下问题：

- 产品解决什么问题，明确不做什么；
- 用户从建立档案到完成申请、面试和复盘的完整流程；
- 当前每项功能是否已经实现；
- 正式业务数据如何产生、确认、冻结和追溯；
- 如何安装、启动、配置、测试、备份和排障；
- 开发新功能时必须维护哪些业务约束。

代码、数据库迁移和自动化测试是实现事实的最终依据。本文不得把规划写成已完成功能；无法从实际代码和测试确认的能力必须标为“部分实现”或“尚未提供”。

状态定义：

- **已实现**：存在正式代码路径、持久化模型/API，并有相应测试或可执行验证。
- **部分实现**：主流程可用，但仍有明确缺口或交付限制。
- **尚未提供**：只有设想，或没有可用的正式产品路径。

## 2. 产品定位

CareerConsole 是面向个人求职者的本地单用户求职操作台。它把分散的简历、岗位、邮件、申请进度、任务和面试反馈组织成可追溯的业务系统，并使用受控 Agent 完成非结构化信息理解和候选建议。

核心业务链路：

```text
用户资料
  → 职业事实与偏好
  → 招聘机会与具体岗位
  → 岗位匹配与每日推荐
  → 简历方向、材料生成与审核
  → 用户在外部网站投递
  → CareerConsole 确认申请并冻结快照
  → 邮件证据、申请事件、日程和任务
  → 面试准备、复盘和成长项
  → 经用户确认后回流职业档案与策略
```

CareerConsole 不是：

- 自动批量投递或自动联系招聘方的机器人；
- 完整邮件客户端；
- 企业 ATS 或多人协作平台；
- 无边界网页抓取器；
- 用聊天历史或模型记忆替代业务数据库的通用助手；
- OpenCLI 本体。OpenCLI 是外部应用，CareerConsole 只通过受控 CLI 和本地插件调用。

## 3. 不可破坏的业务规则

1. **Agent 只输出结构化候选。** 正式业务状态由确定性 Domain 和 Application Service 修改。
2. **事实必须可信。** 未确认职业事实不能进入正式材料或长期策略。
3. **推荐池与申请池分离。** 推荐被用户接受后才能建立待投递申请。
4. **申请绑定具体简历版本。** 确认投递时冻结岗位、简历和导出物快照。
5. **历史不可被未来覆盖。** 后续修改简历或岗位不能改变已投递申请的冻结材料。
6. **面试准备读取实际投递材料。** 没有已提交快照时不得生成正式准备包。
7. **邮件只是证据来源。** 高可信、低歧义招聘邮件可按确定性策略自动补录；其他情况进入待确认。
8. **邮箱同步只读。** 扫描已读和未读邮件，不执行 STORE、MOVE、DELETE、EXPUNGE 或发送邮件。
9. **主动邮件扫描最多一个月。** 业务时间统一按 `Asia/Shanghai` 展示和判断。
10. **工作区由用户选择。** Bootstrap 只保存当前工作区位置和最小启动元数据。
11. **不迁移旧 Career Store。** 新 CareerConsole 数据从当前业务模型开始建立。
12. **密钥不进入普通配置、文档、日志、API 响应或默认导出。**

## 4. 核心业务对象

```text
CandidateProfile
├── CandidateFact
├── CareerPreference
├── ProfileInsightProposal
├── StrategySnapshot
└── DailyDigest

RecruitmentOpportunity
└── JobPost
    ├── JobPostVersion
    ├── JobRequirement
    ├── JobFitProposal / JobMatchAnalysis
    ├── JobRecommendation
    └── ResumeDirectionProposal

Resume / Material
├── ResumeVersion
├── MaterialDraft
├── MaterialAgentProposal
├── MaterialReview
└── MaterialExport

Application
├── ApplicationResumeBinding
├── ApplicationMaterialSnapshot
├── ApplicationEvent
├── ApplicationEventProposal
├── CareerTask / Reminder / Schedule
└── Interview
    ├── PreparationPack
    ├── InterviewRecord
    ├── InterviewFeedback
    └── ImprovementItem

Runtime
├── AgentRun
├── ReviewTask / ReviewBundle
├── BackgroundJob
├── SyncRun
├── SchedulerRun
└── ChannelDeliveryRun
```

## 5. 当前功能总表

| 业务区域 | 状态 | 当前可用能力 | 当前边界 |
|---|---|---|---|
| 初始化与工作区 | 已实现 | 首次向导、目录选择、工作区验证、创建、切换、迁移包导入导出 | 切换为同进程重启，不是独立 Launcher 双实例切换 |
| 统一设置 | 已实现 | 普通配置、Provider、Agent、OpenCLI、牛客、BOSS、IMAP、QQ、Scheduler 的前端配置与独立测试 | 部分外部能力仍依赖用户自行安装或登录 |
| 职业档案 | 已实现 | PDF/DOCX/Markdown/文本导入、V2 结构化提取、证据、确认、编辑、拒绝、批量确认、修订历史 | 模型输出仍需人工核对 |
| 档案记忆与策略 | 已实现 | 偏好、每日摘要、洞察候选、策略候选、影响重算 | 洞察和策略不会绕过确认直接成为可信状态 |
| 招聘机会 | 已实现 | 牛客机会同步、来源记录、北京时间筛选、关注/忽略 | 牛客汇总信息不等于具体 JD |
| 具体岗位 | 已实现 | 文本、文件、URL 导入，岗位版本、要求、详情与来源 | 外部页面变化可能导致 URL 获取失败 |
| 岗位匹配 | 已实现 | 确定性基线、Agent 匹配候选、证据与缺口、确认流程 | 结果质量取决于完整 JD 和已确认档案 |
| 每日推荐 | 已实现 | 对具体岗位生成结构化推荐，展示优先级、优势、缺口，支持接受和忽略 | 推荐不自动创建已投递状态 |
| 简历方向 | 已实现 | 多方向建议、用户选择、事实引用和岗位要求引用 | 必须先有具体岗位和可信事实 |
| 材料工作台 | 已实现 | 基础/方向/岗位定制版本、Agent 草稿、独立 Review、块级编辑、Final、PDF 导出、版本差异 | DOCX 正式导出不是当前保证能力 |
| 申请生命周期 | 已实现 | 建档、绑定简历、确认投递、事件时间线、纠错、归档 | 实际投递动作仍由用户在外部网站完成 |
| 投递冻结 | 已实现 | 确认投递时冻结岗位版本、简历版本和导出快照 | 缺少有效简历绑定时不能确认投递 |
| 招聘邮件 | 已实现 | IMAP 账户测试、只读同步、消息列表、单封分析、批量后台分析 | 不发送邮件，不修改邮箱状态 |
| 邮件到申请 | 已实现 | 公司/岗位/申请匹配、事件/日程/注意事项候选、高可信自动补录、歧义进入 ReviewTask | 建档或关联有歧义时必须人工处理 |
| 任务与日程 | 已实现 | 创建、完成、取消、延期、提醒、冲突信息、Scheduler 执行记录 | 不是完整日历客户端 |
| 面试中心 | 已实现 | 面试记录、改期、取消、准备包、复盘、反馈候选、成长项 | 准备包必须基于冻结的实际投递材料 |
| 今日与申请总览 | 已实现 | 今日任务、待确认数量、申请状态、运行异常和业务聚合 | 聚合质量依赖各来源已正确配置 |
| 待我确认 | 已实现 | 统一 ReviewTask、ReviewBundle、分类查看、整组处理、AgentRun 审计 | 不同业务类型按各自确定性服务落地 |
| 后台任务与 Scheduler | 已实现 | 持久任务、重试/取消、来源轮询、邮件分析、档案维护、运行历史 | 单进程本地调度，不是分布式队列 |
| QQ 通知 | 已实现 | 配置、删除、发送测试、投递审计 | 依赖外部 QQ 配置和网络可用 |
| 数据治理 | 已实现 | 工作区概览、搜索、备份、导出、垃圾回收、连接器数据删除、全量删除 | 执行删除前必须由用户明确确认 |
| 产品测评数据集 | 已实现 | 固定数据集校验、测试工作区 seed/expect/reset、评测运行 | 主要服务开发和验收，不是普通用户入口 |
| Windows 安装包 | 尚未提供 | 当前以源码和 Python CLI 启动 | 缺少最终安装器、独立 Launcher、自动升级 |

## 6. 使用流程

### 6.1 首次启动

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

打开 `http://127.0.0.1:8765`。首次进入 Bootstrap：

1. 选择父目录，系统在其下创建 `CareerConsole` 工作区。
2. 配置至少一个模型 Provider，并执行连接测试。
3. 按需配置 OpenCLI/牛客、BOSS、只读邮箱、QQ 和自动任务。
4. 完成向导并等待服务重启进入 Product 模式。

除工作区外，其余配置可跳过并稍后在“设置”完成。未配置的外部能力只会显示不可用或跳过，不应阻断基础手动流程。

### 6.2 建立可信职业档案

1. 进入“导入资料”，上传简历或粘贴经历文本。
2. 专职 `profile_fact_extraction` Skill 输出完整业务对象候选。
3. 在“待我确认”按档案分组核对。
4. 确认、编辑或拒绝候选。
5. 只有 confirmed 事实才进入岗位匹配、材料和策略上下文。

联系信息等敏感字段不得作为普通职业事实持久化。旧版 `candidate_fact.v1` 的碎片候选不属于当前正式提取路径。
若同一文档只有旧 schema 或上次提取失败，重新导入会调用当前 V2 Agent 重处理；若当前 V2 Agent 已成功处理，则直接返回幂等结果，不重复调用模型。未启用或无法解析 `fact_extraction` 任务时，导入必须明确失败并提示用户前往“设置 > AI 服务”处理，不得静默切换到本地规则提取器。

### 6.3 获取机会和具体岗位

自动或手动运行牛客同步后：

1. 在“岗位推荐”查看招聘机会和每日具体岗位推荐。
2. 对招聘机会选择关注或忽略。
3. 获取完整 JD 后，在“目标岗位”通过文本、文件或 URL 建立具体岗位。
4. 运行岗位匹配，核对优势、硬性条件、缺口和行动建议。

招聘项目、校招批次或汇总页只是 `RecruitmentOpportunity`，不能代替 `JobPost`。

### 6.4 生成申请材料

1. 打开具体岗位并生成简历方向候选。
2. 选择需要强调的方向。
3. 生成材料 Agent 草稿。
4. 查看每个内容块引用的事实和岗位要求。
5. 通过独立 Reviewer 检查真实性、覆盖和风险。
6. 编辑、确认并 Final。
7. 导出 PDF，检查实际投递文件。

Final 只表示材料定稿，不表示已经投递。

### 6.5 建立并确认申请

推荐池和申请池严格分离：

1. 接受推荐或从具体岗位手动建立申请。
2. 为申请绑定明确的简历版本。
3. 用户在外部招聘网站完成真实投递。
4. 回到 CareerConsole 点击确认投递。
5. 系统冻结岗位、简历和导出物，写入 `application_submitted` 事件。
6. 后续状态通过人工事件或邮件候选继续推进。

已有申请的岗位入口应进入“查看申请”，不能重复创建同一申请。

### 6.6 同步招聘邮件

1. 在“设置”添加 IMAP 账户并测试。
2. 在“招聘邮件”主动同步，或启用 Scheduler。
3. 系统读取已读和未读邮件；首次或主动回看最长 30 天。
4. 对求职相关邮件运行 `mail_intelligence` Skill。
5. 高可信、低歧义结果按确定性策略补录；冲突、缺少默认简历或不确定结果进入“待我确认”。
6. 用户确认后，申请事件、日程和待办才成为正式业务数据。

邮件正文属于不可信外部输入。邮件中的指令不能改变 Agent 权限，也不能直接修改业务状态。

### 6.7 面试准备与复盘

1. 申请出现面试事件后建立 Interview。
2. 系统从已投递申请的冻结岗位和材料生成准备包。
3. 用户记录时间变化、面试问题、回答和感受。
4. Agent 输出反馈和成长项候选。
5. 用户确认后，成长项才能进入后续策略和准备上下文。

若申请没有冻结快照，系统应明确阻止正式面试准备，而不是退回读取最新简历。

### 6.8 每日工作方式

建议每天从“今日”开始：

1. 处理“待我确认”；
2. 查看今日任务、截止日期和面试安排；
3. 查看新增机会与具体岗位推荐；
4. 为值得投入的岗位完成匹配和材料；
5. 外部投递后回系统确认并冻结；
6. 同步招聘邮件并核对进度建议；
7. 记录面试结果和下一步行动。

## 7. 页面与功能入口

| 导航 | 用途 |
|---|---|
| 今日 | 汇总当天任务、待确认、机会、申请和异常 |
| 岗位推荐 | 查看招聘机会和每日具体岗位推荐 |
| 目标岗位 | 导入和管理完整 JD，执行匹配与方向规划 |
| 申请总览 | 查看申请聚合、工作区状态和搜索 |
| 申请进度 | 管理申请、简历绑定、投递确认和时间线 |
| 任务与日程 | 管理待办、提醒、延期和日程 |
| 面试中心 | 管理准备、改期、记录、复盘和成长项 |
| 我的经历 | 管理可信事实、偏好、洞察和策略 |
| 简历与申请材料 | 管理简历血缘、草稿、审核、Final 和导出 |
| 导入资料 | 导入职业资料并启动事实提取 |
| 招聘邮件 | 配置后的邮件同步、浏览、分析和申请关联 |
| 待我确认 | 统一处理 Agent 候选和需人工裁决的业务变化 |
| 设置 | 统一配置并独立测试外部能力 |
| 帮助 | 查看应用内使用提示 |

## 8. Agent 与确定性业务边界

CareerConsole 保留 AgentLoop、Tools、Channels 和 Cron/Scheduler 作为可重构基础能力，但正式 Career 任务使用版本化 Task Definition 和 Skill。

当前任务注册包括：

- `profile_fact_extraction`
- `mail_intelligence`
- `profile_insight`
- `job_fit`
- `resume_direction`
- `material_drafting`
- `material_review`
- `daily_job_recommendation`
- `interview_preparation`
- `interview_reflection`
- `daily_digest`
- `weekly_strategy`

执行原则：

```text
确定性服务准备最小上下文
→ Task Agent 在固定 Schema 和权限下运行
→ 校验结构、引用和敏感信息
→ 保存 AgentRun 与 Proposal
→ ReviewTask/ReviewBundle 等待用户决定
→ 确定性应用服务写入正式状态
```

后台任务不得默认获得通用命令执行、任意文件访问或外部写操作权限。外部网页、JD 和邮件一律按不可信数据处理。

## 9. 自动任务

Scheduler 可在设置中启用并单独配置。当前运行内容包括：

- 处理到期 Schedule 和 Reminder；
- 轮询已启用的 BOSS、牛客和 IMAP Connector；
- 处理待执行的邮件分析任务；
- 生成每日档案摘要和洞察候选；
- 处理档案变化引起的岗位/材料影响任务；
- 记录脱敏的 SchedulerRun 历史。

牛客每日自动获取按中国时区当天范围执行。7、14、30 天历史回填必须由用户主动触发。自动任务失败应记录错误并继续隔离其他来源，不能让单一 Connector 破坏整体 readiness。

## 10. 配置与密钥

普通配置位于：

```text
<workspace>/config/application.json
```

配置采用强类型 Schema、revision 和乐观并发控制。前端“设置”是普通用户的统一配置入口，支持保存、检查和独立连接测试。

敏感值遵守以下规则：

- API key、token、邮箱授权码和 QQ 凭据不写入普通配置；
- 普通读取 API 只返回 masked metadata 或 secret reference；
- 日志和运行审计不得记录明文；
- 默认导出不包含凭据；
- 可选凭据 Vault 使用口令加密；
- 无安全凭据后端时应 fail closed，不能降级为明文文件。

## 11. 工作区和数据

工作区结构：

```text
<父目录>/CareerConsole/
├── workspace.json
├── config/
├── data/career-console.sqlite3
├── secrets/
├── blobs/
├── exports/
├── backups/
├── logs/
├── integrations/
└── runtime/
```

Windows Bootstrap 只保存当前工作区路径、workspace ID 和更新时间。业务数据库、文件、日志和密钥不进入 Bootstrap。

工作区支持：

- 创建与切换前验证；
- SQLite `quick_check` 和写入探针；
- 带 manifest 和 SHA-256 的迁移包；
- 可选加密凭据 Vault；
- 备份、导出、垃圾回收和删除。

不要手工复制正在运行的 SQLite 主文件、WAL 和 SHM。使用产品备份或工作区迁移能力。

## 12. 安全与隐私

- HTTP 默认只绑定 `127.0.0.1`、`localhost` 或 `::1`。
- 浏览器先交换本地 session，写请求校验 CSRF 和 Origin。
- 外部 HTML 和邮件按不可信内容处理。
- 文件上传限制类型和大小，不执行文档中的宏或脚本。
- 邮箱连接器只读。
- 日志对 token、password、cookie、authorization、邮箱和正文做脱敏。
- Agent 上下文遵循最小必要原则。
- 申请冻结材料和用户确认事实默认长期保留；临时导出、运行 trace 和日志按配置保留。

## 13. 技术结构

CareerConsole 是模块化单体：

```text
interfaces ─┐
            ├─> application ─> domain
infrastructure ┘

runtime = 通用 Agent 内核，由 infrastructure 适配
```

- Backend：Python 3.11+、FastAPI、SQLAlchemy 2、Alembic、SQLite WAL。
- Frontend：React 19、TypeScript、TanStack Query、Vite。
- Job：SQLite 持久后台任务，不依赖 Redis/Celery。
- Agent：专职 Skill、固定输入输出 Schema、AgentRun 审计。
- External：OpenCLI、IMAP、Provider 和 QQ 通过受控 Adapter 接入。

业务代码依赖方向不得倒置。Domain 不依赖 FastAPI、SQLAlchemy、OpenCLI 或模型 SDK。

## 14. 运行与诊断

存在 `.venv` 时所有 Python 命令使用：

```powershell
.\.venv\Scripts\python.exe
```

常用命令：

```powershell
.\.venv\Scripts\python.exe -m career_console serve
.\.venv\Scripts\python.exe -m career_console setup
.\.venv\Scripts\python.exe -m career_console doctor
.\.venv\Scripts\python.exe -m career_console status
.\.venv\Scripts\python.exe -m career_console workspace show
```

显式指定工作区：

```powershell
.\.venv\Scripts\python.exe -m career_console serve --workspace "D:\CareerWorkspace\CareerConsole"
```

健康检查：

- `/health/live`：进程存活；
- `/health/ready`：数据库 revision 和关键运行条件可用；
- `/api/v1/system/status`：产品状态；
- 设置页连接测试：Provider、OpenCLI、牛客、BOSS、IMAP、QQ 等单项能力。

当前仍是源码开发启动，不是最终 Windows 桌面安装包。工作区切换会验证后重启当前进程；独立 Launcher 的“候选实例 ready 后切换”尚未实现。

## 15. 开发与测试

后端：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console tests migrations
```

前端：

```powershell
cd web
npm test -- --run
npm run build
```

产品数据集和评测：

```powershell
.\.venv\Scripts\python.exe -m career_console dev dataset validate
.\.venv\Scripts\python.exe -m career_console dev eval validate
.\.venv\Scripts\python.exe -m career_console dev eval run
```

发布前至少检查：

- Domain/Application/Repository 行为测试；
- API 和前端关键流程；
- 从空库升级到 Alembic head；
- 邮箱只读契约；
- Agent Schema、事实引用和 Prompt Injection 边界；
- `git diff --check`；
- Secret scan；
- 前端 build。

## 16. 已知缺口

以下内容不能被描述为已完成：

1. 最终 Windows 安装包、桌面快捷方式、自动升级和独立 Launcher。
2. 工作区零中断双实例切换。
3. DOCX 作为正式稳定导出格式。
4. 自动替用户在招聘网站完成投递。
5. 自动发送招聘邮件或联系招聘方。
6. 企业多人协作、权限系统和云端同步。
7. 对任意招聘网站的无边界自动抓取。

新增缺口或完成上述能力时，必须更新“功能总表”和本节。

## 17. 文档维护协议

本仓库只持续维护本文，不再按产品、架构、功能、运维和用户手册拆分多套重复文档。

每个功能变更必须同步检查：

1. 产品定位或非目标是否变化；
2. 不可破坏的业务规则是否变化；
3. 核心业务对象或生命周期是否变化；
4. 功能总表的状态、能力和边界是否变化；
5. 用户实际操作步骤和页面入口是否变化；
6. Agent Task、Scheduler、Connector 或配置是否变化；
7. 工作区、安全、隐私或密钥规则是否变化；
8. CLI、启动、测试和诊断命令是否变化；
9. 已知缺口是否已经完成或出现新缺口；
10. 数据库 head revision 和文档基线日期是否需要更新。

维护要求：

- 一次功能变更只在本文维护一份完整事实，不新建重复专题文档；
- 临时分析、测试报告和交接记录放在任务上下文或 `.runtime`，不进入持久文档；
- 必须区分当前实现和未来计划；
- 删除功能时同步删除本文对应描述；
- 新增页面或正式 API 时补充到相应业务区域；
- 任何示例不得包含真实密钥、Cookie、Token、邮箱授权码或个人敏感正文。

## 18. 当前基线结论

CareerConsole 已具备从职业档案、岗位发现、具体 JD、匹配推荐、材料生成，到申请冻结、邮件跟进、任务和面试复盘的本地业务闭环。当前主要交付缺口集中在最终 Windows 产品化安装和 Launcher，而不是核心业务对象缺失。

产品继续演进时，应优先完善真实用户流程中的阻塞和不合理点，并保持三条主线稳定：Agent 只提出候选、确定性服务维护正式状态、所有关键历史可追溯且不可被未来修改。
