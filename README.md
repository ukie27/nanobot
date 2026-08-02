# CareerConsole

CareerConsole 是本地优先的 AI 求职工作台。它用结构化、可追溯的业务数据管理职业档案、岗位推荐、简历材料、实际申请、招聘邮件、任务和面试，而不是把聊天记录作为产品状态。

当前唯一持续维护的产品文档是 [CareerConsole 核心业务与使用手册](docs/README.md)。产品定位、完整功能、业务规则、使用流程、配置、运行方式、当前边界和维护约定都以该文档为准。

## 启动

```powershell
.\career-console.cmd
```

浏览器打开 `http://127.0.0.1:8765`。首次启动会进入初始化向导，先选择正式工作区，再按需配置模型、招聘来源、只读邮箱、QQ 通知和自动任务。

首次选择或在前端切换工作区后，CareerConsole 会把当前工作区位置保存在本机 Bootstrap 中。后续启动不需要再传 `--workspace`。`--workspace` 仅用于开发、诊断或一次性覆盖。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\product -q
.\.venv\Scripts\python.exe -m ruff check career_console tests migrations
cd web
npm test -- --run
npm run build
```

CareerConsole 使用 [MIT License](LICENSE)。第三方许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
