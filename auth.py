import time
import random
import uuid
from cachetools import TTLCache
import structlog

log = structlog.get_logger()

LOCK_TTL = 15          # must be > worst-case LWA latency
LOCAL_CACHE_SIZE = 1000
FAILURE_CACHE_SIZE = 1000

class TokenData:
    def __init__(self, token, expires_at):
        self.token = token
        self.expires_at = expires_at


class AuthManager:
    def __init__(self, redis_client, lwa_client):
        self.redis = redis_client
        self.lwa = lwa_client

        # ✅ bounded + TTL
        self.local_cache = TTLCache(maxsize=LOCAL_CACHE_SIZE, ttl=3600)
        self.failure_cache = TTLCache(maxsize=FAILURE_CACHE_SIZE, ttl=10)

    def get_access_token(self, store_id: str) -> str:
        cache_key = f"spapi:token:{store_id}"

        # 0. Failure cooldown
        if store_id in self.failure_cache:
            raise Exception("Auth temporarily unavailable")

        # 1. Redis (source of truth)
        try:
            token = self.redis.get(cache_key)
            if token:
                return token
        except Exception:
            pass

        # 2. Local cache
        token_data = self.local_cache.get(store_id)
        if token_data and not self._is_expiring(token_data):
            return token_data.token

        # 3. Refresh
        return self._refresh_with_lock(store_id)

    def _refresh_with_lock(self, store_id):
        lock_key = f"spapi:lock:{store_id}"
        lock_value = str(uuid.uuid4())

        if self._acquire_lock(lock_key, lock_value):
            try:
                token, expires_in = self._fetch_from_lwa(store_id)

                expires_at = time.time() + expires_in

                # Redis write (slightly shorter TTL)
                try:
                    self.redis.setex(
                        f"spapi:token:{store_id}",
                        max(1, expires_in - 60),
                        token
                    )
                except Exception:
                    pass

                # Local cache
                self.local_cache[store_id] = TokenData(token, expires_at)

                self.failure_cache.pop(store_id, None)

                log.info("token_refresh_success", store_id=store_id)
                return token

            except Exception as e:
                self.failure_cache[store_id] = True
                log.error("token_refresh_failed", store_id=store_id, error=str(e))
                raise

            finally:
                self._release_lock(lock_key, lock_value)

        # ❗ Someone else is refreshing
        return self._wait_for_token_or_fallback(store_id)

    def _wait_for_token_or_fallback(self, store_id):
        cache_key = f"spapi:token:{store_id}"

        for attempt in range(3):
            time.sleep(0.1 + random.uniform(0, 0.2))  # ✅ jitter

            try:
                token = self.redis.get(cache_key)
                if token:
                    return token
            except Exception:
                pass

        # ⚠️ last resort — but safer
        return self._fetch_direct(store_id)

    def _fetch_from_lwa(self, store_id):
        creds = self._get_creds(store_id)

        resp = self.lwa.refresh_access_token(...)

        if "error" in resp:
            if resp["error"] == "invalid_grant":
                # ❗ permanent failure → don't retry loop
                raise Exception("Invalid credentials")

            raise Exception("LWA error")

        return resp["access_token"], resp["expires_in"]

    def _fetch_direct(self, store_id):
        """
        Last-resort fallback.
        Still updates cache to reduce blast radius.
        """
        token, expires_in = self._fetch_from_lwa(store_id)

        expires_at = time.time() + expires_in
        self.local_cache[store_id] = TokenData(token, expires_at)

        return token

    # ---------- Locking ----------
    def _acquire_lock(self, key, value):
        try:
            return self.redis.set(key, value, nx=True, ex=LOCK_TTL)
        except Exception:
            return False

    def _release_lock(self, key, value):
        """
        ✅ Safer lock release using Lua (atomic check+delete)
        Prevents deleting someone else's lock
        """
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            self.redis.eval(script, 1, key, value)
        except Exception:
            pass

    # ---------- Expiry ----------
    def _is_expiring(self, token_data):
        return (token_data.expires_at - time.time()) < 60