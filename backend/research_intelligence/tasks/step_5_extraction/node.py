import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class ExtractionNode(BaseWorkflowNode):
    """
    Step 5: Dynamic Parameter Extraction with Pydantic schemas.

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
    dependencies = ["screening"]

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

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
        try:
            async_res = execute_extraction_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue extraction async, executing synchronously: {e}")
            res = execute_extraction_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
