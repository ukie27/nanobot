"""Controlled adapters from Career application ports to nanobot providers."""

from nanobot.career.agent.fact_extractor import NanobotProfileFactExtractor
from nanobot.career.agent.job_fit import NanobotJobFitAnalyzer
from nanobot.career.agent.mail_intelligence import NanobotMailIntelligenceAnalyzer
from nanobot.career.agent.material_drafting import NanobotMaterialReviewer, NanobotResumeDrafter
from nanobot.career.agent.profile_insight import NanobotProfileInsightAnalyzer
from nanobot.career.agent.resume_direction import NanobotResumeDirectionAnalyzer

__all__ = [
    "NanobotMailIntelligenceAnalyzer",
    "NanobotJobFitAnalyzer",
    "NanobotProfileFactExtractor",
    "NanobotProfileInsightAnalyzer",
    "NanobotResumeDirectionAnalyzer",
    "NanobotResumeDrafter",
    "NanobotMaterialReviewer",
]
