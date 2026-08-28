import json
import uuid
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, WorkspaceMember

User = get_user_model()


def _check_workspace_access(user, workspace_id: str, required_roles=None):
    """
    Helper function to verify that a user has access to a workspace.
    Returns (workspace, membership, None) on success or (None, None, error_message) on failure.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return None, None, f"Error: '{workspace_id}' is not a valid UUID."

    try:
        workspace = Workspace.objects.get(id=ws_uuid)
    except Workspace.DoesNotExist:
        return None, None, f"Error: Workspace with ID '{workspace_id}' does not exist."

    if getattr(user, 'is_superuser', False):
        return workspace, None, None

    try:
        membership = WorkspaceMember.objects.get(workspace=workspace, user=user)
    except WorkspaceMember.DoesNotExist:
        return None, None, f"Error: Access denied. User '{user}' is not a member of workspace '{workspace.name}'."

    if required_roles and membership.role not in required_roles:
        return None, None, (
            f"Error: Insufficient workspace permissions. Role '{membership.role}' required to be one of "
            f"{required_roles} for this operation."
        )

    return workspace, membership, None


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
            "signal_score_code": ws.signal_score_code,
            "tokens_consumed_this_month": getattr(ws, 'tokens_consumed_this_month', 0),
            "usd_spent_this_month": float(getattr(ws, 'usd_spent_this_month', 0.0)),
            "created_at": ws.created_at.isoformat()
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_workspace_logic(user, workspace_id: str) -> str:
    """Get full details of a specific workspace, including criteria, scrapers, and extraction definitions."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
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
                "name": s.name,
                "provider": s.provider,
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
    ocr_provider: str = None,
    llm_provider: str = 'google',
    screening_llm_model: str = 'google/gemini-3.7-flash',
    signal_score_code: str = None
) -> str:
    """Create a new workspace and automatically assign the creator as the 'admin' member."""
    if not name or not name.strip():
        return "Error: Workspace name cannot be empty."

    def _format_crit(c):
        if isinstance(c, list):
            return "\n".join(c)
        return c or ""

    ws = Workspace.objects.create(
        name=name.strip(),
        abstract_acceptance_criteria=_format_crit(abstract_acceptance_criteria),
        abstract_rejection_criteria=_format_crit(abstract_rejection_criteria),
        full_text_acceptance_criteria=_format_crit(full_text_acceptance_criteria),
        full_text_rejection_criteria=_format_crit(full_text_rejection_criteria),
        ocr_provider=ocr_provider if ocr_provider and ocr_provider.lower() != 'none' else None,
        llm_provider=llm_provider,
        screening_llm_model=screening_llm_model,
        signal_score_code=signal_score_code
    )
    if user and not getattr(user, 'is_anonymous', False) and getattr(user, 'pk', None):
        WorkspaceMember.objects.create(workspace=ws, user=user, role='admin')

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
    ocr_provider: str = None,
    llm_provider: str = None,
    screening_llm_model: str = None,
    signal_score_code: str = None
) -> str:
    """Update criteria, OCR provider, or LLM configuration for a workspace. Requires admin or manager role."""
    workspace, _, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return error

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
    if ocr_provider is not None:
        workspace.ocr_provider = ocr_provider if ocr_provider.lower() != 'none' else None
        fields_to_update.append('ocr_provider')
    if llm_provider is not None:
        workspace.llm_provider = llm_provider
        fields_to_update.append('llm_provider')
    if screening_llm_model is not None:
        workspace.screening_llm_model = screening_llm_model
        fields_to_update.append('screening_llm_model')
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
