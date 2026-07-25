"""Mail classification domain primitives."""

from .entities import MailClassification, MailEventKind, classification_from_text

__all__ = ["MailClassification", "MailEventKind", "classification_from_text"]
