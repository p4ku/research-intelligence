import json
import uuid
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, WorkspaceMember

User = get_user_model()


from research_intelligence.services import check_workspace_access


def list_workspaces_logic(user) -> str:
    """List all workspaces accessible by the authenticated user along with their role."""
    if getattr(user, 'is_superuser', False):
        memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
        workspaces = Workspace.objects.all().order_by('-created_at')
    else:
        memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
        workspaces = Workspace.objects.filter(id__in=memberships.keys()).order_by('-created_at')

    if not workspaces.exists():
        return json.dumps({"message": "No workspaces found for this user."}, indent=2)

    results = []
    for ws in workspaces:
        role = memberships.get(ws.id, "admin" if getattr(user, 'is_superuser', False) else "unknown")
        results.append({
            "workspace_id": str(ws.id),
            "name": ws.name,
            "role": role,
            "ocr_provider": ws.ocr_provider,
            "llm_provider": ws.llm_provider,
            "screening_llm_model": ws.screening_llm_model,
            "reasoning_effort": getattr(ws, 'reasoning_effort', 'medium'),
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
        "role": getattr(membership, 'role', 'admin' if getattr(user, 'is_superuser', False) else 'unknown'),
        "ocr_provider": workspace.ocr_provider,
        "llm_provider": workspace.llm_provider,
        "screening_llm_model": workspace.screening_llm_model,
        "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
        "signal_score_code": workspace.signal_score_code,
        "quota_tokens_monthly": getattr(workspace, 'quota_tokens_monthly', getattr(workspace, 'monthly_token_limit', None)),
        "quota_usd_monthly": float(workspace.quota_usd_monthly) if getattr(workspace, 'quota_usd_monthly', None) else None,
        "tokens_consumed_this_month": getattr(workspace, 'tokens_consumed_this_month', 0),
        "usd_spent_this_month": float(getattr(workspace, 'usd_spent_this_month', 0.0)),
        "abstract_acceptance_criteria": workspace.get_abstract_acceptance_criteria(),
        "abstract_rejection_criteria": workspace.get_abstract_rejection_criteria(),
        "full_text_acceptance_criteria": workspace.get_full_text_acceptance_criteria(),
        "full_text_rejection_criteria": workspace.get_full_text_rejection_criteria(),
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
                "is_active": s.is_active
            }
            for s in scrapers
        ],
        "extraction_definitions": [
            {
                "definition_id": str(d.id),
                "name": d.name,
                "system_prompt": d.system_prompt,
                "response_schema": d.response_schema,
                "llm_model": d.llm_model,
                "is_active": d.is_active
            }
            for d in extraction_defs
        ]
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
    ocr_provider: str = None,
    screening_llm_model: str = 'google/gemini-3.7-flash',
    llm_provider: str = 'google',
    reasoning_effort: str = 'medium',
    digest_schedule: str = '0 9 * * 5',
    monthly_token_limit: int = 10000000,
    monthly_usd_limit: float = 100.00,
    cost_limit_usd: float = None,
    signal_score_code: str = None
) -> str:
    """Create a new workspace and automatically assign the creator as the 'admin' member."""
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
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        reasoning_effort=reasoning_effort or 'medium',
        digest_schedule=digest_schedule,
        monthly_token_limit=monthly_token_limit if monthly_token_limit is not None else 10000000,
        monthly_usd_limit=usd_limit if usd_limit is not None else 100.00,
        signal_score_code=signal_score_code
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
    ocr_provider: str = None,
    screening_llm_model: str = None,
    llm_provider: str = None,
    reasoning_effort: str = None,
    digest_schedule: str = None,
    monthly_token_limit: int = None,
    cost_limit_usd: float = None,
    monthly_usd_limit: float = None,
    signal_score_code: str = None
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
    if digest_schedule is not None:
        workspace.digest_schedule = digest_schedule
        fields_to_update.append('digest_schedule')
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
