import abc
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


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

    @abc.abstractmethod
    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        """
        Launches execution for this node. Typically queues a Celery task or
        runs synchronously as fallback.
        """
        raise NotImplementedError("Subclasses must implement execute().")

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
