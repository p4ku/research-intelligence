"""
E2E Test Configuration & Environment Resolution.
"""

import os
from dataclasses import dataclass

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
    username: str = os.getenv("E2E_USERNAME", "test_e2e")
    password: str = os.getenv("E2E_PASSWORD", "t4st_pa55w0rD!#")
    provider: str = os.getenv("E2E_PROVIDER", "arxiv").lower()
    paper_limit: int = int(os.getenv("E2E_PAPER_LIMIT", "10"))
    poll_interval_sec: float = float(os.getenv("E2E_POLL_INTERVAL", "5.0"))
    max_timeout_sec: int = int(os.getenv("E2E_TIMEOUT_SEC", "900"))  # 15 minutes max
    cleanup_before: bool = os.getenv("E2E_CLEANUP_BEFORE", "true").lower() in ("true", "1", "yes")
    delete_after: bool = os.getenv("E2E_CLEANUP_AFTER", "false").lower() in ("true", "1", "yes")

    @classmethod
    def from_env(cls, target: str = None) -> "E2EConfig":
        env_name = (target or os.getenv("E2E_TARGET_ENV", "prod")).lower()
        url = ENV_TARGETS.get(env_name, os.getenv("E2E_API_URL", "https://sri-prod.apps.01.cf.eu01.onstackit.cloud"))
        return cls(
            target_env=env_name,
            base_url=url.rstrip("/"),
            username=os.getenv("E2E_USERNAME", "test_e2e"),
            password=os.getenv("E2E_PASSWORD", "t4st_pa55w0rD!#"),
            provider=os.getenv("E2E_PROVIDER", "arxiv").lower(),
            paper_limit=int(os.getenv("E2E_PAPER_LIMIT", "10")),
            poll_interval_sec=float(os.getenv("E2E_POLL_INTERVAL", "5.0")),
            max_timeout_sec=int(os.getenv("E2E_TIMEOUT_SEC", "900")),
            cleanup_before=os.getenv("E2E_CLEANUP_BEFORE", "true").lower() in ("true", "1", "yes"),
            delete_after=os.getenv("E2E_CLEANUP_AFTER", "false").lower() in ("true", "1", "yes"),
        )
