# Nanobot Career 分阶段开发方案

> 文档状态：执行计划初稿<br>
> 依据：[需求分析](./CAREER_REQUIREMENTS_ANALYSIS.md)与[技术实现方案](./TECHNICAL_IMPLEMENTATION_PLAN.md)<br>
> 日期：2026-07-22<br>
> 核心方式：一个大部分完成、实际使用、修复并验收后，再进入下一部分

## 1. 开发方式

本项目不采用“先写完所有后端，再统一做前端和测试”的方式。每个大部分都是一个可以实际运行和使用的纵向模块，同时包含：

```text
Domain/Data Model
→ Application Service
→ API
→ 最小 Web UI
→ 自动化测试
→ 数据迁移/恢复
→ 实际使用验收
→ 问题修复和阶段签收
```

每个部分只有完成以下闭环，才视为完成：

```text
开发完成
→ 自动化检查通过
→ 生成可运行版本
→ 用户实际使用测试
→ 记录反馈和缺陷
→ 修复阻塞问题
→ 回归测试
→ 用户确认通过
→ 打阶段 Tag/记录
→ 开始下一部分
```

### 1.1 总体原则

1. 同一时间只推进一个大部分的主线开发。
2. 每个部分必须有用户能感知和操作的完整结果。
3. 不为后续阶段提前实现大量未验证能力。
4. 数据模型可以提前预留稳定 ID 和审计字段，但不提前创建无用业务表。
5. 每次数据库迁移都必须有备份和从上一阶段升级的测试。
6. 当前 nanobot 框架按影响处理：有用且无冲突的能力保留，必要部分修改，确认冗余后再删除。
7. 未完成的功能通过 feature flag 或不注册入口隐藏，不能把半成品暴露给实际测试。
8. 用户验收发现的真实问题优先于下一部分的新功能。

### 1.2 阶段完成状态

每个部分使用以下状态：

```text
planned
ready
in_development
internal_verification
user_acceptance
stabilizing
accepted
```

`accepted` 是进入下一部分的默认前置条件。用户可以明确允许“带已知非阻塞问题通过”，但问题必须进入 backlog 并注明计划解决阶段。

当前状态：**Part 0–6 = `accepted`，Part 7–9 = `internal_verification`**。用户明确要求先连续完成 Part 8 和 Part 9，再统一进行实际测试与修复；因此 Part 7–9 表示“功能开发和静态构建完成、尚未实际验收”，不伪标为 `accepted`，也不表示已进入发布状态。

## 2. 大部分总览

| 部分 | 名称 | 用户实际获得的能力 | 依赖 |
|---|---|---|---|
| Part 0 | 工程底座与本地应用壳 | 能安装、启动、访问 Web、查看健康状态和后台任务 | 无 |
| Part 1 | 用户档案与事实库 | 导入简历、审查并维护真实经历和偏好 | Part 0 |
| Part 2 | 岗位池与岗位匹配 | 手动导入岗位、查看结构化要求和匹配证据 | Part 1 |
| Part 3 | 简历与申请材料工作台 | 针对岗位生成、审查、修改和导出材料 | Part 2 |
| Part 4 | 申请管理与事件时间线 | 确认投递、绑定材料、维护申请状态和完整时间线 | Part 3 |
| Part 5 | 任务、提醒与 Dashboard | 管理截止时间、待办、提醒和每日概览 | Part 4 |
| Part 6 | OpenCLI 外部工具集成 | 使用已安装的 OpenCLI 登录 BOSS、手动/定时扫描、岗位增量入库 | Part 2、Part 5 |
| Part 7 | 只读 IMAP 邮箱 Connector | 增量读取招聘邮件、提出申请事件和提醒 | Part 4、Part 5 |
| Part 8 | 面试中心与反馈闭环 | 生成面试准备、记录问题和反馈、沉淀改进项 | Part 4、Part 5 |
| Part 9 | 全链路集成、数据治理与发布 | 完整 Demo、备份恢复、导出删除、安装升级 | Part 0–8 |

推荐严格按 Part 0 → 9 执行。Part 6 和 Part 7 技术上可交换，但不建议并行开发，因为两者应共用同一 Connector、SourceEvent、SyncRun 和错误模型。

## 3. 每部分统一执行流程

### 3.1 开始前：Definition of Ready

开始一个部分前必须具备：

