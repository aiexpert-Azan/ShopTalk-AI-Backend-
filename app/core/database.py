
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


# Simple MongoDB Atlas connection using MONGODB_URL
class Database:
    client: AsyncIOMotorClient = None
    _connected: bool = False

    def connect(self):
        if not self._connected:
            try:
                self.client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
                self._connected = True
            except Exception as e:
                print(f"[WARNING] Database connection failed: {e}")
                self._connected = False

    def close(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self._connected = False

    def get_db(self):
        if not self.client:
            self.connect()
        # Extract DB name from URL or use a default
        db_name = settings.MONGODB_URL.rsplit('/', 1)[-1].split('?')[0] if settings.MONGODB_URL else None
        return self.client[db_name] if self.client and db_name else None

db = Database()

async def get_database():
    return db.get_db()
