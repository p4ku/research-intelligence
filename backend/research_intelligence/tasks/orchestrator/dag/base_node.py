import abc
import logging
from typing import List, Dict, Any, Optional, Tuple

from django.db import connection, transaction

logger = logging.getLogger(__name__)


def safe_dispatch_on_commit(callback):
    """
    Executes callback immediately under SQLite test runner or when no atomic block exists;
    otherwise schedules execution via transaction.on_commit for PostgreSQL Celery concurrency safety.
    """
    if connection.vendor == 'postgresql' and transaction.get_connection().in_atomic_block:
        transaction.on_commit(callback)
    else:
        callback()


class BaseWorkflowNode(abc.ABC):
    """
    Abstract Base Class for all Workflow DAG Nodes in the SLR Pipeline.
    
    Each node represents a distinct processing stage (e.g. Search, Download, OCR,
    Screening, Extraction, Signal Scoring, Reporting).
    """

    name: str = ""
    step_type: str = ""
    component_name: str = ""
    description: str = ""
    dependencies: List[str] = []
    input_contract: Dict[str, Any] = {}
    output_contract: Dict[str, Any] = {}

    def __init__(
        self,
        name: Optional[str] = None,
        step_type: Optional[str] = None,
        component_name: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
    ):
        if name:
            self.name = name
        if step_type:
            self.step_type = step_type
        if component_name:
            self.component_name = component_name
        if dependencies is not None:
            self.dependencies = dependencies
        else:
            self.dependencies = list(self.dependencies)

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        """
        Returns True if this node should be marked as 'skipped' rather than executed.
        For example, OCRNode is skippable if workspace.ocr_provider is None.
        """
        return False

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Checks whether pipeline execution should halt early after this node finishes.
        For example, if 0 papers matched search criteria or 0 papers passed screening.
        Returns (should_halt: bool, reason_message: Optional[str]).
        """
        return False, None

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Constructs the dictionary of input parameters to store in ComponentRun.input_params.
        """
        params = {"limit": limit}
        if config:
            params.update({k: v for k, v in config.items() if k not in params})
        return params

    def dispatch_celery_task(self, task_func, comp_run, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Standardized, transactional dispatch routine for Celery tasks across all nodes.
        Attempts async Celery dispatch with celery_task_id tracking, falling back to
        synchronous execution if Celery is not available (or under test runners).
        Guarantees PostgreSQL transaction commit safety via safe_dispatch_on_commit.
        """
        def _dispatch():
            try:
                async_res = task_func.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception as e:
                logger.warning(f"Failed to queue {self.name} async, executing synchronously: {e}")
                task_func(str(comp_run.id), limit=limit)

        safe_dispatch_on_commit(_dispatch)
        return {"status": "dispatched"}

    def dispatch_multiple_celery_tasks(self, task_func, comp_runs: List[Any], limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Dispatches multiple ComponentRuns (e.g. multi-source parallel scrapers)
        safely on database transaction commit.
        """
        def _dispatch_all():
            for comp_run in comp_runs:
                try:
                    async_res = task_func.delay(str(comp_run.id), limit=limit)
                    comp_run.celery_task_id = async_res.id
                    comp_run.save(update_fields=['celery_task_id'])
                except Exception as e:
                    logger.warning(f"Failed to queue {self.name} scraper async, executing synchronously: {e}")
                    task_func(str(comp_run.id), limit=limit)

        safe_dispatch_on_commit(_dispatch_all)
        return {"status": "dispatched", "tasks_count": len(comp_runs)}

    @abc.abstractmethod
    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        """
        Launches execution for this node. Typically delegates to self.dispatch_celery_task().
        """
        raise NotImplementedError("Subclasses must implement execute().")

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        """
        Subclasses override this to return rich, domain-specific summary text
        describing what happened during this stage (e.g. counts, results, decisions).
        """
        if status == 'failed':
            err = (comp_run.error_message if comp_run else None) or 'Unknown error'
            return f"{self.name.title()} failed: {err}"
        elif status == 'skipped':
            return f"{self.name.title()}: Skipped."
        elif status == 'running':
            return f"{self.name.title()} currently executing..."
        return f"{self.name.title()} completed successfully."

    def get_stage_result_entry(self, comp_run=None, status: str = "pending") -> Dict[str, Any]:
        """
        Constructs the structured stage results payload for this node.
        """
        from django.utils import timezone
        st = comp_run.status if comp_run else status
        metrics = dict(comp_run.metrics or {}) if comp_run else {}
        error = comp_run.error_message if comp_run else None
        comp_name = getattr(comp_run, 'component_name', self.component_name)

        return {
            "status": st,
            "summary": self.generate_stage_summary(comp_run, status=st),
            "metrics": metrics,
            "error": error,
            "component_name": comp_name,
            "updated_at": timezone.now().isoformat()
        }

    def on_completed(self, pipeline_run, comp_run, result_data: Optional[Dict[str, Any]] = None):
        """
        Hook called when this node completes successfully.
        """
        logger.info(f"DAG Node '{self.name}' completed for PipelineRun {pipeline_run.id}")

    def on_failed(self, pipeline_run, comp_run, error_message: Optional[str] = None):
        """
        Hook called when this node fails.
        """
        logger.error(f"DAG Node '{self.name}' failed for PipelineRun {pipeline_run.id}: {error_message}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', step_type='{self.step_type}', deps={self.dependencies})>"