- 上一部分已通过用户验收，或用户明确批准提前进入。
- 本部分用户场景和不做范围已确认。
- API、主要实体和迁移影响已经过轻量设计评审。
- 测试样本准备完成，不依赖真实 Secret 才能运行普通测试。
- 已知跨模块风险已记录。

### 3.2 开发过程

每部分内部按以下小步实施：

1. **契约和测试样例**：先定义输入、输出、错误和验收 Fixture。
2. **Domain 和迁移**：实现实体、不变量、Repository 接口和数据库迁移。
3. **Application Service**：实现 Command/Query、事务、幂等和审计。
4. **API**：增加显式路由、DTO、错误映射和 OpenAPI 测试。
5. **最小 Web UI**：提供可操作页面，不等待最终视觉设计。
6. **后台任务/Agent/Connector**：只在本部分需要时接入。
7. **自动化验证**：单元、集成、契约和必要 E2E。
8. **内部演练**：使用脱敏样本完整走一遍用户路径。
9. **生成用户验收版本**：固定版本号、迁移版本和已知问题。

### 3.3 用户实际使用测试

每部分交付一个 `UAT-<part>.md` 或等价记录，包含：

```text
测试版本：
数据库 revision：
操作系统和浏览器：
测试数据说明：

场景 1：
步骤：
预期结果：
实际结果：
结论：通过 / 失败

发现的问题：
严重程度：S0 / S1 / S2 / S3
是否阻塞验收：
```

严重程度：

- `S0`：数据丢失、隐私泄露、Secret 暴露或不可恢复破坏。
- `S1`：核心流程无法完成、程序频繁崩溃或结果严重错误。
- `S2`：主要功能有缺陷，但存在可接受绕行方式。
- `S3`：体验、文案、布局或低影响边缘问题。

### 3.4 阶段通过规则

默认通过条件：

- 没有未解决的 S0、S1。
- S2 已修复，或经用户明确同意进入 backlog。
- 核心验收场景全部通过。
- 数据库升级和备份恢复验证通过。
- 自动化检查全部通过。
- 已知限制已经写入阶段说明。
- 用户明确回复本部分可以进入 `accepted`。

## 4. Part 0：工程底座与本地应用壳

### 4.1 目标

建立后续所有模块共用的运行、数据、测试和 Web 骨架。该部分不实现复杂求职业务，但必须形成一个用户可安装、可启动、可关闭、可诊断的本地应用。

### 4.2 开发范围

工程与运行：

- 建立 `.venv` 和一致的 Python 执行方式。
- 锁定 Python 和前端依赖。
- 配置 Windows、Linux CI。
- 保留现有 nanobot Runtime，建立 `nanobot/career` 分层目录。
- 增加模块依赖检查，禁止 Domain 依赖 Agent/API/SQLAlchemy。

后端：

- FastAPI Career app skeleton。
- `/health/live`、`/health/ready`。
- 统一 Settings、数据目录和运行目录。
- SQLAlchemy Engine、SQLite WAL、Unit of Work。
- Alembic 初始迁移。
- 统一 Problem Details 错误格式。
- correlation ID 和脱敏日志。

后台能力：

- `background_jobs` 最小表和 Worker skeleton。
- 最小 Job 状态查询，不实现业务 Job。
- 应用实例锁和异常重启后的 lease 恢复骨架。

前端：

- React/Vite 项目。
- 应用布局、路由、错误边界。
- 状态页：版本、数据库 revision、健康状态。
- 后台任务列表占位页面，只展示真实 skeleton 数据。

CLI：

- `nanobot career serve` 或最终确认的等价命令。
- `nanobot career doctor`。
- `nanobot career db migrate`。
- `nanobot career db backup`。

### 4.3 不做

- 不实现 Candidate、Job、Application 业务。
- 不接入 OpenCLI、IMAP 或模型任务。
- 不删除现有 Agent、Channel、MCP 等框架能力。
- 不做最终 UI 视觉系统。

### 4.4 自动化测试

- 空数据目录首次启动。
- 重复启动和实例锁。
- 空库迁移到 head。
- 数据库 PRAGMA 验证。
- health/live 和 health/ready。
- Job lease 到期恢复。
- Windows 路径、中文目录和 UTF-8。
- 前端 build、路由和 API 错误展示。

### 4.5 用户验收流程

1. 创建或使用项目 `.venv` 安装依赖。
2. 执行 `doctor`，查看缺失项提示。
3. 启动本地服务。
4. 浏览器打开本地 Web 页面。
5. 查看状态页、版本、数据库和日志目录。
6. 重启服务，确认数据目录和数据库仍可用。
7. 执行数据库备份，确认产生可识别的备份文件。

