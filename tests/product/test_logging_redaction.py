from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from career_console.infrastructure.logging.setup import configure_logging


def test_exception_logs_do_not_capture_sensitive_local_variables(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path, level="INFO")
    sensitive_value = "credential-value-that-must-not-be-logged"

    try:
        raise RuntimeError("credential persistence failed")
    except RuntimeError:
        logger.exception("Unable to persist a credential")

    logger.complete()
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    serialized = json.dumps(records, ensure_ascii=False)

    assert "Unable to persist a credential" in serialized
    assert sensitive_value not in serialized
