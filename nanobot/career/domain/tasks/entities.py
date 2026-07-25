"""Pure task, timezone, reminder, and schedule rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nanobot.career.domain.common.errors import CareerDomainError


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"


def normalize_due(value: datetime, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise CareerDomainError("Unknown IANA timezone.", code="invalid_timezone") from exc
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    local = value.replace(tzinfo=zone)
    if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != value:
        raise CareerDomainError(
            "The local time does not exist because of a daylight-saving transition.",
            code="nonexistent_local_time",
        )
    return local.astimezone(UTC)


def reminder_time(due_at: datetime, offset_minutes: int) -> datetime:
    if not 0 <= offset_minutes <= 60 * 24 * 30:
        raise CareerDomainError(
            "Reminder offset must be between 0 and 30 days.", code="invalid_reminder_offset"
        )
    normalized = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at.astimezone(UTC)
    return normalized - timedelta(minutes=offset_minutes)


def next_schedule_run(
    schedule_type: str,
    current: datetime,
    *,
    interval_seconds: int | None = None,
    cron_expression: str | None = None,
    timezone: str = "Asia/Shanghai",
) -> datetime | None:
    current = current.astimezone(UTC)
    if schedule_type == "once":
        return None
    if schedule_type == "interval":
        if interval_seconds is None or interval_seconds < 10:
            raise CareerDomainError(
                "Interval schedules require at least 10 seconds.", code="invalid_interval"
            )
        return current + timedelta(seconds=interval_seconds)
    if schedule_type != "cron" or cron_expression is None:
        raise CareerDomainError("Unsupported schedule definition.", code="invalid_schedule")
    parts = cron_expression.split()
    if len(parts) != 5 or not parts[0].isdigit() or not parts[1].isdigit():
        raise CareerDomainError(
            "Cron currently supports daily 'minute hour * * *' expressions.",
            code="invalid_cron_expression",
        )
    minute, hour = int(parts[0]), int(parts[1])
    if not 0 <= minute <= 59 or not 0 <= hour <= 23 or parts[2:] != ["*", "*", "*"]:
        raise CareerDomainError("Cron time is invalid.", code="invalid_cron_expression")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise CareerDomainError("Unknown IANA timezone.", code="invalid_timezone") from exc
    local = current.astimezone(zone)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def conflict(left: datetime, right: datetime, *, minutes: int = 30) -> bool:
    return abs((left.astimezone(UTC) - right.astimezone(UTC)).total_seconds()) < minutes * 60
