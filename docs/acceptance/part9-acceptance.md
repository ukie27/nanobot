# Part 9 用户验收指南：集成、数据治理与发布

本指南供 Part 0–9 全部开发完成后的统一验收使用，目前不执行真实数据删除或恢复。

## 全链路

1. 在“全链路工作区”核对申请漏斗、每日/每周简报、最近状态变化和面试/改进指标。
2. 使用公司或岗位关键词跨模块搜索岗位、材料、申请、任务和面试，并检查实体跳转。
3. 核对统一审查队列同时包含申请事件 Proposal 和 Interview Feedback。

## 数据治理

1. 创建完整备份，检查 ZIP 包包含 `career.sqlite3`、Blob、导出文件及 `manifest.json` SHA-256 清单，不包含 Keyring Secret。
2. 导出 JSON，检查全部业务表可读且没有邮箱授权码明文。
3. 在独立临时数据目录执行：

```powershell
.\.venv\Scripts\python.exe -m career_console db restore <backup.zip> --confirm RESTORE --data-dir <temp-dir>
```

4. 恢复后执行 `career doctor`，数据库 revision 应为 `20260726_0021`。
5. Blob 垃圾回收只能删除数据库未引用文件，并按配置清理过期 Agent trace。
6. 删除单一 Connector 必须输入 `DELETE <connector_type>`；删除全部数据必须输入 `DELETE ALL CAREER DATA`，并先自动创建恢复包。
7. 在工作区查看“跨模块一致性”，确认申请时间线、投递快照、面试任务、事件关联和统一审查队列没有 error；历史不完整数据允许以 warning 明确展示。
8. 在 Web 中分别以 `DELETE opencli_boss` 和 `DELETE imap_readonly` 验证单 Connector 删除，仅在隔离测试数据目录执行。

## 发布安全

- Web 只允许 loopback Host。
- 浏览器写请求必须通过本地会话 Cookie、CSRF token 和 Origin 校验。
- 响应包含 CSP、`nosniff`、Referrer Policy 和禁用麦克风/摄像头权限策略。
- 日志默认保留 14 天并脱敏；Agent trace 默认保留 30 天。
- OpenCLI 仍为外部应用，本项目不修改或发布 OpenCLI。
- 浏览器的 JSON、文件上传和删除请求全部使用同一 Session/CSRF 边界。
