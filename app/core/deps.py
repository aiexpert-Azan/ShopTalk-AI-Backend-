from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from app.core.config import settings
from app.core.database import db
from app.models.user import UserInDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        phone: str = payload.get("sub")
        if phone is None:
            raise credentials_exception
    except (JWTError, ValidationError):
        raise credentials_exception

    user_data = await db.get_db().users.find_one({"phone": phone})
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_data["_id"] = str(user_data["_id"])

    safe_data = {
        "_id": user_data.get("_id"),
        "phone": user_data.get("phone", ""),
        "name": user_data.get("name"),
        "email": user_data.get("email"),
        "plan": user_data.get("plan", "starter"),
        "created_at": user_data.get("created_at"),
        "is_active": user_data.get("is_active", True),
        "ai_active": user_data.get("ai_active", False),
        "phone_verified": user_data.get("phone_verified", False),
        "hashed_password": user_data.get("hashed_password"),
    }

    try:
        return UserInDB(**safe_data)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User data validation error: {str(e)}"
        )

async def get_admin_user(current_user: UserInDB = Depends(get_current_user)):
    if getattr(current_user, 'role', None) != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user