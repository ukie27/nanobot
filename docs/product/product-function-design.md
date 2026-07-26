# CareerConsole 产品功能设计与落地方案

> 文档状态：Product redesign baseline  
> 日期：2026-07-26  
> 适用范围：`CareerConsole` 本地单用户求职工作台
> 依据：归档需求分析、[技术实现方案](../architecture/technical-implementation-plan.md)、[开发计划](development-plan.md)、当前 Part 0–9 实现及本轮产品讨论

## 1. 结论

CareerConsole 不应被设计成若干独立 AI 功能的集合，也不应以聊天记录或通用 Agent Memory 作为核心状态。产品的核心是一套本地、可追溯、持续演进的求职业务系统：

```text
用户业务档案
   ↓
机会发现 → 具体岗位 → 匹配判断 → 简历策略与材料 → 用户投递
                                                   ↓
邮件证据 → 申请档案 → 事件时间线 → 日程/待办 → 面试准备与复盘
                                                   ↓
                         结果、反馈和用户确认的洞察回流业务档案
```

最终产品由八个主要业务中心组成：

1. **职业档案中心**：维护用户事实、偏好、能力证据、成长项和策略快照。
2. **机会与岗位中心**：接收牛客/OpenCLI、手动导入等来源，区分招聘机会和具体岗位。
3. **岗位决策中心**：分析岗位要求、用户匹配、硬性缺口、投入产出和行动建议。
4. **材料工作台**：管理基础简历、方向简历和岗位定制版本，执行 Drafter–Reviewer 流程。
5. **申请进度中心**：以申请档案和事件时间线管理全部已投递岗位。
6. **邮件智能中心**：只读同步已读和未读邮件，由受控 Agent 提取结构化进度、日程、待办和注意事项。
7. **日程与行动中心**：统一管理截止日期、投递计划、笔试、面试、提醒和时间冲突。
8. **面试与成长中心**：生成准备包、记录复盘、沉淀经用户确认的长期改进项。

此外有三个横向能力：

- **今日与审查中心**：聚合今天的新机会、待办、待确认 Agent 结论和异常。
- **数据来源与运行中心**：管理 OpenCLI、IMAP、同步记录、Agent Run 和系统健康。
- **数据治理**：负责备份、导出、删除、保留策略、隐私和审计。

## 2. 产品定位与边界

### 2.1 产品定位

面向校招、秋招、春招及早期职业用户的本地个人求职操作系统。它帮助用户长期维护可信职业资料，发现并判断机会，为不同岗位生成真实且有针对性的材料，记录全部申请进度，并把邮件、日程和面试反馈转化为可行动的业务数据。

### 2.2 产品不是什么

- 不是通用聊天机器人。
- 不是用一段“大模型长期记忆”代替数据库的个人助理。
- 不是自动批量投递或自动联系招聘方的机器人。
- 不是全网无边界抓取器。
- 不是完整邮件客户端。
- 不是企业 ATS，也不面向多人协作。
- 不允许外部网页或邮件直接改变正式业务状态。

### 2.3 核心产品不变量

1. **事实不虚构**：正式材料只能使用用户确认的事实。
2. **证据与结论分离**：邮件、岗位、文档是证据；Agent 输出是推断或建议。
3. **关键变化需确认**：新增事实、投递、申请状态、Offer、长期弱点等必须由用户确认。
4. **状态由事件形成**：申请进度必须有完整事件时间线，不能只覆盖一个状态字段。
5. **历史不可被未来修改**：实际投递材料和岗位版本必须冻结为快照。
6. **自动化有边界**：自动采集、分析和提出建议；不自动投递、不发消息、不接受 Offer。
7. **Agent 结构化输出**：后台 Agent 必须使用固定输入、固定 Schema、无工具或最小工具权限。

## 3. 核心业务对象

### 3.1 对象关系

```text
CandidateProfile
├── CandidateFact（已确认事实）
├── CareerPreference（显式求职偏好）
├── CapabilityEvidence / STARCase（能力证据）
├── ProfileInsightProposal（Agent 洞察候选）
├── ImprovementItem（已确认成长项）
└── StrategySnapshot（版本化求职策略）

RecruitmentOpportunity（公司招聘项目/校招批次）
└── JobPost（具体岗位）
    ├── JobPostVersion
    ├── JobRequirement
    ├── JobMatchAnalysis
    └── MaterialWorkflow
        └── MaterialVersion

Application（一次实际申请）
├── SubmittedMaterialSnapshot
├── ApplicationEvent
├── MailEvidence / EventProposal
├── Task / Schedule / Reminder
└── Interview
    ├── PreparationPack
    ├── InterviewRecord
    └── FeedbackProposal → ImprovementItem
```

### 3.2 “业务档案”不是通用长期记忆

职业档案必须保存为结构化、版本化的业务数据，不写入 CareerConsole 通用 `memory/MEMORY.md`，也不依赖聊天历史。建议分为五层：

| 层级 | 内容 | 是否可由 Agent 自动确认 |
|---|---|---|
| 原始证据 | 简历、用户输入、岗位、邮件、面试复盘 | 否 |
| 可信事实 | 教育、经历、项目、技能、证书、真实成果 | 否，必须用户确认 |
| 显式偏好 | 城市、岗位方向、行业、薪资、排斥条件 | 否，必须用户设置或确认 |
| 业务洞察 | 优势、重复缺口、成功模式、风险、偏好变化 | 否，Agent 只能提出候选 |
| 策略快照 | 当前求职方向、优先级、阶段目标和行动计划 | 否，用户确认后形成版本 |

这种结构允许 Agent 持续利用历史信息，同时避免模型总结覆盖真实事实。

## 4. 主要用户场景

### 4.1 首次建立职业档案

1. 用户导入简历、项目资料和已有经历。
2. Agent 提取事实候选并引用原文证据。
3. 用户确认、修改或拒绝。
4. 用户补充求职方向、城市、行业、时间和限制条件。
5. 系统生成第一版“职业画像与求职策略”，仍需用户确认。

结果：形成后续匹配、材料和面试准备可依赖的可信数据集。

### 4.2 每日发现新机会

1. 每天固定时间通过 OpenCLI 牛客插件获取北京时间当天收录的校招项目。
2. 写入 `RecruitmentOpportunity`，完成来源去重和版本化。
3. 根据用户显式偏好做低成本初筛。
4. 在今日页面展示“新机会”，用户选择关注、忽略或进一步查看。
5. 获得具体 JD 后建立 `JobPost`，再执行完整 Agent 匹配。

牛客校招日程是机会发现入口，不等价于具体岗位 JD，不能直接据此生成岗位定制简历。

### 4.3 针对岗位选择简历方向

