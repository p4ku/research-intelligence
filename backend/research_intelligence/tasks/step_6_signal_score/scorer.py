import re
import logging
from typing import Dict, Any, Tuple, Optional, Union
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction

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


def _parse_numeric_value(val: Any) -> Union[float, int, str]:
    """Attempts to parse a numeric value from float, int, dict, or string with units."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, dict):
        for k in ("score", "numeric_value", "value", "normalized_value"):
            if k in val and val[k] is not None:
                return _parse_numeric_value(val[k])
        return 0.0

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


def get_workspace_default_scoring_context(workspace) -> Dict[str, Any]:
    """
    Precomputes the default variables context for a workspace's extraction definitions once,
    avoiding repeated database queries and AST parsing per paper.
    """
    context: Dict[str, Any] = {}
    if not workspace:
        return context

    for ed in workspace.extraction_definitions.all():
        if ed.name:
            name_slug = _sanitize_identifier(ed.name)
            context[name_slug] = 0.0
            if ed.postprocessing_code and ed.postprocessing_code.strip():
                context[f"{name_slug}_postprocessed"] = 0.0
                context[f"{name_slug}_computed"] = 0.0
        if ed.exit_metrics:
            exit_metrics = ed.get_exit_metrics_list()
            for exit_m in exit_metrics:
                context[exit_m] = 0.0
            primary_exit = ed.get_primary_exit_metric()
            if primary_exit and ed.postprocessing_code and ed.postprocessing_code.strip():
                context[f"{primary_exit}_postprocessed"] = 0.0
                context[f"{primary_exit}_computed"] = 0.0

        if ed.postprocessing_code and ed.postprocessing_code.strip():
            try:
                import ast
                post_ast = ast.parse(ed.postprocessing_code)
                for node in ast.walk(post_ast):
                    if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                        for k_node in node.value.keys:
                            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str):
                                ret_k = _sanitize_identifier(k_node.value)
                                if ret_k and ret_k not in context:
                                    context[ret_k] = 0.0
            except Exception:
                pass

    return context


def extract_paper_parameters(
    paper: Paper,
    pipeline_run: Optional[Any] = None,
    preloaded_extractions: Optional[list] = None,
    default_context: Optional[Dict[str, Any]] = None,
    paper_metric: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Collects all parameter extractions for a Paper and returns a clean dictionary
    with sanitized Python variable names and parsed numeric/string values.
    Initializes configured workspace extraction definitions to 0.0 default.
    """
    if default_context is not None:
        context: Dict[str, Any] = dict(default_context)
    else:
        context = get_workspace_default_scoring_context(paper.workspace)

    if preloaded_extractions is not None:
        extractions = preloaded_extractions
    else:
        extractions = list(paper.extractions.all().select_related('extraction_definition'))

    for ext in extractions:
        # Ignore extractions that failed schema validation so variables retain their safe 0.0 default
        if ext.validation_status == 'fail':
            continue

        raw_val = ext.exit_metric or ""
        parsed_val = _parse_numeric_value(raw_val)

        # 1. Map by ExtractionDefinition name (e.g. 'TRL Level' -> 'trl_level')
        if ext.extraction_definition and ext.extraction_definition.name:
            key_name = _sanitize_identifier(ext.extraction_definition.name)
            context[key_name] = parsed_val

        # 2. Map by exit_metrics keys if configured (e.g. 'rigour_score, param1, param2')
        if ext.extraction_definition and ext.extraction_definition.exit_metrics:
            exit_metrics = ext.extraction_definition.get_exit_metrics_list()
            primary_m = ext.extraction_definition.get_primary_exit_metric()
            for exit_m in exit_metrics:
                val_for_m = None
                if ext.fields_data and isinstance(ext.fields_data, dict):
                    f_dict = ext.fields_data.get("fields", ext.fields_data)
                    if isinstance(f_dict, dict):
                        for k, v in f_dict.items():
                            if _sanitize_identifier(k) == exit_m:
                                val_for_m = _parse_numeric_value(v)
                                break
                if val_for_m is None and exit_m == primary_m:
                    val_for_m = parsed_val
                if val_for_m is not None:
                    context[exit_m] = val_for_m

        # 3. Map by category if available
        if ext.category:
            key_cat = _sanitize_identifier(ext.category)
            if key_cat not in context:
                context[key_cat] = parsed_val

        # 4. Map postprocessed and raw field data values if available
        if ext.fields_data and isinstance(ext.fields_data, dict):
            fields_dict = ext.fields_data.get("fields", ext.fields_data)
            if isinstance(fields_dict, dict):
                for f_k, f_v in fields_dict.items():
                    sanitized_f_k = _sanitize_identifier(f_k)
                    # Always set postprocessed / computed parameters or any field with non-zero or new value
                    if (
                        sanitized_f_k.endswith(("_postprocessed", "_computed"))
                        or sanitized_f_k not in context
                        or context[sanitized_f_k] == 0.0
                    ):
                        context[sanitized_f_k] = _parse_numeric_value(f_v)

            # Explicitly map definition-scoped postprocessed keys if present
            if ext.extraction_definition and ext.extraction_definition.name:
                d_slug = _sanitize_identifier(ext.extraction_definition.name)
                for suffix in ("_postprocessed", "_computed"):
                    post_k = f"{d_slug}{suffix}"
                    if post_k in fields_dict:
                        context[post_k] = _parse_numeric_value(fields_dict[post_k])

    # 4. Fallback: check exit metrics stored during Abstract or Full-Text Screening in PaperMetric
    if pipeline_run:
        pm = paper_metric
        if pm is None:
            from research_intelligence.models import PaperMetric
            pm = PaperMetric.objects.filter(paper=paper, pipeline_run=pipeline_run).first()
        if pm and pm.metrics_data and isinstance(pm.metrics_data, dict):
            for stage_k in ['abstract_screening', 'full_text_screening']:
                stage_dict = pm.metrics_data.get(stage_k, {})
                if isinstance(stage_dict, dict):
                    em_k = stage_dict.get("exit_metric_key")
                    em_v = stage_dict.get("exit_metric_value")
                    if em_k:
                        sanitized_em_k = _sanitize_identifier(em_k)
                        if sanitized_em_k not in context:
                            context[sanitized_em_k] = _parse_numeric_value(em_v)

    return context


