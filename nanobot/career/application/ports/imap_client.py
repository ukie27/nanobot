"""Strictly read-only IMAP client contract."""

from typing import Protocol


class ImapReadOnlyError(RuntimeError):
    def __init__(self, message: str, *, code: str = "imap_unavailable") -> None:
        super().__init__(message)
        self.code = code


class ReadOnlyImapClient(Protocol):
    def test_connection(self, **config: object) -> dict: ...
    def synchronize(self, **config: object) -> dict: ...
