
from fastapi import APIRouter, Request

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

@router.post("/start")
async def start_scheduler(request: Request):
    request.app.state.scheduler.start()
    return {"status": "started"}

@router.post("/stop")
async def stop_scheduler(request: Request):
    request.app.state.scheduler.stop()
    return {"status": "stopped"}

@router.get("/status")
async def get_scheduler_status(request: Request):
    return request.app.state.scheduler.get_status()
