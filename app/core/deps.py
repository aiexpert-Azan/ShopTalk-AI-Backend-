from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from app.core.config import settings
from app.core.database import db
from app.models.user import UserInDB

# tokenUrl points to the OAuth2-compatible endpoint — this powers the Swagger 🔒 Authorize button
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

    # Convert ObjectId to string for Pydantic
    user_data["_id"] = str(user_data["_id"])
    return UserInDB(**user_data)