### 4.6 退出条件

- Windows 本地可重复启动。
- Web 页面可访问且只监听 loopback。
- 空库和升级路径稳定。
- 后续模块可以通过 Domain/Application/API/UI 四层添加功能。

## 5. Part 1：用户档案与事实库

### 5.1 用户价值

用户可以导入自己的简历和资料，系统提取事实候选，用户逐条确认、编辑或拒绝，并形成后续所有岗位匹配和材料生成的可信事实源。

### 5.2 开发范围

数据模型：

- CandidateProfile。
- CandidateFact、FactSource、FactRevision。
- Document、BlobReference。
- ReviewTask 最小实现。
- AgentRun 最小审计记录。

导入能力：

- 粘贴文本。
- TXT、Markdown。
- PDF 和 DOCX 文本解析。
- 文件 SHA-256、去重、原子存储。
- 导入失败和不支持格式的明确错误。

事实工作流：

- 基本信息、教育、实习、工作、项目、技能、奖项、证书。
- 目标岗位、城市、时间、偏好和排斥条件。
- 提取结果默认 `proposed`。
- 用户确认后成为 `confirmed`。
- 修改确认事实产生 revision，不静默覆盖。
- 每条事实可以查看来源文档和证据片段。

Agent：

- `profile_fact_extraction` Task Agent。
- 固定输入输出 Schema。
- 无通用 Exec、Web 和任意文件工具。
- 只处理指定 Document 文本。

Web UI：

- Profile 总览。
- 文档上传和导入进度。
- 按类别展示事实。
- Review 页面支持确认、编辑、拒绝和批量操作。
- 来源和历史版本查看。

### 5.3 现有代码处理

- 保留现有 Agent Provider/Runner 能力并通过 `AgentTaskPort` 调用。
- 现有 CareerStore 不继续扩表。
- 新事实库稳定前不立即删除旧 CareerStore。
- 如果发现真实旧简历数据，提供导入；确认无数据和调用后再清理旧实现。

### 5.4 不做

- 不生成定制简历。
- 不分析岗位。
- 不把 Agent 推断自动确认成事实。
- 不导入 GitHub、在线主页或录音。

### 5.5 自动化测试

- 各文件类型解析。
- 相同文件重复导入。
- 提示注入文本只作为数据。
- Fact 状态转换和 revision。
- 未确认 Fact 不出现在 confirmed 查询。
- Agent Schema 错误和修复失败隔离。
- 文件名、路径穿越、超大文件和异常编码。

### 5.6 用户验收流程

1. 导入一份真实简历。
2. 查看系统提取的事实和证据。
3. 修改一条表达不准确的事实。
4. 拒绝一条错误提取。
5. 批量确认剩余事实。
6. 手动补充一条项目成果和来源说明。
7. 重启应用，确认事实、来源和历史仍存在。
8. 再次导入同一文件，确认不会无提示地产生重复事实。

### 5.7 退出条件

- 用户能够建立可信、可编辑、可追溯的事实库。
- 后续模块只能读取 confirmed Fact 生成正式内容。
- 真实简历导入体验达到可持续使用水平。

## 6. Part 2：岗位池与岗位匹配

### 6.1 用户价值

用户可以先不依赖自动抓取，直接粘贴或上传岗位信息，系统形成统一岗位记录，提取要求，并基于事实库给出可解释匹配分析。

### 6.2 开发范围

数据模型：

- Company、CompanyAlias。
- JobPost、JobPostVersion、JobPostSource。
- JobRequirement。
- JobMatchAnalysis、JobMatchEvidence。

岗位导入：

- 粘贴岗位正文。
- 粘贴 URL 并在用户明确触发时使用受控 Web Fetch。
- 上传 TXT、Markdown、PDF。
- 保存原始内容、来源、发现时间和内容哈希。
- 相同岗位更新形成新版本。

岗位要求：

- 职位、公司、地点、类型、招聘对象、截止时间。
- 硬性条件和优先条件。
- 技能、经验、学历、工作方式等分类。
- 原文证据片段。

匹配分析：

- 先执行确定性硬门槛检查。
- Agent 为每项要求关联 Candidate Fact 或标记 gap。
- 确定性代码计算维度和优先级。
- 展示优势、缺口、风险、准备成本和建议。
- 不只显示一个总分。

Web UI：

