import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SignalScoreNode(BaseWorkflowNode):
    """
    Step 6: Composite Signal Score Evaluation (AST Sandboxed Python Formula).
    """
    name = "signal_score"
    step_type = "signal_score"
    component_name = "signal_score_evaluation"
    dependencies = ["extraction"]

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
        try:
            async_res = execute_signal_score_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue signal score async, executing synchronously: {e}")
            res = execute_signal_score_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
