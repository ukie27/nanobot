# CareerConsole 代码结构与依赖规则

## 1. 顶层模块

```text
career_console/
├── domain/          # 实体、值对象、纯业务规则
├── application/     # 用例服务与外部能力端口
├── infrastructure/  # 数据库、外部系统、配置和运行适配器
├── interfaces/http/ # FastAPI 路由、中间件和 Web 静态资源
├── runtime/         # 通用 AgentLoop、Provider、Channel、Cron 和 Tools
├── cli.py           # CareerConsole 唯一命令行入口
└── __main__.py
```

`infrastructure/workspace/onboarding.py` 持有版本化初始化状态；`interfaces/http/routes/onboarding.py` 暴露 Bootstrap 控制面。应用 lifespan 只在 onboarding 完成后创建 Scheduler 循环并执行启动期任务。初始化向导本身可以读取和保存配置，但不会启动邮件扫描、岗位同步或 Channel 分发。

## 2. 依赖方向

- `domain` 不依赖 Application、Infrastructure、Interfaces 或 Web/ORM 框架。
- `application` 只依赖 Domain 和自身 Ports，不导入具体数据库、HTTP 或外部 CLI。
- `infrastructure` 实现 Application Ports，并可调用通用 `runtime`。
- `interfaces` 将 HTTP 输入转换为 Application 调用；应用装配只在接口层的应用工厂中发生。
- `runtime` 不访问 CareerConsole 业务数据库，不持有另一套 Career Store。

这些规则由 `tests/product/test_architecture_boundaries.py` 自动检查。

## 3. 数据所有权

- SQLite/Alembic 数据库是业务事实的唯一持久化来源。
- `application.json` 保存非敏感配置；密钥仅通过 Secret Store 保存。
- Workspace 模块控制所有用户数据路径、备份和迁移包。
- Agent Session 和通用工具文件位于 Workspace 的 `runtime/` 下，不承担业务档案职责。
- `config/onboarding.json` 只记录初始化版本、完成时间和跳过的可选步骤，不复制业务事实或普通配置。

## 4. 进程生命周期

```text
career-console serve
→ 解析正式工作区或机器级 Bootstrap 路径
→ 初始化 HTTP 控制面
→ onboarding 未完成：Bootstrap 向导
→ onboarding 完成：启动 Product Runtime
```

创建/导入工作区或完成/重新打开向导时，通过受控的进程原位重启重新装配数据库与 Runtime。运行中不热切换工作区。

## 5. 扩展位置

- 新业务能力：先在 `domain` 建模，再添加 `application/ports` 和 `application/services`。
- 新数据库实现：放入 `infrastructure/database`。
- 新外部数据源：放入 `infrastructure/connectors`，通过 Application Port 接入。
- 新 HTTP 功能：放入 `interfaces/http/routes`。
- 新通用 Agent Tool 或 Channel：放入 `runtime`；业务专用 Tool 必须调用 Application Port，不能建立独立数据库。
