import time
import random
import requests
from email.utils import parsedate_to_datetime
import structlog
from datetime import datetime
from response import SPAPIResponse
from exceptions.sp_api_errors import RetryableError, UnauthorizedError, SPAPIError

log = structlog.get_logger()


class SPAPIClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager

    def call_api(self, store_id, method, url, payload=None):

        def request():
            token = self.auth.get_access_token(store_id)

            try:
                response = requests.request(
                    method,
                    url,
                    headers={"x-amz-access-token": token},
                    json=payload,
                    timeout=10
                )
            except requests.exceptions.Timeout:
                raise RetryableError("timeout")
            except requests.exceptions.RequestException:
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
                raise Exception("client_error")
            return SPAPIResponse(response.json()) # we can have dedicated spapi response to deal with pagination and proper abstract handling
            # return response.json() 

        return self._execute_with_retries(store_id, request)

    def _execute_with_retries(self, store_id, request):
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                return TokenRetryHandler().execute(
                    request,
                    lambda: self.auth._refresh_with_lock(store_id)
                )

            except RetryableError as e:
                if attempt == max_attempts - 1:
                    break

                delay = self._get_backoff(attempt, e)

                log.warning(
                    "spapi_retry",
                    attempt=attempt,
                    delay=delay,
                    reason=str(e),
                    store_id=store_id
                )

                time.sleep(delay)

        log.error("spapi_failed", store_id=store_id)
        raise SPAPIError("SPAPI failed after retries")

    def _get_backoff(self, attempt, error):
        # Respect Retry-After if valid
        retry_after = getattr(error, "retry_after", None)

        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                try:
                    dt = parsedate_to_datetime(retry_after)
                    return max(0, (dt - datetime.now(dt.tzinfo)).total_seconds())
                except Exception:
                    return 1.0  # safe fallback

        # Exponential backoff with scaled jitter
        base = 2 ** attempt
        return base + random.uniform(0, base * 0.25)


class TokenRetryHandler:
    def execute(self, func, refresh_callback):
        try:
            return func()
        except UnauthorizedError as e:
            if not e.is_token_error:
                raise

            refresh_callback()
            return func()