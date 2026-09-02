"""
Unit tests for FastMCPSessionCache.

Validates:
1. Basic get, set, contains, and dict-like indexing behavior.
2. TTL expiration and eviction of stale entries.
3. Max-size capacity enforcement and LRU eviction order.
4. Automatic invalidation when an API key becomes inactive.
5. Invalidate and clear operations.
6. Edge case handling (None / empty session IDs).
7. Backward-compatible import from mcp_server.server.app.
"""

import time
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from mcp_server.server.session_cache import FastMCPSessionCache
from mcp_server.server.app import FastMCPSessionCache as FastMCPSessionCacheFromApp


class FastMCPSessionCacheTestCase(SimpleTestCase):
    def test_import_compatibility(self):
        """Verify that FastMCPSessionCache is exported from both module and app.py."""
        self.assertIs(FastMCPSessionCache, FastMCPSessionCacheFromApp)

    def test_basic_set_get_and_contains(self):
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=60.0)
        mock_user = MagicMock(username="tester")
        mock_ws = MagicMock()
        mock_ws.name = "TestWorkspace"
        mock_key = MagicMock(key_id="test_key", is_active=True)

        cache.set("session_1", mock_user, mock_ws, mock_key)

        self.assertIn("session_1", cache)
        retrieved = cache.get("session_1")
        self.assertIsNotNone(retrieved)
        u, w, k = retrieved
        self.assertEqual(u.username, "tester")
        self.assertEqual(w.name, "TestWorkspace")
        self.assertEqual(k.key_id, "test_key")

    def test_dict_like_indexing(self):
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=60.0)
        mock_user = MagicMock()
        mock_ws = MagicMock()
        mock_key = MagicMock(is_active=True)

        cache["sess_dict"] = (mock_user, mock_ws, mock_key)
        self.assertIn("sess_dict", cache)
        u, w, k = cache["sess_dict"]
        self.assertIs(u, mock_user)

        with self.assertRaises(KeyError):
            _ = cache["non_existent_session"]

    def test_ttl_expiration(self):
        """Verify entries expire and return None after ttl_seconds."""
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=0.1)
        mock_key = MagicMock(is_active=True)

        cache.set("short_lived", "user", "ws", mock_key)
        self.assertIn("short_lived", cache)

        time.sleep(0.15)

        self.assertNotIn("short_lived", cache)
        self.assertIsNone(cache.get("short_lived"))
        with self.assertRaises(KeyError):
            _ = cache["short_lived"]

    def test_lru_eviction_on_max_size(self):
        """Verify that oldest unaccessed entries are evicted when max_size is reached."""
        cache = FastMCPSessionCache(max_size=3, ttl_seconds=60.0)
        mock_key = MagicMock(is_active=True)

        cache.set("s1", "u1", "w1", mock_key)
        cache.set("s2", "u2", "w2", mock_key)
        cache.set("s3", "u3", "w3", mock_key)

        # Access s1 to make s2 the oldest unaccessed
        _ = cache.get("s1")

        # Adding s4 must evict s2
        cache.set("s4", "u4", "w4", mock_key)

        self.assertIn("s1", cache)
        self.assertNotIn("s2", cache)
        self.assertIn("s3", cache)
        self.assertIn("s4", cache)

    def test_inactive_key_automatic_eviction(self):
        """Verify that if an API key's is_active becomes False, the entry is invalidated."""
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=60.0)
        mock_key = MagicMock(is_active=True)

        cache.set("active_sess", "user", "ws", mock_key)
        self.assertIn("active_sess", cache)

        # Revoke key
        mock_key.is_active = False

        self.assertIsNone(cache.get("active_sess"))
        self.assertNotIn("active_sess", cache)

    def test_invalidate_and_clear(self):
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=60.0)
        mock_key = MagicMock(is_active=True)

        cache.set("s1", "u1", "w1", mock_key)
        cache.set("s2", "u2", "w2", mock_key)

        cache.invalidate("s1")
        self.assertNotIn("s1", cache)
        self.assertIn("s2", cache)

        cache.clear()
        self.assertNotIn("s2", cache)

    def test_none_and_empty_session_handling(self):
        cache = FastMCPSessionCache(max_size=10, ttl_seconds=60.0)
        mock_key = MagicMock(is_active=True)

        self.assertIsNone(cache.get(None))
        self.assertIsNone(cache.get(""))

        cache.set(None, "u", "w", mock_key)
        cache.set("", "u", "w", mock_key)
        self.assertNotIn(None, cache)
        self.assertNotIn("", cache)
