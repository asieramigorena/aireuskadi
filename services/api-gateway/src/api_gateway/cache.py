"""The cache of the gateway: good answers of the services, kept in Redis for a while.

`ask` (routes.py) looks here before asking a service, and keeps here what the service answered.
If Redis cannot be reached the gateway asks the service, as if there were no cache, and leaves Redis
alone for 30 seconds: a Redis that does not answer costs half a second per question.
"""

import logging
import secrets
import time

logger = logging.getLogger("api_gateway")

PAUSE_AFTER_FAILURE = 30  # seconds


class Cache:
    def __init__(self, redis, prefix: str | None = None):
        self.redis = redis
        # Each start of the gateway has keys of its own: a new version can change what an answer
        # looks like, and what an older one kept must not be served. The old keys expire. The texts
        # of the language model have a fixed prefix instead (insight.py): they survive a deployment.
        self.prefix = prefix or f"aireuskadi:gateway:{secrets.token_hex(4)}:"
        self.paused_until = 0.0

    async def get(self, key: str) -> bytes | None:
        if time.monotonic() < self.paused_until:
            return None
        try:
            return await self.redis.get(self.prefix + key)
        except Exception as error:  # noqa: BLE001 - without a cache the gateway still answers
            self.failed(error)
            return None

    async def set(self, key: str, body: bytes, seconds: int) -> None:
        if time.monotonic() < self.paused_until:
            return
        try:
            await self.redis.set(self.prefix + key, body, ex=seconds)
        except Exception as error:  # noqa: BLE001 - without a cache the gateway still answers
            self.failed(error)

    def failed(self, error: Exception) -> None:
        self.paused_until = time.monotonic() + PAUSE_AFTER_FAILURE
        # Only the class of the error: its message says where Redis is.
        logger.warning("The cache failed", extra={"error": type(error).__name__})
