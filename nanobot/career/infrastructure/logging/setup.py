"""Career logging configuration with conservative secret redaction."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from loguru import logger

_SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|password|secret|token)(\s*[:=]\s*)([^\s,;]+)"
)
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[^@\s]*(@[^\s]+)\b")


def redact(value: Any) -> str:
    text = str(value)
    text = _SENSITIVE.sub(r"\1\2[REDACTED]", text)
    return _EMAIL.sub(r"\1***\2", text)


def configure_logging(
    logs_dir: Path, *, level: str = "INFO", verbose: bool = False, retention_days: int = 14
) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "career.log"
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level=level, enqueue=True)
    logger.add(
        log_path,
        level=level,
        rotation="10 MB",
        retention=f"{retention_days} days",
        enqueue=True,
        serialize=True,
        format="{time:YYYY-MM-DDTHH:mm:ss.SSSZ} | {level} | {extra} | {message}",
        filter=lambda record: _redact_record(record),
    )
    return log_path


def _redact_record(record: dict[str, Any]) -> bool:
    record["message"] = redact(record["message"])
    record["extra"] = {key: redact(value) for key, value in record["extra"].items()}
    return True
