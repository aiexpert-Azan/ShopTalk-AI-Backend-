import json
import logging
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from app.core.limiter import limiter
from app.models.contact import ContactSubmission
from app.services.contact_service import (
    ContactEmailDeliveryError,
    ContactEmailProviderUnavailable,
    contact_email_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_CONTACT_REQUEST_BYTES = 16 * 1024


def _failure_response(message: str, http_status: int, *, errors: list[Any] | None = None) -> JSONResponse:
    payload = {"success": False, "message": message}
    if errors:
        payload["errors"] = errors
    return JSONResponse(status_code=http_status, content=payload)


@router.post("")
@router.post("/")
@limiter.limit("5/minute")
async def submit_contact(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_CONTACT_REQUEST_BYTES:
                logger.warning("Rejected oversized contact request: content_length=%s", content_length)
                return _failure_response("Request too large", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        except ValueError:
            logger.warning("Rejected contact request with invalid content_length header")
            return _failure_response("Invalid request size", status.HTTP_400_BAD_REQUEST)

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        logger.warning("Rejected contact request with invalid JSON")
        return _failure_response("Invalid JSON payload", status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.warning("Rejected contact request body that could not be parsed")
        return _failure_response("Unable to read request body", status.HTTP_400_BAD_REQUEST)

    try:
        submission = ContactSubmission.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Contact validation failed: fields=%s", [error.get("loc") for error in exc.errors()])
        return _failure_response("Validation failed", status.HTTP_422_UNPROCESSABLE_ENTITY, errors=exc.errors())

    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        await contact_email_service.send_submission(
            submission,
            ip_address=client_host,
            user_agent=user_agent,
        )
    except ContactEmailProviderUnavailable:
        logger.warning(
            "Contact email provider unavailable: email_domain=%s ip=%s",
            submission.email.split("@")[-1],
            client_host,
        )
        return _failure_response(
            "Contact form is temporarily unavailable. Please try again later.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except ContactEmailDeliveryError:
        logger.error(
            "Contact email delivery failed: email_domain=%s ip=%s",
            submission.email.split("@")[-1],
            client_host,
        )
        return _failure_response(
            "Unable to send your message right now. Please try again later.",
            status.HTTP_502_BAD_GATEWAY,
        )
    except Exception:
        logger.exception(
            "Unexpected contact submission failure: email_domain=%s ip=%s",
            submission.email.split("@")[-1],
            client_host,
        )
        return _failure_response(
            "Unable to process your message right now.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "message": "Message sent successfully"},
    )
