"""Controlled adapters from Career application ports to CareerConsole providers."""

from career_console.infrastructure.agents.fact_extractor import (
    CareerProfileFactExtractor,
    RuntimeConfiguredProfileFactExtractor,
    UnavailableProfileFactExtractor,
)
from career_console.infrastructure.agents.job_fit import CareerJobFitAnalyzer
from career_console.infrastructure.agents.job_recommendation import (
    CareerJobRecommendationAnalyzer,
)
from career_console.infrastructure.agents.mail_intelligence import CareerMailIntelligenceAnalyzer
from career_console.infrastructure.agents.material_drafting import (
    CareerMaterialReviewer,
    CareerResumeDrafter,
)
from career_console.infrastructure.agents.profile_insight import CareerProfileInsightAnalyzer
from career_console.infrastructure.agents.resume_direction import CareerResumeDirectionAnalyzer

__all__ = [
    "CareerMailIntelligenceAnalyzer",
    "CareerJobFitAnalyzer",
    "CareerJobRecommendationAnalyzer",
    "CareerProfileFactExtractor",
    "RuntimeConfiguredProfileFactExtractor",
    "UnavailableProfileFactExtractor",
    "CareerProfileInsightAnalyzer",
    "CareerResumeDirectionAnalyzer",
    "CareerResumeDrafter",
    "CareerMaterialReviewer",
]
