
from fastapi import FastAPI
from contextlib import asynccontextmanager
import redis
import structlog

from config import settings
from database import init_db, async_session
from auth import AuthManager
from client import SPAPIClient
from services.reports_service import ReportsService
from services.inventory_service import InventoryService
from processors.report_processor import ReportProcessor
from scheduler import InventoryScheduler
from core.logging import configure_logging

from routers import stores, inventory, scheduler

configure_logging()
log = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # BOOTSTRAP
    log.info("app_starting")
    
    # Init DB
    await init_db()
    
    # Init Redis
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        db=settings.REDIS_DB
    )
    
    # Init SP-API Stack
    auth_manager = AuthManager(redis_client, async_session)
    client = SPAPIClient(auth_manager)
    
    reports_service = ReportsService(client)
    report_processor = ReportProcessor(settings.CSV_OUTPUT_DIR)
    
    inventory_service = InventoryService(
        reports_service, 
        report_processor, 
        async_session
    )
    
    # Init Scheduler
    app.state.inventory_service = inventory_service
    app.state.scheduler = InventoryScheduler(inventory_service)
    
    # Auto-start scheduler if configured (optional)
    # app.state.scheduler.start()

    yield
    
    # SHUTDOWN
    log.info("app_stopping")
    app.state.scheduler.stop()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# Routes
app.include_router(stores.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(scheduler.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}