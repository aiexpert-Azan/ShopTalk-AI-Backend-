from urllib.parse import quote_plus
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

def build_connection_string() -> str:
    """Build Cosmos DB connection string with properly URL-encoded credentials."""
    username = quote_plus(settings.COSMOS_USERNAME)
    password = quote_plus(settings.COSMOS_PASSWORD)
    host = settings.COSMOS_HOST
    return (
        f"mongodb+srv://{username}:{password}@{host}/"
        f"?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"
    )

class Database:
    client: AsyncIOMotorClient = None
    _connected: bool = False

    def connect(self):
        """Establish database connection"""
        if not self._connected:
            try:
                conn_str = build_connection_string()
                self.client = AsyncIOMotorClient(conn_str, serverSelectionTimeoutMS=5000)
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
        return self.client[settings.COSMOS_DB_NAME] if self.client else None

db = Database()

async def get_database():
    return db.get_db()
