import os

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_embedded_signup_route_is_not_available():
    response = client.post("/api/whatsapp/embedded-signup", json={"code": "abc"})

    assert response.status_code == 404