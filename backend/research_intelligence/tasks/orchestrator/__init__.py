"""
Research Intelligence Orchestrator Package.

Provides the WorkflowDAG engine, pipeline definitions, and the ResearchAgentRunner
state machine execution engine.
"""

from .dag import (
    BaseWorkflowNode,
    WorkflowDAG,
    build_default_slr_dag,
    SearchNode,
    AbstractScreeningNode,
    DownloadNode,
    OCRNode,
    FullTextScreeningNode,
    ExtractionNode,
    SignalScoreNode,
    ReportingNode,
)
from .runner import ResearchAgentRunner
from .agent_engine import (
    notify_pipeline_orchestrator_tick,
    tick_agent_process,
    run_agent_process_tick,
)

__all__ = [
    "BaseWorkflowNode",
    "WorkflowDAG",
    "build_default_slr_dag",
    "SearchNode",
    "AbstractScreeningNode",
    "DownloadNode",
    "OCRNode",
    "FullTextScreeningNode",
    "ExtractionNode",
    "SignalScoreNode",
    "ReportingNode",
    "ResearchAgentRunner",
    "notify_pipeline_orchestrator_tick",
    "tick_agent_process",
    "run_agent_process_tick",
]
