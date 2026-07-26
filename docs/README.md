# CareerConsole 文档

文档按用途分类，避免需求材料、运行手册和验收记录混杂在仓库根目录。

## Product

- [产品功能设计](product/product-function-design.md)
- [开发计划](product/development-plan.md)
- [产品独立化计划](product/independence-plan.md)

## Architecture

- [技术实现方案](architecture/technical-implementation-plan.md)
- [代码结构与依赖规则](architecture/codebase-structure.md)
- [Agent Runtime 边界](architecture/runtime-scope.md)
- [Agent 审核 Runtime](architecture/agent-review-runtime.md)
- [Python SDK](architecture/python-sdk.md)

核心源码依赖方向：

```text
interfaces ─┐
            ├─> application ─> domain
infrastructure ┘

runtime = 独立的通用 Agent 内核，由 infrastructure 适配使用
```

## Operations

配置、Workspace、Provider、OpenCLI、Channel、Scheduler 和 Windows 运行说明位于
[`operations/`](operations/)。

## Features

邮件智能、岗位匹配、职业档案记忆和简历材料说明位于
[`features/`](features/)。

## Acceptance

阶段验收与发布检查位于 [`acceptance/`](acceptance/)。

## Archive

原始探索任务和历史需求分析位于 [`archive/`](archive/)，只作为设计溯源材料，
不代表当前代码结构或运行方式。