1. 用户打开具体岗位。
2. 系统展示要求—事实—缺口分析。
3. Agent 基于同一组真实事实给出 2–4 个材料方向，例如：
   - 工程落地与稳定性方向；
   - 算法/数据能力方向；
   - 业务理解与跨团队协作方向。
4. 每个方向展示覆盖要求、重点事实、弱化内容、风险和预期页数。
5. 用户选择方向后，Drafter 生成草稿，Reviewer 独立检查。
6. 用户编辑、确认并导出实际投递版本。

### 4.4 用户完成投递

1. 用户在外部网站完成真实投递。
2. 回到系统点击“确认已投递”。
3. 系统冻结具体岗位版本和实际材料版本。
4. 创建 Application 和 `application_submitted` 事件。
5. 创建后续跟进任务并等待邮件证据。

### 4.5 邮件建立和维护投递档案

1. IMAP 按日期/UID 读取 INBOX，不区分已读和未读。
2. Agent 判断求职相关性并输出 `mail_intelligence.v1`。
3. 系统提取公司、岗位、申请编号、事件、日程、待办和注意事项。
4. 匹配已有 Application；若没有，提出“从邮件建立投递档案”的建议。
5. 用户确认后写入正式事件时间线，创建或更新日程任务。
6. 在申请详情中永久保留邮件证据引用和 Agent 结论版本。

### 4.6 面试准备与复盘

1. 确认面试事件后自动建立 Interview 和准备任务。
2. Agent 读取冻结岗位、实际投递材料、可信事实和已确认历史改进项。
3. 生成准备包、重点问题、回答证据、Gap Bridge 和检查清单。
4. 面试后用户记录问题、回答和感受。
5. Agent 提出表现洞察与改进项。
6. 用户确认后将其沉淀到业务档案，在下一次同类岗位中使用。

## 5. 功能一：职业档案与业务记忆

### 5.1 用户价值

让系统长期知道“用户真实做过什么、想找什么、在哪些方面持续进步”，同时保证每个结论可查看来源、可撤销、可修订。

### 5.2 功能组成

- 资料导入：PDF、DOCX、Markdown、文本和手动输入。
- 事实审查：确认、编辑、拒绝、合并、标记失效。
- 求职偏好：岗位族、城市、行业、规模、薪资、时间、工作方式。
- 能力证据：项目、实习、成果、量化指标、STAR 案例。
- 业务洞察：优势、缺口、稳定偏好、结果模式。
- 成长项：来自面试、岗位缺口和用户计划的长期任务。
- 策略快照：当前阶段的目标、优先级、投递节奏和材料策略。

### 5.3 Agent 如何持续维护

不采用“每天把全部用户数据重新总结一次”的覆盖式方案，而采用事件驱动加周期归纳：

```text
新文档/用户修改/投递结果/面试复盘
→ 产生业务事件
→ 对相关局部运行 Agent
→ 创建 Fact/Insight/Preference Proposal
→ 用户确认
→ 更新可信档案版本
```

周期任务分为：

- **每日整理**：只处理当天新增证据、未完成任务和待审查项，生成 `DailyDigest`，不改变事实。
- **每周策略回顾**：聚合近 7 天的投递、回复、面试和失败原因，生成 `StrategySnapshotProposal`。
- **按需重建**：用户修改重要偏好或大量事实后，重新计算受影响的岗位匹配和材料建议。

### 5.4 数据模型改造

保留现有 `candidate_profiles`、`candidate_facts`、`fact_sources` 和 revision，引入：

- `career_preferences`：显式偏好和限制，带版本及确认状态。
- `profile_insight_proposals`：Agent 洞察候选、证据引用、置信度和状态。
- `strategy_snapshots`：版本化策略，不覆盖历史。
- `daily_digests`：可重建的当日摘要，不作为事实源。
- `profile_change_events`：档案变化事件和影响范围。

### 5.5 Agent Task Schema

- `candidate_fact.v2`：事实、证据、时间范围、冲突候选。
- `profile_insight.v1`：洞察类型、结论、证据 ID、反例、置信度。
- `career_strategy.v1`：目标方向、优先级、约束、行动、评估周期。
- `daily_digest.v1`：当天变化、待确认、风险和明日行动。

### 5.6 页面设计

职业档案页面采用四个 Tab：

1. 事实与证据；
2. 求职偏好；
3. 优势与成长项；
4. 策略历史。

顶部显示档案完整度、待确认数量、最后维护时间和受影响岗位数量。

### 5.7 当前实现与改造

当前已有文档导入、事实候选、来源、确认/拒绝/编辑和版本历史。需要补齐偏好实体、洞察候选、策略快照、影响重算和真正的 Agent 提取默认路径；不能把确定性占位提取器当成最终智能能力。

## 6. 功能二：机会发现与岗位池

### 6.1 用户价值

持续获得新招聘机会，但不把大量噪声直接推给用户；从“公司开始校招”逐步落到“值得投递的具体岗位”。

### 6.2 两级对象

#### RecruitmentOpportunity

用于牛客校招日程等公司级信息：公司、招聘批次、开始/截止时间、城市、岗位方向、公告和投递入口。

#### JobPost

用于具体 JD：岗位名称、职责、要求、地点、工作方式、具体申请地址和版本。

一个 Opportunity 可以关联多个 JobPost。没有具体 JD 时只允许做方向级初筛，不进行完整岗位打分和岗位定制材料生成。

### 6.3 OpenCLI 的产品位置

OpenCLI 是外部采集基础设施，不是独立业务功能：

```text
牛客 OpenCLI 插件
→ SourceEvent
→ RecruitmentOpportunity
→ 偏好初筛
→ 今日新机会
→ 用户关注/忽略
→ 获取或导入具体 JD
→ JobPost
```

BOSS 保留为用户主动搜索具体岗位的可选来源，不参与每日自动调度。

### 6.4 机会处理动作

- 关注：进入跟踪列表并创建研究/截止任务。
- 忽略：记录原因，供后续偏好洞察使用，但不自动改变偏好。
- 查看岗位：跳转官方入口，用户可导入具体 JD。
- 建立岗位：从文本、文件、URL 或外部来源生成 JobPost。
- 标记已投：进入 Application 流程。

### 6.5 数据与服务改造

新增：

- `recruitment_opportunities`
- `opportunity_versions`
- `opportunity_sources`
- `opportunity_actions`
- `opportunity_job_links`

新增应用服务：

- `OpportunityDiscoveryService`
- `OpportunityTriageService`
- `JobEnrichmentService`

现有牛客 Connector 不再直接调用 `JobApplicationService.import_connector()` 创建伪 JobPost，而是写入 Opportunity。按已确认原则不迁移旧 Career 数据，新模型从启用后采集的数据开始建立。

### 6.6 页面设计

“机会与岗位”页面分为：

