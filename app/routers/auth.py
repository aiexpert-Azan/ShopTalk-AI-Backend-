from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
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
    email: EmailStr
    name: str
    password: str

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

@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    """
    User signup endpoint.
    Phone OTP must be verified before signup is possible.
    Use POST /api/auth/send-signup-otp and POST /api/auth/verify-signup-otp first.
    """
    # Check if phone OTP was verified
    if user.phone not in signup_phone_otps or not signup_phone_otps[user.phone].get("otp_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must be verified with OTP before signup. Use /send-signup-otp first."
        )
    
    # Check if user already exists
    user_exists = await db.get_db().users.find_one({"phone": user.phone})
    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )
    
    # Hash password
    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump(exclude={"password"})
    user_in_db = {
        **user_data,
        "hashed_password": hashed_password,
        "phone_verified": True
    }
    
    # Insert into database
    await db.get_db().users.insert_one(user_in_db)
    
    # Clear OTP verification record
    del signup_phone_otps[user.phone]
    
    # Generate tokens
    access_token = create_access_token(data={"sub": user.phone})
    refresh_token = create_refresh_token(data={"sub": user.phone})
    
    logger.info(f"User created successfully: {user.phone}")
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

@router.post("/login/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.get_db().users.find_one({"phone": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

@router.post("/login", response_model=Token)
async def login(form_data: UserLogin):
    user = await db.get_db().users.find_one({"phone": form_data.phone})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
        )
    
    access_token = create_access_token(data={"sub": user["phone"]})
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

# --- SEND SIGNUP OTP VIA TWILIO VERIFY ---
@router.post("/send-signup-otp", response_model=SendSignupOTPResponse)
async def send_signup_otp(request: SendSignupOTPRequest):
    """
    Send OTP to phone number for signup verification.
    User must verify the OTP before they can complete signup.
    """
    phone = request.phone
    
    # Check if user already exists
    user_exists = await db.get_db().users.find_one({"phone": phone})
    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )
    
    # Convert to international format for Twilio
    international_phone = f"+92{phone[1:]}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
            to=international_phone,
            channel="sms"
        )
        logger.info(f"Signup OTP sent to {phone}, SID: {verification.sid}")
        
        # Store user data temporarily
        signup_phone_otps[phone] = {
            "otp_verified": False,
            "user_data": {
                "phone": phone,
                "email": request.email,
                "name": request.name,
                "password": request.password
            },
            "verification_sid": verification.sid
        }
        
    except Exception as e:
        logger.error(f"Failed to send signup OTP to {phone}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please check your phone number."
        )
    
    return SendSignupOTPResponse(
        message="OTP sent to your phone. It expires in 10 minutes.",
        phone=phone
    )

# --- VERIFY SIGNUP OTP ---
@router.post("/verify-signup-otp", response_model=VerifySignupOTPResponse)
async def verify_signup_otp(request: VerifySignupOTPRequest):
    """
    Verify OTP for signup. Once verified, user can proceed to signup.
    """
    phone = request.phone
    
    if phone not in signup_phone_otps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found for this phone number. Request OTP first."
        )
    
    international_phone = f"+92{phone[1:]}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification_check = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verification_checks.create(
            to=international_phone,
            code=request.code
        )
        
        if verification_check.status == "approved":
            # Mark OTP as verified
            signup_phone_otps[phone]["otp_verified"] = True
            logger.info(f"Signup OTP verified for {phone}")
            
            # Create user automatically
            user_data = signup_phone_otps[phone]["user_data"]
            hashed_password = get_password_hash(user_data["password"])
            
            user_in_db = {
                "phone": user_data["phone"],
                "email": user_data["email"],
                "name": user_data["name"],
                "hashed_password": hashed_password,
                "phone_verified": True,
                "plan": "starter",
                "is_active": True,
                "ai_active": False,
                "created_at": datetime.utcnow()
            }
            
            result = await db.get_db().users.insert_one(user_in_db)
            logger.info(f"User created successfully: {phone}")
            
            # Generate tokens
            access_token = create_access_token(data={"sub": phone})
            refresh_token = create_refresh_token(data={"sub": phone})
            
            # Clear OTP data
            del signup_phone_otps[phone]
            
            return VerifySignupOTPResponse(
                message="Phone verified successfully. User created.",
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP code. Please try again."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification failed for {phone}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )

# --- FORGOT PASSWORD: SEND OTP VIA TWILIO VERIFY ---
@router.post("/forgot-password", response_model=ResetOTPResponse)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Send OTP to phone number for password reset.
    User must verify OTP before resetting password.
    """
    phone = request.phone
    
    # Check if user exists
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        # Don't reveal if user exists (security)
        return ResetOTPResponse(
            message="If an account exists with this phone number, an OTP has been sent.",
            phone=phone
        )
    
    # Convert to international format for Twilio
    international_phone = f"+92{phone[1:]}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verifications.create(
            to=international_phone,
            channel="sms"
        )
        logger.info(f"Password reset OTP sent to {phone}")
        
    except Exception as e:
        logger.error(f"Failed to send password reset OTP to {phone}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please check your phone number."
        )
    
    return ResetOTPResponse(
        message="OTP sent to your phone. It expires in 10 minutes.",
        phone=phone
    )

# --- VERIFY RESET OTP ---
@router.post("/verify-reset-otp", response_model=dict)
async def verify_reset_otp(request: VerifyResetOTPRequest):
    """
    Verify OTP for password reset.
    """
    phone = request.phone
    
    # Check if user exists
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    international_phone = f"+92{phone[1:]}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification_check = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verification_checks.create(
            to=international_phone,
            code=request.code
        )
        
        if verification_check.status == "approved":
            logger.info(f"Reset OTP verified for {phone}")
            return {"message": "OTP verified successfully", "phone": phone}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP code"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification failed for {phone}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )

# --- RESET PASSWORD ---
@router.post("/reset-password", response_model=dict)
async def reset_password(request: ResetPasswordRequest):
    """
    Reset password after OTP verification.
    First call POST /forgot-password, then verify OTP with POST /verify-reset-otp, then call this.
    """
    phone = request.phone
    
    # Verify OTP
    international_phone = f"+92{phone[1:]}"
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        verification_check = client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID).verification_checks.create(
            to=international_phone,
            code=request.code
        )
        
        if verification_check.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP code"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification failed for {phone}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )
    
    # Find user and update password
    user = await db.get_db().users.find_one({"phone": phone})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Hash new password
    hashed_password = get_password_hash(request.new_password)
    
    # Update in database
    await db.get_db().users.update_one(
        {"phone": phone},
        {"$set": {"hashed_password": hashed_password}}
    )
    
    logger.info(f"Password reset successfully for {phone}")
    
    return {"message": "Password reset successfully", "phone": phone}

