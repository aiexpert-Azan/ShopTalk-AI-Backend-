from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class BusinessHoursDay(BaseModel):
    open: str = "09:00"
    close: str = "17:00"
    is_open: bool = Field(True, alias="isOpen")

class BusinessHours(BaseModel):
    monday: BusinessHoursDay = BusinessHoursDay()
    tuesday: BusinessHoursDay = BusinessHoursDay()
    wednesday: BusinessHoursDay = BusinessHoursDay()
    thursday: BusinessHoursDay = BusinessHoursDay()
    friday: BusinessHoursDay = BusinessHoursDay()
    saturday: BusinessHoursDay = BusinessHoursDay()
    sunday: BusinessHoursDay = BusinessHoursDay(isOpen=False)

class DeliverySettings(BaseModel):
    offer_delivery: bool = Field(False, alias="offerDelivery")
    areas: List[str] = []
    fee: float = 0.0

class AIConfig(BaseModel):
    active: bool = Field(True, alias="aiActive")
    reply_mode: str = Field("always", alias="replyMode") # always, businessHours, commonQuestions
    custom_greeting: Optional[str] = Field(None, alias="customGreeting")

class ShopBase(BaseModel):
    name: str = Field(..., max_length=30)
    category: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    ai_response_languages: List[str] = Field(default_factory=list, alias="aiResponseLanguages")

class ShopCreate(ShopBase):
    pass

class ShopUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=30)
    category: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    ai_response_languages: Optional[List[str]] = Field(None, alias="aiResponseLanguages")

class ShopInDB(ShopBase):
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(..., alias="userId")
    business_hours: BusinessHours = Field(default_factory=BusinessHours, alias="businessHours")
    delivery_settings: DeliverySettings = Field(default_factory=DeliverySettings, alias="deliverySettings")
    payment_methods: List[str] = Field(default_factory=list, alias="paymentMethods")
    ai_config: AIConfig = Field(default_factory=AIConfig, alias="aiConfig")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)

class ShopResponse(ShopInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)
