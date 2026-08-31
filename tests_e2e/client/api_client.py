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

    def refresh_auth_token(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            url = f"{self.base_url}/api/auth/refresh/"
            self.session.cookies.clear()
            r = self.session.post(url, json={"refresh": self.refresh_token}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                new_access = data.get("access")
                if new_access:
                    self.set_auth_token(new_access, data.get("refresh", self.refresh_token))
                    logger.info("🔄 Automatically refreshed JWT Access Token.")
                    return True
        except Exception as e:
            logger.warning(f"Failed to refresh JWT token: {e}")
        return False

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

        max_attempts = 4
        last_resp = None
        for attempt in range(1, max_attempts + 1):
            t0 = time.time()
            try:
                # Clear session cookies to prevent cookie bloat causing HTTP 431 on proxies
                self.session.cookies.clear()

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
                last_resp = resp

                # If token expired mid-poll, try refreshing it once
                if resp.status_code == 401 and self.refresh_token and attempt < max_attempts:
                    if self.refresh_auth_token():
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        continue

                # If proxy returns 431 or server is momentarily cycling (502/503/504), retry
                is_transient_proxy_error = (
                    resp.status_code in (431, 502, 503, 504) or
                    (resp.status_code == 404 and "<!doctype html" in resp.text.lower() and attempt < max_attempts)
                )

                if is_transient_proxy_error and attempt < max_attempts:
                    self.session.cookies.clear()
                    logger.warning(f"⚠️ [TRANSIENT {resp.status_code}] {method} {url} returned transient gateway response. Retrying in {attempt * 1.5}s...")
                    time.sleep(attempt * 1.5)
                    continue

                if expected_status and resp.status_code != expected_status:
                    raise AssertionError(
                        f"Expected status {expected_status} but got {resp.status_code} for {method} {url}. Response: {resp.text}"
                    )

                return resp
            except requests.RequestException as e:
                elapsed = round((time.time() - t0) * 1000, 1)
                if attempt < max_attempts:
                    logger.warning(f"⚠️ [NETWORK RETRY {attempt}/{max_attempts}] {method} {url} failed: {e}. Retrying in {attempt * 1.5}s...")
                    time.sleep(attempt * 1.5)
                else:
                    logger.error(f"Network error on {method} {url} after {elapsed}ms: {e}")
                    raise

        if expected_status and last_resp and last_resp.status_code != expected_status:
            raise AssertionError(
                f"Expected status {expected_status} but got {last_resp.status_code} for {method} {url}. Response: {last_resp.text}"
            )
        return last_resp

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
