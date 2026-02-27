from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, validator
import logging
import os
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
async def firebase_verify(id_token: str, phone_number: str, name: Optional[str] = None, email: Optional[EmailStr] = None):
    try:
        if not firebase_admin._apps:
            sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or settings.FIREBASE_SERVICE_ACCOUNT_PATH
            if not sa_path:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Firebase service account path not configured")

            sa_p = Path(sa_path)
            if not sa_p.is_absolute():
                repo_root = Path(__file__).resolve().parents[2]
                sa_p = (repo_root / sa_path).resolve()

            if not sa_p.exists():
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Firebase service account file not found: {sa_p}")

            cred = firebase_credentials.Certificate(str(sa_p))
            firebase_admin.initialize_app(cred)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize firebase-admin: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to initialize Firebase admin")

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase ID token")

    fb_phone = decoded.get("phone_number")
    phone = fb_phone or phone_number
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number required")

    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        new_user = {
            "phone": phone,
            "name": name or decoded.get("name"),
            "email": email or decoded.get("email"),
            "phone_verified": True,
            "is_active": True,
            "plan": "starter",
            "created_at": datetime.utcnow()
        }
        await db.get_db().users.insert_one(new_user)

    access_token = create_access_token(data={"sub": phone})
    refresh_token = create_refresh_token(data={"sub": phone})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

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

    # Mock OTP mode — real Firebase/SMS integration later
    code = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    reset_codes[phone] = {"code": code, "expiry": expiry}

    logger.info(f"[MOCK] Password reset OTP for {phone}: {code}")

    return ResetOTPResponse(
        message="OTP sent to your phone. Use 123456 for testing.",
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

    # Accept 123456 as master test code OR actual generated code
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