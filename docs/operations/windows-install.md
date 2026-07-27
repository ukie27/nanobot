# CareerConsole Windows 本地安装与运行

CareerConsole 当前以 Windows 本地单用户应用方式运行。业务数据位于用户选择的独立工作区；应用不会把新数据写入旧的隐藏目录。OpenCLI 是外部可选应用，本项目只调用它，不修改或发布其源码。

## 当前交付边界

当前版本是源码开发启动，不是最终 Windows 安装包。使用者需要先准备项目依赖和 `.venv`；未来面向普通用户的安装包、桌面快捷方式、独立 Launcher、自动升级和崩溃恢复不属于当前交付。

## 普通用户源码启动

在项目根目录只需执行：

```powershell
.\.venv\Scripts\python.exe -m career_console serve
```

浏览器打开 `http://127.0.0.1:8765`。服务只允许绑定本机 loopback 地址，不应通过公网端口转发暴露。

首次启动会进入初始化向导。用户在前端选择父目录后，CareerConsole 创建独立工作区，并继续配置 AI、职业档案、招聘来源、只读邮箱、通知和自动任务。除工作区外，其余能力均可跳过，之后仍可在“设置”中保存和单独测试。

前端目录选择器仅适用于浏览器与 CareerConsole 服务运行在同一台有桌面会话的 Windows 机器。无桌面环境应手动输入服务端绝对路径。

## 高级启动与自动化

CLI 显式工作区适用于开发、自动化和故障排查，优先级高于前端激活记录：

```powershell
.\.venv\Scripts\python.exe -m career_console serve --workspace "D:\CareerWorkspace\CareerConsole"
```

也可以设置：

```powershell
$env:CAREER_CONSOLE_WORKSPACE = "D:\CareerWorkspace\CareerConsole"
```

其他运行参数统一使用 `CAREER_CONSOLE_` 前缀。Provider、Agent、邮箱、OpenCLI、QQ Channel 和 Scheduler 已集成到初始化向导与设置中心，不建议为普通配置继续增加手工环境变量流程。

## 升级与诊断

```powershell
.\.venv\Scripts\python.exe -m career_console setup
.\.venv\Scripts\python.exe -m career_console doctor
.\.venv\Scripts\python.exe -m career_console status
```

这些命令是高级排障入口，不是首次启动前置步骤。`setup` 在已有数据库上执行迁移前会先创建备份。设置中心已经支持带 manifest 和 SHA-256 校验的工作区迁移包，以及可选的加密凭据 Vault；不要手工复制正在运行的 SQLite 文件。

## 工作区切换限制

当前服务会在切换前验证候选工作区，并通过同进程 `execv` 重启应用。若新进程启动失败，会回滚激活记录，但原进程已经退出，因此这不等同于零中断切换。

工业级 Windows 交付仍需要独立 Launcher：

```text
保留旧实例
→ 启动候选实例
→ 检查候选实例 /health/ready
→ ready 后关闭旧实例
→ 失败时继续使用旧实例
```

在 Launcher 完成前，不应把当前切换机制描述为双实例 ready 切换。

## 可选 OpenCLI

只有启用相应数据源时才需要 Node.js 和 OpenCLI。CareerConsole 仅调用外部 OpenCLI 的登录状态、页面查询和详情命令；安装、浏览器扩展和登录按 OpenCLI 项目自身说明完成。
