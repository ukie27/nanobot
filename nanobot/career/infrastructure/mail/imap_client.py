"""Standard-library IMAP adapter with a deliberately read-only command surface."""

from __future__ import annotations

import imaplib
import re
from datetime import date

from nanobot.career.application.ports.imap_client import ImapReadOnlyError
from nanobot.career.infrastructure.mail.parser import parse_header, parse_message


class StdlibReadOnlyImapClient:
    HEADER_QUERY = "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM TO SUBJECT DATE)] RFC822.SIZE)"
    MAX_MESSAGE_BYTES = 10 * 1024 * 1024
    MAX_HEADER_BYTES = 64 * 1024
    MAX_MESSAGES_PER_SYNC = 500
    CONNECT_TIMEOUT_SECONDS = 30

    def test_connection(self, **config: object) -> dict:
        client = self._connect(config)
        try:
            uid_validity = self._select(client, str(config.get("folder") or "INBOX"))
            return {"status": "healthy", "uid_validity": uid_validity}
        finally:
            self._logout(client)

    def synchronize(self, **config: object) -> dict:
        client = self._connect(config)
        try:
            uid_validity = self._select(client, str(config.get("folder") or "INBOX"))
            last_uid = int(config.get("last_uid") or 0)
            expected = str(config.get("uid_validity") or "")
            if expected and expected != uid_validity:
                last_uid = 0
            criterion = f"UID {last_uid + 1}:*" if last_uid else self._since(config.get("since"))
            status, response = client.uid("search", None, criterion)
            if status != "OK":
                raise ImapReadOnlyError("IMAP UID SEARCH 失败。", code="imap_search_failed")
            search_payload = response[0] if response and isinstance(response[0], bytes) else b""
            uids = sorted(
                {int(item) for item in search_payload.split() if item.isdigit()}
            )[: self.MAX_MESSAGES_PER_SYNC]
            records = []
            for uid in uids:
                raw_header, message_size = self._fetch(client, uid, self.HEADER_QUERY)
                parsed = parse_header(raw_header[: self.MAX_HEADER_BYTES])
                within_limit = message_size is None or message_size <= self.MAX_MESSAGE_BYTES
                if within_limit:
                    raw_message, _ = self._fetch(client, uid, "(BODY.PEEK[] RFC822.SIZE)")
                    if len(raw_message) <= self.MAX_MESSAGE_BYTES:
                        parsed = parse_message(raw_message)
                        parsed["body_fetched"] = True
                    else:
                        parsed.update(self._header_only_fields())
                else:
                    parsed.update(self._header_only_fields())
                parsed["uid"] = uid
                records.append(parsed)
            return {
                "uid_validity": uid_validity,
                "messages": records,
                "last_uid": max(uids, default=last_uid),
            }
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ImapReadOnlyError("IMAP 只读同步失败，请检查服务器和授权码。") from exc
        finally:
            self._logout(client)

    @staticmethod
    def _connect(config: dict[str, object]) -> imaplib.IMAP4_SSL:
        client: imaplib.IMAP4_SSL | None = None
        try:
            client = imaplib.IMAP4_SSL(
                str(config["host"]),
                int(config.get("port") or 993),
                timeout=StdlibReadOnlyImapClient.CONNECT_TIMEOUT_SECONDS,
            )
            client.login(str(config["username"]), str(config["password"]))
            return client
        except (imaplib.IMAP4.error, OSError, KeyError) as exc:
            if client is not None:
                StdlibReadOnlyImapClient._logout(client)
            raise ImapReadOnlyError("IMAP TLS 连接或认证失败。", code="imap_auth_failed") from exc

    @staticmethod
    def _select(client: imaplib.IMAP4_SSL, folder: str) -> str:
        status, _ = client.select(folder, readonly=True)
        if status != "OK":
            raise ImapReadOnlyError("无法以只读方式打开邮箱目录。", code="imap_select_failed")
        response = client.response("UIDVALIDITY")
        uid_validity = response[1] if response and len(response) > 1 else None
        value = (
            uid_validity[0].decode("ascii", errors="ignore")
            if uid_validity and uid_validity[0]
            else ""
        )
        if not value.isdigit():
            raise ImapReadOnlyError(
                "邮箱服务器未返回有效 UIDVALIDITY，无法安全增量同步。",
                code="imap_uidvalidity_missing",
            )
        return value

    @staticmethod
    def _fetch(client: imaplib.IMAP4_SSL, uid: int, query: str) -> tuple[bytes, int | None]:
        status, response = client.uid("fetch", str(uid), query)
        if status != "OK":
            raise ImapReadOnlyError(f"读取邮件 UID {uid} 失败。", code="imap_fetch_failed")
        payload = b"".join(
            item[1]
            for item in (response or [])
            if isinstance(item, tuple) and isinstance(item[1], bytes)
        )
        if not payload:
            raise ImapReadOnlyError(f"读取邮件 UID {uid} 返回空内容。", code="imap_fetch_failed")
        metadata = b" ".join(
            item[0]
            for item in (response or [])
            if isinstance(item, tuple) and isinstance(item[0], bytes)
        )
        match = re.search(rb"RFC822\.SIZE\s+(\d+)", metadata, flags=re.IGNORECASE)
        return payload, int(match.group(1)) if match else None

    @staticmethod
    def _header_only_fields() -> dict[str, object]:
        return {
            "evidence_excerpt": None,
            "body_hash": None,
            "attachments": [],
            "extracted": {},
            "body_fetched": False,
        }

    @staticmethod
    def _since(value: object) -> str:
        day = value if isinstance(value, date) else date.today()
        return f'SINCE "{day.strftime("%d-%b-%Y")}"'

    @staticmethod
    def _logout(client: imaplib.IMAP4_SSL) -> None:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
