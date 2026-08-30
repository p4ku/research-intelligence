"""
Modular Django Models package for Schwarz Research Intelligence.
Preserves 100% backwards compatibility by re-exporting all models and helper classes.
"""

from .workspace import (
    Workspace,
    Subscriber,
    Scraper,
    WorkspaceMember,
    APIKey,
)
from .pipeline import (
    PipelineRun,
    ResearchAgentProcess,
    ComponentRun,
)
from .paper import (
    DocumentRegistry,
    Paper,
    PaperMetric,
)
from .extraction import (
    ExtractionDefinition,
    Extraction,
    HITLCorrection,
)
from .report import (
    NarrativeReport,
)
from .audit import (
    UserActivityLog,
)

# Re-export ejected Chat application models for backwards compatibility
from chat.models import PaperChatSession, PaperChatMessage

__all__ = [
    "Workspace",
    "Subscriber",
    "Scraper",
    "WorkspaceMember",
    "APIKey",
    "PipelineRun",
    "ResearchAgentProcess",
    "ComponentRun",
    "DocumentRegistry",
    "Paper",
    "PaperMetric",
    "ExtractionDefinition",
    "Extraction",
    "HITLCorrection",
    "NarrativeReport",
    "UserActivityLog",
    "PaperChatSession",
    "PaperChatMessage",
]
