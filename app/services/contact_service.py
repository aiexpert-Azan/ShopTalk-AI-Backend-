import asyncio
import logging
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, Mail, To

from app.core.config import settings
from app.models.contact import ContactSubmission

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "support@shoptalkai.app"
MAX_SUBJECT_LENGTH = 80


class ContactEmailProviderUnavailable(Exception):
    pass


class ContactEmailDeliveryError(Exception):
    pass


def _sanitize_header_value(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _classify_sendgrid_failure(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {502, 503, 504}:
        return True
    error_name = error.__class__.__name__.lower()
    return any(keyword in error_name for keyword in ("timeout", "connection", "unavailable"))


class ContactEmailService:
    def __init__(self, api_key: Optional[str] = None, from_email: Optional[str] = None):
        self.api_key = api_key or settings.SENDGRID_API_KEY
        self.from_email = from_email or settings.SENDGRID_FROM_EMAIL or settings.FROM_EMAIL

    async def send_submission(
        self,
        submission: ContactSubmission,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        if not self.api_key:
            raise ContactEmailProviderUnavailable("Email provider is not configured")
        if not self.from_email:
            raise ContactEmailProviderUnavailable("Email sender is not configured")

        sender_name = _sanitize_header_value(submission.name)
        sender_email = _sanitize_header_value(str(submission.email))
        subject = _truncate(f"ShopTalk AI contact: {sender_name}", MAX_SUBJECT_LENGTH)

        lines = [
            "New contact form submission",
            "",
            f"Name: {sender_name}",
            f"Email: {sender_email}",
        ]

        if ip_address:
            lines.append(f"IP Address: {ip_address}")
        if user_agent:
            lines.append(f"User Agent: {_sanitize_header_value(user_agent)}")

        lines.extend([
            "",
            "Message:",
            submission.message,
        ])

        message = Mail(
            from_email=Email(self.from_email),
            to_emails=To(SUPPORT_EMAIL),
            subject=subject,
            plain_text_content="\n".join(lines),
            reply_to=Email(sender_email, sender_name),
        )

        client = SendGridAPIClient(self.api_key)

        try:
            response = await asyncio.to_thread(client.send, message)
        except Exception as error:
            if _classify_sendgrid_failure(error):
                raise ContactEmailProviderUnavailable("Email provider is temporarily unavailable") from error
            raise ContactEmailDeliveryError("Failed to send contact message") from error

        status_code = getattr(response, "status_code", 0) or 0
        if status_code >= 500:
            raise ContactEmailProviderUnavailable("Email provider is temporarily unavailable")
        if status_code >= 300:
            raise ContactEmailDeliveryError("Failed to send contact message")

        logger.info("Contact message delivered to support inbox")


contact_email_service = ContactEmailService()
