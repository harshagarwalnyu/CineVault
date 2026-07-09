"""
Lightweight in-process + optional Redis cache layer.
=====================================================
All hot endpoints funnel through `cached()` so repeat
requests resolve in <1 ms without touching the DB.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Optional

import redis

from backend.config import REDIS_URL

logger = logging.getLogger(__name__)

# ---------- in-process LRU store ----------

_MAX_ENTRIES = 2048

_store: dict[str, tuple[float, Any]] = {}
_store_lock = threading.Lock()


def _evict_expired() -> None:
    """Remove expired entries. Called under _store_lock."""
    now = time.monotonic()
    expired = [k for k, (exp, _) in _store.items() if exp <= now]
    for k in expired:
        del _store[k]


def _local_get(key: str) -> Optional[Any]:
    with _store_lock:
        entry = _store.get(key)
        if entry is None:
            return None
        exp, val = entry
        if time.monotonic() >= exp:
            del _store[key]
            return None
        return val


def _local_set(key: str, value: Any, ttl: float) -> None:
    with _store_lock:
        if len(_store) >= _MAX_ENTRIES:
            _evict_expired()
            # If still at capacity, drop oldest quarter
            if len(_store) >= _MAX_ENTRIES:
                to_drop = sorted(_store, key=lambda k: _store[k][0])[
                    : _MAX_ENTRIES // 4
                ]
                for k in to_drop:
                    del _store[k]
        _store[key] = (time.monotonic() + ttl, value)


# ---------- optional Redis ----------

_redis_client: Optional[redis.Redis] = None
_redis_checked = False


def _get_redis() -> Optional[redis.Redis]:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Cache: Redis connected at %s", REDIS_URL)
    except Exception:
        _redis_client = None
        logger.info("Cache: Redis unavailable — using in-process cache only")
    return _redis_client


# ---------- public API ----------


def cache_key(prefix: str, *parts: Any) -> str:
    raw = f"{prefix}:" + ":".join(str(p) for p in parts)
    if len(raw) > 200:
        return prefix + ":" + hashlib.md5(raw.encode()).hexdigest()
    return raw


def cached(
    key: str,
    compute: Callable[[], Any],
    ttl: int = 60,
    redis_ttl: Optional[int] = None,
) -> Any:
    """
    Return a cached value or compute it.

    1. Check in-process cache (sub-microsecond).
    2. Check Redis (sub-millisecond on localhost).
    3. Call ``compute()``, store the result in both layers.
    """
    # L1: in-process
    hit = _local_get(key)
    if hit is not None:
        return hit

    # L2: Redis
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw is not None:
                val = json.loads(raw)
                _local_set(key, val, ttl)
                return val
        except Exception:
            pass

    # Miss — compute
    val = compute()

    _local_set(key, val, ttl)

    if r is not None:
        try:
            r.setex(key, redis_ttl or ttl, json.dumps(val, default=str))
        except Exception:
            pass

    return val


def invalidate(key: str) -> None:
    """Remove a key from both cache layers."""
    with _store_lock:
        _store.pop(key, None)
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass
