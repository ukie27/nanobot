"""CareerConsole workspace management."""

from typing import TYPE_CHECKING, Any

from .directory_picker import DirectoryPickerUnavailableError, NativeDirectoryPicker
from .manager import (
    BootstrapRegistry,
    WorkspaceManager,
    WorkspacePaths,
    bootstrap_file_path,
    default_workspace_path,
)
from .onboarding import ONBOARDING_VERSION, OnboardingRecord, OnboardingService

if TYPE_CHECKING:
    from .portable import PortableWorkspaceError, PortableWorkspaceService

__all__ = [
    "BootstrapRegistry", "PortableWorkspaceError", "PortableWorkspaceService",
    "DirectoryPickerUnavailableError", "NativeDirectoryPicker",
    "ONBOARDING_VERSION", "OnboardingRecord", "OnboardingService",
    "WorkspaceManager", "WorkspacePaths", "bootstrap_file_path",
    "default_workspace_path",
]


def __getattr__(name: str) -> Any:
    """Load portable-workspace support without creating a settings import cycle."""
    if name in {"PortableWorkspaceError", "PortableWorkspaceService"}:
        from .portable import PortableWorkspaceError, PortableWorkspaceService

        return {
            "PortableWorkspaceError": PortableWorkspaceError,
            "PortableWorkspaceService": PortableWorkspaceService,
        }[name]
    raise AttributeError(name)
