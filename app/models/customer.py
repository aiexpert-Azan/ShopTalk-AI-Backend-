from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class CustomerBase(BaseModel):
    name: str
    phone: str
    total_orders: int = Field(0, alias="totalOrders")
    total_spent: float = Field(0.0, alias="totalSpent")
    last_order_date: Optional[datetime] = Field(None, alias="lastOrderDate")

class CustomerInDB(CustomerBase):
    id: Optional[str] = Field(None, alias="_id")
    shop_id: str = Field(..., alias="shopId")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)

class CustomerResponse(CustomerInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)
