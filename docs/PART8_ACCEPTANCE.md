# Part 8 用户验收指南：面试准备与反馈闭环

本指南暂存，按照当前开发安排，等 Part 9 整体功能完成后再统一执行实际验收。

## 核心场景

1. 为一条已经确认投递且具有实际材料快照的申请创建 phone、technical、case 或 final 面试。
2. 生成准备包，确认其中冻结了对应 `JobPostVersion`、`ApplicationMaterialSnapshot` 和 confirmed Fact ID。
3. 核对准备包没有引用其他申请材料，没有生成未经事实支持的经历；缺口只能形成诚实 Gap Bridge。
4. 手工填写面试问题、回答摘要、自评和结果，不使用麦克风、录音或实时提示。
5. 自评较低的回答形成待确认 Feedback；确认前不得进入长期 Improvement Item。
6. 分别确认和拒绝建议，只有 confirmed 建议进入长期改进项。
7. 再创建同类面试，确认准备包只引用已确认历史改进项。
8. 从申请的 `interview_scheduled` 事件创建面试，确认系统自动关联尚未使用的最近面试事件并复用派生任务。
9. 改期面试，确认关联 Task 和已有 Reminder 同步改期；取消面试，确认 Task、Reminder 和 Schedule 同步取消。
10. 在一次复盘中动态添加多个问题（最多 50 个），确认每题分类和低分建议分别保存。
11. 多次确认同一类别弱点，确认活动中的长期改进项累计 `occurrence_count`，完成或忽略后新反馈可形成新一轮改进项。

## 安全边界

- P0 不录音、不监听麦克风、不实时辅助面试。
- 准备内容只来自冻结岗位、实际投递材料、confirmed Fact 和 confirmed Improvement Item。
- 复盘正文不写日志；日志仅允许记录实体 ID、状态和脱敏错误码。
