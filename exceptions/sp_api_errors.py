class SPAPIError(Exception):
    """Base class for all SP-API related errors"""
    pass

class RetryableError(SPAPIError):
    def __init__(self, reason: str, retry_after=None):
        self.reason = reason
        self.retry_after = retry_after
        super().__init__(f"Retryable error: {reason}")

class UnauthorizedError(SPAPIError):
    def __init__(self, response=None):
        self.response = response

        # token vs other auth failures
        self.is_token_error = True  # default assumption

        try:
            if response is not None:
                body = response.json()
                if "invalid_signature" in str(body):
                    self.is_token_error = False
        except Exception:
            pass

        super().__init__("Unauthorized access")

class ClientError(SPAPIError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Client error {status_code}: {message}")