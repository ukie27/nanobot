# Nanobot Runtime 保留与隔离清单

本项目不整体重写原 nanobot Agent Runtime。Part 9 先冻结职责边界，实际长期运行测试后再删除确认造成维护负担的模块。

| 现有能力 | 当前处置 | 原因 |
|---|---|---|
| Provider registry、Agent loop、Tool registry | 保留并隔离 | 后续受控生成任务仍可能复用，但不能直接写 Career 领域表 |
| Career FastAPI、领域服务、Repository、Scheduler | Career 主路径 | 所有求职业务状态的唯一写入口 |
| 原 Email Channel | 隔离保留、默认不用于 Career | 它可能修改邮件状态，绝不能替代只读 IMAP Connector |
| Cron/通用后台任务 | 保留基础设施，业务调度走 Career 持久 Schedule | 避免形成第二套业务游标和幂等规则 |
| Session/Memory | 不作为 Career 事实来源 | 候选人事实必须进入 confirmed Fact 和可审计来源 |
| 通用聊天 Channel | 暂时保留 | 不影响 Career 主路径，未来可作为通知或交互入口 |
| Career 旧 `store.py` / `resume_service.py` 兼容路径 | 隔离，待整体回归后评估删除 | 当前仍可能被原测试或兼容命令引用，不在开发期破坏 |

删除条件：无运行时引用、无安装兼容要求、无未来扩展价值，并在完整回归、数据迁移和用户确认后执行。OpenCLI 始终属于外部项目，不进入本清理范围。
