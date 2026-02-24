from datetime import datetime, timedelta
from typing import Optional # Add kiya
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, validator # validator add kiya
from twilio.rest import Client
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserInDB
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory storage for signup OTP verification
signup_phone_otps: dict = {}  # {phone: {otp_verified: bool, user_data: {}}}

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
    # FIX: Email ko optional kiya aur empty string handle karne ke liye validator lagaya
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
    if user.phone not in signup_phone_otps or not signup_phone_otps[user.phone].get("otp_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must be verified with OTP before signup."
        )
    
    user_exists = await db.get_db().users.find_one({"phone": user.phone})
    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump(exclude={"password"})
    user_in_db = {
        **user_data,
        "hashed_password": hashed_password,
        "phone_verified": True
    }
    
    await db.get_db().users.insert_one(user_in_db)
    del signup_phone_otps[user.phone]
    
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

@router.post("/send-signup-otp", response_model=SendSignupOTPResponse)
async def send_signup_otp(request: SendSignupOTPRequest):
    phone = request.phone
    user_exists = await db.get_db().users.find_one({"phone": phone})
    if user_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")
    
    international_phone = f"+92{phone[1:]}"
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
            to=international_phone, channel="sms"
        )
        
        signup_phone_otps[phone] = {
            "otp_verified": False,
            "user_data": {
                "phone": phone,
                "email": request.email,
                "name": request.name,
                "password": request.password
            }
        }
    except Exception as e:
        logger.error(f"Twilio Error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send OTP")
    
    return SendSignupOTPResponse(message="OTP sent", phone=phone)

@router.post("/verify-signup-otp", response_model=VerifySignupOTPResponse)
async def verify_signup_otp(request: VerifySignupOTPRequest):
    phone = request.phone
    if phone not in signup_phone_otps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request OTP first")
    
    international_phone = f"+92{phone[1:]}"
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        v_check = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verification_checks.create(
            to=international_phone, code=request.code
        )
        
        if v_check.status == "approved":
            user_data = signup_phone_otps[phone]["user_data"]
            hashed_pwd = get_password_hash(user_data["password"])
            
            user_in_db = {
                "phone": user_data["phone"],
                "email": user_data["email"],
                "name": user_data["name"],
                "hashed_password": hashed_pwd,
                "phone_verified": True,
                "plan": "starter",
                "is_active": True,
                "created_at": datetime.utcnow()
            }
            await db.get_db().users.insert_one(user_in_db)
            
            access_token = create_access_token(data={"sub": phone})
            refresh_token = create_refresh_token(data={"sub": phone})
            del signup_phone_otps[phone]
            
            return VerifySignupOTPResponse(
                message="Verified", access_token=access_token, refresh_token=refresh_token, token_type="bearer"
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Profile and Forgot Password routes as they were...
@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

@router.post("/forgot-password", response_model=ResetOTPResponse)
async def forgot_password(request: ForgotPasswordRequest):
    phone = request.phone
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        return ResetOTPResponse(message="OTP sent if account exists", phone=phone)
    
    international_phone = f"+92{phone[1:]}"
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
            to=international_phone, channel="sms"
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send OTP")
    
    return ResetOTPResponse(message="OTP sent", phone=phone)