from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class Message(BaseModel):
    role: str # customer, ai, human
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_handled_by_ai: bool = Field(True, alias="isHandledByAI")

class ConversationBase(BaseModel):
    customer_id: str = Field(..., alias="customerId")
    customer_name: Optional[str] = Field(None, alias="customerName")
    messages: List[Message] = []
    ai_active: bool = Field(True, alias="aiActive")
    last_message: datetime = Field(default_factory=datetime.utcnow, alias="lastMessage")

class ConversationInDB(ConversationBase):
    id: Optional[str] = Field(None, alias="_id")
    shop_id: str = Field(..., alias="shopId")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)

class ConversationResponse(ConversationInDB):
    id: str = Field(..., alias="_id")
    model_config = ConfigDict(populate_by_name=True)

class ChatRequest(BaseModel):
    customer_id: str = Field(..., alias="customerId")
    message: str
    conversation_history: Optional[List[dict]] = Field(None, alias="conversationHistory")
