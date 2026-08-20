import re
import logging
from typing import Dict, Any, Tuple, Optional
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections

from research_intelligence.models import Paper, PaperMetric, ComponentRun, Extraction
from research_intelligence.utils.sandbox import execute_sandboxed_snippet, SandboxSecurityError, SandboxExecutionError

logger = logging.getLogger(__name__)


def _sanitize_identifier(name: str) -> str:
    """
    Converts a human-readable definition name (e.g. 'TRL Level', 'Fit-Score (0-100)')
    into a valid Python snake_case variable identifier (e.g. 'trl_level', 'fit_score_0_100').
    """
    if not name:
        return "param"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', name.strip().lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    if clean and clean[0].isdigit():
        clean = f"v_{clean}"
    return clean or "param"


def _parse_numeric_value(val: Any) -> Any:
    """
    Converts raw extraction value to float/int if possible, handling strings like '4', 'TRL 4', '95%'.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    str_val = str(val).strip()
    if not str_val or str_val == "-":
        return 0.0

    # Handle percentage e.g. "85%" -> 0.85
    if str_val.endswith("%"):
        try:
            return float(str_val[:-1].strip()) / 100.0
        except ValueError:
            pass

    # Try direct float conversion
    try:
        return float(str_val)
    except ValueError:
        pass

    # Try extracting first number from string e.g. "TRL 4" -> 4.0, "Score: 8.5" -> 8.5
    match = re.search(r'[-+]?\d*\.?\d+', str_val)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass

    return str_val


def extract_paper_parameters(paper: Paper) -> Dict[str, Any]:
    """
    Collects all parameter extractions for a Paper and returns a clean dictionary
    with sanitized Python variable names and parsed numeric/string values.
    Initializes configured workspace extraction definitions to 0.0 default.
    """
    context: Dict[str, Any] = {}

    # Pre-populate defaults from workspace extraction definitions
    if paper.workspace:
        for ed in paper.workspace.extraction_definitions.all():
            if ed.name:
                context[_sanitize_identifier(ed.name)] = 0.0
            if ed.exit_metric:
                context[_sanitize_identifier(ed.exit_metric)] = 0.0

    extractions = paper.extractions.all().select_related('extraction_definition')

    for ext in extractions:
        raw_val = ext.exit_metric or ext.get_exit_metric() or ""
        parsed_val = _parse_numeric_value(raw_val)

        # 1. Map by ExtractionDefinition name (e.g. 'TRL Level' -> 'trl_level')
        if ext.extraction_definition and ext.extraction_definition.name:
            key_name = _sanitize_identifier(ext.extraction_definition.name)
            context[key_name] = parsed_val

        # 2. Map by exit_metric key if configured (e.g. 'fit_score')
        if ext.extraction_definition and ext.extraction_definition.exit_metric:
            key_metric = _sanitize_identifier(ext.extraction_definition.exit_metric)
            context[key_metric] = parsed_val

        # 3. Map by category if available
        if ext.category:
            key_cat = _sanitize_identifier(ext.category)
            if key_cat not in context:
                context[key_cat] = parsed_val

        # Also store raw field data values if available
        if ext.fields_data and isinstance(ext.fields_data, dict):
            fields_dict = ext.fields_data.get("fields", ext.fields_data)
            if isinstance(fields_dict, dict):
                for f_k, f_v in fields_dict.items():
                    sanitized_f_k = _sanitize_identifier(f_k)
                    if sanitized_f_k not in context:
                        context[sanitized_f_k] = _parse_numeric_value(f_v)

    return context


def compute_paper_signal_score(
    paper_id_or_obj: Any,
    custom_code: Optional[str] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Computes the composite signal score for a Paper using the Workspace's sandboxed Python code.
    Saves the calculated signal_score and audit details onto the Paper and PaperMetric models.
    """
    if isinstance(paper_id_or_obj, Paper):
        paper = paper_id_or_obj
    else:
        paper = Paper.objects.select_related('workspace').get(pk=paper_id_or_obj)

    workspace = paper.workspace
    code_to_run = custom_code if custom_code is not None else (workspace.signal_score_code or "")

    context_vars = extract_paper_parameters(paper)

    error_msg = None
    try:
        score = execute_sandboxed_snippet(
            code_snippet=code_to_run,
            context_vars=context_vars,
            timeout_seconds=2.0
        )
    except (SandboxSecurityError, SandboxExecutionError, Exception) as e:
        logger.error(f"❌ [SIGNAL SCORE ERROR] Paper '{paper.title[:30]}' ({paper.id}): {e}")
        score = 0.0
        error_msg = str(e)

    details = {
        "variables": context_vars,
        "code_snippet": code_to_run,
        "score": score,
        "calculated_at": timezone.now().isoformat(),
        "error": error_msg
    }

    # Persist on Paper model
    paper.signal_score = score
    paper.signal_score_details = details
    paper.save(update_fields=['signal_score', 'signal_score_details'])

    # Persist on PaperMetric model
    metric, _ = PaperMetric.objects.get_or_create(
        paper=paper,
        workspace=workspace,
        defaults={"signal_score": score, "signal_score_details": details}
    )
    if metric.signal_score != score or metric.signal_score_details != details:
        metric.signal_score = score
        metric.signal_score_details = details
        metric.save(update_fields=['signal_score', 'signal_score_details'])

    return score, details


