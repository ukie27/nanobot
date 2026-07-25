"""Pure interview enums and deterministic question classification."""

from __future__ import annotations

from enum import StrEnum


class InterviewRound(StrEnum):
    PHONE = "phone"
    TECHNICAL = "technical"
    CASE = "case"
    FINAL = "final"


class InterviewStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FeedbackStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


def question_category(text: str) -> str:
    normalized = text.casefold()
    rules = (
        ("technical", ("技术", "算法", "系统", "代码", "python", "sql", "架构")),
        ("behavioral", ("经历", "冲突", "困难", "团队", "star", "失败")),
        ("case", ("案例", "case", "估算", "分析", "方案")),
        ("motivation", ("为什么", "动机", "职业规划", "离职", "选择")),
    )
    return next((category for category, words in rules if any(word in normalized for word in words)), "general")
