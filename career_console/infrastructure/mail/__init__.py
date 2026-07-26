"""Read-only mail infrastructure."""

from .imap_client import ImapReadOnlyError, StdlibReadOnlyImapClient
from .parser import parse_header, parse_message

__all__ = ["ImapReadOnlyError", "StdlibReadOnlyImapClient", "parse_header", "parse_message"]
