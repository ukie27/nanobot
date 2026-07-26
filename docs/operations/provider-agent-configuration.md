# CareerConsole Provider 与 Agent 配置

CC-3 在数据库 revision `20260726_0023` 引入模型 Provider、系统凭据和业务 Agent 任务路由。后续 revision 不改变本文件描述的安全边界。

## 配置边界

非敏感 Provider 元数据保存在 `<workspace>/config/application.json` 的 `providers` 分区，包括类型、显示名称、API URL、默认模型、可选模型和 `secret_ref`。`agents.tasks` 为七类业务任务保存启停、Provider、模型、Temperature、最大 Token 与 reasoning effort：

- `fact_extraction`：事实提取；
- `mail_intelligence`：招聘邮件结构化分析；
- `profile_insight`：档案洞察；
- `job_fit`：岗位匹配；
- `resume_direction`：简历方向；
- `resume_drafting`：简历撰写；
- `material_review`：材料复核。

Drafter 与 Reviewer 是独立任务映射，可以使用不同 Provider 和模型。任务引用不存在的 Provider、非法 Provider ID 和不属于当前 Provider 的密钥引用会被 Schema 拒绝。

## SecretReference 与 Keyring

API Key 不写入 JSON、SQLite 配置快照、配置变更审计、日志或 API 响应。默认凭据存储为操作系统 Keyring，service 名为 `CareerConsole`，引用格式为：

```text
career-console:<workspace_id>:provider:<provider_id>:api-key
```

设置页的 API Key 输入框仅用于新增或轮换：保存后清空且不回显。更新配置发生 revision 冲突时，新建的凭据会删除，轮换的凭据会恢复旧值。删除 Provider 前必须先解除全部 Agent 任务引用。

## Runtime 读取路径

`CareerAgentRuntime` 在执行每个业务任务时读取当前工作区配置，解析任务映射并由 `CareerProviderFactory` 从 Keyring 获取密钥、构建 Provider。Career Agent 创建路径不再读取用户目录下的旧配置文件。配置更新标记为 `restart_required`；重启后所有 Agent 工厂使用新的工作区配置。

现阶段 Provider 的底层协议实现仍复用已有内部模块，属于 CC-6 完成包迁移前的实现桥，不形成第二套产品配置或运行路径。

## 连接测试与脱敏

连接测试只发送最小探测请求，模型返回正文会立即丢弃。`provider_connection_test_runs` 仅记录 Provider ID/类型、模型、通过或失败、脱敏错误码、耗时和时间。不会保存 Prompt、Response、API Key 或底层异常正文。

错误码限定为 `credential_missing`、`timeout`、`provider_rejected` 或 `connection_failed`。

## API

```text
GET    /api/v1/configuration/provider-catalog
GET    /api/v1/configuration/providers
PUT    /api/v1/configuration/providers/{provider_id}
DELETE /api/v1/configuration/providers/{provider_id}
PUT    /api/v1/configuration/agents
POST   /api/v1/configuration/providers/{provider_id}/test
GET    /api/v1/configuration/provider-tests
```

所有变更接口受本地安全会话与 CSRF 保护，并使用 configuration revision 做乐观并发控制。

## 自动化验收

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product\test_provider_agent_configuration.py -q
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console career_console tests\product migrations\versions\20260726_0023_provider_agent_configuration.py
git diff --check
cd web
npm test -- --run
npm run build
```

人工验收时，在设置页新增 Provider、输入一次 API Key、执行连接测试、分别为 Drafter 与 Reviewer 选择模型，然后重启 CareerConsole 并运行对应业务任务。页面、网络响应、`application.json`、SQLite 审计和日志中均不应出现 API Key。
