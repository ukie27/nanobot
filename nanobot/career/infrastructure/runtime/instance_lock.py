"""Single-instance lock for the local Career service."""

from __future__ import annotations

from pathlib import Path

from filelock import FileLock, Timeout


class InstanceAlreadyRunningError(RuntimeError):
    pass


class CareerInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = FileLock(str(path))

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            raise InstanceAlreadyRunningError(
                f"Another Career service instance holds {self.path}"
            ) from exc

    def release(self) -> None:
        if self._lock.is_locked:
            self._lock.release()

    def __enter__(self) -> "CareerInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
