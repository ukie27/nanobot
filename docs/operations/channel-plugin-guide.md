# Channel 扩展指南

CareerConsole 保留 Channel Runtime，用于向 QQ、飞书、钉钉等目标发送业务提醒，也允许未来按需接收受控事件。Channel 不是独立产品入口，当前产品 CLI 不提供 `gateway`、`onboard`、`plugins list` 或 `channels login` 命令；配置、凭据和连接测试应由设置中心及其后端服务管理。

## 模块边界

- `career_console.runtime.channels`：通用通道协议、内置实现、发现与消息分发。
- `career_console.infrastructure.channels`：CareerConsole 业务通知到 Runtime Channel 的适配。
- `career_console.application`：决定何时发送何种业务通知，不依赖具体通道 SDK。
- 设置中心：保存普通配置；密钥只保存为安全存储引用。

业务服务不得直接导入某个 QQ、飞书或 Telegram SDK。新增通知场景应先定义应用层端口，再由基础设施适配到 Channel Runtime。

## 外部插件契约

外部 Python 包可以通过 entry point 注册 `BaseChannel` 子类：

```toml
[project.entry-points."career_console.runtime.channels"]
webhook = "career_console_channel_webhook:WebhookChannel"
```

插件类至少实现 `start()`、`stop()` 和 `send()`：

```python
from career_console.runtime.bus.events import OutboundMessage
from career_console.runtime.channels.base import BaseChannel


class WebhookChannel(BaseChannel):
    name = "webhook"
    display_name = "Webhook"

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> None:
        await self._deliver(message.chat_id, message.content)

    @classmethod
    def default_config(cls) -> dict:
        return {"enabled": False, "allowFrom": []}
```

`send()` 失败时必须抛出异常，由 `ChannelManager` 统一执行重试和审计。实现不得把 token、Cookie、Webhook secret 或完整消息正文写入日志。

## 发现与配置

Runtime 使用 `career_console.runtime.channels` entry point 发现外部插件。内置 Channel 优先，插件不能覆盖同名内置实现。只有同时满足以下条件才会实例化插件：

1. 插件已安装在 CareerConsole 使用的 Python 环境中；
2. Runtime 配置 Schema 中存在同名 Channel 配置段；
3. 配置段的 `enabled` 为 `true`。

因此，安装 Python 包本身不等于完成产品接入。新增插件还必须补充配置 Schema、设置中心表单、安全存储字段、连接测试、通知路由和回归测试。

## 权限与数据安全

- 接收消息时统一通过 `_handle_message()`，由基类执行 `allow_from` 校验。
- 空 `allow_from` 表示拒绝所有来源；不要把 `"*"` 用于正式环境。
- 默认将 Channel 作为通知出口；启用入站事件必须有明确业务场景和权限模型。
- OAuth session、二维码登录结果和浏览器 Cookie 不进入普通配置或工作区导出。
- 网络请求必须设置超时，错误信息必须脱敏。

## 流式发送

只有配置启用 `streaming` 且子类覆盖 `send_delta()` 时才使用流式发送。实现应按 metadata 中的 `_stream_id` 隔离缓冲，并处理 `_stream_delta`、`_stream_end` 和 `_resuming`。不支持流式发送时只实现 `send()` 即可。

## 开发与验收

本地开发可用 editable install 安装插件，然后运行：

```powershell
python -m pytest tests/channels/test_channel_plugins.py
python -m pytest tests/channels
```

产品接入至少验收：发现与同名冲突、配置关闭/开启、权限拒绝、发送成功、超时重试、错误脱敏、优雅停止、设置 round-trip，以及真实平台的测试消息。交互式授权如果存在，应由设置中心触发专用后端流程，而不是恢复旧 CLI。
