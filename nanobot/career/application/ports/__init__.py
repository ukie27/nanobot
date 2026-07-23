"""Ports implemented by Career infrastructure."""

from nanobot.career.application.ports.fact_extractor import ExtractedFact, FactExtractor
from nanobot.career.application.ports.job_extractor import (
    ExtractedJob,
    ExtractedRequirement,
    JobExtractor,
)
from nanobot.career.application.ports.job_gateway import JobGateway
from nanobot.career.application.ports.profile_gateway import ProfileGateway
from nanobot.career.application.ports.unit_of_work import UnitOfWork

__all__ = [
    "ExtractedFact",
    "ExtractedJob",
    "ExtractedRequirement",
    "FactExtractor",
    "JobExtractor",
    "JobGateway",
    "ProfileGateway",
    "UnitOfWork",
]
