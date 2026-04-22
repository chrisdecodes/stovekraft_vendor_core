
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import settings
import structlog

log = structlog.get_logger()

class InventoryScheduler:
    def __init__(self, inventory_service):
        self.scheduler = AsyncIOScheduler()
        self.inventory_service = inventory_service
        self.job_id = "inventory_sync_job"

    def start(self):
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.inventory_service.run_sync_for_all_stores,
                trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
                id=self.job_id,
                replace_existing=True
            )
            self.scheduler.start()
            log.info("scheduler_started", interval_hours=settings.SCHEDULER_INTERVAL_HOURS)

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            log.info("scheduler_stopped")

    def get_status(self):
        return {
            "running": self.scheduler.running,
            "jobs": [
                {
                    "id": job.id,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else None
                }
                for job in self.scheduler.get_jobs()
            ]
        }
