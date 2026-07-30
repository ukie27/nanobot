# CareerConsole v1 开发数据集

该数据集使用固定的北京时间 `2026-07-28T09:00:00+08:00`，覆盖从职业档案、机会、岗位、材料、申请、邮件、确认到面试复盘的完整旅程。

所有人物、公司、邮箱、岗位和会话响应均为虚构测试数据。数据集不包含真实账号、凭据、浏览器会话或个人信息。

使用方式：

```text
career-console dev dataset validate
career-console dev dataset seed --scenario full-journey --workspace <test-workspace>
career-console dev dataset expect --scenario full-journey --workspace <test-workspace>
career-console dev dataset reset --workspace <test-workspace>
career-console dev eval validate
career-console dev eval run
career-console dev eval run --results <normalized-results.json> --report <report.json>
```

工作区必须预先包含 `.runtime/career-console-test-workspace` 标记。Reset 只清理 `data/dev-dataset/career_console_v1`，不会删除工作区标记或其他文件。

`evaluation/benchmark.json` 定义产品能力维度、案例、权重、阈值和关键失败项。`evaluation/reference-results.json` 是评分器的金标自检结果，不代表真实模型运行结果。真实产品或 Agent 运行必须输出相同的 `career-console.evaluation-results.v1` 协议，再通过 `dev eval run --results` 评分。
