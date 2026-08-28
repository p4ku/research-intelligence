"""
Base TestCase and Fixture Helpers for Chat Test Suite.
"""
from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import Workspace, WorkspaceMember, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage

User = get_user_model()


class BaseChatTestCase(TestCase):
    """
    Standard test case foundation for Chat application.
    Provides pre-authenticated API client, test workspace, paper, and session fixtures.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.password = "SecureChatTest123!"

        self.user = self.create_user(username="chat_tester", email="chat_tester@schwarz.com", password=self.password)
        self.outsider = self.create_user(username="chat_outsider", email="outsider@external.com", password=self.password)

        self.workspace = self.create_workspace(name="Chat Intelligence Lab", user=self.user, role="researcher")
        self.run = PipelineRun.objects.create(workspace=self.workspace)

        self.paper = self.create_paper(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_neuromorphic_01",
            title="Neuromorphic Optical Computing",
            abstract="Energy efficient spiking neural networks with silicon photonics."
        )

        self.session = self.create_session(paper=self.paper, user=self.user, title="Optical Computing Review")

        # Authenticate default APIClient as self.user
        self.authenticate_as(self.user, self.password)

    def create_user(self, username: str, email: str = None, password: str = "SecurePass123!", is_superuser: bool = False):
        email = email or f"{username}@schwarz.com"
        if is_superuser:
            return User.objects.create_superuser(username=username, email=email, password=password)
        return User.objects.create_user(username=username, email=email, password=password)

    def create_workspace(self, name: str, user=None, role: str = "admin", **kwargs):
        ws = Workspace.objects.create(name=name, **kwargs)
        if user:
            WorkspaceMember.objects.create(workspace=ws, user=user, role=role)
        return ws

    def create_paper(self, workspace, pipeline_run=None, hash_id="sha256_test_paper", title="Test Paper", abstract="Test abstract", **kwargs):
        return Paper.objects.create(
            workspace=workspace,
            pipeline_run=pipeline_run,
            hash_id=hash_id,
            title=title,
            abstract=abstract,
            **kwargs
        )

    def create_session(self, paper=None, user=None, title="Chat Session", workspace=None, **kwargs):
        target_paper = paper or self.paper
        target_workspace = workspace or (target_paper.workspace if target_paper else self.workspace)
        return PaperChatSession.objects.create(
            workspace=target_workspace,
            paper=target_paper,
            user=user or self.user,
            title=title,
            **kwargs
        )

    def create_message(self, session=None, sender="user", message="What is this paper about?", status="completed", **kwargs):
        return PaperChatMessage.objects.create(
            session=session or self.session,
            sender=sender,
            message=message,
            status=status,
            **kwargs
        )

    def authenticate_as(self, user, password=None, client=None):
        """Authenticates client with JWT tokens."""
        target_client = client or self.client
        password = password or self.password
        login_res = target_client.post('/api/auth/login/', {
            'username': user.username,
            'password': password
        }, format='json')
        if login_res.status_code == status.HTTP_200_OK and "access" in login_res.data:
            target_client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_res.data["access"]}')
        return target_client

    def create_mock_llm_provider(self, response_text: str = "Verified answer [Page 1, Fig 2].", stream_chunks=None):
        """Helper to create a mocked LLM Provider with standard sync and streaming returns."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = response_text
        if stream_chunks:
            mock_provider.generate_stream.return_value = iter(stream_chunks)
        else:
            mock_provider.generate_stream.return_value = iter([
                ("Here is the answer: ", None),
                (response_text, {"prompt_tokens": 500, "candidates_tokens": 50, "total_tokens": 550})
            ])
        return mock_provider
