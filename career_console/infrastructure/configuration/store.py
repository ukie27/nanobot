"""Crash-safe JSON configuration persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from career_console.infrastructure.configuration.schema import ConfigurationDocument


class AtomicConfigurationStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def load(self) -> ConfigurationDocument | None:
        with self._lock:
            if not self.path.is_file():
                return None
            return ConfigurationDocument.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )

    def save(self, document: ConfigurationDocument) -> None:
        payload = document.model_dump(mode="json")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}-", dir=self.path.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(
                    descriptor, "w", encoding="utf-8", newline="\n"
                ) as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
