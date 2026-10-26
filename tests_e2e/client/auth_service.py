"""
Authentication Service for E2E Tests.
"""

import logging
from typing import Dict, Any
from .api_client import APIClient

logger = logging.getLogger("e2e_auth")


class AuthService:
    def __init__(self, client: APIClient):
        self.client = client

    def login(self, username: str, password: str) -> Dict[str, Any]:
        logger.info(f"🔑 Authenticating user '{username}' against {self.client.base_url}...")
        resp = self.client.post(
            "/api/auth/login/",
            json_data={"username": username, "password": password},
            expected_status=200,
        )
        data = resp.json()
        access_token = data.get("access")
        refresh_token = data.get("refresh")
        if not access_token:
            raise ValueError(f"Login failed: No access token in response: {data}")

        self.client.set_auth_token(access_token, refresh_token)
        logger.info(f"✅ Authenticated successfully as '{username}' (User ID: {data.get('user_id')}).")
        return data

    def get_profile(self) -> Dict[str, Any]:
        resp = self.client.get("/api/auth/me/", expected_status=200)
        return resp.json()

    def create_user_if_missing(self, username: str, password: str, email: str = "") -> Dict[str, Any]:
        """Creates a user via POST /api/auth/users/ (requires superuser/staff). Ignores existing users."""
        resp = self.client.post(
            "/api/auth/users/",
            json_data={
                "username": username,
                "password": password,
                "email": email or f"{username}@example.com",
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if resp.status_code in (200, 201):
            logger.info(f"👤 Created reviewer user '{username}'.")
            return resp.json()
        logger.info(f"ℹ️ Reviewer user '{username}' ready (status: {resp.status_code}).")
        return {}
