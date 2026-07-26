# Resume Direction Planner

数据库 revision：`20260726_0021`。

## 目标

`resume_direction.v1` 在生成材料前提供 2–4 个真实不同的简历方向，避免系统直接产出一份“唯一正确”的简历。每个方向包含核心叙事、重点岗位要求、强调/弱化的 confirmed Fact ID、预计修改比例、页数、证据缺口、风险和理由。

## Agent 边界

Planner 使用共享 AgentRunner 的 task mode，工具注册表为空。输入仅包含当前 JobPostVersion、最新正式 JobMatchAnalysis、结构化要求及其匹配 Fact、confirmed facts 和 confirmed preferences。不加载聊天 Memory、SOUL、Skills、邮件或工作区文件。

应用服务严格验证 Requirement ID 和 Fact ID，并拒绝名称或核心叙事重复的伪方向。非法输出只写失败 AgentRun，不创建 Proposal。

## 审核与选择

Agent 输出写入 `resume_direction_proposals` 和 ReviewTask。用户可以：

- 选择一个方向；
- 组合两个方向；
- 拒绝整组候选。

确认时重新校验 JobPostVersion、正式 JobMatchAnalysis、confirmed fact set 和 confirmed preference set。任何输入变化都会阻止确认旧候选。

确认结果持久化为 `resume_direction_selections`。同一岗位的新 Selection 生效时，旧 active Selection 变为 `superseded`，历史不会被覆盖。Selection 是下一阶段 Drafter 的正式输入；当前确定性材料骨架生成器尚不消费它。