- Job Pool 列表、筛选和处理状态。
- Job Detail、原文和版本。
- Requirement–Evidence 对照。
- 重新分析和分析历史。

### 6.3 不做

- 不自动扫描招聘网站。
- 不创建申请记录。
- 不生成材料。
- 不自动合并模糊的跨来源岗位。

### 6.4 自动化测试

- 岗位版本哈希和幂等导入。
- 公司/岗位精确去重。
- 截止时间和时区。
- 硬门槛 veto。
- Match Evidence 必须引用有效 Fact ID。
- Agent 幻觉 Fact 引用被拒绝。
- 相同岗位内容变化形成版本而非覆盖。

### 6.5 用户验收流程

1. 粘贴一个真实岗位 JD。
2. 检查公司、职位、地点、截止时间和要求提取结果。
3. 查看匹配分析中的每条事实证据。
4. 确认缺口没有被虚构经历掩盖。
5. 导入同一岗位，验证去重。
6. 修改岗位正文后再次导入，验证产生新版本。
7. 导入一个明显不符合硬性要求的岗位，确认系统给出明确原因。

### 6.6 退出条件

- 用户能用岗位池长期保存和比较岗位。
- 匹配结论可解释、可追溯且不虚构。
- JobPost 模型可以承接后续 OpenCLI 来源。

## 7. Part 3：简历与申请材料工作台

### 7.1 用户价值

用户选择一个岗位后，可以使用确认事实生成针对性材料，经过 Reviewer 审查和用户修改，最终导出一份可以实际投递的材料。

### 7.2 开发范围

数据模型：

- Resume、ResumeVersion。
- MaterialDraft、MaterialReview、ReviewFinding。
- MaterialExport。
- FactSnapshot/FactReference。

工作流：

```text
选择岗位版本
→ 选择基础简历
→ 锁定 confirmed Fact 集合
→ Drafter
→ 事实引用校验
→ Reviewer
→ 修订
→ 用户编辑
→ 导出验证
→ 用户确认 final
```

材料范围：

- P0 优先完成定制简历。
- 求职信作为同一部分的第二个小切片；如果影响验收周期，可在简历通过后单独启用。
- 自我介绍先作为文本输出，不作为独立复杂编辑器。

质量检查：

- 不允许引用未确认事实。
- 不允许未解析占位符进入 final。
- 岗位关键词覆盖与真实 gap 区分。
- PDF 页数、渲染和文本层检查。
- 导出文件内容哈希。

Web UI：

- Materials 列表和版本树。
- 基础简历系列的新建、选择与跨材料复用。
- 岗位关联。
- Draft/Review/修订对比。
- 事实引用侧栏。
- 用户编辑和 Final 确认。
- PDF 下载和验证结果。

### 7.3 借鉴 ai-job-search

- 单一事实来源。
- Drafter–Reviewer。
- PDF 渲染和 ATS 文本层检查。
- 缺口诚实表达。
- Final 文件快照。

不复制其依赖特定 Agent 命令和 Markdown/文件作为业务状态的方式。

### 7.4 不做

- 不自动投递。
- 不批量生成大量岗位材料。
- P0 不保证 DOCX 导出；PDF 是首要验收格式。
- 不实现复杂模板市场。

### 7.5 自动化测试

- 未确认 Fact 无法进入 Draft/Final。
- 无效 Fact ID 和 unsupported claim 拦截。
- Reviewer 输出 Schema。
- 版本父子关系和不可变 Final。
- PDF 生成、页数、文本层和所需文本。
- 用户编辑后的版本和审计。
- 基础简历系列复用和材料计数。

### 7.6 用户验收流程

1. 从岗位池选择一个真实岗位。
2. 选择基础简历并生成定制草稿。
3. 检查每个重点表达对应的事实来源。
4. 查看 Reviewer 问题和修改建议。
5. 手动修改一处文本并重新验证。
6. 确认 Final，导出 PDF。
7. 用 PDF 阅读器检查布局，并复制文本检查 ATS 可读性。
8. 再次编辑基础简历，确认已 Final 的版本不发生变化。

### 7.7 退出条件

- 至少一份真实岗位的材料达到用户可实际投递标准。
- Drafter、Reviewer、用户编辑和导出形成完整版本链。
- Final 材料中的事实全部可追溯。

## 8. Part 4：申请管理与事件时间线

### 8.1 用户价值

用户可以确认已经投递某岗位，绑定实际材料，并通过时间线管理后续测评、笔试、面试、Offer 和拒绝等事件。

