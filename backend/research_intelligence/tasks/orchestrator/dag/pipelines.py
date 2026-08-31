"""
Pipeline Definitions for the Schwarz Research Intelligence DAG Workflow Engine.

This module defines standard, reusable Workflow DAG topologies for Systematic
Literature Review (SLR), deep-tech competitive scouting, and dynamic parameter extraction.

Architecture & Execution Topology:
===================================
The standard Systematic Literature Review pipeline consists of 7 modular stages
organized as a Directed Acyclic Graph (DAG):

  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                           STANDARD SLR WORKFLOW DAG                         │
  └─────────────────────────────────────────────────────────────────────────────┘

    [SearchNode]
           │ (fetches papers from ArXiv, OpenAlex, Lens, PubMed with deduplication)
           ▼
    [DownloadNode]
           │ (downloads PDFs in parallel & caches in Document Registry)
           ▼
    [OCRNode]  ─────────► [Skipped automatically if workspace.ocr_provider is None]
           │ (converts PDF layout to Markdown / Vision JSON)
           ▼
    [ScreeningNode]
           │ (Stage A: Abstract criteria -> Stage B: Multimodal Full-text criteria)
           ▼
    [ExtractionNode]
           │ (schema-validated parameter extraction with evidence quotes & confidence)
           ▼
    [SignalScoreNode]
           │ (sandboxed AST execution of custom mathematical formula on workspace)
           ▼
    [ReportingNode]  ───► [Generates narrative executive report & sends email alerts]

Topological Dependency Gating:
------------------------------
- Each node declares its default prerequisite dependencies directly on its class
  definition (e.g. `DownloadNode.dependencies = ["search"]`, `SignalScoreNode.dependencies = ["extraction"]`).
- When nodes are instantiated without arguments (e.g. `DownloadNode()`), they inherit
  their canonical dependencies automatically, eliminating redundant boilerplate.
- The `WorkflowDAG` engine validates that the graph is strictly acyclic (via Depth-First
  Search cycle detection) and evaluates readiness in real-time against `ComponentRun` DB records.
- A downstream node (e.g. `SignalScoreNode`) is ONLY dispatched when all its prerequisite
  nodes have reached 'completed' or 'skipped' status, guaranteeing sequential macro integrity
  while supporting micro-level worker parallelism on Celery.
"""

import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.engine import WorkflowDAG
from research_intelligence.tasks.orchestrator.dag.nodes import (
    SearchNode,
    AbstractScreeningNode,
    DownloadNode,
    OCRNode,
    FullTextScreeningNode,
    ExtractionNode,
    SignalScoreNode,
    ReportingNode,
)

logger = logging.getLogger(__name__)


def build_default_slr_dag(workspace=None, config: Optional[Dict[str, Any]] = None) -> WorkflowDAG:
    """
    Constructs, validates, and returns the canonical Systematic Literature Review Workflow DAG.

    Topology & Dependency Flow:
    ---------------------------
    1. SearchNode (dependencies: [])
       - Dispatches multi-source scrapers (ArXiv, OpenAlex, Lens, PubMed).
       - Ingests papers and deduplicates by Title, DOI, and arXiv ID.
       - Halts pipeline gracefully if 0 papers match workspace search criteria.

    2. AbstractScreeningNode (dependencies: ['search'])
       - First-stage AI screening: evaluates paper title & abstract against criteria.
       - Automatically marked as 'skipped' if skip_abstract_screening is True in workspace/config.
       - Halts pipeline gracefully if 0 papers pass abstract screening.

    3. DownloadNode (dependencies: ['abstract_screening'])
       - Multi-threaded PDF fetching to unified workspace storage.
       - Downloads ONLY abstract_passed papers (or all papers if abstract screening was skipped).
       - Uses global SHA-256 DocumentRegistry cache to prevent duplicate downloads.

    4. OCRNode (dependencies: ['download'])
       - Layout OCR conversion via PyPDF, Mistral OCR, or Gemini Vision.
        - Automatically marked as 'skipped' if workspace.ocr_provider is None,
          enabling multimodal Gemini 3.7 Flash direct PDF ingestion in Full-Text Screening.

    5. FullTextScreeningNode (dependencies: ['ocr'])
       - Second-stage AI screening: deep multimodal analysis of raw PDF binaries (or OCR Markdown).
       - Evaluates papers against workspace full-text acceptance and rejection criteria.
       - Halts pipeline gracefully if 0 papers pass full-text screening.

    6. ExtractionNode (dependencies: ['full_text_screening'])
       - Dynamic parameter extraction driven by ExtractionDefinition JSON schemas.
       - Generates schema-validated extractions with confidence scores and evidence quotes.

    7. SignalScoreNode (dependencies: ['extraction'])
       - Sandboxed Python AST evaluation of workspace.signal_score_code.
       - Computes composite signal score from extracted metrics (e.g. TRL, Fit, Novelty).

    8. ReportingNode (dependencies: ['signal_score'])
       - Generates executive narrative reports (Markdown/HTML).
       - Skippable if generate_narrative_report is False in workspace/config.
       - Dispatches transactional email notifications via Mailgun API.

    Args:
        workspace: Optional Workspace model instance for context-aware customization.
        config: Optional configuration dictionary overrides.

    Returns:
        WorkflowDAG: Fully configured, validated, and ready-to-execute DAG instance.
    """
    dag = WorkflowDAG(name="slr_systematic_review_dag")

    # Nodes declare their dependencies as class defaults.
    # Instantiating them directly inherits the canonical SLR pipeline dependency structure.
    dag.add_node(SearchNode())
    dag.add_node(AbstractScreeningNode())
    dag.add_node(DownloadNode())
    dag.add_node(OCRNode())
    dag.add_node(FullTextScreeningNode())
    dag.add_node(ExtractionNode())
    dag.add_node(SignalScoreNode())
    dag.add_node(ReportingNode())

    # Ensure the graph is strictly acyclic and all dependencies exist
    dag.validate_graph()

    return dag
