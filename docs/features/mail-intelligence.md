# Agent 邮件智能（mail_intelligence.v1）

数据库 revision：`20260726_0021`。

## 当前链路

```text
只读 IMAP（已读 + 未读，最长 30 天）
→ 邮件证据摘录 + 持久化 BackgroundJob
→ 独立 worker 租约消费 / 指数退避 / 最多三次自动尝试
→ 共享 AgentRunner / task mode / tools=None
→ mail_intelligence.v1 + 原文证据校验
→ AgentRun（敏感数据审计）
→ MailIntelligenceAnalysis + 多个 Item
→ 每个 Item 对应统一 ReviewTask
→ 用户确认
→ 匹配事件写入 Application 时间线；日程写入 CareerTask
```

邮件正文始终是不可信数据。该任务不会加载聊天 Session、SOUL、Workspace Memory 或 Skills，不注册工具，也不会发送、移动、删除或标记邮件。模型输出中的应用 ID 必须来自最小候选列表；事件、日程和注意事项的 evidence 必须是邮件证据的原文子串；所有时间必须带时区并归一化为 `Asia/Shanghai`。

## API

- `POST /api/v1/mail/messages/{message_id}/analyze`：幂等分析单封已抓取正文的邮件。
- `POST /api/v1/mail/intelligence-items/{item_id}/resolve`：确认或拒绝候选。
- `GET /api/v1/mail/messages`：返回邮件及其最新结构化分析。
- `GET /api/v1/runtime/reviews`：统一审核队列。
- `GET /api/v1/runtime/agent-runs`：不回显邮件正文的运行审计。

默认 `CAREER_CONSOLE_MAIL_INTELLIGENCE_MODE=agent`。模型与 Provider 继续使用 CareerConsole 现有配置；若未配置，邮箱连接和只读同步仍可使用，但分析接口明确返回 `mail_intelligence_unavailable`，不会降级为可信自由文本。

## 下一步

新邮件同步后会幂等进入 `mail.intelligence.analyze` 后台任务；Worker 与 IMAP 同步事务分离，因此模型延迟或失败不会阻止游标提交。失败任务保留脱敏错误码，可在后台任务页面人工重试。消息中心仍保留单封手动分析入口。

匹配到现有申请的分析会显示在申请详情“招聘邮件证据”区域。无匹配分析不会直接伪造 JobPost 或 Application：用户必须导入真实完整 JD，在岗位详情确认“加入申请跟踪”；系统随后把邮件分析、岗位和申请关联起来。
