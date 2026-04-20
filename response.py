class SPAPIResponse:
    def __init__(self, raw: dict):
        self.raw = raw or {}

        # normalize common patterns
        self.next_token = (
            self.raw.get("NextToken")
            or self.raw.get("nextToken")
            or self.raw.get("next_token")
        )

        self.rate_limit = self.raw.get("RateLimit")

    def get(self, key, default=None):
        return self.raw.get(key, default)

    @property
    def payload(self):
        return self.raw