# Part 6 用户验收指南：OpenCLI BOSS 只读 Connector

Part 6 已进入 `user_acceptance`。本项目只消费已安装的 OpenCLI 外部应用，不修改、构建或维护 `D:\project\job-agent\OpenCLI`。Career 仅允许 BOSS 的登录、状态、搜索和详情命令，不提供打招呼、发消息、交换联系方式、邀请、标记或自动投递。

## 1. 安装外部应用与 Browser Bridge

当前机器的 Node.js `v24.16.0` 满足要求，但尚未在 PATH 中发现 `opencli`。请按 OpenCLI 官方方式安装发布包：

```powershell
npm install -g @jackwener/opencli
opencli --version
opencli doctor
```

再安装 OpenCLI Browser Bridge Chrome 扩展。扩展连接成功后，打开 Chrome 并登录 BOSS 直聘。不要把账号密码写入 Career 配置；Career 复用 Chrome 已有会话。

如果 OpenCLI 安装在非 PATH 位置，可在启动 Career 前配置可执行文件：

```powershell
$env:NANOBOT_CAREER_OPENCLI_EXECUTABLE = "D:\path\to\opencli.cmd"
```

## 2. 数据库升级和诊断

```powershell
.\.venv\Scripts\python.exe -m nanobot career db migrate
.\.venv\Scripts\python.exe -m nanobot career doctor
```

预期关键结果：

```text
DB revision  20260724_0010  20260724_0010  PASS
Node.js      v20+            >= 20 ...      PASS
OpenCLI      <version>       available ... PASS
```

## 3. 启动并配置数据来源

```powershell
.\.venv\Scripts\python.exe -m nanobot career serve
```

打开 `http://127.0.0.1:8765/data-sources`：

1. 填写唯一的 Browser Profile alias、关键词和城市。
2. 启用 BOSS 来源；需要时启用每日 `09:00 / 18:00` 扫描。
3. 保存后点击“检查环境与登录”。
4. 如果显示 `requires_login`，点击“打开登录”，在可见浏览器窗口中人工完成登录。
5. 再次检查，确认状态为 `healthy`。

## 4. 真实岗位同步验收

1. 点击“立即扫描”，等待同步完成。
2. 在最近同步中检查发现、新增、更新、重复和隔离数量。
3. 打开“岗位池”，核对公司、岗位、地点、描述和要求。
4. 再次使用相同条件扫描，确认同一内容计入重复，不新增岗位或版本。
5. 岗位详情发生变化后重新扫描，确认同一岗位形成新版本。
6. 退出 BOSS 或选择未登录 Profile，确认状态变为 `requires_login`，既有岗位仍可正常访问。
7. 对无效 Schema，确认数据只进入隔离区，不进入岗位池。

## 5. 定时和安全验收

- Career 运行期间每分钟检查到期计划；配置的扫描时间使用 `Asia/Shanghai` 等 IANA 时区计算。
- 重启后 `next_scan_at`、SyncRun、SourceEvent 和同步游标保持有效。
- OpenCLI 退出码会映射为登录失效、Bridge 不可用、临时超时、参数错误或执行失败。
- BOSS 写操作不在 Career allowlist 中，不能从 API 或 Web UI 触发。
- 日志和 API 不保存 Chrome Cookie、账号密码或其他凭据。

## 6. 已知环境状态

- `D:\project\job-agent\OpenCLI` 当前是参考源码目录，未生成 `dist/src/main.js`；Career 不会替它构建。
- 当前 PATH 中尚未安装 `opencli`，所以真实 BOSS 验收前必须先安装 OpenCLI 发布应用并配置 Browser Bridge。
- OpenCLI 或 BOSS 的服务波动只会使本 Connector 的 SyncRun 失败，不会阻断任务提醒、材料或申请管理。
