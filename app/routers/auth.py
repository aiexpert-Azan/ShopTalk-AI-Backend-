from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, validator
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

# In-memory reset codes storage
reset_codes: dict = {}

# --- Pydantic Models ---

class VerifyTokenRequest(BaseModel):
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

class SendSignupOTPRequest(BaseModel):
    phone: str
    email: Optional[EmailStr] = None
    name: str
    password: str

    @validator('email', pre=True)
    def allow_empty_email(cls, v):
        if v == "" or v is None:
            return None
        return v

class SendSignupOTPResponse(BaseModel):
    message: str
    phone: str

class VerifySignupOTPRequest(BaseModel):
    phone: str
    code: str

class VerifySignupOTPResponse(BaseModel):
    message: str
    access_token: str
    refresh_token: str
    token_type: str

# --- SIGNUP ---
@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    user_exists = await db.get_db().users.find_one({"phone": user.phone})
    if user_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")

    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump(exclude={"password"})
    user_in_db = {
        **user_data,
        "hashed_password": hashed_password,
        "phone_verified": True,
        "plan": "starter",
        "is_active": True,
        "created_at": datetime.utcnow()
    }

    await db.get_db().users.insert_one(user_in_db)
    access_token = create_access_token(data={"sub": user.phone})
    refresh_token = create_refresh_token(data={"sub": user.phone})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# --- LOGIN ---
@router.post("/login", response_model=Token)
async def login(form_data: UserLogin):
    user = await db.get_db().users.find_one({"phone": form_data.phone})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect phone or password")

    access_token = create_access_token(data={"sub": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# --- FIREBASE VERIFY ---
@router.post("/firebase-verify", response_model=Token)
async def firebase_verify(request: VerifyTokenRequest):
    # Initialize Firebase Admin if not already done
    try:
        if not firebase_admin._apps:
            # Preferred: initialize from environment variables (suitable for Render)
            project_id = os.getenv("FIREBASE_PROJECT_ID")
            client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
            private_key = os.getenv("FIREBASE_PRIVATE_KEY")

            if private_key:
                # Convert escaped newlines into real newlines
                private_key = private_key.replace('\\n', '\n')

            if project_id and client_email and private_key:
                cred_dict = {
                    "type": "service_account",
                    "project_id": project_id,
                    "private_key": private_key,
                    "client_email": client_email,
                }
                try:
                    cred = firebase_credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                    logger.info("Initialized firebase-admin from environment credentials")
                except Exception as e:
                    logger.exception("Failed to initialize firebase-admin from environment credentials: %s", e)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to initialize Firebase admin from environment credentials")
            else:
                # Fallback: try a JSON file path if provided
                sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', None)
                if not sa_path:
                    msg = "Firebase credentials not configured. Set FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, and FIREBASE_PRIVATE_KEY, or provide FIREBASE_SERVICE_ACCOUNT_PATH."
                    logger.error(msg)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)

                sa_p = Path(sa_path)
                if not sa_p.is_absolute():
                    repo_root = Path(__file__).resolve().parents[2]
                    sa_p = (repo_root / sa_path).resolve()

                if not sa_p.exists():
                    msg = f"Firebase service account file not found: {sa_p}"
                    logger.error(msg)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)

                try:
                    cred = firebase_credentials.Certificate(str(sa_p))
                    firebase_admin.initialize_app(cred)
                    logger.info("Initialized firebase-admin from service account file: %s", sa_p)
                except Exception as e:
                    logger.exception("Failed to initialize firebase-admin from file: %s", e)
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to initialize Firebase admin from file")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize firebase-admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to initialize Firebase admin"
        )

    # Verify Firebase ID token
    try:
        decoded = firebase_auth.verify_id_token(request.id_token)
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token"
        )

    # Get phone number
    fb_phone = decoded.get("phone_number")
    phone = fb_phone or request.phone_number
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number required"
        )

    # Find or create user
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        new_user = {
            "phone": phone,
            "name": request.name or decoded.get("name"),
            "email": request.email or decoded.get("email"),
            "phone_verified": True,
            "is_active": True,
            "plan": "starter",
            "created_at": datetime.utcnow()
        }
        await db.get_db().users.insert_one(new_user)
        logger.info(f"New user created via Firebase: {phone}")

    # Issue app JWT tokens
    access_token = create_access_token(data={"sub": phone})
    refresh_token = create_refresh_token(data={"sub": phone})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# --- FORGOT PASSWORD ---
@router.post("/forgot-password", response_model=ResetOTPResponse)
async def forgot_password(request: ForgotPasswordRequest):
    phone = request.phone

    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this phone number."
        )

    code = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    reset_codes[phone] = {"code": code, "expiry": expiry}

    logger.info(f"[MOCK] Password reset OTP for {phone}: {code}")

    return ResetOTPResponse(
        message="OTP sent. Use 123456 for testing.",
        phone=phone
    )

# --- VERIFY RESET OTP ---
@router.post("/verify-reset-otp", response_model=dict)
async def verify_reset_otp(request: VerifyResetOTPRequest):
    phone = request.phone

    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stored = reset_codes.get(phone)
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No OTP found. Request a new one.")

    if datetime.utcnow() > stored["expiry"]:
        del reset_codes[phone]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired. Request a new one.")

    if request.code != "123456" and request.code != stored["code"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code.")

    return {"message": "OTP verified successfully", "phone": phone}

# --- RESET PASSWORD ---
@router.post("/reset-password", response_model=dict)
async def reset_password(request: ResetPasswordRequest):
    phone = request.phone

    stored = reset_codes.get(phone)
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No reset request found.")

    if datetime.utcnow() > stored["expiry"]:
        del reset_codes[phone]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired.")

    if request.code != "123456" and request.code != stored["code"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code.")

    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    hashed_password = get_password_hash(request.new_password)
    await db.get_db().users.update_one(
        {"phone": phone},
        {"$set": {"hashed_password": hashed_password}}
    )

    del reset_codes[phone]
    logger.info(f"Password reset successful for {phone}")

    return {"message": "Password reset successfully", "phone": phone}

# --- PROFILE ---
@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user