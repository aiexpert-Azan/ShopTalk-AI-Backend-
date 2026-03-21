import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from app.core.database import db
from app.core.security import get_password_hash

async def set_admin():
    # Connect to database
    database = db.get_db()
    
    phone = "+923269157985"   # ← apna exact phone number
    password = "Az@nxh2610s"  # ← apna password
    
    hashed = get_password_hash(password)
    
    result = await database.users.update_one(
        {"$or": [
            {"phone": phone},
            {"phone": "0" + phone[3:]}  # 03XXXXXXXXX format bhi check
        ]},
        {"$set": {
            "hashed_password": hashed,
            "role": "admin"
        }}
    )
    
    print(f"Documents modified: {result.modified_count}")
    if result.modified_count == 0:
        print("WARNING: No user found! Check phone number.")
    else:
        print("Admin set successfully!")

asyncio.run(set_admin())