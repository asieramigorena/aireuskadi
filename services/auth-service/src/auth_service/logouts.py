"""The tokens of the logouts, which no longer open anything, as (account id, expiry).

They are kept in memory and, when there is one, in Redis: a restart of the service forgets the
memory, and without Redis the old token of a logout would open again until it expires (8 hours).
Each one is kept only until its token would have expired anyway, so they never pile up. If Redis
does not answer, the memory still counts. Security fix by Claude (audit 2026-11-26).
"""

import logging
import time

import redis

logger = logging.getLogger("auth_service")

PREFIX = "aireuskadi:logout:v1:"


class Logouts:
    def __init__(self, store=None, clock=time.time):
        # `store` is a client of Redis (a fake in the tests), or None: memory only.
        self.store = store
        self.clock = clock
        self.memory: set[tuple[int, int]] = set()

    def add(self, account: int, expiry: int) -> None:
        now = self.clock()
        self.memory = {old for old in self.memory if old[1] >= now}
        self.memory.add((account, expiry))
        if self.store is not None:
            try:
                self.store.set(f"{PREFIX}{account}:{expiry}", "1", exat=expiry)
            except redis.RedisError as error:
                logger.warning("logout not kept in redis", extra={"error": type(error).__name__})

    def __contains__(self, token: tuple[int, int]) -> bool:
        if token in self.memory:
            return True
        if self.store is None:
            return False
        account, expiry = token
        try:
            return self.store.exists(f"{PREFIX}{account}:{expiry}") == 1
        except redis.RedisError as error:
            logger.warning("logouts not read from redis", extra={"error": type(error).__name__})
            return False
