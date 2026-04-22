
import time
import random
import uuid
import json
import httpx
from cachetools import TTLCache
import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from models import Store, Creds
from security import encryption_manager
import asyncio

log = structlog.get_logger()

LOCK_TTL = 15
LOCAL_CACHE_SIZE = 1000
FAILURE_CACHE_SIZE = 1000

class TokenData:
    def __init__(self, token, expires_at):
        self.token = token
        self.expires_at = expires_at

class AuthManager:
    def __init__(self, redis_client, db_session_factory):
        self.redis = redis_client
        self.db_factory = db_session_factory
        self.local_cache = TTLCache(maxsize=LOCAL_CACHE_SIZE, ttl=3600)
        self.failure_cache = TTLCache(maxsize=FAILURE_CACHE_SIZE, ttl=10)

    async def get_access_token(self, store_id: str) -> str:
        cache_key = f"spapi:token:{store_id}"

        if store_id in self.failure_cache:
            raise Exception(f"Auth temporarily unavailable for store {store_id}")

        # 1. Redis
        try:
            token = self.redis.get(cache_key)
            if token:
                return token.decode() if isinstance(token, bytes) else token
        except Exception:
            pass

        # 2. Local cache
        token_data = self.local_cache.get(store_id)
        if token_data and not self._is_expiring(token_data):
            return token_data.token

        # 3. Refresh
        return await self._refresh_with_lock(store_id)

    async def _refresh_with_lock(self, store_id):
        lock_key = f"spapi:lock:{store_id}"
        lock_value = str(uuid.uuid4())

        if self._acquire_lock(lock_key, lock_value):
            try:
                token, expires_in = await self._fetch_from_lwa_api(store_id)
                expires_at = time.time() + expires_in

                try:
                    self.redis.setex(
                        f"spapi:token:{store_id}",
                        max(1, expires_in - 60),
                        token
                    )
                except Exception:
                    pass

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

        # Fallback if lock fails or Redis is down
        token, expires_in = await self._fetch_from_lwa_api(store_id)
        self.local_cache[store_id] = TokenData(token, time.time() + expires_in)
        return token


    async def _fetch_from_lwa_api(self, store_id):
        async with self.db_factory() as db:
            stmt = select(Store).options(joinedload(Store.creds)).where(Store.store_id == store_id)
            result = await db.execute(stmt)
            store = result.scalar_one_or_none()
            
            if not store:
                raise Exception(f"Store {store_id} not found")
            
            creds = store.creds
            client_id = encryption_manager.decrypt(creds.lwa_client_id)
            client_secret = encryption_manager.decrypt(creds.lwa_client_secret)
            refresh_token = encryption_manager.decrypt(creds.refresh_token)

        # Real LWA Request via httpx
        url = "https://api.amazon.com/auth/o2/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10)
            if response.status_code != 200:
                log.error("lwa_auth_error", status=response.status_code, body=response.text)
                raise Exception(f"LWA Error: {response.text}")
                
            data = response.json()
            return data["access_token"], data["expires_in"]


    async def _wait_for_token_or_fallback(self, store_id):
        cache_key = f"spapi:token:{store_id}"
        for attempt in range(5):
            await asyncio.sleep(0.2 + random.uniform(0, 0.3))
            try:
                token = self.redis.get(cache_key)
                if token:
                    return token.decode() if isinstance(token, bytes) else token
            except Exception:
                pass
        return (await self._fetch_from_lwa_api(store_id))[0]

    def _acquire_lock(self, key, value):
        try:
            return self.redis.set(key, value, nx=True, ex=LOCK_TTL)
        except Exception:
            return False

    def _release_lock(self, key, value):
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

    def _is_expiring(self, token_data):
        return (token_data.expires_at - time.time()) < 60
