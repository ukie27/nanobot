# CareerConsole Workspace Foundation

本文定义 CC-1 已实现的工作区边界和验收方式。

## 目录模型

用户选择父目录后，CareerConsole 创建固定名称的子目录：

```text
<父目录>/CareerConsole/
├── workspace.json
├── config/
├── data/career-console.sqlite3
├── secrets/
├── blobs/
├── exports/
├── backups/
├── logs/
├── integrations/
└── runtime/
```

`workspace.json` 是可移植的工作区身份清单，不保存 API Key、邮箱授权码或其他密钥。`runtime/` 只保存锁、写入探针等可重建状态。

## 启动边界

Windows 上的 `%LOCALAPPDATA%\CareerConsole\bootstrap.json` 只保存当前工作区路径、workspace ID 和更新时间。业务数据库、配置、日志和文件均不进入该目录。

工作区解析优先级：

1. CLI 的 `--workspace` 显式路径；
2. `CAREER_CONSOLE_WORKSPACE`；
3. bootstrap 中已激活的路径；
4. 首次启动临时默认路径。

无已激活工作区时，第 4 项是 `%LOCALAPPDATA%\CareerConsole\workspaces\default` 机器级 Bootstrap 控制面。它不作为正式业务工作区。前端创建或激活正式工作区后返回 `restart_required=true`，服务会原位自动重启；数据库连接和后台任务不会热切换。

## 首次初始化与运行模式

普通用户始终使用一个启动命令：

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

- `Bootstrap`：只提供初始化控制面；Scheduler、邮件轮询、岗位同步、Channel 分发和其他自动业务任务不启动。
- `Product`：`config/onboarding.json` 已记录当前 onboarding 版本完成，重启后才启动已启用的业务 Runtime。
- 正式工作区是唯一必选项；邮箱、OpenCLI/牛客、QQ 等能力均可跳过并在设置中补充。
- Windows 本地运行时可点击“选择文件夹”打开系统原生目录选择器；无图形界面的容器环境仍可手动输入绝对路径。
- “设置 → 高级诊断 → 重新进入初始化向导”会恢复 Bootstrap 状态并要求重启。

## 安全规则

- 拒绝磁盘根目录、用户主目录本身和源码目录作为父目录；
- 拒绝目标位置已存在、非空且没有合法 `workspace.json` 的目录；
- 所有清单写入使用同目录临时文件、`fsync` 和原子替换；
- 支持 Windows 空格和 Unicode 路径；
- 普通配置和导出不得包含明文密钥；
- 导入导出、完整性清单和加密密钥包属于 CC-5，不在 CC-1 内假装提供。

## 验收命令

请使用测试目录，不要覆盖正在使用的工作区：

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

首次进入应只显示初始化向导，且正式工作区创建前不能继续。创建后服务应自动重启并继续向导；完成向导后再次自动重启，主产品导航才出现。前端“设置”应能看到根目录、数据库、配置、备份和导出路径。

自动化门禁：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product\test_workspace_foundation.py -q
.\.venv\Scripts\python.exe -m pytest tests\product\test_onboarding_runtime.py -q
.\.venv\Scripts\python.exe -m ruff check career_console tests migrations
cd web
npm test -- --run
npm run build
```
