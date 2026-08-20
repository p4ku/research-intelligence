import logging
from typing import Dict, Any, Optional, Tuple

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class ScreeningNode(BaseWorkflowNode):
    """
    Step 4: Two-stage AI Screening (Abstract Screening + Full-Text Screening).
    """
    name = "screening"
    step_type = "screening"
    component_name = "abstract_screening"
    dependencies = ["ocr"]

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        skip_abstract = config.get("skip_abstract_screening", getattr(workspace, 'skip_abstract_screening', False))
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params["skip_abstract_screening"] = skip_abstract
        return params

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import Paper
        accepted_count = Paper.objects.filter(workspace=workspace, screening_status='accepted').count()
        from research_intelligence.models import ComponentRun
        comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='screening')
        has_full_text = comp_runs.filter(component_name='full_text_screening', status='completed').exists()
        has_abstract_only = comp_runs.filter(component_name='abstract_screening', status='completed').exists() and config.get("skip_full_text_screening", False)

        if (has_full_text or has_abstract_only) and accepted_count == 0:
            return True, f"Screening finished: 0 papers were accepted for workspace '{workspace.name}'. Halting pipeline."
        return False, None

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        skip_abstract = comp_run.input_params.get("skip_abstract_screening", False)
        if comp_run.component_name == "full_text_screening" or skip_abstract:
            from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
            func = execute_full_text_screening_job
        else:
            from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
            func = execute_screening_job

        try:
            async_res = func.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue screening async, executing synchronously: {e}")
            res = func(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
