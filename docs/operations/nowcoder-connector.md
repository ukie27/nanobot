# 牛客校招日程 Connector

## 边界

- 默认来源：牛客校招日程。
- 每日自动招聘信息只来自牛客；BOSS Connector 保留为手动定向搜索，不参与调度。
- 自动同步：只读取 `Asia/Shanghai` 当前自然日收录的数据。
- 手动同步：用户可明确选择当天、最近 7、14 或 30 天。
- 历史硬上限：30 天；系统不主动回扫。
- 只读：不投递、不收藏、不订阅、不发消息，也不绕过登录、验证码或访问控制。

## OpenCLI Plugin

插件源码位于：

```text
integrations/opencli-plugins/career-sources/
```

每台机器安装或重新链接一次：

```powershell
opencli plugin install file:///D:/project/job-agent/CareerConsole/integrations/opencli-plugins/career-sources
```

验证：

```powershell
opencli plugin list
opencli nowcoder schedule --lookback 0 --limit 3 -f json
```

`--lookback` 只接受 `0`、`7`、`14`、`30`。其中 `0` 表示中国时间当天。

## 数据入口

插件使用牛客页面自身的只读接口：

```text
POST https://www.nowcoder.com/np-api/u/school-schedule/list-card
```

日常模式使用页面的 `tab=3`（24h 更新），随后按 `wangshenUpdateTime` 再次执行中国自然日过滤。不能直接把整个滚动 24 小时窗口作为“当天”，否则凌晨运行时会混入前一天数据。

手动历史模式使用按更新时间排序的公开列表，并在达到用户所选日期边界时停止；单页 50 条、最多 20 页、最多输出 1000 条。

## Career API

```text
GET  /api/v1/connectors/nowcoder
PUT  /api/v1/connectors/nowcoder
POST /api/v1/connectors/nowcoder/health
POST /api/v1/connectors/nowcoder/scan
GET  /api/v1/opportunities
GET  /api/v1/opportunities/{id}
POST /api/v1/opportunities/{id}/triage
```

手动请求示例：

```json
{"lookback_days": 30}
```

调度器不接受历史参数，固定调用 `lookback_days=0`。Application Service 会再次验证每条记录的 `collected_at`，超出允许范围的数据进入 quarantine，不写入正式业务表。

通过校验的数据写入 `RecruitmentOpportunity` 机会池，并保留来源身份、不可变内容版本和对应 `SourceEvent`。牛客的公司招聘批次不是具体 JD，因此不会创建 `JobPost`；用户从官方入口取得真实 JD 后，再通过文本、文件或 URL 导入具体岗位池。

机会可标记为 `new`、`following` 或 `ignored`。状态更新使用 `expected_version` 做乐观并发控制，冲突时 API 返回 HTTP 409。

用户从机会页导入真实 JD 时，导入请求携带 `opportunity_id`。岗位版本与 `opportunity_job_links` 在同一事务中写入；重复导入不会产生重复关联。今日概览通过 `GET /api/v1/opportunities?today=true` 获取北京时间当天收录的机会。
