"""FastAPI route dependencies."""

from filament_api.api.dependencies.auth import get_current_agent_context

__all__ = ["get_current_agent_context"]

