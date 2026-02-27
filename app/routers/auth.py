from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
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

# In-memory reset codes storage
reset_codes: dict = {}

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
                
                # Full required dictionary for Firebase Admin
                cred_dict = {
                    "type": "service_account",
                    "project_id": project_id,
                    "private_key": private_key,
                    "client_email": client_email,
                    # Ye missing fields hain jo 503 error de rahi thi
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                }
                
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
            return False
    return True

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
    # Initialize app if needed
    if not initialize_firebase_admin():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Firebase Service Unavailable (Config Error)"
        )

    # Verify Token
    try:
        decoded = firebase_auth.verify_id_token(request.id_token)
    except Exception as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token"
        )

    # Phone number logic
    fb_phone = decoded.get("phone_number")
    phone = fb_phone or request.phone_number
    
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required")

    # DB User check/create
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        new_user = {
            "phone": phone,
            "name": request.name or decoded.get("name") or "User",
            "email": request.email or decoded.get("email"),
            "phone_verified": True,
            "is_active": True,
            "plan": "starter",
            "created_at": datetime.utcnow()
        }
        await db.get_db().users.insert_one(new_user)

    # Issue Tokens
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
        raise HTTPException(status_code=404, detail="No account found with this phone number.")

    code = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    reset_codes[phone] = {"code": code, "expiry": expiry}
    
    logger.info(f"Password reset OTP for {phone}: {code}")
    return ResetOTPResponse(message="OTP sent. Use 123456 for testing.", phone=phone)

# --- VERIFY RESET OTP ---
@router.post("/verify-reset-otp")
async def verify_reset_otp(request: VerifyResetOTPRequest):
    stored = reset_codes.get(request.phone)
    if not stored or datetime.utcnow() > stored["expiry"]:
        raise HTTPException(status_code=400, detail="OTP expired or not found")
    
    if request.code != "123456" and request.code != stored["code"]:
        raise HTTPException(status_code=400, detail="Invalid OTP code")
        
    return {"message": "OTP verified successfully", "phone": request.phone}

# --- RESET PASSWORD ---
@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    stored = reset_codes.get(request.phone)
    if not stored or request.code != stored["code"] and request.code != "123456":
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    hashed_password = get_password_hash(request.new_password)
    await db.get_db().users.update_one(
        {"phone": request.phone},
        {"$set": {"hashed_password": hashed_password}}
    )
    if request.phone in reset_codes: del reset_codes[request.phone]
    return {"message": "Password reset successfully"}

# --- PROFILE ---
@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user