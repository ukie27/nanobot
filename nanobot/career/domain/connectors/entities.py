"""Pure connector validation and scheduling rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


class ConnectorHealth(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    REQUIRES_LOGIN = "requires_login"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ConnectorError(StrEnum):
    NOT_INSTALLED = "opencli_not_installed"
    AUTH_REQUIRED = "requires_login"
    BRIDGE_UNAVAILABLE = "bridge_unavailable"
    TIMEOUT = "temporary_timeout"
    INVALID_ARGUMENT = "invalid_argument"
    SCHEMA_INVALID = "schema_invalid"
    COMMAND_DENIED = "command_denied"
    EXECUTION_FAILED = "execution_failed"


def validate_profile_alias(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 120 or any(char in value for char in "\r\n\0"):
        raise ValueError("Browser Profile alias 无效。")
    return value


def validate_schedule_times(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except (ValueError, TypeError) as exc:
            raise ValueError("扫描时间必须使用 HH:MM。") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("扫描时间必须使用 HH:MM。")
        normalized.append(f"{hour:02d}:{minute:02d}")
    if not normalized:
        raise ValueError("至少配置一个扫描时间。")
    return sorted(set(normalized))


def next_scan_time(now: datetime, times: list[str], timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    current = (now.replace(tzinfo=UTC) if now.tzinfo is None else now).astimezone(zone)
    for day_offset in (0, 1):
        day = current.date() + timedelta(days=day_offset)
        for value in validate_schedule_times(times):
            hour, minute = (int(part) for part in value.split(":"))
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            if candidate > current:
                return candidate.astimezone(UTC)
    raise RuntimeError("无法计算下一次扫描时间。")


def boss_external_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.zhipin.com", "zhipin.com"}:
        raise ValueError("BOSS 岗位 URL 无效。")
    value = parsed.path.removeprefix("/job_detail/").removesuffix(".html").strip("/")
    if not value:
        raise ValueError("BOSS 岗位缺少外部 ID。")
    return value


def validate_nowcoder_lookback(days: int, *, scheduled: bool = False) -> int:
    if days not in {0, 7, 14, 30}:
        raise ValueError("牛客历史范围只能选择当天、最近 7、14 或 30 天。")
    if scheduled and days != 0:
        raise ValueError("牛客自动同步只能获取中国时间当天的数据。")
    return days


def nowcoder_external_id(value: str, source_url: str) -> str:
    external_id = value.strip()
    if not external_id or len(external_id) > 300 or any(char in external_id for char in "\r\n\0"):
        raise ValueError("牛客日程外部 ID 无效。")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.nowcoder.com", "nowcoder.com"}:
        raise ValueError("牛客日程来源 URL 无效。")
    if not parsed.path.startswith("/enterprise/"):
        raise ValueError("牛客日程来源 URL 路径无效。")
    return external_id
