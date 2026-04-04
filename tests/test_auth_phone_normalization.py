import os

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.main import app
from app.routers import auth as auth_router


client = TestClient(app)


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUsersCollection:
    def __init__(self):
        self.records = []

    async def find_one(self, query):
        phone = query.get("phone")
        for record in self.records:
            if record.get("phone") == phone:
                return record
        return None

    async def insert_one(self, document):
        stored = dict(document)
        stored.setdefault("_id", str(len(self.records) + 1))
        self.records.append(stored)
        return FakeInsertResult(stored["_id"])


class FakeDB:
    def __init__(self):
        self.users = FakeUsersCollection()


def test_signup_normalizes_phone_format(monkeypatch):
    fake_db = FakeDB()
    monkeypatch.setattr(auth_router.db, "get_db", lambda: fake_db)

    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Ali",
            "phone": "03 00-123(4567)",
            "email": "ali@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    assert fake_db.users.records[0]["phone"] == "+923001234567"


def test_login_accepts_local_phone_format(monkeypatch):
    fake_db = FakeDB()
    fake_db.users.records.append(
        {
            "_id": "1",
            "phone": "+923001234567",
            "name": "Ali",
            "email": "ali@example.com",
            "hashed_password": get_password_hash("secret123"),
            "plan": "free",
            "is_active": True,
            "phone_verified": True,
        }
    )
    monkeypatch.setattr(auth_router.db, "get_db", lambda: fake_db)

    response = client.post(
        "/api/auth/login",
        json={
            "phone": "0300 123-4567",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"


def test_login_rejects_wrong_password(monkeypatch):
    fake_db = FakeDB()
    fake_db.users.records.append(
        {
            "_id": "1",
            "phone": "+923001234567",
            "name": "Ali",
            "email": "ali@example.com",
            "hashed_password": get_password_hash("secret123"),
            "plan": "free",
            "is_active": True,
            "phone_verified": True,
        }
    )
    monkeypatch.setattr(auth_router.db, "get_db", lambda: fake_db)

    response = client.post(
        "/api/auth/login",
        json={
            "phone": "+92 300 123 4567",
            "password": "wrongpass",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect phone or password"