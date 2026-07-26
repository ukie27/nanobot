# CareerConsole 统一配置基础

CC-2 建立了强类型、版本化、可审计且不允许保存密钥的工作区配置系统。数据库 revision 为 `20260726_0022`。

## 配置文件

当前非敏感配置写入：

```text
<workspace>/config/application.json
```

文件包含 `schema_version`、单调递增的 `revision`、UTC 更新时间和完整 `configuration`。未知字段会被拒绝，前端不能提交任意 JSON 覆盖文件。

配置写入使用同目录临时文件、flush、`fsync` 和原子替换。API 使用 `expected_revision` 做乐观并发控制；旧页面提交返回 HTTP 409，不会覆盖较新的设置。

## 配置分区

- `general`：语言、业务时区、日期格式和启动行为；
- `appearance`：界面密度和减少动效；
- `runtime`：日志级别、日志/Agent 审计保留期、任务租约和文档上限；
- `privacy`：诊断元数据开关，以及不可关闭的敏感日志脱敏和仅本机绑定。

API Key、Token、邮箱授权码、Cookie 和 OAuth Session 不属于该 Schema。CC-3 使用 `SecretReference` 与系统凭据库接入，普通配置 API 仍不会返回密钥值。

## 生效语义

- 外观密度和减少动效：`hot_reload`，前端立即应用；
- Runtime 参数：`restart_required`，下次 CLI/Web 启动时在构造服务前加载；
- 多字段同时变更时返回其中最强的生效要求；
- 页面保存后展示当前 revision、变更路径和是否需要重启。

`active_revision` 表示当前进程已经应用的版本。纯热更新会推进 active revision；包含重启参数的版本在重启前保持 `restart_required`。

## 审计

数据库保存：

- `configuration_snapshots`：每个 revision 的非敏感完整快照与 SHA-256；
- `configuration_changes`：前后 revision、变更字段、变更原因、生效方式和时间。

配置文件写成功但审计事务失败时，服务会原子恢复旧文件。审计表和配置文件均不允许出现密钥。

## API

```text
GET /api/v1/configuration
PUT /api/v1/configuration
GET /api/v1/configuration/schema
GET /api/v1/configuration/changes
```

## 自动化验收

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product\test_configuration_foundation.py -q
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console career_console tests\product
cd web
npm test -- --run
npm run build
```
