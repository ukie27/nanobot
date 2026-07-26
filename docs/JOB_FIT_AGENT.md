# Agent 岗位语义匹配

数据库 revision：`20260726_0021`。

## 执行边界

`job_fit_analysis.v2` 使用共享 AgentRunner 的 task mode，工具注册表为空。输入只包含当前 JobPost 元数据、当前版本的结构化 JobRequirement、confirmed facts 和 confirmed preferences；岗位字段被视为不可信数据，不加载聊天 Memory、SOUL、Skills、邮件或其他工作区内容。

Agent 负责要求语义、直接证据候选、可迁移能力、优势、风险、材料修改量和准备时间。应用层要求 Agent 恰好覆盖当前版本的全部 Requirement ID，并严格验证所有 Fact ID 属于本次输入的 confirmed facts。失败执行只写失败 AgentRun，不创建 Proposal。

## Proposal 与正式分析

Agent 输出先写入 `job_fit_proposals`，并关联 AgentRun 和 ReviewTask。用户确认前不会改变正式 JobMatchAnalysis。

确认时再次校验：

- JobPostVersion 未变化；
- confirmed fact set 未变化；
- confirmed preference set 未变化。

任一输入过期都要求重新分析。通过校验后，Domain 根据逐项证据重新计算硬门槛和要求匹配分。学历、年限、语言、地点和工作方式等硬约束只接受直接事实，不能由可迁移能力代替。

决策优先级与要求匹配分分离：Domain 在要求匹配分之外计算偏好调整和投入成本调整，硬门槛仍拥有最终否决权。正式分析保留事实值与版本快照，历史记录不会被后续档案变化覆盖。
