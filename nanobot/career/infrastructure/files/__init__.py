"""Content-addressed file storage and document parsing."""

from nanobot.career.infrastructure.files.blob_store import LocalBlobStore
from nanobot.career.infrastructure.files.document_parser import DocumentParser
from nanobot.career.infrastructure.files.web_fetcher import SafeJobPageFetcher

__all__ = ["DocumentParser", "LocalBlobStore", "SafeJobPageFetcher"]
