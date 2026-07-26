# CareerConsole 产品独立化、工作区与配置中心实施方案

版本日期：2026-07-26  
状态：CC-1 至 CC-6 已完成，进入完整功能验收与缺陷修复阶段

## 1. 命名基线

| 项目 | 最终名称 |
|---|---|
| 产品显示名称 | `CareerConsole` |
| Python 主包 | `career_console` |
| CLI 命令 | `career-console` |
| 环境变量前缀 | `CAREER_CONSOLE_` |
| 默认工作区文件夹 | `CareerConsole` |
| Windows 启动注册目录 | `%LOCALAPPDATA%\CareerConsole` |
| Agent 业务适配器 | `career_console.infrastructure.agent_runtime` |
| 通用 Agent Runtime | `career_console.runtime` |
| 业务领域 | `career_console.domain` / `career_console.application` |

最终产品、页面、日志、CLI、配置、数据库元数据和文档不再暴露旧框架名称。现有 AgentLoop、Provider、Channel、Cron、Tool 等可复用实现已迁入 CareerConsole 内部模块；它们是实现来源，不再是并存产品或兼容层。

## 2. 核心原则

1. CareerConsole 是独立产品，Agent Runtime 只为 CareerConsole 业务服务。
2. 不保留旧框架与 CareerConsole 两套运行路径。
3. 用户可见配置全部通过 Web 设置中心维护。
4. 普通配置进入工作区；密钥进入系统凭据库或加密 Vault。
5. 工作区可迁移、可校验、可导入导出。
6. 工作区切换、恢复和覆盖数据库必须经过停止写入、备份、校验和原子切换。
7. 最终配置以 Schema 为唯一来源，前端表单、后端校验、配置文件和运行时读取使用同一字段定义。
8. 普通用户只有一个启动入口；初始化是产品运行状态，不是必须预先执行的 CLI 命令。

## 3. 工作区架构

用户首次启动时选择一个父目录，CareerConsole 在其中创建：

```text
<用户选择目录>/CareerConsole/
├── workspace.json
├── config/
│   ├── application.json
│   ├── agents.json
│   ├── providers.json
│   ├── channels.json
│   ├── connectors.json
│   └── schedules.json
├── data/
│   └── career-console.sqlite3
├── secrets/
│   └── vault.meta.json
├── blobs/
├── exports/
├── backups/
├── logs/
├── integrations/
└── runtime/
```

`workspace.json` 至少包含 workspace ID、名称、Schema 版本、创建时间、最近打开时间、数据库 revision、产品版本、相对目录和 portable 标记，不包含密钥。

### 3.1 启动注册

应用必须在打开业务数据库前知道工作区位置，因此 Windows 保留最小启动文件：

```text
%LOCALAPPDATA%\CareerConsole\bootstrap.json
```

它只保存最近工作区路径、workspace ID、首次启动状态和 UI 端口偏好，不保存业务数据或凭据。普通用户启动：

```powershell
career-console serve
```

无正式工作区时进入 Bootstrap 初始化向导；创建工作区、完成必选配置后自动重启进入 Product。显式参数仅用于便携运行、开发和运维：

```powershell
career-console serve --workspace "D:\CareerWorkspace\CareerConsole"
```

Bootstrap 模式不启动 Scheduler、邮件扫描、岗位同步或 Channel 分发。邮箱、OpenCLI/牛客、QQ 等是可选能力，跳过后保持关闭，不阻止主产品使用。

### 3.2 目录选择

当前是本地 Web 应用，第一版采用“前端输入绝对路径 → 后端规范化和写入探针验证 → 显示最终目录 → 用户二次确认 → 创建工作区”。后续接入桌面壳后再提供原生目录选择器。后端拒绝系统根目录、用户主目录本身、源码根目录和不可写目录作为递归操作目标。

## 4. 前端设置中心

新增一级导航“设置”，路由 `/settings`。

### 4.1 工作区

- 当前目录、新建、切换和重新定位；
- 空间占用、数据库 revision、完整性检查；
- 立即备份、导入、导出；
- 日志、备份和导出目录。

### 4.2 大模型与 Agent

- Provider、API URL、API Key、Model；
- 超时、重试、并发、Temperature、最大 Token；
- 连接测试和模型列表；
- 默认模型与任务级模型覆盖；
- 邮件分析、档案洞察、岗位匹配、简历方向、Drafter、Reviewer、面试等 Agent 的启停和模型映射。

### 4.3 邮箱与数据源

- IMAP 只读连接和最近 30 天边界；
- OpenCLI 可执行文件和本地插件；
- 牛客每日同步和健康状态。

### 4.4 Channel

- QQ、Telegram、飞书、钉钉、Discord、Webhook；
- enabled、凭据、接收目标、事件订阅、免打扰时间、测试发送和健康状态。

Channel 默认是通知与任务触达出口，不再默认作为自由聊天入口。

### 4.5 定时任务

- 邮件同步、每日岗位、档案摘要；
- 截止时间、测评、笔试和面试提醒；
- Channel 分发、失败重试和告警。

Cron/BackgroundJob 保留并改造成由设置中心管理的业务调度能力。

## 5. 配置 Schema 与写入

新增配置领域：`ConfigurationSchema`、`ConfigurationSnapshot`、`ConfigurationChange`、`SecretReference`、`ConnectionTestRun`。

```text
前端提交
→ Pydantic Schema 校验
→ 敏感字段拆分
→ 普通配置写入临时文件并 fsync
→ 原子替换 JSON
→ 密钥写入 Keyring/Vault
→ 写变更审计
→ hot reload、service reload 或提示重启
```