### 8.2 开发范围

数据模型：

- Application。
- ApplicationEvent。
- ApplicationEventProposal。
- ApplicationMaterialSnapshot。
- ReviewTask 完整业务类型和 Resolution。

状态机：

- discovered、preparing_materials、ready_to_apply、submitted。
- application_confirmed、assessment、written_test、interview。
- offer、rejected、withdrawn、archived。
- 更正和 supersede 事件。

核心命令：

- CreateApplication。
- ConfirmApplicationSubmitted。
- ProposeApplicationEvent。
- Confirm/RejectApplicationEvent。
- CorrectApplicationEvent。
- ArchiveApplication。

Web UI：

- Application Board。
- Application Detail。
- 完整时间线。
- 岗位版本和实际材料快照。
- Review Center：确认/拒绝事件候选。
- 手动添加事件和更正。

### 8.3 不做

- 不自动从邮件更新状态。
- 不自动投递或联系招聘方。
- 不做完整漏斗分析。

### 8.4 自动化测试

- 合法/非法状态转换。
- Event 不可变和更正语义。
- current_status 投影重建。
- Final Material Snapshot 不受后续修改影响。
- 重复确认 Command 幂等。
- 并发 expectedVersion 冲突。
- ReviewTask 处理审计。

### 8.5 用户验收流程

1. 从一个已 Final 材料的岗位创建申请。
2. 确认已经投递并选择实际材料。
3. 查看 submitted 时间线事件和快照。
4. 手动添加网申确认、笔试和面试事件。
5. 尝试非法状态转换，确认系统拒绝并解释。
6. 更正一个错误时间，确认历史仍可追溯。
7. 查看 Board 中状态变化。

### 8.6 退出条件

- 一次真实申请可以被完整记录。
- 状态由事件推导，不允许直接篡改。
- 后续邮件 Connector 有稳定的 EventProposal 和 ReviewTask 落点。

## 9. Part 5：任务、提醒与 Dashboard

### 9.1 用户价值

用户可以看到今天需要做什么、哪些岗位即将截止、什么时候笔试或面试，并获得可靠的本地提醒。

### 9.2 开发范围

数据模型：

- Task。
- Reminder。
- Schedule。
- Notification。
- OutboxEvent 完整实现。

后台系统：

- Job lease、重试、幂等和取消。
- Scheduler cron/interval/once。
- Outbox Dispatcher。
- SSE 轻量进度和变化通知。

业务能力：

- 岗位截止提醒。
- 投递计划。
- 笔试/面试多阶段提醒。
- 跟进任务。
- 任务完成、延后、取消。
- 时间冲突基础检测。

Web UI：

- Dashboard：今日待办、临近截止、即将面试、待确认事项。
- Task 列表和日历式时间视图。
- Reminder 设置。
- Background Job 状态和失败重试。

### 9.3 不做

- 不发送邮件或短信。
- 桌面系统通知可作为小切片，不能阻塞核心验收。
- 不做复杂第三方日历双向同步。

### 9.4 自动化测试

- 不同时区和夏令时。
- Job 崩溃、lease 过期和重试。
- 相同 Outbox 重放不重复创建 Reminder。
- 过期任务和 missed schedule 补偿。
- Reminder 完成/取消。
- SSE 只发送轻量引用。

### 9.5 用户验收流程

1. 给真实岗位设置截止时间和投递计划。
2. 给申请添加未来笔试/面试时间。
3. 检查 Dashboard 和任务列表。
4. 创建提前一天和提前一小时的提醒。
5. 重启应用，确认 Schedule 和 Job 不丢失。
6. 手动将系统时间测试到提醒窗口或使用测试时钟。
7. 完成、延后和取消任务。

### 9.6 退出条件

- Dashboard 可以作为用户每日打开的主页。
- Scheduler 和 Job 经重启、重试后不重复产生业务结果。
- Connector 可以复用统一 Job/Outbox/Schedule 基础。

## 10. Part 6：OpenCLI 外部工具集成

### 10.1 用户价值

用户可以在本地浏览器登录 BOSS，通过手动刷新或每天两次定时扫描发现新岗位，岗位自动进入现有 Job Pool。

### 10.2 开发范围

统一 Connector 基础：

- ConnectorConfig、ConnectorHealth。
- SourceEvent、SyncCursor、SyncRun。
- Connector 错误分类和状态。
- Schema validation、quarantine 和重放。

OpenCLI：

