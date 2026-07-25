# Part 0–9 开发完成与统一测试入口

## 当前结论

Part 0–9 的计划内业务能力已经完成开发并进入 `internal_verification`。该状态只表示代码、数据库迁移、Web 入口、操作文档和静态构建链路已经形成，不表示真实邮箱、外部 OpenCLI、备份恢复、删除、升级或长期运行已经验收。

## Part 8 收口能力

- 面试可自动关联同一申请最近且尚未使用的 `interview_scheduled` 事件，也支持显式事件 ID。
- 创建面试时创建或复用派生 Task；改期同步 Task 和活动 Reminder/Schedule；取消或完成面试同步关闭提醒。
- 准备包冻结岗位版本、实际投递快照、confirmed Fact 和 confirmed ImprovementItem。
- Web 手工复盘支持动态 1–50 个问题，不使用录音、麦克风或实时提示。
- 待确认 Feedback 进入统一审查队列；拒绝项不进入长期改进。
- 同类活动弱点按类别聚合并增加 `occurrence_count`，完成或忽略后允许开启新一轮改进。

## Part 9 收口能力

- 工作区提供漏斗、简报、最近变化、跨模块搜索、统一审查队列和跨模块一致性报告。
- Web 和 CLI 提供完整备份、JSON 导出及 Blob/Agent trace 清理；恢复只允许停服后通过 CLI 显式确认。
- Web 提供 BOSS/OpenCLI 与只读 IMAP 的定向删除入口；全量删除会先生成完整恢复包。
- 浏览器执行 JSON、文件上传和删除写操作时统一通过 Session、Origin 和 CSRF 校验。
- `career doctor` 覆盖治理目录、Web 静态资源、migration 资源、loopback 安全、数据库、Node.js、外部 OpenCLI 和端口。
- Wheel 配置包含 Web 静态资源、Alembic 配置和 migration。

## 统一测试阶段顺序

1. 使用独立临时数据目录测试 0001–0010 migration 升降级和从旧 revision 升级。
2. 新增并执行 Part 8/9 定向 API、事务、并发和安全测试。
3. 分模块完成 Part 1–9 Web 实际操作，记录并修复 S0/S1/S2。
4. 使用专门测试邮箱验证最长 30 天初扫、北京时间展示、严格只读和增量幂等。
5. 安装并调用外部 OpenCLI，完成真实 Connector 联调；不修改 OpenCLI 项目。
6. 在隔离目录演练完整备份、SHA-256 校验、恢复、单 Connector 删除和全量删除后恢复。
7. 执行全量自动化、长时间运行、依赖安全检查和 Windows wheel 安装验证。

## 已知限制与非阻塞项

- 尚未执行本文件所列实际测试；任何模块都不能在测试前标记为 `accepted`。
- 同类弱点当前采用确定性的类别级聚合，测试阶段需要用真实复盘内容评估粒度是否需要进一步细分。
- P0 不录音、不转写、不做面试实时辅助。
- OpenCLI 是外部应用；本仓库不开发、修改或发布 OpenCLI。
- 目标招聘网站专用 CLI 不在未明确目标网站的情况下猜测开发，后续需单独确定站点、合规边界和接口契约。
- 第一版发布采用 Python wheel 和 Windows 安装说明；是否制作独立 Windows 安装器将在实际安装验收后决定。
