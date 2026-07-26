# 职业档案业务记忆

数据库 revision：`20260726_0021`。

Career 的长期信息不是聊天摘要或 Markdown Memory，而是以下结构化对象：

- `career_preferences`：用户明确确认的岗位族、城市、行业、工作方式和约束。
- `profile_change_events`：事实、偏好、洞察和策略变化的不可变事件，记录 entity revision 与 impact scopes。
- `profile_impact_runs`：每个变化事件/影响范围唯一的执行投影，关联 BackgroundJob、输入 revision、状态、影响数量与错误码。
- `profile_insight_proposals`：可确认或拒绝的反思性结论，不能直接覆盖事实。
- `strategy_snapshots`：按版本保存的阶段策略候选和历史。
- `daily_digests`：按北京时间日期从业务事件重建的摘要，不作为事实源。

事实确认或编辑会产生变化事件，影响范围可包含 `job_fit`、`material_strategy`、`career_strategy` 和 `opportunity_filter`。每个范围会按事件 revision 投影为 `profile_impact_runs` 与幂等 BackgroundJob；`job_fit` 自动重算活动岗位，`material_strategy` 将材料标记为待复核，其他范围保留可审计的持久化投影供后续模块接管。

## Profile Insight Agent

`profile_insight.v1` 通过共享 AgentRunner 的 task mode 执行，工具注册表为空，不加载聊天记忆、SOUL、skills 或邮件/文档原文。输入只有已确认事实、已确认偏好、可选的已确认策略摘要和近 7 天聚合统计。

Agent 输出只能创建 Proposal。应用服务会再次校验所有 evidence/counter-evidence Fact ID 均属于本次输入的 confirmed facts；非法 Schema、未知 ID 或工具调用只写失败 AgentRun，不创建洞察。成功执行会原子写入 AgentRun、多个 `profile_insight_proposals` 和逐条 ReviewTask。

## 影响重算与材料失效

- 幂等键：`profile-impact:{change_event_id}:{scope}`。
- 岗位匹配以 `job_post_version_id + confirmed fact_set_hash` 去重；输入未变化时复用已有分析。
- 档案变化不会改写历史材料或 Final 快照，只设置 `strategy_stale`、原因和时间。
- 非 Final 材料保存新内容版本后清除 stale；Final 材料保持不可变并继续显示档案已变化提示。

DailyDigest 每次生成都从当天档案事件、申请事件、待审核项和待办任务重建，并使用 SQLite 原子 upsert 处理调度器与用户手动生成的并发。每周策略是 Proposal，进入统一 ReviewTask；用户确认后才产生策略确认事件。