@shared_task(bind=True)
def execute_signal_score_job(self, component_run_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Step 6 Celery Task: Evaluates the composite signal score for all screened/accepted papers
    in the active PipelineRun using the Workspace's sandboxed Python logic.
    """
    close_old_connections()

    try:
        comp_run = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(pk=component_run_id)
    except ComponentRun.DoesNotExist:
        logger.error(f"ComponentRun {component_run_id} does not exist.")
        return {"success": False, "error": "ComponentRun not found"}

    pipeline_run = comp_run.pipeline_run
    workspace = pipeline_run.workspace

    logger.info(f"🚀 [STEP 6 START] Signal Score Evaluation for Run {pipeline_run.id} in Workspace '{workspace.name}'")

    comp_run.status = 'running'
    comp_run.started_at = timezone.now()
    comp_run.save(update_fields=['status', 'started_at'])

    # Query all papers that passed screening
    accepted_statuses = ['accepted', 'full_text_passed', 'abstract_passed']
    papers_qs = Paper.objects.filter(
        pipeline_run=pipeline_run,
        screening_status__in=accepted_statuses
    ).order_by('-created_at')

    if limit and limit > 0:
        papers = list(papers_qs[:limit])
    else:
        papers = list(papers_qs)

    total_papers = len(papers)
    scored_count = 0
    scores_list = []
    errors_list = []

    evaluated_papers = []
    for paper in papers:
        close_old_connections()
        try:
            score, details = compute_paper_signal_score(paper)
            scores_list.append(score)
            scored_count += 1
            evaluated_papers.append({
                "paper_id": str(paper.id),
                "hash_id": paper.hash_id,
                "title": paper.title,
                "authors": paper.authors,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "screening_status": paper.screening_status,
                "signal_score": score,
                "variables": details.get("variables", {}),
                "error": details.get("error")
            })
            if details.get("error"):
                errors_list.append({"paper_id": str(paper.id), "error": details["error"]})
        except Exception as e:
            logger.exception(f"Unexpected error scoring paper {paper.id}: {e}")
            errors_list.append({"paper_id": str(paper.id), "error": str(e)})
            evaluated_papers.append({
                "paper_id": str(paper.id),
                "hash_id": paper.hash_id,
                "title": paper.title,
                "signal_score": 0.0,
                "error": str(e)
            })

    avg_score = float(sum(scores_list) / len(scores_list)) if scores_list else 0.0
    max_score = float(max(scores_list)) if scores_list else 0.0
    min_score = float(min(scores_list)) if scores_list else 0.0

    metrics = {
        "total_papers": total_papers,
        "scored_count": scored_count,
        "avg_signal_score": avg_score,
        "max_signal_score": max_score,
        "min_signal_score": min_score,
        "errors_count": len(errors_list),
        "errors": errors_list[:10],
    }

    output_data = {
        "summary": {
            "total_papers": total_papers,
            "scored_count": scored_count,
            "avg_signal_score": round(avg_score, 2),
            "max_signal_score": round(max_score, 2),
            "min_signal_score": round(min_score, 2),
            "errors_count": len(errors_list)
        },
        "signal_score_code": workspace.signal_score_code,
        "papers": evaluated_papers
    }

    comp_run.status = 'completed'
    comp_run.completed_at = timezone.now()
    comp_run.metrics = metrics
    comp_run.output_data = output_data
    comp_run.save(update_fields=['status', 'completed_at', 'metrics', 'output_data'])

    logger.info(
        f"🏁 [STEP 6 FINISHED] Signal Score Evaluation Run {pipeline_run.id}: "
        f"Scored {scored_count}/{total_papers} papers. Avg Score: {avg_score:.2f}, Max: {max_score:.2f}."
    )

    # If no agent process is running (e.g. manual step trigger), update pipeline_run to completed
    if not pipeline_run.agent_processes.filter(status='running').exists():
        if not pipeline_run.component_runs.filter(status__in=['pending', 'running']).exclude(id=comp_run.id).exists():
            pipeline_run.status = 'completed'
            pipeline_run.current_stage = 'completed'
            if not pipeline_run.completed_at:
                pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at'])

    # Notify Orchestrator state machine
    try:
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(str(pipeline_run.id))
    except Exception as e:
        logger.warning(f"Failed to notify orchestrator tick after signal scoring: {e}")

    return {
        "success": True,
        "component_run_id": str(comp_run.id),
        "metrics": metrics
    }
