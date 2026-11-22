"""Local-first, cross-agent feedback collection."""
from importlib.metadata import PackageNotFoundError, version

from .service import FeedbackService

try:
    __version__ = version("agent-feedback-local")
except PackageNotFoundError:
    __version__ = "0.11.1"

__all__ = ["FeedbackService"]
