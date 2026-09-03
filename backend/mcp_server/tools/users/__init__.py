"""
FastMCP User Management Tools.
Allows Django superusers and staff members to manage users, reset passwords, and update attributes.
Enforces strict protection preventing deletion or deactivation of the root 'admin' user.
"""
from .management import (
    check_staff_or_superuser,
    list_users_logic,
    get_user_logic,
    create_user_logic,
    update_user_logic,
    delete_user_logic,
)

__all__ = [
    "check_staff_or_superuser",
    "list_users_logic",
    "get_user_logic",
    "create_user_logic",
    "update_user_logic",
    "delete_user_logic",
]
