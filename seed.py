
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, init_db
from models import Marketplace

MARKETPLACES = [
    {"marketplace_id": "US", "marketplace_name": "United States", "amazon_marketplace_id": "ATVPDKIKX0DER", "region": "NA"},
    {"marketplace_id": "CA", "marketplace_name": "Canada", "amazon_marketplace_id": "A2EUQ1WTGCTBG2", "region": "NA"},
    {"marketplace_id": "MX", "marketplace_name": "Mexico", "amazon_marketplace_id": "A1AM78C64UM0Y8", "region": "NA"},
    {"marketplace_id": "UK", "marketplace_name": "United Kingdom", "amazon_marketplace_id": "A1F83G8C2ARO7P", "region": "EU"},
    {"marketplace_id": "DE", "marketplace_name": "Germany", "amazon_marketplace_id": "A1PA6795UKMFR9", "region": "EU"},
    {"marketplace_id": "AU", "marketplace_name": "Australia", "amazon_marketplace_id": "A39IBJ37TRP1C6", "region": "FE"},
]

async def seed():
    print("Initializing Database...")
    await init_db()
    
    async with async_session() as db:
        for m_data in MARKETPLACES:
            m = await db.get(Marketplace, m_data["marketplace_id"])
            if not m:
                print(f"Adding Marketplace: {m_data['marketplace_id']}")
                db.add(Marketplace(**m_data))
        
        await db.commit()
    print("Seed complete.")

if __name__ == "__main__":
    asyncio.run(seed())
