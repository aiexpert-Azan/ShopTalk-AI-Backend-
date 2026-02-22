import asyncio
from app.core.database import Database
from app.core.config import settings
from app.core.security import get_password_hash
from bson import ObjectId
from datetime import datetime

async def create_test_user():
    """Create a test user in the database for authentication testing"""
    
    db_instance = Database()
    try:
        db_instance.connect()
        print("[OK] Database connected")
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        print("Please verify your CosmosDB credentials in .env file")
        return False
    
    db = db_instance.get_db()
    
    # Test credentials
    phone = "1234567890"
    password = "testpass123"
    hashed_password = get_password_hash(password)
    
    try:
        # Check if user already exists
        existing_user = await db.users.find_one({"phone": phone})
        if existing_user:
            print(f"[INFO] User with phone {phone} already exists")
            print(f"Use these credentials to login:")
            print(f"  Phone: {phone}")
            print(f"  Password: {password}")
            return True
        
        # Create new user
        user_data = {
            "_id": ObjectId(),
            "phone": phone,
            "hashed_password": hashed_password,
            "name": "Test User",
            "email": "test@shoptalk.ai",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = await db.users.insert_one(user_data)
        if result.inserted_id:
            print("[OK] Test user created successfully!")
            print(f"\nUse these credentials in Swagger UI Authorize button:")
            print(f"  Username (Phone): {phone}")
            print(f"  Password: {password}")
            return True
        else:
            print("[ERROR] Failed to insert user")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to create user: {e}")
        return False
    finally:
        try:
            db_instance.close()
        except:
            pass

if __name__ == "__main__":
    import sys
    sys.stdout.flush()
    print("[START] Creating test user...", flush=True)
    success = asyncio.run(create_test_user())
    print(f"[END] Result: {success}", flush=True)
    exit(0 if success else 1)
