import time
from datetime import timedelta
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from research_intelligence.models import Workspace
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
            acceptance_criteria="Inclusion rules",
            rejection_criteria="Exclusion rules"
        )
        self.list_url = reverse('workspace-list')
        self.login_url = reverse('login')
        self.refresh_url = reverse('refresh-token')
        self.test_user = User(id=9999, username='test_user', is_active=True)

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

    def test_login_endpoint_accessible_without_authentication(self):
        """Verify that the login endpoint does not require auth headers."""
        data = {
            "api_key": "some-api-key",
            "workspace_id": str(self.workspace.id)
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    # ==========================================
    # 2. Dynamic Endpoint Security Scanner
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
