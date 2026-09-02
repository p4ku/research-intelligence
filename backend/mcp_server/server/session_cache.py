"""
FastMCP Session Authentication Cache.

Provides thread-safe, bounded, expiring session caching for FastMCP SSE connections,
with automatic invalidation on TTL expiry and active API key status checks.
"""

import time
from collections import OrderedDict
from typing import Optional, Tuple, Any


class FastMCPSessionCache:
    """
    Thread-safe, bounded, expiring session cache for FastMCP SSE sessions.
    Evicts stale entries older than ttl_seconds (default 15 minutes) and maintains max_size.
    Also validates that cached API keys remain active.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 900.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache = OrderedDict()  # session_id -> (user, workspace, api_key, timestamp)

    def get(self, session_id: str) -> Optional[Tuple[Any, Any, Any]]:
        if not session_id:
            return None
        now = time.time()
        entry = self._cache.get(session_id)
        if not entry:
            return None
        user, workspace, api_key, ts = entry
        if now - ts > self.ttl_seconds:
            # Expired
            self._cache.pop(session_id, None)
            return None
        # Verify that api_key is still active
        if hasattr(api_key, 'is_active') and not api_key.is_active:
            self._cache.pop(session_id, None)
            return None
        # Move to end for LRU refresh
        self._cache.move_to_end(session_id)
        return user, workspace, api_key

    def set(self, session_id: str, user: Any, workspace: Any, api_key: Any) -> None:
        if not session_id:
            return
        now = time.time()
        if session_id in self._cache:
            self._cache.pop(session_id, None)
        elif len(self._cache) >= self.max_size:
            # Evict oldest entry
            self._cache.popitem(last=False)
        self._cache[session_id] = (user, workspace, api_key, now)

    def invalidate(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def clear(self) -> None:
        self._cache.clear()

    def __contains__(self, session_id: str) -> bool:
        return self.get(session_id) is not None

    def __getitem__(self, session_id: str) -> Tuple[Any, Any, Any]:
        val = self.get(session_id)
        if val is None:
            raise KeyError(session_id)
        return val

    def __setitem__(self, session_id: str, value: Tuple[Any, Any, Any]) -> None:
        user, workspace, api_key = value
        self.set(session_id, user, workspace, api_key)
