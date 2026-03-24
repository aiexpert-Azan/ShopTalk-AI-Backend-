from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from app.core.limiter import limiter
from pydantic import BaseModel, EmailStr, validator, Field
import logging
import os
import json
import random

logger = logging.getLogger(__name__)
router = APIRouter()

from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserInDB
from app.core.config import settings

import firebase_admin
from firebase_admin import credentials as firebase_credentials, auth as firebase_auth
from pathlib import Path



# --- Pydantic Models ---

class VerifyTokenRequest(BaseModel):
    # Frontend snake_case bhej raha he, isliye yahan id_token hi use kiya he
    id_token: str
    phone_number: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None

    @validator('email', pre=True)
    def allow_empty_email(cls, v):
        if v == "" or v is None:
            return None
        return v

class ForgotPasswordRequest(BaseModel):
    phone: str

class VerifyResetOTPRequest(BaseModel):
    phone: str
    code: str

class ResetPasswordRequest(BaseModel):
    phone: str
    code: str
    new_password: str

class ResetOTPResponse(BaseModel):
    message: str
    phone: str

# --- FIREBASE INITIALIZATION HELPER ---

def initialize_firebase_admin():
    """Robustly initialize Firebase Admin using Environment Variables or File."""
    if not firebase_admin._apps:
        try:
            # 1. Try Environment Variables (Best for Render)
            project_id = os.getenv("FIREBASE_PROJECT_ID")
            client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
            private_key_raw = os.getenv("FIREBASE_PRIVATE_KEY")

            if project_id and client_email and private_key_raw:
                # Handle escaped newlines properly
                private_key = private_key_raw.replace('\\n', '\n')
                
                # Fetch optional fields from env with Google defaults
                token_uri = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
                auth_uri = os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
                auth_provider_cert_url = os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs")
                
                # Full required dictionary for Firebase Admin
                cred_dict = {
                    "type": "service_account",
                    "project_id": project_id,
                    "private_key": private_key,
                    "client_email": client_email,
                    "token_uri": token_uri,
                    "auth_uri": auth_uri,
                    "auth_provider_x509_cert_url": auth_provider_cert_url,
                }
                
                logger.info(f"Attempting Firebase init with project_id={project_id}, client_email={client_email[:20]}...")
                cred = firebase_credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin initialized successfully from Env Vars")
                return True

            # 2. Fallback to Service Account File
            sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
            if sa_path and Path(sa_path).exists():
                cred = firebase_credentials.Certificate(sa_path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase Admin initialized from file: {sa_path}")
                return True
                
            logger.error("Firebase credentials missing in Env Vars and File")
            return False

        except Exception as e:
            logger.error(f"Critical Firebase Init Failure: {repr(e)}")
            print(f"[FIREBASE ERROR] {repr(e)}")  # Print to stdout for Render logs
            return False
    return True

# --- SIGNUP ---
@router.post("/signup", response_model=Token)
@limiter.limit("3/minute")
async def signup(request: Request, user: UserCreate):
    user_exists = await db.get_db().users.find_one({"phone": user.phone})
    if user_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")

    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump(exclude={"password"})
    user_in_db = {
        **user_data,
        "hashed_password": hashed_password,
        "phone_verified": True,
        "plan": "free",
        "is_active": True,
        "created_at": datetime.utcnow()
    }

    await db.get_db().users.insert_one(user_in_db)
    access_token = create_access_token(data={"sub": user["phone"], "role": user.get("role", None), "phone": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# --- LOGIN ---
@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, form_data: UserLogin):
    user = await db.get_db().users.find_one({"phone": form_data.phone})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect phone or password")

    access_token = create_access_token(data={"sub": user["phone"], "role": user.get("role", None), "phone": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# --- FIREBASE VERIFY ---
@router.post("/firebase-verify", response_model=Token)
@limiter.limit("10/minute")
async def firebase_verify(request: Request, request_data: VerifyTokenRequest):
    if not initialize_firebase_admin():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Service Unavailable (Config Error)"
        )

    try:
        decoded = firebase_auth.verify_id_token(request_data.id_token)
    except Exception as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token"
        )

    fb_phone = decoded.get("phone_number")
    phone = fb_phone or request.phone_number

    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required")

    # Normalize — always +92XXXXXXXXX
    def normalize_phone(p: str) -> str:
        p = p.strip()
        if p.startswith('+92'):
            return p
        if p.startswith('92'):
            return '+' + p
        if p.startswith('0'):
            return '+92' + p[1:]
        return p

    normalized_phone = normalize_phone(phone)
    local_phone = '0' + normalized_phone[3:]  # +923001234567 → 03001234567

    # Check both formats
    user = await db.get_db().users.find_one({
        "$or": [
            {"phone": normalized_phone},
            {"phone": local_phone}
        ]
    })

    if user:
        # Existing user — just return token
        access_token = create_access_token(data={
            "sub": user.get("phone"),
            "phone": user.get("phone")
        })
        refresh_token = create_refresh_token(data={"sub": user.get("phone")})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    # New user
    new_user = {
        "phone": normalized_phone,
        "name": request_data.name or decoded.get("name") or "User",
        "email": request_data.email or decoded.get("email"),
        "phone_verified": True,
        "is_active": True,
        "plan": "free",
        "created_at": datetime.utcnow()
    }
    await db.get_db().users.insert_one(new_user)

    access_token = create_access_token(data={
        "sub": normalized_phone,
        "phone": normalized_phone
    })
    refresh_token = create_refresh_token(data={"sub": normalized_phone})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# --- FORGOT PASSWORD ---
@router.post("/forgot-password", response_model=ResetOTPResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, request_data: ForgotPasswordRequest):
    phone = request_data.phone
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this phone number.")
    code = str(random.randint(100000, 999999))
    # Remove any existing OTP for this phone
    await db.get_db().otp_codes.delete_many({"phone": phone})
    await db.get_db().otp_codes.insert_one({
        "phone": phone,
        "code": code,
        "createdAt": datetime.utcnow()
    })
    logger.info(f"Password reset OTP for {phone}: {code}")
    return ResetOTPResponse(message="OTP sent. Use 123456 for testing.", phone=phone)
    phone = request.phone
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this phone number.")

    code = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    reset_codes[phone] = {"code": code, "expiry": expiry}
    
    logger.info(f"Password reset OTP for {phone}: {code}")
    return ResetOTPResponse(message="OTP sent. Use 123456 for testing.", phone=phone)

# --- VERIFY RESET OTP ---
@router.post("/verify-reset-otp")
async def verify_reset_otp(request: VerifyResetOTPRequest):
    otp_doc = await db.get_db().otp_codes.find_one({"phone": request.phone})
    if not otp_doc:
        raise HTTPException(status_code=400, detail="OTP expired or not found")
    # Check expiry (TTL index will auto-delete, but double-check)
    if (datetime.utcnow() - otp_doc["createdAt"]).total_seconds() > 600:
        await db.get_db().otp_codes.delete_one({"_id": otp_doc["_id"]})
        raise HTTPException(status_code=400, detail="OTP expired or not found")
    if request.code != "123456" and request.code != otp_doc["code"]:
        raise HTTPException(status_code=400, detail="Invalid OTP code")
    return {"message": "OTP verified successfully", "phone": request.phone}

# --- RESET PASSWORD ---

# --- RESET PASSWORD (with +92/0 normalization) ---
@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    # Normalize phone for lookup
    phone_variants = [request.phone]
    if request.phone.startswith("+92"):
        phone_variants.append("0" + request.phone[3:])
    elif request.phone.startswith("0"):
        phone_variants.append("+92" + request.phone[1:])

    otp_doc = await db.get_db().otp_codes.find_one({"phone": request.phone})
    if not otp_doc:
        raise HTTPException(status_code=400, detail="OTP expired or not found")
    if (datetime.utcnow() - otp_doc["createdAt"]).total_seconds() > 600:
        await db.get_db().otp_codes.delete_one({"_id": otp_doc["_id"]})
        raise HTTPException(status_code=400, detail="OTP expired or not found")
    if request.code != "123456" and request.code != otp_doc["code"]:
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    user = await db.get_db().users.find_one({"phone": {"$in": phone_variants}})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed = get_password_hash(request.new_password)
    await db.get_db().users.update_one(
        {"_id": user["_id"]},
        {"$set": {"hashed_password": hashed}}
    )
    await db.get_db().otp_codes.delete_one({"_id": otp_doc["_id"]})
    return {"message": "Password reset successfully"}

# --- CHANGE PASSWORD (authenticated) ---
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: UserInDB = Depends(get_current_user)
):
    # Get user with hashed_password from DB
    user = await db.get_db().users.find_one({"phone": current_user.phone})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Check if user has password (Firebase users may not)
    if not user.get("hashed_password"):
        raise HTTPException(
            status_code=400,
            detail="No password set. Use forgot password to set one."
        )
    # Verify current password
    if not verify_password(request.current_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    # Set new password
    hashed = get_password_hash(request.new_password)
    await db.get_db().users.update_one(
        {"phone": current_user.phone},
        {"$set": {"hashed_password": hashed}}
    )
    return {"message": "Password changed successfully"}

# --- PROFILE ---
@router.get("/profile")
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    # Get shop plan
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    plan = shop.get("plan", "free") if shop else "free"
    messages_this_month = shop.get("messages_this_month", 0) if shop else 0
    messages_limit = {
        "free": 200,
        "starter": 1000,
        "growth": 5000,
        "business": float('inf')
    }.get(plan, 200)
    return {
        "phone": current_user.phone,
        "name": current_user.name,
        "email": current_user.email,
        "plan": plan,
        "is_active": current_user.is_active,
        "phone_verified": current_user.phone_verified,
        "ai_active": current_user.ai_active,
        "messages_this_month": messages_this_month,
        "messages_limit": messages_limit
    }