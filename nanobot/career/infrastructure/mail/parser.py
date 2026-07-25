"""Bounded MIME parsing that never persists a complete message body."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from email import policy
from email.header import decode_header
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

from nanobot.career.domain.mail import classification_from_text

MAX_EXTRACTED_TEXT_CHARS = 200_000
MAX_ATTACHMENT_METADATA = 100


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.length = 0

    def handle_data(self, data: str) -> None:
        remaining = MAX_EXTRACTED_TEXT_CHARS - self.length
        if remaining <= 0:
            return
        bounded = data[:remaining]
        self.parts.append(bounded)
        self.length += len(bounded)


def _decoded(value: str | None) -> str:
    parts = []
    for payload, charset in decode_header(value or ""):
        if isinstance(payload, bytes):
            parts.append(_decode_bytes(payload, charset))
        else:
            parts.append(payload)
    return "".join(parts).strip()


def _decode_bytes(payload: bytes, charset: str | None) -> str:
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _date(value: str | None) -> datetime | None:
    try:
        result = parsedate_to_datetime(value or "")
    except (OverflowError, TypeError, ValueError):
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return result.astimezone(UTC)


def parse_header(raw: bytes) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    subject = _decoded(message.get("Subject"))
    sender = _decoded(message.get("From"))
    classification, event_kind = classification_from_text(subject, sender)
    return {
        "message_id": (message.get("Message-ID") or "").strip() or None,
        "sender": sender[:500],
        "subject": subject[:998],
        "sent_at": _date(message.get("Date")),
        "classification": classification,
        "event_kind": event_kind,
    }


def parse_message(raw: bytes) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    header = parse_header(raw)
    text_parts: list[str] = []
    text_length = 0
    attachments: list[dict[str, Any]] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        disposition = part.get_content_disposition()
        filename = _decoded(part.get_filename()) if part.get_filename() else None
        if disposition == "attachment" or filename:
            if len(attachments) < MAX_ATTACHMENT_METADATA:
                payload = part.get_payload(decode=True) or b""
                attachments.append(
                    {
                        "filename": filename[:255] if filename else None,
                        "content_type": content_type[:255],
                        "size_bytes": len(payload),
                    }
                )
            continue
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        decoded = _decode_bytes(payload, charset)
        if content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(decoded)
            decoded = " ".join(parser.parts)
        remaining = MAX_EXTRACTED_TEXT_CHARS - text_length
        if remaining > 0:
            bounded = decoded[:remaining]
            text_parts.append(bounded)
            text_length += len(bounded)
    body = re.sub(r"\s+", " ", "\n".join(text_parts)).strip()
    classification, event_kind = classification_from_text(header["subject"], header["sender"], body)
    header.update(
        {
            "classification": classification,
            "event_kind": event_kind,
            "evidence_excerpt": body[:2000] or None,
            "body_hash": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None,
            "attachments": attachments,
            "extracted": _extract(body, header["subject"]),
        }
    )
    return header


def _extract(body: str, subject: str) -> dict[str, Any]:
    text = f"{subject}\n{body}"
    result: dict[str, Any] = {}
    patterns = {
        "application_reference": r"(?:申请编号|应聘编号|application\s*(?:id|no))\s*[:：#]?\s*([\w-]{4,40})",
        "company": r"(?:公司|企业)\s*[:：]\s*(.{2,80}?)(?=\s+(?:职位|岗位)\s*[:：]|[，。;；]|$)",
        "job_title": r"(?:职位|岗位)\s*[:：]\s*(.{2,80}?)(?=\s+(?:公司|企业|面试|笔试|时间)\s*[:：]?|[，。;；]|$)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            result[key] = match.group(1).strip()
    urls = re.findall(r"https?://[^\s<>\"']+", text, flags=re.IGNORECASE)
    if urls:
        result["links"] = urls[:10]
    scheduled = re.search(
        r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})日?\s*(上午|下午)?\s*(\d{1,2})[:：](\d{2})",
        text,
    )
    if scheduled:
        year, month, day, period, hour, minute = scheduled.groups()
        hour_number = int(hour)
        if period == "下午" and hour_number < 12:
            hour_number += 12
        try:
            result["scheduled_at"] = datetime(
                int(year),
                int(month),
                int(day),
                hour_number,
                int(minute),
                tzinfo=ZoneInfo("Asia/Shanghai"),
            ).isoformat()
        except ValueError:
            pass
    return result