- 今日新机会；
- 已关注招聘项目；
- 具体岗位池；
- 已忽略；
- 来源和更新时间。

卡片必须明确标识“招聘项目”或“具体岗位”，避免用户误以为公司秋招批次就是一个岗位。

当前实现状态：机会池、来源版本、关注/忽略、北京时间今日筛选以及 `opportunity_job_links` 已落地。用户可从机会卡片进入带上下文的 JD 导入页，关联岗位后从岗位详情直接建立申请档案。

## 7. 功能三：岗位分析与决策

### 7.1 分析目标

帮助用户回答四个问题：

1. 我是否满足硬性条件？
2. 我的哪些事实能证明匹配？
3. 最大缺口是什么，是否值得补？
4. 这个岗位是否值得现在投入时间？

### 7.2 执行流程

```text
JobPostVersion
→ Agent 提取结构化要求
→ 硬门槛确定性校验
→ 要求与 CandidateFact 证据关联
→ 识别缺口与可迁移能力
→ 结合偏好和当前负载计算优先级
→ 保存 JobMatchAnalysis
```

### 7.3 输出内容

- 硬性门槛是否通过。
- 要求—证据—缺口逐项表格。
- 优势和风险。
- 申请成本：材料修改量、准备时间、截止时间。
- 建议：高优先、考虑、低优先、阻塞。
- 下一步：导入更完整 JD、补充事实、生成材料或忽略。

### 7.4 Agent 与确定性逻辑

Agent 负责要求语义、证据候选、可迁移能力和解释；最终硬门槛、分项权重和优先级计算由 Domain 完成。Agent 引用的 Fact ID 必须存在且为 confirmed。

### 7.5 当前实现与改造

当前已有岗位导入、版本、要求和基础匹配页面，但主要使用本地提取/评分。需要引入 `job_requirement.v2`、`job_fit_analysis.v2`、事实 ID 验证、偏好维度、机会成本和受档案变化触发的重算。

## 8. 功能四：简历策略与材料工作台

### 8.1 三层材料模型

```text
Base Resume（基础事实表达）
→ Resume Track（岗位族/表达方向）
→ Job-tailored Material（某个具体岗位版本）
```

- 基础简历：完整、稳定、便于长期维护。
- 方向简历：如后端工程、数据工程、AI 应用、产品技术等。
- 岗位定制版本：锁定岗位版本和事实快照，只服务一次申请。

### 8.2 方向选择

生成前先运行 `resume_direction.v1`，给出 2–4 个候选方向。每个方向包含：

- 方向名称和核心叙事。
- 重点岗位要求。
- 将突出哪些已确认事实。
- 哪些内容降权或删除。
- 预计修改范围和页数。
- 事实不足和表达风险。
- 推荐理由。

用户可以选择方向、组合两个方向，或手动指定重点。系统不应直接生成一份“唯一正确”的简历。

### 8.3 生成与审查

```text
用户选择方向
→ 锁定 JobPostVersion + CandidateFact revisions + Base ResumeVersion
→ Drafter 输出结构化 blocks 和事实引用
→ 引用完整性校验
→ Reviewer 独立检查真实性、覆盖率、表达、ATS 和风险
→ 用户编辑
→ PDF 渲染与文本层检查
→ 用户 Final
```

### 8.4 关键 Schema

- `resume_direction.v1`
- `resume_draft.v2`
- `material_review.v2`
- `export_validation.v1`

每个生成 block 都必须附 `fact_ids`；没有可信事实支持的内容不能进入 Final。

### 8.5 页面设计

- 简历系列：基础简历和方向简历。
- 岗位材料向导：选岗位 → 看方向 → 选方向 → 生成 → 审查 → 导出。
- 版本对比：显示增删内容、事实引用和岗位覆盖变化。
- 实际投递标记：Final 不等于已投递，投递时另行确认。

### 8.6 当前实现与改造

当前已有材料实体、block 编辑、版本、确定性 Review、Final 和 PDF；Drafter–Reviewer 已消费活动 ResumeDirectionSelection，并以 `resume_draft.v2`、`material_review.v2`、双 AgentRun、Proposal、ReviewTask、FactSnapshot 和 FactReference 形成确认闭环。基础简历、方向简历和岗位定制版本已经通过 `version_scope`、`source_resume_version_id` 与独立快照形成正式血缘，Web 可查看块级和 Fact 级差异。原 `generate()` 继续作为明确标注的确定性基线。

## 9. 功能五：申请进度与投递档案

### 9.1 产品形态

申请管理应成为核心进度页面，提供三种视图：

- **看板**：待投递、已投递、测评/笔试、面试、Offer、结束。
- **列表**：公司、岗位、当前阶段、下一事项、更新时间、风险。
- **日历**：截止、测评、笔试和面试。

### 9.2 申请详情页

点击任意申请后展示：

1. 当前状态与下一步；
2. 完整不可变事件时间线；
3. 当时的岗位版本；
4. 实际投递材料快照；
5. 关联邮件及结构化分析；
6. 日程、任务和提醒；
7. 面试记录和准备包；
8. 用户备注、联系方式和申请编号；
9. Agent 建议及其审查状态。

### 9.3 建档来源

- 用户从岗位页确认投递。
- 用户手动创建历史申请。
- Agent 从招聘邮件提出建档建议。
- 导入已有申请清单。

邮件发现未知申请时不得直接创建正式 Application，应生成 `application_creation_proposal.v1`，由用户确认公司、岗位和投递时间。

### 9.4 状态与事件

状态只是事件投影。建议事件类型扩充为：

- `application_submitted`
- `application_confirmed`
- `assessment_invited/completed`
- `written_test_invited/completed`
- `interview_invited/rescheduled/completed/cancelled`
- `additional_material_requested/submitted`
- `offer_received/accepted/declined`
- `application_rejected/withdrawn/archived`

同一封邮件可以提出多个事件和多个日程，但正式写入前都需要确认。

### 9.5 当前实现与改造

当前已有 Application、状态机、事件、更正、材料快照、Proposal 和审查任务。需要升级看板/列表/日历视图，扩展事件粒度，引入从邮件建档、邮件证据详情、联系人和下一行动投影。

## 10. 功能六：Agent 邮件智能

### 10.1 目标

邮件模块的目标不是显示一个收件箱，而是从已读和未读招聘邮件中维护投递档案、申请进度、日程和待办。

### 10.2 数据获取

- 首次同步只读最近 7/14/30 天，由用户选择。
- 后续按 UID 增量同步。
- 不使用 `UNSEEN` 条件，已读和未读一并处理。
- `SELECT readonly=True`，只允许 `UID SEARCH` 和 `BODY.PEEK`。
- 不发送、回复、移动、删除或标记已读。

### 10.3 分层分析流程

