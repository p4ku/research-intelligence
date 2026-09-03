import json
import logging
from typing import Optional
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


def check_staff_or_superuser(user) -> tuple[bool, Optional[str]]:
    """
    Verify that the authenticated MCP user is an active Django staff member or superuser.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False, "Authentication required. Please provide valid API credentials."
    if not (getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)):
        return False, "Permission denied. Only staff members or superusers can manage users via MCP."
    if not getattr(user, 'is_active', False):
        return False, "Permission denied. Inactive user accounts cannot perform management actions."
    return True, None


def serialize_user(user_obj) -> dict:
    """Format user model instance into standard JSON-serializable dictionary."""
    return {
        "id": user_obj.id,
        "username": user_obj.username,
        "email": user_obj.email,
        "first_name": user_obj.first_name,
        "last_name": user_obj.last_name,
        "is_staff": user_obj.is_staff,
        "is_superuser": user_obj.is_superuser,
        "is_active": user_obj.is_active,
        "date_joined": user_obj.date_joined.isoformat() if user_obj.date_joined else None,
        "last_login": user_obj.last_login.isoformat() if user_obj.last_login else None,
    }


def _record_audit_log(user, action_name: str, status: str, input_params: dict, output_summary: dict, error_message: str = None):
    """Best-effort audit recording into UserActivityLog."""
    try:
        from research_intelligence.models import UserActivityLog
        UserActivityLog.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            user_username=getattr(user, 'username', 'Anonymous'),
            user_email=getattr(user, 'email', ''),
            interface='mcp',
            action_name=action_name,
            status=status,
            input_params=input_params,
            output_summary=output_summary,
            error_message=error_message or "",
        )
    except Exception as e:
        logger.warning(f"Could not record UserActivityLog for action {action_name}: {e}")


def list_users_logic(
    user,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_staff: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    limit: int = 50
) -> str:
    """
    List user accounts in the Django system with filtering.
    Requires staff or superuser privileges.
    """
    allowed, err = check_staff_or_superuser(user)
    if not allowed:
        return json.dumps({"status": "error", "error": err}, indent=2)

    qs = User.objects.all().order_by('id')

    if search:
        s = search.strip()
        qs = qs.filter(
            Q(username__icontains=s) |
            Q(email__icontains=s) |
            Q(first_name__icontains=s) |
            Q(last_name__icontains=s)
        )

    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    if is_staff is not None:
        qs = qs.filter(is_staff=is_staff)

    if is_superuser is not None:
        qs = qs.filter(is_superuser=is_superuser)

    users = list(qs[:limit])
    serialized = [serialize_user(u) for u in users]

    return json.dumps({
        "status": "success",
        "count": len(serialized),
        "total_matching": qs.count(),
        "users": serialized
    }, indent=2, cls=DjangoJSONEncoder)


def get_user_logic(user, user_id_or_username: str) -> str:
    """
    Retrieve details of a specific user by numeric ID or username.
    Superusers and staff members can view any user profile.
    Regular (non-staff) users can ONLY view their own profile.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return json.dumps({"status": "error", "error": "Authentication required. Please provide valid API credentials."}, indent=2)
    if not getattr(user, 'is_active', False):
        return json.dumps({"status": "error", "error": "Permission denied. Inactive user accounts cannot perform actions."}, indent=2)

    val = str(user_id_or_username).strip()
    target_user = None
    if val.isdigit():
        target_user = User.objects.filter(id=int(val)).first()
    if not target_user:
        target_user = User.objects.filter(username__iexact=val).first()

    if not target_user:
        return json.dumps({"status": "error", "error": f"User '{user_id_or_username}' not found."}, indent=2)

    is_caller_staff = getattr(user, 'is_staff', False)
    is_caller_superuser = getattr(user, 'is_superuser', False)
    is_privileged = is_caller_staff or is_caller_superuser

    # Regular user check: can only view themselves
    if not is_privileged:
        if target_user.id != getattr(user, 'id', None) and target_user.username.lower() != getattr(user, 'username', '').lower():
            return json.dumps({
                "status": "error",
                "error": "Permission denied. Regular users can only view their own profile. Only staff members or superusers can view other users."
            }, indent=2)

    data = serialize_user(target_user)

    # Attach workspace memberships
    try:
        from research_intelligence.models import WorkspaceMember
        memberships = WorkspaceMember.objects.filter(user=target_user).select_related('workspace')
        data["workspace_memberships"] = [
            {
                "workspace_id": str(m.workspace.id),
                "workspace_name": m.workspace.name,
                "role": m.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None
            }
            for m in memberships
        ]
    except Exception:
        data["workspace_memberships"] = []

    return json.dumps({
        "status": "success",
        "user": data
    }, indent=2, cls=DjangoJSONEncoder)


