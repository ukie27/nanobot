"""Application-material workflow domain."""

from .agent_draft import (
    AgentMaterialFinding,
    MaterialReviewResult,
    ResumeDraftBlock,
    ResumeDraftResult,
)
from .direction import ResumeDirectionItem, ResumeDirectionResult
from .entities import (
    FactSnapshot,
    MaterialBlock,
    MaterialFinding,
    MaterialType,
    VersionStatus,
    review_material,
)

__all__ = [
    "FactSnapshot",
    "AgentMaterialFinding",
    "MaterialBlock",
    "MaterialFinding",
    "MaterialType",
    "MaterialReviewResult",
    "ResumeDraftBlock",
    "ResumeDraftResult",
    "ResumeDirectionItem",
    "ResumeDirectionResult",
    "VersionStatus",
    "review_material",
]
