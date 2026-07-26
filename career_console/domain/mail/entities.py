"""Deterministic, non-agent mail classification rules."""

from __future__ import annotations

import re
from enum import StrEnum


class MailClassification(StrEnum):
    RECRUITING = "recruiting"
    POSSIBLY_RELATED = "possibly_related"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


class MailEventKind(StrEnum):
    ASSESSMENT = "assessment"
    WRITTEN_TEST = "written_test"
    INTERVIEW = "interview"
    RESCHEDULE = "reschedule"
    REJECTED = "rejected"
    OFFER = "offer"


_EVENT_RULES = (
    (MailEventKind.OFFER, ("offer", "录用", "聘用", "录取通知")),
    (MailEventKind.REJECTED, ("遗憾", "不匹配", "未通过", "拒绝", "淘汰")),
    (MailEventKind.RESCHEDULE, ("改期", "调整时间", "重新安排", "reschedule")),
    (MailEventKind.WRITTEN_TEST, ("笔试", "在线测评", "编程测试", "written test")),
    (MailEventKind.INTERVIEW, ("面试", "面谈", "interview")),
    (MailEventKind.ASSESSMENT, ("测评", "assessment")),
)
_RECRUITING = ("招聘", "应聘", "候选人", "职位", "岗位", "校招", "面试", "笔试", "offer")
_POSSIBLE = ("人才", "简历", "hr", "career", "job", "申请")


def classification_from_text(subject: str, sender: str, body: str = "") -> tuple[str, str | None]:
    text = re.sub(r"\s+", " ", f"{subject} {sender} {body}").casefold()
    event = next(
        (kind for kind, words in _EVENT_RULES if any(word in text for word in words)), None
    )
    if event is not None or any(word in text for word in _RECRUITING):
        return MailClassification.RECRUITING.value, event.value if event else None
    if any(word in text for word in _POSSIBLE):
        return MailClassification.POSSIBLY_RELATED.value, None
    if subject.strip() or sender.strip():
        return MailClassification.UNRELATED.value, None
    return MailClassification.UNKNOWN.value, None