```text
Header + 发件域 + 邮件线程 + 已有申请线索
→ 低成本候选判断
→ 对候选读取受限正文
→ Tool-free Mail Agent
→ mail_intelligence.v1 校验
→ 申请候选排序
→ 建档/事件/日程/任务 Proposal
→ 用户审查
```

为降低漏判，候选判断不能只依赖当前少量主题关键词，还要使用：招聘发件域历史、邮件线程、申请编号模式、日历时间模式、已有 Application 公司别名，并允许用户将误判邮件标记为招聘相关后重新分析。

### 10.4 `mail_intelligence.v1`

至少包含：

- `isCareerRelated`、`category`、`confidence`；
- 公司、岗位、招聘项目、申请编号、候选人编号；
- `events[]`：类型、发生时间、状态建议和证据；
- `schedules[]`：开始、结束、截止、时区、方式、地点、会议链接；
- `actionItems[]`：任务、截止、优先级；
- `cautions[]`：设备、材料、签到、次数、改期等注意事项；
- 联系人、链接、中文摘要；
- 每项结论对应的精确原文证据。

Agent 无工具权限，邮件正文被明确标记为不可信数据。Schema、枚举、时间范围、证据子串和链接协议需要二次校验。

### 10.5 隐私模式

页面必须显示当前分析 Provider：

- 本地 Provider：正文只在本机处理。
- 在线 Provider：候选邮件正文会发送给已配置服务商。
- 规则模式：不调用模型，但能力降级。

用户应能选择专用求职邮箱、允许分析的发件域和是否启用在线 Provider。无关正文不长期保存；业务库保存必要摘录、哈希、结构化结果和原始 UID 引用。

### 10.6 页面设计

消息中心按业务状态分组：

- 待分析/分析失败；
- 待关联申请；
- 待确认进度；
- 已归档到申请；
- 非求职邮件（仅最小记录）。

邮件详情显示摘要、事件、日程、注意事项、证据和候选申请，不需要模拟完整邮件客户端。

### 10.7 当前实现与改造

当前已完成严格只读 IMAP、已读/未读统一 UID 扫描、30 天上限、游标、去重、最小持久化和确定性分类。需要替换关键词/正则作为最终分类器，引入 MailAnalyzer Port、Agent 实现、结构化 Schema、分析状态、重分析入口、Agent Run、多个事件/日程和从邮件建档。

## 11. 功能七：日程、任务与今日行动

### 11.1 统一模型

- `ScheduleItem`：客观发生的时间，例如网申截止、笔试、面试。
- `Task`：用户需要完成的动作，例如完善材料、设备检查、参加笔试。
- `Reminder`：何时提醒某个 Schedule 或 Task。

三者不能混为一个对象。

### 11.2 自动来源

- Opportunity 的申请截止时间。
- 用户的投递计划。
- 邮件 Agent 提取的测评/笔试/面试时间。
- 面试准备和复盘任务。
- 用户手动创建的任务。

外部来源产生 Proposal；用户确认后才成为正式日程。改期邮件需要 supersede 原日程并同步相关提醒。

### 11.3 今日页面

首页应成为行动入口，按优先顺序展示：

1. 今天必须完成；
2. 未来 72 小时的笔试/面试；
3. 临近截止但尚未处理的机会；
4. 当天新增且高相关的机会；
5. 待确认邮件事件和档案变化；
6. 同步/Agent 异常；
7. 当日简报。

### 11.4 每日简报

`DailyDigest` 是可重建视图，不是用户长期事实。内容包括当天新增机会、申请变化、任务完成、风险和明日重点。没有新数据时不调用 Agent，只使用确定性聚合。

### 11.5 当前实现与改造

当前已有 Task、Schedule、Reminder、Dashboard、冲突和北京时间。需要拆清 Schedule 与 Task 的展示，加入 Opportunity 截止、邮件多个日程、统一日历和 DailyDigest。

## 12. 功能八：面试准备、复盘与成长

### 12.1 面试准备

准备包必须锁定：

- 实际岗位版本；
- 实际投递材料；
- confirmed Candidate Facts；
- 已确认的历史改进项；
- 面试轮次和时间。

Agent 输出：重点考查、可能问题、事实证据、回答结构、诚实 Gap Bridge、反问清单和设备/资料检查。

### 12.2 面试复盘

用户记录问题、回答摘要、自评、结果和补充反馈。Agent 生成：

- 问题分类；
- 回答中的有效证据和缺失；
- 表达/技术/业务弱点；
- 下次可执行改进；
- 是否属于重复模式。

所有长期改进项先进入 Review，不能因为一次面试自动定义用户能力。

### 12.3 回流职业档案

- 面试结果作为 ApplicationEvent，不是 CandidateFact。
- 已确认的重复弱点进入 ImprovementItem。
- 用户补充的真实项目细节可形成 CandidateFact Proposal。
- 阶段性表现用于 StrategySnapshot，不直接改写基础事实。

### 12.4 当前实现与改造

当前已有 Interview、改期/取消、准备包冻结、问题记录、反馈候选和长期改进项。当前准备与反馈多数为确定性生成，需要接入结构化 Agent Task、证据验证、重复模式分析和更清晰的档案回流审查。

## 13. 横向功能：审查中心、Agent 透明度与治理

### 13.1 统一审查中心

统一处理：

- 新事实和档案洞察；
- 邮件与申请关联；
- 从邮件建立申请；
- 申请事件和日程；
- 岗位合并；
- 简历 Final；
- 面试长期改进项；
- 周策略快照。

按风险、截止时间和来源排序，支持批量确认低风险项，但不允许批量确认 Offer、拒绝、投递或档案核心事实。

### 13.2 Agent Run

每次后台 Agent 调用记录：任务类型、Provider、模型、Prompt/Schema 版本、输入业务引用、状态、耗时、错误和结果哈希。敏感全文不默认进入日志。

用户可以回答“这条结论来自哪里”“为什么匹配这个申请”“为什么这样改简历”。

### 13.3 数据治理

- SQLite、Blob、导出文件和配置可完整备份。
- Secret 不进入数据库备份或 JSON 导出。
- 支持按 Connector、申请、邮件和全部数据删除。
- 支持重新分析而不重新采集原始数据；必要时按 UID 受控重取邮件。
- Agent 洞察和 DailyDigest 可重建，事实与事件不可静默删除。

## 14. 功能协作矩阵

