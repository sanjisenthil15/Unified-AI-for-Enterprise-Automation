"""
modules/intelligence/cache.py

Thread-safe in-memory TTL cache for AI intelligence insights.

Architectural Notes & Production Limitations:
  1. Process-Local: This cache resides in the memory of the current Python process.
     In a multi-worker deployment (e.g. Uvicorn with multiple workers), each worker
     maintains its own isolated cache.
  2. Cloud Ephemerality: Hosting platforms like Render, Railway, or Heroku periodically
     restart or spin down idle containers. When a container restarts, in-memory cache
     entries are cleared, and the next request triggers a fresh evaluation.
  3. Quota & Throttling: To protect external Gemini API quotas and prevent concurrent
     duplicate model calls (thundering herd), key-level threading locks and refresh
     rate limits are implemented.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 1800  # 30 minutes
MIN_REFRESH_INTERVAL_SECONDS = 10  # Minimum delay between forced manual refreshes


@dataclass
class CacheEntry:
    data: Any
    created_at: float
    expires_at: float


class IntelligenceCache:
    """Thread-safe in-memory cache with scope-aware keys, expiration,
    throttling, and duplicate call serialization."""

    def __init__(self, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._last_evaluated_at: Dict[str, float] = {}
        self._global_lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: str) -> Optional[Any]:
        """Fetch cached data if present and not expired."""
        with self._global_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                # Expired — clear entry
                del self._cache[key]
                return None
            return entry.data

    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """Store data in cache with a TTL in seconds."""
        now = time.time()
        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expires_at = now + ttl_seconds

        with self._global_lock:
            self._cache[key] = CacheEntry(
                data=data,
                created_at=now,
                expires_at=expires_at,
            )
            self._last_evaluated_at[key] = now

    def check_refresh_throttle(self, key: str) -> Tuple[bool, float]:
        """Checks if a manual refresh request is permitted or throttled.

        Returns:
            (is_allowed: bool, seconds_remaining: float)
        """
        now = time.time()
        with self._global_lock:
            last_run = self._last_evaluated_at.get(key, 0.0)
            elapsed = now - last_run
            if elapsed < MIN_REFRESH_INTERVAL_SECONDS:
                remaining = round(MIN_REFRESH_INTERVAL_SECONDS - elapsed, 1)
                return False, remaining
            return True, 0.0

    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache key."""
        with self._global_lock:
            self._cache.pop(key, None)

    def invalidate_scope(self, prefix: str) -> int:
        """Invalidate all cache keys starting with the given prefix."""
        with self._global_lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._global_lock:
            self._cache.clear()
            self._last_evaluated_at.clear()

    def get_or_evaluate(
        self,
        key: str,
        evaluator_fn: Any,
        ttl: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Tuple[Any, bool]:
        """Thread-safe get-or-evaluate pattern.

        Protects against concurrent duplicate generation: if multiple threads
        request an uncached key, only one runs the evaluator_fn while the others
        wait and consume the newly cached result.

        Returns:
            (result: Any, is_cached: bool)
        """
        if not force_refresh:
            cached = self.get(key)
            if cached is not None:
                return cached, True

        key_lock = self._get_key_lock(key)
        with key_lock:
            # Double-check after acquiring key lock
            if not force_refresh:
                cached = self.get(key)
                if cached is not None:
                    return cached, True

            # Evaluate fresh data
            result = evaluator_fn()
            self.set(key, result, ttl=ttl)
            return result, False


# Global singleton instance for the intelligence module
intelligence_cache = IntelligenceCache()
