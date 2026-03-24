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
    shop_id: Optional[str] = None  # Optional ab


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


class EmbeddedSignupRequest(BaseModel):
    code: str


class EmbeddedSignupResponse(BaseModel):
    success: bool
    shop_id: str
    waba_id: str
    phone_number_id: str
    connected: bool
    message: str


@router.post("/embedded-signup", response_model=EmbeddedSignupResponse)
async def embedded_signup(
    request: EmbeddedSignupRequest,
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Complete Facebook Embedded Signup flow for WhatsApp Business API.
    Exchanges authorization code for access token, fetches WABA info,
    saves credentials, and subscribes to webhooks.
    """
    try:
        logger.info(f"Starting embedded signup for user {current_user.phone}")

        # Exchange code for short-lived access token
        token_url = f"https://graph.facebook.com/v18.0/oauth/access_token"
        token_params = {
            "client_id": settings.WHATSAPP_CLIENT_ID,
            "client_secret": settings.WHATSAPP_CLIENT_SECRET,
            "redirect_uri": settings.WHATSAPP_REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code"
        }
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(token_url, data=token_params)
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data["access_token"]

        # Exchange for long-lived token
        long_token_url = f"https://graph.facebook.com/v18.0/oauth/access_token"
        long_token_params = {
            "grant_type": "fb_exchange_token",
            "client_id": settings.WHATSAPP_CLIENT_ID,
            "client_secret": settings.WHATSAPP_CLIENT_SECRET,
            "fb_exchange_token": access_token
        }
        async with httpx.AsyncClient() as client:
            long_token_resp = await client.get(long_token_url, params=long_token_params)
            long_token_resp.raise_for_status()
            long_token_data = long_token_resp.json()
            long_lived_token = long_token_data.get("access_token", access_token)

        # Fetch business info
        business_url = f"https://graph.facebook.com/v18.0/me?fields=id,name,verification_status&access_token={long_lived_token}"
        async with httpx.AsyncClient() as client:
            business_resp = await client.get(business_url)
            business_resp.raise_for_status()
            business_data = business_resp.json()
            business_id = business_data["id"]

        # Fetch WABA info
        waba_url = f"https://graph.facebook.com/v18.0/{business_id}/owned_whatsapp_business_accounts?access_token={long_lived_token}"
        async with httpx.AsyncClient() as client:
            waba_resp = await client.get(waba_url)
            waba_resp.raise_for_status()
            waba_data = waba_resp.json()
            waba_id = waba_data["data"][0]["id"]

        # Save credentials
        await save_whatsapp_credentials(shop_id, long_lived_token, business_id, waba_id)

        # Token health check (optional, can be a separate endpoint)
        health_url = f"https://graph.facebook.com/v18.0/me?access_token={long_lived_token}"
        async with httpx.AsyncClient() as client:
            health_resp = await client.get(health_url)
            if health_resp.status_code != 200:
                logger.error("WhatsApp token health check failed", extra={"shop_id": shop_id})
                return {"message": "Token health check failed"}

        return {"message": "WhatsApp embedded signup successful"}

            if businesses_resp.status_code != 200:
                logger.error(f"Failed to fetch businesses: {businesses_resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch businesses from Facebook"
                )

            businesses_data = businesses_resp.json()
            businesses = businesses_data.get("data", [])

            if not businesses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No businesses found for this Facebook account"
                )

            business_id = businesses[0].get("id")
            logger.info(f"Found business_id: {business_id}")

            # Step 3: Get WhatsApp Business Accounts
            waba_resp = await client.get(
                f"https://graph.facebook.com/v22.0/{business_id}/owned_whatsapp_business_accounts",
                headers=headers
            )

            if waba_resp.status_code != 200:
                logger.error(f"Failed to fetch WABA: {waba_resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch WhatsApp Business Account"
                )

            waba_data = waba_resp.json()
            wabas = waba_data.get("data", [])

            if not wabas:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No WhatsApp Business Account found"
                )

            waba_id = wabas[0].get("id")
            logger.info(f"Found waba_id: {waba_id}")

            # Step 4: Get phone numbers
            phone_resp = await client.get(
                f"https://graph.facebook.com/v22.0/{waba_id}/phone_numbers",
                headers=headers
            )

            if phone_resp.status_code != 200:
                logger.error(f"Failed to fetch phone numbers: {phone_resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch phone numbers"
                )

            phone_data = phone_resp.json()
            phone_numbers = phone_data.get("data", [])

            if not phone_numbers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone numbers found for this WhatsApp Business Account"
                )

            phone_number_id = phone_numbers[0].get("id")
            logger.info(f"Found phone_number_id: {phone_number_id}")

            # Step 5: Find or create shop
            shop = await db.get_db().shops.find_one({
                "ownerPhone": current_user.phone
            })

            if not shop:
                shop = await db.get_db().shops.find_one({
                    "userId": str(current_user.id)
                })

            if not shop:
                new_shop = {
                    "ownerPhone": current_user.phone,
                    "userId": str(current_user.id),
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                result = await db.get_db().shops.insert_one(new_shop)
                shop = {"_id": result.inserted_id}
                logger.info(f"New shop created for user {current_user.phone}")

            shop_id = str(shop["_id"])

            # Step 6: Save credentials to MongoDB
            update_data = {
                "whatsapp_app_id": settings.FACEBOOK_APP_ID,
                "whatsapp_waba_id": waba_id,
                "whatsapp_phone_number_id": phone_number_id,
                "whatsapp_access_token": access_token,
                "whatsapp_connected": True,
                "whatsapp_connected_at": datetime.utcnow(),
                "whatsapp_setup_method": "embedded_signup",
                "updatedAt": datetime.utcnow()
            }

            await db.get_db().shops.update_one(
                {"_id": shop["_id"]},
                {"$set": update_data}
            )

            logger.info(f"WhatsApp credentials saved for shop {shop_id}")

            # Step 7: Subscribe app to webhooks
            subscribe_resp = await client.post(
                f"https://graph.facebook.com/v22.0/{waba_id}/subscribed_apps",
                headers=headers
            )

            if subscribe_resp.status_code != 200:
                logger.warning(f"Webhook subscription warning: {subscribe_resp.text}")
                # Don't fail the whole flow, just log warning
            else:
                logger.info(f"Successfully subscribed to webhooks for WABA {waba_id}")

        return EmbeddedSignupResponse(
            success=True,
            shop_id=shop_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            connected=True,
            message="WhatsApp Business API connected successfully via Embedded Signup"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedded signup error: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedded signup failed: {str(e)}"
        )


@router.post("/save-credentials", response_model=WhatsAppCredentialsResponse)
async def save_whatsapp_credentials(
    creds: WhatsAppCredentials,
    current_user: UserInDB = Depends(get_current_user)
):
    """Save WhatsApp Business API credentials for a shop"""
    try:
        # User ke phone se shop dhundo
        shop = await db.get_db().shops.find_one({
            "ownerPhone": current_user.phone
        })

        # Agar phone se nahi mila to userId se try karo
        if not shop:
            shop = await db.get_db().shops.find_one({
                "userId": str(current_user.id)
            })

        # Agar shop_id diya hai to us se bhi try karo
        if not shop and creds.shop_id:
            try:
                shop = await db.get_db().shops.find_one({
                    "_id": ObjectId(creds.shop_id)
                })
            except Exception:
                pass

        if not shop:
            # Shop nahi mila to naya create karo
            new_shop = {
                "ownerPhone": current_user.phone,
                "userId": str(current_user.id),
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
            result = await db.get_db().shops.insert_one(new_shop)
            shop = {"_id": result.inserted_id}
            logger.info(f"New shop created for user {current_user.phone}")

        shop_id = str(shop["_id"])

        # Credentials verify karo
        is_valid = await verify_whatsapp_credentials(creds.access_token, creds.phone_number_id)

        # Credentials save karo
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
            {"_id": shop["_id"]},
            {"$set": update_data}
        )

        logger.info(f"WhatsApp credentials saved for shop {shop_id}, valid={is_valid}")

        return WhatsAppCredentialsResponse(
            message="WhatsApp credentials saved successfully" if is_valid else "Credentials saved but verification failed",
            shop_id=shop_id
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
        # Phone se dhundo pehle
        shop = await db.get_db().shops.find_one({
            "ownerPhone": current_user.phone
        })

        if not shop:
            try:
                shop = await db.get_db().shops.find_one({
                    "_id": ObjectId(shop_id)
                })
            except Exception:
                pass

        if not shop:
            return WhatsAppStatusResponse(
                connected=False,
                verified=False,
                message="Shop not found"
            )

        has_credentials = bool(
            shop.get("whatsapp_access_token") and
            shop.get("whatsapp_phone_number_id")
        )

        if has_credentials:
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
            "ownerPhone": current_user.phone
        })

        if not shop:
            try:
                shop = await db.get_db().shops.find_one({
                    "_id": ObjectId(shop_id)
                })
            except Exception:
                pass

        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )

        await db.get_db().shops.update_one(
            {"_id": shop["_id"]},
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