| 来源/动作 | 写入对象 | 自动触发 | 需要用户确认 | 下游影响 |
|---|---|---|---|---|
| 导入简历 | Document、Fact Proposal | 事实提取 | Fact | 岗位重算、材料可用事实 |
| 修改偏好 | Preference Revision | 机会重排 | 核心偏好 | 今日机会、岗位优先级 |
| 牛客每日同步 | Opportunity | 初筛、去重 | 关注/忽略 | 机会页、截止任务 |
| 导入具体 JD | JobPostVersion | 要求提取、匹配 | 模糊合并 | 简历方向、申请准备 |
| Final 材料 | MaterialVersion | 导出检查 | Final | 可用于确认投递 |
| 确认投递 | Application/Event/Snapshot | 跟进任务 | 投递事实 | 邮件匹配、进度页 |
| IMAP 同步 | MailEvidence/Analysis | Agent 分析 | 建档、事件、日程 | 申请、任务、面试 |
| 确认面试 | ApplicationEvent/Interview | 准备任务 | 事件 | 准备包、提醒 |
| 面试复盘 | Record/Feedback Proposal | Agent 分析 | Improvement | 下次准备、周策略 |
| 每日整理 | DailyDigest | 确定性聚合/按需 Agent | 否 | 今日页面 |
| 每周回顾 | Strategy Proposal | Agent 归纳 | StrategySnapshot | 机会和行动策略 |

## 15. Agent 执行模型

### 15.1 以 Task Agent 为核心

产品的主要交互是用户在 Web 中执行明确操作，因此核心只有一种 Agent：**由业务工作流触发、输入输出 Schema 化的 Task Agent**。它负责邮件、岗位、材料、面试和策略等有限任务，不进行通用自由对话。

未来如果增加自然语言入口，它只是 `Command Assistant`：负责解释页面数据或把用户意图转换为明确 Application Command，不拥有独立 Memory、业务写入路径或自由工具权限，也不成为产品主流程。

### 15.2 推荐 Task 列表

- `extract_candidate_facts`
- `derive_profile_insights`
- `propose_career_strategy`
- `extract_job_requirements`
- `analyze_job_fit`
- `propose_resume_directions`
- `draft_resume_material`
- `review_resume_material`
- `analyze_career_email`
- `rank_application_candidates`
- `prepare_interview`
- `analyze_interview_feedback`
- `compose_weekly_strategy_review`

### 15.3 统一校验流水线

```text
业务对象引用
→ 最小化上下文
→ Tool-free 或工具白名单 Agent
→ JSON 解析/修复一次
→ Pydantic Schema 校验
→ Domain 枚举、时间和状态校验
→ Evidence/Fact ID 校验
→ 保存 AgentRun
→ Proposal 或正式派生视图
```

Schema 失败、证据无效或模型不可用时进入可重试状态，不允许退化成未经标识的自由文本结论。

## 16. 页面信息架构

当前导航过于按工程 Part 展开，建议调整为：

```text
今日
机会与岗位
申请进度
材料工作台
职业档案
日程任务
面试成长
审查中心
设置
  ├── 数据来源
  ├── Agent 与模型
  ├── 运行与后台任务
  └── 数据治理
```

“简历导入”“事实审查”成为职业档案的子页；“事件审查”并入统一审查中心；“运行状态”和“后台任务”移入设置；“全链路工作区”不再作为与业务页面平级的入口。

## 17. 后端模块落地

### 17.1 Domain

```text
domain/profile       事实、偏好、洞察、策略
domain/opportunity   招聘项目和处理状态
domain/jobs          具体岗位、版本、要求和匹配
domain/materials     简历系列、方向、版本和 Final
domain/applications  申请、事件、Proposal 和状态投影
domain/mail          邮件分析、实体、日程和注意事项
domain/planning      Schedule、Task、Reminder、Digest
domain/interviews    面试、准备、记录和成长项
domain/review        统一审查任务和风险策略
```

### 17.2 Application Services

每个模块只暴露明确用例，不提供通用表修改：

- `ProfileMaintenanceService`
- `OpportunityDiscoveryService`
- `JobDecisionService`
- `MaterialWorkflowService`
- `ApplicationTimelineService`
- `MailIntelligenceService`
- `PlanningService`
- `InterviewGrowthService`
- `ReviewCenterService`

### 17.3 Ports

新增或统一：

- `AgentTaskPort`
- `MailAnalyzer`
- `ProfileInsightAnalyzer`
- `ResumeDirectionPlanner`
- `MaterialDrafter` / `MaterialReviewer`
- `OpportunityGateway`
- `ScheduleGateway`
- `AgentRunGateway`

Domain 不依赖 Provider、SQLAlchemy、OpenCLI、IMAP 或 FastAPI。

### 17.4 后台任务

建议任务类型：

- `sync_nowcoder_today`
- `process_opportunity_source_event`
- `analyze_job_fit`
- `analyze_mail_message`
- `reconcile_mail_application`
- `generate_material_draft`
- `review_material`
- `generate_interview_pack`
- `analyze_interview_record`
- `build_daily_digest`
- `propose_weekly_strategy`

任务使用持久化队列、幂等键、lease、有限重试和错误隔离。同步任务不在持有数据库事务时调用外部程序或模型。

### 17.5 API 方向

```text
/api/v1/profile/*
/api/v1/profile-insights/*
/api/v1/strategies/*
/api/v1/opportunities/*
/api/v1/job-posts/*
/api/v1/job-analyses/*
/api/v1/resume-tracks/*
/api/v1/material-workflows/*
/api/v1/applications/*
/api/v1/application-events/*
/api/v1/mail/*
/api/v1/schedules/*
/api/v1/tasks/*
/api/v1/interviews/*
/api/v1/review-tasks/*
/api/v1/agent-runs/*
/api/v1/connectors/*
/api/v1/dashboard/*
```

命令使用显式 endpoint，例如 `confirm-submitted`、`resolve`、`reanalyze`、`choose-direction`，不使用一个通用 PATCH 任意修改状态。

## 18. 当前实现差距

| 产品能力 | 当前基础 | 主要差距 |
|---|---|---|
| 职业档案 | 事实、来源、确认、revision | 偏好实体、洞察、策略、事件驱动维护、Agent 默认能力 |
| 牛客每日获取 | 当天同步、30 天手动回填 | Opportunity 与 JobPost 混用、同步后缺少产品化分流 |
| 岗位分析 | 要求、匹配、版本 | Agent 证据匹配、偏好、投入产出、自动重算 |
| 材料 | 版本、block、Review、PDF、Final | 方向选择、真正 Drafter/Reviewer、事实引用 |
| 申请进度 | Application、事件、快照、Proposal | 完整看板/日历、细粒度事件、从邮件建档 |
| 邮件 | 严格只读、UID、30 天、去重 | Agent Schema、多事件/日程、重分析、申请档案维护 |
| 日程任务 | Task、Reminder、Dashboard、冲突 | 独立 Schedule、统一日历、DailyDigest |
| 面试 | 准备、记录、反馈、改进项 | Agent 分析、证据和档案回流 |
| 审查 | 事实审查、事件审查 | 统一风险队列和所有 Agent Proposal |
| Agent 审计 | 少量提取调用 | 统一 AgentTaskPort、AgentRun、模型/隐私展示 |

