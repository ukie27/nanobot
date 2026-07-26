"""Career application services."""

from nanobot.career.application.services.applications import CareerApplicationService
from nanobot.career.application.services.connectors import (
    ConnectorApplicationService,
    NowcoderConnectorApplicationService,
)
from nanobot.career.application.services.governance import GovernanceApplicationService
from nanobot.career.application.services.interviews import InterviewApplicationService
from nanobot.career.application.services.job_fit import JobFitApplicationService
from nanobot.career.application.services.jobs import JobApplicationService
from nanobot.career.application.services.mail import MailApplicationService
from nanobot.career.application.services.material_agent import MaterialAgentApplicationService
from nanobot.career.application.services.materials import MaterialApplicationService
from nanobot.career.application.services.opportunities import OpportunityApplicationService
from nanobot.career.application.services.profile import ProfileApplicationService
from nanobot.career.application.services.profile_memory import (
    ProfileImpactApplicationService,
    ProfileMemoryApplicationService,
)
from nanobot.career.application.services.resume_direction import ResumeDirectionApplicationService
from nanobot.career.application.services.runtime import RuntimeApplicationService
from nanobot.career.application.services.tasks import TaskApplicationService

__all__ = [
    "CareerApplicationService",
    "ConnectorApplicationService",
    "NowcoderConnectorApplicationService",
    "OpportunityApplicationService",
    "RuntimeApplicationService",
    "ResumeDirectionApplicationService",
    "GovernanceApplicationService",
    "JobApplicationService",
    "JobFitApplicationService",
    "InterviewApplicationService",
    "MaterialApplicationService",
    "MaterialAgentApplicationService",
    "MailApplicationService",
    "ProfileApplicationService",
    "ProfileImpactApplicationService",
    "ProfileMemoryApplicationService",
    "TaskApplicationService",
]
