
import asyncio
import time
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from models import Store, SyncState, Marketplace
from config import settings

log = structlog.get_logger()

class InventoryService:
    def __init__(self, reports_service, report_processor, db_factory):
        self.reports_service = reports_service
        self.processor = report_processor
        self.db_factory = db_factory

    async def run_sync_for_all_stores(self):
        """Iterates through all active stores and triggers sync."""
        async with self.db_factory() as db:
            stmt = select(Store).where(Store.deleted_at == None)
            result = await db.execute(stmt)
            stores = result.scalars().all()

        log.info("starting_bulk_inventory_sync", store_count=len(stores))
        
        tasks = [self.sync_store_inventory(store.store_id) for store in stores]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results

    async def sync_store_inventory(self, store_id: str):
        """Orchestrates full report flow for a single store."""
        start_time = time.time()
        log.info("sync_start", store_id=store_id)

        try:
            async with self.db_factory() as db:
                # 1. Update status to RUNNING
                await self._update_sync_state(db, store_id, "RUNNING")
                
                # Get marketplace for store
                stmt = (
                    select(Store)
                    .options(joinedload(Store.marketplace))
                    .where(Store.store_id == store_id)
                )
                result = await db.execute(stmt)
                store = result.scalar_one()
                marketplace_id = store.marketplace.amazon_marketplace_id
                region = store.marketplace.region

            # 2. Build and Create Report
            report_type = settings.DEFAULT_REPORT_TYPE
            body = self._build_report_body(report_type, marketplace_id)
            
            res = await self.reports_service.create_report(store_id, region, body)
            report_id = res.get("reportId")
            log.info("report_created", store_id=store_id, report_id=report_id)

            # 3. Poll Status
            document_id, last_status = await self._poll_report_status(store_id, region, report_id)
            
            # 4. Get Document Metadata
            doc_res = await self.reports_service.get_document(store_id, region, document_id)
            
            # 5. Download & Save
            content = self.processor.download_report(doc_res.raw)
            raw_path = self.processor.save_raw_report(content, store_id, report_type)
            
            if last_status != "DONE":
                # It's an error document, save raw and stop
                path = self.processor.save_raw_report(content, store_id, report_type, is_error=True)
                raise Exception(f"Report failed with status {last_status}. Error details saved to: {path}")

            # Normal flow
            rows = self.processor.parse_report(content, report_type)
            csv_path = self.processor.save_to_csv(rows, store_id, report_type)

            duration = time.time() - start_time
            
            async with self.db_factory() as db:
                await self._update_sync_state(
                    db, store_id, "IDLE", 
                    checkpoint=datetime.now(timezone.utc),
                    last_report_id=report_id
                )

            log.info("sync_complete", store_id=store_id, duration=duration, row_count=len(rows))
            return {
                "status": "success",
                "store_id": store_id,
                "report_id": report_id,
                "csv_path": csv_path,
                "rows": len(rows)
            }

        except Exception as e:
            log.error("sync_failed", store_id=store_id, error=str(e))
            async with self.db_factory() as db:
                await self._update_sync_state(db, store_id, "ERROR", error_msg=str(e))
            return {"status": "error", "store_id": store_id, "message": str(e)}

    async def _poll_report_status(self, store_id, region, report_id, timeout=1800):
        """Polls until report is DONE, FATAL, or CANCELLED."""
        start = time.time()
        wait = 30
        
        while time.time() - start < timeout:
            res = await self.reports_service.get_report(store_id, region, report_id)
            status = res.get("processingStatus")
            
            if status == "DONE":
                return res.get("reportDocumentId"), status
            
            if status in ("FATAL", "CANCELLED"):
                doc_id = res.get("reportDocumentId")
                if doc_id:
                    log.warning("report_failed_but_has_id", store_id=store_id, report_id=report_id, status=status, doc_id=doc_id)
                    return doc_id, status
                raise Exception(f"Report {report_id} failed with status {status} and no error document was provided.")
            
            log.info("polling_report", store_id=store_id, report_id=report_id, status=status)
            await asyncio.sleep(wait)
            wait = min(wait * 2, 300) # Exp backoff
            
        raise TimeoutError(f"Report {report_id} timed out")

    async def _update_sync_state(self, db, store_id, status, checkpoint=None, last_report_id=None, error_msg=None):
        stmt = select(SyncState).where(SyncState.store_id == store_id, SyncState.job_name == "inventory_sync")
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()
        
        if not state:
            state = SyncState(store_id=store_id, job_name="inventory_sync")
            db.add(state)
        
        state.status = status
        if checkpoint: state.last_checkpoint = checkpoint
        if last_report_id: state.last_report_id = last_report_id
        if error_msg: state.last_error = error_msg
        
        await db.commit()

    def _build_report_body(self, report_type: str, marketplace_id: str) -> dict:
        """Constructs the report request body with type-specific options."""
        body = {
            "reportType": report_type,
            "marketplaceIds": [marketplace_id]
        }

        # Configuration for specific report types
        configs = {
            "GET_VENDOR_SALES_REPORT": {
                "reportOptions": {
                    "reportPeriod": "DAY",
                    "distributorView": "MANUFACTURING",
                    "sellingProgram": "RETAIL"
                },
                "requires_time_range": True
            },
            "GET_VENDOR_INVENTORY_REPORT": {
                "reportOptions": {
                    "reportPeriod": "DAY",
                    "distributorView": "MANUFACTURING",
                    "sellingProgram": "RETAIL"
                },
                "requires_time_range": True
            },
            "GET_VENDOR_TRAFFIC_REPORT": {
                "reportOptions": {
                    "reportPeriod": "DAY"
                },
                "requires_time_range": True
            },
            "GET_VENDOR_FORECASTING_REPORT": {
                "reportOptions": {
                    "sellingProgram": "RETAIL"
                }
            },
            "GET_VENDOR_REAL_TIME_INVENTORY_REPORT": {
                "reportOptions": {
                    "sellingProgram": "RETAIL"
                },
                "requires_time_range": True,
                "short_window": True
            },
            "GET_VENDOR_REAL_TIME_SALES_REPORT": {
                "reportOptions": {
                    "sellingProgram": "RETAIL"
                },
                "requires_time_range": True
            }
        }

        if report_type in configs:
            config = configs[report_type]
            if "reportOptions" in config:
                body["reportOptions"] = config["reportOptions"]
            
            if config.get("requires_time_range"):
                # Real-time reports must have a window < 24 hours
                if config.get("short_window"):
                    end = datetime.now(timezone.utc)
                    start = end - timedelta(hours=23)
                else:
                    # Default to last 7 days with lag for stability
                    end = datetime.now(timezone.utc) - timedelta(days=2)
                    start = end - timedelta(days=7)
                
                body["dataStartTime"] = start.isoformat()
                body["dataEndTime"] = end.isoformat()
        
        return body
