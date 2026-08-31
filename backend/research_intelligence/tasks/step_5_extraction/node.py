import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class ExtractionNode(BaseWorkflowNode):
    """
    Dynamic Parameter Extraction with Pydantic schemas.

    Inputs:
        - Accepted Paper documents (full text / raw PDF).
        - Workspace.extraction_definitions (target schemas, JSON schema definitions, system prompts).
    Outputs:
        - Extraction DB records containing extracted JSON data, confidence score, evidence quotes,
          and validation status ('pass', 'warn', 'fail').
        - ComponentRun.metrics: papers_processed, extractions_created, validation_passed.
    """
    name = "extraction"
    step_type = "extraction"
    component_name = "parameter_extraction"
    description = "Extracts dynamic, schema-validated parameters, evidence quotes, and confidence scores."
    dependencies = ["full_text_screening"]

    input_contract = {
        "accepted_papers": "QuerySet[Paper] (papers with screening_status='accepted')",
        "extraction_definitions": "QuerySet[ExtractionDefinition] (workspace.extraction_definitions.all())",
        "llm_model": "ExtractionDefinition.llm_model (or workspace default)",
    }

    output_contract = {
        "extractions": "QuerySet[Extraction] (Extraction objects with extracted_data, confidence_score, evidence_quote, validation_status)",
        "component_run_metrics": {
            "papers_processed": "int",
            "extractions_created": "int",
            "validation_passed": "int",
        },
    }

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            extracted = metrics.get('extractions_count', metrics.get('succeeded', metrics.get('extractions_created', metrics.get('extracted_count', 0))))
            papers = metrics.get('papers_processed', metrics.get('total_papers', 0))
            return f"Extraction: {extracted} parameters extracted across {papers} accepted paper(s)."
        return super().generate_stage_summary(comp_run, status=status)

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
        return self.dispatch_celery_task(execute_extraction_job, comp_run, limit=limit)
