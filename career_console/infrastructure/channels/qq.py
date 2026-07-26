"""Minimal outbound-only QQ Bot API adapter."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class QQChannelDeliveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class QQNotificationSender:
    token_url = "https://bots.qq.com/app/getAppAccessToken"
    api_base = "https://api.sgroup.qq.com"

    def send(self, *, app_id: str, secret: str, target: str, content: str) -> None:
        token = self._token(app_id, secret)
        target_type, openid = target.split(":", 1)
        path = (
            f"/v2/users/{openid}/messages"
            if target_type == "c2c"
            else f"/v2/groups/{openid}/messages"
        )
        self._request(
            f"{self.api_base}{path}",
            {"content": content, "msg_type": 0},
            {"Authorization": f"QQBot {token}"},
        )

    def _token(self, app_id: str, secret: str) -> str:
        result = self._request(
            self.token_url, {"appId": app_id, "clientSecret": secret}, {}
        )
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise QQChannelDeliveryError("authentication_failed")
        return token

    @staticmethod
    def _request(url: str, payload: dict, headers: dict[str, str]) -> dict:
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310
                data = response.read(64 * 1024)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                code = "authentication_failed"
            elif exc.code == 429:
                code = "rate_limited"
            else:
                code = "delivery_rejected"
            raise QQChannelDeliveryError(code) from None
        except (TimeoutError, URLError, OSError):
            raise QQChannelDeliveryError("connection_failed") from None
        try:
            result = json.loads(data or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise QQChannelDeliveryError("invalid_response") from None
        if not isinstance(result, dict):
            raise QQChannelDeliveryError("invalid_response")
        return result
