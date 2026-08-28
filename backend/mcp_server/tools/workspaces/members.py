import json
from django.db.models import Q
from django.contrib.auth import get_user_model
from research_intelligence.models import WorkspaceMember
from research_intelligence.services import check_workspace_access

User = get_user_model()


def add_workspace_member_logic(
    user,
    workspace_id: str,
    member_username_or_email: str = None,
    target_username: str = None,
    role: str = "researcher"
) -> str:
    """Add or update a user's membership and role in a workspace. Requires admin role."""
    workspace, _, error = check_workspace_access(user, workspace_id, required_roles=['admin'])
    if error:
        return error

    identifier = member_username_or_email or target_username
    if not identifier:
        return "Error: member_username_or_email is required."

    if role not in ['admin', 'manager', 'researcher']:
        return "Error: Invalid role. Must be 'admin', 'manager', or 'researcher'."

    target_user = User.objects.filter(Q(username=identifier) | Q(email=identifier)).first()
    if not target_user:
        return f"Error: User '{identifier}' not found."

    membership, created = WorkspaceMember.objects.update_or_create(
        workspace=workspace,
        user=target_user,
        defaults={'role': role}
    )
    action = "added to" if created else "updated in"
    return json.dumps({
        "status": "success",
        "success": True,
        "message": f"User '{identifier}' {action} workspace '{workspace.name}' with role '{role}'."
    }, indent=2)

