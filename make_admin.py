import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def make_admin():
    username = quote_plus("azanshoptalkai")
    password = quote_plus("Az%nxh2610")  # apna password yahan
    
    MONGODB_URL = f"mongodb+srv://{username}:{password}@shoptalk-cluster.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"
    
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client["shoptalk-cluster"]
    result = await db.users.update_one(
        {"phone": "03269157985"},
        {"$set": {"role": "admin"}}
    )
    print("Modified:", result.modified_count)
    client.close()

asyncio.run(make_admin())