def compute_paper_signal_score(
    paper_id_or_obj: Any,
    custom_code: Optional[str] = None,
    pipeline_run: Optional[Any] = None,
    preloaded_extractions: Optional[list] = None,
    default_context: Optional[Dict[str, Any]] = None,
    paper_metric: Optional[Any] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Computes the composite signal score for a Paper using the Workspace's sandboxed Python code.
    Saves the calculated signal_score and audit details onto the Paper and PaperMetric models per pipeline_run.
    """
    if isinstance(paper_id_or_obj, Paper):
        paper = paper_id_or_obj
    else:
        paper = Paper.objects.select_related('workspace').get(pk=paper_id_or_obj)

    workspace = paper.workspace
    if pipeline_run is None:
        pipeline_run = getattr(paper, 'pipeline_run', None)

    code_to_run = custom_code if custom_code is not None else (workspace.signal_score_code or "")

    context_vars = extract_paper_parameters(
        paper,
        pipeline_run=pipeline_run,
        preloaded_extractions=preloaded_extractions,
        default_context=default_context,
        paper_metric=paper_metric
    )

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

    # Persist on PaperMetric per pipeline run (Single Source of Truth)
    metric = paper_metric
    if metric is None:
        with transaction.atomic():
            metric, created = PaperMetric.objects.get_or_create(
                paper=paper,
                pipeline_run=pipeline_run,
                workspace=workspace,
                defaults={"signal_score": score, "signal_score_details": details, "metrics_data": context_vars}
            )
    merged_metrics = dict(metric.metrics_data or {})
    merged_metrics.update(context_vars)
    if metric.signal_score != score or metric.signal_score_details != details or metric.metrics_data != merged_metrics:
        metric.signal_score = score
        metric.signal_score_details = details
        metric.metrics_data = merged_metrics
        metric.save(update_fields=['signal_score', 'signal_score_details', 'metrics_data'])

    return score, details


calculate_paper_signal_score = compute_paper_signal_score


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2, default_retry_delay=10)
def execute_signal_score_job(self, component_run_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Celery Task: Evaluates the composite signal score for all screened/accepted papers
    in the active PipelineRun using the Workspace's sandboxed Python logic.
    """
    comp_run = None
    for attempt in range(4):
        try:
            close_old_connections()
            comp_run = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(pk=component_run_id)
            break
        except ComponentRun.DoesNotExist:
            if attempt < 3:
                time.sleep(0.5)
            else:
                logger.error(f"ComponentRun {component_run_id} does not exist after 4 attempts.")
                return {"success": False, "error": "ComponentRun not found"}

    # A re-delivered message for a step that already finished (worker shutdown between the
    # final save and the ack) must not run it again.
    if comp_run.status in ('completed', 'skipped', 'aborted'):
        logger.info(f"ComponentRun '{component_run_id}' is already {comp_run.status}; ignoring re-delivered task.")
        return {"success": True, "skipped": f"already {comp_run.status}"}

    pipeline_run = comp_run.pipeline_run
    workspace = pipeline_run.workspace

    logger.info(f"🚀 [SIGNAL SCORE START] Signal Score Evaluation for Run {pipeline_run.id} in Workspace '{workspace.name}'")

    comp_run.status = 'running'
    comp_run.started_at = timezone.now()
    comp_run.completed_at = None
    comp_run.error_message = ''

    # Snapshot signal score formula and scoring variables into comp_run.input_params for auditability
    try:
        current_input_params = comp_run.input_params or {}
        current_input_params.update(workspace.get_signal_score_prompt_snapshot())
        comp_run.input_params = current_input_params
    except Exception as snap_err:
        logger.warning(f"Could not snapshot signal score formula into comp_run.input_params: {snap_err}")

    comp_run.save(update_fields=['status', 'started_at', 'completed_at', 'error_message', 'input_params'])

    # Query all papers that passed screening
    accepted_statuses = ['accepted', 'full_text_passed', 'abstract_passed']
    papers_qs = pipeline_run.get_papers(screening_status=accepted_statuses).order_by('-created_at')

    if limit and limit > 0:
        papers = list(papers_qs[:limit])
    else:
        papers = list(papers_qs)

    total_papers = len(papers)
    scored_count = 0
    scores_list = []
    errors_list = []

    # Pre-fetch default scoring context once for workspace
    default_context = get_workspace_default_scoring_context(workspace)

    # Pre-fetch extractions for all papers in one single batch query
    from collections import defaultdict
    extractions_by_paper = defaultdict(list)
    for ext in Extraction.objects.filter(paper__in=papers).select_related('extraction_definition'):
        extractions_by_paper[ext.paper_id].append(ext)

    # Pre-fetch paper metrics for all papers in one single batch query
    pm_by_paper = {
        pm.paper_id: pm
        for pm in PaperMetric.objects.filter(pipeline_run=pipeline_run, paper__in=papers)
    }

    evaluated_papers = []
    for paper in papers:
        close_old_connections()
        try:
            paper_exts = extractions_by_paper.get(paper.id, [])
            paper_pm = pm_by_paper.get(paper.id)
            try:
                res = compute_paper_signal_score(
                    paper,
                    pipeline_run=pipeline_run,
                    preloaded_extractions=paper_exts,
                    default_context=default_context,
                    paper_metric=paper_pm,
                )
            except TypeError:
                res = compute_paper_signal_score(paper, pipeline_run=pipeline_run)

            if isinstance(res, tuple):
                score, details = res
            else:
                score = float(res)
                details = {"variables": {}, "score": score, "calculated_at": timezone.now().isoformat(), "error": None}

            details_dict = details if isinstance(details, dict) else {}
            metric = pm_by_paper.get(paper.id)
            if metric is None:
                with transaction.atomic():
                    metric, _ = PaperMetric.objects.get_or_create(
                        paper=paper,
                        pipeline_run=pipeline_run,
                        workspace=workspace,
                        defaults={"signal_score": score, "signal_score_details": details_dict, "metrics_data": {}}
                    )
                    pm_by_paper[paper.id] = metric

            if metric.signal_score != score or metric.signal_score_details != details_dict:
                metric.signal_score = score
                metric.signal_score_details = details_dict
                metric.save(update_fields=['signal_score', 'signal_score_details'])

            scores_list.append(score)
            scored_count += 1
            evaluated_papers.append({
                "paper_id": str(paper.id),
                "hash_id": paper.hash_id,
                "title": paper.title,
                "authors": paper.authors,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "screening_status": metric.screening_status if metric else "pending",
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
        f"🏁 [SIGNAL SCORE FINISHED] Signal Score Evaluation Run {pipeline_run.id}: "
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
