import uuid
import logging
from typing import Optional, Tuple, List, Dict, Any, Union
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember

logger = logging.getLogger(__name__)
User = get_user_model()


def check_workspace_access(
    user,
    workspace_id: Union[str, uuid.UUID],
    required_roles: Optional[List[str]] = None
) -> Tuple[Optional[Workspace], Optional[WorkspaceMember], Optional[str]]:
    """
    Verifies that a user has authorized access to a workspace with the required role.

    Returns:
        (workspace, membership, None) on success.
        (None, None, error_message) on failure.
    """
    if isinstance(workspace_id, uuid.UUID):
        ws_uuid = workspace_id
    else:
        try:
            ws_uuid = uuid.UUID(str(workspace_id))
        except (ValueError, TypeError):
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


def get_user_accessible_workspaces(user):
    """
    Returns a QuerySet of all workspaces accessible to the user,
    along with a dictionary mapping workspace_id -> member_role.
    """
    if getattr(user, 'is_superuser', False):
        memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
        workspaces = Workspace.objects.all().order_by('-created_at')
    else:
        memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
        workspaces = Workspace.objects.filter(id__in=memberships.keys()).order_by('-created_at')
    return workspaces, memberships


def create_workspace_record(
    user,
    name: str,
    abstract_acceptance_criteria: Union[List[str], str] = None,
    abstract_rejection_criteria: Union[List[str], str] = None,
    full_text_acceptance_criteria: Union[List[str], str] = None,
    full_text_rejection_criteria: Union[List[str], str] = None,
    abstract_screening_system_prompt: Optional[str] = None,
    abstract_screening_user_prompt_template: Optional[str] = None,
    abstract_screening_response_schema: Optional[dict] = None,
    abstract_screening_exit_metric: Optional[str] = None,
    full_text_screening_system_prompt: Optional[str] = None,
    full_text_screening_user_prompt_template: Optional[str] = None,
    full_text_screening_response_schema: Optional[dict] = None,
    full_text_screening_exit_metric: Optional[str] = None,
    ocr_provider: Optional[str] = None,
    llm_provider: str = "google",
    screening_llm_model: str = "google/gemini-3.7-flash",
    signal_score_code: Optional[str] = None,
    monthly_token_limit: int = 10000000,
    monthly_usd_limit: float = 100.0,
    skip_abstract_screening: bool = False,
    notification_email: Optional[str] = None
) -> Tuple[Optional[Workspace], Optional[str]]:
    """
    Creates a new Workspace domain record, formats screening criteria, and establishes admin membership.
    """
    def _format_criteria(crit):
        if crit is None:
            return ""
        if isinstance(crit, list):
            return "\n".join(f"- {c.strip()}" for c in crit if c and c.strip())
        return crit.strip()

    valid_ocr = ["pypdf", "mistral", "gemini", "none", None]
    if ocr_provider is not None and str(ocr_provider).lower() == "none":
        ocr_provider = None
    elif ocr_provider and ocr_provider not in valid_ocr:
        return None, f"Error: Invalid ocr_provider '{ocr_provider}'. Choose from {valid_ocr}."

    valid_llm = ["google", "openrouter"]
    if llm_provider not in valid_llm:
        return None, f"Error: Invalid llm_provider '{llm_provider}'. Choose from {valid_llm}."

    workspace = Workspace.objects.create(
        name=name,
        abstract_acceptance_criteria=_format_criteria(abstract_acceptance_criteria),
        abstract_rejection_criteria=_format_criteria(abstract_rejection_criteria),
        full_text_acceptance_criteria=_format_criteria(full_text_acceptance_criteria),
        full_text_rejection_criteria=_format_criteria(full_text_rejection_criteria),
        abstract_screening_system_prompt=abstract_screening_system_prompt,
        abstract_screening_user_prompt_template=abstract_screening_user_prompt_template,
        abstract_screening_response_schema=abstract_screening_response_schema,
        abstract_screening_exit_metric=abstract_screening_exit_metric,
        full_text_screening_system_prompt=full_text_screening_system_prompt,
        full_text_screening_user_prompt_template=full_text_screening_user_prompt_template,
        full_text_screening_response_schema=full_text_screening_response_schema,
        full_text_screening_exit_metric=full_text_screening_exit_metric,
        ocr_provider=ocr_provider,
        llm_provider=llm_provider,
        screening_llm_model=screening_llm_model,
        signal_score_code=signal_score_code,
        monthly_token_limit=monthly_token_limit if monthly_token_limit is not None else 10000000,
        monthly_usd_limit=monthly_usd_limit if monthly_usd_limit is not None else 100.0,
        skip_abstract_screening=bool(skip_abstract_screening),
        notification_email=notification_email
    )

    WorkspaceMember.objects.create(
        workspace=workspace,
        user=user,
        role="admin"
    )

    return workspace, None
