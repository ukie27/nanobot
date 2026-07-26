# Material Drafter–Reviewer

数据库 revision：`20260726_0021`。

本切片实现的正式链路：

```text
active ResumeDirectionSelection
+ locked JobPostVersion
+ confirmed Fact revisions
+ optional Resume series
→ tool-free Drafter (`resume_draft.v2`)
→ block-level Fact ID / Requirement ID validation
→ isolated tool-free Reviewer (`material_review.v2`)
→ AgentRun × 2 + Proposal + ReviewTask
→ user confirmation
→ MaterialDraft + immutable ResumeVersion v1
+ FactSnapshot + FactReference + deterministic review
```

## 边界

- Drafter 和 Reviewer 使用独立 AgentRun；Reviewer 只接收结构化草稿、锁定事实、岗位和要求，不共享 Drafter 的自由隐藏状态。
- Agent 没有工具，不能修改业务数据，输出始终是 Proposal。
- 没有活动方向、方向已经 stale、未知/未确认 Fact ID、未知 Requirement ID、无事实支持的表达都会阻断。
- Reviewer 失败时保留 Drafter 成功和 Reviewer 失败审计，但不创建 Proposal。
- Reviewer 给出 `needs_revision` 时可以查看和拒绝，但不能确认成为正式材料。
- 可选基础简历锁定到具体 Base ResumeVersion ID 和 content hash；确认时再次检查岗位版本、活动 Selection、Base ResumeVersion 和 Fact set hash，并再次运行确定性事实审查。
- 确认前不创建 MaterialDraft；确认事务一次性写入材料、不可变 v1、事实快照、块级引用和正式 Review。
- 原确定性本地生成器继续作为明确标注的基线，未伪装为 Agent Drafter。
- 后续编辑沿用现有版本链、确定性 Review、Final 不可变和 PDF 文本层/渲染验证。

## API

- `POST /api/v1/materials/agent-proposals`
- `GET /api/v1/materials/agent-proposals?job_post_id=...`
- `POST /api/v1/materials/agent-proposals/{proposal_id}/resolve`

Web 材料入口在携带 `jobId` 时展示活动方向、Drafter 内容块到 Fact/Requirement 的引用、Reviewer findings，以及确认/拒绝操作。

## 当前限制与下一步

严格确定性审查目前要求生成文本保留引用事实完整原文，所以本阶段 Agent 主要负责内容取舍、结构、排序和受控引导语。基础简历、方向简历、岗位定制版本关系和差异页已在 revision `20260726_0021` 落地；若要支持更自然的改写，应新增可验证 Claim/Evidence 语义规则，不能降低现有事实门禁。