def create_user_logic(
    user,
    username: str,
    password: str,
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    is_active: bool = True
) -> str:
    """
    Create a new Django user with encrypted password and specified role flags.
    Requires staff or superuser privileges. Regular users cannot manage or create users.
    Non-superusers cannot create superusers.
    """
    allowed, err = check_staff_or_superuser(user)
    if not allowed:
        return json.dumps({"status": "error", "error": err}, indent=2)

    username_clean = (username or "").strip()
    if not username_clean:
        return json.dumps({"status": "error", "error": "Username cannot be empty."}, indent=2)

    if not password or len(password) < 4:
        return json.dumps({"status": "error", "error": "Password must be at least 4 characters long."}, indent=2)

    if User.objects.filter(username__iexact=username_clean).exists():
        return json.dumps({"status": "error", "error": f"User with username '{username_clean}' already exists."}, indent=2)

    email_clean = (email or "").strip()
    if email_clean:
        try:
            validate_email(email_clean)
        except ValidationError:
            return json.dumps({"status": "error", "error": f"Invalid email format: '{email_clean}'."}, indent=2)

    # Privilege escalation guard: Only superusers can create superuser accounts
    if is_superuser and not getattr(user, 'is_superuser', False):
        return json.dumps({
            "status": "error",
            "error": "Permission denied. Only existing superusers can create superuser accounts."
        }, indent=2)

    try:
        new_user = User.objects.create_user(
            username=username_clean,
            email=email_clean,
            password=password,
            first_name=(first_name or "").strip(),
            last_name=(last_name or "").strip(),
        )
        new_user.is_staff = bool(is_staff or is_superuser)
        new_user.is_superuser = bool(is_superuser)
        new_user.is_active = bool(is_active)
        new_user.save()

        user_data = serialize_user(new_user)
        _record_audit_log(
            user=user,
            action_name='create_user',
            status='success',
            input_params={"username": username_clean, "email": email_clean, "is_staff": is_staff, "is_superuser": is_superuser},
            output_summary=user_data
        )

        return json.dumps({
            "status": "success",
            "message": f"User '{new_user.username}' (ID: {new_user.id}) created successfully.",
            "user": user_data
        }, indent=2, cls=DjangoJSONEncoder)

    except Exception as e:
        logger.exception(f"Error creating user '{username_clean}': {e}")
        return json.dumps({"status": "error", "error": f"Failed to create user: {str(e)}"}, indent=2)


