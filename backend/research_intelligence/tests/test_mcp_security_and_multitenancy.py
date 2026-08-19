import json
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import Workspace, WorkspaceMember, APIKey
from research_intelligence.mcp.server import check_scope
from research_intelligence.mcp.tools.workspaces import (
    get_workspace_logic,
    add_workspace_member_logic,
    list_workspaces_logic
)
from research_intelligence.mcp.tools.scrapers import (
    list_papers_logic,
    create_scraper_logic
)
from research_intelligence.mcp.tools.agent_processes import start_research_agent_logic

User = get_user_model()


class MCPSecurityAndMultiTenancyTestCase(TestCase):
    """
    Validates tenant isolation, role-based access control (RBAC), and FastMCP API Key scope enforcement:
    1. Tenant isolation: Users cannot access, inspect, or launch pipelines on workspaces they do not own/belong to.
    2. RBAC permissions: Researcher role cannot perform administrative actions (e.g. member invitation).
    3. Scope enforcement: Restrictive API key scopes strictly block unauthorized tool actions.
    """

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", email="alice@company.com", password="password123")
        self.bob = User.objects.create_user(username="bob", email="bob@competitor.com", password="password123")
        self.charlie = User.objects.create_user(username="charlie", email="charlie@company.com", password="password123")

        # Alice creates Workspace A
        self.workspace_a = Workspace.objects.create(name="Alice Secret Quantum Lab")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.alice, role="admin")

        # Bob creates Workspace B
        self.workspace_b = Workspace.objects.create(name="Bob Research Group")
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.bob, role="admin")

        # Charlie is a researcher member in Workspace A
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.charlie, role="researcher")

    def test_multi_tenancy_cross_workspace_isolation(self):
        """
        Ensures Bob cannot view or execute actions on Alice's workspace.
        """
        ws_a_id = str(self.workspace_a.id)

        # 1. Bob tries to get Workspace A details
        get_res_str = get_workspace_logic(self.bob, ws_a_id)
        self.assertIn("Error", get_res_str)
        self.assertIn("not a member", get_res_str)

        # 2. Bob tries to list papers from Workspace A
        papers_res_str = list_papers_logic(self.bob, ws_a_id)
        self.assertIn("Error", papers_res_str)
        self.assertIn("not a member", papers_res_str)

        # 3. Bob tries to configure a scraper on Workspace A
        scraper_res_str = create_scraper_logic(self.bob, ws_a_id, provider="arxiv", search_query="quantum")
        self.assertIn("Error", scraper_res_str)
        self.assertIn("not a member", scraper_res_str)

        # 4. Bob tries to launch a research agent on Workspace A
        agent_res_str = start_research_agent_logic(self.bob, ws_a_id)
        self.assertIn("Error", agent_res_str)
        self.assertIn("not a member", agent_res_str)

        # 5. Alice successfully lists her workspace
        alice_ws_list = json.loads(list_workspaces_logic(self.alice))
        self.assertEqual(len(alice_ws_list), 1)
        self.assertEqual(alice_ws_list[0]["workspace_id"], ws_a_id)

    def test_workspace_rbac_role_enforcement(self):
        """
        Ensures researcher role cannot perform admin operations like adding workspace members.
        """
        ws_a_id = str(self.workspace_a.id)

        # Charlie (researcher) tries to add a new member -> Denied
        denied_res_str = add_workspace_member_logic(
            self.charlie,
            ws_a_id,
            member_username_or_email="dave@company.com",
            role="researcher"
        )
        self.assertIn("Error: Insufficient workspace permissions", denied_res_str)

        # Alice (admin) adds a new member -> Permitted
        dave = User.objects.create_user(username="dave", email="dave@company.com", password="password123")
        allowed_res_str = add_workspace_member_logic(
            self.alice,
            ws_a_id,
            member_username_or_email="dave@company.com",
            role="researcher"
        )
        allowed_res = json.loads(allowed_res_str)
        self.assertTrue(allowed_res["success"])
        self.assertTrue(WorkspaceMember.objects.filter(workspace=self.workspace_a, user=dave).exists())

    def test_mcp_api_key_scope_enforcement(self):
        """
        Validates check_scope against fine-grained scopes (read-only vs write).
        """
        read_only_key = APIKey(
            name="Read Only Key",
            user=self.alice,
            scopes=["workspaces:read", "scrapers:read"]
        )

        full_access_key = APIKey(
            name="Wildcard Key",
            user=self.alice,
            scopes=["*"]
        )

        # 1. Allowed scope on read-only key
        check_scope(read_only_key, "workspaces:read")
        check_scope(read_only_key, "scrapers:read")

        # 2. Denied scope on read-only key raises PermissionError
        with self.assertRaises(PermissionError) as ctx:
            check_scope(read_only_key, "workspaces:write")
        self.assertIn("Insufficient permissions", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            check_scope(read_only_key, "runs:write")
        self.assertIn("Insufficient permissions", str(ctx.exception))

        # 3. Wildcard key allows any requested scope
        check_scope(full_access_key, "workspaces:read")
        check_scope(full_access_key, "workspaces:write")
        check_scope(full_access_key, "prompts:write")
        check_scope(full_access_key, "runs:write")
