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

    def test_update_user_profile_self(self):
        """User can update their own username, email, and name."""
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Update username and email
        patch_resp = self.client.patch('/api/auth/me/', {
            'username': 'marie_curie_updated',
            'email': 'marie.updated@schwarz-intelligence.com',
            'first_name': 'Marie Sklodowska',
            'last_name': 'Curie'
        }, format='json')

        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data['username'], 'marie_curie_updated')
        self.assertEqual(patch_resp.data['email'], 'marie.updated@schwarz-intelligence.com')
        self.assertEqual(patch_resp.data['full_name'], 'Marie Sklodowska Curie')

        # Verify persisted in DB
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'marie_curie_updated')
        self.assertEqual(self.user.email, 'marie.updated@schwarz-intelligence.com')

    def test_update_user_profile_duplicate_validation(self):
        """Cannot take another user's username or email."""
        User.objects.create_user(username='existing_user', email='existing@example.com', password='password123')

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        # Duplicate username
        res_dup_username = self.client.patch('/api/auth/me/', {'username': 'existing_user'}, format='json')
        self.assertEqual(res_dup_username.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', res_dup_username.data)

        # Duplicate email
        res_dup_email = self.client.patch('/api/auth/me/', {'email': 'existing@example.com'}, format='json')
        self.assertEqual(res_dup_email.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', res_dup_email.data)

    def test_change_password_flow(self):
        """User can change their password and log in with the new one."""
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        new_password = "BrandNewSuperPassword123!"

        # 1. Invalid old password -> 400
        res_bad_old = self.client.post('/api/auth/change-password/', {
            'old_password': 'WrongOldPassword123!',
            'new_password': new_password,
            'confirm_password': new_password,
        }, format='json')
        self.assertEqual(res_bad_old.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Mismatched confirmation -> 400
        res_mismatch = self.client.post('/api/auth/change-password/', {
            'old_password': self.password,
            'new_password': new_password,
            'confirm_password': 'DifferentPassword123!',
        }, format='json')
        self.assertEqual(res_mismatch.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Successful change -> 200 OK
        res_success = self.client.post('/api/auth/change-password/', {
            'old_password': self.password,
            'new_password': new_password,
            'confirm_password': new_password,
        }, format='json')
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)

        # 4. Old password no longer works
        self.client.credentials()  # Clear auth headers
        old_login = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        # 5. New password works
        new_login = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': new_password
        }, format='json')
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)
        self.assertIn('access', new_login.data)

    def test_user_cannot_modify_another_user_account(self):
        """Verify that passing arbitrary user_id / target fields cannot modify another user."""
        other_user = User.objects.create_user(
            username='victim_user',
            email='victim@example.com',
            password='VictimPassword123!',
            first_name='Victim',
            last_name='User'
        )

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'testresearcher',
            'password': self.password
        }, format='json')
        access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Attacker tries to send other user's ID or overwrite their email
        res = self.client.patch('/api/auth/me/', {
            'id': other_user.id,
            'user_id': other_user.id,
            'username': 'testresearcher_safe',
            'first_name': 'ChangedName'
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Confirm the attacking user was updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'testresearcher_safe')
        self.assertEqual(self.user.first_name, 'ChangedName')

        # Confirm the other user was completely untouched
        other_user.refresh_from_db()
        self.assertEqual(other_user.username, 'victim_user')
        self.assertEqual(other_user.email, 'victim@example.com')
        self.assertEqual(other_user.first_name, 'Victim')
        self.assertTrue(other_user.check_password('VictimPassword123!'))

    def test_legacy_api_key_login(self):
        resp = self.client.post('/api/auth/login/', {
            'api_key': 'mcp_key_123:mcp_secret_xyz',
            'workspace_id': str(self.workspace.id)
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertEqual(resp.data['user']['username'], 'testresearcher')
