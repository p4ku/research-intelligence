import json
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import Workspace, WorkspaceMember, APIKey
from mcp_server.server import check_scope
from mcp_server.tools.workspaces import (
    get_workspace_logic,
    add_workspace_member_logic,
    list_workspaces_logic
)
from mcp_server.tools.scrapers import (
    list_papers_logic,
    create_scraper_logic
)
from mcp_server.tools.agents import start_research_agent_logic

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
        from mcp_server.server import get_auth_context, list_workspaces, get_workspace

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

        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_bob):
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
        from mcp_server.server import QueryParamAuthMiddleware, SESSION_AUTH_CACHE

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

    def test_two_distinct_users_positive_and_negative_audit_logging_and_workspace_isolation(self):
        """
        Comprehensive test for:
        1. Two distinct users (Adam and Josh), each with their own API Key and Workspace.
        2. Positive tests: Adam and Josh successfully perform actions on their own workspaces.
        3. Negative tests: Adam cannot perform actions on Josh's workspace, and Josh cannot on Adam's.
        4. Negative tests: An unassigned third user (Mallory) is denied access to both workspaces.
        5. AuditLog verification: Every single action (success or failure) is logged with the EXACT
           user, username, email, api_key_id, status ('success' or 'failed'), and error message.
           Zero log cross-contamination between users.
        """
        from unittest.mock import patch, MagicMock
        from research_intelligence.models import UserActivityLog
        from mcp_server.server import (
            list_workspaces,
            get_workspace,
            create_scraper,
            list_papers,
            start_research_agent
        )

        # Clear prior logs to start clean
        UserActivityLog.objects.all().delete()

        # 1. Setup User Adam and Workspace Adam
        adam = User.objects.create_user(username="adam", email="adam@schwarz.de", password="password123")
        ws_adam = Workspace.objects.create(name="Adam Autonomous Agents Lab")
        WorkspaceMember.objects.create(workspace=ws_adam, user=adam, role="admin")
        key_adam = APIKey(name="Adam MCP Key", user=adam, scopes=["*"])
        key_adam.generate_key()
        key_adam.save()

        # 2. Setup User Josh and Workspace Josh
        josh = User.objects.create_user(username="josh", email="josh@adder.dev", password="password123")
        ws_josh = Workspace.objects.create(name="Josh Materials Science")
        WorkspaceMember.objects.create(workspace=ws_josh, user=josh, role="admin")
        key_josh = APIKey(name="Josh MCP Key", user=josh, scopes=["*"])
        key_josh.generate_key()
        key_josh.save()

        # 3. Setup User Mallory (Attacker / No workspace memberships)
        mallory = User.objects.create_user(username="mallory", email="mallory@attacker.com", password="password123")
        key_mallory = APIKey(name="Mallory MCP Key", user=mallory, scopes=["*"])
        key_mallory.generate_key()
        key_mallory.save()

        def make_mock_req(user, workspace, api_key, ip="127.0.0.1"):
            req = MagicMock()
            req.scope = {
                "type": "http",
                "state": {
                    "user": user,
                    "workspace": workspace,
                    "api_key": api_key
                }
            }
            req.state = MagicMock()
            req.state.user = user
            req.state.workspace = workspace
            req.state.api_key = api_key
            req.headers = {"user-agent": f"TestClient/{user.username}"}
            req.client = MagicMock(host=ip)
            return req

        # ==========================================
        # PART A: POSITIVE TESTS - ADAM ON WS_ADAM
        # ==========================================
        mock_req_adam = make_mock_req(adam, ws_adam, key_adam, ip="10.0.0.1")
        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_adam):
            # A1. Adam lists workspaces -> Only Adam's workspace
            adam_ws_list = json.loads(list_workspaces())
            self.assertEqual(len(adam_ws_list), 1)
            self.assertEqual(adam_ws_list[0]["workspace_id"], str(ws_adam.id))
            self.assertEqual(adam_ws_list[0]["name"], "Adam Autonomous Agents Lab")

            # A2. Adam gets details of his own workspace -> Success
            adam_get_ws = json.loads(get_workspace(workspace_id=str(ws_adam.id)))
            self.assertEqual(adam_get_ws["workspace_id"], str(ws_adam.id))
            self.assertEqual(adam_get_ws["name"], "Adam Autonomous Agents Lab")

            # A3. Adam creates a scraper on his own workspace -> Success
            adam_scraper_res = json.loads(create_scraper(
                workspace_id=str(ws_adam.id),
                provider="arxiv",
                search_query="autonomous agents"
            ))
            self.assertTrue(adam_scraper_res["success"])

        # Check Adam's positive logs
        adam_success_logs = UserActivityLog.objects.filter(user=adam, status="success")
        self.assertEqual(adam_success_logs.count(), 3)
        for log in adam_success_logs:
            self.assertEqual(log.user_username, "adam")
            self.assertEqual(log.user_email, "adam@schwarz.de")
            self.assertEqual(log.api_key_id, key_adam.key_id)
            self.assertEqual(log.status, "success")
            self.assertEqual(log.ip_address, "10.0.0.1")

        # ==========================================
        # PART B: POSITIVE TESTS - JOSH ON WS_JOSH
        # ==========================================
        mock_req_josh = make_mock_req(josh, ws_josh, key_josh, ip="10.0.0.2")
        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_josh):
            # B1. Josh lists workspaces -> Only Josh's workspace
            josh_ws_list = json.loads(list_workspaces())
            self.assertEqual(len(josh_ws_list), 1)
            self.assertEqual(josh_ws_list[0]["workspace_id"], str(ws_josh.id))
            self.assertEqual(josh_ws_list[0]["name"], "Josh Materials Science")

            # B2. Josh gets details of his own workspace -> Success
            josh_get_ws = json.loads(get_workspace(workspace_id=str(ws_josh.id)))
            self.assertEqual(josh_get_ws["workspace_id"], str(ws_josh.id))
            self.assertEqual(josh_get_ws["name"], "Josh Materials Science")

            # B3. Josh creates a scraper on his own workspace -> Success
            josh_scraper_res = json.loads(create_scraper(
                workspace_id=str(ws_josh.id),
                provider="openalex",
                search_query="superconductors"
            ))
            self.assertTrue(josh_scraper_res["success"])

        # Check Josh's positive logs
        josh_success_logs = UserActivityLog.objects.filter(user=josh, status="success")
        self.assertEqual(josh_success_logs.count(), 3)
        for log in josh_success_logs:
            self.assertEqual(log.user_username, "josh")
            self.assertEqual(log.user_email, "josh@adder.dev")
            self.assertEqual(log.api_key_id, key_josh.key_id)
            self.assertEqual(log.status, "success")
            self.assertEqual(log.ip_address, "10.0.0.2")

        # ==========================================
        # PART C: NEGATIVE TESTS - ADAM TRIES JOSH'S WORKSPACE
        # ==========================================
        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_adam):
            # C1. Adam tries to get Josh's workspace -> Denied
            res_c1 = get_workspace(workspace_id=str(ws_josh.id))
            self.assertIn("Error: Access denied", res_c1)
            self.assertIn("not a member", res_c1)

            # C2. Adam tries to list papers in Josh's workspace -> Denied
            res_c2 = list_papers(workspace_id=str(ws_josh.id))
            self.assertIn("Error: Access denied", res_c2)

            # C3. Adam tries to create scraper in Josh's workspace -> Denied
            res_c3 = create_scraper(workspace_id=str(ws_josh.id), provider="arxiv", search_query="hack")
            self.assertIn("Error: Access denied", res_c3)

            # C4. Adam tries to start research agent in Josh's workspace -> Denied
            res_c4 = start_research_agent(workspace_id=str(ws_josh.id))
            self.assertIn("Error: Access denied", res_c4)

        # Check Adam's failed logs
        adam_failed_logs = UserActivityLog.objects.filter(user=adam, status="failed")
        self.assertEqual(adam_failed_logs.count(), 4)
        for log in adam_failed_logs:
            self.assertEqual(log.user_username, "adam")
            self.assertEqual(log.api_key_id, key_adam.key_id)
            self.assertEqual(log.status, "failed")
            self.assertIn("Access denied", log.error_message)

        # ==========================================
        # PART D: NEGATIVE TESTS - JOSH TRIES ADAM'S WORKSPACE
        # ==========================================
        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_josh):
            # D1. Josh tries to get Adam's workspace -> Denied
            res_d1 = get_workspace(workspace_id=str(ws_adam.id))
            self.assertIn("Error: Access denied", res_d1)
            self.assertIn("not a member", res_d1)

            # D2. Josh tries to list papers in Adam's workspace -> Denied
            res_d2 = list_papers(workspace_id=str(ws_adam.id))
            self.assertIn("Error: Access denied", res_d2)

            # D3. Josh tries to create scraper in Adam's workspace -> Denied
            res_d3 = create_scraper(workspace_id=str(ws_adam.id), provider="openalex", search_query="hack")
            self.assertIn("Error: Access denied", res_d3)

            # D4. Josh tries to start research agent in Adam's workspace -> Denied
            res_d4 = start_research_agent(workspace_id=str(ws_adam.id))
            self.assertIn("Error: Access denied", res_d4)

        # Check Josh's failed logs
        josh_failed_logs = UserActivityLog.objects.filter(user=josh, status="failed")
        self.assertEqual(josh_failed_logs.count(), 4)
        for log in josh_failed_logs:
            self.assertEqual(log.user_username, "josh")
            self.assertEqual(log.api_key_id, key_josh.key_id)
            self.assertEqual(log.status, "failed")
            self.assertIn("Access denied", log.error_message)

        # ==========================================
        # PART E: NEGATIVE TESTS - UNASSIGNED USER MALLORY
        # ==========================================
        mock_req_mallory = make_mock_req(mallory, None, key_mallory, ip="192.168.99.99")
        with patch("mcp_server.server.app.get_http_request", return_value=mock_req_mallory):
            # E1. Mallory lists workspaces -> No workspaces / empty message
            mallory_ws_list = json.loads(list_workspaces())
            if isinstance(mallory_ws_list, dict):
                self.assertIn("message", mallory_ws_list)
            else:
                self.assertEqual(len(mallory_ws_list), 0)

            # E2. Mallory tries to access Adam's workspace -> Denied
            res_e2 = get_workspace(workspace_id=str(ws_adam.id))
            self.assertIn("Error: Access denied", res_e2)

            # E3. Mallory tries to access Josh's workspace -> Denied
            res_e3 = get_workspace(workspace_id=str(ws_josh.id))
            self.assertIn("Error: Access denied", res_e3)

        # Check Mallory's failed logs
        mallory_failed_logs = UserActivityLog.objects.filter(user=mallory, status="failed")
        self.assertEqual(mallory_failed_logs.count(), 2)
        for log in mallory_failed_logs:
            self.assertEqual(log.user_username, "mallory")
            self.assertEqual(log.user_email, "mallory@attacker.com")
            self.assertEqual(log.api_key_id, key_mallory.key_id)
            self.assertEqual(log.status, "failed")

        # ==========================================
        # PART F: AUDIT LOG TOTAL INTEGRITY & ISOLATION
        # ==========================================
        # Total logs created in this test:
        # Adam: 3 success + 4 failed = 7 logs
        # Josh: 3 success + 4 failed = 7 logs
        # Mallory: 1 success (list_workspaces returning []) + 2 failed = 3 logs
        self.assertEqual(UserActivityLog.objects.filter(user=adam).count(), 7)
        self.assertEqual(UserActivityLog.objects.filter(user=josh).count(), 7)
        self.assertEqual(UserActivityLog.objects.filter(user=mallory).count(), 3)

        # Verify absolutely ZERO cross-contamination
        self.assertEqual(UserActivityLog.objects.filter(user=adam, user_username="josh").count(), 0)
        self.assertEqual(UserActivityLog.objects.filter(user=adam, user_username="mallory").count(), 0)
        self.assertEqual(UserActivityLog.objects.filter(user=josh, user_username="adam").count(), 0)
        self.assertEqual(UserActivityLog.objects.filter(user=josh, user_username="mallory").count(), 0)
        self.assertEqual(UserActivityLog.objects.filter(user_username="admin").count(), 0)


