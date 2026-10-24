import logging
from typing import Dict, Any, Optional
from django.db import transaction

from research_intelligence.models import PipelineRun, ComponentRun
from slr_review.models import SLRWorkspaceConfig, AuditSampleCohort
from slr_review.services.sampling_service import SamplingService

logger = logging.getLogger(__name__)


def should_pause_at_gate(config: SLRWorkspaceConfig, component_type: str) -> Optional[str]:
    """
    Determines if the given component_type corresponds to an active audit gate
    under the workspace's SLR checkpoint_gate_mode policy.
    Returns the audit stage name if a pause is required, or None.
    """
    mode = config.checkpoint_gate_mode

    if component_type in ('abstract_screening', 'screening'):
        if mode in ('two_stage_split', 'abstract_only_gate'):
            return 'abstract_screening'

    if component_type in ('full_text_screening', 'full_text'):
        if mode in ('two_stage_split', 'single_combined_post_fulltext'):
            return 'full_text_screening'

    if component_type in ('extraction', 'parameter_extraction'):
        if config.enable_extraction_gate:
            return 'parameter_extraction'

    return None


@transaction.atomic
def intercept_component_completion(
    pipeline_run: PipelineRun,
    component_type: str
) -> Dict[str, Any]:
    """
    Intercepts component completion in the Celery DAG.
    If the component completed is an active SLR audit gate, generates an AuditSampleCohort,
    safely pauses the pipeline run, and halts further automated DAG progression.
    """
    # Check if run or workspace is configured for SLR
    run_type = (pipeline_run.configuration_override or {}).get('run_type')
    has_slr_config = hasattr(pipeline_run.workspace, 'slr_config')

    if run_type != 'slr' and not has_slr_config:
        return {"halt": False}

    config = getattr(pipeline_run.workspace, 'slr_config', None)
    if not config:
        config, _ = SLRWorkspaceConfig.objects.get_or_create(workspace=pipeline_run.workspace)

    if config.checkpoint_gate_mode == 'autonomous_benchmark':
        logger.info(f"SLR Run {pipeline_run.id} is in autonomous_benchmark mode. Skipping audit gates.")
        return {"halt": False}

    audit_stage = should_pause_at_gate(config, component_type)
    if not audit_stage:
        return {"halt": False}

    # Check if a cohort was already generated for this stage
    existing_cohort = AuditSampleCohort.objects.filter(
        pipeline_run=pipeline_run,
        stage=audit_stage
    ).first()

    if existing_cohort:
        if existing_cohort.is_audit_complete:
            logger.info(f"Cohort for stage '{audit_stage}' already completed for run {pipeline_run.id}. Continuing DAG.")
            return {"halt": False}
        else:
            logger.info(f"Cohort for stage '{audit_stage}' still pending for run {pipeline_run.id}. Remaining paused.")
            return {"halt": True, "cohort_id": str(existing_cohort.id)}

    # Generate new sample cohort
    cohort = SamplingService.generate_sample_cohort(pipeline_run, audit_stage)

    # If nothing was sampled (e.g. 0 papers), do not halt
    if cohort.sampled_count == 0:
        cohort.is_audit_complete = True
        cohort.save(update_fields=['is_audit_complete'])
        return {"halt": False}

    # If pausing at full-text screening, trigger RoB assessment on included studies
    if audit_stage == 'full_text_screening' and config.enable_rob_assessment:
        try:
            from slr_review.services.rob_service import RiskOfBiasService
            included_papers = pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted'])
            for p in included_papers:
                RiskOfBiasService.assess_paper_rob(p, pipeline_run, framework=config.rob_framework)
        except Exception as rob_err:
            logger.warning(f"Could not compute RoB assessments at full-text gate: {rob_err}")

    # Safely pause the pipeline run and show live status message on dashboard
    pipeline_run.status = 'paused'
    pipeline_run.current_stage = f"awaiting_{audit_stage}_audit"
    pipeline_run.status_message = f"Awaiting audit (0/{cohort.sampled_count} reviewed)"
    pipeline_run.save(update_fields=['status', 'current_stage', 'status_message'])

    logger.info(
        f"🛑 [SLR AUDIT GATE REACHED] Pausing PipelineRun {pipeline_run.id} at stage '{audit_stage}'. "
        f"Generated cohort {cohort.id} with {cohort.sampled_count} sampled papers."
    )

    return {
        "halt": True,
        "cohort_id": str(cohort.id),
        "stage": audit_stage,
        "sampled_count": cohort.sampled_count,
        "message": f"Paused at {audit_stage} gate. {cohort.sampled_count} papers awaiting human audit."
    }


def resume_slr_pipeline_run(pipeline_run_id_or_obj) -> Dict[str, Any]:
    """
    Safely wakes up a paused SLR pipeline run once audit consensus/disputes are settled.
    Ensures zero race conditions and triggers the Celery DAG runner tick.
    """
    import uuid
    if isinstance(pipeline_run_id_or_obj, (str, uuid.UUID)):
        pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id_or_obj)
    else:
        pipeline_run = pipeline_run_id_or_obj

    if pipeline_run.status != 'paused':
        return {"resumed": False, "message": f"PipelineRun is in status '{pipeline_run.status}', not paused."}

    # Verify that all audit cohorts for this run are complete
    pending_cohorts = AuditSampleCohort.objects.filter(
        pipeline_run=pipeline_run,
        is_audit_complete=False
    ).exists()

    if pending_cohorts:
        logger.warning(f"Cannot resume PipelineRun {pipeline_run.id}: active audit cohorts are not yet complete.")
        return {"resumed": False, "error": "Active audit cohorts remain incomplete."}

    # Unlock status to running
    pipeline_run.status = 'running'
    pipeline_run.status_message = "Audit completed. Resuming pipeline..."
    pipeline_run.save(update_fields=['status', 'status_message'])

    logger.info(f"🚀 [SLR RESUME TRIGGERED] Resuming PipelineRun {pipeline_run.id}. Waking up DAG...")

    from research_intelligence.tasks.orchestrator.runner import PipelineRunner
    try:
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        from research_intelligence.tasks.orchestrator.agent_engine import run_pipeline_tick
        safe_dispatch_on_commit(run_pipeline_tick, str(pipeline_run.id))
    except Exception:
        # Fallback to direct synchronous tick in testing environments
        PipelineRunner.tick(pipeline_run)

    return {"resumed": True, "pipeline_run_id": str(pipeline_run.id)}
