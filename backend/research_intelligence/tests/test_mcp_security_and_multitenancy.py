import json
from django.test import TransactionTestCase
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


class MCPSecurityAndMultiTenancyTestCase(TransactionTestCase):
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

    def test_mcp_auth_context_user_resolution_and_activity_logging(self):
        """
        Validates that when a request arrives with an API Key:
        1. get_auth_context() resolves the specific user associated with that key (NOT admin).
        2. Tool execution enforces workspace permissions for that specific user.
        3. UserActivityLog records the action under that specific user and key_id.
        """
        from unittest.mock import patch, MagicMock
        from research_intelligence.models import UserActivityLog
        from research_intelligence.mcp.server import get_auth_context, list_workspaces, get_workspace

        key_alice = APIKey(name="Alice Key", user=self.alice, scopes=["*"])
        key_alice.generate_key()
        key_alice.save()

        key_bob = APIKey(name="Bob Key", user=self.bob, scopes=["*"])
        key_bob.generate_key()
        key_bob.save()

        # 1. Simulate HTTP request authenticated as Bob
        mock_req_bob = MagicMock()
        mock_req_bob.scope = {
            "type": "http",
            "state": {
                "user": self.bob,
                "workspace": self.workspace_b,
                "api_key": key_bob
            }
        }
        mock_req_bob.state = MagicMock()
        mock_req_bob.state.user = self.bob
        mock_req_bob.state.workspace = self.workspace_b
        mock_req_bob.state.api_key = key_bob
        mock_req_bob.headers = {}
        mock_req_bob.client = MagicMock(host="192.168.1.100")

        with patch("research_intelligence.mcp.server.get_http_request", return_value=mock_req_bob):
            user, ws, key = get_auth_context()
            self.assertEqual(user, self.bob)
            self.assertEqual(key, key_bob)

            # Bob lists workspaces -> Only Bob's workspace returned
            ws_list_str = list_workspaces()
            ws_list = json.loads(ws_list_str)
            self.assertEqual(len(ws_list), 1)
            self.assertEqual(ws_list[0]["workspace_id"], str(self.workspace_b.id))

            # Bob tries to get Alice's workspace -> Denied
            denied_str = get_workspace(workspace_id=str(self.workspace_a.id))
            self.assertIn("Error: Access denied", denied_str)

            # Check UserActivityLog entries recorded for Bob
            bob_logs = UserActivityLog.objects.filter(user=self.bob).order_by("-timestamp")
            self.assertGreaterEqual(bob_logs.count(), 2)

            get_ws_log = bob_logs.filter(action_name="get_workspace").first()
            self.assertIsNotNone(get_ws_log)
            self.assertEqual(get_ws_log.user_username, "bob")
            self.assertEqual(get_ws_log.status, "failed")
            self.assertEqual(get_ws_log.api_key_id, key_bob.key_id)

    def test_asgi_auth_middleware_valid_and_invalid_keys(self):
        """
        Tests QueryParamAuthMiddleware ASGI request processing:
        - Valid key_id/secret sets user in scope dictionary.
        - Invalid secret returns HTTP 401 Unauthorized.
        - Cached session_id recovers user credentials.
        """
        import asyncio
        from unittest.mock import MagicMock
        from research_intelligence.mcp.server import QueryParamAuthMiddleware, SESSION_AUTH_CACHE

        key_alice = APIKey(name="Alice ASGI Key", user=self.alice, scopes=["*"])
        raw_secret = key_alice.generate_key()
        key_alice.save()

        app_mock = MagicMock()
        async def dummy_app(scope, receive, send):
            return "app_called"
        app_mock.side_effect = dummy_app

        middleware = QueryParamAuthMiddleware(app_mock)

        # 1. Valid API Key via query parameters
        scope_valid = {
            "type": "http",
            "path": "/sse",
            "headers": [],
            "query_string": f"api_key_id={key_alice.key_id}&api_secret={raw_secret}&session_id=sess_123".encode()
        }
        sent_messages = []
        async def mock_send(msg):
            sent_messages.append(msg)

        asyncio.run(middleware(scope_valid, None, mock_send))
        self.assertIn("state", scope_valid)
        self.assertEqual(scope_valid["state"]["user"], self.alice)
        self.assertEqual(scope_valid["state"]["api_key"].key_id, key_alice.key_id)
        self.assertIn("sess_123", SESSION_AUTH_CACHE)

        # 2. Subsequent request with cached session_id
        scope_session = {
            "type": "http",
            "path": "/messages",
            "headers": [],
            "query_string": b"session_id=sess_123"
        }
        asyncio.run(middleware(scope_session, None, mock_send))
        self.assertEqual(scope_session["state"]["user"], self.alice)

        # 3. Invalid API secret -> 401 Unauthorized
        sent_messages.clear()
        scope_invalid = {
            "type": "http",
            "path": "/sse",
            "headers": [],
            "query_string": f"api_key_id={key_alice.key_id}&api_secret=WRONG_SECRET".encode()
        }
        asyncio.run(middleware(scope_invalid, None, mock_send))
        self.assertEqual(sent_messages[0]["type"], "http.response.start")
        self.assertEqual(sent_messages[0]["status"], 401)

        # 4. Completely unauthenticated request (no credentials) -> 401 Unauthorized (NEVER fallback to admin)
        sent_messages.clear()
        scope_unauthenticated = {
            "type": "http",
            "path": "/sse",
            "headers": [],
            "query_string": b""
        }
        asyncio.run(middleware(scope_unauthenticated, None, mock_send))
        self.assertEqual(sent_messages[0]["type"], "http.response.start")
        self.assertEqual(sent_messages[0]["status"], 401)
        self.assertNotIn("state", scope_unauthenticated)

