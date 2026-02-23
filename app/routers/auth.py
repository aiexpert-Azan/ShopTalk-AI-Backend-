from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserInDB
from app.core.config import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import random
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# --- In-memory password reset codes storage (email -> {code, expiry}) ---
# In production, store in Redis or database
reset_codes: dict = {}

# --- Pydantic Models for Password Reset ---
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class ResetCodeResponse(BaseModel):
    message: str
    email: str

# --- SIGNUP ENDPOINT ---
@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    # Check if user already exists in Cosmos DB
    user_exists = await db.get_db().users.find_one({"phone": user.phone})
    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )
    
    # Password hashing
    hashed_password = get_password_hash(user.password)
    
    # Prepare User object for DB
    user_data = user.model_dump(exclude={"password"})
    user_in_db = {
        **user_data,
        "hashed_password": hashed_password
    }
    
    # Insert into Cosmos DB
    await db.get_db().users.insert_one(user_in_db)
    
    # Generate Tokens
    access_token = create_access_token(data={"sub": user.phone})
    refresh_token = create_refresh_token(data={"sub": user.phone})
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

# --- SWAGGER COMPATIBLE LOGIN (OAuth2) ---
# Is endpoint ko Swagger ka "Authorize" button use karega
@router.post("/login/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    # OAuth2 standard 'username' field mein phone mangta hai
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

# --- JSON-BASED LOGIN (For Frontend/App) ---
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

# --- PROFILE ENDPOINT ---
@router.get("/profile", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

# --- FORGOT PASSWORD ENDPOINT ---
@router.post("/forgot-password", response_model=ResetCodeResponse)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Generate a 6-digit reset code and send it via email.
    Code expires in 10 minutes.
    """
    # Check if user exists with this email (assuming users have email field)
    user = await db.get_db().users.find_one({"email": request.email})
    if not user:
        # Don't reveal if email exists (security best practice) but still respond positively
        return ResetCodeResponse(
            message="If an account exists with this email, a reset code has been sent.",
            email=request.email
        )
    
    # Generate 6-digit code
    code = str(random.randint(100000, 999999))
    expiry_time = datetime.utcnow() + timedelta(minutes=10)
    
    # Store code with expiry
    reset_codes[request.email] = {"code": code, "expiry": expiry_time}
    
    # Send email via SendGrid
    try:
        send_reset_code_email(request.email, code)
        logger.info(f"Password reset code sent to {request.email}")
    except Exception as e:
        logger.error(f"Failed to send reset email to {request.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reset code email"
        )
    
    return ResetCodeResponse(
        message="Reset code sent to your email. It expires in 10 minutes.",
        email=request.email
    )

# --- VERIFY RESET CODE ENDPOINT ---
@router.post("/verify-reset-code", response_model=dict)
async def verify_reset_code(request: VerifyResetCodeRequest):
    """
    Verify that the reset code is valid and not expired.
    """
    if request.email not in reset_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reset code found for this email. Please request a new one."
        )
    
    stored_data = reset_codes[request.email]
    
    # Check if code is expired
    if datetime.utcnow() > stored_data["expiry"]:
        del reset_codes[request.email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code has expired. Please request a new one."
        )
    
    # Verify code matches
    if stored_data["code"] != request.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code."
        )
    
    return {"message": "Code verified successfully", "email": request.email}

# --- RESET PASSWORD ENDPOINT ---
@router.post("/reset-password", response_model=dict)
async def reset_password(request: ResetPasswordRequest):
    """
    Verify reset code and update password.
    """
    # Verify code first
    if request.email not in reset_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reset request found. Please request a password reset."
        )
    
    stored_data = reset_codes[request.email]
    
    # Check if code is expired
    if datetime.utcnow() > stored_data["expiry"]:
        del reset_codes[request.email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code has expired. Please request a new one."
        )
    
    # Verify code matches
    if stored_data["code"] != request.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code."
        )
    
    # Find user and update password
    user = await db.get_db().users.find_one({"email": request.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    # Hash new password
    hashed_password = get_password_hash(request.new_password)
    
    # Update in database
    await db.get_db().users.update_one(
        {"email": request.email},
        {"$set": {"hashed_password": hashed_password}}
    )
    
    # Remove used code
    del reset_codes[request.email]
    
    logger.info(f"Password reset successful for {request.email}")
    
    return {"message": "Password reset successfully", "email": request.email}

# --- HELPER FUNCTION: Send Reset Code Email ---
def send_reset_code_email(email: str, code: str):
    """
    Send HTML email with 6-digit reset code via SendGrid.
    """
    if not settings.SENDGRID_API_KEY:
        raise ValueError("SENDGRID_API_KEY not configured")
    
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h2 style="color: #333; text-align: center;">Password Reset Request</h2>
                <p style="color: #666; font-size: 16px;">Hi there,</p>
                <p style="color: #666; font-size: 16px;">We received a request to reset your password. Use the code below to reset your password.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <p style="color: #666; font-size: 14px; margin-bottom: 10px;">Your 6-digit reset code:</p>
                    <div style="background-color: #f0f0f0; border: 2px solid #007bff; border-radius: 8px; padding: 20px; display: inline-block;">
                        <span style="font-size: 36px; font-weight: bold; color: #007bff; letter-spacing: 8px;">{code}</span>
                    </div>
                </div>
                
                <p style="color: #666; font-size: 14px;">This code expires in <strong>10 minutes</strong>.</p>
                <p style="color: #666; font-size: 14px;">If you didn't request a password reset, please ignore this email or contact our support team.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">© 2024 ShopTalk AI. All rights reserved.</p>
            </div>
        </body>
    </html>
    """
    
    message = Mail(
        from_email=settings.SENDGRID_FROM_EMAIL,
        to_emails=email,
        subject="Password Reset Code",
        html_content=html_content
    )
    
    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        sg.send(message)
    except Exception as e:
        logger.error(f"SendGrid error: {str(e)}")
        raise