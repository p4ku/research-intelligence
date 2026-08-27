from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from research_intelligence.models import Workspace, WorkspaceMember, APIKey


class JWTAuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "Secr3tP@ssw0rd!"
        self.user = User.objects.create_user(
            username="testresearcher",
            email="researcher@schwarz-intelligence.com",
            password=self.password,
            first_name="Marie",
            last_name="Curie"
        )
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence",
            abstract_acceptance_criteria="Quantum algorithms"
        )

        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.api_key = APIKey.objects.create(
            user=self.user,
            key_id="mcp_key_123",
            is_active=True
        )
        self.api_key.set_secret("mcp_secret_xyz")
        self.api_key.save()


    def test_login_with_username_and_password(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertEqual(resp.data['user']['username'], 'testresearcher')
        self.assertEqual(resp.data['user']['email'], 'researcher@schwarz-intelligence.com')
        self.assertEqual(resp.data['user']['full_name'], 'Marie Curie')

    def test_login_with_email_and_password(self):
        resp = self.client.post('/api/auth/login/', {
            'email': 'researcher@schwarz-intelligence.com',
            'password': self.password
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertEqual(resp.data['user']['id'], self.user.id)

    def test_login_with_invalid_credentials(self):
        resp = self.client.post('/api/auth/login/', {
            'email': 'researcher@schwarz-intelligence.com',
            'password': 'WrongPassword123'
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', resp.data)

    def test_authenticated_user_profile_and_workspaces(self):
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        access_token = login_resp.data['access']

        # 1. Fetch user profile /api/auth/me/
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_resp = self.client.get('/api/auth/me/')
        self.assertEqual(me_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(me_resp.data['email'], 'researcher@schwarz-intelligence.com')
        self.assertEqual(me_resp.data['workspaces_count'], 1)

        # 2. Fetch accessible workspaces /api/workspaces/
        ws_resp = self.client.get('/api/workspaces/')
        self.assertEqual(ws_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ws_resp.data), 1)
        self.assertEqual(ws_resp.data[0]['name'], 'Quantum Computing Intelligence')

    def test_token_refresh_flow(self):
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        refresh_token = login_resp.data['refresh']

        refresh_resp = self.client.post('/api/auth/refresh/', {
            'refresh': refresh_token
        }, format='json')

        self.assertEqual(refresh_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_resp.data)

    def test_legacy_api_key_login(self):
        resp = self.client.post('/api/auth/login/', {
            'api_key': 'mcp_key_123:mcp_secret_xyz',
            'workspace_id': str(self.workspace.id)
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertEqual(resp.data['user']['username'], 'testresearcher')
