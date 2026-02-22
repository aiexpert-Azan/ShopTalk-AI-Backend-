from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    category: str
    image_url: Optional[str] = Field(None, alias="imageUrl")
    in_stock: bool = Field(True, alias="inStock")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    category: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    in_stock: Optional[bool] = Field(None, alias="inStock")

class ProductInDB(ProductBase):
    id: Optional[str] = Field(None, alias="_id")
    shop_id: str = Field(..., alias="shopId")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)

class ProductResponse(ProductInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)

class ProductListResponse(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    limit: int
