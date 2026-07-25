# Windows 本地安装与运行

Nanobot Career 的首发主平台是 Windows，业务数据默认位于 `%USERPROFILE%\.nanobot\career`。OpenCLI 是外部可选应用，本项目不会安装、修改或发布它。

## 源码环境

```powershell
cd D:\project\job-agent\nanobot-career
.\.venv\Scripts\python.exe -m nanobot career setup
.\.venv\Scripts\python.exe -m nanobot career doctor
.\.venv\Scripts\python.exe -m nanobot career serve
```

浏览器打开 `http://127.0.0.1:8765`。服务拒绝非 loopback Host；不要通过公网端口转发暴露。

## 升级

```powershell
.\.venv\Scripts\python.exe -m nanobot career db migrate
.\.venv\Scripts\python.exe -m nanobot career doctor
```

升级会先生成数据库备份。正式升级前建议额外执行：

```powershell
.\.venv\Scripts\python.exe -m nanobot career data backup
```

## 备份、导出和恢复

```powershell
.\.venv\Scripts\python.exe -m nanobot career data backup
.\.venv\Scripts\python.exe -m nanobot career data export
.\.venv\Scripts\python.exe -m nanobot career data gc
```

恢复前先停止 Web 服务：

```powershell
.\.venv\Scripts\python.exe -m nanobot career db restore <backup.zip> --confirm RESTORE
```

完整备份包含 SQLite、Blob、PDF/导出文件和 SHA-256 清单，不包含 Windows Credential Manager 中的授权码。恢复后如邮箱 Secret 不存在，需要在消息中心重新录入。

## 可选外部 OpenCLI

只有启用 BOSS Connector 时才需要 Node.js 和 OpenCLI。Career 只调用外部 OpenCLI 的只读登录状态、搜索和详情命令；安装与登录按 OpenCLI 项目自身说明完成。