- OpenCLI 是本项目使用的外部应用；不在本项目内开发、修改或维护 OpenCLI 本体及其通用 Adapter。
- 本项目只实现 Career 侧的受控调用、输出校验和业务数据映射。

- `OpenCliProcessRunner`。
- executable/version/Node/Bridge doctor。
- Career Adapter Descriptor。
- BOSS status、login、latest、detail 映射。
- 一个 Browser Profile alias。
- foreground 登录、background read scan。
- OpenCLI exit code 映射。
- 命令 allowlist，禁止 BOSS 写操作。

岗位处理：

- SourceEvent 到 JobPost/Version。
- 外部 ID、URL 和内容哈希去重。
- 登录失效、空结果、Schema 错误和 Adapter 退化。
- 手动扫描和 09:00/18:00 可配置 Schedule。

Web UI：

- Data Sources 列表。
- BOSS 设置、Profile、健康状态。
- 登录和重新登录。
- 手动刷新、最近 SyncRun 和统计。
- 错误恢复建议。

### 10.3 不做

- 不支持多个招聘网站。
- 不支持多个 Browser Profile。
- 不执行 greet、send、exchange、invite、mark 或自动投递。
- 不实现 Adapter 自动生成、发布或回滚。

### 10.4 自动化测试

- Fake Process Runner 的全部退出码。
- argv 参数数组和禁止 `shell=True`。
- 写命令无法通过 allowlist。
- 相同扫描重复执行幂等。
- 岗位更新形成版本。
- 登录失效只影响该 Connector。
- Schema 错误不写正式 JobPost。
- Profile 并发锁。

### 10.5 用户验收流程

1. 运行 OpenCLI/Browser Bridge doctor。
2. 选择浏览器 Profile。
3. 打开登录流程并由用户人工登录 BOSS。
4. 执行 status，确认 authenticated。
5. 手动扫描一个真实关键词。
6. 查看新增岗位和详情是否准确。
7. 再次扫描，确认不重复。
8. 模拟或等待岗位变化，检查版本。
9. 退出登录或使用无登录 Profile，验证 requires_login。
10. 验证其他模块仍正常工作。

### 10.6 退出条件

- 一个真实 BOSS 来源可以稳定完成只读采集。
- 失败可诊断、可恢复且不污染 Job Pool。
- 定时扫描不依赖 Agent 自由决定执行命令。

## 11. Part 7：只读 IMAP 邮箱 Connector

### 11.1 用户价值

用户可以连接一个邮箱，系统只读同步招聘邮件，识别笔试、面试、拒信和 Offer，并提出申请事件和提醒供用户确认。

### 11.2 开发范围

Secret：

- OS Keyring SecretStore。
- 配置和数据库只保存 `secret_ref`。
- 更新、删除和脱敏显示。

IMAP：

- 一个账户、一个 INBOX。
- TLS、readonly select。
- IMAP 连接和读取采用 30 秒 socket timeout；UIDVALIDITY 缺失时拒绝推进 Cursor。
- UID、UIDVALIDITY、last committed UID。
- 首次同步可选最近 7/14/30 天，硬上限为 30 天；更早进度由用户在申请看板手动录入。
- 十分钟增量轮询。
- Header-first、BODY.PEEK。
- multipart、字符集、HTML 转文本。
- 单封邮件正文读取上限 10 MiB，超限时只保存 Header 和去重信息。
- 每轮最多处理 500 封，游标只推进到实际处理的最后 UID，积压由后续轮询续传。
- MIME 文本提取和附件元数据数量有固定资源上限，畸形字符集或非法时间不阻塞游标。
- 附件只保存元数据。

分类和匹配：

- 规则初筛。
- 招聘相关/可能相关/无关/未知。
- 笔试、面试、调整、拒信、Offer。
- 公司、岗位、申请编号、时间、链接提取。
- 精确匹配、候选排序、ReviewTask。
- 用户确认后写 ApplicationEvent 和 Reminder。

Web UI：

- 邮箱设置和连接测试。
- 首次同步范围。
- 同步进度、Cursor 和错误。
- Message Center。
- 邮件事件 Proposal 和证据确认；自动匹配不足时可由用户选择现有申请后生成待审 Proposal。

### 11.3 只读红线

- 不标记已读。
- 不 STORE、MOVE、COPY、DELETE、EXPUNGE。
- 不 SMTP。
- 不执行邮件正文指令。
- 不把全部邮箱正文发送给模型。

### 11.4 不做

