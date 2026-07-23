# Part 0 用户验收指南

> 当前状态：`user_acceptance`<br>
> 适用环境：Windows PowerShell 7<br>
> 验收目标：确认工程底座和本地应用壳能在真实使用环境中稳定启动、停止、诊断和备份。

## 1. 已交付能力

- 项目 `.venv`、Python 3.12 和锁定的 `uv.lock`。
- `nanobot career` 独立产品入口，不影响原有 Agent CLI。
- FastAPI Career 服务与嵌入式 React 页面。
- SQLite WAL、SQLAlchemy、Alembic 初始迁移和 Unit of Work。
- `/health/live`、`/health/ready` 和系统状态接口。
- RFC 9457 Problem Details、correlation ID 和日志脱敏。
- 持久化后台任务表、过期 lease 启动恢复骨架和只读任务列表。
- 单实例锁、`doctor`、数据库迁移和一致性备份。

Part 0 不包含候选人档案、岗位、简历材料或申请管理功能。OpenCLI 在本阶段不接入；后续仅作为外部应用使用，本项目不开发 OpenCLI 本体。

## 2. 开始前检查

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m nanobot career doctor
```

预期：

- Python、数据目录和 Web 端口显示 `PASS`。
- 首次运行时数据库可以显示 `not initialized`，这不是失败。
- OpenCLI 可以显示 `not installed`，在 Part 0 属于可选项。

## 3. 初始化数据库

```powershell
.\.venv\Scripts\python.exe -m nanobot career db migrate
```

预期看到：

```text
Database migrated: 20260723_0001
```

再次执行 `doctor`，数据库完整性和 revision 应显示 `PASS`。

## 4. 启动和浏览器验收

```powershell
.\.venv\Scripts\python.exe -m nanobot career serve
```

浏览器打开：

```text
http://127.0.0.1:8765
```

请实际检查：

1. 页面显示“运行状态”和“后台任务”两个入口。
2. 运行状态为“服务就绪”。
3. 数据库显示“正常”，Schema revision 为 `20260723_0001`。
4. 页面显示数据、数据库、日志和备份的真实本地路径。
5. 后台任务页为空，并明确说明 Part 0 尚无业务任务。
6. 在浏览器地址栏直接访问 `http://127.0.0.1:8765/status`，页面仍能正常显示。

## 5. 单实例验收

保持第一个服务运行，在第二个 PowerShell 窗口执行：

```powershell
.\.venv\Scripts\python.exe -m nanobot career serve --port 8766
```

预期第二个实例被拒绝，并提示已有实例持有 Career lock。端口不同也不允许同一数据目录启动两个实例。

## 6. 数据库备份验收

在第二个 PowerShell 窗口执行：

```powershell
.\.venv\Scripts\python.exe -m nanobot career db backup
```

预期在 `doctor`/状态页显示的备份目录中生成：

```text
career-YYYYMMDD-HHMMSS-ffffff.sqlite3
```

备份使用 SQLite backup API，可在服务运行期间生成一致性副本。

## 7. 重启验收

1. 在服务窗口按 `Ctrl+C` 停止服务。
2. 再次执行 `nanobot career serve`。
3. 页面应继续显示同一数据库路径和 revision。
4. 再次执行 `doctor`，所有必需检查仍应通过。

## 8. 验收反馈

请记录以下信息，但不要粘贴 API key、Cookie、Token 或隐私数据：

- 哪一步与预期不一致。
- 页面或命令显示的错误摘要。
- correlation ID（如果页面提供）。
- `career.log` 中对应时间点的脱敏错误类型。

完成上述操作并确认体验后，Part 0 才从 `user_acceptance` 更新为 `accepted`，随后进入 Part 1。
