# Part 5 用户验收指南：任务、提醒与今日 Dashboard

Part 5 已进入 `user_acceptance`。本阶段提供本地任务、提醒、通知和可靠调度，不发送邮件或短信，不同步第三方日历，也不调用或开发 OpenCLI。

## 1. 升级数据库

```powershell
.\.venv\Scripts\python.exe -m career_console db migrate
.\.venv\Scripts\python.exe -m career_console doctor
```

迁移前会创建 SQLite 一致性备份。预期：

```text
DB revision  20260724_0006  20260724_0006  PASS
```

## 2. 启动

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

打开 `http://127.0.0.1:8765`。根页面现在进入“今日概览”，侧栏新增“任务日程”。

## 3. 实际验收流程

1. 在“任务日程”创建一个关联真实申请的“投递计划”，时间设为今天稍后。
2. 为任务分别增加“提前 1 天”和“提前 1 小时”提醒；重复点击相同提醒不应产生重复记录。
3. 在申请详情添加未来笔试或面试事件，再打开任务页；该事件应自动同步为任务，并保留申请、公司和岗位关联。
4. 创建两个相差不足 30 分钟的笔试或面试任务；Dashboard 应提示时间冲突。
5. 检查“今日概览”的今日待办、逾期任务、未来 7 天流程、待审事项和未读通知。
6. 延后一个尚未触发提醒的任务；任务时间、Reminder 时间和持久化 Schedule 应同步后移。
7. 完成一个任务，确认其未触发提醒被取消；再创建一个任务并执行取消。
8. 停止并重新启动服务，确认任务、提醒和处理状态不丢失；启动过程会恢复过期 lease 并补偿已错过的 Schedule。
9. 到达提醒窗口后点击 Dashboard 的“立即检查提醒”；应只生成一条本地通知。重复检查不得重复通知。
10. 将通知标记已读，确认未读计数下降。
11. 如后台任务失败或取消，在“后台任务”中执行重试，确认尝试次数从新的执行周期重新计算。

## 4. 使用测试时钟验证提醒

无需修改系统时间。先从任务页面记录提醒计划时间，然后调用本地调度入口：

```powershell
$body = @{ now = "2026-07-25T09:00:00+08:00" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/scheduler/run-due -ContentType application/json -Body $body
```

将 `now` 改为该提醒计划时间之后。返回值中的 `reminders_triggered` 首次应增加，再次使用相同时间调用应为 `0`。

## 5. 关键边界

- 数据库存储 UTC，并保留任务的 IANA 时区；页面按 `Asia/Shanghai` 展示。
- 夏令时不存在的本地时间会被拒绝，不会静默偏移。
- Task 使用版本号防止并发覆盖；过期页面会收到 `version_conflict`。
- Schedule 支持 once、interval，以及受控的每日 cron 表达式。
- 到期处理采用 Schedule → Outbox → Notification；Outbox 重放不会重复产生通知。
- SSE 仅发送实体 ID 和事件类型，不发送简历、备注或其他敏感正文。
- 本阶段通知只在应用内保存，不进行外部发送。

## 6. 反馈格式

请提供任务类型、计划时间、时区、提醒偏移、操作步骤、页面提示和预期结果。不要提供账号、Cookie、Token、API key 或私人联系方式。
