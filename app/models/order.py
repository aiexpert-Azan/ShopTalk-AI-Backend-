from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class OrderItem(BaseModel):
    product_id: str = Field(..., alias="productId")
    name: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)

class OrderBase(BaseModel):
    customer_id: str = Field(..., alias="customerId")
    customer_name: str = Field(..., alias="customerName")
    customer_phone: str = Field(..., alias="customerPhone")
    items: List[OrderItem]
    total_amount: float = Field(..., alias="totalAmount")
    status: str = "new" # new, processing, ready, completed, rejected
    delivery_method: str = Field("delivery", alias="deliveryMethod")
    payment_method: str = Field("COD", alias="paymentMethod")
    notes: Optional[str] = None
    
class OrderTimeline(BaseModel):
    action: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: Optional[str] = None

class OrderCreate(OrderBase):
    pass

class OrderUpdateStatus(BaseModel):
    status: str

class OrderInDB(OrderBase):
    id: Optional[str] = Field(None, alias="_id")
    shop_id: str = Field(..., alias="shopId")
    timeline: List[OrderTimeline] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)

class OrderResponse(OrderInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)
