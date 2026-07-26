# CareerConsole

CareerConsole 是本地优先的 AI 求职工作台。它围绕用户职业档案、岗位机会、投递进度、邮件智能、任务提醒、岗位匹配和简历版本建立可追溯的业务数据，而不是把聊天记录当作产品状态。

当前项目处于分阶段开发期，后端使用 Python/FastAPI/SQLite，前端使用 React/TypeScript。Agent Runtime、Channel、Cron 和工具能力将作为 CareerConsole 的内部基础设施继续演进。

## 当前能力

- 结构化职业档案、事实库和档案洞察；
- 岗位池、岗位匹配与每日岗位数据源；
- 投递时间线、邮件只读同步与结构化邮件分析；
- 待办、提醒、面试准备和 Dashboard；
- 简历方向规划、生成、独立审核、事实引用和版本差异；
- 独立 Workspace、数据库迁移、备份目录和 Web 设置入口。
- 带 manifest/SHA-256 的工作区迁移包，以及可选 AES-256-GCM 加密凭据 Vault。

## Windows 源码启动

项目已有虚拟环境时始终使用 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

浏览器打开 `http://127.0.0.1:8765`。首次启动自动进入 Bootstrap 初始化向导：先选择正式工作区，再按需配置 AI、职业档案、邮箱、OpenCLI/牛客、通知渠道和自动任务。除工作区外均为可选能力；完成后服务自动重启进入 Product 模式。以后仍可在“设置”中修改配置或重新打开向导。

`workspace create`、`setup` 和 `doctor` 保留给运维、自动化和故障修复，普通用户首次使用不需要预先执行。也可用已安装的入口运行 `career-console serve`。

详细说明见：

- [文档索引](docs/README.md)
- [产品功能设计](docs/product/product-function-design.md)
- [技术实现方案](docs/architecture/technical-implementation-plan.md)
- [Workspace Foundation](docs/operations/workspace.md)
- [工作区迁移包与加密 Vault](docs/operations/portable-workspace.md)
- [Windows 安装与运行](docs/operations/windows-install.md)

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console career_console tests\product
cd web
npm test -- --run
npm run build
```

## 数据与安全

CareerConsole 默认只绑定本机地址。密钥不得写入普通配置、日志或默认导出。工作区切换不进行运行时热切换；创建并激活新工作区后必须重启服务。

发布边界统一使用 `CareerConsole`、`career_console`、`career-console` 和
`CAREER_CONSOLE_`。业务代码遵守 Domain → Application → Infrastructure/Interfaces
的单向依赖规则；通用 Agent 能力封装在 `career_console.runtime`。

## License

CareerConsole 使用 [MIT License](LICENSE)。衍生代码的上游版权与许可见
[第三方声明](THIRD_PARTY_NOTICES.md)。