def update_user_logic(
    user,
    user_id_or_username: str,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    password: Optional[str] = None,
    is_staff: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    is_active: Optional[bool] = None
) -> str:
    """
    Update attributes, role flags, and password for a specified user.
    PERMISSIONS:
    - Superusers and staff members can manage users.
    - Regular users (non-staff, non-superuser) CANNOT manage other users.
      They can AT MOST update their OWN password, first_name, and last_name.
    - Protected user 'admin' cannot be deactivated or have administrative access revoked.
    - Staff members cannot modify superusers or grant superuser privileges.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return json.dumps({"status": "error", "error": "Authentication required. Please provide valid API credentials."}, indent=2)
    if not getattr(user, 'is_active', False):
        return json.dumps({"status": "error", "error": "Permission denied. Inactive user accounts cannot perform actions."}, indent=2)

    val = str(user_id_or_username).strip()
    target_user = None
    if val.isdigit():
        target_user = User.objects.filter(id=int(val)).first()
    if not target_user:
        target_user = User.objects.filter(username__iexact=val).first()

    if not target_user:
        return json.dumps({"status": "error", "error": f"User '{user_id_or_username}' not found."}, indent=2)

    is_calling_staff = getattr(user, 'is_staff', False)
    is_calling_superuser = getattr(user, 'is_superuser', False)
    is_privileged = is_calling_staff or is_calling_superuser

    # 1. Non-staff / non-superuser strict constraint:
    if not is_privileged:
        is_self = (target_user.id == getattr(user, 'id', None)) or (target_user.username.lower() == getattr(user, 'username', '').lower())
        if not is_self:
            return json.dumps({
                "status": "error",
                "error": "Permission denied. Non-staff users cannot manage other users. You can only update your own account."
            }, indent=2)

        # Non-staff users can ONLY update their own password, first_name, and last_name
        disallowed_fields = []
        if email is not None:
            disallowed_fields.append("email")
        if is_staff is not None:
            disallowed_fields.append("is_staff")
        if is_superuser is not None:
            disallowed_fields.append("is_superuser")
        if is_active is not None:
            disallowed_fields.append("is_active")

        if disallowed_fields:
            return json.dumps({
                "status": "error",
                "error": f"Permission denied. Non-staff users can only update their own password, first_name, and last_name (attempted to modify: {', '.join(disallowed_fields)})."
            }, indent=2)

    # 2. Staff privilege boundary: Staff members cannot edit superuser accounts
    if is_privileged and target_user.is_superuser and not is_calling_superuser:
        return json.dumps({
            "status": "error",
            "error": "Permission denied. Staff members cannot modify superuser accounts."
        }, indent=2)

    # 3. Staff privilege boundary: Staff members cannot grant superuser privileges
    if is_privileged and is_superuser is True and not is_calling_superuser:
        return json.dumps({
            "status": "error",
            "error": "Permission denied. Only superusers can grant superuser privileges."
        }, indent=2)

    # 4. Protected user 'admin' guardrails:
    if target_user.username.lower() == "admin":
        if is_active is False:
            return json.dumps({
                "status": "error",
                "error": "Protected user 'admin' cannot be deactivated."
            }, indent=2)
        if is_staff is False or is_superuser is False:
            return json.dumps({
                "status": "error",
                "error": "Protected user 'admin' administrative privileges cannot be revoked."
            }, indent=2)

    updated_fields = []

    if email is not None:
        email_clean = email.strip()
        if email_clean:
            try:
                validate_email(email_clean)
            except ValidationError:
                return json.dumps({"status": "error", "error": f"Invalid email format: '{email_clean}'."}, indent=2)
        target_user.email = email_clean
        updated_fields.append('email')

    if first_name is not None:
        target_user.first_name = first_name.strip()
        updated_fields.append('first_name')

    if last_name is not None:
        target_user.last_name = last_name.strip()
        updated_fields.append('last_name')

    if is_active is not None:
        target_user.is_active = bool(is_active)
        updated_fields.append('is_active')

    if is_staff is not None:
        target_user.is_staff = bool(is_staff)
        updated_fields.append('is_staff')

    if is_superuser is not None:
        target_user.is_superuser = bool(is_superuser)
        if target_user.is_superuser:
            target_user.is_staff = True
            if 'is_staff' not in updated_fields:
                updated_fields.append('is_staff')
        updated_fields.append('is_superuser')

    if password is not None:
        if len(password) < 4:
            return json.dumps({"status": "error", "error": "Password must be at least 4 characters long."}, indent=2)
        target_user.set_password(password)
        updated_fields.append('password')

    if updated_fields:
        target_user.save()

    user_data = serialize_user(target_user)
    _record_audit_log(
        user=user,
        action_name='update_user',
        status='success',
        input_params={"user_id_or_username": user_id_or_username, "updated_fields": [f for f in updated_fields if f != 'password']},
        output_summary=user_data
    )

    return json.dumps({
        "status": "success",
        "message": f"User '{target_user.username}' updated successfully ({', '.join(updated_fields)}).",
        "updated_fields": updated_fields,
        "user": user_data
    }, indent=2, cls=DjangoJSONEncoder)


def delete_user_logic(user, user_id_or_username: str) -> str:
    """
    Delete a user account from Django.
    SAFETY CONSTRAINTS:
    - User 'admin' CANNOT be deleted via MCP.
    - Calling user cannot delete their own active account via MCP.
    - Non-superusers (staff) cannot delete superusers.
    """
    allowed, err = check_staff_or_superuser(user)
    if not allowed:
        return json.dumps({"status": "error", "error": err}, indent=2)

    val = str(user_id_or_username).strip()
    target_user = None
    if val.isdigit():
        target_user = User.objects.filter(id=int(val)).first()
    if not target_user:
        target_user = User.objects.filter(username__iexact=val).first()

    if not target_user:
        return json.dumps({"status": "error", "error": f"User '{user_id_or_username}' not found."}, indent=2)

    # 1. Critical User Requirement: "nie mozna usunąc usera admin przez MCP"
    if target_user.username.lower() == "admin":
        return json.dumps({
            "status": "error",
            "error": "Protected user 'admin' cannot be deleted via MCP."
        }, indent=2)

    # 2. Self-deletion safety rule
    if target_user.id == getattr(user, 'id', None):
        return json.dumps({
            "status": "error",
            "error": "Cannot delete your own active user account via MCP."
        }, indent=2)

    # 3. Privilege boundary: Staff members cannot delete a superuser
    if target_user.is_superuser and not getattr(user, 'is_superuser', False):
        return json.dumps({
            "status": "error",
            "error": "Permission denied. Staff members cannot delete a superuser."
        }, indent=2)

    target_id = target_user.id
    target_username = target_user.username
    target_email = target_user.email

    try:
        target_user.delete()

        _record_audit_log(
            user=user,
            action_name='delete_user',
            status='success',
            input_params={"user_id_or_username": user_id_or_username, "target_id": target_id, "target_username": target_username},
            output_summary={"deleted_user_id": target_id, "deleted_username": target_username}
        )

        return json.dumps({
            "status": "success",
            "message": f"User '{target_username}' (ID: {target_id}, Email: '{target_email}') successfully deleted.",
            "deleted_user_id": target_id,
            "deleted_username": target_username
        }, indent=2, cls=DjangoJSONEncoder)

    except Exception as e:
        logger.exception(f"Error deleting user '{target_username}': {e}")
        return json.dumps({"status": "error", "error": f"Failed to delete user: {str(e)}"}, indent=2)