前端不能提交任意 JSON 覆盖文件；未知字段拒绝。每个字段声明 `hot_reload`、`service_reload` 或 `restart_required`，页面必须显示真实生效状态。

## 6. 密钥

默认使用 Windows Credential Manager/Keyring。跨设备迁移采用可选密码加密 Vault：每次导出使用独立 salt/nonce 和认证加密；数据库、普通 JSON、API 响应和日志均不出现明文密钥。

导出模式：

1. 不包含密钥，默认；
2. 包含密码加密的密钥包，二次确认。

OAuth Session 和浏览器 Cookie 默认不导出，目标设备重新授权。

## 7. 导入导出

导出文件：

```text
CareerConsole-workspace-<workspace-id>-<timestamp>.zip
```

`manifest.json` 记录包格式、产品版本、数据库 revision、文件大小和 SHA-256、密钥包标记、创建时间和来源 workspace ID。

导出流程：暂停写任务 → SQLite 一致性备份 → 收集配置/数据/blobs/exports/integrations → manifest/hash → 可选加密 secrets → 临时 zip → 验证 → 原子移动 → 恢复任务。

导入流程：受控临时解压 → 防 Zip Slip 和资源限制 → 校验 manifest/hash → 兼容性检查 → 内容预览 → 选择新目录 → 数据库迁移和 quick_check → 原子注册 → 重启。禁止覆盖当前运行中的工作区。

## 8. 包结构迁移

目标结构：

```text
career_console/
├── domain/
├── application/
│   ├── ports/
│   └── services/
├── infrastructure/
│   ├── agents/
│   ├── agent_runtime/
│   ├── database/
│   ├── configuration/
│   ├── channels/
│   ├── scheduling/
│   └── workspace/
├── interfaces/
│   └── http/
├── runtime/
└── cli.py
```

- Career 业务按 Domain、Application、Infrastructure、Interfaces 分层；
- AgentLoop/Runner/Provider 等通用能力位于 `career_console.runtime`；
- 业务任务到通用 Runtime 的适配位于 `career_console.infrastructure.agent_runtime`；
- 删除旧通用聊天产品入口和品牌资源；
- 保留可复用 Channel、Cron 和 Tool 实现，由 CareerConsole 配置和权限调用；
- 删除旧框架环境变量、旧隐藏目录和用户可见旧名称；
- 不长期保留两套 import 或运行入口。

## 9. 开发阶段

### 运行状态基线

- `Bootstrap`：初始化 API 与向导可用，自动业务 Runtime 关闭；
- `Product`：当前 onboarding 版本完成，重启后按配置启动 Runtime；
- 设置按“常规与工作区、AI 与 Agent、数据来源、通知渠道、自动任务、数据与迁移、高级诊断”分组；
- 主导航面向求职任务组织，高级运行记录和诊断入口默认折叠。

### CC-1：命名与 Workspace Foundation

- `career_console` 包和 `career-console` CLI；
- WorkspaceManifest、BootstrapRegistry、WorkspacePaths；
- 首次启动状态 API；
- 工作区创建、验证和切换；
- 数据库、日志、备份、blobs、exports 迁入工作区；
- 确认不再新写入旧默认目录。

验收：全新设备可选择目录、创建工作区并启动 CareerConsole。

### CC-2：统一配置领域与设置页面

- 配置 Schema、原子 JSON、变更审计；
- `/settings` 框架；
- reload/restart 状态。

### CC-3：Provider 与 Agent 配置

- Provider CRUD、API URL、Model、连接测试；
- Keyring/Vault；
- 任务级模型映射；
- Agent Runtime 改从新配置读取。

验收：无需手工编辑文件即可运行全部 Agent。

### CC-4：Connector、邮箱、Channel 和 Scheduler

- 迁移邮箱/OpenCLI；
- Channel 配置、测试发送和事件订阅；
- 调度配置、健康状态和失败审计。

### CC-5：工作区导入导出

- 一致性导出、manifest/hash、安全导入；
- 可选加密 secrets；
- 空设备恢复测试。

### CC-6：彻底移除旧名称

- 完成包、前端、CLI、环境变量、文档和构建产物迁移；
- 删除旧入口和临时重定向；
- 全仓扫描，除必要的第三方来源许可文本外不再出现旧名称。

## 10. 测试门禁

- Windows 空格路径和中文路径；
- 路径穿越、重解析点和递归目标边界；
- 配置并发写和崩溃恢复；
- 密钥不进入日志、数据库和普通导出；
- 工作区切换时后台任务停止；
- SQLite 备份、迁移和 quick_check；
- 导出篡改、Zip Slip、资源耗尽和版本不兼容；
- Provider/Channel 超时和错误脱敏；
- 前端表单、API Schema、配置文件 round-trip；
- 全量 CareerConsole 业务回归。

## 11. 下一步

CC-1 至 CC-6 已完成：独立品牌与工作区、统一配置、Provider/Agent 路由、OpenCLI/IMAP、QQ 通知出口、配置驱动 Scheduler、工作区迁移闭环，以及 Python 包、CLI、源码路径、构建边界和 Runtime 品牌迁移均已落地。旧名称仅保留在 `THIRD_PARTY_NOTICES.md` 的上游许可声明和 `docs/archive/` 历史需求材料中；AgentLoop、Channel、Cron/Scheduler 与 Tools 继续作为 CareerConsole 核心运行能力保留。

下一阶段进入完整功能验收与缺陷修复：按设置与工作区、Provider/Agent、邮件档案、岗位同步、材料工作台、提醒与 Channel、迁移包的顺序逐项进行真实数据测试，并将发现的问题纳入回归测试后修复。