- 不支持 OAuth。
- 不支持 IMAP IDLE。
- 不支持多邮箱统一收件箱。
- 不自动修改申请状态。
- 不下载和分析完整附件。
- 不回复或发送邮件。

### 11.5 自动化测试

- Fake IMAP 断言无修改命令。
- 首次同步、增量同步和断点恢复。
- UIDVALIDITY 变化对账。
- 重复 Message-ID 和 UID 幂等。
- 邮件编码和 multipart Fixture。
- Prompt injection 邮件。
- 无关邮件正文不长期保存。
- Secret 不出现在 API、日志和导出中。

### 11.6 用户验收流程

验收前建议使用专门测试邮箱，再使用个人邮箱进行有限范围验证。

1. 在 OS Keyring 保存授权码。
2. 配置一个 IMAP 账户并测试连接。
3. 选择较短历史范围完成首次同步。
4. 查看识别出的招聘邮件和无关邮件处理情况。
5. 确认邮箱中邮件已读状态没有变化。
6. 将邮件关联到真实申请并确认事件。
7. 检查时间线和 Reminder。
8. 收到或发送到测试邮箱一封新招聘样例邮件。
9. 等待增量轮询，确认只处理一次。
10. 重启应用，确认 Cursor 正确继续。

### 11.7 退出条件

- 协议和实际邮箱测试均证明严格只读。
- 招聘邮件可以形成有证据的 Proposal。
- 用户确认前 Application 状态不会变化。
- Secret 和无关邮件隐私满足要求。

## 12. Part 8：面试中心与反馈闭环

### 12.1 用户价值

用户可以根据实际投递岗位和材料准备面试，记录面试问题和反馈，并让系统把重复弱点用于下一次准备。

### 12.2 开发范围

数据模型：

- Interview、InterviewRecord。
- InterviewQuestion、InterviewFeedback。
- ImprovementItem/Weakness linkage。

面试准备：

- 使用 JobPostVersion。
- 使用实际 ApplicationMaterialSnapshot。
- 使用 confirmed Fact。
- 使用前一轮反馈和历史弱点。
- 按 phone/technical/case/final 生成不同准备包。
- STAR 案例映射和诚实 gap bridge。
- 生成问题、复习点、提问和检查清单。

面试复盘：

- 手动填写面试问题、回答摘要、自评和结果。
- Agent 提取问题类别、回答缺口和改进建议。
- 用户确认后形成 Feedback/Improvement Item。
- 下一次同类岗位准备时检索历史弱点。

Web UI：

- Interview Center 日程。
- 准备包。
- 面试记录表单。
- 问题和反馈列表。
- 重复弱点与改进任务。

### 12.3 不做

- P0 不做实时录音。
- 不自动监听麦克风。
- 不做面试中的实时提示。
- 录音上传和转写放入后续增强小切片，需另行确认合规和模型方案。

### 12.4 自动化测试

- 准备包只引用实际材料和 confirmed Fact。
- 不同轮次上下文差异。
- 历史反馈优先级。
- 未确认复盘建议不进入长期弱点。
- Application/Interview 关联和时间线。
- 敏感反馈日志脱敏。

### 12.5 用户验收流程

1. 选择一条真实面试阶段申请。
2. 生成准备包。
3. 检查内容是否使用了实际投递材料，而不是最新基础简历。
4. 检查技术缺口和 STAR 建议是否真实。
5. 手动记录一次模拟或真实面试。
6. 查看问题提取和改进建议。
7. 确认部分建议，拒绝不准确建议。
8. 为下一次同类面试生成准备包，验证历史反馈被正确使用。

### 12.6 退出条件

- 面试前准备和面试后复盘形成闭环。
- 历史反馈可复用但必须经过确认。
- 不出现超出用户事实和实际材料的回答建议。

## 13. Part 9：全链路集成、数据治理与发布

### 13.1 用户价值

把前面独立通过验收的模块组合成一个可以长期日常使用的本地产品，并具备备份、恢复、升级、数据删除和故障诊断能力。

### 13.2 开发范围

全链路：

- Dashboard 申请漏斗和最近变化。
- 每日/每周求职简报。
- Connector、Application、Reminder 和 Interview 联动检查。
- 跨模块搜索和实体跳转。
- Review Center 统一队列。

数据治理：

- 全量备份和恢复。
- 数据导出。
- 删除单一 Connector 数据。
- 删除全部个人数据。
- Blob 垃圾回收。
- 日志和 Agent trace 保留策略。