现有 Part 0–9 代码是可利用的工程骨架，不应整体推倒；但“功能存在”不等于产品闭环已经正确。下一阶段应按本设计重构边界和用户流程。

## 19. 推荐开发顺序

### Phase A：产品模型校正

1. [已完成] 引入 Opportunity，改造牛客数据流，不再把招聘批次当具体岗位。
2. [已完成] 重组导航和今日/机会/申请三个核心页面；今日新机会、带来源的 JD 导入、岗位详情和申请建档已串联。
3. [已完成] 统一 ReviewTask 与 AgentRun 基础设施，事实、申请事件和面试反馈共用审查队列，业务 Agent 使用可追溯审计记录。

验收结果：用户能从每日新机会进入具体岗位和申请链路，概念不混乱。

Phase A 与 Phase B 已完成。下一阶段进入 Phase C，建设可追溯的档案维护与业务记忆。

### Phase B：Agent 邮件与申请档案

1. [已完成] 定义 `mail_intelligence.v1` 和 MailAnalyzer Port。
2. [已完成] 接入共享 AgentRunner 的 tool-free CareerConsole Task Agent；不加载会话、SOUL、工作区记忆或 Skills。
3. [已完成] 支持多事件、日程、注意事项、应用匹配和从邮件建档候选；统一进入 ReviewTask。
4. [已完成] 邮件中心展示分析、证据和审核动作；申请详情聚合关联邮件及其候选状态。
5. [已完成] 同步后通过持久化 BackgroundJob 独立批处理，使用租约、指数退避和人工重试，IMAP 游标提交不受模型延迟影响。
6. [已完成] 无匹配邮件通过“导入真实 JD → 岗位详情确认跟踪”建档，邮件、岗位和申请保持可追溯关联。

验收结果：真实已读/未读招聘邮件能够维护投递档案，但所有正式变化经过确认。

### Phase C：档案维护与业务记忆

1. [已完成] 显式偏好、可审核洞察候选、版本化策略快照。
2. [已完成] 事实、偏好和已确认业务结论写入不可变档案变化事件；每个 impact scope 投影为带幂等键、租约和重试的持久化任务。
3. [已完成] DailyDigest 可按北京时间事件重建；每周 Strategy Proposal 进入统一审核。
4. [已完成] tool-free `profile_insight.v1` Agent 使用最小结构化上下文，严格校验 confirmed Fact ID，并原子记录 AgentRun、Proposal 与 ReviewTask。
5. [已完成] 活动岗位按 JD 版本和 confirmed fact hash 自动重算；材料策略变化只做 stale 标记，不改写 Final 或历史快照。

当前开发结果：Phase C 两条纵向切片已经贯通，显式偏好、事实确认、Agent 洞察、策略、摘要、影响任务、岗位重算和材料失效均可追溯。下一步统一执行 Phase C 的真实配置与人工验收，再进入 Phase D 的岗位决策和材料方向智能。

### Phase D：岗位决策与材料智能

1. [已完成] `job_fit_analysis.v2` Agent 逐项解释岗位要求并引用 confirmed Fact；Proposal 经 ReviewTask 和用户确认后，由 Domain 计算硬门槛、匹配分、偏好/投入调整和正式优先级。
2. [已完成] `resume_direction.v1` Planner 生成 2–4 个有不同叙事和事实重点的方向；用户选择一个或组合两个后形成版本锁定的 ResumeDirectionSelection。
3. [已完成] Drafter–Reviewer 和事实引用校验。
4. [已完成] 方向简历、岗位定制版本和差异页面。

Phase D 四条纵向链路均已完成。下一步进入真实配置与人工验收，按“岗位分析 → 方向选择 → Agent 草稿 → Reviewer → 血缘/差异 → Final PDF”逐项测试和修复。

### Phase E：面试与策略闭环

1. Agent 面试准备和复盘。
2. 改进项去重、确认和回流。
3. 周策略回顾与结果分析。

验收结果：过去的真实申请和面试结果能改善下一次岗位判断、材料和准备。

## 20. 产品级验收场景

完整验收不以“页面能打开”为标准，而以以下闭环为准：

1. 导入真实简历，Agent 提取事实，用户确认。
2. 设置真实求职偏好，形成第一版策略快照。
3. 牛客获取当天招聘项目，用户关注其中一个。
4. 导入该项目下的具体岗位 JD，获得有事实证据的匹配分析。
5. 系统列出至少两个简历修改方向，用户选择后生成和审查材料。
6. 用户在外部完成投递，并在系统冻结岗位和材料快照。
7. 同步一封已读或未读的投递确认邮件，Agent 关联到该申请。
8. 同步笔试或面试邮件，提取北京时间日程、待办和注意事项。
9. 用户确认事件后，在申请时间线、日历和今日页面同时出现。
10. 系统生成面试准备包，用户完成复盘并确认一个改进项。
11. 下一次同类岗位分析、材料建议和面试准备能够引用该改进项。
12. 用户能查看每个关键结论的证据、Agent Run、确认人和版本。

## 21. 已确定的产品决策

- 用户业务档案是结构化领域数据，不是常规 Agent 长期记忆。
- 档案采用事件驱动维护；每日只增量整理，每周生成可审查策略，不做每日覆盖式总结。
- 简历生成前提供多个修改方向，由用户选择后再生成。
- 申请进度是核心页面，必须具备看板、列表、日历和详情时间线。
- 邮件用于维护投递档案，扫描已读和未读邮件，并由 Agent 输出固定 Schema。
- OpenCLI 是数据入口；牛客每日数据进入 Opportunity，具体 JD 才进入完整岗位与材料流程。
- 自动化负责发现、分析和提出建议，用户负责投递、确认事实和批准正式状态变化。

## 22. 后续文档关系

本文件定义“产品应该如何工作”。后续执行时：

- `CAREER_REQUIREMENTS_ANALYSIS.md` 保留为三项目调研和原始需求依据。
- [技术实现方案](../architecture/technical-implementation-plan.md)继续描述通用工程架构，但需要根据 Opportunity、业务记忆和 AgentTaskPort 补充修订。
- [开发计划](development-plan.md)需要从原 Part 0–9 完成状态转为本文件 Phase A–E 的产品改进计划。
- 每个 Phase 开发前另建短期实施文档，冻结 Schema、迁移、API、页面和验收用例。

## 23. CareerConsole Runtime 适配与改造

### 23.1 总体结论

CareerConsole 在本项目中是可修改的源码基础，不是需要保留兼容性的独立产品。目标是形成一套 **Career-only Runtime**：

```text
Web UI 明确操作
→ Career API Command/Query
→ Domain + Database Transaction
→ Background Job / Workflow
→ Career Agent Task Runtime
→ Schema 校验 + Proposal
→ 用户审查
→ 正式业务事件
```

