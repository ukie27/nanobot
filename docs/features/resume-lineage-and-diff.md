# 简历血缘与版本差异

数据库 revision：`20260726_0021`。

## 三层模型

```text
Base ResumeVersion
  → Direction ResumeVersion
    → Job-tailored ResumeVersion
      → edit v2/v3...
      → Final + verified PDF
```

- `Resume.series_type` 区分 `base` 与 `direction`。
- 方向系列必须通过 `parent_resume_id` 关联基础系列，并保存 `direction_label`。
- 独立基础/方向版本不依附 `MaterialDraft`；`ResumeVersion.material_draft_id` 因此允许为空。
- `ResumeVersion.version_scope` 区分 `base`、`direction`、`job_tailored`。
- `source_resume_version_id` 表示跨层来源；`parent_version_id` 只表示同一岗位材料内的编辑版本链。
- `MaterialDraft` 同时锁定来源 ResumeVersion 和 ResumeDirectionSelection。
- 已有材料统一视为 `job_tailored`，不伪造不存在的历史来源。

## 操作规则

审查通过或 Final 的岗位材料可以复制为可复用基础简历。方向简历也从审查通过的材料内容建立，但其血缘来源必须是所选基础简历的最新可复用版本。复制时重新生成 FactSnapshot 和 FactReference ID，保留事实 revision、内容和 hash 语义，不共享可变记录。

从基础或方向系列生成岗位材料时，系统锁定该系列最新可复用 ResumeVersion；后续上游版本变化不会静默改写已生成的岗位版本。

## 差异模型

`GET /api/v1/resumes/versions/{from}/diff/{to}` 返回：

- 内容块 `added / removed / changed / unchanged`；
- 前后 section、text 和 Fact ID；
- 新增和移除的 Fact ID；
- 两侧版本 scope、hash、状态和血缘。

Web 材料详情可以比较上游来源或初始版本与当前版本。差异只读，不会修改任一历史快照。
