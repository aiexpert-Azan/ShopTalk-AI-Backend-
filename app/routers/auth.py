from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, validator
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()

from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserInDB
from app.core.config import settings

# Firebase admin
import firebase_admin
from firebase_admin import credentials as firebase_credentials, auth as firebase_auth
from pathlib import Path

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
    # Email optional to accept null/missing
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

# --- Routes ---

@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    # legacy signup route: create account directly (no OTP required)
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

@router.post("/login", response_model=Token)
async def login(form_data: UserLogin):
    user = await db.get_db().users.find_one({"phone": form_data.phone})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect phone or password")

    access_token = create_access_token(data={"sub": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# NOTE: Twilio OTP endpoints removed. Firebase verification endpoint below replaces signup OTP flow.

@router.post("/firebase-verify", response_model=Token)
async def firebase_verify(id_token: str, phone_number: str, name: Optional[str] = None, email: Optional[EmailStr] = None):
    """Verify a Firebase idToken and create/return a local JWT for the app.

    Expects `id_token` (Firebase ID token string) and `phone_number` (client-provided).
    """
    # Initialize firebase-admin if not already
    try:
        if not firebase_admin._apps:
            # Prefer explicit environment variable (production/workloads). Fall back to settings value.
            sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or settings.FIREBASE_SERVICE_ACCOUNT_PATH
            if not sa_path:
                msg = "Firebase service account path not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH env var or add serviceAccountKey.json to the repo root."
                logger.error(msg)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)

            sa_p = Path(sa_path)
            # If relative path or running from subdirectory, resolve against repo root
            if not sa_p.is_absolute():
                repo_root = Path(__file__).resolve().parents[2]
                sa_p = (repo_root / sa_path).resolve()

            if not sa_p.exists():
                # tried direct and repo-root-resolved path
                msg = (
                    f"Firebase service account file not found. Checked: {sa_path} and {sa_p}."
                    " If you don't have a service account JSON in development, set the"
                    " FIREBASE_SERVICE_ACCOUNT_PATH environment variable or place the file in the repo root."
                )
                logger.error(msg)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)

            cred = firebase_credentials.Certificate(str(sa_p))
            firebase_admin.initialize_app(cred)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize firebase-admin: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to initialize Firebase admin")

    # Verify token
    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase ID token")

    # Prefer phone_number from token if present
    fb_phone = decoded.get("phone_number")
    phone = fb_phone or phone_number
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number required")

    # Check for existing user
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        # create new user profile
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

    # Issue our app JWT
    access_token = create_access_token(data={"sub": phone})
    refresh_token = create_refresh_token(data={"sub": phone})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# Profile route
@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user