import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password

from mcp_server.tools.users import (
    list_users_logic,
    get_user_logic,
    create_user_logic,
    update_user_logic,
    delete_user_logic,
)
from research_intelligence.models import UserActivityLog

User = get_user_model()


class MCPUserManagementTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True
            }
        )
        self.admin_user.set_password("adminpassword123")
        self.admin_user.is_staff = True
        self.admin_user.is_superuser = True
        self.admin_user.is_active = True
        self.admin_user.save()

        self.staff_user = User.objects.create_user(
            username="staff_member",
            email="staff@example.com",
            password="staffpassword123",
            is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username="regular_researcher",
            email="researcher@example.com",
            password="researcherpass123",
            is_staff=False,
            is_superuser=False
        )

    def parse_res(self, res_str: str) -> dict:
        return json.loads(res_str)

    def test_permission_denied_for_regular_user_managing_others(self):
        """Regular non-staff/non-superuser users cannot list, create, delete, or modify other users."""
        res_list = self.parse_res(list_users_logic(self.regular_user))
        self.assertEqual(res_list["status"], "error")
        self.assertIn("Permission denied", res_list["error"])

        res_get_other = self.parse_res(get_user_logic(self.regular_user, "admin"))
        self.assertEqual(res_get_other["status"], "error")
        self.assertIn("Permission denied", res_get_other["error"])

        res_create = self.parse_res(create_user_logic(self.regular_user, "newbie", "pass123"))
        self.assertEqual(res_create["status"], "error")
        self.assertIn("Permission denied", res_create["error"])

        res_update_other = self.parse_res(update_user_logic(self.regular_user, "admin", first_name="Hacked"))
        self.assertEqual(res_update_other["status"], "error")
        self.assertIn("Permission denied", res_update_other["error"])

        res_delete = self.parse_res(delete_user_logic(self.regular_user, "staff_member"))
        self.assertEqual(res_delete["status"], "error")
        self.assertIn("Permission denied", res_delete["error"])

    def test_regular_user_can_only_update_self_password_and_name(self):
        """
        Regular non-staff user can view themselves and update password, first_name, last_name.
        Attempting to update email or role flags (is_staff, is_superuser, is_active) must be rejected.
        """
        # 1. Can view own profile
        res_get_self = self.parse_res(get_user_logic(self.regular_user, "regular_researcher"))
        self.assertEqual(res_get_self["status"], "success")
        self.assertEqual(res_get_self["user"]["username"], "regular_researcher")

        # 2. Can update own first_name, last_name, and password
        res_update_self = self.parse_res(update_user_logic(
            user=self.regular_user,
            user_id_or_username="regular_researcher",
            first_name="Jan",
            last_name="Kowalski",
            password="MyNewSecurePassword123!"
        ))
        self.assertEqual(res_update_self["status"], "success")
        self.assertEqual(res_update_self["user"]["first_name"], "Jan")
        self.assertEqual(res_update_self["user"]["last_name"], "Kowalski")

        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.first_name, "Jan")
        self.assertEqual(self.regular_user.last_name, "Kowalski")
        self.assertTrue(self.regular_user.check_password("MyNewSecurePassword123!"))

        # 3. Cannot update own email
        res_email = self.parse_res(update_user_logic(
            user=self.regular_user,
            user_id_or_username="regular_researcher",
            email="hacker@corp.com"
        ))
        self.assertEqual(res_email["status"], "error")
        self.assertIn("Non-staff users can only update their own password, first_name, and last_name", res_email["error"])

        # 4. Cannot elevate own privileges
        res_staff = self.parse_res(update_user_logic(
            user=self.regular_user,
            user_id_or_username="regular_researcher",
            is_staff=True
        ))
        self.assertEqual(res_staff["status"], "error")
        self.assertIn("Non-staff users can only update their own password, first_name, and last_name", res_staff["error"])

        res_super = self.parse_res(update_user_logic(
            user=self.regular_user,
            user_id_or_username="regular_researcher",
            is_superuser=True
        ))
        self.assertEqual(res_super["status"], "error")
        self.assertIn("Non-staff users can only update their own password, first_name, and last_name", res_super["error"])

    def test_staff_and_superuser_can_list_and_get_users(self):
        """Both staff and superusers can list and view user accounts."""
        res_list = self.parse_res(list_users_logic(self.staff_user))
        self.assertEqual(res_list["status"], "success")
        self.assertGreaterEqual(res_list["count"], 3)

        res_search = self.parse_res(list_users_logic(self.admin_user, search="regular"))
        self.assertEqual(res_search["status"], "success")
        self.assertEqual(res_search["count"], 1)
        self.assertEqual(res_search["users"][0]["username"], "regular_researcher")

        res_get = self.parse_res(get_user_logic(self.staff_user, "admin"))
        self.assertEqual(res_get["status"], "success")
        self.assertEqual(res_get["user"]["username"], "admin")
        self.assertTrue(res_get["user"]["is_superuser"])

    def test_create_user_success(self):
        """Staff member can create a regular or staff user."""
        res = self.parse_res(create_user_logic(
            user=self.staff_user,
            username="analyst1",
            password="SecurePassword456!",
            email="analyst1@corp.com",
            first_name="Jane",
            last_name="Doe",
            is_staff=True,
            is_active=True
        ))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["user"]["username"], "analyst1")
        self.assertEqual(res["user"]["email"], "analyst1@corp.com")
        self.assertTrue(res["user"]["is_staff"])
        self.assertFalse(res["user"]["is_superuser"])

        created = User.objects.get(username="analyst1")
        self.assertTrue(created.check_password("SecurePassword456!"))

        # Verify audit log was created
        audit = UserActivityLog.objects.filter(action_name="create_user", user=self.staff_user).first()
        self.assertIsNotNone(audit)

    def test_staff_cannot_create_superuser(self):
        """Privilege escalation check: Staff members cannot create superusers."""
        res = self.parse_res(create_user_logic(
            user=self.staff_user,
            username="fake_admin",
            password="fake_password_123",
            is_superuser=True
        ))
        self.assertEqual(res["status"], "error")
        self.assertIn("Only existing superusers can create superuser accounts", res["error"])

    def test_superuser_can_create_superuser(self):
        """Superusers are permitted to create superuser accounts."""
        res = self.parse_res(create_user_logic(
            user=self.admin_user,
            username="co_admin",
            password="co_admin_password_123",
            is_superuser=True
        ))
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["user"]["is_superuser"])
        self.assertTrue(res["user"]["is_staff"])

    def test_update_user_attributes_and_password(self):
        """Can update user attributes and reset user password."""
        res = self.parse_res(update_user_logic(
            user=self.admin_user,
            user_id_or_username="regular_researcher",
            email="updated_researcher@example.com",
            first_name="UpdatedName",
            password="NewPassword789!",
            is_staff=True
        ))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["user"]["email"], "updated_researcher@example.com")
        self.assertEqual(res["user"]["first_name"], "UpdatedName")
        self.assertTrue(res["user"]["is_staff"])

        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.email, "updated_researcher@example.com")
        self.assertEqual(self.regular_user.first_name, "UpdatedName")
        self.assertTrue(self.regular_user.check_password("NewPassword789!"))

    def test_cannot_delete_admin_user(self):
        """CRITICAL REQUIREMENT: User 'admin' CANNOT be deleted via MCP."""
        res = self.parse_res(delete_user_logic(
            user=self.staff_user,
            user_id_or_username="admin"
        ))
        self.assertEqual(res["status"], "error")
        self.assertIn("Protected user 'admin' cannot be deleted via MCP", res["error"])
        self.assertTrue(User.objects.filter(username="admin").exists())

        # Also test deletion attempt by another superuser
        other_super = User.objects.create_superuser("super2", "s2@example.com", "pass")
        res_super = self.parse_res(delete_user_logic(
            user=other_super,
            user_id_or_username="admin"
        ))
        self.assertEqual(res_super["status"], "error")
        self.assertIn("Protected user 'admin' cannot be deleted via MCP", res_super["error"])
        self.assertTrue(User.objects.filter(username="admin").exists())

    def test_cannot_deactivate_or_demote_admin_user(self):
        """Protected user 'admin' cannot be deactivated or have superuser stripped."""
        res_deact = self.parse_res(update_user_logic(
            user=self.admin_user,
            user_id_or_username="admin",
            is_active=False
        ))
        self.assertEqual(res_deact["status"], "error")
        self.assertIn("Protected user 'admin' cannot be deactivated", res_deact["error"])

        res_demote = self.parse_res(update_user_logic(
            user=self.admin_user,
            user_id_or_username="admin",
            is_superuser=False
        ))
        self.assertEqual(res_demote["status"], "error")
        self.assertIn("Protected user 'admin' administrative privileges cannot be revoked", res_demote["error"])

    def test_cannot_delete_self(self):
        """User cannot delete their own active account via MCP."""
        res = self.parse_res(delete_user_logic(
            user=self.staff_user,
            user_id_or_username=str(self.staff_user.id)
        ))
        self.assertEqual(res["status"], "error")
        self.assertIn("Cannot delete your own active user account", res["error"])

    def test_staff_cannot_delete_or_edit_superuser(self):
        """Staff members cannot delete or modify superuser accounts."""
        co_super = User.objects.create_superuser("co_super", "cs@example.com", "pass")

        # Edit attempt
        res_edit = self.parse_res(update_user_logic(
            user=self.staff_user,
            user_id_or_username="co_super",
            email="hacked@example.com"
        ))
        self.assertEqual(res_edit["status"], "error")
        self.assertIn("Staff members cannot modify superuser accounts", res_edit["error"])

        # Delete attempt
        res_del = self.parse_res(delete_user_logic(
            user=self.staff_user,
            user_id_or_username="co_super"
        ))
        self.assertEqual(res_del["status"], "error")
        self.assertIn("Staff members cannot delete a superuser", res_del["error"])

    def test_delete_regular_user_success(self):
        """Regular user can be successfully deleted by staff/superuser."""
        user_to_delete = User.objects.create_user("temp_user", "temp@example.com", "pass123")

        res = self.parse_res(delete_user_logic(
            user=self.staff_user,
            user_id_or_username="temp_user"
        ))
        self.assertEqual(res["status"], "success")
        self.assertIn("successfully deleted", res["message"])
        self.assertFalse(User.objects.filter(username="temp_user").exists())

        # Verify audit log
        audit = UserActivityLog.objects.filter(action_name="delete_user", user=self.staff_user).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.input_params["target_username"], "temp_user")

    def test_mcp_registered_tools_integration(self):
        """Validates invoking the registered @mcp.tool() functions directly with auth context."""
        from unittest.mock import patch
        from mcp_server.server.app import list_users, get_user, create_user, update_user, delete_user

        with patch("mcp_server.server.app.get_auth_context", return_value=(self.admin_user, None, None)):
            res_create = self.parse_res(create_user(username="mcp_created_user", password="PassWord123!"))
            self.assertEqual(res_create["status"], "success")

            res_list = self.parse_res(list_users(search="mcp_created"))
            self.assertEqual(res_list["status"], "success")
            self.assertEqual(res_list["count"], 1)

            res_get = self.parse_res(get_user(user_id_or_username="mcp_created_user"))
            self.assertEqual(res_get["status"], "success")
            self.assertEqual(res_get["user"]["username"], "mcp_created_user")

            res_update = self.parse_res(update_user(user_id_or_username="mcp_created_user", first_name="MCPFirst"))
            self.assertEqual(res_update["status"], "success")
            self.assertEqual(res_update["user"]["first_name"], "MCPFirst")

            # Try deleting protected user 'admin' via tool -> must be blocked
            res_del_admin = self.parse_res(delete_user(user_id_or_username="admin"))
            self.assertEqual(res_del_admin["status"], "error")
            self.assertIn("Protected user 'admin' cannot be deleted via MCP", res_del_admin["error"])

            # Delete the test user
            res_del = self.parse_res(delete_user(user_id_or_username="mcp_created_user"))
            self.assertEqual(res_del["status"], "success")

