
import time
import random
import httpx
import asyncio
from email.utils import parsedate_to_datetime
import structlog
from datetime import datetime
from response import SPAPIResponse
from exceptions.sp_api_errors import RetryableError, UnauthorizedError, SPAPIError

log = structlog.get_logger()

class SPAPIClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager

    async def call_api(self, store_id, method, url, payload=None):
        async def request():
            token = await self.auth.get_access_token(store_id)

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        url,
                        headers={"x-amz-access-token": token},
                        json=payload,
                        timeout=30
                    )
            except httpx.TimeoutException:
                raise RetryableError("timeout")
            except httpx.RequestError:
                raise RetryableError("network_error")

            if response.status_code == 401:
                raise UnauthorizedError(response)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise RetryableError("throttled", retry_after)

            if response.status_code >= 500:
                raise RetryableError("server_error")

            if response.status_code >= 400:
                log.error(
                    "spapi_client_error",
                    store_id=store_id,
                    status=response.status_code,
                    body=response.text
                )
                raise Exception(f"client_error: {response.text}")
            
            return SPAPIResponse(response.json())

        return await self._execute_with_retries(store_id, request)

    async def _execute_with_retries(self, store_id, request):
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                # Simplification: token retry logic integrated into request() or handled here
                return await request()

            except UnauthorizedError:
                # Force refresh token on 401
                await self.auth._refresh_with_lock(store_id)
                if attempt == max_attempts - 1: raise
                continue

            except RetryableError as e:
                if attempt == max_attempts - 1:
                    break

                delay = self._get_backoff(attempt, e)
                log.warning("spapi_retry", attempt=attempt, delay=delay, reason=str(e), store_id=store_id)
                await asyncio.sleep(delay)

        log.error("spapi_failed", store_id=store_id)
        raise SPAPIError("SPAPI failed after retries")

    def _get_backoff(self, attempt, error):
        retry_after = getattr(error, "retry_after", None)
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                try:
                    dt = parsedate_to_datetime(retry_after)
                    return max(0, (dt - datetime.now(dt.tzinfo)).total_seconds())
                except Exception:
                    return 1.0

        base = 2 ** attempt
        return base + random.uniform(0, base * 0.25)