import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SignalScoreNode(BaseWorkflowNode):
    """
    Step 6: Composite Signal Score Evaluation (AST Sandboxed Python Formula).

    Inputs:
        - Extractions for all accepted papers.
        - Workspace.signal_score_code (sandboxed Python math formula).
        - Extracted variables mapped to snake_case (e.g. `fit_score`, `novelty_score`, `trl_level`).
    Outputs:
        - Updated Paper.signal_score (float).
        - Created/updated PaperMetric records with composite and sub-scores.
        - ComponentRun.metrics: papers_scored, avg_signal_score, top_score.
    """
    name = "signal_score"
    step_type = "signal_score"
    component_name = "signal_score_evaluation"
    description = "Evaluates composite ranking signal scores via sandboxed Python AST formulas."
    dependencies = ["extraction"]

    input_contract = {
        "extractions": "QuerySet[Extraction] (extractions attached to pipeline papers)",
        "signal_score_code": "str (workspace.signal_score_code: AST-sandboxed Python code)",
        "variables": "Dict[str, float] (sanitized extraction metrics like fit_score, novelty_score, trl_level)",
    }

    output_contract = {
        "updated_models": {
            "Paper.signal_score": "float (composite calculated score, e.g. 0.0 - 100.0)",
            "PaperMetric.signal_score": "float",
        },
        "component_run_metrics": {
            "papers_scored": "int",
            "avg_signal_score": "float",
            "top_score": "float",
        },
    }

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
        def _dispatch():
            try:
                async_res = execute_signal_score_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception as e:
                logger.warning(f"Failed to queue signal score async, executing synchronously: {e}")
                execute_signal_score_job(str(comp_run.id), limit=limit)

        safe_dispatch_on_commit(_dispatch)
        return {"status": "dispatched"}
