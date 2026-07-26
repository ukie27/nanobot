"""CareerConsole internal Agent Runtime."""

from career_console import __version__

__logo__ = "🐈"

from career_console.runtime.facade import CareerAgent, RunResult

__all__ = ["CareerAgent", "RunResult", "__version__"]
