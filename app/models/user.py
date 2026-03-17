from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

class UserBase(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=30)
    phone: str = Field(..., min_length=10, max_length=15)
    email: Optional[EmailStr] = None

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Allow both 03XXXXXXXXX and +92XXXXXXXXX formats
        if v.startswith('+92') and len(v) == 13:
            return v
        if v.startswith('92') and len(v) == 12:
            return v
        if v.startswith('03') and len(v) == 11 and v.isdigit():
            return v
        raise ValueError("Please enter a valid Pakistani mobile number (03XXXXXXXXX or +92XXXXXXXXX)")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    phone: str
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=30)
    email: Optional[EmailStr] = None

class UserInDB(UserBase):
    id: Optional[str] = Field(None, alias="_id")
    plan: str = "starter"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    ai_active: bool = False
    phone_verified: bool = False
    hashed_password: Optional[str] = None  # Optional for Firebase users

    model_config = ConfigDict(populate_by_name=True)

class UserResponse(UserBase):
    id: str = Field(..., alias="_id")
    plan: str
    created_at: datetime
    is_active: bool
    ai_active: bool
    phone_verified: bool

    model_config = ConfigDict(populate_by_name=True)

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str