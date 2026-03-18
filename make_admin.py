import asyncio
from app.core.database import db
from app.core.security import get_password_hash

async def set_admin():
    await db.connect()
    phone = "+923269157985"  # ← apna number daalo
    password = "Az@nxh2610s"  # ← apna password daalo
    
    hashed = get_password_hash(password)
    result = await db.get_db().users.update_one(
        {"phone": phone},
        {"$set": {
            "hashed_password": hashed,
            "role": "admin"
        }}
    )
    print(f"Modified: {result.modified_count}")
    print("Done!")

asyncio.run(set_admin())