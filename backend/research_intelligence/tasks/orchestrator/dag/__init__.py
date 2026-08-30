"""
Workflow DAG Orchestrator Framework.
Provides BaseWorkflowNode, concrete SLR pipeline nodes, and the WorkflowDAG graph engine.
"""

from .base_node import BaseWorkflowNode
from .engine import WorkflowDAG
from .pipelines import build_default_slr_dag
from .nodes import (
    SearchNode,
    AbstractScreeningNode,
    DownloadNode,
    OCRNode,
    FullTextScreeningNode,
    ExtractionNode,
    SignalScoreNode,
    ReportingNode,
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
]