工程和发布：

- Python wheel 包含 Web 静态资源和 migrations。
- setup/doctor 完整向导。
- 从每个已发布阶段数据库升级。
- Windows 安装说明和可选安装器评估。
- 性能、稳定性和长时间运行测试。
- 安全检查和依赖漏洞扫描。
- 根据实际使用评估现有 nanobot 冗余模块；无影响且有扩展价值的保留，确认负担项再删除。

### 13.3 完整验收场景

1. 从全新数据目录安装和启动。
2. 导入真实简历并确认事实。
3. 通过 OpenCLI 发现岗位。
4. 查看岗位匹配并生成材料。
5. 确认投递和材料快照。
6. 通过 IMAP 收到流程邮件。
7. 确认事件和提醒。
8. 生成面试准备、记录反馈。
9. 重启应用并检查状态恢复。
10. 备份数据库和文件。
11. 在独立临时数据目录恢复备份。
12. 导出用户数据。
13. 验证删除流程不会留下敏感正文和 Secret。

### 13.4 非功能验收

- Dashboard 常规查询达到目标响应时间。
- 连续运行和定时同步没有重复数据。
- 单个 Connector 持续失败不影响其他模块。
- 数据库 migration、备份和恢复通过。
- 日志无 Secret、Cookie、完整邮件或简历正文。
- localhost 鉴权、CSRF、CORS、CSP 检查通过。
- Windows 主平台通过，Linux 基础兼容测试通过。

### 13.5 退出条件

- 完整 Demo 闭环通过实际使用测试。
- 所有 S0/S1 清零。
- 安装、升级、备份、恢复和删除均有文档并实际验证。
- 可以发布第一个长期使用版本。

## 14. 部分之间的数据和接口冻结原则

每部分通过验收后，不代表相关代码永远不能改变，而是以下内容进入受控变更：

- 已发布数据库迁移不可修改，只能追加。
- 已被下一部分使用的 Domain 行为需要回归测试。
- API breaking change 必须同步前端并记录。
- 状态 Enum 和事件类型不能静默改名。
- 用户数据语义变化必须提供迁移。
- 实际使用中发现错误可以修正，但必须避免为了下一部分方便破坏已验收流程。

## 15. 跨部分 Backlog 管理

问题分为：

```text
current-part-blocker    当前部分验收前必须解决
current-part-followup   当前部分可接受改进
future-part-dependency  由后续模块自然解决
product-idea            尚未进入已确认范围
technical-debt          不影响当前功能但需跟踪
```

每个问题至少记录：来源部分、复现步骤、影响、优先级、目标部分和是否涉及数据迁移。

不得把 S0/S1 标记为普通 technical debt 后继续推进。

## 16. 每部分交付物

每个 Part 最少交付：

```text
代码和数据库 migration
自动化测试
API/OpenAPI 更新
最小 Web UI
用户操作说明
UAT 验收脚本
已知问题列表
数据备份/恢复说明
阶段变更日志
下一部分依赖说明
```

建议 Tag：

```text
part-0-foundation-accepted
part-1-profile-accepted
part-2-jobs-accepted
...
part-9-release-accepted
```

是否实际创建 Git Tag 由用户在每部分验收时确认，开发过程不自动对外发布。

## 17. Part 0 开始前需要确认

开始编码前只需确认以下执行级选择：

1. Career Web 主 Server 使用 FastAPI。
2. 前端使用 React + TypeScript + Vite。
3. Career 数据库使用 SQLite + SQLAlchemy + Alembic。
4. 继续在现有 `nanobot/` 包内增加 `career` 分层，不整体重写 Agent 框架。
5. 每部分必须经过用户实际使用验收后再推进。
6. P0 招聘网站为 BOSS，邮箱为一个标准 IMAP 账户。
7. Part 3 首要导出格式为 PDF；DOCX 和录音转写不阻塞第一轮闭环。

## 18. 推荐的当前下一步

Part 0–9 的计划内功能现已全部进入实现完成状态，下一步按照用户指令统一进入实际测试与修复。测试顺序为：隔离临时数据目录中的迁移与 API 自动化测试、Part 1–9 分模块 Web 验收、真实只读邮箱和外部 OpenCLI 联调、完整备份恢复与删除演练、长时间运行及发布检查。外部 OpenCLI 仍只消费，不在本项目开发；目标网站专用 CLI 也必须在用户明确目标网站与范围后另立项目开发。
