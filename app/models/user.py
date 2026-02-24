from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

class UserBase(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=30)
    phone: str = Field(..., min_length=11, max_length=11)
    email: EmailStr

    @field_validator('phone')
    @classmethod
    def validate_pakistani_phone(cls, v: str) -> str:
        """Validate Pakistani mobile number format."""
        if not v.isdigit():
            raise ValueError("Phone number must contain only digits")
        if len(v) != 11:
            raise ValueError("Phone number must be exactly 11 digits")
        if not v.startswith('03'):
            raise ValueError("Please enter a valid Pakistani mobile number starting with 03")
        return v

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
    hashed_password: str

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
