import logging
from typing import Dict, Any, Optional, Tuple

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class AbstractScreeningNode(BaseWorkflowNode):
    """
    Title & Abstract Screening (First-Stage AI Screening).

    Evaluates paper titles and abstracts against Workspace abstract acceptance/rejection criteria
    using Gemini 3.7 Flash before any PDF binary downloads occur.
    """
    name = "abstract_screening"
    step_type = "screening"
    component_name = "abstract_screening"
    description = "Evaluates paper titles & abstracts against Workspace criteria using Gemini 3.7 Flash."
    dependencies = ["search"]

    input_contract = {
        "abstract_stage": {
            "acceptance_criteria": "workspace.get_abstract_acceptance_criteria()",
            "rejection_criteria": "workspace.get_abstract_rejection_criteria()",
            "paper_fields": "Paper.title, Paper.abstract",
        },
        "llm_model": "google/gemini-3.7-flash",
    }

    output_contract = {
        "updated_models": {
            "Paper.screening_status": "'abstract_passed' | 'rejected' | 'pending'",
            "Paper.screening_reason": "Detailed markdown explanation with criteria evaluation",
            "Paper.screening_history": "JSON audit trail with timestamps and LLM confidence",
        },
        "component_run_metrics": {
            "total_screened": "int",
            "passed": "int",
            "rejected": "int",
        },
    }

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        return bool(config.get("skip_abstract_screening", getattr(workspace, 'skip_abstract_screening', False)))

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import Paper, ComponentRun
        reprocess = config.get("reprocess_existing", getattr(pipeline_run, 'reprocess_existing', False))
        comp_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            step_type='screening',
            component_name='abstract_screening',
            status='completed'
        ).first()

        if not comp_run:
            return False, None

        if reprocess:
            passed_count = Paper.objects.filter(workspace=workspace, screening_status__in=['abstract_passed', 'accepted', 'full_text_passed']).count()
            total_papers = Paper.objects.filter(workspace=workspace).count()
        else:
            passed_count = Paper.objects.filter(pipeline_run=pipeline_run, screening_status__in=['abstract_passed', 'accepted', 'full_text_passed']).count()
            total_papers = Paper.objects.filter(pipeline_run=pipeline_run).count()

        if total_papers > 0 and passed_count == 0:
            rejected_count = Paper.objects.filter(
                workspace=workspace if reprocess else pipeline_run.workspace,
                pipeline_run=pipeline_run,
                screening_status='rejected'
            ).count()
            return True, f"Abstract Screening: 0 papers accepted ({rejected_count}/{total_papers} rejected against criteria for workspace '{workspace.name}'). Pipeline halted cleanly."

        return False, None

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'skipped':
            return "Abstract Screening: Skipped (Proceeding directly to download)."
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            passed = metrics.get('passed', 0)
            rejected = metrics.get('rejected', 0)
            total = metrics.get('total_screened', 0)
            return f"Abstract Screening: {passed} passed, {rejected} rejected out of {total} screened."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params.update({
            "stage": "abstract",
            "llm_model": getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash'),
            "llm_provider": getattr(workspace, 'llm_provider', 'google'),
            "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
            "abstract_acceptance_criteria": workspace.get_abstract_acceptance_criteria(),
            "abstract_rejection_criteria": workspace.get_abstract_rejection_criteria(),
            "abstract_screening_system_prompt": workspace.get_abstract_screening_system_prompt(),
            "abstract_screening_user_prompt_template": workspace.get_abstract_screening_user_prompt_template(),
            "abstract_screening_exit_metric": workspace.get_abstract_screening_exit_metric(),
            "abstract_screening_response_schema": workspace.get_abstract_screening_response_schema(),
        })
        return params

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
        return self.dispatch_celery_task(execute_screening_job, comp_run, limit=limit)


class FullTextScreeningNode(BaseWorkflowNode):
    """
    Full-Text Screening (Second-Stage Multimodal AI Screening).

    Performs deep multimodal analysis of raw PDF binaries (or OCR Markdown) against
    Workspace full_text acceptance/rejection criteria using Gemini 3.7 Flash.
    """
    name = "full_text_screening"
    step_type = "screening"
    component_name = "full_text_screening"
    description = "Evaluates full PDF binary (or OCR Markdown) against full-text criteria using Gemini 3.7 Flash."
    dependencies = ["ocr"]

    input_contract = {
        "full_text_stage": {
            "acceptance_criteria": "workspace.get_full_text_acceptance_criteria()",
            "rejection_criteria": "workspace.get_full_text_rejection_criteria()",
            "document_content": "Raw binary PDF (or OCR markdown text)",
        },
        "llm_model": "google/gemini-3.7-flash",
    }

    output_contract = {
        "updated_models": {
            "Paper.screening_status": "'full_text_passed' | 'accepted' | 'rejected' | 'pending'",
            "Paper.screening_reason": "Detailed markdown explanation with criteria evaluation",
            "Paper.screening_history": "JSON audit trail with timestamps and LLM confidence",
        },
        "component_run_metrics": {
            "total_screened": "int",
            "passed": "int",
            "rejected": "int",
        },
    }

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        return bool(config.get("skip_full_text_screening", False))

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import Paper, ComponentRun
        reprocess = config.get("reprocess_existing", getattr(pipeline_run, 'reprocess_existing', False))
        comp_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            step_type='screening',
            component_name='full_text_screening',
            status='completed'
        ).first()

        if not comp_run:
            return False, None

        if reprocess:
            passed_count = Paper.objects.filter(workspace=workspace, screening_status__in=['full_text_passed', 'accepted']).count()
            total_papers = Paper.objects.filter(workspace=workspace).count()
        else:
            passed_count = Paper.objects.filter(pipeline_run=pipeline_run, screening_status__in=['full_text_passed', 'accepted']).count()
            total_papers = Paper.objects.filter(pipeline_run=pipeline_run).count()

        if total_papers > 0 and passed_count == 0:
            rejected_count = Paper.objects.filter(
                workspace=workspace if reprocess else pipeline_run.workspace,
                pipeline_run=pipeline_run,
                screening_status='rejected'
            ).count()
            return True, f"Full-Text Screening: 0 papers accepted ({rejected_count}/{total_papers} rejected against criteria for workspace '{workspace.name}'). Pipeline halted cleanly."

        return False, None

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'skipped':
            return "Full-Text Screening: Skipped."
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            passed = metrics.get('passed', 0)
            rejected = metrics.get('rejected', 0)
            total = metrics.get('total_screened', 0)
            return f"Full-Text Screening: {passed} accepted, {rejected} rejected out of {total} screened."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params.update({
            "stage": "full_text",
            "llm_model": getattr(workspace, 'screening_llm_model', 'google/gemini-3.7-flash'),
            "llm_provider": getattr(workspace, 'llm_provider', 'google'),
            "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
            "full_text_acceptance_criteria": workspace.get_full_text_acceptance_criteria(),
            "full_text_rejection_criteria": workspace.get_full_text_rejection_criteria(),
            "full_text_screening_system_prompt": workspace.get_full_text_screening_system_prompt(),
            "full_text_screening_user_prompt_template": workspace.get_full_text_screening_user_prompt_template(),
            "full_text_screening_exit_metric": workspace.get_full_text_screening_exit_metric(),
            "full_text_screening_response_schema": workspace.get_full_text_screening_response_schema(),
        })
        return params

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
        return self.dispatch_celery_task(execute_full_text_screening_job, comp_run, limit=limit)

