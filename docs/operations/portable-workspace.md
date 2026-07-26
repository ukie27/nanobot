# CareerConsole 工作区迁移包

CC-5 提供从设置页完成的工作区一致性导出与安全导入。迁移包扩展名为 `.ccworkspace`，内部是受约束的 ZIP 容器，但只能通过 CareerConsole 的校验流程恢复。

## 导出边界

导出包含：

- `workspace.json`；
- `config/` 普通配置；
- SQLite 在线一致性快照；
- `blobs/` 材料原件；
- `integrations/` 本地集成文件。

导出不包含日志、运行时锁、历史备份、历史导出和 `secrets/` 明文。导出器拒绝符号链接与 Windows 重解析点，避免把工作区之外的文件带入迁移包。

每个文件在 `manifest.json` 中记录相对路径、字节数和 SHA-256；manifest 同时记录归档 Schema、产品名、数据库 revision、生成时间和凭据模式。数据库通过 SQLite Backup API 创建，不直接复制运行中的数据库文件。

## 可选凭据 Vault

“包含凭据”默认关闭。开启后必须设置至少 12 个字符的迁移密码，CareerConsole 仅收集当前 `application.json` 中引用且在系统凭据库中实际存在的凭据。

Vault 使用：

- PBKDF2-HMAC-SHA256，随机 128-bit salt，600,000 次迭代；
- AES-256-GCM，随机 96-bit nonce；
- 固定版本 AAD，提供密文完整性认证。

迁移密码不保存、不可找回。Vault 在导入后写入新设备的系统凭据库，并从恢复后的工作区目录删除；API、SQLite、日志和 manifest 均不回显密码或凭据值。

## 安全导入流程

1. 用户选择迁移包和一个新的父目录；目标 `CareerConsole` 必须不存在或为空，系统不会覆盖已有工作区。
2. 限制上传大小、文件数量、单文件大小、解压总量和压缩比。
3. 拒绝绝对路径、`..`、反斜杠路径、重复路径、ZIP 符号链接和 Zip Slip。
4. 清单必须与归档成员完全一致，并逐文件验证大小与 SHA-256。
5. 验证 Workspace Schema、配置 Schema、SQLite `quick_check` 和数据库 revision；高于当前应用的数据库版本会被拒绝。
6. 完整恢复到新目录；若包含 Vault，再认证解密并恢复属于该 workspace ID 的凭据。
7. 最后更新机器本地 bootstrap 激活指针。此前任何失败都会清理新目录，不改变当前工作区。
8. 用户重启 CareerConsole 后进入恢复的工作区。

恢复采用“新工作区 + 重启切换”，不在服务运行时覆盖当前打开的 SQLite 数据库，也不热切换 Scheduler、Agent 或 Connector。

## API

```text
POST /api/v1/workspace/portable-export
GET  /api/v1/workspace/portable-exports/{filename}
POST /api/v1/workspace/portable-import
```

导入接口使用 multipart：`file`、`parent_directory` 和可选 `passphrase`。导出接口只返回脱敏元数据与受控下载地址。