Provider、AgentLoop、模型适配、重试、响应转换、Cron、Channels、Tools 等基础能力可以保留并按 Career 需要重构。Markdown Memory 和旧 Career Store 等业务模型不正确的部分可以直接替换。目标不是机械删除通用能力，而是避免为旧业务长期维护与 Career 重复的状态和执行逻辑。

判断标准不是“它原来属于 CareerConsole”，而是：是否符合 Career 业务模型、可靠性、安全性和长期维护要求。

### 23.2 Memory 系统

当前 `MemoryStore` 使用：

- `memory/MEMORY.md`：模型生成并整段更新的长期 Markdown。
- `memory/HISTORY.md`：聊天摘要或失败后的原始会话归档。
- `ContextBuilder`：把 `MEMORY.md` 自动注入后续交互 Prompt。

这套机制不适合作为 Career 产品的核心系统，原因是：

- 没有事实 ID、来源、状态和 revision。
- 模型可以在 consolidation 时改写或遗漏旧内容。
- 无法区分事实、偏好、洞察、邮件证据和申请状态。
- 无法执行状态机、用户确认和冲突处理。
- Markdown 全量注入会造成隐私、上下文膨胀和过期信息问题。
- consolidation 失败后的原始聊天归档也不适合承载敏感求职数据。

因此不在旧 Memory 上增加 Career namespace，而是用“业务知识与状态系统”取代它。可以参考先进 Agent 的分层记忆思想，但按本产品映射：

| 常见 Agent 概念 | Career 中的实现 | 持久化策略 |
|---|---|---|
| Working memory | 单次 Agent Task 的 `ContextPack` | 临时，任务结束即释放或只留哈希 |
| Episodic memory | 投递、邮件、事件、面试和用户操作记录 | 不可变业务事件与证据 |
| Semantic memory | 已确认事实、偏好、公司/岗位实体、能力证据 | 结构化、版本化、可追溯 |
| Procedural memory | Workflow、Prompt、Schema、评审规则 | 代码/版本化配置，不由模型自改 |
| Reflective memory | ProfileInsight、Improvement、StrategySnapshot | Agent Proposal，用户确认后生效 |
| Retrieval memory | FTS/结构化索引/可选 embedding | 可重建索引，不是真实来源 |

核心组件调整为：

1. `EvidenceStore`：保存文档、邮件、岗位和复盘的必要证据引用。
2. `FactLedger`：保存已确认事实、来源、revision、冲突和有效期。
3. `BusinessEventStore`：保存 ApplicationEvent、用户动作和状态变更。
4. `InsightRegistry`：保存待确认/已确认/失效的洞察和成长项。
5. `StrategySnapshotStore`：保存阶段策略版本。
6. `ContextAssembler`：按具体任务从以上数据生成有 revision 的最小上下文包。
7. `RetrievalIndex`：只做加速和召回，随时可从业务数据重建。

Agent 没有通用 `save_memory` 权限。任何“记住这个”都必须转化为明确业务命令，例如提出事实、修改偏好、记录申请事件或创建成长项。

现有 `career_console/runtime/agent/memory.py` 不再承担 Career 业务知识。可以重写为基于业务知识系统的检索/上下文接口，或在确认没有独立对话记忆需求后移除其中的 Markdown consolidation；具体代码处置不影响 AgentLoop 继续存在。

### 23.3 Context Builder

当前 `ContextBuilder` 会加载身份文件、通用 Memory、Skills 摘要、会话历史和运行环境。这不适合直接用于后台 Career Task。

现有通用 `ContextBuilder` 不进入 Career Agent 主路径，替换为 `CareerTaskContextBuilder`。它只接收 Task Handler 声明的数据，不扫描 workspace，不加载 `MEMORY.md`、`SOUL.md`、通用 Skills 或聊天 Session。

每个 Career Task 声明 `ContextManifest`，包含允许的实体类型、字段、revision、敏感等级、最大条数、token budget 和排序规则。例如邮件分析仅允许：邮件 Header、受限正文、线程摘要、候选 Application 摘要和中国时区；不能读取完整简历、其他邮件或文件系统。

上下文包保存业务引用和内容哈希，确保 Agent 结果可以复现“当时看到了哪些版本的数据”。

### 23.4 Agent Loop 与 Task Runtime

AgentLoop 是 Agent 的核心编排能力，应保留并面向 Career 重构。问题不在于 Loop 本身，而在于不能让每个后台任务都以无限制自由对话方式运行。

不另建一套与 AgentLoop 重复的执行器，而是在同一运行核心上增加两种执行策略：

- `interactive`：未来用于自然语言解释、导航或明确命令，允许受控多轮和工具调用。
- `task`：用于邮件、岗位、材料、面试等后台任务，固定 Context、Schema、预算、迭代次数和工具白名单。

`AgentTaskPort` 是 Application 层对 AgentLoop task mode 的稳定适配接口，不是第二套 Agent 核心。

```python
class AgentTaskPort(Protocol):
    async def run(
        self,
        task_type: str,
        input: BaseModel,
        policy: AgentExecutionPolicy,
    ) -> AgentTaskResult: ...
```

`AgentExecutionPolicy` 至少包含：

- Provider/模型和本地或在线数据策略；
- input/output schema version；
- tools allowlist，默认空；
- timeout、token budget 和最大修复次数；
- Prompt/Skill version；
- 敏感等级和允许发送的数据字段；
- 幂等键、重试策略和审计要求。

AgentLoop 内部复用 Provider 的 `chat_with_retry`、消息转换、错误映射、流式能力和 Tool Registry。Task mode 禁止自动注入通用 Memory/无关 Session，并由策略限制多轮规划和工具选择；Interactive mode 可按需使用短期 Session 和受控工具。两种模式共享一个执行核心和审计体系。

### 23.5 Tool 系统

通用 Tool Registry 和工具类保留，以支持 Agent 当前和未来能力。Career Task 的首选接口仍是类型明确的 Application Query/Command Port；只有需要模型主动选择的能力才包装为 Tool，并增加严格权限元数据：

- `risk_level`：read、propose、confirmed_write、external_write。
- `data_scope`：允许读取的业务对象和字段。
- `requires_user_confirmation`。
- `idempotency_required`。
- `audit_required`。
- `available_to`：interactive、task 或两者。

后台邮件、岗位、简历和面试分析默认 `tools=None`。确需工具时，只能调用只读业务 Query。未来自然语言入口的写操作也只能转换为显式 Application Command，例如提出事实、创建草稿或建立 ReviewTask；不得提供 `execute_sql`、`update_any_table`、任意文件修改或任意 OpenCLI 命令。

