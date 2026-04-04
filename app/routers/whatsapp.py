from datetime import datetime
from typing import Optional

import httpx
import logging
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.database import db
from app.core.deps import get_current_user
from app.models.user import UserInDB

logger = logging.getLogger(__name__)
router = APIRouter()


class WhatsAppCredentials(BaseModel):
    app_id: Optional[str] = None
    waba_id: str = Field(..., min_length=1)
    phone_number_id: str = Field(..., min_length=1)
    access_token: str = Field(..., min_length=1)
    shop_id: Optional[str] = None


class WhatsAppCredentialsResponse(BaseModel):
    message: str
    shop_id: str


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    app_id: Optional[str] = None
    verified: bool = False
    message: str


@router.post("/save-credentials", response_model=WhatsAppCredentialsResponse)
async def save_whatsapp_credentials(
    creds: WhatsAppCredentials,
    current_user: UserInDB = Depends(get_current_user)
):
    """Save WhatsApp Business API credentials for a shop."""
    try:
        shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})

        if not shop:
            shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})

        if not shop and creds.shop_id:
            try:
                shop = await db.get_db().shops.find_one({"_id": ObjectId(creds.shop_id)})
            except Exception:
                shop = None

        if not shop:
            new_shop = {
                "ownerPhone": current_user.phone,
                "userId": str(current_user.id),
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            result = await db.get_db().shops.insert_one(new_shop)
            shop = {"_id": result.inserted_id}
            logger.info("New shop created for user %s", current_user.phone)

        shop_id = str(shop["_id"])

        is_valid = await verify_whatsapp_credentials(creds.access_token, creds.phone_number_id)

        update_data = {
            "whatsapp_app_id": creds.app_id or "",
            "whatsapp_waba_id": creds.waba_id,
            "whatsapp_phone_number_id": creds.phone_number_id,
            "whatsapp_access_token": creds.access_token,
            "whatsapp_connected": is_valid,
            "whatsapp_connected_at": datetime.utcnow() if is_valid else None,
            "updatedAt": datetime.utcnow(),
        }

        await db.get_db().shops.update_one({"_id": shop["_id"]}, {"$set": update_data})

        logger.info("WhatsApp credentials saved for shop %s, valid=%s", shop_id, is_valid)

        return WhatsAppCredentialsResponse(
            message="WhatsApp credentials saved successfully" if is_valid else "Credentials saved but verification failed",
            shop_id=shop_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error saving WhatsApp credentials: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {str(e)}",
        )


@router.get("/status/{shop_id}", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Check WhatsApp connection status for a shop."""
    try:
        shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})

        if not shop:
            try:
                shop = await db.get_db().shops.find_one({"_id": ObjectId(shop_id)})
            except Exception:
                shop = None

        if not shop:
            return WhatsAppStatusResponse(
                connected=False,
                verified=False,
                message="Shop not found",
            )

        has_credentials = bool(
            shop.get("whatsapp_access_token") and shop.get("whatsapp_phone_number_id")
        )

        if has_credentials:
            is_valid = await verify_whatsapp_credentials(
                shop.get("whatsapp_access_token"),
                shop.get("whatsapp_phone_number_id"),
            )

            return WhatsAppStatusResponse(
                connected=is_valid,
                phone_number_id=shop.get("whatsapp_phone_number_id"),
                waba_id=shop.get("whatsapp_waba_id"),
                app_id=shop.get("whatsapp_app_id"),
                verified=is_valid,
                message="WhatsApp Business API connected" if is_valid else "Credentials invalid or expired",
            )

        return WhatsAppStatusResponse(
            connected=False,
            verified=False,
            message="WhatsApp not configured for this shop",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error checking WhatsApp status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check status: {str(e)}",
        )


@router.delete("/disconnect/{shop_id}")
async def disconnect_whatsapp(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Disconnect WhatsApp from a shop."""
    try:
        shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})

        if not shop:
            try:
                shop = await db.get_db().shops.find_one({"_id": ObjectId(shop_id)})
            except Exception:
                shop = None

        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found",
            )

        await db.get_db().shops.update_one(
            {"_id": shop["_id"]},
            {"$unset": {
                "whatsapp_app_id": "",
                "whatsapp_waba_id": "",
                "whatsapp_phone_number_id": "",
                "whatsapp_access_token": "",
                "whatsapp_connected": "",
                "whatsapp_connected_at": "",
                "whatsapp_setup_method": "",
            }},
        )

        logger.info("WhatsApp disconnected for shop %s", shop_id)
        return {"message": "WhatsApp disconnected successfully", "shop_id": shop_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error disconnecting WhatsApp: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect: {str(e)}",
        )


async def verify_whatsapp_credentials(access_token: str, phone_number_id: str) -> bool:
    """Verify WhatsApp credentials by making a test API call."""
    try:
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10)
            return resp.status_code == 200

    except Exception as e:
        logger.warning("WhatsApp credential verification failed: %s", e)
        return False