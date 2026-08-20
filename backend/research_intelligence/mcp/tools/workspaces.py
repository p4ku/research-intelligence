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
            "screening_llm_model": ws.screening_llm_model,
            "llm_provider": ws.llm_provider,
            "digest_schedule": ws.digest_schedule,
            "monthly_token_limit": ws.monthly_token_limit,
            "tokens_in_consumed_this_month": ws.tokens_in_consumed_this_month,
            "tokens_out_consumed_this_month": ws.tokens_out_consumed_this_month,
            "tokens_consumed_this_month": ws.tokens_consumed_this_month,
            "monthly_usd_limit": float(ws.monthly_usd_limit),
            "usd_spent_this_month": float(ws.usd_spent_this_month),
            "signal_score_code": ws.signal_score_code,
            "created_at": ws.created_at.isoformat()
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_workspace_logic(user, workspace_id: str) -> str:
    """Retrieve full configuration details, component configurations, scrapers, prompts, and member roster for a workspace."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
    if error:
        return error

    members = WorkspaceMember.objects.filter(workspace=workspace).select_related('user')
    member_roster = [
        {
            "user_id": m.user.id,
            "username": m.user.username,
            "email": m.user.email,
            "role": m.role,
            "joined_at": m.created_at.isoformat()
        }
        for m in members
    ]

    scrapers = workspace.scrapers.all()
    scrapers_list = [
        {
            "scraper_id": str(s.id),
            "provider": s.provider,
            "search_query": s.search_query,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat()
        }
        for s in scrapers
    ]

    extractions = workspace.extraction_definitions.all()
    extractions_list = [
        {
            "definition_id": str(ed.id),
            "name": ed.name,
            "llm_model": ed.llm_model,
            "version": ed.version,
            "response_schema": ed.response_schema
        }
        for ed in extractions
    ]

    details = {
        "workspace_id": str(workspace.id),
        "name": workspace.name,
        "abstract_acceptance_criteria": workspace.abstract_acceptance_criteria,
        "abstract_rejection_criteria": workspace.abstract_rejection_criteria,
        "full_text_acceptance_criteria": workspace.full_text_acceptance_criteria,
        "full_text_rejection_criteria": workspace.full_text_rejection_criteria,
        "created_at": workspace.created_at.isoformat(),
        "components_config": {
            "search_scrapers": scrapers_list,
            "ocr_provider": workspace.ocr_provider,
            "screening_llm_model": workspace.screening_llm_model,
            "llm_provider": workspace.llm_provider,
            "extraction_definitions": extractions_list,
            "signal_score_code": workspace.signal_score_code,
            "digest_schedule": workspace.digest_schedule,
            "monthly_token_limit": workspace.monthly_token_limit,
            "tokens_in_consumed_this_month": workspace.tokens_in_consumed_this_month,
            "tokens_out_consumed_this_month": workspace.tokens_out_consumed_this_month,
            "tokens_consumed_this_month": workspace.tokens_consumed_this_month,
            "monthly_usd_limit": float(workspace.monthly_usd_limit),
            "usd_spent_this_month": float(workspace.usd_spent_this_month)
        },
        "members": member_roster
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def create_workspace_logic(
    user,
    name: str,
    abstract_acceptance_criteria: str = "",
    abstract_rejection_criteria: str = "",
    full_text_acceptance_criteria: str = "",
    full_text_rejection_criteria: str = "",
    ocr_provider: str = None,
    screening_llm_model: str = "google/gemini-3.7-flash",
    llm_provider: str = "google",
    digest_schedule: str = "0 9 * * 5",
    monthly_token_limit: int = 10000000,
    monthly_usd_limit: float = 100.0,
    cost_limit_usd: float = None,
    signal_score_code: str = None,
    **kwargs
) -> str:
    """Create a new workspace project and assign the creating user as Admin."""
    if not name or not name.strip():
        return "Error: Workspace name is required and cannot be empty."

    if isinstance(ocr_provider, str) and ocr_provider.strip().lower() in ('none', 'null', '', 'disabled'):
        ocr_provider = None

    try:
        workspace = Workspace.objects.create(
            name=name.strip(),
            abstract_acceptance_criteria=abstract_acceptance_criteria,
            abstract_rejection_criteria=abstract_rejection_criteria,
            full_text_acceptance_criteria=full_text_acceptance_criteria,
            full_text_rejection_criteria=full_text_rejection_criteria,
            ocr_provider=ocr_provider,
            screening_llm_model=screening_llm_model,
            llm_provider=llm_provider,
            signal_score_code=signal_score_code,
            digest_schedule=digest_schedule,
            monthly_token_limit=monthly_token_limit,
            monthly_usd_limit=cost_limit_usd if cost_limit_usd is not None else monthly_usd_limit
        )

        # Assign creator as Admin
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            role='admin'
        )

        return json.dumps({
            "success": True,
            "message": f"Successfully created workspace '{workspace.name}'.",
            "workspace_id": str(workspace.id),
            "role": "admin"
        }, indent=2)
    except Exception as e:
        return f"Error creating workspace: {e}"


def update_workspace_logic(
    user,
    workspace_id: str,
    name: str = None,
    abstract_acceptance_criteria: str = None,
    abstract_rejection_criteria: str = None,
    full_text_acceptance_criteria: str = None,
    full_text_rejection_criteria: str = None,
    ocr_provider: str = None,
    screening_llm_model: str = None,
    llm_provider: str = None,
    digest_schedule: str = None,
    monthly_token_limit: int = None,
    monthly_usd_limit: float = None,
    cost_limit_usd: float = None,
    signal_score_code: str = None,
    **kwargs
) -> str:
    """Update settings of an existing workspace (requires Admin or Manager role)."""
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return error

    if name is not None:
        if not name.strip():
            return "Error: Workspace name cannot be blank."
        workspace.name = name.strip()
    if abstract_acceptance_criteria is not None:
        workspace.abstract_acceptance_criteria = abstract_acceptance_criteria
    if abstract_rejection_criteria is not None:
        workspace.abstract_rejection_criteria = abstract_rejection_criteria
    if full_text_acceptance_criteria is not None:
        workspace.full_text_acceptance_criteria = full_text_acceptance_criteria
    if full_text_rejection_criteria is not None:
        workspace.full_text_rejection_criteria = full_text_rejection_criteria
    if ocr_provider is not None:
        if isinstance(ocr_provider, str) and ocr_provider.strip().lower() in ('none', 'null', '', 'disabled'):
            workspace.ocr_provider = None
        else:
            workspace.ocr_provider = ocr_provider
    if screening_llm_model is not None:
        workspace.screening_llm_model = screening_llm_model
    if llm_provider is not None:
        workspace.llm_provider = llm_provider
    if signal_score_code is not None:
        workspace.signal_score_code = signal_score_code
    if digest_schedule is not None:
        workspace.digest_schedule = digest_schedule
    if monthly_token_limit is not None:
        workspace.monthly_token_limit = monthly_token_limit
    if monthly_usd_limit is not None:
        workspace.monthly_usd_limit = monthly_usd_limit
    elif cost_limit_usd is not None:
        workspace.monthly_usd_limit = cost_limit_usd

    workspace.save()

    return json.dumps({
        "success": True,
        "message": f"Workspace '{workspace.name}' successfully updated.",
        "workspace_id": str(workspace.id)
    }, indent=2)


def add_workspace_member_logic(
    user,
    workspace_id: str,
    member_username_or_email: str,
    role: str = "researcher"
) -> str:
    """Add a user to a workspace or update their role (requires Admin role)."""
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin'])
    if error:
        return error

    valid_roles = [c[0] for c in WorkspaceMember.ROLE_CHOICES]
    if role not in valid_roles:
        return f"Error: Invalid role '{role}'. Allowed roles are: {valid_roles}"

    # Find target user by username or email
    target_user = User.objects.filter(username=member_username_or_email).first()
    if not target_user:
        target_user = User.objects.filter(email=member_username_or_email).first()

    if not target_user:
        return f"Error: User '{member_username_or_email}' not found."

    member, created = WorkspaceMember.objects.update_or_create(
        workspace=workspace,
        user=target_user,
        defaults={'role': role}
    )

    action_text = "added to" if created else "updated in"
    return json.dumps({
        "success": True,
        "message": f"User '{target_user.username}' successfully {action_text} workspace '{workspace.name}' with role '{role}'.",
        "workspace_id": str(workspace.id),
        "user_id": target_user.id,
        "role": member.role
    }, indent=2)
