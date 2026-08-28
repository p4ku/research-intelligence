"""
Base TestCase and Fixture Helpers for MCP Test Suite.
"""
import json
import hashlib
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    APIKey,
)

User = get_user_model()


class BaseMCPTestCase(TestCase):
    """
    Standard test case foundation providing clean fixtures, auth patching,
    and response parsing for MCP tools and server endpoints.
    """

    def setUp(self):
        super().setUp()
        self.admin = self.create_user(username="mcp_admin", email="admin@schwarz.de", is_superuser=True)
        self.researcher = self.create_user(username="mcp_researcher", email="researcher@schwarz.de")
        self.outsider = self.create_user(username="mcp_outsider", email="outsider@external.com")

        self.workspace = self.create_workspace(name="Default MCP Workspace", user=self.admin, role="admin")
        self.api_key = self.create_api_key(user=self.admin, name="Admin Key", scopes=["*"])

    def create_user(self, username: str, email: str = None, password: str = "password123", is_superuser: bool = False):
        email = email or f"{username}@schwarz.de"
        if is_superuser:
            return User.objects.create_superuser(username=username, email=email, password=password)
        return User.objects.create_user(username=username, email=email, password=password)

    def create_workspace(self, name: str, user=None, role: str = "admin", **kwargs):
        ws = Workspace.objects.create(name=name, **kwargs)
        if user:
            WorkspaceMember.objects.create(workspace=ws, user=user, role=role)
        return ws

    def add_member(self, workspace, user, role: str = "researcher"):
        return WorkspaceMember.objects.create(workspace=workspace, user=user, role=role)

    def create_api_key(self, user, name: str = "Test Key", scopes=None, key_id: str = None, raw_secret: str = "schwarz123!"):
        scopes = scopes or ["*"]
        key_id = key_id or f"key_{user.username}"
        hashed = hashlib.sha256(raw_secret.encode()).hexdigest()
        key = APIKey.objects.create(
            user=user,
            name=name,
            key_id=key_id,
            hashed_secret=hashed,
            scopes=scopes
        )
        key.raw_secret = raw_secret
        return key

    def create_mock_request(self, user=None, workspace=None, api_key=None, ip: str = "127.0.0.1"):
        mock_req = MagicMock()
        mock_req.scope = {"type": "http", "client": (ip, 50000)}
        mock_req.client = MagicMock(host=ip)
        mock_req.query_params = {}
        mock_req.headers = {}

        if api_key:
            mock_req.headers["x-mcp-key-id"] = api_key.key_id
            mock_req.headers["x-mcp-secret-key"] = getattr(api_key, "raw_secret", "schwarz123!")
            if workspace:
                mock_req.headers["x-mcp-workspace-id"] = str(workspace.id)

        return mock_req

    @contextmanager
    def patch_auth(self, user=None, workspace=None, api_key=None, ip: str = "127.0.0.1"):
        """
        Unified context manager for FastMCP tool execution.
        Patches both `get_auth_context` and `get_http_request`.
        """
        user = user or self.admin
        workspace = workspace or self.workspace
        api_key = api_key or self.api_key
        mock_req = self.create_mock_request(user=user, workspace=workspace, api_key=api_key, ip=ip)

        with patch("mcp.server.app.get_auth_context", return_value=(user, workspace, api_key)), \
             patch("mcp.server.app.get_http_request", return_value=mock_req):
            yield

    def parse_res(self, res_str):
        """Helper to parse JSON string results from MCP tools."""
        if isinstance(res_str, dict) or isinstance(res_str, list):
            return res_str
        return json.loads(res_str)
