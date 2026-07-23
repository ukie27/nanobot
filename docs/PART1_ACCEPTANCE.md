# Part 1 用户验收指南

> 当前状态：`user_acceptance`<br>
> 前置条件：Part 0 已验收<br>
> 验收目标：使用真实简历建立可确认、可编辑、可拒绝且来源可追溯的职业事实库。

## 1. 本部分交付

- 职业档案、简历导入、事实审查三个真实 Web 页面。
- TXT、Markdown、PDF、DOCX 和粘贴文本导入。
- SHA-256 文件去重与本地内容寻址存储。
- `CandidateProfile`、`CandidateFact`、`FactSource`、`FactRevision`。
- 最小 `ReviewTask` 和 `AgentRun` 审计记录。
- proposed → confirmed/rejected 状态工作流和乐观锁。
- 单条确认、编辑、拒绝以及原子批量确认。
- 本地事实提取器，以及无工具权限的 nanobot Task Agent 提取适配器。
- Part 0 数据库升级前自动备份。

只有 `confirmed` 事实显示在可信职业档案中。导入和模型提取结果永远不会自动确认。

## 2. 升级和启动

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m nanobot career doctor
.\.venv\Scripts\python.exe -m nanobot career db migrate
.\.venv\Scripts\python.exe -m nanobot career serve
```

如果已有 Part 0 数据库，迁移前会在备份目录产生带 `pre-migration` 标识的一致性备份。

浏览器打开：

```text
http://127.0.0.1:8765
```

状态页的目标 revision 应为：

```text
20260723_0002
```

## 3. 导入真实简历

1. 进入“简历导入”。
2. 上传一份真实 TXT、Markdown、PDF 或 DOCX 简历。
3. 确认页面显示成功提取的待审查事实数量。
4. 在“已导入文档”中确认文件名、解析器、大小、哈希摘要和来源数量存在。
5. 不要上传扫描图片型 PDF；当前版本只处理包含真实文本层的 PDF。

也可以在“粘贴简历文本”中使用如下结构测试：

```text
姓名：你的姓名
目标岗位：Python 后端工程师
目标城市：上海

专业技能
- Python, FastAPI, SQLite

项目经历
- 项目名称：负责的工作和可验证结果
```

默认使用本地结构化提取器，因此不需要 API key，也不会把简历发送到模型服务。

## 4. 事实审查

进入“事实审查”，完成以下操作：

1. 展开一条事实的“来源证据”，确认它来自刚导入的文档原文。
2. 编辑一条表达不准确的事实并保存。
3. 确认编辑后的事实版本号增加。
4. 拒绝一条不正确或不希望保留的候选事实。
5. 勾选多条剩余事实，执行“确认所选”。
6. 确认已处理事实从待审查列表消失。

批量确认是单事务操作：任意一条发生版本冲突时，整批都不会部分确认。

## 5. 可信档案和手动事实

1. 进入“职业档案”。
2. 确认只显示已经确认的事实，并按基本信息、教育、项目、技能等类别分组。
3. 展开“来源与历史”，查看证据和修改记录。
4. 点击“手动补充事实”。
5. 新增一条真实项目成果，并填写来源说明。
6. 返回“事实审查”确认这条手动事实。
7. 再次打开职业档案，确认该事实已经出现。

## 6. 去重和持久化

1. 再次上传完全相同的简历文件。
2. 页面应提示文件已导入，不产生重复事实。
3. 停止服务并重新启动。
4. 确认文档、事实状态、来源和 revision 历史仍然存在。

## 7. 可选 Task Agent 验收

如果现有 nanobot 配置已经设置可用模型，可以在启动服务前执行：

```powershell
$env:NANOBOT_CAREER_FACT_EXTRACTOR_MODE = 'agent'
.\.venv\Scripts\python.exe -m nanobot career serve
```

该模式具有以下强制边界：

- 不注册 Exec、Web、文件系统或其他工具。
- 只向 Provider 发送当前指定 Document 的解析文本。
- 输出必须符合 `candidate_fact.v1` Schema。
- 每条 evidence 必须是 Document 原文中的精确片段。
- 校验失败只记录失败审计，不创建事实。

测试结束后可关闭当前 PowerShell，或执行：

```powershell
Remove-Item Env:NANOBOT_CAREER_FACT_EXTRACTOR_MODE
```

未配置模型时跳过本节，不影响 Part 1 本地功能验收。

## 8. 反馈内容

如发现问题，请提供：

- 使用的文件类型和大致大小，不要直接发送包含隐私的简历文件。
- 操作步骤和页面错误摘要。
- 页面提供的 correlation ID。
- 对应时间点的脱敏日志错误类型。

完成上述实测并确认后，Part 1 才更新为 `accepted`，随后进入 Part 2 岗位池与岗位匹配。
