"""Mail classification domain primitives."""

from .entities import MailClassification, MailEventKind, classification_from_text
from .intelligence import MailIntelligenceResult

__all__ = ["MailClassification", "MailEventKind", "MailIntelligenceResult", "classification_from_text"]
