from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.core.deps import get_current_user
from app.core.database import db
from app.core.config import settings
from app.models.user import UserInDB
from datetime import datetime
from bson import ObjectId
import logging
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()


class WhatsAppCredentials(BaseModel):
    app_id: str
    waba_id: str
    phone_number_id: str
    access_token: str
    shop_id: str


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
    """Save WhatsApp Business API credentials for a shop"""
    try:
        # Verify shop belongs to user
        shop = await db.get_db().shops.find_one({
            "_id": ObjectId(creds.shop_id),
            "userId": str(current_user.id)
        })
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found or access denied"
            )
        
        # Validate credentials by making a test API call
        is_valid = await verify_whatsapp_credentials(creds.access_token, creds.phone_number_id)
        
        # Save credentials to shop document
        update_data = {
            "whatsapp_app_id": creds.app_id,
            "whatsapp_waba_id": creds.waba_id,
            "whatsapp_phone_number_id": creds.phone_number_id,
            "whatsapp_access_token": creds.access_token,
            "whatsapp_connected": is_valid,
            "whatsapp_connected_at": datetime.utcnow() if is_valid else None,
            "updatedAt": datetime.utcnow()
        }
        
        await db.get_db().shops.update_one(
            {"_id": ObjectId(creds.shop_id)},
            {"$set": update_data}
        )
        
        logger.info(f"WhatsApp credentials saved for shop {creds.shop_id}, valid={is_valid}")
        
        return WhatsAppCredentialsResponse(
            message="WhatsApp credentials saved successfully" if is_valid else "Credentials saved but verification failed",
            shop_id=creds.shop_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving WhatsApp credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {str(e)}"
        )


@router.get("/status/{shop_id}", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Check WhatsApp connection status for a shop"""
    try:
        shop = await db.get_db().shops.find_one({
            "_id": ObjectId(shop_id),
            "userId": str(current_user.id)
        })
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found or access denied"
            )
        
        has_credentials = bool(
            shop.get("whatsapp_access_token") and 
            shop.get("whatsapp_phone_number_id")
        )
        
        if has_credentials:
            # Verify credentials are still valid
            is_valid = await verify_whatsapp_credentials(
                shop.get("whatsapp_access_token"),
                shop.get("whatsapp_phone_number_id")
            )
            
            return WhatsAppStatusResponse(
                connected=is_valid,
                phone_number_id=shop.get("whatsapp_phone_number_id"),
                waba_id=shop.get("whatsapp_waba_id"),
                app_id=shop.get("whatsapp_app_id"),
                verified=is_valid,
                message="WhatsApp Business API connected" if is_valid else "Credentials invalid or expired"
            )
        
        return WhatsAppStatusResponse(
            connected=False,
            verified=False,
            message="WhatsApp not configured for this shop"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking WhatsApp status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check status: {str(e)}"
        )


@router.delete("/disconnect/{shop_id}")
async def disconnect_whatsapp(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Disconnect WhatsApp from a shop"""
    try:
        shop = await db.get_db().shops.find_one({
            "_id": ObjectId(shop_id),
            "userId": str(current_user.id)
        })
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found or access denied"
            )
        
        await db.get_db().shops.update_one(
            {"_id": ObjectId(shop_id)},
            {"$unset": {
                "whatsapp_app_id": "",
                "whatsapp_waba_id": "",
                "whatsapp_phone_number_id": "",
                "whatsapp_access_token": "",
                "whatsapp_connected": "",
                "whatsapp_connected_at": ""
            }}
        )
        
        logger.info(f"WhatsApp disconnected for shop {shop_id}")
        return {"message": "WhatsApp disconnected successfully", "shop_id": shop_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting WhatsApp: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect: {str(e)}"
        )


async def verify_whatsapp_credentials(access_token: str, phone_number_id: str) -> bool:
    """Verify WhatsApp credentials by making a test API call"""
    try:
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10)
            return resp.status_code == 200
            
    except Exception as e:
        logger.warning(f"WhatsApp credential verification failed: {e}")
        return False
