"""Content-addressed file storage and document parsing."""

from career_console.infrastructure.files.blob_store import LocalBlobStore
from career_console.infrastructure.files.document_parser import DocumentParser
from career_console.infrastructure.files.web_fetcher import SafeJobPageFetcher

__all__ = ["DocumentParser", "LocalBlobStore", "SafeJobPageFetcher"]
