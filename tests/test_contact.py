import os

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("FACEBOOK_APP_ID", "test-facebook-app-id")
os.environ.setdefault("FACEBOOK_APP_SECRET", "test-facebook-app-secret")
os.environ.setdefault("FACEBOOK_REDIRECT_URI", "https://example.com/callback")

from fastapi.testclient import TestClient

from app.main import app
from app.routers import contact as contact_router
from app.services.contact_service import ContactEmailDeliveryError, ContactEmailProviderUnavailable


client = TestClient(app)


class DummyEmailService:
    def __init__(self, exception=None):
        self.exception = exception
        self.calls = []

    async def send_submission(self, submission, *, ip_address=None, user_agent=None):
        self.calls.append(
            {
                "submission": submission,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )
        if self.exception:
            raise self.exception


def test_contact_submission_succeeds(monkeypatch):
    service = DummyEmailService()
    monkeypatch.setattr(contact_router, "contact_email_service", service)

    response = client.post(
        "/api/contact",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "message": "I need help with my store setup.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Message sent successfully"}
    assert len(service.calls) == 1


def test_contact_submission_validation_failure(monkeypatch):
    service = DummyEmailService()
    monkeypatch.setattr(contact_router, "contact_email_service", service)

    response = client.post(
        "/api/contact",
        json={
            "name": "",
            "email": "not-an-email",
            "message": "short",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Validation failed"
    assert "errors" in body
    assert service.calls == []


def test_contact_submission_provider_failure(monkeypatch):
    service = DummyEmailService(exception=ContactEmailDeliveryError("boom"))
    monkeypatch.setattr(contact_router, "contact_email_service", service)

    response = client.post(
        "/api/contact",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "message": "I need help with my store setup.",
        },
    )

    assert response.status_code == 502
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Unable to send your message right now. Please try again later."


def test_contact_submission_unavailable_returns_503(monkeypatch):
    service = DummyEmailService(exception=ContactEmailProviderUnavailable("down"))
    monkeypatch.setattr(contact_router, "contact_email_service", service)

    response = client.post(
        "/api/contact",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "message": "I need help with my store setup.",
        },
    )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Contact form is temporarily unavailable. Please try again later."
