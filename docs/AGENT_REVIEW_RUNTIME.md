# AgentRun 与统一审查运行时

## 业务边界

- `AgentRun` 是后台业务 Agent 的审计记录，不是聊天 Session，也不保存业务正式状态。
- `ReviewTask` 是跨业务模块的人工确认投影；正式变化仍由事实、申请、面试等 Application Command 执行。
- Agent 输出只能生成 Proposal、草稿或待审对象，不能直接写入 confirmed 事实或申请进度。
- 审计 API 返回模型、Schema、哈希、Token、耗时和错误，不返回简历或邮件全文。

## 当前接入

| 业务来源 | ReviewTask 类型 | AgentRun 关联 |
|---|---|---|
| 简历事实提取 | `candidate_fact_review` | 是 |
| 手动新增事实 | `candidate_fact_review` | 否 |
| 申请事件候选 | `application_event_proposal` | 后续邮件 Agent 接入 |
| 面试改进建议 | `interview_feedback` | 后续面试 Agent 接入 |

所有创建和完成动作复用 `review_runtime.py`，与业务对象保持同一数据库事务。旧的 Workspace 审查查询已转发到统一 Runtime Service，不再维护第二套队列映射。

## API

```text
GET /api/v1/runtime/reviews?status=open
GET /api/v1/runtime/reviews/{id}
GET /api/v1/runtime/agent-runs?limit=100
GET /api/v1/runtime/agent-runs/{id}
```

审查详情的 `target_url` 指向对应业务确认页面。统一 API 不提供通用“确认”接口，因为事实确认、申请状态转换和面试建议确认具有不同的领域规则。

## AgentRun 审计字段

- 任务、执行模式、实现、Provider、模型；
- Prompt、Skill、输入和输出 Schema 版本；
- 输入业务对象、revision、输入输出哈希；
- 工具调用摘要，后台任务默认空；
- Token、耗时、重试次数和错误码；
- 敏感级别和保留期限。

数据库 revision：`20260726_0021`。
