"""Redis-backed metering for persistent, shared free-tier tracking.

Requires ``pip install vaulls[redis]``. Use :func:`vaulls.metering.set_meter`
to swap in this backend::

    from vaulls import set_meter
    from vaulls.metering_redis import RedisCallMeter
    import redis

    set_meter(RedisCallMeter(redis.Redis()))
"""

from __future__ import annotations

try:
    import redis as _redis_mod  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "Redis metering requires the 'redis' package. "
        "Install it with: pip install vaulls[redis]"
    ) from exc

from redis import Redis


class RedisCallMeter:
    """Redis-backed per-tool, per-caller call counter.

    Args:
        client: A ``redis.Redis`` instance.
        prefix: Key prefix in Redis. Defaults to ``"vaulls:meter"``.
        ttl: Optional TTL in seconds for counter keys. ``None`` means no expiry.
    """

    def __init__(
        self,
        client: Redis,
        prefix: str = "vaulls:meter",
        ttl: int | None = None,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, tool_name: str) -> str:
        return f"{self._prefix}:{tool_name}"

    def record_call(self, tool_name: str, caller_id: str) -> int:
        """Atomically increment and return the new count."""
        key = self._key(tool_name)
        count = self._client.hincrby(key, caller_id, 1)
        if self._ttl is not None and count == 1:
            self._client.expire(key, self._ttl)
        return count

    def get_count(self, tool_name: str, caller_id: str) -> int:
        """Return the current call count for a tool/caller pair."""
        val = self._client.hget(self._key(tool_name), caller_id)
        return int(val) if val else 0

    def is_free(self, tool_name: str, caller_id: str, free_limit: int) -> bool:
        """Check if the next call would be within the free tier."""
        if free_limit <= 0:
            return False
        return self.get_count(tool_name, caller_id) < free_limit

    def reset(self) -> None:
        """Delete all meter keys. Primarily for testing."""
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor, match=f"{self._prefix}:*", count=100)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break
