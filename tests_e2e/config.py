"""
E2E Test Configuration & Environment Resolution.
"""

import os
from dataclasses import dataclass

from typing import Optional

ENV_TARGETS = {
    "staging": "https://sri.soinventive.co.uk",
    "prod": "https://sri-prod.apps.01.cf.eu01.onstackit.cloud",
    "production": "https://sri-prod.apps.01.cf.eu01.onstackit.cloud",
    "local": "http://localhost:8000",
}


@dataclass
class E2EConfig:
    target_env: str = os.getenv("E2E_TARGET_ENV", "prod").lower()
    base_url: str = os.getenv("E2E_API_URL", ENV_TARGETS.get(os.getenv("E2E_TARGET_ENV", "prod").lower(), "https://sri-prod.apps.01.cf.eu01.onstackit.cloud"))
    username: str = os.getenv("E2E_USERNAME", os.getenv("TEST_USERNAME", os.getenv("ADMIN_USERNAME", "test_e2e")))
    password: str = os.getenv("E2E_PASSWORD", os.getenv("TEST_PASSWORD", os.getenv("ADMIN_PASSWORD", "t4st_pa55w0rD!#")))
    provider: str = os.getenv("E2E_PROVIDER", "arxiv").lower()
    paper_limit: int = int(os.getenv("E2E_PAPER_LIMIT", "10"))
    poll_interval_sec: float = float(os.getenv("E2E_POLL_INTERVAL", "5.0"))
    max_timeout_sec: int = int(os.getenv("E2E_TIMEOUT_SEC", "900"))  # 15 minutes max
    cleanup_before: bool = os.getenv("E2E_CLEANUP_BEFORE", "true").lower() in ("true", "1", "yes")
    delete_after: bool = os.getenv("E2E_CLEANUP_AFTER", "false").lower() in ("true", "1", "yes")

    def __init__(
        self,
        target_env: Optional[str] = None,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        provider: Optional[str] = None,
        paper_limit: Optional[int] = None,
        poll_interval_sec: Optional[float] = None,
        max_timeout_sec: Optional[int] = None,
        cleanup_before: Optional[bool] = None,
        delete_after: Optional[bool] = None,
        cleanup_after: Optional[bool] = None,
    ):
        self.target_env = target_env if target_env is not None else os.getenv("E2E_TARGET_ENV", "prod").lower()
        self.base_url = base_url if base_url is not None else os.getenv("E2E_API_URL", ENV_TARGETS.get(self.target_env, "https://sri-prod.apps.01.cf.eu01.onstackit.cloud"))
        self.username = username if username is not None else os.getenv("E2E_USERNAME", os.getenv("TEST_USERNAME", os.getenv("ADMIN_USERNAME", "test_e2e")))
        self.password = password if password is not None else os.getenv("E2E_PASSWORD", os.getenv("TEST_PASSWORD", os.getenv("ADMIN_PASSWORD", "t4st_pa55w0rD!#")))
        self.provider = provider if provider is not None else os.getenv("E2E_PROVIDER", "arxiv").lower()
        self.paper_limit = paper_limit if paper_limit is not None else int(os.getenv("E2E_PAPER_LIMIT", "10"))
        self.poll_interval_sec = poll_interval_sec if poll_interval_sec is not None else float(os.getenv("E2E_POLL_INTERVAL", "5.0"))
        self.max_timeout_sec = max_timeout_sec if max_timeout_sec is not None else int(os.getenv("E2E_TIMEOUT_SEC", "900"))
        self.cleanup_before = cleanup_before if cleanup_before is not None else (os.getenv("E2E_CLEANUP_BEFORE", "true").lower() in ("true", "1", "yes"))
        resolved_delete = cleanup_after if cleanup_after is not None else delete_after
        self.delete_after = resolved_delete if resolved_delete is not None else (os.getenv("E2E_CLEANUP_AFTER", "false").lower() in ("true", "1", "yes"))

    @property
    def timeout_sec(self) -> int:
        return self.max_timeout_sec

    @property
    def poll_interval(self) -> float:
        return self.poll_interval_sec

    @property
    def cleanup_after(self) -> bool:
        return self.delete_after

    @cleanup_after.setter
    def cleanup_after(self, val: bool) -> None:
        self.delete_after = val

    @classmethod
    def from_env(cls, target: str = None) -> "E2EConfig":
        env_name = (target or os.getenv("E2E_TARGET_ENV", "prod")).lower()
        url = ENV_TARGETS.get(env_name, os.getenv("E2E_API_URL", "https://sri-prod.apps.01.cf.eu01.onstackit.cloud"))
        return cls(
            target_env=env_name,
            base_url=url.rstrip("/"),
            username=os.getenv("E2E_USERNAME", os.getenv("TEST_USERNAME", os.getenv("ADMIN_USERNAME", "test_e2e"))),
            password=os.getenv("E2E_PASSWORD", os.getenv("TEST_PASSWORD", os.getenv("ADMIN_PASSWORD", "t4st_pa55w0rD!#"))),
            provider=os.getenv("E2E_PROVIDER", "arxiv").lower(),
            paper_limit=int(os.getenv("E2E_PAPER_LIMIT", "10")),
            poll_interval_sec=float(os.getenv("E2E_POLL_INTERVAL", "5.0")),
            max_timeout_sec=int(os.getenv("E2E_TIMEOUT_SEC", "900")),
            cleanup_before=os.getenv("E2E_CLEANUP_BEFORE", "true").lower() in ("true", "1", "yes"),
            delete_after=os.getenv("E2E_CLEANUP_AFTER", "false").lower() in ("true", "1", "yes"),
        )

