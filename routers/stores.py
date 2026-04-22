
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Store, Creds, Marketplace
from security import encryption_manager
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/stores", tags=["Stores"])

class CredsCreate(BaseModel):
    lwa_client_id: str
    lwa_client_secret: str
    refresh_token: str

class StoreCreate(BaseModel):
    store_name: str
    marketplace_id: str
    creds: CredsCreate

@router.post("/")
async def create_store(data: StoreCreate, db: AsyncSession = Depends(get_db)):
    # 1. Check if marketplace exists
    stmt = select(Marketplace).where(Marketplace.marketplace_id == data.marketplace_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invalid marketplace_id")

    # 2. Create Creds
    creds = Creds(
        lwa_client_id=encryption_manager.encrypt(data.creds.lwa_client_id),
        lwa_client_secret=encryption_manager.encrypt(data.creds.lwa_client_secret),
        refresh_token=encryption_manager.encrypt(data.creds.refresh_token)
    )
    db.add(creds)
    await db.flush()

    # 3. Create Store
    store = Store(
        store_name=data.store_name,
        marketplace_id=data.marketplace_id,
        cred_id=creds.cred_id
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    
    return {"store_id": store.store_id}

@router.get("/")
async def list_stores(db: AsyncSession = Depends(get_db)):
    stmt = select(Store).where(Store.deleted_at == None)
    result = await db.execute(stmt)
    return result.scalars().all()
