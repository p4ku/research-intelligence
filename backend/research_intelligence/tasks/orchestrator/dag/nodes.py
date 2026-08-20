import logging
from typing import Dict, Any, Optional, Tuple

from .base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SearchNode(BaseWorkflowNode):
    """
    Step 1: Multi-source search & paper ingestion (ArXiv, OpenAlex, Lens, PubMed).
    """
    name = "search"
    step_type = "search"
    component_name = "workspace_search"
    dependencies = []

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        reprocess = config.get("reprocess_existing", False)
        # Check if any papers exist for this workspace
        from research_intelligence.models import Paper
        papers_count = Paper.objects.filter(workspace=workspace).count()
        if papers_count == 0 and not reprocess:
            return True, f"Search completed but 0 papers were found matching criteria for workspace '{workspace.name}'. Halting pipeline."
        return False, None

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_1_search.search import execute_workspace_search
        try:
            async_res = execute_workspace_search.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue search async, executing synchronously: {e}")
            res = execute_workspace_search(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res


class DownloadNode(BaseWorkflowNode):
    """
    Step 2: Parallel PDF document download & registry caching.
    """
    name = "download"
    step_type = "download"
    component_name = "document_download"
    dependencies = ["search"]

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
        try:
            async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue download async, executing synchronously: {e}")
            res = execute_pdf_download_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res


class OCRNode(BaseWorkflowNode):
    """
    Step 3: Document Layout OCR Conversion (Optional / Skippable if ocr_provider is None).
    """
    name = "ocr"
    step_type = "ocr"
    component_name = "layout_ocr"
    dependencies = ["download"]

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        provider = config.get("ocr_provider", workspace.ocr_provider)
        return not provider or provider in ("None", "none", "")

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
        try:
            async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue OCR async, executing synchronously: {e}")
            res = execute_ocr_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res


class ScreeningNode(BaseWorkflowNode):
    """
    Step 4: Two-stage AI Screening (Abstract Screening + Full-Text Screening).
    """
    name = "screening"
    step_type = "screening"
    component_name = "abstract_screening"
    dependencies = ["ocr"]

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        skip_abstract = config.get("skip_abstract_screening", workspace.skip_abstract_screening)
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params["skip_abstract_screening"] = skip_abstract
        return params

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import Paper
        accepted_count = Paper.objects.filter(workspace=workspace, screening_status='accepted').count()
        # If screening finished and 0 papers were accepted
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


class ExtractionNode(BaseWorkflowNode):
    """
    Step 5: Dynamic Parameter Extraction with Pydantic schemas.
    """
    name = "extraction"
    step_type = "extraction"
    component_name = "parameter_extraction"
    dependencies = ["screening"]

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


class ReportingNode(BaseWorkflowNode):
    """
    Step 7 / Auxiliary: Executive Narrative & Notification Dispatch.
    """
    name = "reporting"
    step_type = "reporting"
    component_name = "executive_narrative"
    dependencies = ["signal_score"]

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        # Skippable if no narrative reporting requested in config
        return not config.get("generate_narrative_report", False)

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        # Auxiliary reporting execution placeholder
        comp_run.status = "completed"
        comp_run.save(update_fields=['status'])
        return {"status": "completed"}
