from fastapi import Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from app.core.config import settings
import os

# Use the same tokenUrl as your OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login/token")

async def isAdmin(request: Request, token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        phone = payload.get("sub")
        role = payload.get("role")
        if not phone:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    admin_phone = os.getenv("ADMIN_PHONE_NUMBER", getattr(settings, "ADMIN_PHONE_NUMBER", None))
    if (admin_phone and phone == admin_phone) or (role == "admin"):
        return {"phone": phone, "role": role}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
