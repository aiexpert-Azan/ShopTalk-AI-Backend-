from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class TopQuestion(BaseModel):
    question: str
    count: int

class BusiestHour(BaseModel):
    label: str
    messages: int

class PopularProduct(BaseModel):
    name: str
    inquiries: int
    demand: str

class AutomatedSale(BaseModel):
    customer_name: str = Field(..., alias="customerName")
    interaction: str
    value: float

class InsightData(BaseModel):
    week_start_date: datetime = Field(..., alias="weekStartDate")
    top_questions: List[TopQuestion] = Field(default_factory=list, alias="topQuestions")
    busiest_hours: List[BusiestHour] = Field(default_factory=list, alias="busiestHours")
    popular_products: List[PopularProduct] = Field(default_factory=list, alias="popularProducts")
    automated_sales: List[AutomatedSale] = Field(default_factory=list, alias="automatedSales")
    ai_insight: str = Field(..., alias="aiInsight")

class InsightInDB(InsightData):
    id: Optional[str] = Field(None, alias="_id")
    shop_id: str = Field(..., alias="shopId")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)

class InsightResponse(InsightInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)