现有 filesystem、exec、web、message、cron 等通用工具暂时保留，但不默认暴露给 Career 后台任务。每个 execution policy 明确 allowlist；邮件等不可信输入任务通常 `tools=None`。OpenCLI 仍由 Connector Service 的固定 argv 和命令白名单调用，不交给 Agent 自由执行。

### 23.6 Session 与 AgentRun

现有 Session 可保留并按 Career 交互需求重构，但不作为业务数据库或审计记录。业务 Agent 过程统一使用 `AgentRun`：

- `task_type`、状态和 correlation ID；
- Provider、模型、Prompt/Skill/Schema 版本；
- 输入业务对象 ID 和 revision；
- 工具调用摘要；
- 输出结构化结果或安全哈希；
- token、耗时、重试和错误码；
- 敏感数据等级和保留期限。

Session 只负责交互连续性并设置明确保留期限；业务审计始终以 AgentRun 和 Domain Event 为准。后续可将 JSONL 存储替换为更合适的实现，但不需要现在删除 Session 抽象。

### 23.7 Cron、Scheduler 与后台任务

CronService 的定时能力有长期价值，应保留并改造成统一调度引擎。它负责“何时触发”，BackgroundJob/Workflow 负责“如何可靠执行”：

- 牛客每日同步、IMAP 轮询、DailyDigest、Weekly Strategy 和用户提醒都由统一 Cron/Scheduler 计算触发时间。
- CronService 抽象 `ScheduleRepository`，正式配置落数据库，不再只有 JSON Store。
- Cron payload 扩展为类型化 `job_type + entity_ref + idempotency_key`，而不只是一段 `agent_turn` message。
- 到期后只入队 BackgroundJob/NotificationDelivery；具体工作由具备 lease、重试和错误隔离的 Worker 执行。
- 保留 cron expression、时区、一次性/周期任务和手动触发能力。
- 避免同时维护“通用 Cron”和“Career Scheduler”两套持久状态，最终收敛为一个调度服务。

### 23.8 Channel 与通知

Channels 具有向用户发送提醒、任务变化和异常通知的价值，应保留并改造成 `NotificationChannel` 适配器。它们不再默认承担“用户发消息驱动 Agent 对话”的主入口，但可以支持出站通知，未来再按明确需求增加安全的确认回执。

原 Email Channel 的入站读取不能替代只读 IMAP Connector；其中会修改邮件状态的逻辑必须关闭或拆除。其出站发送能力若未来需要，可作为单独 Notification Adapter。Discord、Telegram、飞书、钉钉等 Channel 可复用连接和发送能力，并遵守：

- Channel Message 不直接成为正式业务事件。
- 外部消息先标准化为 SourceEvent 或用户命令。
- 通知默认只包含最小必要信息，不包含邮件正文、简历全文或 Secret。
- 通过 Channel 执行确认操作时需要短期签名 token 或回到本地 Web 确认。

### 23.9 Skill 和 Prompt

Skill 只定义模型如何完成任务，不定义业务状态机。Career Skills 需要：

- 与 `task_type` 和 output schema 绑定；
- 保存版本和变更记录；
- 明确不可信输入和禁止行为；
- 配套 Fixture、Schema 和回归测试；
- 不能通过编辑 Markdown Skill 改变数据库规则或用户确认边界。

通用 `resume-assistant`、`boss-job-assistant` 可以保留为参考和未来能力，但正式流程使用版本化 Career Task Prompt。旧 Skill 不得绕过 Career Application Service 或通过自由 Exec 改写业务状态。

### 23.10 Provider 与隐私路由

Provider Registry 可以复用，但要新增 Career 数据策略层：

- 标识 Provider 是 local、private endpoint 还是 external。
- 每种 Task 声明敏感等级和可用 Provider。
- 页面显示当前实际模型和数据处理位置。
- 用户可以禁止邮件、简历或面试内容发送给在线 Provider。
- Provider 不可用时任务进入可重试/需配置状态，不静默退化成未经标识的结果。

推荐建立 `ProviderPolicyResolver`，由业务任务、用户设置和数据等级共同决定模型，而不是只按全局默认模型路由。

### 23.11 CareerConsole 模块处置矩阵

| CareerConsole 模块 | 目标处置 | Career 用法 |
|---|---|---|
| Provider Registry / Provider adapters | 保留并增强 | Career Task Runtime 使用，增加隐私策略 |
| Agent Runner 的模型请求/重试 | 抽取复用 | Career Task 使用单次/有限修复调用 |
| Agent Loop | 保留并重构 | 作为统一 Agent 核心，支持 interactive/task execution policy |
| MemoryStore / Consolidator | 重写为业务知识/上下文系统 | 删除 Markdown 全量 consolidation，不删除“记忆能力”本身 |
| ContextBuilder | 重写 | 仅保留 Schema 化 Career Task Context |
| SessionManager | 保留/重构 | 只负责短期交互，不承担业务状态和审计 |
| Tool Registry / Base Tool | 保留并增强 | 按 execution policy、风险和数据范围控制暴露 |
| CronService | 保留并重构 | 与数据库 Schedule 收敛为统一调度引擎 |
| MessageBus | 保留并明确边界 | 用于 Agent/Channel 运行时消息，不替代 Domain Event/Outbox |
| Email Channel | 拆分/改造 | 入站使用只读 IMAP；出站可作为通知适配器 |
| 其他 Channels | 保留并改造 | 以出站提醒为主，未来支持安全回执 |
| Skills Loader | 保留并规范 | 正式任务增加版本化 Task Prompt Registry，Skill 不承载业务规则 |
| 通用 filesystem/exec/web 工具 | 保留并策略隔离 | 默认不向不可信后台任务开放 |
| 旧 Career store/resume tool | 直接删除旧业务逻辑 | 不做旧数据迁移，只清理运行引用 |

### 23.12 推荐实施顺序

CareerConsole Runtime 改造应嵌入产品 Phase，而不是单独大重写：

1. Phase A 建立 `AgentRun`、统一 ReviewTask 和业务知识系统，停止旧 Memory 写入 Career 数据。
2. Phase B 实现 `AgentTaskPort`、`CareerTaskContextBuilder`、ProviderPolicy，用于 Mail Agent。
3. Phase C 实现结构化业务记忆、CareerContextAssembler 和策略任务。
4. Phase D 扩展到岗位、简历 Drafter–Reviewer，并增强 Tool 权限。
5. Phase E 接入面试任务，完成 AgentLoop 双模式、统一 Cron、Channel 通知和工具策略的长期运行验证。

旧 Career Store 和粗糙 Career Tool 不需要数据迁移；移除启动引用和旧测试后可直接删除。CareerConsole AgentLoop、Cron、Channels、Tools 等通用能力则按上述方向保留和改造，不纳入无差别清理范围。
