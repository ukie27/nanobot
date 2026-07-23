"""Explicit, size-limited public web fetch for user-selected job pages."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
from lxml.html import fromstring
from readability import Document

from nanobot.career.domain.common.errors import CareerDomainError


class SafeJobPageFetcher:
    def __init__(self, *, max_bytes: int, timeout_seconds: float = 15.0) -> None:
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> tuple[str, str]:
        normalized = url.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise CareerDomainError(
                "Only public HTTP(S) URLs without credentials are allowed.", code="invalid_job_url"
            )
        self._assert_public_host(parsed.hostname, parsed.port)
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "Nanobot-Career/0.1 job-import"},
            ) as client:
                with client.stream("GET", normalized) as response:
                    response.raise_for_status()
                    if 300 <= response.status_code < 400:
                        raise CareerDomainError(
                            "Redirecting job URLs are not fetched automatically.",
                            code="job_url_redirect",
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type and content_type not in {
                        "text/html",
                        "text/plain",
                        "application/xhtml+xml",
                    }:
                        raise CareerDomainError(
                            "The job URL did not return readable text or HTML.",
                            code="unsupported_job_url_content",
                        )
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise CareerDomainError(
                                "Fetched job page exceeds the size limit.",
                                code="document_too_large",
                            )
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    html = b"".join(chunks).decode(encoding, errors="replace")
        except CareerDomainError:
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            raise CareerDomainError(
                "The job page could not be fetched.", code="job_url_fetch_failed"
            ) from exc
        try:
            readable = Document(html)
            title = readable.short_title() or parsed.hostname
            text = fromstring(readable.summary()).text_content()
        except Exception as exc:
            raise CareerDomainError(
                "The fetched page did not contain readable job text.", code="job_page_unreadable"
            ) from exc
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not text:
            raise CareerDomainError(
                "The fetched page did not contain readable job text.", code="job_page_unreadable"
            )
        return title[:300], text

    @staticmethod
    def _assert_public_host(host: str, port: int | None) -> None:
        try:
            addresses = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise CareerDomainError(
                "The job URL host could not be resolved.", code="job_url_fetch_failed"
            ) from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise CareerDomainError(
                    "Private or local network job URLs are not allowed.",
                    code="job_url_private_address",
                )
