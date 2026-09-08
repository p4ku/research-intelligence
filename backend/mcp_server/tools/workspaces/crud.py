from __future__ import annotations
import json
import uuid
from typing import Optional, List, Dict, Any, Union
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, WorkspaceMember
from research_intelligence.features import is_feature_enabled, Feature

User = get_user_model()


from research_intelligence.services import check_workspace_access


def list_workspaces_logic(user) -> str:
    """List all workspaces accessible by the authenticated user along with their role."""
    memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
    workspaces = Workspace.objects.filter(id__in=memberships.keys()).order_by('-created_at')

    if not workspaces.exists():
        return json.dumps({"message": "No workspaces found for this user."}, indent=2)

    results = []
    for ws in workspaces:
        role = memberships.get(ws.id, "unknown")
        results.append({
            "workspace_id": str(ws.id),
            "name": ws.name,
            "role": role,
            "ocr_provider": ws.ocr_provider,
            "llm_provider": ws.llm_provider,
            "screening_llm_model": ws.screening_llm_model,
            "reasoning_effort": getattr(ws, 'reasoning_effort', 'medium'),
            "skip_abstract_screening": getattr(ws, 'skip_abstract_screening', False),
            "reprocess_existing": getattr(ws, 'reprocess_existing', False),
            "signal_score_code": ws.signal_score_code,
            "tokens_consumed_this_month": getattr(ws, 'tokens_consumed_this_month', 0),
            "usd_spent_this_month": float(getattr(ws, 'usd_spent_this_month', 0.0)),
            "created_at": ws.created_at.isoformat()
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_workspace_logic(user, workspace_id: str) -> str:
    """Get full details of a specific workspace, including criteria, scrapers, and extraction definitions."""
    workspace, membership, error = check_workspace_access(user, workspace_id)
    if error:
        return error

    scrapers = workspace.scrapers.all()
    extraction_defs = workspace.extraction_definitions.all()
    members = workspace.memberships.select_related('user').all()

    data = {
        "workspace_id": str(workspace.id),
        "name": workspace.name,
        "role": getattr(membership, 'role', 'unknown'),
        "ocr_provider": workspace.ocr_provider,
        "llm_provider": workspace.llm_provider,
        "screening_llm_model": workspace.screening_llm_model,
        "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
        "skip_abstract_screening": getattr(workspace, 'skip_abstract_screening', False),
        "reprocess_existing": getattr(workspace, 'reprocess_existing', False),
        "signal_score_code": workspace.signal_score_code,
        "monthly_token_limit": workspace.monthly_token_limit,
        "monthly_usd_limit": float(workspace.monthly_usd_limit) if workspace.monthly_usd_limit is not None else None,
        "tokens_consumed_this_month": getattr(workspace, 'tokens_consumed_this_month', 0),
        "usd_spent_this_month": float(getattr(workspace, 'usd_spent_this_month', 0.0)),
        "abstract_acceptance_criteria": workspace.get_abstract_acceptance_criteria(),
        "abstract_rejection_criteria": workspace.get_abstract_rejection_criteria(),
        "abstract_screening_system_prompt": workspace.abstract_screening_system_prompt,
        "abstract_screening_user_prompt_template": workspace.abstract_screening_user_prompt_template,
        "abstract_screening_response_schema": workspace.abstract_screening_response_schema,
        "abstract_screening_exit_metric": workspace.abstract_screening_exit_metric,
        "full_text_acceptance_criteria": workspace.get_full_text_acceptance_criteria(),
        "full_text_rejection_criteria": workspace.get_full_text_rejection_criteria(),
        "full_text_screening_system_prompt": workspace.full_text_screening_system_prompt,
        "full_text_screening_user_prompt_template": workspace.full_text_screening_user_prompt_template,
        "full_text_screening_response_schema": workspace.full_text_screening_response_schema,
        "full_text_screening_exit_metric": workspace.full_text_screening_exit_metric,
        "narrative_report_prompt": workspace.narrative_report_prompt,
        "narrative_report_system_prompt": workspace.narrative_report_system_prompt,
        "narrative_report_top_n_papers": workspace.narrative_report_top_n_papers,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": getattr(workspace, 'updated_at', workspace.created_at).isoformat(),
        "members": [
            {
                "user_id": m.user.id,
                "username": m.user.username,
                "role": m.role,
                "created_at": m.created_at.isoformat()
            }
            for m in members
        ],
        "scrapers": [
            {
                "scraper_id": str(s.id),
                "provider": s.provider,
                "provider_name": s.get_provider_display(),
                "search_query": s.search_query,
                "limit": s.limit,
                "n_last_days": s.n_last_days,
                "is_active": s.is_active
            }
            for s in scrapers
        ],
        "extraction_definitions": [
            {
                "definition_id": str(d.id),
                "name": d.name,
                "exit_metrics": d.get_exit_metrics_list(),
                "has_postprocessing_code": bool(d.postprocessing_code),
                "postprocessing_code": d.postprocessing_code or "",
                "system_prompt": d.system_prompt,
                "user_prompt_template": d.user_prompt_template,
                "response_schema": d.response_schema,
                "llm_model": d.llm_model,
                "version": d.version,
                "requires_consensus": d.requires_consensus,
                "is_active": d.is_active
            }
            for d in extraction_defs
        ],
        "subscribers": [
            {
                "subscriber_id": str(sub.id),
                "email": sub.email,
                "name": sub.name,
                "subscription_type": sub.subscription_type,
                "is_active": sub.is_active
            }
            for sub in workspace.subscribers.all()
        ] if is_feature_enabled(Feature.EMAIL_NOTIFICATIONS) else [],
        "schedules": [
            {
                "schedule_id": str(sched.id),
                "name": sched.name,
                "frequency": sched.frequency,
                "cron_expression": sched.cron_expression,
                "reprocess_existing": sched.reprocess_existing,
                "is_active": sched.is_active,
                "prevent_overlap": sched.prevent_overlap,
                "consecutive_failures_count": sched.consecutive_failures_count,
                "max_consecutive_failures": sched.max_consecutive_failures,
                "success_rate_percent": sched.success_rate_percent,
                "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
                "last_run_at": sched.last_run_at.isoformat() if sched.last_run_at else None,
                "last_status": sched.current_execution_status or sched.last_status,
            }
            for sched in workspace.schedules.all()
        ] if is_feature_enabled(Feature.SCHEDULING) else []
    }
    return json.dumps(data, indent=2, cls=DjangoJSONEncoder)


def create_workspace_logic(
    user,
    name: str,
    abstract_acceptance_criteria: list[str] | str = None,
    abstract_rejection_criteria: list[str] | str = None,
    full_text_acceptance_criteria: list[str] | str = None,
    full_text_rejection_criteria: list[str] | str = None,
    abstract_screening_system_prompt: str = None,
    abstract_screening_user_prompt_template: str = None,
    abstract_screening_response_schema: dict = None,
    abstract_screening_exit_metric: str = None,
    full_text_screening_system_prompt: str = None,
    full_text_screening_user_prompt_template: str = None,
    full_text_screening_response_schema: dict = None,
    full_text_screening_exit_metric: str = None,
    narrative_report_prompt: str = None,
    narrative_report_system_prompt: str = None,
    narrative_report_top_n_papers: int = 10,
    ocr_provider: str = None,
    screening_llm_model: str = 'google/gemini-3.8-flash',
    llm_provider: str = 'google',
    reasoning_effort: str = 'medium',
    monthly_token_limit: int = 10000000,
    monthly_usd_limit: float = 100.00,
    cost_limit_usd: float = None,
    signal_score_code: str = None,
    skip_abstract_screening: bool = False,
    reprocess_existing: bool = False
) -> str:
    """
    Create a new systematic review workspace and assign the creator as 'admin'.
    
    Parameters:
    - reprocess_existing: Default workspace policy (boolean, default False). If True, pipeline runs
      default to re-screening and re-evaluating existing workspace papers unless overridden per-run.
    """
    from research_intelligence.services import create_workspace_record

    usd_limit = cost_limit_usd if cost_limit_usd is not None else monthly_usd_limit

    ws, err = create_workspace_record(
        user=user,
        name=name,
        abstract_acceptance_criteria=abstract_acceptance_criteria,
        abstract_rejection_criteria=abstract_rejection_criteria,
        full_text_acceptance_criteria=full_text_acceptance_criteria,
        full_text_rejection_criteria=full_text_rejection_criteria,
        abstract_screening_system_prompt=abstract_screening_system_prompt,
        abstract_screening_user_prompt_template=abstract_screening_user_prompt_template,
        abstract_screening_response_schema=abstract_screening_response_schema,
        abstract_screening_exit_metric=abstract_screening_exit_metric,
        full_text_screening_system_prompt=full_text_screening_system_prompt,
        full_text_screening_user_prompt_template=full_text_screening_user_prompt_template,
        full_text_screening_response_schema=full_text_screening_response_schema,
        full_text_screening_exit_metric=full_text_screening_exit_metric,
        narrative_report_prompt=narrative_report_prompt,
        narrative_report_system_prompt=narrative_report_system_prompt,
        narrative_report_top_n_papers=narrative_report_top_n_papers,
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        reasoning_effort=reasoning_effort or 'medium',
        monthly_token_limit=monthly_token_limit if monthly_token_limit is not None else 10000000,
        monthly_usd_limit=usd_limit if usd_limit is not None else 100.00,
        signal_score_code=signal_score_code,
        skip_abstract_screening=bool(skip_abstract_screening),
        reprocess_existing=bool(reprocess_existing)
    )

    if err:
        return json.dumps({"status": "error", "error": err}, indent=2)

    return json.dumps({
        "status": "success",
        "message": f"Workspace '{ws.name}' created successfully.",
        "workspace_id": str(ws.id),
        "role": "admin"
    }, indent=2)


def update_workspace_logic(
    user,
    workspace_id: str,
    name: str = None,
    abstract_acceptance_criteria: list[str] | str = None,
    abstract_rejection_criteria: list[str] | str = None,
    full_text_acceptance_criteria: list[str] | str = None,
    full_text_rejection_criteria: list[str] | str = None,
    abstract_screening_system_prompt: str = None,
    abstract_screening_user_prompt_template: str = None,
    abstract_screening_response_schema: dict = None,
    abstract_screening_exit_metric: str = None,
    full_text_screening_system_prompt: str = None,
    full_text_screening_user_prompt_template: str = None,
    full_text_screening_response_schema: dict = None,
    full_text_screening_exit_metric: str = None,
    narrative_report_prompt: str = None,
    narrative_report_system_prompt: str = None,
    narrative_report_top_n_papers: int = None,
    ocr_provider: str = None,
    screening_llm_model: str = None,
    llm_provider: str = None,
    reasoning_effort: str = None,
    monthly_token_limit: int = None,
    cost_limit_usd: float = None,
    monthly_usd_limit: float = None,
    signal_score_code: str = None,
    skip_abstract_screening: bool = None,
    reprocess_existing: bool = None
) -> str:
    """Update criteria, OCR provider, screening prompts/schemas, or LLM configuration for a workspace. Requires admin or manager role."""
    workspace, _, error = check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    def _format_crit(c):
        if isinstance(c, list):
            return "\n".join(c)
        return c or ""

    fields_to_update = []
    if name is not None:
        workspace.name = name.strip()
        fields_to_update.append('name')
    if abstract_acceptance_criteria is not None:
        workspace.abstract_acceptance_criteria = _format_crit(abstract_acceptance_criteria)
        fields_to_update.append('abstract_acceptance_criteria')
    if abstract_rejection_criteria is not None:
        workspace.abstract_rejection_criteria = _format_crit(abstract_rejection_criteria)
        fields_to_update.append('abstract_rejection_criteria')
    if full_text_acceptance_criteria is not None:
        workspace.full_text_acceptance_criteria = _format_crit(full_text_acceptance_criteria)
        fields_to_update.append('full_text_acceptance_criteria')
    if full_text_rejection_criteria is not None:
        workspace.full_text_rejection_criteria = _format_crit(full_text_rejection_criteria)
        fields_to_update.append('full_text_rejection_criteria')
    if abstract_screening_system_prompt is not None:
        workspace.abstract_screening_system_prompt = abstract_screening_system_prompt
        fields_to_update.append('abstract_screening_system_prompt')
    if abstract_screening_user_prompt_template is not None:
        workspace.abstract_screening_user_prompt_template = abstract_screening_user_prompt_template
        fields_to_update.append('abstract_screening_user_prompt_template')
    if abstract_screening_response_schema is not None:
        workspace.abstract_screening_response_schema = abstract_screening_response_schema
        fields_to_update.append('abstract_screening_response_schema')
    if abstract_screening_exit_metric is not None:
        workspace.abstract_screening_exit_metric = abstract_screening_exit_metric
        fields_to_update.append('abstract_screening_exit_metric')
    if full_text_screening_system_prompt is not None:
        workspace.full_text_screening_system_prompt = full_text_screening_system_prompt
        fields_to_update.append('full_text_screening_system_prompt')
    if full_text_screening_user_prompt_template is not None:
        workspace.full_text_screening_user_prompt_template = full_text_screening_user_prompt_template
        fields_to_update.append('full_text_screening_user_prompt_template')
    if full_text_screening_response_schema is not None:
        workspace.full_text_screening_response_schema = full_text_screening_response_schema
        fields_to_update.append('full_text_screening_response_schema')
    if full_text_screening_exit_metric is not None:
        workspace.full_text_screening_exit_metric = full_text_screening_exit_metric
        fields_to_update.append('full_text_screening_exit_metric')
    if narrative_report_prompt is not None:
        workspace.narrative_report_prompt = narrative_report_prompt
        fields_to_update.append('narrative_report_prompt')
    if narrative_report_system_prompt is not None:
        workspace.narrative_report_system_prompt = narrative_report_system_prompt
        fields_to_update.append('narrative_report_system_prompt')
    if narrative_report_top_n_papers is not None:
        workspace.narrative_report_top_n_papers = int(narrative_report_top_n_papers)
        fields_to_update.append('narrative_report_top_n_papers')
    if skip_abstract_screening is not None:
        workspace.skip_abstract_screening = bool(skip_abstract_screening)
        fields_to_update.append('skip_abstract_screening')
    if reprocess_existing is not None:
        workspace.reprocess_existing = bool(reprocess_existing)
        fields_to_update.append('reprocess_existing')
    if ocr_provider is not None:
        if isinstance(ocr_provider, str) and (ocr_provider.strip().lower() in ('none', '')):
            workspace.ocr_provider = None
        else:
            valid_ocr = ["pypdf", "mistral", "gemini"]
            if ocr_provider not in valid_ocr:
                return json.dumps({"status": "error", "error": f"Error: Invalid ocr_provider '{ocr_provider}'. Choose from {valid_ocr + ['none']}."}, indent=2)
            workspace.ocr_provider = ocr_provider
        fields_to_update.append('ocr_provider')
    if screening_llm_model is not None:
        workspace.screening_llm_model = screening_llm_model
        fields_to_update.append('screening_llm_model')
    if llm_provider is not None:
        valid_llm = ["google", "openrouter"]
        if llm_provider not in valid_llm:
            return json.dumps({"status": "error", "error": f"Error: Invalid llm_provider '{llm_provider}'. Choose from {valid_llm}."}, indent=2)
        workspace.llm_provider = llm_provider
        fields_to_update.append('llm_provider')
    if reasoning_effort is not None:
        valid_efforts = ["off", "low", "medium", "high"]
        if reasoning_effort not in valid_efforts:
            return json.dumps({"status": "error", "error": f"Error: Invalid reasoning_effort '{reasoning_effort}'. Choose from {valid_efforts}."}, indent=2)
        workspace.reasoning_effort = reasoning_effort
        fields_to_update.append('reasoning_effort')
    if monthly_token_limit is not None:
        workspace.monthly_token_limit = monthly_token_limit
        fields_to_update.append('monthly_token_limit')
    
    usd_val = cost_limit_usd if cost_limit_usd is not None else monthly_usd_limit
    if usd_val is not None:
        workspace.monthly_usd_limit = usd_val
        fields_to_update.append('monthly_usd_limit')

    if signal_score_code is not None:
        workspace.signal_score_code = signal_score_code
        fields_to_update.append('signal_score_code')

    if fields_to_update:
        workspace.save(update_fields=fields_to_update)

    return json.dumps({
        "status": "success",
        "message": f"Workspace '{workspace.name}' updated successfully.",
        "updated_fields": fields_to_update,
        "workspace_id": str(workspace.id)
    }, indent=2)
