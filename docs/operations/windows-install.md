# CareerConsole Windows 本地安装与运行

CareerConsole 当前以 Windows 本地单用户应用方式运行。业务数据位于用户选择的独立工作区；应用不会再把新数据写入旧的隐藏目录。OpenCLI 是外部可选应用，本项目只调用它，不修改或发布其源码。

## 源码环境

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m career_console workspace create "D:\CareerWorkspace"
.\.venv\Scripts\python.exe -m career_console setup
.\.venv\Scripts\python.exe -m career_console doctor
.\.venv\Scripts\python.exe -m career_console serve
```

第一条命令会创建并激活 `D:\CareerWorkspace\CareerConsole`。也可以先启动服务，再在前端“设置”中验证并选择父目录；前端切换后必须重启服务，运行中的数据库不会热切换。

浏览器打开 `http://127.0.0.1:8765`。服务只允许绑定本机 loopback 地址，不应通过公网端口转发暴露。

## 指定工作区

命令行显式路径的优先级最高：

```powershell
.\.venv\Scripts\python.exe -m career_console serve --workspace "D:\CareerWorkspace\CareerConsole"
```

也可以设置：

```powershell
$env:CAREER_CONSOLE_WORKSPACE = "D:\CareerWorkspace\CareerConsole"
```

其他运行参数统一使用 `CAREER_CONSOLE_` 前缀。Provider、Agent、邮箱、OpenCLI、Channel 和调度配置将在设置中心后续阶段接入，不建议继续增加手工环境变量流程。

## 升级与诊断

```powershell
.\.venv\Scripts\python.exe -m career_console setup
.\.venv\Scripts\python.exe -m career_console doctor
.\.venv\Scripts\python.exe -m career_console status
```

`setup` 在已有数据库上执行迁移前会先创建备份。完整的工作区导入导出与加密密钥包将在 CC-5 提供；当前不要手工复制正在运行的 SQLite 文件。

## 可选 OpenCLI

只有启用相应数据源时才需要 Node.js 和 OpenCLI。CareerConsole 仅调用外部 OpenCLI 的登录状态、页面查询和详情命令；安装、浏览器扩展和登录按 OpenCLI 项目自身说明完成。
