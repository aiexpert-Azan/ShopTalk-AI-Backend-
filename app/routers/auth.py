from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserCreate, UserLogin, UserResponse, Token, UserInDB
from app.core.config import settings

router = APIRouter()

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