import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SignalScoreNode(BaseWorkflowNode):
    """
    Composite Signal Score Evaluation (AST Sandboxed Python Formula).

    Inputs:
        - Extractions for all accepted papers.
        - Workspace.signal_score_code (sandboxed Python math formula).
        - Extracted variables mapped to snake_case (e.g. `fit_score`, `novelty_score`, `trl_level`).
    Outputs:
        - Created/updated PaperMetric.signal_score (float) and signal_score_details.
        - ComponentRun.metrics: scored_count, avg_signal_score, max_signal_score.
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
            "PaperMetric.signal_score": "float (composite calculated score, e.g. 0.0 - 100.0)",
            "PaperMetric.signal_score_details": "dict (variable audit)",
        },
        "component_run_metrics": {
            "scored_count": "int",
            "avg_signal_score": "float",
            "max_signal_score": "float",
        },
    }

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            scored = metrics.get('scored_count', 0)
            return f"Signal Scoring: Computed scores for {scored} paper(s)."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params.update(workspace.get_signal_score_prompt_snapshot())
        params["composite_extraction_schema"] = workspace.get_composite_extraction_schema()
        return params

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
        return self.dispatch_celery_task(execute_signal_score_job, comp_run, limit=limit)
