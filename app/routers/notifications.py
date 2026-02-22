from typing import List
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import UserInDB

router = APIRouter()

class Notification(BaseModel):
    id: str
    title: str
    description: str
    read: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)

@router.get("/", response_model=List[Notification])
async def get_notifications(current_user: UserInDB = Depends(get_current_user)):
    return [
        Notification(
            id="1", 
            title="New Order", 
            description="You have a new order from Ali.", 
            read=False
        )
    ]

@router.put("/{notification_id}/read")
async def mark_read(notification_id: str, current_user: UserInDB = Depends(get_current_user)):
    return {"message": "Marked as read"}
