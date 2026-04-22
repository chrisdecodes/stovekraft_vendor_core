
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from sqlalchemy import select
from models import SyncState

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.post("/sync")
async def trigger_sync(request: Request):
    inventory_service = request.app.state.inventory_service
    results = await inventory_service.run_sync_for_all_stores()
    return {"results": results}

@router.post("/sync/{store_id}")
async def trigger_store_sync(store_id: str, request: Request):
    inventory_service = request.app.state.inventory_service
    result = await inventory_service.sync_store_inventory(store_id)
    return result

@router.get("/status")
async def get_sync_status(db: AsyncSession = Depends(get_db)):
    stmt = select(SyncState)
    result = await db.execute(stmt)
    return result.scalars().all()
