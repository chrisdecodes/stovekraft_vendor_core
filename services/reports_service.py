class ReportsService:
    def __init__(self, client):
        self.client = client
        self.endpoints = {
            "NA": "https://sellingpartnerapi-na.amazon.com",
            "EU": "https://sellingpartnerapi-eu.amazon.com",
            "FE": "https://sellingpartnerapi-fe.amazon.com"
        }

    def _get_url(self, region, path):
        base = self.endpoints.get(region, self.endpoints["NA"])
        return f"{base}{path}"

    async def create_report(self, store_id, region, body):
        return await self.client.call_api(
            store_id,
            "POST",
            self._get_url(region, "/reports/2021-06-30/reports"),
            payload=body
        )

    async def get_report(self, store_id, region, report_id):
        return await self.client.call_api(
            store_id,
            "GET",
            self._get_url(region, f"/reports/2021-06-30/reports/{report_id}")
        )

    async def get_document(self, store_id, region, doc_id):
        return await self.client.call_api(
            store_id,
            "GET",
            self._get_url(region, f"/reports/2021-06-30/documents/{doc_id}")
        )