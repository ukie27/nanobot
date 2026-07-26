# CareerConsole 数据源、Channel 与 Scheduler

CC-4 将外部数据源、只读邮箱、通知 Channel 和业务调度纳入工作区配置中心。当前数据库 head 为 `20260726_0026`。

## 配置所有权

`<workspace>/config/application.json` 是用户配置的唯一主源：

- `connectors.opencli`：外部 OpenCLI 可执行文件、牛客和可选 BOSS 参数；
- `connectors.imap`：只读邮箱的非敏感连接参数、最长 30 天边界和轮询周期；
- `channels.qq`：outbound-only 通知目标、事件订阅、格式和免打扰；
- `scheduler`：总开关、检查周期以及提醒、Connector、档案维护和 Channel 分发开关。

SQLite 只保存同步游标、健康状态、运行历史、站内通知、Channel Delivery 和 SchedulerRun。revision `0024` 修复了牛客与 IMAP 共用 Connector ID 的旧问题；`0025`、`0026` 分别增加脱敏 Channel 和 Scheduler 审计。

## 密钥边界

邮箱授权码和 QQ App Secret 只进入系统 Keyring：

```text
career-console:<workspace_id>:connector:imap:password
career-console:<workspace_id>:channel:qq:secret
```

既有 `imap-account:primary` 会在启动时迁移。API、JSON、SQLite 审计、日志和前端 DOM 不返回密钥值；revision 冲突会恢复旧凭据。

## 调度流程

```text
配置驱动循环
→ 到期任务与 Reminder Outbox
→ 牛客当天同步 / IMAP 只读轮询
→ 邮件 Agent 后台任务
→ 北京时间档案维护
→ 站内通知
→ 订阅与免打扰过滤
→ QQ 目标发送
→ 脱敏 Delivery/SchedulerRun 审计
```

各子系统失败互相隔离，只记录稳定错误码。QQ 目标以 `c2c:<openid>` 或 `group:<openid>` 配置，审计中只保留 SHA-256 摘要。成功目标不会重复发送；失败目标按 `send_max_retries` 重试。

## API

```text
GET/PUT /api/v1/connectors/opencli
GET/PUT /api/v1/connectors/nowcoder
GET/PUT /api/v1/connectors/boss
GET/PUT/DELETE /api/v1/mail/account
GET/PUT/DELETE /api/v1/channels/qq
POST /api/v1/channels/qq/test
GET /api/v1/channels/deliveries
GET/PUT /api/v1/scheduler/configuration
POST /api/v1/scheduler/run-due
GET /api/v1/scheduler/runs
```

## 验收

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console career_console tests\product migrations\versions
git diff --check
cd web
npm test -- --run
npm run build
```

真实 QQ 测试需要用户自己的 App ID、App Secret 和 OpenID；自动化测试使用发送适配器替身，验证正文和凭据不会进入审计。
