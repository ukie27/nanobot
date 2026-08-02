"""Career application services."""

from career_console.application.services.applications import CareerApplicationService
from career_console.application.services.connectors import (
    ConnectorApplicationService,
    NowcoderConnectorApplicationService,
)
from career_console.application.services.governance import GovernanceApplicationService
from career_console.application.services.interviews import InterviewApplicationService
from career_console.application.services.job_fit import JobFitApplicationService
from career_console.application.services.jobs import JobApplicationService
from career_console.application.services.mail import MailApplicationService
from career_console.application.services.material_agent import (
    MaterialAgentApplicationService,
)
from career_console.application.services.materials import MaterialApplicationService
from career_console.application.services.opportunities import OpportunityApplicationService
from career_console.application.services.profile import ProfileApplicationService
from career_console.application.services.profile_memory import (
    ProfileImpactApplicationService,
    ProfileMemoryApplicationService,
)
from career_console.application.services.recommendations import (
    JobRecommendationApplicationService,
)
from career_console.application.services.resume_direction import (
    ResumeDirectionApplicationService,
)
from career_console.application.services.review_maintenance import ReviewMaintenanceService
from career_console.application.services.runtime import RuntimeApplicationService
from career_console.application.services.standalone_resumes import (
    StandaloneResumeApplicationService,
)
from career_console.application.services.tasks import TaskApplicationService

__all__ = [
    "CareerApplicationService",
    "ConnectorApplicationService",
    "NowcoderConnectorApplicationService",
    "OpportunityApplicationService",
    "RuntimeApplicationService",
    "StandaloneResumeApplicationService",
    "ReviewMaintenanceService",
    "ResumeDirectionApplicationService",
    "GovernanceApplicationService",
    "JobApplicationService",
    "JobFitApplicationService",
    "JobRecommendationApplicationService",
    "InterviewApplicationService",
    "MaterialApplicationService",
    "MaterialAgentApplicationService",
    "MailApplicationService",
    "ProfileApplicationService",
    "ProfileImpactApplicationService",
    "ProfileMemoryApplicationService",
    "TaskApplicationService",
]
