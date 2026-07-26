"""Constrained fact extraction adapters."""

from career_console.infrastructure.extraction.local import LocalResumeFactExtractor
from career_console.infrastructure.extraction.local_job import LocalJobExtractor

__all__ = ["LocalJobExtractor", "LocalResumeFactExtractor"]
