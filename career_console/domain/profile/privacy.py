"""Privacy rules for career facts."""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d(?:[\s-]?\d){8}(?!\d)"
)
_CONTACT_ONLY_LABEL = re.compile(
    r"^\s*(?:邮箱|email|电子邮箱|电话|手机|phone|mobile)\s*[：:]?\s*$",
    re.IGNORECASE,
)


def contains_contact_information(value: str) -> bool:
    return bool(EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value))


def remove_contact_information(value: str) -> str:
    """Remove email/mobile values while preserving unrelated line content."""
    cleaned_lines: list[str] = []
    for line in value.splitlines():
        cleaned = EMAIL_PATTERN.sub("", line)
        cleaned = PHONE_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        if not cleaned or _CONTACT_ONLY_LABEL.fullmatch(cleaned):
            continue
        cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines)
