import time
from datetime import timedelta
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from research_intelligence.models import Workspace, WorkspaceMember, APIKey
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from api.urls import router

class APISecurityTestCase(APITestCase):
    """
    Verifies that all API endpoints require authentication
    and refuse access to unauthenticated or expired requests using SimpleJWT.
    """

    def setUp(self):
        # Create a workspace for testing endpoints
        self.workspace = Workspace.objects.create(
            name="Test Scan Project",
            abstract_acceptance_criteria="Inclusion rules",
            abstract_rejection_criteria="Exclusion rules"
        )
        self.list_url = reverse('workspace-list')
        self.login_url = reverse('login')
        self.refresh_url = reverse('refresh-token')
        self.test_user = User.objects.create_user(username='test_user', password='testpass123', is_active=True)
        # Grant membership so scoped ViewSets return data for valid token tests
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.test_user, role='admin')

        # Create a valid MCP API key for login tests
        self.api_key_obj = APIKey.objects.create(
            name="Test API Key",
            user=self.test_user,
            workspace=self.workspace,
            is_active=True,
            scopes=["workspaces:read", "workspaces:write"],
        )
        self.raw_secret = self.api_key_obj.generate_key()
        self.api_key_obj.save()
        self.api_key_string = f"{self.api_key_obj.key_id}:{self.raw_secret}"

    # ==========================================
    # 1. SimpleJWT Lifecycle Tests
    # ==========================================

    def test_jwt_creation_and_usage(self):
        """Test creating a SimpleJWT token and using it to authenticate."""
        token = AccessToken.for_user(self.test_user)
        token['workspace_id'] = str(self.workspace.id)
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_jwt_expiration(self):
        """Test that an expired SimpleJWT token is rejected."""
        token = AccessToken.for_user(self.test_user)
        token['workspace_id'] = str(self.workspace.id)
        # Set expiration in the past
        token['exp'] = int(time.time()) - 10

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("token_not_valid", response.data.get("code", ""))

    def test_jwt_regeneration_refresh(self):
        """Test exchanging a SimpleJWT refresh token for a new access token."""
        # 1. Generate access and refresh tokens
        refresh = RefreshToken.for_user(self.test_user)
        refresh['workspace_id'] = str(self.workspace.id)
        
        # 2. Call SimpleJWT's refresh endpoint
        response = self.client.post(self.refresh_url, {"refresh": str(refresh)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        new_access_token = response.data.get("access")
        self.assertIsNotNone(new_access_token)

        # 3. Verify the new access token successfully accesses the API
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access_token}')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==========================================
    # 2. Login Endpoint Security Tests
    # ==========================================

    def test_login_with_valid_api_key(self):
        """Login with a valid API key returns JWT tokens with real user_id."""
        data = {
            "api_key": self.api_key_string,
            "workspace_id": str(self.workspace.id)
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user_id"], self.test_user.id)

    def test_login_with_invalid_api_key_rejected(self):
        """Login with a random/invalid API key must be rejected."""
        data = {
            "api_key": "totally-fake-key",
            "workspace_id": str(self.workspace.id)
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED,
                         "🔴 Login endpoint accepted an invalid API key!")

    def test_login_with_wrong_secret_rejected(self):
        """Login with correct key_id but wrong secret must be rejected."""
        data = {
            "api_key": f"{self.api_key_obj.key_id}:wrong_secret_here",
            "workspace_id": str(self.workspace.id)
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_endpoint_accessible_without_authentication(self):
        """Verify that the login endpoint does not require auth headers (AllowAny)."""
        data = {
            "api_key": self.api_key_string,
            "workspace_id": str(self.workspace.id)
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    # ==========================================
    # 3. Dynamic Endpoint Security Scanner
    # ==========================================

    def test_dynamic_endpoint_scanner(self):
        """
        Dynamically discovers all viewset endpoints registered in the router,
        and tests them against various token authentication states:
        - No token
        - Valid token
        - Expired token
        """
        for prefix, viewset, basename in router.registry:
            list_url = f"/api/{prefix}/"
            
            # A. Access Without Token
            self.client.credentials()  # Clear credentials
            response = self.client.get(list_url)
            self.assertEqual(
                response.status_code, status.HTTP_401_UNAUTHORIZED,
                f"Endpoint {list_url} allowed access without token!"
            )

            # B. Access With Expired Token
            token = AccessToken.for_user(self.test_user)
            token['workspace_id'] = str(self.workspace.id)
            token['exp'] = int(time.time()) - 10

            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
            response = self.client.get(list_url)
            self.assertEqual(
                response.status_code, status.HTTP_401_UNAUTHORIZED,
                f"Endpoint {list_url} allowed access with an expired token!"
            )

            # C. Access With Valid Token
            token = AccessToken.for_user(self.test_user)
            token['workspace_id'] = str(self.workspace.id)

            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
            response = self.client.get(list_url)
            # A valid request should NOT be rejected with 401 Unauthorized or 403 Forbidden
            self.assertNotIn(
                response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
                f"Endpoint {list_url} rejected a valid token with {response.status_code}!"
            )
