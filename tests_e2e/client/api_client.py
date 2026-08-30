"""
Base HTTP API Client for E2E Testing with automatic JWT Bearer token injection,
retry handling, logging, and response normalization.
"""

import logging
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger("e2e_client")


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def set_auth_token(self, access_token: str, refresh_token: Optional[str] = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    def clear_auth(self):
        self.access_token = None
        self.refresh_token = None
        self.session.headers.pop("Authorization", None)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        timeout: int = 45,
        expected_status: Optional[int] = None,
    ) -> requests.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        t0 = time.time()
        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=timeout,
            )
            elapsed = round((time.time() - t0) * 1000, 1)
            logger.debug(f"{method} {url} -> {resp.status_code} ({elapsed}ms)")

            if expected_status and resp.status_code != expected_status:
                raise AssertionError(
                    f"Expected status {expected_status} but got {resp.status_code} for {method} {url}. Response: {resp.text}"
                )

            return resp
        except requests.RequestException as e:
            elapsed = round((time.time() - t0) * 1000, 1)
            logger.error(f"Network error on {method} {url} after {elapsed}ms: {e}")
            raise

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, expected_status: Optional[int] = None) -> requests.Response:
        return self._request("GET", endpoint, params=params, expected_status=expected_status)

    def post(self, endpoint: str, json_data: Optional[Any] = None, expected_status: Optional[int] = None) -> requests.Response:
        return self._request("POST", endpoint, json_data=json_data, expected_status=expected_status)

    def put(self, endpoint: str, json_data: Optional[Any] = None, expected_status: Optional[int] = None) -> requests.Response:
        return self._request("PUT", endpoint, json_data=json_data, expected_status=expected_status)

    def patch(self, endpoint: str, json_data: Optional[Any] = None, expected_status: Optional[int] = None) -> requests.Response:
        return self._request("PATCH", endpoint, json_data=json_data, expected_status=expected_status)

    def delete(self, endpoint: str, expected_status: Optional[int] = None) -> requests.Response:
        return self._request("DELETE", endpoint, expected_status=expected_status)
