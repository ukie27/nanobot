"""Constrained fact extraction adapters."""

from nanobot.career.infrastructure.extraction.local import LocalResumeFactExtractor
from nanobot.career.infrastructure.extraction.local_job import LocalJobExtractor

__all__ = ["LocalJobExtractor", "LocalResumeFactExtractor"]
